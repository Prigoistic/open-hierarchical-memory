"""Context-bound task memory with explicit archive recovery and scoped graph support.

The canonical bank/index can grow. Only available payloads enter the planner;
archive construction, retrieval and selected payload reads are separately metered.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict
from typing import Any, Literal

import torch

from open_hierarchical_memory import (
    ExecutionMode,
    HierarchicalIndex,
    QueryBudget,
    ResourceLimitError,
)
from research.dependency_memory import DependencyReader
from research.minigrid_benchmark import Fact, KnownCoverage, ReadContext, fact_features
from research.task_references import GEOMETRY, digest
from research.task_store import TaskStore

Backend = Literal["zha", "exact", "none"]


class PersistentTaskReader:
    def __init__(
        self,
        store: TaskStore,
        context: str,
        *,
        backend: Backend = "zha",
        threshold: float = 0.8,
        budget: QueryBudget | None = None,
    ) -> None:
        if (
            backend not in ("zha", "exact", "none")
            or type(threshold) not in (int, float)
            or not math.isfinite(threshold)
            or not 0 < threshold <= 1
        ):
            raise ValueError("invalid archive reader configuration")
        if store.config.capacity < 8:
            raise ValueError("task planner requires at least8 active slots")
        self.store, self.context, self.backend = store, context, backend
        self.threshold = float(threshold)
        self.budget = budget or QueryBudget(
            max_scored_nodes=4096, max_attention_pairs=4096, max_trace_nodes=4096
        )
        self.store.bind(context)
        self.support = DependencyReader("bundle_exact", store.config.capacity)
        self._index: HierarchicalIndex | None = None
        self._index_version = -1
        self._ids: list[int] = []
        self._keys = torch.empty((0, 30), dtype=torch.float64)
        self.work: dict[str, int | float] = dict.fromkeys(
            (
                "index_builds",
                "index_key_rows",
                "index_owned_tensor_bytes_peak",
                "adapter_key_tensor_bytes_peak",
                "archive_raw_pairs",
                "archive_summary_nodes",
                "archive_summary_dot_products",
                "archive_rerank_pairs",
                "hot_score_pairs",
                "recovered_facts",
                "recovery_budget_failures",
                "reads",
                "index_build_seconds",
                "retrieval_seconds",
            ),
            0,
        )
        self.costs: dict[str, int | float] = {}
        self._sync_costs()

    def _sync_costs(self) -> None:
        self.costs = {
            **self.work,
            **{f"store_{k}": v for k, v in self.store.work.items()},
            **{f"support_{k}": v for k, v in self.support.work.items()},
        }

    def observe(self, visible: list[Fact]) -> list[Fact]:
        if len(visible) > self.store.config.capacity:
            raise ValueError("current observation exceeds this workspace capacity")
        result = self.store.observe(self.context, visible)
        self._sync_costs()
        return result

    def archive(self) -> list[dict[str, Any]]:
        """Evaluator-only full export. The controller never calls this method."""
        result = self.store.export(self.context)
        self._sync_costs()
        return result

    def fade(self, ticks: int) -> list[int]:
        result = self.store.fade(self.context, ticks)
        self._sync_costs()
        return result

    def _build_archive_index(self, version: int) -> None:
        if self._index_version == version:
            return
        started = time.perf_counter()
        records = self.store.heads(self.context)
        self._ids = [f.id for f in records]
        self._keys = torch.stack(
            [torch.zeros(30, dtype=torch.float64), *[fact_features(f) for f in records]]
        )
        if self.backend == "zha":
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
                self.store.router.tensor(),
                config=GEOMETRY,
            )
            owned = self._index.info.owned_tensor_bytes
        else:
            owned = self._keys.numel() * self._keys.element_size()
        self.work["adapter_key_tensor_bytes_peak"] = max(
            self.work["adapter_key_tensor_bytes_peak"],
            self._keys.numel() * self._keys.element_size(),
        )
        self._index_version = version
        self.work["index_builds"] += 1
        self.work["index_key_rows"] += len(records)
        self.work["index_owned_tensor_bytes_peak"] = max(
            self.work["index_owned_tensor_bytes_peak"], owned
        )
        self.work["index_build_seconds"] += time.perf_counter() - started

    def _recover(
        self, queries: torch.Tensor, active: set[int], limit: int, version: int
    ) -> tuple[list[int], list[dict[str, Any]], str]:
        if self.backend == "none" or limit == 0:
            return [], [], "disabled"
        self._build_archive_index(version)
        traces = []
        if self.backend == "zha":
            assert self._index is not None
            try:
                result = self._index.attend(
                    queries[None, None],
                    visible_counts=torch.full(
                        (1, len(queries)), len(self._ids) + 1, dtype=torch.int64
                    ),
                    mode=ExecutionMode.PAPER_APPROXIMATE,
                    p=self.threshold,
                    budget=self.budget,
                    collect_trace=True,
                )
            except ResourceLimitError:
                self.work["recovery_budget_failures"] += 1
                return (
                    [],
                    [
                        {
                            "status": "budget_exhausted",
                            "spent_work": "unavailable after interrupted core call",
                            "declared_limits": asdict(self.budget),
                        }
                    ],
                    "budget_exhausted",
                )
            candidates = sorted({i for route in result.routes for i in route.selected_ids if i})
            for route in result.routes:
                self.work["archive_raw_pairs"] += len(route.selected_ids)
                self.work["archive_summary_nodes"] += route.scored_nodes
                self.work["archive_summary_dot_products"] += route.scored_nodes * 8
                traces.append(
                    {
                        "query_index": route.query_index,
                        "selected_logical_ids": list(route.selected_ids),
                        "selected_fact_ids": [self._ids[i - 1] for i in route.selected_ids if i],
                        "snapshot_id": result.snapshot_id,
                        "reference_hash": self.store.router.sha256,
                        "index_fact_ids": self._ids.copy(),
                        "scored_nodes": route.scored_nodes,
                        "steps": [
                            {
                                "level": s.level,
                                "candidates": [n.index for n in s.candidates],
                                "selected": [n.index for n in s.selected],
                                "scores": list(s.scores),
                            }
                            for s in route.steps
                        ],
                    }
                )
        else:
            candidates = list(range(1, len(self._ids) + 1))
            if len(queries) * len(candidates) > self.budget.max_attention_pairs:
                self.work["recovery_budget_failures"] += 1
                return (
                    [],
                    [
                        {
                            "status": "budget_exhausted",
                            "spent_scoring_pairs": 0,
                            "declared_limits": asdict(self.budget),
                        }
                    ],
                    "budget_exhausted",
                )
            self.work["archive_raw_pairs"] += len(queries) * len(candidates)
        # Rank only actually routed candidates. No full-bank hidden rerank.
        if not candidates:
            return [], traces, "empty"
        scores = (queries @ self._keys[candidates].T / math.sqrt(30)).max(0).values
        if self.backend == "zha":
            self.work["archive_rerank_pairs"] += len(queries) * len(candidates)
        ordering = torch.argsort(scores, descending=True, stable=True).tolist()
        recovered = [
            self._ids[candidates[i] - 1]
            for i in ordering
            if self._ids[candidates[i] - 1] not in active
        ][:limit]
        return recovered, traces, "selected" if recovered else "no_dormant_candidate"

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
        if len(context.current_facts) > self.store.config.capacity:
            raise ValueError("current observations exceed workspace capacity")
        self._sync_costs()
        before = self.costs.copy()
        started = time.perf_counter()
        current = self.store.current(self.context, [f.position for f in context.current_facts])
        current_ids = [f.id for f in current]
        # Current perception is an explicit input, even after a long idle interval.
        evicted = self.store.promote(self.context, current_ids)
        active = self.store.heads(self.context, active=True, tag="active_payload_rows")
        active_before = [f.id for f in active]
        limit = min(self.store.config.recovery_limit, self.store.config.capacity - len(current_ids))
        recovered, routes, status = self._recover(
            queries, set(active_before), limit, state["version"]
        )
        recovered_facts = self.store.fetch(self.context, recovered)
        self.work["recovered_facts"] += len(recovered_facts)
        evicted += self.store.promote(self.context, [*current_ids, *recovered])
        available = self.store.heads(self.context, active=True, tag="active_payload_rows")
        if any(f.observed_step > context.step for f in available):
            raise ValueError("future evidence in active workspace")
        if available:
            scores = (
                (queries @ torch.stack([fact_features(f) for f in available]).T / math.sqrt(30))
                .max(0)
                .values
            )
            self.work["hot_score_pairs"] += len(queries) * len(available)
            seeds = [
                available[i] for i in torch.argsort(scores, descending=True, stable=True).tolist()
            ]
        else:
            seeds = []
        selected, bundles = self.support.pack_available_support(available, seeds, context)
        allowed = {f.id: f for f in available}
        if (
            len(selected) > self.store.config.capacity
            or len({f.id for f in selected}) != len(selected)
            or any(allowed.get(f.id) != f for f in selected)
        ):
            raise ValueError("support escaped the active evidence boundary")
        self.store.use(self.context, [f.id for f in selected])
        self.work["reads"] += 1
        self.work["retrieval_seconds"] += time.perf_counter() - started
        self._sync_costs()
        coverage = KnownCoverage(
            bytes.fromhex(state["coverage"]),
            state["version"],
            digest([self.context, state["version"], state["coverage"]]),
        )
        receipt = {
            "mode": f"persistent_{self.backend}",
            "context_id": self.context,
            "source_version": state["version"],
            "reference_hash": self.store.router.sha256,
            "reference_kind": self.store.router.kind,
            "recovery_status": status,
            "work_complete": status != "budget_exhausted",
            "current_ids": current_ids,
            "active_before_recovery": active_before,
            "recovered_ids": recovered,
            "evicted_ids": sorted(set(evicted)),
            "available_ids": [f.id for f in available],
            "graph_source": "active_and_explicitly_recovered_only",
            "returned_ids": [f.id for f in selected],
            "bundles": bundles,
            "active_capacity": self.store.config.capacity,
            "raw_fact_budget": self.store.config.capacity,
            "coverage_scope": "observed-known bits only; no cold payload/passability",
            "coverage_identity": "context/version/coverage binding; not a full-head content hash",
            "work_delta": {k: v - before.get(k, 0) for k, v in self.costs.items()},
        }
        return selected, routes, receipt, coverage
