"""Experimental CPU-float64 execution, independent of the reference kernel.

Only actual candidate nodes and selected keys are scored. Rectangular padding
is used for ordering/softmax, not node scoring or value accumulation. The
reference snapshot stays immutable; its packed copy is counted as extra memory.
Detailed traces/custom budgets/dense fallback are explicitly reference-dispatched.
This module is research code, not a new supported public package backend.
"""

import math
from dataclasses import dataclass

import torch

from open_hierarchical_memory import (
    AttentionResult,
    ExecutionMode,
    HierarchicalIndex,
    InputError,
    QueryBudget,
    ResourceLimitError,
    ResultState,
)
from open_hierarchical_memory.contracts import QueryTrace
from open_hierarchical_memory.summaries import require_finite, require_tensor


@dataclass(frozen=True)
class ExecutionResult:
    result: AttentionResult
    engine: str
    scored_summary_slots: int = 0
    selected_key_slots: int = 0
    ordering_slots: int = 0
    attention_softmax_slots: int = 0

    @property
    def output(self):
        return self.result.output

    @property
    def routes(self):
        return self.result.routes


class BatchedHierarchicalIndex:
    def __init__(
        self, keys, values, references, *, config=None, max_stage_tensor_bytes=256 * 1024 * 1024
    ):
        if type(max_stage_tensor_bytes) is not int or max_stage_tensor_bytes < 1:
            raise InputError("max_stage_tensor_bytes must be a positive integer")
        self._reference = HierarchicalIndex(keys, values, references, config=config)
        info = self._reference.info
        extra = info.owned_tensor_bytes - sum(
            t.numel() * t.element_size()
            for t in (self._reference._keys, self._reference._values, self._reference._references)
        )
        self._owned_bytes = info.owned_tensor_bytes + extra
        if self._owned_bytes > info.config.max_snapshot_tensor_bytes:
            raise ResourceLimitError("snapshot budget includes additional packed-summary storage")
        self._stage_limit = max_stage_tensor_bytes
        self._levels = []
        for level in range(info.config.depth):
            batches = [tree[level] for tree in self._reference._trees]
            if batches[0]:
                means = torch.stack(
                    [
                        torch.stack([node.summary.means for node in batch], dim=1)
                        for batch in batches
                    ]
                )
                biases = torch.stack(
                    [
                        torch.stack([node.summary.biases for node in batch], dim=1)
                        for batch in batches
                    ]
                )
            else:
                means = torch.empty(
                    (info.batch_size, info.kv_heads, 0, info.reference_count, info.key_dim),
                    dtype=torch.float64,
                )
                biases = torch.empty(
                    (info.batch_size, info.kv_heads, 0, info.reference_count), dtype=torch.float64
                )
            self._levels.append((means, biases))

    @property
    def owned_tensor_bytes(self):
        return self._owned_bytes

    @property
    def info(self):
        # Preserve immutable metadata while reporting all owned tensor storage.
        from dataclasses import replace

        return replace(self._reference.info, owned_tensor_bytes=self._owned_bytes)

    def node_summary(self, *args):
        return self._reference.node_summary(*args)

    def _check_stage(self, size):
        if size > self._stage_limit:
            raise ResourceLimitError("batched stage tensor estimate exceeds declared limit")

    @torch.no_grad()
    def attend(
        self,
        queries,
        *,
        visible_counts,
        mode,
        p=0.95,
        budget=None,
        collect_trace=False,
        allow_dense_fallback=False,
    ):
        # Explicit metadata reports use of the reference implementation; timings
        # must assert engine == 'batched' before claiming a backend measurement.
        if (
            mode is not ExecutionMode.PAPER_APPROXIMATE
            or budget is not None
            or collect_trace is not False
            or allow_dense_fallback is not False
        ):
            result = self._reference.attend(
                queries,
                visible_counts=visible_counts,
                mode=mode,
                p=p,
                budget=budget,
                collect_trace=collect_trace,
                allow_dense_fallback=allow_dense_fallback,
            )
            return ExecutionResult(result, "reference")
        if type(p) not in (int, float) or not math.isfinite(p) or not 0 < p <= 1:
            raise InputError("p must be finite and in (0,1]")
        require_tensor("queries", queries, 4)
        batch, heads, query_count, dim = queries.shape
        info = self._reference.info
        if batch != info.batch_size or dim != info.key_dim or heads % info.kv_heads:
            raise InputError("query batch/dimension/head grouping does not match snapshot")
        if (
            not isinstance(visible_counts, torch.Tensor)
            or visible_counts.dtype != torch.int64
            or visible_counts.device.type != "cpu"
            or visible_counts.layout != torch.strided
            or visible_counts.shape != (batch, query_count)
        ):
            raise InputError("visible_counts must be a CPU int64 [B,Qlen] tensor")
        if bool(((visible_counts < 1) | (visible_counts > info.key_count)).any()):
            raise InputError("each visibility count must be in [1,N]")
        limits = QueryBudget()
        rows = batch * heads * query_count
        output_bytes = rows * info.value_dim * 8
        if output_bytes > limits.max_output_tensor_bytes:
            raise ResourceLimitError("output tensor budget exceeded")
        queries = queries.detach().clone(memory_format=torch.contiguous_format)
        visible_counts = visible_counts.clone()
        require_finite("owned queries", queries)
        flat = queries.reshape(rows, dim)
        visible = visible_counts[:, None, :].expand(batch, heads, query_count).reshape(-1).tolist()
        row_batches = torch.arange(rows) // (heads * query_count)
        row_heads = (torch.arange(rows) // query_count) % heads
        kv_heads = row_heads // (heads // info.kv_heads)
        chunk, depth = info.config.chunk_size, info.config.depth
        parent = [[] for _ in range(rows)]
        leaves = [[] for _ in range(rows)]
        per_row_nodes = [0] * rows
        scored = ordering_slots = 0
        for level in range(depth, 0, -1):
            candidates = []
            for row in range(rows):
                full = (visible[row] - 1) // chunk**level
                parented = (
                    ((visible[row] - 1) // chunk ** (level + 1)) * chunk if level < depth else 0
                )
                ids = sorted(
                    {
                        child
                        for parent_id in parent[row]
                        for child in range(parent_id * chunk, (parent_id + 1) * chunk)
                    }
                    | set(range(parented, full))
                )
                candidates.append(ids)
                per_row_nodes[row] += len(ids)
            counts = [len(ids) for ids in candidates]
            maximum = max(counts)
            total = sum(counts)
            scored += total
            if scored > limits.max_scored_nodes:
                raise ResourceLimitError("route node budget exceeded")
            if not total:
                parent = [[] for _ in range(rows)]
                continue
            # Check a conservative stage-tensor estimate; this is not a process-RSS limit.
            self._check_stage(
                total * (2 * info.reference_count * dim + dim + 6 * info.reference_count + 16) * 8
                + rows * maximum * 64
                + output_bytes
            )
            owners = torch.tensor(
                [row for row, ids in enumerate(candidates) for _ in ids], dtype=torch.int64
            )
            nodes = torch.tensor([node for ids in candidates for node in ids], dtype=torch.int64)
            positions = torch.tensor(
                [i for ids in candidates for i in range(len(ids))], dtype=torch.int64
            )
            means, biases = self._levels[level - 1]
            selected_means = means[row_batches[owners], kv_heads[owners], nodes]
            selected_biases = biases[row_batches[owners], kv_heads[owners], nodes]
            scores = (
                (selected_means * flat.index_select(0, owners)[:, None, :]).sum(-1) / math.sqrt(dim)
                + selected_biases
            ).amax(-1)
            require_finite("routing scores", scores)
            dense_scores = torch.full((rows, maximum), float("-inf"), dtype=torch.float64)
            dense_scores[owners, positions] = scores
            empty = torch.tensor(counts) == 0
            dense_scores[empty, 0] = 0  # inert row, count remains zero
            order = torch.argsort(dense_scores, dim=-1, descending=True, stable=True)
            if p == 1:
                stops = counts
            else:
                probabilities = torch.softmax(dense_scores.gather(1, order), dim=-1)
                cumulative = probabilities.cumsum(-1)
                stop = (
                    torch.searchsorted(
                        cumulative, torch.full((rows, 1), float(p), dtype=torch.float64)
                    ).squeeze(1)
                    + 1
                )
                stops = torch.minimum(stop, torch.tensor(counts)).tolist()
            ordered = order.tolist()
            parent = [
                [ids[position] for position in ordered[row][: stops[row]]]
                for row, ids in enumerate(candidates)
            ]
            ordering_slots += rows * maximum
            if level == 1:
                leaves = parent
            # Do not retain the previous level's scratch buffers into the next.
            del owners, nodes, positions, selected_means, selected_biases, scores
            del dense_scores, empty, order, ordered
            if p != 1:
                del probabilities, cumulative, stop
        selected = []
        for row in range(rows):
            local_start = 1 + (visible[row] - 1) // chunk * chunk
            ids = {0, *range(local_start, visible[row])}
            for leaf in leaves[row]:
                ids.update(range(1 + leaf * chunk, 1 + (leaf + 1) * chunk))
            selected.append(sorted(ids))
        key_slots = sum(len(ids) for ids in selected)
        if key_slots > limits.max_attention_pairs:
            raise ResourceLimitError("attention pair budget exceeded; no result returned")
        width = max(len(ids) for ids in selected)
        self._check_stage(
            key_slots * (3 * dim + 3 * info.value_dim + 16) * 8 + rows * width * 32 + output_bytes
        )
        owners = torch.tensor(
            [row for row, ids in enumerate(selected) for _ in ids], dtype=torch.int64
        )
        key_ids = torch.tensor([key for ids in selected for key in ids], dtype=torch.int64)
        positions = torch.tensor(
            [i for ids in selected for i in range(len(ids))], dtype=torch.int64
        )
        keys = self._reference._keys[row_batches[owners], kv_heads[owners], key_ids]
        values = self._reference._values[row_batches[owners], kv_heads[owners], key_ids]
        logits = (keys * flat.index_select(0, owners)).sum(-1) / math.sqrt(dim)
        require_finite("attention logits", logits)
        dense_logits = torch.full((rows, width), float("-inf"), dtype=torch.float64)
        dense_logits[owners, positions] = logits
        weights = torch.softmax(dense_logits, -1)[owners, positions]
        output = torch.zeros((rows, info.value_dim), dtype=torch.float64)
        output.index_add_(0, owners, weights[:, None] * values)
        require_finite("attention output", output)
        traces = tuple(
            QueryTrace(
                row // (heads * query_count),
                (row // query_count) % heads,
                row % query_count,
                visible[row],
                ResultState.PAPER_APPROXIMATE,
                tuple(selected[row]),
                per_row_nodes[row],
                (),
                None,
            )
            for row in range(rows)
        )
        result = AttentionResult(
            output.reshape(batch, heads, query_count, info.value_dim),
            mode,
            info.snapshot_id,
            float(p),
            traces,
        )
        return ExecutionResult(result, "batched", scored, key_slots, ordering_slots, rows * width)
