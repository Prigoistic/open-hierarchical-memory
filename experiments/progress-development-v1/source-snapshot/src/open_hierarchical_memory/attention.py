"""Explicit dense/approximate execution with honest per-query failure states."""

import math

import torch
from torch import Tensor

from .contracts import (
    AttentionResult,
    ExecutionMode,
    InputError,
    QueryBudget,
    QueryTrace,
    ResourceLimitError,
    ResultState,
    RouteStep,
)
from .routing import WorkCounter, route
from .summaries import require_finite, require_tensor
from .tree import KVSnapshot


class HierarchicalIndex(KVSnapshot):
    """No-RoPE CPU float64 inference reference. No runtime error guarantee."""

    @torch.no_grad()
    def attend(
        self,
        queries: Tensor,
        *,
        visible_counts: Tensor,
        mode: ExecutionMode,
        p: float = 0.95,
        budget: QueryBudget | None = None,
        collect_trace: bool = False,
        allow_dense_fallback: bool = False,
    ) -> AttentionResult:
        if not isinstance(mode, ExecutionMode):
            raise InputError("mode must explicitly be an ExecutionMode")
        if type(p) not in (float, int) or not math.isfinite(p) or not 0 < p <= 1:
            raise InputError("p must be finite and in (0,1]")
        if type(collect_trace) is not bool or type(allow_dense_fallback) is not bool:
            raise InputError("trace and fallback options must be booleans")
        if budget is not None and not isinstance(budget, QueryBudget):
            raise InputError("budget must be a QueryBudget")
        budget = budget if budget is not None else QueryBudget()
        require_tensor("queries", queries, 4)
        batch, heads, query_count, dimension = queries.shape
        info = self.info
        if batch != info.batch_size or dimension != info.key_dim or heads % info.kv_heads:
            raise InputError("query batch/dimension/head grouping does not match snapshot")
        if (
            not isinstance(visible_counts, Tensor)
            or visible_counts.dtype != torch.int64
            or visible_counts.device.type != "cpu"
            or visible_counts.layout != torch.strided
            or visible_counts.shape != (batch, query_count)
        ):
            raise InputError("visible_counts must be a CPU int64 [B,Qlen] tensor")
        if bool(((visible_counts < 1) | (visible_counts > info.key_count)).any()):
            raise InputError("each visibility count must be in [1,N]")
        output_bytes = batch * heads * query_count * info.value_dim * 8
        if output_bytes > budget.max_output_tensor_bytes:
            raise ResourceLimitError("output tensor budget exceeded")
        # Own this call's public inputs as well. Concurrent mutation DURING the
        # copy is unsupported; callers must not race input creation/execution.
        queries = queries.detach().clone(memory_format=torch.contiguous_format)
        visible_counts = visible_counts.clone()
        require_finite("owned queries", queries)
        output = torch.empty((batch, heads, query_count, info.value_dim), dtype=torch.float64)
        routes: list[QueryTrace] = []
        work = WorkCounter()
        for b in range(batch):
            for h in range(heads):
                kv_head = h // (heads // info.kv_heads)
                for t in range(query_count):
                    query = queries[b, h, t]
                    visible = int(visible_counts[b, t].item())
                    steps: tuple[RouteStep, ...] = ()
                    reason = None
                    before = work.scored_nodes
                    if mode == ExecutionMode.DENSE:
                        if work.attention_pairs + visible > budget.max_attention_pairs:
                            raise ResourceLimitError(
                                "attention pair budget exceeded before allocation"
                            )
                        ids = tuple(range(visible))
                        state = ResultState.DENSE_REFERENCE
                    else:
                        try:
                            ids, steps = route(
                                query,
                                self._trees[b],
                                kv_head,
                                visible,
                                self._config.chunk_size,
                                float(p),
                                budget,
                                work,
                                collect_trace=collect_trace,
                                max_selected_keys=budget.max_attention_pairs - work.attention_pairs,
                            )
                            state = ResultState.PAPER_APPROXIMATE
                        except ResourceLimitError as error:
                            if not allow_dense_fallback:
                                raise
                            if work.attention_pairs + visible > budget.max_attention_pairs:
                                raise ResourceLimitError(
                                    "dense fallback attention pair budget exceeded"
                                ) from error
                            ids = tuple(range(visible))
                            state = ResultState.DENSE_FALLBACK
                            reason = str(error)
                    # Failure here aborts the entire call, with no partial result.
                    if work.attention_pairs + len(ids) > budget.max_attention_pairs:
                        raise ResourceLimitError(
                            "attention pair budget exceeded; no result returned"
                        )
                    work.attention_pairs += len(ids)
                    selected = torch.tensor(ids, dtype=torch.int64)
                    keys = self._keys[b, kv_head].index_select(0, selected)
                    values = self._values[b, kv_head].index_select(0, selected)
                    logits = (keys * query).sum(dim=-1) / math.sqrt(dimension)
                    require_finite("attention logits", logits)
                    value = torch.softmax(logits, dim=-1) @ values
                    require_finite("attention output", value)
                    output[b, h, t] = value
                    routes.append(
                        QueryTrace(
                            b,
                            h,
                            t,
                            visible,
                            state,
                            ids,
                            work.scored_nodes - before,
                            steps,
                            reason,
                        )
                    )
        return AttentionResult(output, mode, info.snapshot_id, float(p), tuple(routes))
