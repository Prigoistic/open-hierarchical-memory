"""Explicit observed-graph support recovery under an unchanged active-fact cap.

Cold graph materialisation is additional, charged work. ZHA nominates seeds;
path connectors may be outside its routed set and are separately disclosed.
No hidden simulator state, imagined facts or planner changes are used.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict
from typing import Any, Literal

import torch

from open_hierarchical_memory import QueryBudget
from research.dependency_memory import ObservedGraph
from research.minigrid_benchmark import Fact, KnownCoverage, ReadContext, fact_features
from research.persistent_task_memory import Backend, PersistentTaskReader, RecoveryPolicy
from research.task_references import digest
from research.task_store import TaskStore

SupportMode = Literal["compact", "connected"]


class SupportTaskReader(PersistentTaskReader):
    def __init__(
        self,
        store: TaskStore,
        context: str,
        *,
        backend: Backend = "zha",
        threshold: float = 0.8,
        recovery_policy: RecoveryPolicy = "on_stall",
        budget: QueryBudget | None = None,
        support_mode: SupportMode = "connected",
        cache_heads: bool = True,
    ) -> None:
        if support_mode not in ("compact", "connected") or type(cache_heads) is not bool:
            raise ValueError("invalid support policy")
        super().__init__(
            store,
            context,
            backend=backend,
            threshold=threshold,
            recovery_policy=recovery_policy,
            budget=budget,
        )
        self.support_mode, self.cache_heads = support_mode, cache_heads
        self._head_version = -1
        self._head_cache: tuple[Fact, ...] = ()
        self.work.update(
            dict.fromkeys(
                (
                    "connector_attempts",
                    "connector_head_scans",
                    "connector_cache_hits",
                    "connector_cache_payload_bytes_peak",
                    "connector_recovered_facts",
                    "compact_attempts",
                ),
                0,
            )
        )
        self._sync_costs()

    def _heads(self, version: int) -> list[Fact]:
        if self.cache_heads and self._head_version == version:
            self.work["connector_cache_hits"] += 1
            return list(self._head_cache)
        heads = self.store.heads(self.context)
        self.work["connector_head_scans"] += len(heads)
        if self.cache_heads:
            self._head_cache = tuple(heads)
            self._head_version = version
            # Serialized payload bytes, not a Python RSS measurement.
            size = len(json.dumps([asdict(f) for f in heads], separators=(",", ":")).encode())
            self.work["connector_cache_payload_bytes_peak"] = max(
                self.work["connector_cache_payload_bytes_peak"], size
            )
        return heads

    def _compact(
        self,
        heads: list[Fact],
        seeds: list[Fact],
        context: ReadContext,
        coverage: KnownCoverage,
        active: set[int],
        current: set[int],
    ) -> tuple[list[Fact], list[dict[str, Any]]]:
        self.work["compact_attempts"] += 1
        graph = ObservedGraph(heads, context, self.support.work)
        nominated = self.support._nominate(seeds, graph, context, known_coverage=coverage)
        cues = [f for f in heads if f.cue and f.object in (5, 6)]
        cue = min(cues, key=lambda f: (f.first_seen, f.id)) if cues else None
        packed: set[int] = set()
        receipts = []
        for seed, kind in nominated:
            b = graph.bundle(seed, kind, (cue,) if kind == "matching_landmark" and cue else ())
            # Known-only coverage already suppresses false frontiers. Halos are
            # optional context; preserve actual paths, prerequisites and cue.
            required = (
                set(b.path_ids)
                | {b.seed_id}
                | set(b.prerequisite_ids)
                | set(b.semantic_support_ids)
            )
            historical = required - current
            candidate = packed | historical
            cold = candidate - active
            self.support.work["packing_checks"] += len(candidate)
            status = (
                "missing_prerequisite"
                if b.missing
                else "overbudget"
                if len(candidate | current) > self.store.config.capacity
                or len(cold) > self.store.config.recovery_limit
                else "complete"
            )
            if status == "complete":
                packed = candidate
            receipts.append(
                {
                    "seed_id": seed.id,
                    "kind": kind,
                    "status": status,
                    "required_ids": sorted(required),
                    "historical_ids": sorted(historical),
                    "path_ids": list(b.path_ids),
                    "paths": [list(p) for p in b.paths],
                    "support_edges": [list(e) for e in b.support_edges],
                    "prerequisite_ids": list(b.prerequisite_ids),
                    "semantic_support_ids": list(b.semantic_support_ids),
                    "missing": list(b.missing),
                    "omitted_ids": sorted(historical - packed),
                    "candidate_packed_count": len(candidate | current),
                    "cold_count": len(cold),
                    "scope": "compact path support; optional halo omitted",
                }
            )
        return [graph.by_id[i] for i in sorted(packed)], receipts

    def select_with_context(
        self, queries: torch.Tensor, context: ReadContext
    ) -> tuple[list[Fact], list[dict[str, Any]], dict[str, Any], KnownCoverage | None]:
        if (
            not isinstance(queries, torch.Tensor)
            or queries.dtype != torch.float64
            or queries.device.type != "cpu"
            or queries.ndim != 2
            or not 1 <= len(queries) <= 8
            or queries.shape[1] != 30
            or not bool(torch.isfinite(queries).all())
        ):
            raise ValueError("task queries require finite CPU float64[1..8,30]")
        state = self.store.state(self.context)
        if (
            context.step != state["last_step"]
            or [asdict(f) for f in context.current_facts] != state["visible"]
        ):
            raise ValueError("read context differs from latest observed prefix")
        run, reason, control = self._recovery_gate(context, state["coverage"])
        self._sync_costs()
        before = self.costs.copy()
        started = time.perf_counter()
        current = self.store.current(self.context, [f.position for f in context.current_facts])
        current_ids = {f.id for f in current}
        evicted = self.store.promote(self.context, sorted(current_ids))
        active_facts = self.store.heads(self.context, active=True, tag="active_payload_rows")
        active = {f.id for f in active_facts}
        coverage = KnownCoverage(
            bytes.fromhex(state["coverage"]),
            state["version"],
            digest([self.context, state["version"], state["coverage"]]),
        )
        limit = min(self.store.config.recovery_limit, self.store.config.capacity - len(current))
        recovered, routes, status = (
            self._recover(queries, active, limit, state["version"])
            if run
            else ([], [], "deferred_active_progress")
        )
        fetched = self.store.fetch(self.context, recovered)
        pool = sorted([*active_facts, *fetched], key=lambda f: f.id)
        scores = (
            (queries @ torch.stack([fact_features(f) for f in pool]).T / math.sqrt(30))
            .max(0)
            .values
        )
        self.work["hot_score_pairs"] += len(queries) * len(pool)
        seeds = [pool[i] for i in torch.argsort(scores, descending=True, stable=True).tolist()]
        selected, bundles = self._compact(pool, seeds, context, coverage, active, current_ids)
        connector: dict[str, Any] = {
            "attempted": False,
            "status": "not_needed",
            "source_ids": [],
            "seed_ids": [],
            "recovered_ids": [],
        }
        progress = any(b["status"] == "complete" and b["kind"] != "cue" for b in bundles)
        if (
            self.support_mode == "connected"
            and not progress
            and (run or control["stable_reads"] >= 2)
            and status != "budget_exhausted"
        ):
            self.work["connector_attempts"] += 1
            if self.backend != "none" and not run:
                recovered, routes, status = self._recover(queries, active, limit, state["version"])
                run, reason = True, "support_gap"
                control["since_attempt"] = 0
            if status != "budget_exhausted":
                heads = self._heads(state["version"])
                routed = {i for route in routes for i in route.get("selected_fact_ids", [])}
                seed_ids = active | routed if self.backend == "zha" else {f.id for f in heads}
                source_seeds = [f for f in heads if f.id in seed_ids]
                chosen, choices = self._compact(
                    heads, source_seeds, context, coverage, active, current_ids
                )
                selected, bundles = chosen, choices
                connector = {
                    "attempted": True,
                    "status": "complete"
                    if any(b["status"] == "complete" for b in choices)
                    else "no_fitting_bundle",
                    "source_ids": [f.id for f in heads],
                    "seed_ids": [f.id for f in source_seeds],
                    "recovered_ids": sorted({f.id for f in selected} - active),
                    "scope": "full observed-head graph scan; ZHA seed support may include unrouted connectors",
                }
        selected_ids = {f.id for f in selected}
        final_cold = sorted(selected_ids - active)
        if len(selected_ids | current_ids) > self.store.config.capacity or len(final_cold) > limit:
            raise ValueError("compact support exceeded active/recovery capacity")
        self.store.fetch(self.context, final_cold)
        evicted += self.store.promote(self.context, sorted(current_ids | selected_ids))
        available = self.store.heads(self.context, active=True, tag="active_payload_rows")
        allowed = {f.id: f for f in available}
        if any(allowed.get(f.id) != f or f.observed_step > context.step for f in selected):
            raise ValueError("compact support escaped current active evidence")
        self.store.use(self.context, sorted(selected_ids), recovery_control=control)
        self.work["recovered_facts"] += len(final_cold)
        self.work["connector_recovered_facts"] += len(connector["recovered_ids"])
        self.work["reads"] += 1
        self.work["retrieval_seconds"] += time.perf_counter() - started
        self._sync_costs()
        receipt = {
            "mode": f"support_{self.backend}",
            "context_id": self.context,
            "source_version": state["version"],
            "reference_hash": self.store.router.sha256,
            "reference_kind": self.store.router.kind,
            "recovery_status": status,
            "recovery_policy": self.recovery_policy,
            "recovery_reason": reason,
            "recovery_control": control,
            "work_complete": status != "budget_exhausted",
            "current_ids": [f.id for f in current],
            "active_before_recovery": sorted(active),
            "recovered_ids": final_cold,
            "evicted_ids": sorted(set(evicted)),
            "available_ids": [f.id for f in available],
            "graph_source": "active_and_explicitly_recovered_only",
            "connector": connector,
            "bundles": bundles,
            "returned_ids": sorted(selected_ids),
            "active_capacity": self.store.config.capacity,
            "raw_fact_budget": self.store.config.capacity,
            "support_mode": self.support_mode,
            "coverage_scope": "observed-known bits only; no cold payload/passability",
            "work_delta": {k: v - before.get(k, 0) for k, v in self.costs.items()},
            "scope": "connector graph can inspect cold observed heads; planner receives only promoted raw facts",
        }
        return selected, routes, receipt, coverage
