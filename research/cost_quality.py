"""Cost/quality diagnostics, deterministic validation selection and CPU timing.

All dense-oracle quality calculations are outside timed execution. The vector
work counters are proxies, not full FLOP, latency or traffic estimates.
"""

import math
import random
import statistics
import time
from collections.abc import Callable

import torch
import torch.nn.functional as functional

from open_hierarchical_memory import ExecutionMode, HierarchicalIndex, TreeConfig

from .fitting import TraceExample
from .metrics import evaluate_routes
from .protocol import validate_protocol

METRICS = (
    "retained_mass",
    "retained_non_sink_mass",
    "attention_l2_error",
    "relative_l2_error",
    "selected_key_fraction",
    "selected_keys",
    "scored_summary_nodes",
    "qk_score_ratio",
    "qk_plus_av_vector_work_ratio",
    "oracle_topk_retained_mass",
    "same_k_mass_gap",
)


def positions_for(config: dict, context: int) -> tuple[int, ...]:
    return tuple(context * quarter // 4 - 1 for quarter in config["query_quarters"])


def validate_study(config: dict, manifest: dict) -> None:
    contexts = config["contexts"]
    if contexts != sorted(set(contexts)) or not contexts:
        raise ValueError("unique ordered contexts required")
    if config["query_quarters"] != [1, 2, 3, 4]:
        raise ValueError("study requires the four declared quarter positions")
    for context in contexts:
        validate_protocol(
            {
                **config,
                "context_tokens": context,
                "query_positions": list(positions_for(config, context)),
            },
            manifest,
        )
    if set(config["splits"]["test"]) & set(config["previous_pilot_documents"]):
        raise ValueError("new held-out documents must exclude all previous pilot documents")
    seeds = config["seeds"]
    if not seeds or len(set(seeds)) != len(seeds) or any(type(s) is not int for s in seeds):
        raise ValueError("unique integer seeds required")
    ids = []
    for geometry in config["geometries"]:
        TreeConfig(chunk_size=geometry["chunk_size"], depth=geometry["depth"])
        if type(geometry["reference_count"]) is not int or geometry["reference_count"] < 1:
            raise ValueError("positive reference count required")
        ids.append(geometry["id"])
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("unique geometry identities required")
    thresholds = config["routing_thresholds"]
    if (
        not thresholds
        or thresholds != sorted(set(thresholds))
        or any(
            type(p) not in (int, float) or not math.isfinite(p) or not 0 < p <= 1
            for p in thresholds
        )
    ):
        raise ValueError("unique valid thresholds required")
    for field in ("max_mean_relative_l2", "max_p95_relative_l2", "relative_l2_denominator_floor"):
        value = config["selection"][field]
        if not math.isfinite(value) or value <= 0:
            raise ValueError("finite positive quality thresholds required")
    timing = config["timing"]
    for field in (
        "cpu_threads",
        "warmup_rounds",
        "timed_rounds",
        "build_warmup_rounds",
        "build_timed_rounds",
    ):
        if type(timing[field]) is not int or timing[field] < 1:
            raise ValueError("positive timing counts required")
    if not timing["static_snapshot_reuse_counts"] or any(
        type(n) is not int or n < 1 for n in timing["static_snapshot_reuse_counts"]
    ):
        raise ValueError("positive static reuse counts required")


def distribution(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "mean": None, "median": None, "p95": None}
    if any(not math.isfinite(value) for value in values):
        raise ValueError("nonfinite measurement")
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "mean": statistics.fmean(ordered),
        "median": statistics.median(ordered),
        "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
    }


def aggregate_quality(records: list[dict]) -> dict:
    return {
        name: distribution([r[name] for r in records if r[name] is not None]) for name in METRICS
    }


@torch.no_grad()
def quality_records(
    samples: list[TraceExample],
    references,
    positions: tuple[int, ...],
    geometry: TreeConfig,
    p: float,
    denominator_floor: float,
) -> list[dict]:
    if not math.isfinite(denominator_floor) or denominator_floor <= 0:
        raise ValueError("positive denominator floor required")
    records = evaluate_routes(samples, references, positions, geometry, p)
    by_sample = {(s.document_id, s.window_offset): s for s in samples}
    if len(by_sample) != len(samples):
        raise ValueError("duplicate sample identity")
    # Compute targets once per window, independently of the timed SDPA baseline.
    targets = {}
    for identity, sample in by_sample.items():
        queries = sample.queries[:, list(positions)]
        logits = queries @ sample.keys.transpose(-2, -1) / math.sqrt(queries.shape[-1])
        visible = torch.tensor([position + 1 for position in positions])
        eligible = torch.arange(sample.keys.shape[1])[None, :] < visible[:, None]
        weights = logits.masked_fill(~eligible, float("-inf")).softmax(-1)
        targets[identity] = (weights, weights @ sample.values)
    for record in records:
        weights, outputs = targets[record["document_id"], record["window_offset"]]
        head, pos = record["query_head"], positions.index(record["query_position"])
        norm = float(torch.linalg.vector_norm(outputs[head, pos]))
        record["dense_output_norm"] = norm
        record["relative_l2_error"] = record["attention_l2_error"] / max(norm, denominator_floor)
        count, visible, nodes = (
            record["selected_keys"],
            record["visible_keys"],
            record["scored_summary_nodes"],
        )
        record["qk_score_ratio"] = (references.shape[1] * nodes + count) / visible
        record["qk_plus_av_vector_work_ratio"] = (references.shape[1] * nodes + 2 * count) / (
            2 * visible
        )
        oracle = float(weights[head, pos, :visible].topk(count).values.sum())
        if oracle + 1e-10 < record["retained_mass"]:
            raise ArithmeticError("same-budget mass oracle violated")
        record["oracle_topk_retained_mass"] = oracle
        record["same_k_mass_gap"] = max(0.0, oracle - record["retained_mass"])
    return records


def choose_on_validation(candidates: list[dict], config: dict, context: int) -> dict | None:
    """Only pooled validation aggregates enter this selector, never test data."""
    expected = {(g["id"], p) for g in config["geometries"] for p in config["routing_thresholds"]}
    if {(row["geometry"], row["p"]) for row in candidates} != expected or len(candidates) != len(
        expected
    ):
        raise ValueError("complete unique validation grid required")
    eligible = []
    for row in candidates:
        if row["split"] != "validation" or row["context"] != context:
            raise ValueError("selection accepts this context's validation data only")
        if row["seeds"] != config["seeds"]:
            raise ValueError("all prespecified seeds required for selection")
        metrics = row["metrics"]
        for name, statistic in [
            ("relative_l2_error", "mean"),
            ("relative_l2_error", "p95"),
            ("qk_plus_av_vector_work_ratio", "mean"),
        ]:
            value = metrics[name][statistic]
            if value is None or not math.isfinite(value):
                raise ValueError("finite validation measurements required")
        if (
            metrics["relative_l2_error"]["mean"] <= config["selection"]["max_mean_relative_l2"]
            and metrics["relative_l2_error"]["p95"] <= config["selection"]["max_p95_relative_l2"]
        ):
            eligible.append(row)
    if not eligible:
        return None
    best = min(
        eligible,
        key=lambda r: (r["metrics"]["qk_plus_av_vector_work_ratio"]["mean"], r["geometry"], r["p"]),
    )
    return {
        "context": context,
        "geometry": best["geometry"],
        "p": best["p"],
        "validation_metrics": best["metrics"],
        "eligible_pairs": len(eligible),
    }


@torch.no_grad()
def sdpa_inputs(sample: TraceExample, positions: tuple[int, ...]) -> tuple:
    queries = sample.queries[:, list(positions)].unsqueeze(0).contiguous()
    keys, values = sample.keys.unsqueeze(0), sample.values.unsqueeze(0)
    visible = torch.tensor([[position + 1 for position in positions]], dtype=torch.int64)
    mask = torch.arange(sample.keys.shape[1])[None, :] < visible[0, :, None]
    return queries, keys, values, visible, mask


def timed_batches(functions: dict[str, Callable], config: dict) -> dict:
    """Interleave deterministic randomized order; clocks exclude quality oracles."""
    measurements = {name: [] for name in functions}
    generator = random.Random(config["order_seed"])
    for repetition in range(config["warmup_rounds"] + config["timed_rounds"]):
        names = list(functions)
        generator.shuffle(names)
        for name in names:
            started = time.perf_counter_ns()
            result = functions[name]()
            elapsed = (time.perf_counter_ns() - started) / 1e6
            del result
            if repetition >= config["warmup_rounds"]:
                measurements[name].append(elapsed)
    return {
        name: {**distribution(values), "raw_ms_per_window_batch": values}
        for name, values in measurements.items()
    }


@torch.no_grad()
def benchmark_routes(
    samples: list[TraceExample],
    references,
    positions: tuple[int, ...],
    geometry: TreeConfig,
    p: float,
    config: dict,
) -> dict:
    prepared = [sdpa_inputs(sample, positions) for sample in samples]
    build = []
    indexes = []
    for repetition in range(config["build_warmup_rounds"] + config["build_timed_rounds"]):
        started = time.perf_counter_ns()
        fresh = [HierarchicalIndex(k, v, references, config=geometry) for _, k, v, _, _ in prepared]
        elapsed = (time.perf_counter_ns() - started) / 1e6
        indexes = fresh
        if repetition >= config["build_warmup_rounds"]:
            build.append(elapsed)

    def sparse():
        return [
            index.attend(
                q,
                visible_counts=visible,
                mode=ExecutionMode.PAPER_APPROXIMATE,
                p=p,
                collect_trace=False,
            )
            for index, (q, _, _, visible, _) in zip(indexes, prepared, strict=True)
        ]

    def dense():
        return [
            functional.scaled_dot_product_attention(q, k, v, attn_mask=mask, dropout_p=0.0)
            for q, k, v, _, mask in prepared
        ]

    # Verify SDPA's prefix masking outside the timed region.
    for q, k, v, visible, mask in prepared:
        logits = q @ k.transpose(-2, -1) / math.sqrt(q.shape[-1])
        manual = logits.masked_fill(~mask, float("-inf")).softmax(-1) @ v
        native = functional.scaled_dot_product_attention(q, k, v, attn_mask=mask, dropout_p=0.0)
        torch.testing.assert_close(native, manual, atol=1e-10, rtol=1e-9)
        assert torch.equal(mask.sum(-1), visible[0])
    timing = timed_batches({"sdpa_dense": dense, "hierarchical": sparse}, config)
    for reuse in config["static_snapshot_reuse_counts"]:
        cost = statistics.median(build) / reuse + timing["hierarchical"]["median"]
        timing[f"static_reuse_{reuse}"] = {
            "estimated_ms_per_batch_including_amortized_build": cost,
            "sdpa_over_hierarchical_speed_ratio": timing["sdpa_dense"]["median"] / cost,
        }
    raw_bytes = sum(
        k.numel() * k.element_size() + v.numel() * v.element_size() for _, k, v, _, _ in prepared
    )
    owned = sum(index.info.owned_tensor_bytes for index in indexes)
    return {
        "window_count": len(samples),
        "query_head_cases": len(samples) * references.shape[0] * len(positions),
        "tree_build_ms_per_window_batch": {**distribution(build), "raw": build},
        "owned_index_tensor_bytes": owned,
        "raw_kv_tensor_bytes": raw_bytes,
        "owned_index_over_raw_kv_ratio": owned / raw_bytes,
        "nodes_per_window": len(indexes[0].info.spans),
        "active_summary_levels": len({span.node_id.level for span in indexes[0].info.spans}),
        "timing": timing,
        "scope": "CPU float64, no quality oracle or detailed trace in timing. Index construction includes ownership copies and hashing. Reuse is a static-snapshot scenario, not growing-cache decode. Tensor bytes exclude caller storage, Python/scratch allocations and process RSS.",
    }
