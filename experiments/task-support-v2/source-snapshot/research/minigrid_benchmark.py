"""Observation-only MiniGrid planning with interchangeable historical-fact readers.

The controller never receives an environment handle. Outside its reader, persistent
spatial state is egomotion and a sixteen-pose loop-avoidance deque. The planning
map is reconstructed from selected historical facts and the current observation.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal, Protocol

import numpy as np
import torch

from open_hierarchical_memory import ExecutionMode, HierarchicalIndex, TreeConfig

ReaderName = Literal["zha", "zha_adaptive", "exact", "recency", "fifo", "none", "full"]
READERS = ("zha", "zha_adaptive", "exact", "recency", "fifo", "none", "full")
ADAPTIVE_P = (0.4, 0.6, 0.8, 0.95, 1.0)
DIRECTIONS = ((1, 0), (0, 1), (-1, 0), (0, -1))
COLORS = {"red": 0, "green": 1, "blue": 2, "purple": 3, "yellow": 4, "grey": 5}
OBJECTS = {
    "unseen": 0,
    "empty": 1,
    "wall": 2,
    "floor": 3,
    "door": 4,
    "key": 5,
    "ball": 6,
    "box": 7,
    "goal": 8,
    "lava": 9,
    "agent": 10,
}
FEATURE_VERSION = "minigrid-observed-semantic-position-v1"
DIMENSION = 30


@dataclass(frozen=True)
class Fact:
    id: int
    x: int
    y: int
    object: int
    color: int
    state: int
    first_seen: int
    observed_step: int
    previous: int | None = None
    cue: bool = False

    @property
    def position(self) -> tuple[int, int]:
        return self.x, self.y


@dataclass(frozen=True)
class ReadContext:
    """Official current cells and controller-owned egomotion; no remembered map."""

    position: tuple[int, int]
    direction: int
    mission: str
    inventory: tuple[int, int] | None
    current_facts: tuple[Fact, ...]
    step: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.position, tuple)
            or len(self.position) != 2
            or any(type(x) is not int or abs(x) > 64 for x in self.position)
            or type(self.direction) is not int
            or not 0 <= self.direction < 4
            or not isinstance(self.mission, str)
            or len(self.mission) > 1024
            or type(self.step) is not int
            or self.step < 0
            or not isinstance(self.current_facts, tuple)
            or len(self.current_facts) > 49
            or any(
                not isinstance(f, Fact) or f.id != 0 or f.observed_step != self.step
                for f in self.current_facts
            )
            or len({f.position for f in self.current_facts}) != len(self.current_facts)
        ):
            raise ValueError("invalid observation-bound read context")
        if self.inventory is not None and (
            not isinstance(self.inventory, tuple)
            or len(self.inventory) != 2
            or any(type(v) is not int for v in self.inventory)
            or self.inventory[0] not in (5, 6, 7)
            or not 0 <= self.inventory[1] <= 5
        ):
            raise ValueError("invalid observed inventory")


@dataclass(frozen=True)
class KnownCoverage:
    """Fixed observed-known bits only; no passability/object information."""

    bits: bytes
    version: int
    head_hash: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.bits, bytes)
            or len(self.bits) != 512
            or type(self.version) is not int
            or self.version < 0
            or len(self.head_hash) != 64
            or any(c not in "0123456789abcdef" for c in self.head_hash)
        ):
            raise ValueError("invalid fixed64x64 known-coverage mask")

    def contains(self, point: tuple[int, int]) -> bool:
        x, y = point
        if not (-32 <= x < 32 and -32 <= y < 32):
            return False
        index = (y + 32) * 64 + x + 32
        return bool(self.bits[index // 8] & (1 << (index % 8)))

    def serialized(self) -> dict[str, Any]:
        return {
            "origin": [-32, -32],
            "width": 64,
            "height": 64,
            "version": self.version,
            "head_hash": self.head_hash,
            "bits_hex": self.bits.hex(),
            "binary_bytes": len(self.bits),
        }


class ContextualFactReader(Protocol):
    costs: dict[str, int | float]

    def observe(self, visible: list[Fact]) -> list[Fact]: ...

    def select_with_context(
        self, queries: torch.Tensor, context: ReadContext
    ) -> tuple[list[Fact], list[dict[str, Any]], dict[str, Any], KnownCoverage | None]: ...

    def archive(self) -> list[dict[str, Any]]: ...


def normalize_observation(observation: dict[str, Any]) -> dict[str, Any]:
    if set(observation) != {"image", "direction", "mission"}:
        raise ValueError("controller accepts only official image/direction/mission")
    image = np.asarray(observation["image"])
    if image.shape != (7, 7, 3) or image.dtype != np.uint8:
        raise ValueError("expected official uint8 partial image7x7x3")
    direction = observation["direction"]
    if (
        isinstance(direction, (bool, np.bool_))
        or not isinstance(direction, (int, np.integer))
        or not 0 <= int(direction) < 4
    ):
        raise ValueError("invalid compass observation")
    if not isinstance(observation["mission"], str) or len(observation["mission"]) > 1024:
        raise ValueError("invalid mission")
    if (
        bool((image[:, :, 0] > 10).any())
        or bool((image[:, :, 1] > 5).any())
        or bool((image[:, :, 2] > 2).any())
    ):
        raise ValueError("unsupported symbolic image encoding")
    return {"image": image.copy(), "direction": int(direction), "mission": observation["mission"]}


def serial_observation(observation: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_observation(observation)
    return {**normalized, "image": normalized["image"].tolist()}


def observed_cells(
    observation: dict[str, Any], position: tuple[int, int], step: int
) -> tuple[list[Fact], tuple[int, int] | None]:
    obs = normalize_observation(observation)
    forward = DIRECTIONS[obs["direction"]]
    right = DIRECTIONS[(obs["direction"] + 1) % 4]
    image = obs["image"]
    cells = []
    carried = (
        (int(image[3, 6, 0]), int(image[3, 6, 1])) if int(image[3, 6, 0]) in (5, 6, 7) else None
    )
    for vx in range(7):
        for vy in range(7):
            obj, color, state = (int(v) for v in image[vx, vy])
            if obj == 0:
                continue
            x = position[0] + forward[0] * (6 - vy) + right[0] * (vx - 3)
            y = position[1] + forward[1] * (6 - vy) + right[1] * (vx - 3)
            if abs(x) > 64 or abs(y) > 64:
                raise ValueError("egomotion exceeds declared coordinate support")
            if (vx, vy) == (3, 6):
                obj, color, state = 1, 0, 0  # carrying is inventory, not a ground object
            cells.append(Fact(0, x, y, obj, color, state, step, step))
    visible = {cell.position: cell for cell in cells}
    tagged = []
    for cell in cells:
        directions = [
            i
            for i, (dx, dy) in enumerate(DIRECTIONS)
            if (neighbor := visible.get((cell.x + dx, cell.y + dy))) is not None
            and neighbor.object in (1, 3, 8)
        ]
        # Explicit observed-topology heuristic: sample room objects have
        # orthogonal free neighbors; Memory choice markers occupy straight paths.
        cue = cell.object in (5, 6) and any(
            (a - b) % 2 == 1 for a in directions for b in directions
        )
        tagged.append(replace(cell, cue=cue))
    return tagged, carried


def position_features(position: tuple[int, int]) -> torch.Tensor:
    return torch.tensor(
        [
            2.0 * fn(frequency * math.pi * coordinate / 128.0)
            for coordinate in position
            for frequency in (1, 2, 4)
            for fn in (math.cos, math.sin)
        ],
        dtype=torch.float64,
    )


def fact_features(fact: Fact) -> torch.Tensor:
    vector = torch.zeros(DIMENSION, dtype=torch.float64)
    vector[:12] = position_features(fact.position)
    vector[12 + fact.object] = 4.0
    vector[23 + fact.color] = 2.0
    vector[-1] = 6.0 * fact.cue
    return vector


def query_vectors(position: tuple[int, int], mission: str) -> torch.Tensor:
    local = torch.zeros(DIMENSION, dtype=torch.float64)
    local[:12] = position_features(position)
    task = torch.zeros(DIMENSION, dtype=torch.float64)
    task[12 + 8] = 8.0
    task[12 + 5] = 6.0
    task[12 + 4] = 4.0
    if "pick up" in mission:
        kind = next((name for name in ("ball", "box", "key") if name in mission), "ball")
        task[12 + OBJECTS[kind]] = 8.0
        for color, index in COLORS.items():
            if color in mission:
                task[23 + index] = 3.0
    queries = [local, task]
    if "matching" in mission:
        sample = torch.zeros(DIMENSION, dtype=torch.float64)
        sample[-1] = 8.0
        queries.append(sample)
    return torch.stack(queries)


def fixed_references() -> torch.Tensor:
    references = []
    for obj in (8, 5, 4, 6):
        vector = torch.zeros(DIMENSION, dtype=torch.float64)
        vector[12 + obj] = 8.0
        references.append(vector)
    sample = torch.zeros(DIMENSION, dtype=torch.float64)
    sample[-1] = 8.0
    references.append(sample)
    for position in ((-16, 0), (16, 0), (0, 16)):
        vector = torch.zeros(DIMENSION, dtype=torch.float64)
        vector[:12] = position_features(position)
        references.append(vector)
    return torch.stack(references)[None]


class FactReader:
    """Reader-owned canonical history; controller cannot consult its full map."""

    def __init__(self, name: ReaderName, capacity: int = 96) -> None:
        if name not in READERS or type(capacity) is not int or not 8 <= capacity <= 256:
            raise ValueError("unsupported reader/capacity")
        self.name = name
        self.capacity = capacity
        self._records: list[Fact] = []
        self._heads: dict[tuple[int, int], int] = {}
        self._last_seen: dict[int, int] = {}
        self._index: HierarchicalIndex | None = None
        self._index_ids: list[int] = []
        self._keys = torch.empty((0, DIMENSION), dtype=torch.float64)
        self._dirty = True
        self.costs: dict[str, int | float] = {
            key: 0
            for key in (
                "index_builds",
                "index_owned_tensor_bytes_peak",
                "scored_nodes",
                "summary_dot_products",
                "raw_attention_pairs",
                "rerank_pairs",
                "exact_score_pairs",
                "returned_facts",
                "routing_passes",
                "full_candidate_fallbacks",
            )
        }
        self.costs.update(index_rebuild_seconds=0.0, retrieval_seconds=0.0)

    def observe(self, visible: list[Fact]) -> list[Fact]:
        added = []
        for cell in visible:
            previous_id = self._heads.get(cell.position)
            previous = self._records[previous_id - 1] if previous_id else None
            same_object = previous is not None and (previous.object, previous.color) == (
                cell.object,
                cell.color,
            )
            cue = cell.cue or bool(same_object and previous and previous.cue)
            if previous is not None and (
                previous.object,
                previous.color,
                previous.state,
                previous.cue,
            ) == (cell.object, cell.color, cell.state, cue):
                self._last_seen[previous.id] = cell.observed_step
                continue
            if len(self._records) >= 8192:
                raise ValueError("episode exceeds8192 original facts")
            record = replace(
                cell,
                id=len(self._records) + 1,
                previous=previous_id,
                first_seen=previous.first_seen if previous else cell.observed_step,
                cue=cue,
            )
            self._records.append(record)
            self._heads[cell.position] = record.id
            self._last_seen[record.id] = record.observed_step
            self._dirty = True
            added.append(record)
        return added

    def _build(self, records: list[Fact]) -> None:
        started = time.perf_counter()
        self._index_ids = [fact.id for fact in records]
        self._keys = torch.stack(
            [
                torch.zeros(DIMENSION, dtype=torch.float64),
                *[fact_features(fact) for fact in records],
            ]
        )
        values = torch.tensor(
            [
                [0.0, 0.0, 0.0],
                *[[float(f.object), float(f.color), float(f.state)] for f in records],
            ],
            dtype=torch.float64,
        )
        self._index = HierarchicalIndex(
            self._keys[None, None],
            values[None, None],
            fixed_references(),
            config=TreeConfig(chunk_size=4, depth=3),
        )
        self.costs["index_builds"] += 1
        self.costs["index_rebuild_seconds"] += time.perf_counter() - started
        self.costs["index_owned_tensor_bytes_peak"] = max(
            self.costs["index_owned_tensor_bytes_peak"], self._index.info.owned_tensor_bytes
        )
        self._dirty = False

    def select(self, queries: torch.Tensor) -> tuple[list[Fact], list[dict[str, Any]]]:
        started = time.perf_counter()
        if (
            not isinstance(queries, torch.Tensor)
            or queries.dtype != torch.float64
            or queries.device.type != "cpu"
            or queries.ndim != 2
            or queries.shape[1] != DIMENSION
            or not 1 <= queries.shape[0] <= 8
            or not bool(torch.isfinite(queries).all())
        ):
            raise ValueError("queries must be finite CPU float64[1..8,30]")
        current = [self._records[i - 1] for i in sorted(self._heads.values())]
        trace: list[dict[str, Any]] = []
        if self.name == "none" or not current:
            selected = []
        elif self.name == "full":
            selected = current
        elif self.name == "recency":
            selected = sorted(current, key=lambda f: (-self._last_seen[f.id], -f.id))[
                : self.capacity
            ]
        elif self.name == "fifo":
            selected = current[: self.capacity]
        else:
            if self._dirty:
                if self.name in ("zha", "zha_adaptive"):
                    self._build(current)
                else:
                    self._index_ids = [fact.id for fact in current]
                    self._keys = torch.stack(
                        [
                            torch.zeros(DIMENSION, dtype=torch.float64),
                            *[fact_features(fact) for fact in current],
                        ]
                    )
                    self._dirty = False
            if self.name in ("zha", "zha_adaptive"):
                assert self._index is not None
                candidate_union: set[int] = set()
                thresholds = ADAPTIVE_P if self.name == "zha_adaptive" else (0.4,)
                for attempt, threshold in enumerate(thresholds):
                    result = self._index.attend(
                        queries[None, None],
                        visible_counts=torch.full(
                            (1, queries.shape[0]), len(current) + 1, dtype=torch.int64
                        ),
                        mode=ExecutionMode.PAPER_APPROXIMATE,
                        p=threshold,
                        collect_trace=True,
                    )
                    self.costs["routing_passes"] += 1
                    if threshold == 1.0:
                        self.costs["full_candidate_fallbacks"] += 1
                    for route in result.routes:
                        candidate_union.update(i for i in route.selected_ids if i)
                        trace.append(
                            {
                                "attempt": attempt,
                                "p": threshold,
                                "query_index": route.query_index,
                                "selected_logical_ids": list(route.selected_ids),
                                "selected_fact_ids": [
                                    self._index_ids[i - 1] for i in route.selected_ids if i
                                ],
                                "steps": [
                                    {
                                        "level": step.level,
                                        "candidates": [node.index for node in step.candidates],
                                        "selected": [node.index for node in step.selected],
                                        "scores": list(step.scores),
                                    }
                                    for step in route.steps
                                ],
                                "attention_output": result.output[0, 0, route.query_index].tolist(),
                            }
                        )
                        self.costs["scored_nodes"] += route.scored_nodes
                        self.costs["summary_dot_products"] += route.scored_nodes * 8
                        self.costs["raw_attention_pairs"] += len(route.selected_ids)
                    # The only widening signal is original-candidate slot coverage.
                    # No planner connectivity, success, hidden cells or unselected
                    # scores influence stopping. p=1 is explicit full-candidate work.
                    if len(candidate_union) >= min(self.capacity, len(current)):
                        break
                candidates = sorted(candidate_union)
            else:
                candidates = list(range(1, len(current) + 1))
                self.costs["exact_score_pairs"] += len(current) * queries.shape[0]
            scores = (queries @ self._keys[candidates].T / math.sqrt(DIMENSION)).max(0).values
            positions = torch.argsort(scores, descending=True, stable=True)[
                : self.capacity
            ].tolist()
            selected = [self._records[self._index_ids[candidates[i] - 1] - 1] for i in positions]
            if self.name in ("zha", "zha_adaptive"):
                self.costs["rerank_pairs"] += len(candidates) * queries.shape[0]
        self.costs["retrieval_seconds"] += time.perf_counter() - started
        self.costs["returned_facts"] += len(selected)
        if self.name not in ("full", "none") and len(selected) > self.capacity:
            raise AssertionError("reader exceeded active fact limit")
        return selected, trace

    def archive(self) -> list[dict[str, Any]]:
        """Evaluator-only export; the policy never calls this method."""
        return [asdict(fact) for fact in self._records]


def can_move(
    cell: Fact | None, inventory: tuple[int, int] | None, *, planning: bool = False
) -> bool:
    if cell is None:
        return False
    if cell.object in (1, 3, 8):
        return True
    if cell.object == 4:
        return cell.state == 0 or (
            planning
            and (cell.state == 1 or (inventory is not None and inventory == (5, cell.color)))
        )
    return False


def observation_digest(observation: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(serial_observation(observation), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class ObservationPlanner:
    """A shared task-aware symbolic controller receiving no environment handle."""

    def __init__(
        self,
        reader: ReaderName,
        capacity: int = 96,
        *,
        injected_reader: ContextualFactReader | None = None,
        progress_repairs: bool = False,
    ) -> None:
        self.reader: FactReader | ContextualFactReader = (
            injected_reader if injected_reader is not None else FactReader(reader, capacity)
        )
        self.progress_repairs = progress_repairs
        self.position = (0, 0)
        self.direction: int | None = None
        self.previous_action: int | None = None
        self.previous_front: Fact | None = None
        self.recent: deque[tuple[int, int, int]] = deque(maxlen=16)
        self.step = 0

    def _advance(self, direction: int) -> None:
        if self.direction is None:
            self.direction = direction
            return
        expected = self.direction
        if self.previous_action == 0:
            expected = (expected - 1) % 4
        elif self.previous_action == 1:
            expected = (expected + 1) % 4
        elif self.previous_action == 2 and can_move(self.previous_front, None):
            dx, dy = DIRECTIONS[expected]
            self.position = (self.position[0] + dx, self.position[1] + dy)
        if direction != expected:
            raise ValueError("unexpected compass transition; hidden pose correction is prohibited")
        self.direction = direction

    def _turn(self, direction: int) -> int:
        assert self.direction is not None
        return 0 if (direction - self.direction) % 4 == 3 else 1

    def act(self, observation: dict[str, Any]) -> tuple[int, dict[str, Any], list[Fact]]:
        started = time.perf_counter()
        obs = normalize_observation(observation)
        self._advance(obs["direction"])
        visible, inventory = observed_cells(obs, self.position, self.step)
        additions = self.reader.observe(visible)
        queries = query_vectors(self.position, obs["mission"])
        receipt = None
        coverage = None
        if isinstance(self.reader, FactReader):
            recalled, trace = self.reader.select(queries)
        else:
            context = ReadContext(
                self.position,
                obs["direction"],
                obs["mission"],
                inventory,
                tuple(visible),
                self.step,
            )
            recalled, trace, receipt, coverage = self.reader.select_with_context(queries, context)
        planning_started = time.perf_counter()
        view = {fact.position: fact for fact in recalled}
        for cell in visible:
            past = view.get(cell.position)
            if past is not None and (past.object, past.color) == (cell.object, cell.color):
                cell = replace(cell, cue=cell.cue or past.cue)
            view[cell.position] = cell
        waypoint = None
        if self.progress_repairs and receipt is not None and receipt.get("waypoint_id"):
            waypoint = next((f for f in recalled if f.id == receipt["waypoint_id"]), None)
            if waypoint is None:
                raise ValueError("waypoint is not an explicitly returned fact")
        action, objective, goal, sources, plan = self._plan(
            view, inventory, obs["mission"], known_coverage=coverage, waypoint=waypoint
        )
        assert self.direction is not None
        dx, dy = DIRECTIONS[self.direction]
        self.previous_front = next(
            (f for f in visible if f.position == (self.position[0] + dx, self.position[1] + dy)),
            None,
        )
        decision = {
            "pose": [*self.position, self.direction],
            "inventory": inventory,
            "memory_ids": [fact.id for fact in recalled],
            "memory_facts": [asdict(fact) for fact in recalled],
            "current_facts": [asdict(fact) for fact in visible],
            "queries": queries.tolist(),
            "route": trace,
            "objective": objective,
            "goal": goal,
            "goal_sources": sources,
            "plan": plan,
            "plan_fact_ids": [view[p].id for p in plan if p in view and view[p].id],
            "recent_history": list(self.recent),
            "work": self.reader.costs.copy(),
            "planning_seconds": time.perf_counter() - planning_started,
            "policy_seconds": time.perf_counter() - started,
        }
        if receipt is not None:
            decision["dependency"] = receipt
        if coverage is not None:
            decision["coverage"] = coverage.serialized()
        self.previous_action = action
        self.recent.append((*self.position, self.direction))
        self.step += 1
        return action, decision, additions

    def _plan(
        self,
        view: dict[tuple[int, int], Fact],
        inventory: tuple[int, int] | None,
        mission: str,
        *,
        known_coverage: KnownCoverage | None = None,
        waypoint: Fact | None = None,
    ) -> tuple[int, str, tuple[int, int] | None, list[int], list[tuple[int, int]]]:
        assert self.direction is not None
        matching = "matching" in mission
        samples = [f for f in view.values() if f.cue and f.object in (5, 6)]
        sample = min(samples, key=lambda f: (f.first_seen, f.id, f.x, f.y)) if samples else None
        danger: set[tuple[int, int]] = set()
        if matching:
            for fact in view.values():
                if (
                    fact.object in (5, 6)
                    and not fact.cue
                    and (sample is None or fact.object != sample.object)
                ):
                    danger.update((fact.x + dx, fact.y + dy) for dx, dy in DIRECTIONS)
        queue = deque([self.position])
        parent: dict[tuple[int, int], tuple[int, int] | None] = {self.position: None}
        while queue:
            x, y = queue.popleft()
            for dx, dy in DIRECTIONS:
                point = (x + dx, y + dy)
                if (
                    point not in parent
                    and point not in danger
                    and can_move(view.get(point), inventory, planning=True)
                ):
                    parent[point] = (x, y)
                    queue.append(point)

        def path(point: tuple[int, int]) -> list[tuple[int, int]]:
            result = [point]
            while parent[result[-1]] is not None:
                previous = parent[result[-1]]
                assert previous is not None
                result.append(previous)
            return list(reversed(result))

        targets: list[tuple[int, Fact, bool]] = []
        if matching and sample is not None:
            targets = [
                (0, f, True)
                for f in view.values()
                if f.object == sample.object and f.color == sample.color and not f.cue
            ]
        elif "pick up" in mission:
            kind = next((OBJECTS[name] for name in ("ball", "box", "key") if name in mission), 6)
            color = next((index for name, index in COLORS.items() if name in mission), None)
            targets = [
                (0, f, True)
                for f in view.values()
                if f.object == kind and (color is None or f.color == color)
            ]
        else:
            targets = [(0, f, False) for f in view.values() if f.object == 8]
        needed = {f.color for f in view.values() if f.object == 4 and f.state == 2} - (
            {inventory[1]} if inventory and inventory[0] == 5 else set()
        )
        targets.extend(
            (1, f, True)
            for f in view.values()
            if f.object == 5 and (f.color in needed or (inventory is None and not matching))
        )
        choices = []
        for priority, target, adjacent in targets:
            points = (
                [(target.x + dx, target.y + dy) for dx, dy in DIRECTIONS]
                if adjacent
                else [target.position]
            )
            for point in points:
                if point in parent:
                    route = path(point)
                    choices.append(
                        (priority, len(route), target.id, point, target, adjacent, route)
                    )
        if choices:
            _, _, _, point, target, adjacent, route = min(choices, key=lambda item: item[:4])
            sources = [i for i in (target.id, sample.id if matching and sample else 0) if i]
            if len(route) > 1:
                objective = (
                    "matching-target"
                    if matching
                    else "goal"
                    if target.object in (6, 7, 8)
                    else "fetch-key"
                )
                return self._move(route[1], view), objective, point, sources, route
            if adjacent:
                desired = DIRECTIONS.index(
                    (target.x - self.position[0], target.y - self.position[1])
                )
                if matching:
                    return self._turn(desired), "matching-target-adjacent", point, sources, route
                if inventory is not None:
                    free = [
                        (direction, (self.position[0] + dx, self.position[1] + dy))
                        for direction, (dx, dy) in enumerate(DIRECTIONS)
                        if (cell := view.get((self.position[0] + dx, self.position[1] + dy)))
                        is not None
                        and cell.object == 1
                    ]
                    if free:
                        desired, _ = min(
                            free, key=lambda pair: (pair[0] != self.direction, pair[0])
                        )
                        return (
                            (4 if desired == self.direction else self._turn(desired)),
                            "drop-for-pickup",
                            point,
                            sources,
                            route,
                        )
                    if self.progress_repairs:
                        # A pickup with occupied hands cannot succeed. Seek a
                        # drop site using only this read's admitted raw facts.
                        staging = []
                        for standing in parent:
                            for facing, (dx, dy) in enumerate(DIRECTIONS):
                                empty = view.get((standing[0] + dx, standing[1] + dy))
                                if (
                                    empty is not None
                                    and empty.object == 1
                                    and empty.position != self.position
                                ):
                                    approach = path(standing)
                                    staging.append(
                                        (len(approach), standing, facing, approach, empty)
                                    )
                        if staging:
                            _, standing, facing, approach, empty = min(staging, key=lambda x: x[:3])
                            if len(approach) > 1:
                                return (
                                    self._move(approach[1], view),
                                    "seek-drop-space",
                                    standing,
                                    sources,
                                    approach,
                                )
                            return (
                                (4 if facing == self.direction else self._turn(facing)),
                                "drop-for-pickup",
                                standing,
                                sources,
                                approach,
                            )
                        return 1, "scan-for-drop-space", None, sources, [self.position]
                return (
                    (3 if desired == self.direction else self._turn(desired)),
                    "pickup-target",
                    point,
                    sources,
                    route,
                )
        if waypoint is not None:
            actual = view.get(waypoint.position)
            if (
                not self.progress_repairs
                or actual is None
                or (actual.object, actual.color, actual.state)
                != (waypoint.object, waypoint.color, waypoint.state)
            ):
                raise ValueError("invalid admitted waypoint")
            if waypoint.position in parent:
                route = path(waypoint.position)
                if len(route) > 1:
                    return (
                        self._move(route[1], view),
                        "follow-observed-waypoint",
                        waypoint.position,
                        [waypoint.id],
                        route,
                    )
        visits = Counter(self.recent)
        frontiers = []
        for point in parent:
            for direction, (dx, dy) in enumerate(DIRECTIONS):
                unknown = (point[0] + dx, point[1] + dy)
                if (
                    unknown not in view
                    and unknown not in danger
                    and (known_coverage is None or not known_coverage.contains(unknown))
                ):
                    route = path(point)
                    score = len(route) + 12 * visits[(*point, direction)]
                    frontiers.append((score, len(route), point[0], point[1], direction, route))
        if frontiers:
            _, _, _, _, desired, route = min(frontiers)
            if len(route) > 1:
                return self._move(route[1], view), "explore", route[-1], [], route
            return self._turn(desired), "scan-frontier", self.position, [], route
        doors = [
            (len(path(f.position)), f.position, path(f.position))
            for f in view.values()
            if f.object == 4 and f.state != 0 and f.position in parent
        ]
        if doors:
            _, point, route = min(doors)
            if len(route) > 1:
                return self._move(route[1], view), "open-door", point, [], route
        return 1, "scan-no-reachable-frontier", None, [], [self.position]

    def _move(self, point: tuple[int, int], view: dict[tuple[int, int], Fact]) -> int:
        assert self.direction is not None
        desired = DIRECTIONS.index((point[0] - self.position[0], point[1] - self.position[1]))
        if desired != self.direction:
            return self._turn(desired)
        return 5 if view[point].object == 4 and view[point].state != 0 else 2
