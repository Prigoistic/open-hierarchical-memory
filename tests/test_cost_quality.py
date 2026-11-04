import copy
import json
from pathlib import Path

import pytest
import torch
import torch.nn.functional as functional

from open_hierarchical_memory import TreeConfig
from research.cost_quality import (
    aggregate_quality,
    benchmark_routes,
    choose_on_validation,
    positions_for,
    quality_records,
    sdpa_inputs,
    validate_study,
)
from research.fitting import TraceExample

ROOT = Path(__file__).resolve().parents[1]


def settings():
    return json.loads((ROOT / "research/cost_quality_protocol.json").read_text())


def manifest(config):
    return {
        "schema_version": 1,
        "model_id": config["model_id"],
        "model_revision": config["model_revision"],
        "documents": [
            {"book_id": book, "split": split, "body_sha256": f"{book:064x}"}
            for split, ids in config["splits"].items()
            for book in ids
        ],
    }


def candidates(config):
    return [
        {
            "context": 256,
            "split": "validation",
            "geometry": g["id"],
            "p": p,
            "seeds": config["seeds"],
            "metrics": {
                "relative_l2_error": {"mean": 0.04, "p95": 0.15},
                "qk_plus_av_vector_work_ratio": {"mean": 1.0},
            },
        }
        for g in config["geometries"]
        for p in config["routing_thresholds"]
    ]


def test_study_enforces_native_context_fresh_holdout_and_unique_grid():
    config = settings()
    validate_study(config, manifest(config))
    assert positions_for(config, 1024) == (255, 511, 767, 1023)
    bad = copy.deepcopy(config)
    bad["splits"]["test"] = [74]
    with pytest.raises(ValueError, match="previous pilot"):
        validate_study(bad, manifest(bad))
    bad = copy.deepcopy(config)
    bad["contexts"] = [2048]
    with pytest.raises(ValueError, match="context"):
        validate_study(bad, manifest(bad))
    bad = copy.deepcopy(config)
    bad["geometries"].append(bad["geometries"][0])
    with pytest.raises(ValueError, match="unique geometry"):
        validate_study(bad, manifest(bad))


def test_selection_cannot_accept_test_missing_seed_or_incomplete_grid():
    config = settings()
    for modify, message in [
        (lambda rows: rows[0].update(split="test"), "validation data only"),
        (lambda rows: rows[0].update(seeds=[7]), "all prespecified seeds"),
        (lambda rows: rows.pop(), "complete unique"),
    ]:
        rows = candidates(config)
        modify(rows)
        with pytest.raises(ValueError, match=message):
            choose_on_validation(rows, config, 256)


def test_selection_has_a_real_quality_gate_and_deterministic_cost_choice():
    config = settings()
    rows = candidates(config)
    # An extremely cheap row must be rejected when quality is outside budget.
    rows[0]["metrics"]["qk_plus_av_vector_work_ratio"]["mean"] = 0.001
    rows[0]["metrics"]["relative_l2_error"]["p95"] = 0.3
    chosen = choose_on_validation(rows, config, 256)
    assert chosen["geometry"] == "c16-r2-d2"
    assert chosen["p"] == 0.73
    for row in rows:
        row["metrics"]["relative_l2_error"]["mean"] = 0.1
    assert choose_on_validation(rows, config, 256) is None


def test_same_budget_mass_oracle_and_work_counts_match_uniform_closed_form():
    q = torch.zeros((1, 17, 2), dtype=torch.float64)
    sample = TraceExample("uniform", 0, q, q.clone(), torch.ones_like(q))
    refs = torch.zeros((1, 2, 2), dtype=torch.float64)
    records = quality_records(
        [sample], refs, (0, 8, 16), TreeConfig(chunk_size=2, depth=2), 0.5, 1e-12
    )
    for row in records:
        assert row["retained_mass"] == pytest.approx(row["selected_keys"] / row["visible_keys"])
        assert row["oracle_topk_retained_mass"] == pytest.approx(row["retained_mass"])
        assert row["same_k_mass_gap"] == pytest.approx(0, abs=1e-12)
        assert row["relative_l2_error"] == pytest.approx(0, abs=1e-12)
        assert (
            row["qk_score_ratio"]
            == (2 * row["scored_summary_nodes"] + row["selected_keys"]) / row["visible_keys"]
        )
    assert aggregate_quality(records)["relative_l2_error"]["count"] == 3


def test_relative_error_is_finite_for_zero_dense_output():
    q = torch.zeros((1, 9, 2), dtype=torch.float64)
    records = quality_records(
        [TraceExample("zero", 0, q, q.clone(), q.clone())],
        torch.zeros((1, 2, 2), dtype=torch.float64),
        (8,),
        TreeConfig(chunk_size=2, depth=2),
        0.5,
        1e-12,
    )
    assert records[0]["relative_l2_error"] == 0


def test_sdpa_uses_offset_prefix_mask_instead_of_upper_left_decode_mask():
    q = torch.zeros((1, 9, 2), dtype=torch.float64)
    v = torch.arange(18, dtype=torch.float64).reshape(1, 9, 2)
    sample = TraceExample("offset", 0, q, q.clone(), v)
    query, key, value, visible, mask = sdpa_inputs(sample, (4, 8))
    result = functional.scaled_dot_product_attention(query, key, value, attn_mask=mask, dropout_p=0)
    torch.testing.assert_close(result[0, 0, 0], v[0, :5].mean(0))
    torch.testing.assert_close(result[0, 0, 1], v[0, :9].mean(0))
    assert visible.tolist() == [[5, 9]]


def test_benchmark_reports_build_memory_and_static_amortization_separately():
    q = torch.zeros((1, 17, 2), dtype=torch.float64)
    sample = TraceExample("timing", 0, q, q.clone(), torch.ones_like(q))
    timing = {
        "warmup_rounds": 1,
        "timed_rounds": 2,
        "build_warmup_rounds": 1,
        "build_timed_rounds": 2,
        "order_seed": 7,
        "static_snapshot_reuse_counts": [1, 16],
    }
    result = benchmark_routes(
        [sample],
        torch.zeros((1, 2, 2), dtype=torch.float64),
        (8, 16),
        TreeConfig(chunk_size=2, depth=2),
        0.5,
        timing,
    )
    assert result["owned_index_tensor_bytes"] > result["raw_kv_tensor_bytes"]
    assert result["active_summary_levels"] == 2
    assert len(result["timing"]["sdpa_dense"]["raw_ms_per_window_batch"]) == 2
    query_ms = result["timing"]["hierarchical"]["median"]
    build_ms = result["tree_build_ms_per_window_batch"]["median"]
    assert result["timing"]["static_reuse_16"][
        "estimated_ms_per_batch_including_amortized_build"
    ] == pytest.approx(query_ms + build_ms / 16)


def test_captured_noncontiguous_projection_views_roundtrip_without_value_changes(tmp_path):
    safetensors = pytest.importorskip("safetensors.torch")
    from research.cost_quality import save_trace

    view = torch.arange(2 * 17 * 3, dtype=torch.float64).reshape(17, 2, 3).transpose(0, 1)
    assert not view.is_contiguous()
    sample = TraceExample("projection-view", 0, view, view + 1, view + 2)
    destination = tmp_path / "trace.safetensors"
    save_trace(sample, destination)
    restored = safetensors.load_file(str(destination))
    for name in ("queries", "keys", "values"):
        torch.testing.assert_close(restored[name], getattr(sample, name), rtol=0, atol=0)
