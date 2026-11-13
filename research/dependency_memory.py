"""Observed raw-fact bundles with explicit full-graph and coverage costs.

This is not sublinear retrieval: the reader derives an observed graph, and all
seed methods share nomination, closure and packing. No reader action reaches
its common planner. One-hop path halos do not claim global frontier closure.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any, Literal

import torch

from research.minigrid_benchmark import (
    COLORS,
    DIRECTIONS,
    OBJECTS,
    Fact,
    FactReader,
    KnownCoverage,
    ReadContext,
    ReaderName,
)

DependencyName = Literal[
    "flat_zha_mask",
    "flat_exact_mask",
    "flat_exact_history_mask",
    "bundle_zha",
    "bundle_exact",
    "bundle_recency",
    "graph",
]
DEPENDENCY_READERS = (
    "flat_zha_mask",
    "flat_exact_mask",
    "flat_exact_history_mask",
    "bundle_zha",
    "bundle_exact",
    "bundle_recency",
    "graph",
)
MAX_BUNDLES = 8
WORK_KEYS = (
    "flat_history_filter_items",
    "source_head_scan_items",
    "output_facts",
    "current_context_lookups",
    "graph_materialization_items",
    "path_node_visits",
    "seed_role_scan_items",
    "support_classification_items",
    "seed_identity_lookups",
    "head_scan_items",
    "head_hash_items",
    "graph_build_nodes",
    "graph_neighbor_checks",
    "nomination_items",
    "landmark_checks",
    "prerequisite_checks",
    "bfs_calls",
    "bfs_nodes",
    "bfs_edge_checks",
    "halo_lookups",
    "packing_checks",
    "coverage_bit_writes",
    "coverage_binary_bytes",
    "coverage_json_bytes",
    "residual_neighbor_checks",
    "bundles_complete",
    "bundles_overbudget",
    "bundles_missing",
    "bundles_packed",
)


def neighbors(point: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    return tuple((point[0] + dx, point[1] + dy) for dx, dy in DIRECTIONS)


def walkable(fact: Fact) -> bool:
    return fact.object in (1, 3, 4, 8)


@dataclass(frozen=True)
class Bundle:
    seed_id: int
    kind: str
    required_ids: tuple[int, ...]
    path_ids: tuple[int, ...]
    support_edges: tuple[tuple[int, int], ...]
    prerequisite_ids: tuple[int, ...]
    halo_ids: tuple[int, ...]
    current_support_ids: tuple[int, ...]
    historical_ids: tuple[int, ...]
    missing: tuple[str, ...]
    paths: tuple[tuple[int, ...], ...] = ()
    semantic_support_ids: tuple[int, ...] = ()


class ObservedGraph:
    """Per-read derived graph, never cached in the actor."""

    def __init__(self, heads: list[Fact], context: ReadContext, work: dict[str, int]) -> None:
        self.work = work
        self.context = context
        work["graph_materialization_items"] += 2 * len(heads)
        self.cells = {f.position: f for f in heads}
        self.by_id = {f.id: f for f in heads}
        self.adjacency: dict[tuple[int, int], tuple[tuple[int, int], ...]] = {}
        for fact in heads:
            work["graph_build_nodes"] += 1
            if not walkable(fact):
                continue
            nearby = []
            for point in neighbors(fact.position):
                work["graph_neighbor_checks"] += 1
                other = self.cells.get(point)
                if other is not None and walkable(other):
                    nearby.append(point)
            self.adjacency[fact.position] = tuple(nearby)
        self._searches: dict[
            frozenset[int] | None, dict[tuple[int, int], tuple[int, int] | None]
        ] = {}

    def search(
        self, colors: frozenset[int] | None
    ) -> dict[tuple[int, int], tuple[int, int] | None]:
        """None permits optimistic locked-door passage only for dependency finding."""
        if colors in self._searches:
            return self._searches[colors]
        self.work["bfs_calls"] += 1
        parent: dict[tuple[int, int], tuple[int, int] | None] = {self.context.position: None}
        queue = deque([self.context.position])
        while queue:
            point = queue.popleft()
            self.work["bfs_nodes"] += 1
            for nxt in self.adjacency.get(point, ()):
                self.work["bfs_edge_checks"] += 1
                cell = self.cells[nxt]
                if nxt in parent or (
                    colors is not None
                    and cell.object == 4
                    and cell.state == 2
                    and cell.color not in colors
                ):
                    continue
                parent[nxt] = point
                queue.append(nxt)
        self._searches[colors] = parent
        return parent

    def path(self, target: Fact, colors: frozenset[int] | None) -> list[Fact]:
        parent = self.search(colors)
        points = [target.position] if walkable(target) else list(neighbors(target.position))
        choices = []
        for point in points:
            if point not in parent:
                continue
            self.work["path_node_visits"] += 1
            route = [point]
            while parent[route[-1]] is not None:
                previous = parent[route[-1]]
                assert previous is not None
                self.work["path_node_visits"] += 1
                route.append(previous)
            route.reverse()
            choices.append(route)
        if not choices:
            return []
        route = min(choices, key=lambda path: (len(path), path[-1]))
        return [self.cells[p] for p in route]

    def bundle(self, seed: Fact, kind: str, semantic_support: tuple[Fact, ...] = ()) -> Bundle:
        self.work["seed_identity_lookups"] += 1 + len(semantic_support)
        if any(self.by_id.get(f.id) != f for f in (seed, *semantic_support)):
            raise ValueError("bundle seed/support is not a current canonical head")
        held = self.context.inventory
        available = frozenset([held[1]]) if held is not None and held[0] == 5 else frozenset()
        optimistic = self.path(seed, available) or self.path(seed, None)
        missing = []
        if not optimistic:
            missing.append("no_observed_route")
        prerequisite: list[Fact] = []
        supporting_paths: list[list[Fact]] = []
        locks = [f for f in optimistic if f.object == 4 and f.state == 2]
        if seed.object == 4 and seed.state == 2 and seed not in locks:
            locks.append(seed)
        for door in locks:
            if door.color in available:
                continue
            key_paths = []
            for candidate in self.cells.values():
                self.work["prerequisite_checks"] += 1
                if candidate.object == 5 and candidate.color == door.color:
                    route = self.path(candidate, available)
                    if route:
                        key_paths.append((len(route), candidate.id, candidate, route))
            if not key_paths:
                missing.append(f"unreachable_matching_key:{door.id}:{door.color}")
                continue
            _, _, key, route = min(key_paths, key=lambda item: item[:2])
            prerequisite.append(key)
            supporting_paths.append(route)
            available = available | {key.color}
        routes = [optimistic, *supporting_paths]
        path_facts = {f.id: f for path in routes for f in path}
        required = {
            seed.id: seed,
            **path_facts,
            **{f.id: f for f in prerequisite},
            **{f.id: f for f in semantic_support},
        }
        halo: dict[int, Fact] = {}
        for fact in path_facts.values():
            for point in neighbors(fact.position):
                self.work["halo_lookups"] += 1
                if (cell := self.cells.get(point)) is not None:
                    halo[cell.id] = cell
        required.update(halo)
        self.work["support_classification_items"] += len(required)
        visible = {f.position: f for f in self.context.current_facts}
        current = tuple(
            sorted(
                f.id
                for f in required.values()
                if f.position in visible and f.cue == visible[f.position].cue
            )
        )
        historical = tuple(sorted(set(required) - set(current)))
        edges = {(a.id, b.id) for path in routes for a, b in zip(path, path[1:], strict=False)}
        return Bundle(
            seed.id,
            kind,
            tuple(sorted(required)),
            tuple(sorted(path_facts)),
            tuple(sorted(edges)),
            tuple(sorted({f.id for f in prerequisite})),
            tuple(sorted(halo)),
            current,
            historical,
            tuple(missing),
            paths=tuple(tuple(f.id for f in path) for path in routes),
            semantic_support_ids=tuple(f.id for f in semantic_support),
        )


class DependencyReader:
    """Canonical observation owner plus explicitly charged structural adapter."""

    def __init__(self, name: DependencyName, capacity: int = 96) -> None:
        if name not in DEPENDENCY_READERS or type(capacity) is not int or not 8 <= capacity <= 192:
            raise ValueError("unsupported dependency reader/capacity")
        self.name, self.capacity = name, capacity
        source: ReaderName = (
            "zha_adaptive"
            if "zha" in name
            else "exact"
            if "exact" in name
            else "recency"
            if "recency" in name
            else "full"
        )
        self.source = FactReader(
            source, capacity + 49 if name == "flat_exact_history_mask" else capacity
        )
        self._heads: dict[tuple[int, int], Fact] = {}
        self._version = 0
        self._latest_step = -1
        self._visible: tuple[Fact, ...] = ()
        self.work = dict.fromkeys(WORK_KEYS, 0)
        self.costs: dict[str, int | float] = self.source.costs.copy()
        self._structural_seconds = 0.0

    def observe(self, visible: list[Fact]) -> list[Fact]:
        if (
            not isinstance(visible, list)
            or len(visible) > 49
            or any(
                not isinstance(f, Fact)
                or f.id != 0
                or any(
                    type(v) is not int
                    for v in (f.x, f.y, f.object, f.color, f.state, f.observed_step)
                )
                or not (-32 <= f.x < 32 and -32 <= f.y < 32)
                or not 1 <= f.object <= 10
                or not 0 <= f.color <= 5
                or not 0 <= f.state <= 2
                or f.observed_step < self._latest_step
                for f in visible
            )
            or len({f.position for f in visible}) != len(visible)
            or len({f.observed_step for f in visible}) > 1
        ):
            raise ValueError("expected bounded raw current visible facts in observation order")
        self._visible = tuple(visible)
        if visible:
            self._latest_step = visible[0].observed_step
        added = self.source.observe(visible)
        for fact in added:
            self._heads[fact.position] = fact
            self._version = fact.id
        return added

    def archive(self) -> list[dict[str, Any]]:
        return self.source.archive()

    def _coverage(self, heads: list[Fact], head_hash: str) -> KnownCoverage:
        bits = bytearray(512)
        for fact in heads:
            self.work["coverage_bit_writes"] += 1
            if not (-32 <= fact.x < 32 and -32 <= fact.y < 32):
                raise ValueError("observed coordinate outside declared64x64 coverage support")
            index = (fact.y + 32) * 64 + fact.x + 32
            bits[index // 8] |= 1 << (index % 8)
        coverage = KnownCoverage(bytes(bits), self._version, head_hash)
        self.work["coverage_binary_bytes"] += len(bits)
        self.work["coverage_json_bytes"] += len(
            json.dumps(coverage.serialized(), separators=(",", ":")).encode()
        )
        return coverage

    def select_with_context(
        self, queries: torch.Tensor, context: ReadContext
    ) -> tuple[list[Fact], list[dict[str, Any]], dict[str, Any], KnownCoverage | None]:
        if context.step != self._latest_step or context.current_facts != self._visible:
            raise ValueError("read context step differs from latest observed batch")
        before = self.work.copy()
        seeds, routes = self.source.select(queries)
        started = time.perf_counter()
        heads = sorted(self._heads.values(), key=lambda f: f.id)
        self.work["source_head_scan_items"] += len(heads)
        self.work["head_scan_items"] += len(heads)
        self.work["head_hash_items"] += len(heads)
        head_hash = hashlib.sha256(
            json.dumps([asdict(f) for f in heads], sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        for fact in context.current_facts:
            self.work["current_context_lookups"] += 1
            actual = self._heads.get(fact.position)
            if actual is None or (actual.object, actual.color, actual.state) != (
                fact.object,
                fact.color,
                fact.state,
            ):
                raise ValueError("read context is not backed by current canonical observations")
        coverage = self._coverage(heads, head_hash)
        receipt: dict[str, Any] = {
            "mode": self.name,
            "context": asdict(context),
            "source_head_hash": head_hash,
            "source_head_ids": [f.id for f in heads],
            "source_version": self._version,
            "seed_reader": self.source.name,
            "seed_ids": [f.id for f in seeds],
            "coverage_scope": "observed-known only;64x64 bits; no passability",
            "closure_scope": "one-hop halo of stated paths; not global frontier closure",
        }
        if self.name.startswith("flat_"):
            if self.name == "flat_exact_history_mask":
                visible_positions = {f.position for f in context.current_facts}
                self.work["flat_history_filter_items"] += len(seeds)
                selected = [f for f in seeds if f.position not in visible_positions][
                    : self.capacity
                ]
                receipt["history_excluded_ids"] = [
                    f.id for f in seeds if f.position in visible_positions
                ]
            else:
                selected = seeds
            receipt.update(bundles=[], status="flat_mask_only")
        else:
            selected, bundles = self._structural(heads, seeds, context)
            receipt.update(
                bundles=bundles,
                status="packed"
                if any(b["status"] == "complete" for b in bundles)
                else "structural_rejection",
            )
        effective = {f.position for f in [*selected, *context.current_facts]}
        residual = []
        for fact in [*selected, *context.current_facts]:
            if not walkable(fact):
                continue
            for point in neighbors(fact.position):
                self.work["residual_neighbor_checks"] += 1
                if point in self._heads and point not in effective:
                    residual.append([fact.x, fact.y, point[0], point[1], self._heads[point].id])
        receipt.update(
            returned_ids=[f.id for f in selected], residual_known_neighbor_omissions=residual
        )
        self.work["output_facts"] += len(selected)
        receipt["work_delta"] = {key: self.work[key] - before[key] for key in WORK_KEYS}
        self._structural_seconds += time.perf_counter() - started
        self.costs = {
            **self.source.costs,
            **{f"dependency_{k}": v for k, v in self.work.items()},
            "dependency_seconds": self._structural_seconds,
        }
        if len(selected) > self.capacity:
            raise AssertionError("structural adapter exceeded raw fact capacity")
        return selected, routes, receipt, coverage

    def pack_available_support(
        self,
        available: list[Fact],
        seeds: list[Fact],
        context: ReadContext,
        *,
        known_coverage: KnownCoverage | None = None,
    ) -> tuple[list[Fact], list[dict[str, Any]]]:
        """Pack only caller-authorized evidence; never consult this reader's archive.

        This public boundary lets lifecycle adapters withhold dormant content.
        Known-only coverage is not sufficient evidence to add an available cell.
        """
        by_id = {f.id: f for f in available}
        by_position = {f.position: f for f in available}
        if (
            len(by_id) != len(available)
            or len(by_position) != len(available)
            or any(f.id <= 0 or f.observed_step > context.step for f in available)
            or any(by_id.get(f.id) != f for f in seeds)
            or any(
                (head := by_position.get(f.position)) is None
                or (head.object, head.color, head.state) != (f.object, f.color, f.state)
                for f in context.current_facts
            )
        ):
            raise ValueError("support contains missing, future or conflicting evidence")
        return self._structural(available, seeds, context, known_coverage=known_coverage)

    def _structural(
        self,
        heads: list[Fact],
        seeds: list[Fact],
        context: ReadContext,
        *,
        known_coverage: KnownCoverage | None = None,
    ) -> tuple[list[Fact], list[dict[str, Any]]]:
        graph = ObservedGraph(heads, context, self.work)
        nominated = self._nominate(seeds, graph, context, known_coverage=known_coverage)
        self.work["seed_role_scan_items"] += len(seeds)
        cues = [f for f in seeds if f.cue and f.object in (5, 6)]
        cue = min(cues, key=lambda f: (f.first_seen, f.id)) if cues else None
        packed: set[int] = set()
        receipts = []
        for seed, kind in nominated:
            bundle = graph.bundle(seed, kind, (cue,) if kind == "matching_landmark" and cue else ())
            candidate = packed | set(bundle.historical_ids)
            self.work["packing_checks"] += len(candidate)
            if bundle.missing:
                status = "missing_prerequisite"
                self.work["bundles_missing"] += 1
            elif len(candidate) > self.capacity:
                status = "overbudget"
                self.work["bundles_overbudget"] += 1
            else:
                status = "complete"
                self.work["bundles_complete"] += 1
                self.work["bundles_packed"] += 1
                packed = candidate
            receipts.append(
                {
                    **asdict(bundle),
                    "status": status,
                    "required_historical_count": len(bundle.historical_ids),
                    "candidate_packed_count": len(candidate),
                    "omitted_ids": sorted(set(bundle.historical_ids) - packed),
                }
            )
        return [graph.by_id[i] for i in sorted(packed)], receipts

    def _nominate(
        self,
        seeds: list[Fact],
        graph: ObservedGraph,
        context: ReadContext,
        *,
        known_coverage: KnownCoverage | None = None,
    ) -> list[tuple[Fact, str]]:
        parent = graph.search(None)
        matching = "matching" in context.mission
        candidates = []
        self.work["seed_role_scan_items"] += len(seeds)
        samples = [f for f in seeds if f.cue and f.object in (5, 6)]
        sample = min(samples, key=lambda f: (f.first_seen, f.id)) if samples else None
        kind = next((OBJECTS[k] for k in ("ball", "box", "key") if k in context.mission), 6)
        color = next((value for name, value in COLORS.items() if name in context.mission), None)
        for seed in seeds:
            self.work["nomination_items"] += 1
            self.work["landmark_checks"] += 1
            role = None
            priority = 5
            if seed.cue and matching:
                priority, role = 0, "cue"
            elif (
                matching
                and sample
                and not seed.cue
                and (seed.object, seed.color) == (sample.object, sample.color)
            ):
                priority, role = 0, "matching_landmark"
            elif (
                "pick up" in context.mission
                and seed.object == kind
                and (color is None or seed.color == color)
            ):
                priority, role = 0, "mission_landmark"
            elif not matching and "pick up" not in context.mission and seed.object == 8:
                priority, role = 0, "goal_landmark"
            elif seed.object == 5 and not matching:
                priority, role = 1, "key_landmark"
            elif seed.object == 4 and seed.state != 0:
                priority, role = 2, "door_landmark"
            elif seed.position in parent and walkable(seed):
                if any(
                    point not in graph.cells
                    and (known_coverage is None or not known_coverage.contains(point))
                    for point in neighbors(seed.position)
                ):
                    priority, role = 3, "true_observed_frontier"
            if role is not None:
                route = graph.path(seed, None)
                if route or role != "true_observed_frontier":
                    candidates.append(
                        (priority, len(route) if route else 8193, seed.id, seed, role)
                    )
        return [
            (seed, role)
            for _, _, _, seed, role in sorted(candidates, key=lambda x: x[:3])[:MAX_BUNDLES]
        ]
