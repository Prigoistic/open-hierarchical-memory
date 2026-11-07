"""Query-local top-p traversal. Complete boundary orphans are always candidates."""

import math
from dataclasses import dataclass

import torch
from torch import Tensor

from .contracts import NodeId, QueryBudget, ResourceLimitError, RouteStep
from .summaries import require_finite
from .tree import Levels


@dataclass
class WorkCounter:
    """One counter per attention call; no global mutable work state."""

    scored_nodes: int = 0
    attention_pairs: int = 0
    trace_nodes: int = 0


def _top_p(scores: Tensor, p: float) -> tuple[int, ...]:
    # Stable input order is logical node order, giving deterministic score ties.
    ordering = torch.argsort(scores, descending=True, stable=True)
    if p == 1.0:
        return tuple(int(i) for i in ordering.tolist())
    probabilities = torch.softmax(scores[ordering], dim=0)
    cumulative = probabilities.cumsum(dim=0)
    stop = min(int(torch.searchsorted(cumulative, p).item()) + 1, len(ordering))
    return tuple(int(i) for i in ordering[:stop].tolist())


def route(
    query: Tensor,
    levels: Levels,
    kv_head: int,
    visible: int,
    chunk: int,
    p: float,
    budget: QueryBudget,
    work: WorkCounter,
    *,
    collect_trace: bool,
    max_selected_keys: int,
) -> tuple[tuple[int, ...], tuple[RouteStep, ...]]:
    depth = len(levels)
    full_counts = [(visible - 1) // chunk**level for level in range(1, depth + 1)]
    parent_selection: tuple[int, ...] = ()
    steps: list[RouteStep] = []
    selected_leaves: tuple[int, ...] = ()
    for level in range(depth, 0, -1):
        full = full_counts[level - 1]
        parented = full_counts[level] * chunk if level < depth else 0
        candidate_ids = sorted(
            {
                child
                for parent in parent_selection
                for child in range(parent * chunk, (parent + 1) * chunk)
            }
            | set(range(parented, full))
        )
        if not candidate_ids:
            parent_selection = ()
            continue
        if work.scored_nodes + len(candidate_ids) > budget.max_scored_nodes:
            raise ResourceLimitError("route node budget exceeded")
        if collect_trace and work.trace_nodes + len(candidate_ids) > budget.max_trace_nodes:
            raise ResourceLimitError("route trace budget exceeded")
        summaries = [levels[level - 1][index].summary for index in candidate_ids]
        means = torch.stack([summary.means[kv_head] for summary in summaries])
        biases = torch.stack([summary.biases[kv_head] for summary in summaries])
        scores = ((means * query).sum(dim=-1) / math.sqrt(query.numel()) + biases).amax(dim=-1)
        require_finite("routing scores", scores)
        work.scored_nodes += len(candidate_ids)
        positions = _top_p(scores, p)
        selected = tuple(candidate_ids[pos] for pos in positions)
        if collect_trace:
            work.trace_nodes += len(candidate_ids)
            steps.append(
                RouteStep(
                    level,
                    tuple(NodeId(level, i) for i in candidate_ids),
                    tuple(float(s) for s in scores.tolist()),
                    tuple(NodeId(level, i) for i in selected),
                )
            )
        parent_selection = selected
        if level == 1:
            selected_leaves = selected
    local_start = 1 + (visible - 1) // chunk * chunk
    if 1 + visible - local_start + chunk * len(selected_leaves) > max_selected_keys:
        raise ResourceLimitError("attention pair budget exceeded during selection")
    ids = {0, *range(local_start, visible)}
    for index in selected_leaves:
        ids.update(range(1 + index * chunk, 1 + (index + 1) * chunk))
    return tuple(sorted(ids)), tuple(steps)
