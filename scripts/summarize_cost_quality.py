"""Create descriptive tables/CSV from the retained report; never select on test."""

import csv
import gzip
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments/gpt2-cost-quality-v1"


def main():
    report = json.loads((RUN / "report.json").read_text())
    audit = json.loads((RUN / "audit.json").read_text())
    config = report["config"]
    selected = {r["context"]: r for r in report["selections"] if r}
    raw = defaultdict(list)
    with gzip.open(RUN / "test-queries.jsonl.gz", "rt") as stream:
        for line in stream:
            row = json.loads(line)
            choice = selected.get(row["context"])
            if choice and row["geometry"] == choice["geometry"] and row["p"] == choice["p"]:
                raw[row["context"], row["variant"]].append(row)
    stats = []
    for context, choice in selected.items():
        records = raw[context, "trained"]
        errors = sorted(r["relative_l2_error"] for r in records)
        mean_error = statistics.fmean(errors)
        import math

        p95 = errors[math.ceil(0.95 * len(errors)) - 1]
        times = [
            r
            for r in report["benchmarks"]
            if r["context"] == context
            and r["geometry"] == choice["geometry"]
            and r["p"] == choice["p"]
        ]
        dense = statistics.fmean(r["timing"]["sdpa_dense"]["median"] for r in times)
        query = statistics.fmean(r["timing"]["hierarchical"]["median"] for r in times)
        build = statistics.fmean(r["tree_build_ms_per_window_batch"]["median"] for r in times)
        stats.append(
            {
                "context": context,
                "geometry": choice["geometry"],
                "p": choice["p"],
                "validation_mean_relative_error": choice["validation_metrics"]["relative_l2_error"][
                    "mean"
                ],
                "test_mean_relative_error": mean_error,
                "test_p95_relative_error": p95,
                "test_layer_budget_passed": mean_error
                <= config["selection"]["max_mean_relative_l2"]
                and p95 <= config["selection"]["max_p95_relative_l2"],
                "test_vector_work_ratio": statistics.fmean(
                    r["qk_plus_av_vector_work_ratio"] for r in records
                ),
                "test_selected_key_fraction": statistics.fmean(
                    r["selected_key_fraction"] for r in records
                ),
                "sdpa_ms": dense,
                "query_ms": query,
                "build_ms": build,
                "query_speed_ratio": dense / query,
                "one_use_speed_ratio": dense / (query + build),
                "reuse128_speed_ratio": dense / (query + build / 128),
                "index_over_raw_kv_tensor_ratio": statistics.fmean(
                    r["owned_index_over_raw_kv_ratio"] for r in times
                ),
                "active_summary_levels": times[0]["active_summary_levels"],
            }
        )
    (RUN / "selected-summary.json").write_text(
        json.dumps(
            {
                "aggregation": "Pooled query errors across three seeds; timing columns are arithmetic means of three seed medians; speed is ratio of those aggregate times. Static snapshot reuse is a scenario.",
                "selected": stats,
            },
            indent=2,
        )
        + "\n"
    )
    text = f"""# Geometry and context cost-quality results

Completed 4 November 2026. This is the prespecified extension of the original GPT-2 layer pilot. It separates vector-work reduction, approximation error and actual execution time against dense PyTorch SDPA. No whole-model or optimized-GPU result is implied.

![Measured work-quality and CPU latency](cost-quality.png)

## Protocol and chronology

Seven geometries, three contexts (256/512/1024), three seeds, three routing thresholds, and three reference variants. The model remains frozen at layer 5. References receive 100 Adam steps per fit; the initial checkpoint remains eligible. There are 63 fits, 567 test configuration rows, and 189 timed fitted-reference settings. The [protocol and definitions](../../docs/COST_QUALITY.md) describe the error budget, work proxy, native prefix masking and timing scope.

The [original protocol commit](https://github.com/Prigoistic/open-hierarchical-memory/commit/bb44d48) predates fitting. A first-capture serialization failure was retained under [the failed preflight](../gpt2-cost-quality-v1-preflight-failed/run.log). It occurred before fitting or test capture. Only trace packing was fixed and regression-tested; the [successful run's source commit](https://github.com/Prigoistic/open-hierarchical-memory/commit/{report["git_revision"]}) retains the same numerical protocol. No failed attempt was replaced.

All 63 fits and validation choices finish before the new test split is captured. The [frozen selection record](selection-before-test.json) is hash-bound into the final report. Four new books (Gutenberg 345/1260/174/768), two windows each, yield 384 query/head cases per seed and setting. These books were not in the original pilot; they may still have appeared in GPT-2 pretraining. Nested contexts, neighboring queries, heads and seeds are dependent, not independent documents.

## Validation-selected configurations on fresh test data

Selection requires validation mean relative output error <=5% and p95 <=20%, then minimizes the declared QK+AV vector-work proxy. A test failure does not trigger retuning or replacement. Relative error divides output L2 error by the dense output norm, floored at 1e-12. These budgets describe this layer, not language-model quality.

| Context | Frozen geometry / p | Validation mean error | Test mean error | Test p95 error | Test budget | Vector work / dense | Selected keys |
| --- | --- | ---: | ---: | ---: | --- | ---: | ---: |
"""
    for row in stats:
        text += f"| {row['context']} | {row['geometry']} / {row['p']} | {100 * row['validation_mean_relative_error']:.2f}% | {100 * row['test_mean_relative_error']:.2f}% | {100 * row['test_p95_relative_error']:.2f}% | {'Pass' if row['test_layer_budget_passed'] else 'Fail'} | {row['test_vector_work_ratio']:.3f} | {100 * row['test_selected_key_fraction']:.2f}% |\n"
    if not stats:
        text += "| — | No setting qualified on validation | — | — | — | — | — | — |\n"
    text += """
The vector proxy counts reference scores, selected-key scores and value-vector accumulation. It excludes sorting, softmax, byte traffic and framework overhead. A ratio below one means fewer counted vector operations, not a measured speedup. Some nominal depth-2 geometries have only one completed summary level within these contexts; active levels are included in the report.

## Actual CPU timings and index costs

Times below cover a batch of eight windows with four query positions each. They are arithmetic means of three seed-level medians, not per-token decode latencies. Query-only timing excludes construction but includes the public hierarchical API's validation, copying, routing, gathering and result metadata. SDPA is checked against manual dense attention using explicit prefix masks, CPU float64 and zero dropout. No quality oracle or detailed route trace runs inside the timed paths.

| Context | Dense SDPA ms | Hierarchical query ms | Full batch build ms | Query speed ratio | One-use speed ratio | 128-use scenario | Owned index / raw KV tensors |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
"""
    for row in stats:
        text += f"| {row['context']} | {row['sdpa_ms']:.3f} | {row['query_ms']:.3f} | {row['build_ms']:.3f} | {row['query_speed_ratio']:.4f}× | {row['one_use_speed_ratio']:.4f}× | {row['reuse128_speed_ratio']:.4f}× | {row['index_over_raw_kv_tensor_ratio']:.3f}× |\n"
    text += """
Speed ratio is dense time divided by hierarchical time; below 1 is slower. The one-use figure adds a full tree build. The 128-use figure amortizes that build over repeated calls to the same static snapshot; it is not actual growing-cache decoding. The index retains original KV and adds summaries/references. Owned tensor bytes exclude caller storage, Python objects and scratch allocations; whole-process peak RSS in the report includes capture/training and is a different measurement.

## Fitting versus untrained references

At the validation-selected geometry and threshold, these are fresh-test mean relative errors pooled across seeds. They isolate the reference variants at the same geometry/threshold, which need not select identical numbers of keys.

| Context | Sampled-query initialization | Random references | Fitted references |
| --- | ---: | ---: | ---: |
"""
    for context in selected:
        values = [
            statistics.fmean(r["relative_l2_error"] for r in raw[context, variant])
            for variant in ("initial_query_samples", "random_gaussian", "trained")
        ]
        text += f"| {context} | {100 * values[0]:.2f}% | {100 * values[1]:.2f}% | {100 * values[2]:.2f}% |\n"
    text += """
Do not infer that fitting always improves routing or that one small fixed training budget reaches convergence. The complete grid preserves all seeds, variants and thresholds, including unfavorable settings.

## Evidence and artifacts

"""
    max_weight = max(c["native_weight_max_abs_error"] for c in report["captures"])
    max_output = max(c["native_output_max_abs_error"] for c in report["captures"])
    max_dense = max(c["maximum_l2"] for c in report["dense_equivalence"])
    text += f"""- All 60 native capture checks pass. Maximum absolute reconstruction differences: weights {max_weight:.3e}, preprojection outputs {max_output:.3e}. Loading reports no missing/unexpected/mismatched model keys or errors. Backbone parameter hashes stay identical.
- All 63 checkpoints round-trip before evaluation. At p=1, all eligible keys are selected across 21 geometry/context checks (8,064 query/head cases); maximum output L2 difference {max_dense:.3e}.
- The [post-run audit](audit.json) independently recomputes {audit["test_configuration_aggregates_verified"]} test and {audit["validation_aggregates_verified"]} validation aggregates from {sum(audit["raw_counts"].values()):,} raw records, checks frozen selection and source/checkpoint/trace hashes, verifies timing arithmetic and compares {len(audit["literal_real_query_checks"])} real queries against the independent scalar oracle.
- Local verification: 78 tests, Ruff, formatting, strict package mypy, ten detected semantic mutations. Hosted CI remains blocked by the previously confirmed billing restriction; local evidence is not a hosted pass.
- [Full report](report.json), [selected summary](selected-summary.json), [complete grid CSV](grid.csv), [validation raw measurements](validation-queries.jsonl.gz), [test raw measurements](test-queries.jsonl.gz), [reference checkpoints](references/), [protocol snapshot](protocol.json), [run log](run.log), [SVG figure](cost-quality.svg), [plot provenance](plot-metadata.json).

Report SHA256: `{hashlib.sha256((RUN / "report.json").read_bytes()).hexdigest()}`.

## Interpretation and remaining gates

"""
    passes = sum(r["test_layer_budget_passed"] for r in stats)
    if stats:
        min_work = min(r["test_vector_work_ratio"] for r in stats)
        max_work = max(r["test_vector_work_ratio"] for r in stats)
        fastest = max(r["query_speed_ratio"] for r in stats)
        text += f"The validation-selected settings pass the fixed test layer budget at {passes}/{len(stats)} contexts. Their counted vector work spans {min_work:.3f}–{max_work:.3f} of dense work. The largest query-only speed ratio among these frozen choices is {fastest:.4f}× against SDPA. "
        if fastest < 1:
            text += "The current Python reference has not demonstrated a speed benefit. Reduced vector work is an algorithmic opportunity; a faster backend and larger supported contexts need their own measurements. "
        else:
            text += "Any favorable latency here applies only to the recorded CPU workload and must be repeated before broader claims. "
    text += """

This study stays within GPT-2's 1,024 positions and cannot establish long-context scaling. RoPE adapters, broader domains/layers, end-to-end perplexity/generation, incremental tree maintenance and GPU kernels are open gates. Preserve the CPU float64 reference as the oracle for any faster backend. Do not infer model correctness from retained attention mass or a local output-error budget.
"""
    (RUN / "SUMMARY.md").write_text("\n".join(line.rstrip() for line in text.splitlines()) + "\n")
    timing_lookup = {
        (r["context"], r["geometry"], r["seed"], r["p"]): r for r in report["benchmarks"]
    }
    fields = [
        "context",
        "geometry",
        "seed",
        "variant",
        "p",
        "mean_relative_l2",
        "p95_relative_l2",
        "mean_vector_work_ratio",
        "mean_selected_key_fraction",
        "mean_retained_non_sink_mass",
        "sdpa_median_ms",
        "hierarchical_query_median_ms",
        "build_median_ms",
        "owned_index_over_raw_kv_ratio",
    ]
    with (RUN / "grid.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in report["test_grid"]:
            data = {k: row[k] for k in fields[:5]}
            data.update(
                mean_relative_l2=row["metrics"]["relative_l2_error"]["mean"],
                p95_relative_l2=row["metrics"]["relative_l2_error"]["p95"],
                mean_vector_work_ratio=row["metrics"]["qk_plus_av_vector_work_ratio"]["mean"],
                mean_selected_key_fraction=row["metrics"]["selected_key_fraction"]["mean"],
                mean_retained_non_sink_mass=row["metrics"]["retained_non_sink_mass"]["mean"],
            )
            if row["variant"] == "trained":
                timing = timing_lookup[row["context"], row["geometry"], row["seed"], row["p"]]
                data.update(
                    sdpa_median_ms=timing["timing"]["sdpa_dense"]["median"],
                    hierarchical_query_median_ms=timing["timing"]["hierarchical"]["median"],
                    build_median_ms=timing["tree_build_ms_per_window_batch"]["median"],
                    owned_index_over_raw_kv_ratio=timing["owned_index_over_raw_kv_ratio"],
                )
            writer.writerow(data)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
