"""Post-run audit: identities, raw records, validation choices and scalar oracle.

No training, model selection or modification of the original measurements.
Run as python -m scripts.audit_cost_quality with the recorded local traces.
"""

import gzip
import hashlib
import json
import math
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path

from safetensors.torch import load_file

from tests import oracle

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments/gpt2-cost-quality-v1"
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


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def close(actual, expected):
    if not math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-10):
        raise AssertionError(f"measurement differs: {actual} versus {expected}")


def audit_aggregate(rows, aggregate):
    for metric in METRICS:
        values = sorted(row[metric] for row in rows if row[metric] is not None)
        summary = aggregate[metric]
        if len(values) != summary["count"]:
            raise AssertionError("aggregate count mismatch")
        if not values:
            if any(summary[name] is not None for name in ("mean", "median", "p95")):
                raise AssertionError("nonempty summary of empty metric")
            continue
        for observed, expected in [
            (statistics.fmean(values), summary["mean"]),
            (statistics.median(values), summary["median"]),
            (values[math.ceil(0.95 * len(values)) - 1], summary["p95"]),
        ]:
            close(observed, expected)


def main():
    report = json.loads((RUN / "report.json").read_text())
    config, revision = report["config"], report["git_revision"]
    geometries = {g["id"]: g for g in config["geometries"]}
    for path, digest in report["source_sha256"].items():
        committed = subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)
        if hashlib.sha256(committed).hexdigest() != digest:
            raise AssertionError("source identity mismatch")
    for name, value in [
        ("cost_quality_protocol.json", config),
        ("cost_quality_manifest.json", report["manifest"]),
    ]:
        if (
            json.loads(
                subprocess.check_output(["git", "show", f"{revision}:research/{name}"], cwd=ROOT)
            )
            != value
        ):
            raise AssertionError("protocol/manifest differs from source commit")
    if sha(RUN / "protocol.json") != report["config_sha256"]:
        raise AssertionError("protocol snapshot mismatch")
    if report["frozen_backbone_sha256_before"] != report["frozen_backbone_sha256_after"]:
        raise AssertionError("backbone changed")
    if any(report["model_loading_info"].values()):
        raise AssertionError("incomplete pretrained restoration")
    if sha(RUN / "selection-before-test.json") != report["selection_sha256"]:
        raise AssertionError("frozen selection record changed")
    selection_record = json.loads((RUN / "selection-before-test.json").read_text())
    if (
        selection_record["test_capture_started"]
        or selection_record["selections"] != report["selections"]
    ):
        raise AssertionError("selection chronology mismatch")
    for fit in report["fitting"]:
        digest = sha(RUN / fit["checkpoint"])
        if (
            digest != fit["checkpoint_sha256"]
            or digest != selection_record["checkpoint_hashes"][fit["checkpoint"]]
        ):
            raise AssertionError("checkpoint changed after selection")
        minimum = min(row["validation_kl"] for row in fit["history"])
        chosen = next(row for row in fit["history"] if row["step"] == fit["selected_step"])
        if chosen["validation_kl"] > minimum + 1e-12:
            raise AssertionError("checkpoint not selected by validation minimum")
        refs = load_file(str(RUN / fit["checkpoint"]))
        expected_shape = (12, geometries[fit["geometry"]]["reference_count"], 64)
        if any(tuple(t.shape) != expected_shape for t in refs.values()):
            raise AssertionError("reference geometry mismatch")
    for capture in report["captures"]:
        path = (
            ROOT
            / f".cache/cost-quality-v1/trace-{capture['context']}-{capture['book']}-{capture['offset']}.safetensors"
        )
        if sha(path) != capture["trace_sha256"]:
            raise AssertionError("local trace changed")
    groups = {}
    counts = {}
    for split in ("validation", "test"):
        name = f"{split}-queries.jsonl.gz"
        if sha(RUN / name) != report["raw_measurement_sha256"][name]:
            raise AssertionError("raw measurements changed")
        split_groups = defaultdict(list)
        identities = set()
        with gzip.open(RUN / name, "rt") as stream:
            for line in stream:
                row = json.loads(line)
                variant = row.get("variant", "trained")
                group = (row["context"], row["geometry"], row["seed"], variant, row["p"])
                identity = (
                    *group,
                    row["document_id"],
                    row["window_offset"],
                    row["query_position"],
                    row["query_head"],
                )
                if identity in identities or row["split"] != split:
                    raise AssertionError("duplicate identity or split leakage")
                identities.add(identity)
                if row["document_id"] not in {
                    f"gutenberg:{book}" for book in config["splits"][split]
                }:
                    raise AssertionError("unrecognized split document")
                visible, selected, nodes = (
                    row["visible_keys"],
                    row["selected_keys"],
                    row["scored_summary_nodes"],
                )
                if visible != row["query_position"] + 1 or not 1 <= selected <= visible:
                    raise AssertionError("invalid visibility/selection")
                refs = geometries[row["geometry"]]["reference_count"]
                close(row["selected_key_fraction"], selected / visible)
                close(row["qk_score_ratio"], (refs * nodes + selected) / visible)
                close(
                    row["qk_plus_av_vector_work_ratio"],
                    (refs * nodes + 2 * selected) / (2 * visible),
                )
                close(
                    row["relative_l2_error"],
                    row["attention_l2_error"]
                    / max(
                        row["dense_output_norm"],
                        config["selection"]["relative_l2_denominator_floor"],
                    ),
                )
                if (
                    not row["retained_mass"] - 1e-10
                    <= row["oracle_topk_retained_mass"]
                    <= 1 + 1e-10
                ):
                    raise AssertionError("invalid mass oracle")
                split_groups[group].append(row)
        groups[split] = split_groups
        counts[split] = len(identities)
    for row in report["test_grid"]:
        key = (row["context"], row["geometry"], row["seed"], row["variant"], row["p"])
        records = groups["test"][key]
        if len(records) != 384:
            raise AssertionError("incomplete query/head grid")
        audit_aggregate(records, row["metrics"])
        for document, metrics in row["per_document"].items():
            audit_aggregate([r for r in records if r["document_id"] == document], metrics)
    for row in report["validation_grid"]:
        records = [
            r
            for seed in config["seeds"]
            for r in groups["validation"][
                row["context"], row["geometry"], seed, "trained", row["p"]
            ]
        ]
        if len(records) != 576:
            raise AssertionError("incomplete pooled validation grid")
        audit_aggregate(records, row["metrics"])
    # Independent application of the frozen choice rule, without importing it.
    for context, selected in zip(config["contexts"], report["selections"], strict=True):
        eligible = [
            r
            for r in report["validation_grid"]
            if r["context"] == context
            and r["metrics"]["relative_l2_error"]["mean"]
            <= config["selection"]["max_mean_relative_l2"]
            and r["metrics"]["relative_l2_error"]["p95"]
            <= config["selection"]["max_p95_relative_l2"]
        ]
        best = (
            min(
                eligible,
                key=lambda r: (
                    r["metrics"]["qk_plus_av_vector_work_ratio"]["mean"],
                    r["geometry"],
                    r["p"],
                ),
            )
            if eligible
            else None
        )
        if (best is None) != (selected is None) or (
            best and (best["geometry"], best["p"]) != (selected["geometry"], selected["p"])
        ):
            raise AssertionError("selection does not follow fixed rule")
    for row in report["benchmarks"]:
        timing = row["timing"]
        for name in ("sdpa_dense", "hierarchical"):
            values = timing[name]["raw_ms_per_window_batch"]
            close(timing[name]["median"], statistics.median(values))
            if len(values) != config["timing"]["timed_rounds"]:
                raise AssertionError("timing count mismatch")
        for reuse in config["timing"]["static_snapshot_reuse_counts"]:
            value = (
                row["tree_build_ms_per_window_batch"]["median"] / reuse
                + timing["hierarchical"]["median"]
            )
            close(
                timing[f"static_reuse_{reuse}"]["estimated_ms_per_batch_including_amortized_build"],
                value,
            )
            close(
                timing[f"static_reuse_{reuse}"]["sdpa_over_hierarchical_speed_ratio"],
                timing["sdpa_dense"]["median"] / value,
            )
    literal = []
    # Every geometry/context, plus a second book/head for selected configurations.
    cases = {
        (context, g["id"], config["splits"]["test"][0], 0, 0.73)
        for context in config["contexts"]
        for g in config["geometries"]
    }
    cases.update(
        (r["context"], r["geometry"], config["splits"]["test"][-1], 11, r["p"])
        for r in report["selections"]
        if r is not None
    )
    for context, geometry, book, head, p in sorted(cases):
        item = geometries[geometry]
        trace = load_file(
            str(ROOT / f".cache/cost-quality-v1/trace-{context}-{book}-4096.safetensors")
        )
        checkpoint = RUN / f"references/t{context}-{geometry}-s7.safetensors"
        refs = load_file(str(checkpoint))["trained"][head].tolist()
        query = trace["queries"][head, context - 1].tolist()
        keys = trace["keys"][head].tolist()
        values = trace["values"][head].tolist()
        ids, _ = oracle.route(query, keys, refs, item["chunk_size"], item["depth"], context, p)
        dense = oracle.attention(query, keys, values, tuple(range(context)))
        sparse = oracle.attention(query, keys, values, ids)
        logits = [oracle.dot(query, key) / math.sqrt(64) for key in keys]
        denominator = oracle.lse(logits)
        mass = math.fsum(math.exp(logits[i] - denominator) for i in ids)
        error = math.sqrt(math.fsum((a - b) ** 2 for a, b in zip(dense, sparse, strict=True)))
        record = next(
            r
            for r in groups["test"][context, geometry, 7, "trained", p]
            if r["document_id"] == f"gutenberg:{book}"
            and r["window_offset"] == 4096
            and r["query_position"] == context - 1
            and r["query_head"] == head
        )
        if len(ids) != record["selected_keys"]:
            raise AssertionError("literal selected-key count differs")
        close(mass, record["retained_mass"])
        close(error, record["attention_l2_error"])
        literal.append(
            {
                "context": context,
                "geometry": geometry,
                "book": book,
                "head": head,
                "p": p,
                "selected_keys": len(ids),
                "retained_mass": mass,
                "output_l2_error": error,
            }
        )
    expected_fits = len(config["contexts"]) * len(config["geometries"]) * len(config["seeds"])
    if (
        len(report["fitting"]) != expected_fits
        or len(report["test_grid"]) != expected_fits * 9
        or len(report["benchmarks"]) != expected_fits * 3
        or counts != {"validation": 36288, "test": 217728}
    ):
        raise AssertionError("incomplete overall study grid")
    result = {
        "source_commit_verified": revision,
        "raw_counts": counts,
        "checkpoint_hashes_verified": len(report["fitting"]),
        "test_configuration_aggregates_verified": len(report["test_grid"]),
        "validation_aggregates_verified": len(report["validation_grid"]),
        "timing_configurations_verified": len(report["benchmarks"]),
        "frozen_validation_choices_verified": True,
        "literal_real_query_checks": literal,
        "scope": "Post-run source/hash/aggregate/selection audit and scoped independent scalar routing; not a proof of all executions or model quality.",
    }
    (RUN / "audit.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(
        json.dumps({k: v for k, v in result.items() if k != "literal_real_query_checks"}, indent=2)
    )


if __name__ == "__main__":
    main()
