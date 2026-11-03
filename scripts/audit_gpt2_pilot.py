"""Post-run audit of source identities, raw measurements and literal routing.

This does not retrain, select checkpoints or change the original experiment.
Run as: python -m scripts.audit_gpt2_pilot
"""

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
RUN = ROOT / "experiments/gpt2-layer5-pilot-v1"


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def committed(revision: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)


def main() -> None:
    report = json.loads((RUN / "report.json").read_text())
    config = report["config"]
    revision = report["git_revision"]
    for path, expected in report["source_sha256"].items():
        if hashlib.sha256(committed(revision, path)).hexdigest() != expected:
            raise AssertionError(f"source identity mismatch: {path}")
    if (
        hashlib.sha256(committed(revision, "research/gpt2_pilot.json")).hexdigest()
        != report["config_sha256"]
    ):
        raise AssertionError("protocol is not bound to the preregistration commit")
    if json.loads(committed(revision, "research/gpt2_data_manifest.json")) != report["manifest"]:
        raise AssertionError("data manifest differs from preregistration")
    if (
        report["source_tree_dirty_at_start"]
        or report["frozen_backbone_sha256_before"] != report["frozen_backbone_sha256_after"]
    ):
        raise AssertionError("source/backbone invariant failed")
    if any(
        report["model_loading_info"][name]
        for name in ("missing_keys", "mismatched_keys", "error_msgs")
    ):
        raise AssertionError("pretrained model not completely restored")
    if sha(RUN / "query-metrics.jsonl") != report["query_metrics_sha256"]:
        raise AssertionError("raw metric file identity mismatch")
    for fit in report["fitting"]:
        if sha(RUN / f"references-seed-{fit['seed']}.safetensors") != fit["checkpoint_sha256"]:
            raise AssertionError("checkpoint identity mismatch")
        chosen = next(row for row in fit["history"] if row["step"] == fit["selected_step"])
        if chosen["validation_kl"] > min(row["validation_kl"] for row in fit["history"]) + 1e-12:
            raise AssertionError("selected checkpoint is not the validation minimum")
    groups = defaultdict(list)
    all_records = [
        json.loads(line) for line in (RUN / "query-metrics.jsonl").read_text().splitlines()
    ]
    for record in all_records:
        if record["document_id"] not in {f"gutenberg:{book}" for book in config["splits"]["test"]}:
            raise AssertionError("non-test query in test measurements")
        groups[record["seed"], record["variant"], record["p"]].append(record)
    if len(groups) != len(config["seeds"]) * 3 * len(config["routing_thresholds"]):
        raise AssertionError("missing experiment configurations")
    for result in report["test_results"]:
        records = groups[result["seed"], result["variant"], result["p"]]
        expected_count = (
            len(config["splits"]["test"])
            * len(config["window_offsets"])
            * len(config["query_positions"])
            * 12
        )
        if len(records) != expected_count:
            raise AssertionError("missing query/head measurements")
        for metric, summary in result["metrics"].items():
            values = sorted(row[metric] for row in records if row[metric] is not None)
            if len(values) != summary["count"]:
                raise AssertionError("summary count mismatch")
            for observed, expected in [
                (statistics.fmean(values), summary["mean"]),
                (statistics.median(values), summary["median"]),
                (values[math.ceil(0.95 * len(values)) - 1], summary["p95"]),
            ]:
                if not math.isclose(observed, expected, rel_tol=1e-12, abs_tol=1e-12):
                    raise AssertionError(f"aggregate differs from raw records: {metric}")
    # Independent scalar, direct-original-key routing on eight real queries.
    # Covers both held-out books, both extreme heads and two routing thresholds.
    literal_checks = []
    references = load_file(str(RUN / "references-seed-7.safetensors"))["references"]
    for book in config["splits"]["test"]:
        offset = config["window_offsets"][0]
        trace = load_file(str(ROOT / f".cache/gpt2-pilot/trace-{book}-{offset}.safetensors"))
        for head in (0, 11):
            query = trace["queries"][head, 255].tolist()
            keys = trace["keys"][head].tolist()
            values = trace["values"][head].tolist()
            logits = [oracle.dot(query, key) / math.sqrt(len(query)) for key in keys]
            denominator = oracle.lse(logits)
            dense = oracle.attention(query, keys, values, tuple(range(256)))
            for p in (0.73, 0.95):
                ids, _ = oracle.route(
                    query,
                    keys,
                    references[head].tolist(),
                    config["chunk_size"],
                    config["depth"],
                    256,
                    p,
                )
                predicted = oracle.attention(query, keys, values, ids)
                mass = math.fsum(math.exp(logits[i] - denominator) for i in ids)
                error = math.sqrt(
                    math.fsum((a - b) ** 2 for a, b in zip(predicted, dense, strict=True))
                )
                record = next(
                    row
                    for row in groups[7, "trained", p]
                    if row["document_id"] == f"gutenberg:{book}"
                    and row["window_offset"] == offset
                    and row["query_position"] == 255
                    and row["query_head"] == head
                )
                if (
                    len(ids) != record["selected_keys"]
                    or not math.isclose(mass, record["retained_mass"], abs_tol=1e-10)
                    or not math.isclose(error, record["attention_l2_error"], abs_tol=1e-9)
                ):
                    raise AssertionError("literal real-query oracle mismatch")
                literal_checks.append(
                    {
                        "book_id": book,
                        "head": head,
                        "p": p,
                        "selected_keys": len(ids),
                        "retained_mass": mass,
                        "attention_l2_error": error,
                    }
                )
    summary = {
        "source_commit_verified": revision,
        "protocol_verified": True,
        "corpus_manifest_verified": True,
        "backbone_parameters_unchanged": True,
        "raw_query_records_verified": len(all_records),
        "configuration_aggregates_verified": len(groups),
        "literal_real_query_checks": literal_checks,
        "scope": "Post-run identity/aggregation audit and eight independent real-query checks; not exhaustive proof or a new training run.",
    }
    (RUN / "audit.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
