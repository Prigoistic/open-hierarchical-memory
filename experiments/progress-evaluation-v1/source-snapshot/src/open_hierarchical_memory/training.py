"""Reference-only pooled-KL supervision for the supported no-RoPE construction.

Queries and keys are frozen observations, not parameters. Every level uses a
partition of the entire eligible prefix, including the exact sink and exact
incomplete tail. No routing decisions or held-out samples enter this loss.
"""

import math

import torch
from torch import Tensor

from .contracts import InputError, positive_int
from .summaries import require_finite, require_tensor, summarize


def pooled_chunk_kl(
    queries: Tensor,
    keys: Tensor,
    references: Tensor,
    *,
    visible_counts: Tensor,
    chunk_size: int,
    depth: int,
) -> Tensor:
    """Sum over levels, mean over query positions and heads.

    Shapes: queries [H,Q,D], keys [H,N,D], references [H,R,D], counts [Q].
    References alone receive gradients. Inputs must not be concurrently mutated.
    Complete-node summaries are computed directly from original keys; for this
    fixed shared-reference/no-RoPE construction this equals recursive merging.
    """
    require_tensor("queries", queries, 3)
    require_tensor("keys", keys, 3)
    require_tensor("references", references, 3)
    positive_int("chunk_size", chunk_size)
    positive_int("depth", depth)
    if chunk_size < 2 or depth > 32:
        raise InputError("unsupported tree geometry")
    heads, query_count, dimension = queries.shape
    if keys.shape[0] != heads or references.shape[0] != heads:
        raise InputError("query, key and reference heads must match")
    if keys.shape[-1] != dimension or references.shape[-1] != dimension:
        raise InputError("query, key and reference dimensions must match")
    if (
        not isinstance(visible_counts, Tensor)
        or visible_counts.device.type != "cpu"
        or visible_counts.dtype != torch.int64
        or visible_counts.layout != torch.strided
        or visible_counts.shape != (query_count,)
        or bool(((visible_counts < 1) | (visible_counts > keys.shape[1])).any())
    ):
        raise InputError("visible_counts must be CPU int64 [Q] with counts in [1,N]")
    frozen_queries = queries.detach()
    frozen_keys = keys.detach()
    scale = math.sqrt(dimension)
    loss = references.sum() * 0.0
    for query_index in range(query_count):
        visible = int(visible_counts[query_index].item())
        query = frozen_queries[:, query_index]
        raw_logits = (frozen_keys[:, :visible] * query.unsqueeze(1)).sum(-1) / scale
        require_finite("teacher logits", raw_logits)
        for level in range(1, depth + 1):
            span = chunk_size**level
            full_count = (visible - 1) // span
            complete_stop = 1 + full_count * span
            predicted = [raw_logits[:, :1]]
            teacher = [raw_logits[:, :1]]
            if full_count:
                blocks = frozen_keys[:, 1:complete_stop].reshape(
                    heads * full_count, span, dimension
                )
                expanded_references = (
                    references[:, None]
                    .expand(heads, full_count, references.shape[1], dimension)
                    .reshape(heads * full_count, references.shape[1], dimension)
                )
                summary = summarize(blocks, expanded_references)
                means = summary.means.reshape(heads, full_count, references.shape[1], dimension)
                biases = summary.biases.reshape(heads, full_count, references.shape[1])
                scores = (means * query[:, None, None]).sum(-1) / scale + biases
                predicted.append(scores.amax(dim=-1))
                teacher.append(
                    raw_logits[:, 1:complete_stop].reshape(heads, full_count, span).logsumexp(-1)
                )
            if complete_stop < visible:
                exact_tail = raw_logits[:, complete_stop:].logsumexp(-1, keepdim=True)
                teacher.append(exact_tail)
                predicted.append(exact_tail)
            teacher_log = torch.log_softmax(torch.cat(teacher, dim=-1), dim=-1)
            predicted_log = torch.log_softmax(torch.cat(predicted, dim=-1), dim=-1)
            require_finite("pooled teacher log probabilities", teacher_log)
            require_finite("pooled predicted log probabilities", predicted_log)
            loss = loss + (teacher_log.exp() * (teacher_log - predicted_log)).sum(-1).mean()
    loss = loss / query_count
    require_finite("pooled KL loss", loss)
    return loss
