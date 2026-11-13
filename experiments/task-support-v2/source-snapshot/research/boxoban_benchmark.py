"""Case-guided push search on pinned Boxoban puzzles, separate from the ZHA core.

All puzzle tiles are observed. Retrieval estimates search priority; it is not
used as a move-validity oracle or claimed to be an admissible heuristic.
"""

from __future__ import annotations

import copy
import hashlib
import heapq
import itertools
import json
import math
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
import torch

from open_hierarchical_memory import (
    ExecutionMode,
    HierarchicalIndex,
    QueryBudget,
    ResourceLimitError,
    TreeConfig,
)

Method = Literal["matching", "linear", "dense", "top16", "zha", "random_values"]
DIRECTIONS = ((0, -1, "U"), (1, 0, "R"), (0, 1, "D"), (-1, 0, "L"))
FEATURE_VERSION = "boxoban-local-geometry-v1"


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True)
class State:
    player: int
    boxes: tuple[int, ...]


@dataclass(frozen=True)
class Level:
    split: str
    identifier: int
    rows: tuple[str, ...]
    width: int
    height: int
    floor: frozenset[int]
    goals: tuple[int, ...]
    initial: State

    @property
    def identity(self) -> str:
        return digest({"rows": self.rows})

    def step(self, cell: int, direction: int) -> int | None:
        dx, dy, _ = DIRECTIONS[direction]
        x, y = cell % self.width + dx, cell // self.width + dy
        if 0 <= x < self.width and 0 <= y < self.height:
            nxt = y * self.width + x
            return nxt if nxt in self.floor else None
        return None


def parse_levels(text: str, split: str) -> tuple[Level, ...]:
    """Parse fixed ASCII levels; do not interpret arbitrary input as code."""
    result: list[Level] = []
    for block in text.split(";")[1:]:
        lines = block.splitlines()
        identifier = int(lines[0].strip())
        rows = tuple(line.rstrip("\r") for line in lines[1:] if line)
        if not rows or len(rows) > 40 or max(map(len, rows)) > 40:
            raise ValueError("invalid or oversized board")
        width = len(rows[0])
        if any(len(row) != width or set(row) - set("# @$.*+") for row in rows):
            raise ValueError("board must be rectangular with supported symbols")
        floor = frozenset(
            y * width + x for y, row in enumerate(rows) for x, c in enumerate(row) if c != "#"
        )
        boxes = tuple(
            y * width + x for y, row in enumerate(rows) for x, c in enumerate(row) if c in "$*"
        )
        goals = tuple(
            y * width + x for y, row in enumerate(rows) for x, c in enumerate(row) if c in ".*+"
        )
        players = [
            y * width + x for y, row in enumerate(rows) for x, c in enumerate(row) if c in "@+"
        ]
        if len(players) != 1 or len(boxes) != len(goals) or not 1 <= len(boxes) <= 4:
            raise ValueError("expected one player and one to four matched boxes/goals")
        result.append(
            Level(split, identifier, rows, width, len(rows), floor, goals, State(players[0], boxes))
        )
    if not result or len({level.identifier for level in result}) != len(result):
        raise ValueError("missing or duplicate level IDs")
    return tuple(result)


def reachable(level: Level, state: State) -> dict[int, str]:
    occupied = set(state.boxes)
    paths = {state.player: ""}
    todo = deque([state.player])
    while todo:
        cell = todo.popleft()
        for direction, (_, _, letter) in enumerate(DIRECTIONS):
            nxt = level.step(cell, direction)
            if nxt is not None and nxt not in occupied and nxt not in paths:
                paths[nxt] = paths[cell] + letter
                todo.append(nxt)
    return paths


def state_key(level: Level, state: State) -> tuple[int, tuple[int, ...]]:
    return min(reachable(level, state)), state.boxes


def replay(level: Level, moves: str, start: State | None = None) -> State:
    state = level.initial if start is None else start
    for letter in moves:
        try:
            direction = next(i for i, (_, _, c) in enumerate(DIRECTIONS) if c == letter)
        except StopIteration as exc:
            raise ValueError("unknown move") from exc
        nxt = level.step(state.player, direction)
        if nxt is None:
            raise ValueError("walk into a wall")
        boxes = set(state.boxes)
        if nxt in boxes:
            beyond = level.step(nxt, direction)
            if beyond is None or beyond in boxes:
                raise ValueError("illegal push")
            boxes.remove(nxt)
            boxes.add(beyond)
        state = State(nxt, tuple(sorted(boxes)))
    return state


class Geometry:
    """Exact static reverse-push distances and a box-goal assignment bound."""

    def __init__(self, level: Level):
        self.level = level
        self.distances: list[dict[int, int]] = []
        for goal in level.goals:
            distances = {goal: 0}
            todo = deque([goal])
            while todo:
                cell = todo.popleft()
                for direction in range(4):
                    previous = level.step(cell, (direction + 2) % 4)
                    support = (
                        None if previous is None else level.step(previous, (direction + 2) % 4)
                    )
                    if previous is not None and support is not None and previous not in distances:
                        distances[previous] = distances[cell] + 1
                        todo.append(previous)
            self.distances.append(distances)
        self.dead = level.floor - set().union(*(set(d) for d in self.distances))
        self.cache: dict[tuple[int, ...], float] = {}

    def lower_bound(self, boxes: tuple[int, ...]) -> float:
        if boxes not in self.cache:
            self.cache[boxes] = min(
                sum(
                    self.distances[g].get(box, math.inf)
                    for box, g in zip(boxes, assignment, strict=True)
                )
                for assignment in itertools.permutations(range(len(boxes)))
            )
        return self.cache[boxes]

    def blocked_square(self, boxes: tuple[int, ...]) -> bool:
        occupied = set(boxes)
        level = self.level
        for box in boxes:
            x, y = box % level.width, box // level.width
            for dx, dy in ((0, 0), (-1, 0), (0, -1), (-1, -1)):
                cells = [(x + dx + a, y + dy + b) for a, b in ((0, 0), (1, 0), (0, 1), (1, 1))]
                if not all(0 <= a < level.width and 0 <= b < level.height for a, b in cells):
                    continue
                square = {b * level.width + a for a, b in cells}
                if all(c not in level.floor or c in occupied for c in square) and bool(
                    (square & occupied) - set(level.goals)
                ):
                    return True
        return False


def successors(level: Level, state: State, geometry: Geometry) -> list[tuple[State, str]]:
    paths = reachable(level, state)
    occupied = set(state.boxes)
    result = []
    for box in state.boxes:
        for direction, (_, _, letter) in enumerate(DIRECTIONS):
            support = level.step(box, (direction + 2) % 4)
            target = level.step(box, direction)
            if (
                support not in paths
                or target is None
                or target in occupied
                or target in geometry.dead
            ):
                continue
            boxes = tuple(sorted((occupied - {box}) | {target}))
            if not geometry.blocked_square(boxes) and math.isfinite(geometry.lower_bound(boxes)):
                result.append((State(box, boxes), paths[support] + letter))
    return result


def features(
    level: Level, state: State, geometry: Geometry
) -> np.ndarray[Any, np.dtype[np.float64]]:
    """Fixed local motifs and relative geometry, not puzzle/state identifiers."""
    walls: list[float] = []
    goals: list[float] = []
    occupied = set(state.boxes)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            wall = goal = other = 0
            for box in state.boxes:
                x, y = box % level.width + dx, box // level.width + dy
                cell = y * level.width + x
                inside = 0 <= x < level.width and 0 <= y < level.height
                wall += int(not inside or cell not in level.floor)
                goal += int(inside and cell in level.goals)
                other += int(inside and cell in occupied and (dx != 0 or dy != 0))
            walls.extend((wall / 4, other / 4))
            goals.append(goal / 4)
    distances = sorted(
        min(
            (abs(b % level.width - g % level.width) + abs(b // level.width - g // level.width))
            for g in level.goals
        )
        / 20
        for b in state.boxes
    )
    distances += [0.0] * (4 - len(distances))
    bound = geometry.lower_bound(state.boxes)
    raw = np.asarray(
        [
            1.0,
            *walls,
            *goals,
            *distances,
            bound / 40,
            len(reachable(level, state)) / 100,
            len(occupied & set(level.goals)) / 4,
        ],
        dtype=np.float64,
    )
    return raw / max(float(np.linalg.norm(raw)), 1e-12) * 12.0


def symmetry_key(level: Level) -> str:
    """Eight board symmetries, including equivalent player-region starts."""
    region = reachable(level, level.initial)
    candidates = []
    for reflected in (False, True):
        for turns in range(4):
            groups = []
            for cells in (level.floor, level.goals, level.initial.boxes, region):
                transformed = []
                for cell in cells:
                    x, y = cell % level.width, cell // level.width
                    if reflected:
                        x = level.width - 1 - x
                    width, height = level.width, level.height
                    for _ in range(turns):
                        x, y, width, height = height - 1 - y, x, height, width
                    transformed.append((x, y))
                groups.append(sorted(transformed))
            candidates.append(json.dumps(groups, separators=(",", ":")))
    return hashlib.sha256(min(candidates).encode()).hexdigest()


@dataclass(frozen=True)
class Case:
    split: str
    level_id: int
    level_hash: str
    player: int
    boxes: tuple[int, ...]
    remaining_pushes: int
    lower_bound: float
    feature: tuple[float, ...]

    @property
    def gap(self) -> float:
        return self.remaining_pushes - self.lower_bound


class CaseReader:
    """Same fixed observed case bank, with all retrieval work charged."""

    def __init__(self, cases: tuple[Case, ...], method: Method, *, p: float = 0.8):
        if method not in {"matching", "linear", "dense", "top16", "zha", "random_values"}:
            raise ValueError("unsupported search reader")
        if not cases or any(
            c.split != "train" or c.gap < 0 or not math.isfinite(c.gap) for c in cases
        ):
            raise ValueError("case bank requires finite solved training observations")
        if len({len(c.feature) for c in cases}) != 1:
            raise ValueError("inconsistent case dimensions")
        if (
            len(cases) > 512
            or not 1 <= len(cases[0].feature) <= 512
            or not all(math.isfinite(v) for c in cases for v in c.feature)
        ):
            raise ValueError("case bank exceeds bounded finite domain")
        self.method = method
        self.p = p
        self.cases = cases
        self.logs: list[dict[str, Any]] = []
        self.calls = self.failed_calls = 0
        self.raw_key_scores = self.raw_value_reads = self.summary_dot_products = 0
        self.query_seconds = 0.0
        self.index: HierarchicalIndex | None = None
        self.index_build_seconds = 0.0
        self.index_bytes = 0
        self.coefficients: np.ndarray[Any, np.dtype[np.float64]] | None = None
        started = time.perf_counter()
        array = np.asarray([c.feature for c in cases], dtype=np.float64)
        self.keys = torch.from_numpy(np.vstack((np.zeros((1, array.shape[1])), array)))
        labels = np.asarray([0.0, *(c.gap for c in cases)], dtype=np.float64)
        if method == "random_values":
            labels[1:] = np.random.default_rng(23).permutation(labels[1:])
        self.values = torch.from_numpy(labels)
        if method == "linear":
            design = np.column_stack((np.ones(len(cases)), array))
            target = labels[1:]
            penalty = np.eye(design.shape[1]) * 0.1
            self.coefficients = np.linalg.solve(design.T @ design + penalty, design.T @ target)
        elif method == "zha":
            positions = np.linspace(1, len(cases), min(8, len(cases)), dtype=int)
            references = self.keys[positions].reshape(1, len(positions), -1)
            self.index = HierarchicalIndex(
                self.keys.reshape(1, 1, len(cases) + 1, -1),
                self.values.reshape(1, 1, len(cases) + 1, 1),
                references,
                config=TreeConfig(chunk_size=8, depth=2),
            )
            self.index_bytes = self.index.info.owned_tensor_bytes
        self.index_build_seconds = time.perf_counter() - started
        self.input_tensor_bytes = self.keys.numel() * 8 + self.values.numel() * 8

    def estimate(self, feature: np.ndarray[Any, np.dtype[np.float64]], state: State) -> float:
        if self.method == "matching":
            return 0.0
        self.calls += 1
        started = time.perf_counter()
        query = torch.from_numpy(feature)
        selected: list[int] | None = None
        try:
            if self.method == "linear":
                assert self.coefficients is not None
                value = float(np.r_[1.0, feature] @ self.coefficients)
                dots = 0
                scored = used = 0
            elif self.index is not None:
                result = self.index.attend(
                    query.reshape(1, 1, 1, -1),
                    visible_counts=torch.tensor([[len(self.cases) + 1]], dtype=torch.int64),
                    mode=ExecutionMode.PAPER_APPROXIMATE,
                    p=self.p,
                    budget=QueryBudget(max_scored_nodes=512, max_attention_pairs=128),
                )
                route = result.routes[0]
                value = float(result.output[0, 0, 0, 0])
                selected = list(route.selected_ids)
                scored = used = len(selected)
                dots = route.scored_nodes * self.index.info.reference_count
            else:
                logits = (self.keys * query).sum(dim=-1) / math.sqrt(len(feature))
                scored = len(logits)
                if self.method == "top16":
                    selected = torch.argsort(logits, descending=True, stable=True)[:16].tolist()
                    if 0 not in selected:
                        selected.append(0)
                    ids = torch.tensor(selected, dtype=torch.int64)
                    value = float(torch.softmax(logits[ids], dim=0) @ self.values[ids])
                    used = len(selected)
                else:
                    value = float(torch.softmax(logits, dim=0) @ self.values)
                    used = scored
                dots = 0
            self.raw_key_scores += scored
            self.raw_value_reads += used
            self.summary_dot_products += dots
            self.logs.append(
                {
                    "player": state.player,
                    "boxes": list(state.boxes),
                    "query": feature.tolist(),
                    "selected_ids": selected,
                    "selected_count": used,
                    "raw_key_scores": scored,
                    "summary_dot_products": dots,
                    "value": value,
                }
            )
            return max(0.0, min(40.0, value))
        except ResourceLimitError:
            self.failed_calls += 1
            raise
        finally:
            self.query_seconds += time.perf_counter() - started

    def work(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "failed_calls": self.failed_calls,
            "failed_query_work_unknown": self.failed_calls,
            "raw_key_scores": self.raw_key_scores,
            "raw_value_reads": self.raw_value_reads,
            "summary_dot_products": self.summary_dot_products,
            "query_seconds": self.query_seconds,
            "index_build_seconds": self.index_build_seconds,
            "index_owned_tensor_bytes": self.index_bytes,
            "input_tensor_bytes": self.input_tensor_bytes,
        }


@dataclass(frozen=True)
class SearchNode:
    state: State
    pushes: int
    parent: int | None
    moves: str


def solve(
    level: Level,
    reader: CaseReader | None = None,
    *,
    expansion_limit: int = 2000,
    wall_seconds: float = 30.0,
    weight: float = 1.5,
) -> dict[str, Any]:
    """Bounded weighted A*; failures are returned, never counted as solves.

    Push edges contain actual player walks. Immutable parent nodes prevent
    canonical player-region merging from invalidating reconstructed paths.
    """
    if (
        type(expansion_limit) is not int
        or not 1 <= expansion_limit <= 100_000
        or not math.isfinite(wall_seconds)
        or wall_seconds <= 0
        or not math.isfinite(weight)
        or weight < 1
    ):
        raise ValueError("invalid search budget")
    started = time.perf_counter()
    log_start = 0 if reader is None else len(reader.logs)
    work_start = {} if reader is None else reader.work()
    geometry = Geometry(level)
    nodes = [SearchNode(level.initial, 0, None, "")]
    initial_key = state_key(level, level.initial)
    best = {initial_key: 0}
    queue: list[tuple[float, int]] = [(geometry.lower_bound(level.initial.boxes), 0)]
    expanded: list[dict[str, Any]] = []
    generated = duplicates = 0
    max_queue = 1
    winner: int | None = None
    status = "exhausted"
    error: str | None = None
    while queue:
        if len(expanded) >= expansion_limit:
            status = "expansion_limit"
            break
        if time.perf_counter() - started >= wall_seconds:
            status = "wall_timeout"
            break
        priority, index = heapq.heappop(queue)
        node = nodes[index]
        key = state_key(level, node.state)
        if node.pushes != best.get(key):
            continue
        expanded.append(
            {
                "player": node.state.player,
                "boxes": list(node.state.boxes),
                "pushes": node.pushes,
                "priority": priority,
                "frontier": len(queue),
            }
        )
        if set(node.state.boxes) == set(level.goals):
            winner, status = index, "solved"
            break
        try:
            for nxt, moves in successors(level, node.state, geometry):
                generated += 1
                nxt_key = state_key(level, nxt)
                cost = node.pushes + 1
                if best.get(nxt_key, 1_000_000) <= cost:
                    duplicates += 1
                    continue
                bound = geometry.lower_bound(nxt.boxes)
                gap = (
                    0.0
                    if reader is None
                    or reader.method == "matching"
                    or set(nxt.boxes) == set(level.goals)
                    else reader.estimate(features(level, nxt, geometry), nxt)
                )
                best[nxt_key] = cost
                nodes.append(SearchNode(nxt, cost, index, moves))
                heapq.heappush(queue, (cost + weight * (bound + gap), len(nodes) - 1))
            max_queue = max(max_queue, len(queue))
        except ResourceLimitError as exc:
            status, error = "retrieval_budget", str(exc)
            break
    path: list[dict[str, Any]] = []
    if winner is not None:
        cursor: int | None = winner
        while cursor is not None:
            node = nodes[cursor]
            path.append(
                {
                    "player": node.state.player,
                    "boxes": list(node.state.boxes),
                    "pushes": node.pushes,
                    "moves_from_previous": node.moves,
                }
            )
            cursor = node.parent
        path.reverse()
        moves = "".join(str(row["moves_from_previous"]) for row in path)
        end = replay(level, moves)
        if end != nodes[winner].state or set(end.boxes) != set(level.goals):
            raise AssertionError("search produced an invalid solution")
    else:
        moves = ""
    work = {} if reader is None else reader.work()
    for field in (
        "calls",
        "failed_calls",
        "failed_query_work_unknown",
        "raw_key_scores",
        "raw_value_reads",
        "summary_dot_products",
        "query_seconds",
    ):
        if reader is not None:
            work[field] -= work_start[field]
    if reader is not None:
        work["lifetime_reader_setup_seconds"] = work.pop("index_build_seconds")
    result = {
        "schema": "boxoban-search-v1",
        "split": level.split,
        "level_id": level.identifier,
        "level_hash": level.identity,
        "rows": list(level.rows),
        "method": "matching" if reader is None else reader.method,
        "status": status,
        "error": error,
        "success": winner is not None,
        "pushes": None if winner is None else nodes[winner].pushes,
        "moves": moves,
        "path": path,
        "expanded": len(expanded),
        "generated": generated,
        "duplicates": duplicates,
        "max_frontier": max_queue,
        "stored_search_nodes": len(nodes),
        "expanded_trace": expanded,
        "expansion_limit": expansion_limit,
        "wall_limit": wall_seconds,
        "weight": weight,
        "read_work": work,
        "reads": [] if reader is None else copy.deepcopy(reader.logs[log_start:]),
    }
    result["wall_seconds"] = time.perf_counter() - started
    return result


def make_cases(level: Level, solution: dict[str, Any], limit: int = 16) -> tuple[Case, ...]:
    if (
        level.split != "train"
        or not solution["success"]
        or solution["level_hash"] != level.identity
    ):
        raise ValueError("only solved training-level paths may produce cases")
    path = solution["path"]
    if not path or len(path) - 1 != solution["pushes"]:
        raise ValueError("solution path and push count disagree")
    previous = level.initial
    for index, row in enumerate(path):
        current = State(row["player"], tuple(row["boxes"]))
        if row["pushes"] != index or replay(level, row["moves_from_previous"], previous) != current:
            raise ValueError("training path is not a valid observed transition chain")
        if index == 0 and current != level.initial:
            raise ValueError("training path does not start at the initial state")
        if index and len(set(previous.boxes) ^ set(current.boxes)) != 2:
            raise ValueError("each training macro must push one box")
        previous = current
    if (
        set(previous.boxes) != set(level.goals)
        or "".join(row["moves_from_previous"] for row in path) != solution["moves"]
    ):
        raise ValueError("training path does not finish at the claimed goal")
    geometry = Geometry(level)
    chosen = sorted(set(np.linspace(0, len(path) - 1, min(limit, len(path)), dtype=int).tolist()))
    result = []
    for index in chosen:
        row = path[index]
        state = State(row["player"], tuple(row["boxes"]))
        remaining = int(solution["pushes"] - row["pushes"])
        bound = geometry.lower_bound(state.boxes)
        if remaining < bound:
            raise AssertionError("training solution violates push lower bound")
        result.append(
            Case(
                "train",
                level.identifier,
                level.identity,
                state.player,
                state.boxes,
                remaining,
                bound,
                tuple(features(level, state, geometry).tolist()),
            )
        )
    return tuple(result)


def case_payload(cases: tuple[Case, ...]) -> dict[str, Any]:
    return {
        "schema": "boxoban-cases-v1",
        "feature_version": FEATURE_VERSION,
        "cases": [asdict(c) for c in cases],
        "hash": digest([asdict(c) for c in cases]),
    }
