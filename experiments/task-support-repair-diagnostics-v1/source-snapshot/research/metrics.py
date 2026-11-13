"""Offline dense-oracle measurements. These are not runtime certificates."""

import math
import statistics

import torch

from open_hierarchical_memory import ExecutionMode, HierarchicalIndex, TreeConfig

from .fitting import TraceExample


@torch.no_grad()
def evaluate_routes(
    samples: list[TraceExample],
    references,
    positions: tuple[int, ...],
    geometry: TreeConfig,
    p: float,
) -> list[dict]:
    records = []
    visible = torch.tensor([[position + 1 for position in positions]], dtype=torch.int64)
    for sample in samples:
        query = sample.queries[:, list(positions)]
        index = HierarchicalIndex(
            sample.keys.unsqueeze(0), sample.values.unsqueeze(0), references, config=geometry
        )
        sparse = index.attend(
            query.unsqueeze(0), visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=p
        )
        logits = query @ sample.keys.transpose(-2, -1) / math.sqrt(query.shape[-1])
        eligible = torch.arange(sample.keys.shape[1])[None, :] < visible[0, :, None]
        probabilities = logits.masked_fill(~eligible, float("-inf")).softmax(-1)
        dense = probabilities @ sample.values
        for route in sparse.routes:
            h, t = route.query_head, route.query_index
            weights = probabilities[h, t]
            retained = float(weights[list(route.selected_ids)].sum())
            non_sink = float(weights[1:].sum())
            retained_non_sink = float(weights[[i for i in route.selected_ids if i != 0]].sum())
            actual = sparse.output[0, h, t]
            error = float(torch.linalg.vector_norm(actual - dense[h, t]))
            if not -1e-12 <= retained <= 1 + 1e-12:
                raise ArithmeticError("invalid measured attention mass")
            if p == 1:
                torch.testing.assert_close(actual, dense[h, t], rtol=1e-9, atol=1e-10)
            records.append(
                {
                    "document_id": sample.document_id,
                    "window_offset": sample.window_offset,
                    "query_position": positions[t],
                    "query_head": h,
                    "retained_mass": retained,
                    "retained_non_sink_mass": retained_non_sink / non_sink
                    if non_sink > 1e-12
                    else None,
                    "attention_l2_error": error,
                    "selected_key_fraction": len(route.selected_ids) / route.visible_count,
                    "selected_keys": len(route.selected_ids),
                    "visible_keys": route.visible_count,
                    "scored_summary_nodes": route.scored_nodes,
                }
            )
    return records


def aggregate(records: list[dict]) -> dict:
    def summarize(name):
        values = sorted(record[name] for record in records if record[name] is not None)
        if not values:
            return {"count": 0, "mean": None, "median": None, "p95": None}
        return {
            "count": len(values),
            "mean": statistics.fmean(values),
            "median": statistics.median(values),
            "p95": values[math.ceil(0.95 * len(values)) - 1],
        }

    return {
        name: summarize(name)
        for name in [
            "retained_mass",
            "retained_non_sink_mass",
            "attention_l2_error",
            "selected_key_fraction",
            "scored_summary_nodes",
        ]
    }
