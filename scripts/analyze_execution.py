"""Summarize measured execution experiments and exploratory reference frontiers.

This is post-run analysis of fixed records, not fitting or new test selection.
"""

import argparse
import hashlib
import json
import math
import statistics
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "experiments/execution-profile-v1"
DEFAULT_RUN = ROOT / "experiments/batched-execution-v2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    processes = [json.loads((run / f"process-{i}.json").read_text()) for i in range(3)]
    parity = json.loads((run / "parity.json").read_text())
    if (
        not parity["selected_ids_equal"]
        or not parity["physical_scored_nodes_and_keys_equal"]
        or parity["query_head_cases"] != 96768
    ):
        raise AssertionError("incomplete real-trace parity gate")
    for report in [parity, *processes]:
        for path, digest in report["source_sha256"].items():
            committed = subprocess.check_output(
                ["git", "show", f"{report['git_revision']}:{path}"], cwd=ROOT
            )
            if hashlib.sha256(committed).hexdigest() != digest:
                raise AssertionError("recorded source hash differs from source commit")
    rows = [row for process in processes for row in process["rows"]]
    if len(rows) != 81 or any(row["engine"] != "batched" for row in rows):
        raise AssertionError("missing timing cases or hidden reference dispatch")
    aggregate = []
    for context in (256, 512, 1024):
        for layout in ("separate_four_queries", "stacked_four_queries", "separate_last_query"):
            cases = [row for row in rows if row["context"] == context and row["layout"] == layout]
            if len(cases) != 9:
                raise AssertionError("missing process/seed cases")
            timing = {}
            for engine in ("reference", "batched", "sdpa"):
                values = []
                for row in cases:
                    observed = row["timing"][engine]
                    if observed["count"] != 50 or observed["median"] != statistics.median(
                        observed["raw_ms_per_window_batch"]
                    ):
                        raise AssertionError("timing arithmetic mismatch")
                    values.extend(observed["raw_ms_per_window_batch"])
                ordered = sorted(values)
                timing[engine] = {
                    "mean_seed_process_median_ms": statistics.fmean(
                        r["timing"][engine]["median"] for r in cases
                    ),
                    "pooled_p95_ms": ordered[math.ceil(0.95 * len(ordered)) - 1],
                    "pooled_p99_ms": ordered[math.ceil(0.99 * len(ordered)) - 1],
                    "measured_batches": len(values),
                }
            before = timing["reference"]["mean_seed_process_median_ms"]
            after = timing["batched"]["mean_seed_process_median_ms"]
            dense = timing["sdpa"]["mean_seed_process_median_ms"]
            build_before = statistics.fmean(r["construction"]["reference"]["median"] for r in cases)
            build_after = statistics.fmean(r["construction"]["batched"]["median"] for r in cases)
            for row in cases:
                if (
                    row["selected_key_slots"] < 1
                    or row["ordering_slots"] < row["scored_summary_slots"]
                    or row["attention_softmax_slots"] < row["selected_key_slots"]
                ):
                    raise AssertionError("invalid physical/padding counters")
            aggregate.append(
                {
                    "context": context,
                    "layout": layout,
                    "query_head_cases_per_batch": cases[0]["query_head_cases"],
                    "timing": timing,
                    "reference_over_batched_speed_ratio": before / after,
                    "sdpa_over_batched_speed_ratio": dense / after,
                    "reference_build_ms": build_before,
                    "batched_build_ms": build_after,
                    "one_use_speed_ratio_vs_sdpa": dense / (after + build_after),
                    "static128_speed_ratio_vs_sdpa": dense / (after + build_after / 128),
                    "reference_owned_tensor_bytes": cases[0]["reference_owned_tensor_bytes"],
                    "batched_owned_tensor_bytes": cases[0]["batched_owned_tensor_bytes"],
                    "ordering_padding_ratio": statistics.fmean(
                        r["ordering_slots"] / r["scored_summary_slots"] for r in cases
                    ),
                    "attention_softmax_padding_ratio": statistics.fmean(
                        r["attention_softmax_slots"] / r["selected_key_slots"] for r in cases
                    ),
                    "process_speed_ratios": [
                        statistics.fmean(
                            r["timing"]["reference"]["median"]
                            for r in p["rows"]
                            if r["context"] == context and r["layout"] == layout
                        )
                        / statistics.fmean(
                            r["timing"]["batched"]["median"]
                            for r in p["rows"]
                            if r["context"] == context and r["layout"] == layout
                        )
                        for p in processes
                    ],
                }
            )
    # Exploratory learning diagnostic. Existing test records are now development
    # evidence; neither fitting nor new held-out selection is performed here.
    study_path = ROOT / "experiments/gpt2-cost-quality-v1/report.json"
    study = json.loads(study_path.read_text())
    frontiers = []
    for context in study["config"]["contexts"]:
        for geometry in study["config"]["geometries"]:
            points = {}
            for variant in ("random_gaussian", "trained"):
                points[variant] = []
                for p in study["config"]["routing_thresholds"]:
                    selected = [
                        r
                        for r in study["test_grid"]
                        if r["context"] == context
                        and r["geometry"] == geometry["id"]
                        and r["p"] == p
                        and r["variant"] == variant
                    ]
                    points[variant].append(
                        {
                            "p": p,
                            "mean_relative_error": statistics.fmean(
                                r["metrics"]["relative_l2_error"]["mean"] for r in selected
                            ),
                            "mean_vector_work_ratio": statistics.fmean(
                                r["metrics"]["qk_plus_av_vector_work_ratio"]["mean"]
                                for r in selected
                            ),
                        }
                    )
            for fitted in points["trained"]:
                dominators = [
                    r
                    for r in points["random_gaussian"]
                    if r["mean_relative_error"] <= fitted["mean_relative_error"]
                    and r["mean_vector_work_ratio"] <= fitted["mean_vector_work_ratio"]
                    and (
                        r["mean_relative_error"] < fitted["mean_relative_error"]
                        or r["mean_vector_work_ratio"] < fitted["mean_vector_work_ratio"]
                    )
                ]
                frontiers.append(
                    {
                        "context": context,
                        "geometry": geometry["id"],
                        "trained_point": fitted,
                        "random_dominators_on_declared_grid": dominators,
                    }
                )
    diagnostic = {
        "scope": "Exploratory Pareto comparisons of mean errors and counted work on the already inspected original test cohort. Three thresholds only; no interpolation, significance or new generalization claim.",
        "source_report_sha256": sha(study_path),
        "points": frontiers,
        "trained_points_dominated_by_random": sum(
            bool(r["random_dominators_on_declared_grid"]) for r in frontiers
        ),
        "trained_points_compared": len(frontiers),
    }
    (run / "learning-diagnostic.json").write_text(json.dumps(diagnostic, indent=2) + "\n")
    result = {
        "aggregation": "Arithmetic mean of seed/process medians; p95/p99 pool 450 observed batches per engine/case. No confidence intervals. Three fresh processes, three frozen-reference seeds. Ratios below one are slower.",
        "input_hashes": {f"process-{i}.json": sha(run / f"process-{i}.json") for i in range(3)},
        "parity_sha256": sha(run / "parity.json"),
        "rows": aggregate,
    }
    (run / "aggregate.json").write_text(json.dumps(result, indent=2) + "\n")
    text = """# Profile-driven batched execution experiment

Completed 4 November 2026. This experiment profiles the existing reference and tests a separate batched research implementation without changing any numerical core source file or fitting any model parameters. It uses existing GPT-2 development traces, not a new model-quality holdout.

## What changed

The reference profile identified summary gathering, repeated per-query scoring/selection and raw-KV processing as substantial costs. The prototype packs summary copies, scores only actual candidates across independent queries, and processes selected KV in ragged batches. Sorting/softmax padding is reported separately. The prototype retains the immutable reference snapshot, so its additional storage is included.

The [implementation and fixed comparison protocol](../../docs/EXECUTION_BACKEND.md) describe its supported scope. Detailed traces, custom budgets, dense mode and fallback requests explicitly use the reference engine. Every timing row here confirms `engine=batched`; reference dispatch is not passed off as an optimization result.

## Correctness gates

"""
    text += f"""- All 252 trained geometry/context/seed/threshold combinations (including p=1) pass selected-ID and output checks across {parity["query_head_cases"]:,} query/head cases. Selected IDs and logical scoring counts match exactly; maximum absolute output difference is {parity["maximum_output_abs_difference"]:.3e}, within the unchanged `atol=1e-10, rtol=1e-9` tolerance.
- Scored summary slots and selected-key slots match the reference's logical work. No full-tree or full-prefix scoring is hidden behind a sparse mask. Padding affects ordering/softmax and is reported below.
- The local behavior suite passes, including sixty generated batched configurations checked against the independent scalar oracle. Six deliberately broken batched variants are detected, in addition to the ten original core mutations. Batch/GQA isolation, causality, ownership, budgets, p=1, dispatch and scratch limits are covered.
- The original core remains byte-identical to the profiled reference. Instrumented profiling separately checks exact output/route parity before reporting components. These self-checks and independent numerical algorithms are not an external review or a universal correctness proof.

## Measured query latency

Three fresh sequential processes, three fixed reference seeds, five warmups and fifty recorded repetitions per case. CPU float64, four threads. Each time is the arithmetic mean of nine process/seed medians for the complete eight-window batch. All three paths receive matching query layout and prefix masks. p=.90, C16/R2/depth2. There are 384 query/head cases for four-query layouts and 96 for final-query-only calls. These are static-cache workloads, not end-to-end generation.

| Context | Layout | Reference ms | Batched ms | Dense SDPA ms | Gain over reference | Speed ratio vs SDPA |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
"""
    labels = {
        "separate_four_queries": "8 separate calls / 4 queries",
        "stacked_four_queries": "1 stacked batch / 4 queries",
        "separate_last_query": "8 separate calls / final query",
    }
    for row in aggregate:
        t = row["timing"]
        text += f"| {row['context']} | {labels[row['layout']]} | {t['reference']['mean_seed_process_median_ms']:.3f} | {t['batched']['mean_seed_process_median_ms']:.3f} | {t['sdpa']['mean_seed_process_median_ms']:.3f} | {row['reference_over_batched_speed_ratio']:.2f}x | {row['sdpa_over_batched_speed_ratio']:.3f}x |\n"
    text += """
Gain over the old reference is an engineering comparison. Speed ratio vs SDPA is dense time divided by batched time; below one means the prototype is slower than dense. Native SDPA's layout changes with the hierarchical layout, so stacked speed cannot be attributed to sparse routing alone. Detailed tails, process-to-process ratios and raw times are retained.

## Construction, storage and padding

| Context | Layout | Batched build ms | One-use speed ratio vs SDPA | 128-static-use scenario | Owned tensor storage vs reference | Ordering padding | Attention-softmax padding |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
"""
    for row in aggregate:
        text += f"| {row['context']} | {labels[row['layout']]} | {row['batched_build_ms']:.3f} | {row['one_use_speed_ratio_vs_sdpa']:.4f}x | {row['static128_speed_ratio_vs_sdpa']:.4f}x | {row['batched_owned_tensor_bytes'] / row['reference_owned_tensor_bytes']:.3f}x | {row['ordering_padding_ratio']:.2f}x | {row['attention_softmax_padding_ratio']:.2f}x |\n"
    text += """
One use includes full construction. The 128-use scenario amortizes the same static snapshot's build, not an incrementally growing cache. Owned tensor storage includes canonical KV, references and both summary representations; it excludes caller data, Python metadata and scratch. Whole-process RSS includes both backends and data loading, and is not a per-setting inference memory measurement. Stage estimates are not hard process-RSS limits.

## Learning diagnosis remains separate

"""
    text += f"""On the previously inspected test records, random references dominate fitted references in error and counted work at {diagnostic["trained_points_dominated_by_random"]}/{diagnostic["trained_points_compared"]} fitted points on the original three-threshold grid within the same geometry/context. This is exploratory and not a new statistical result. It does not prove random references are always better; it prevents claiming that fitting consistently improves executed attention. See [every comparison](learning-diagnostic.json). Use validation data and a new sealed cohort for any further duration/data/loss study.

## Artifacts and remaining work

- [Aggregate timings](aggregate.json), [complete real-trace parity](parity.json), [learning diagnostic](learning-diagnostic.json).
- Raw workers: [process 0](process-0.json), [process 1](process-1.json), [process 2](process-2.json). Each records source hashes, dependency/platform metadata, work/padding, raw timings, index costs and explicit engine.
- [Reference component profile](../execution-profile-v1/SUMMARY.md), [core verification](../../docs/evidence/core-verification.json), [batched mutation evidence](../../docs/evidence/batched-mutations.json), [execution plan](../../docs/NEXT_EXPERIMENTS.md).

This remains one layer and contexts within GPT-2's native 1,024 positions. It changes execution, not the learned model or routing quality. No GPU, long-context language, whole-model generation, conservative-error or production-readiness result is implied. Profile any remaining gap before another optimization; preserve unfavorable layouts, build costs and memory. Incremental updates and new precision/backends require independent gates.
"""
    (run / "SUMMARY.md").write_text("\n".join(line.rstrip() for line in text.splitlines()) + "\n")
    profiles = [json.loads((PROFILE / f"process-{i}.json").read_text()) for i in range(3)]
    text = """# Reference execution profile

Completed before implementing the batched prototype. Existing development traces, frozen C16/R2/depth2, p=.90, CPU float64, four threads. Three fresh processes, three seeds, five warmups and fifty timed repetitions. Numbers below average nine seed/process medians for eight windows with four query positions each.

| Context | Reference query ms | Dense SDPA ms | Selected-ID replay ms |
| --- | ---: | ---: | ---: |
"""
    for context in (256, 512, 1024):
        cases = [r for p in profiles for r in p["rows"] if r["context"] == context]
        values = [
            statistics.fmean(r["timing"][name]["median"] for r in cases)
            for name in ("reference", "sdpa", "selected_id_replay")
        ]
        text += f"| {context} | {values[0]:.3f} | {values[1]:.3f} | {values[2]:.3f} |\n"
    text += """
Replay receives the actual selected IDs in advance and omits routing, public validation and result metadata. It is a diagnostic only. It remains slower than dense, so optimizing routing alone cannot close the gap in this execution style.

## Instrumented component attribution at 1,024 tokens, seed 7

These are exclusive component times from a separate instrumented call, not headline latency. Every instrumented call first matches exact reference outputs and routes. Inclusive parent times overlap children and must not be added together.

| Stage | Calls | Exclusive ms |
| --- | ---: | ---: |
"""
    component = next(
        r["components"] for r in profiles[0]["rows"] if r["context"] == 1024 and r["components"]
    )
    for name, row in component["stages"].items():
        text += f"| {name} | {row['calls']} | {row['exclusive_ms']:.3f} |\n"
    text += """
Summary gathering is the largest isolated measured component, but selected-ID replay also shows significant residual cost. The resulting prototype therefore batches actual candidate scoring and selected attention in addition to packing summary reads. Construction stages and full cProfile call records remain in process 0.

[Process 0](process-0.json), [process 1](process-1.json), [process 2](process-2.json), [prototype results](../batched-execution-v1/SUMMARY.md). Source hashes and the earlier study-report identity are retained in each process report. The numerical core was not edited by profiling.
"""
    (PROFILE / "SUMMARY.md").write_text(text)
    print(
        json.dumps(
            [
                {
                    k: r[k]
                    for k in (
                        "context",
                        "layout",
                        "reference_over_batched_speed_ratio",
                        "sdpa_over_batched_speed_ratio",
                    )
                }
                for r in aggregate
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
