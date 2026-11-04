"""Audit and summarize the fixed-data TRAIN/VALIDATION duration diagnosis."""

import gzip
import hashlib
import json
import math
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments/training-duration-diagnostic-v1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    report = json.loads((RUN / "report.json").read_text())
    if report["test_evaluated"] or not report["prior_100_step_checkpoints_reproduced_exactly"]:
        raise AssertionError("development boundary or reproduction gate failed")
    for path, digest in report["source_sha256"].items():
        raw = subprocess.check_output(["git", "show", f"{report['git_revision']}:{path}"], cwd=ROOT)
        if hashlib.sha256(raw).hexdigest() != digest:
            raise AssertionError("duration source identity mismatch")
    if sha(RUN / "validation-queries.jsonl.gz") != report["raw_validation_sha256"]:
        raise AssertionError("raw validation identity mismatch")
    groups = defaultdict(list)
    with gzip.open(RUN / "validation-queries.jsonl.gz", "rt") as stream:
        for line in stream:
            row = json.loads(line)
            if row["document_id"] not in report["validation_documents"]:
                raise AssertionError("non-validation sample in diagnosis")
            groups[row["seed"], row["maximum_steps"], row["variant"], row["p"]].append(row)
    checked = 0
    for fit in report["fits"]:
        if sha(RUN / fit["checkpoint"]) != fit["checkpoint_sha256"]:
            raise AssertionError("duration checkpoint changed")
        chosen = next(h for h in fit["history"] if h["step"] == fit["selected_step"])
        if chosen["validation_kl"] > min(h["validation_kl"] for h in fit["history"]) + 1e-12:
            raise AssertionError("checkpoint selection differs from validation minimum")
        for result in fit["quality"]:
            records = groups[fit["seed"], fit["maximum_steps"], result["variant"], result["p"]]
            if len(records) != 192:
                raise AssertionError("missing validation query/head cases")
            for name, expected in result["metrics"].items():
                values = sorted(r[name] for r in records if r[name] is not None)
                if len(values) != expected["count"]:
                    raise AssertionError("validation aggregate count mismatch")
                if values:
                    for actual, wanted in [
                        (statistics.fmean(values), expected["mean"]),
                        (statistics.median(values), expected["median"]),
                        (values[math.ceil(0.95 * len(values)) - 1], expected["p95"]),
                    ]:
                        if not math.isclose(actual, wanted, rel_tol=1e-10, abs_tol=1e-10):
                            raise AssertionError("validation aggregate mismatch")
            checked += 1
    rows = []
    for budget, variant in [
        (0, "initial_query_samples"),
        (0, "random_gaussian"),
        (100, "trained"),
        (300, "trained"),
        (1000, "trained"),
    ]:
        fits = [f for f in report["fits"] if f["maximum_steps"] == (budget or 100)]
        records = [
            r
            for seed in report["protocol"]["seeds"]
            for r in groups[seed, budget or 100, variant, 0.9]
        ]
        errors = sorted(r["relative_l2_error"] for r in records)
        loss = (
            statistics.fmean(min(h["validation_kl"] for h in f["history"]) for f in fits)
            if budget
            else None
        )
        rows.append(
            {
                "maximum_steps": budget,
                "variant": variant,
                "mean_selected_validation_kl": loss,
                "selected_steps": [f["selected_step"] for f in fits] if budget else [],
                "validation_mean_relative_error": statistics.fmean(errors),
                "validation_p95_relative_error": errors[math.ceil(0.95 * len(errors)) - 1],
                "validation_mean_vector_work_ratio": statistics.fmean(
                    r["qk_plus_av_vector_work_ratio"] for r in records
                ),
                "validation_mean_selected_key_fraction": statistics.fmean(
                    r["selected_key_fraction"] for r in records
                ),
            }
        )
    (RUN / "aggregate.json").write_text(
        json.dumps(
            {
                "scope": "Validation diagnosis at p=.90, pooled errors across three seeds. Validation selects checkpoints; no new holdout or learning-superiority claim.",
                "rows": rows,
            },
            indent=2,
        )
        + "\n"
    )
    audit = {
        "raw_records_verified": sum(len(v) for v in groups.values()),
        "configuration_aggregates_verified": checked,
        "source_commit_verified": report["git_revision"],
        "checkpoint_hashes_verified": len(report["fits"]),
        "test_evaluated": False,
        "prior_100_step_checkpoints_reproduced_exactly": True,
    }
    (RUN / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    text = """# Fixed-data training-duration diagnosis

This is a training/validation diagnosis, not a new model-quality test. The same 8,192 unique training tokens, C16/R2/depth2, three initializations, optimizer/lr and validation selection rule are reused. Only the maximum step budget changes: 100/300/1,000. Each arm restarts from its seed; longer training repeats the data. The original 100-step checkpoints reproduce exactly.

The loader refuses test activation requests. No old or fresh test activation is evaluated. Validation both selects checkpoints and supplies the diagnostic metrics, so favorable numbers are not new generalization evidence.

## Validation outcomes at the fixed p=.90 threshold

Errors and work are pooled across the three seeds' 576 validation query/head cases. These dependent observations come from two validation books. KL is the mean selected-checkpoint KL across seeds. Raw records preserve all three original thresholds, per-seed and per-book behavior.

| References / maximum budget | Selected steps | Validation KL | Mean relative error | p95 relative error | Vector work / dense | Selected keys |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
"""
    for row in rows:
        label = f"Trained / {row['maximum_steps']}" if row["maximum_steps"] else row["variant"]
        loss = f"{row['mean_selected_validation_kl']:.5f}" if row["maximum_steps"] else "—"
        text += f"| {label} | {', '.join(map(str, row['selected_steps'])) or '—'} | {loss} | {100 * row['validation_mean_relative_error']:.2f}% | {100 * row['validation_p95_relative_error']:.2f}% | {row['validation_mean_vector_work_ratio']:.3f} | {100 * row['validation_mean_selected_key_fraction']:.2f}% |\n"
    text += """
Lower KL is a surrogate improvement. Interpret executed output error and actual work together; identical p does not match cost, and these three budgets do not establish convergence. Data coverage, alternative losses and whole-model effects were not changed or tested.

## Integrity and artifacts

"""
    text += f"""The [audit](audit.json) checks source/trace-record/checkpoint identities, validation checkpoint selection and all {checked} aggregate rows from {audit["raw_records_verified"]:,} raw validation records. The run asserts exact reproduction of the original 100-step references. The training documents are disjoint from validation; [protocol and boundaries](../../docs/TRAINING_DURATION.md) were committed before execution.

[Full report and histories](report.json), [raw validation queries](validation-queries.jsonl.gz), [aggregate outcomes](aggregate.json), [protocol snapshot](protocol.json), [run log](run.log). Small reference checkpoints are retained beside the report. No new backbone model or raw corpus text is bundled.

The next training study must separate duration from unique-data coverage and reserve a new sealed test cohort before a generalization claim. This validation diagnosis does not authorize choosing a favorable test result or treating a layer-error budget as answer correctness.
"""
    (RUN / "SUMMARY.md").write_text(text)
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
