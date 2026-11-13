"""Bounded observation-progress repair around the unchanged dependency reader.

Requeries are actual numerical ZHA/exact reads. Last-resort observed-graph
recovery is explicitly a different, metered source, never a hierarchy success.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict
from typing import Any, Literal

import torch

from research.dependency_memory import DependencyReader
from research.minigrid_benchmark import (
    DIRECTIONS,
    Fact,
    KnownCoverage,
    ReadContext,
    position_features,
)

ProgressName = Literal["progress_zha", "progress_exact", "cues_zha", "cues_exact"]
PROGRESS_READERS = ("progress_zha", "progress_exact", "cues_zha", "cues_exact")
HISTORY_LIMIT = 24
CUE_AFTER = 8
WIDEN_AFTER = 16
GRAPH_AFTER = 24
HARD_GRAPH_AFTER = 48
CANDIDATE_BUDGET = 192
CUE_DISTANCE = 8
PROGRESS_WORK = (
    "payload_novelty_checks",
    "history_pose_checks",
    "cue_vectors_created",
    "cue_query_rows",
    "source_candidate_facts",
    "requery_reads",
    "widened_reads",
    "graph_fallback_reads",
    "graph_fallback_episodes",
    "novel_information_resets",
    "stage_transitions",
    "trace_index_ids",
    "trace_node_spans",
)


class ProgressReader(DependencyReader):
    """Uses own observed-prefix novelty and bounded poses, never simulator state."""

    def __init__(self, variant: ProgressName, capacity: int = 96) -> None:
        if variant not in PROGRESS_READERS or capacity != 96 or type(capacity) is not int:
            raise ValueError("supported progress variants require96 raw-fact capacity")
        super().__init__("bundle_zha" if "zha" in variant else "bundle_exact", capacity)
        self.variant = variant
        self.allow_fallback = variant.startswith("progress_")
        self._payloads: set[tuple[int, int, int, int, int, bool]] = set()
        self._pending_novel: list[int] = []
        self._history: deque[tuple[int, int, int]] = deque(maxlen=HISTORY_LIMIT)
        self._no_information = 0
        self._fallback_active = False
        self._previous_stage = 0
        self._repair_work = dict.fromkeys(PROGRESS_WORK, 0)
        self._reported_work = self._repair_work.copy()
        self._repair_seconds = 0.0

    def observe(self, visible: list[Fact]) -> list[Fact]:
        added = super().observe(visible)
        for fact in added:
            self._repair_work["payload_novelty_checks"] += 1
            payload = (fact.x, fact.y, fact.object, fact.color, fact.state, fact.cue)
            if payload not in self._payloads:
                self._payloads.add(payload)
                self._pending_novel.append(fact.id)
        return added

    def _stage(self, repeated: bool) -> tuple[int, str]:
        if self._pending_novel:
            return 0, "new_observed_information"
        if self._fallback_active:
            return 3, "continue_graph_until_information"
        if self.allow_fallback and (
            self._no_information >= HARD_GRAPH_AFTER
            or (self._no_information >= GRAPH_AFTER and repeated)
        ):
            self._fallback_active = True
            self._repair_work["graph_fallback_episodes"] += 1
            return (
                3,
                "hard_no_information_limit"
                if self._no_information >= HARD_GRAPH_AFTER
                else "repeated_stall_after_widening",
            )
        if self._no_information >= WIDEN_AFTER:
            return 2, "candidate_budget_widening"
        if self._no_information >= CUE_AFTER and repeated:
            return 1, "repeated_pose_without_information"
        return 0, "ordinary_retrieval"

    @staticmethod
    def _cues(
        queries: torch.Tensor, context: ReadContext, stage: int
    ) -> tuple[torch.Tensor, list[dict[str, Any]]]:
        labels = ["Local position", "Mission objects"]
        if "matching" in context.mission:
            labels.append("Remembered sample")
        if len(labels) != len(queries):
            raise ValueError("progress adapter expects the declared common-controller cues")
        vectors = [row.clone() for row in queries]
        if stage in (1, 2):
            for (dx, dy), label in zip(
                DIRECTIONS,
                ("Explore east", "Explore south", "Explore west", "Explore north"),
                strict=True,
            ):
                vector = torch.zeros(30, dtype=torch.float64)
                target = (
                    context.position[0] + CUE_DISTANCE * dx,
                    context.position[1] + CUE_DISTANCE * dy,
                )
                vector[:12] = position_features(target) - 0.5 * position_features(context.position)
                vector[12 + 1] = vector[12 + 3] = 6.0
                vectors.append(vector)
                labels.append(label)
        effective = torch.stack(vectors)
        return effective, [
            {"label": label, "query_index": i, "vector": vector.tolist()}
            for i, (label, vector) in enumerate(zip(labels, effective, strict=True))
        ]

    def select_with_context(
        self, queries: torch.Tensor, context: ReadContext
    ) -> tuple[list[Fact], list[dict[str, Any]], dict[str, Any], KnownCoverage | None]:
        if (
            not isinstance(queries, torch.Tensor)
            or queries.dtype != torch.float64
            or queries.device.type != "cpu"
            or queries.ndim != 2
            or queries.shape != (3 if "matching" in context.mission else 2, 30)
            or not bool(torch.isfinite(queries).all())
        ):
            raise ValueError(
                "progress queries must match finite common-controller CPU float64 cues"
            )
        if context.step != self._latest_step or context.current_facts != self._visible:
            raise ValueError("progress read context differs from observed prefix")
        started = time.perf_counter()
        before = self._reported_work.copy()
        novel = self._pending_novel.copy()
        if novel:
            self._no_information = 0
            self._fallback_active = False
            self._repair_work["novel_information_resets"] += 1
        else:
            self._no_information += 1
        pose = (*context.position, context.direction)
        self._history.append(pose)
        self._repair_work["history_pose_checks"] += len(self._history)
        repeat_count = sum(p == pose for p in self._history)
        repeated = repeat_count >= 2
        stage, trigger = self._stage(repeated)
        if stage != self._previous_stage:
            self._repair_work["stage_transitions"] += 1
        self._previous_stage = stage
        effective, cues = self._cues(queries, context, stage)
        for cue in cues:
            cue["used"] = stage != 3
            cue["decision_source"] = "full_observed_graph" if stage == 3 else self.source.name
        self._repair_work["cue_vectors_created"] += len(cues) - len(queries)
        self._repair_work["cue_query_rows"] += len(cues)
        if stage in (1, 2):
            self._repair_work["requery_reads"] += 1
        if stage == 2:
            self._repair_work["widened_reads"] += 1
        if stage == 3:
            self._repair_work["graph_fallback_reads"] += 1
        source_name, source_capacity = self.source.name, self.source.capacity
        self.source.name = "full" if stage == 3 else source_name
        self.source.capacity = CANDIDATE_BUDGET if stage == 2 else self.capacity
        setup_seconds = time.perf_counter() - started
        try:
            selected, routes, receipt, coverage = super().select_with_context(effective, context)
        finally:
            self.source.name, self.source.capacity = source_name, source_capacity
        finished = time.perf_counter()
        self._repair_work["source_candidate_facts"] += len(receipt["seed_ids"])
        if routes:
            assert self.source._index is not None
            info = self.source._index.info
            for route in routes:
                route["index_fact_ids"] = self.source._index_ids.copy()
                route["node_spans"] = [
                    {
                        "level": span.node_id.level,
                        "index": span.node_id.index,
                        "start": span.start,
                        "stop": span.stop,
                    }
                    for span in info.spans
                ]
                route["chunk_size"], route["depth"] = info.config.chunk_size, info.config.depth
                route["logical_key_count"] = info.key_count
                route["snapshot_id"] = info.snapshot_id
                route["used"] = True
                route["decision_source"] = source_name
                self._repair_work["trace_index_ids"] += len(route["index_fact_ids"])
                self._repair_work["trace_node_spans"] += len(route["node_spans"])
        repair = {
            "variant": self.variant,
            "stage": stage,
            "trigger": trigger,
            "no_information_reads": self._no_information,
            "repeated_pose": repeated,
            "repeat_count": repeat_count,
            "history": list(self._history),
            "history_limit": HISTORY_LIMIT,
            "novel_observed_ids": novel,
            "fallback_allowed": self.allow_fallback,
            "fallback_active": stage == 3,
            "executed_source": "full_observed_graph" if stage == 3 else source_name,
            "candidate_budget": None
            if stage == 3
            else CANDIDATE_BUDGET
            if stage == 2
            else self.capacity,
            "raw_fact_budget": self.capacity,
            "cues": cues,
            "attempts": [
                {**route, "cue_label": cues[route["query_index"]]["label"]} for route in routes
            ],
            "source_original_ids": receipt["seed_ids"].copy(),
            "work_delta": {k: self._repair_work[k] - before[k] for k in PROGRESS_WORK},
            "context": asdict(context),
        }
        self._reported_work = self._repair_work.copy()
        self._pending_novel.clear()
        receipt["repair"] = repair
        receipt["mode"] = self.variant
        self._repair_seconds += setup_seconds + time.perf_counter() - finished
        self.costs.update({f"repair_{k}": v for k, v in self._repair_work.items()})
        self.costs["repair_seconds"] = self._repair_seconds
        return selected, routes, receipt, coverage
