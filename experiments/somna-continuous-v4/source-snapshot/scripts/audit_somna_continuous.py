"""Independent scalar audit of selected reads, observed sources and fork evidence.

Imports no engine, feature encoder, simulator, router or learned-model code.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import torch
from torch.nn import functional as functional


def digest(value: Any) -> str:
    normalized = json.loads(json.dumps(value, allow_nan=False))
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def encoding(row: dict[str, Any], version: str = "continuous-harmonic-cue-v1") -> list[float]:
    out = []
    for x, visible in zip(row["position"], row.get("mask", [True, True]), strict=True):
        out.extend(
            [
                3 * fn(f * math.pi * x) if visible else 0.0
                for f in ((0.5, 1.0) if version == "continuous-half-harmonic-cue-v2" else (1, 2))
                for fn in (math.cos, math.sin)
            ]
        )
    out.extend([0.0, 0.0] if row.get("action") is None else [4 * v for v in row["action"]])
    out.extend(
        [0.0, 0.0] if row.get("context") is None else [6.0 * (row["context"] == c) for c in (0, 1)]
    )
    return out


def mixture(
    identifiers: list[int],
    vector: list[float],
    records: dict[int, dict[str, Any]],
    version: str = "continuous-harmonic-cue-v1",
) -> tuple[list[float], dict[int, float]]:
    scores = [0.0] + [
        sum(a * b for a, b in zip(vector, encoding(records[i], version), strict=True))
        / math.sqrt(12)
        for i in identifiers
    ]
    weights = [math.exp(s - max(scores)) for s in scores]
    normal = sum(weights)
    probabilities = {i: w / normal for i, w in zip(identifiers, weights[1:], strict=True)}
    predicted = [
        sum(
            probabilities[i] * (records[i]["successor"][j] - records[i]["position"][j])
            for i in identifiers
        )
        for j in (0, 1)
    ]
    return predicted, probabilities


def audit_read(read: dict[str, Any], records: dict[int, dict[str, Any]]) -> None:
    assert set(read["cue"]) == {"position", "action", "context", "mask", "audit"}
    ids = read["selected_ids"]
    assert len(ids) == len(set(ids)) and set(ids) <= set(read["index_ids"])
    assert all(i in records and records[i]["evidence"] == "observed" for i in ids)
    version = read.get("feature_version", "continuous-harmonic-cue-v1")
    assert version in ("continuous-harmonic-cue-v1", "continuous-half-harmonic-cue-v2")
    vector = encoding(read["cue"], version)
    scores = [0.0]
    deltas = [[0.0, 0.0]]
    for identifier in ids:
        row = records[identifier]
        scores.append(
            sum(a * b for a, b in zip(vector, encoding(row, version), strict=True)) / math.sqrt(12)
        )
        deltas.append([b - a for a, b in zip(row["position"], row["successor"], strict=True)])
    weights = [math.exp(s - max(scores)) for s in scores]
    denominator = sum(weights)
    expected = [
        sum(w * d[j] for w, d in zip(weights, deltas, strict=True)) / denominator for j in (0, 1)
    ]
    assert all(
        math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10)
        for a, b in zip(read["prediction"], expected, strict=True)
    )
    ranked = {r["id"]: r["weight"] for r in read["ranked"]}
    assert set(ranked) == set(ids)
    for i, w in zip(ids, weights[1:], strict=True):
        assert math.isclose(ranked[i], w / denominator, rel_tol=1e-10, abs_tol=1e-10)
    assert read["work"]["raw_pairs"] == len(ids) + 1
    assert read["work"]["summary_dot_products"] == 8 * sum(
        len(s["candidates"]) for s in read["route"]
    )
    if read.get("cold_route") is not None:
        bank = read["cold_index_ids"]
        cold_expected = set(bank[(len(bank) // 4) * 4 :])
        for level in read["cold_route"]:
            if level["level"] == 1:
                for group in level["selected"]:
                    cold_expected.update(bank[group * 4 : (group + 1) * 4])
        assert set(read["cold_selected_ids"]) == cold_expected
        assert read["cold_work"]["raw_pairs"] == len(cold_expected) + 1 <= 128
        assert read["cold_work"]["summary_dot_products"] == 8 * sum(
            len(s["candidates"]) for s in read["cold_route"]
        )
    audit = read.get("dense_audit")
    if audit is not None:
        predicted, probabilities = mixture(sorted(records), vector, records, version)
        assert all(
            math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10)
            for a, b in zip(predicted, audit["full_current_prediction"], strict=True)
        )
        assert math.isclose(
            sum(probabilities[i] for i in ids),
            audit["observed_selected_mass_full_archive"],
            rel_tol=1e-10,
            abs_tol=1e-10,
        )
        if "exact_knn_audit" in read:
            scored = [(0, 0.0)] + [
                (
                    i,
                    sum(a * b for a, b in zip(vector, encoding(records[i], version), strict=True))
                    / math.sqrt(12),
                )
                for i in sorted(records)
            ]
            chosen = sorted(i for i, _ in sorted(scored, key=lambda x: (-x[1], x[0]))[:16] if i)
            nearest, _ = mixture(chosen, vector, records, version)
            assert all(
                math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10)
                for a, b in zip(nearest, read["exact_knn_audit"]["prediction"], strict=True)
            )


def forward(weights: dict[str, torch.Tensor], inputs: torch.Tensor, member: int) -> torch.Tensor:
    def layer(value: torch.Tensor, index: int) -> torch.Tensor:
        return functional.linear(
            value,
            weights[f"{member}.layers.{index}.weight"],
            weights[f"{member}.layers.{index}.bias"],
        )

    return layer(torch.tanh(layer(torch.tanh(layer(inputs, 0)), 2)), 4)


def gradient_audit(run: dict[str, Any], records: dict[int, dict[str, Any]]) -> None:
    weights = {
        name: torch.tensor(value, dtype=torch.float64, requires_grad=True)
        for name, value in run["initial_weights"].items()
    }
    for event in run["trace"]:
        rows = [records[i] for i in event["sources"]]
        inputs = torch.tensor(
            [
                [*r["position"], *r["action"], float(r["context"] == 0), float(r["context"] == 1)]
                for r in rows
            ],
            dtype=torch.float64,
        )
        target = torch.tensor(
            [[b - a for a, b in zip(r["position"], r["successor"], strict=True)] for r in rows],
            dtype=torch.float64,
        )
        losses = []
        for member in range(3):
            prediction = forward(weights, inputs, member)
            loss = (prediction - target).square().mean()
            losses.append(float(loss.detach()))
            names = [name for name in weights if name.startswith(f"{member}.")]
            gradients = torch.autograd.grad(loss, [weights[name] for name in names])
            norm = torch.linalg.vector_norm(
                torch.stack([torch.linalg.vector_norm(g) for g in gradients])
            )
            coefficient = min(1.0, 5.0 / (float(norm) + 1e-6))
            with torch.no_grad():
                for name, gradient in zip(names, gradients, strict=True):
                    weights[name].add_(gradient, alpha=-0.06 * coefficient)
        assert math.isclose(sum(losses) / 3, event["loss"], rel_tol=1e-9, abs_tol=1e-10)
    expected = run.get("discarded_weights", run["final_weights"])
    for name, value in expected.items():
        assert torch.allclose(
            weights[name].detach(), torch.tensor(value, dtype=torch.float64), atol=1e-10, rtol=1e-9
        ), name
    if run.get("discarded_weights"):
        assert run["final_weights"] == run["initial_weights"]
    final = {
        name: torch.tensor(value, dtype=torch.float64)
        for name, value in run["final_weights"].items()
    }
    for evaluation in run["evaluations"]:
        for row in evaluation["rows"]:
            inputs = torch.tensor(
                [
                    [
                        *row["position"],
                        *row["action"],
                        float(row["context"] == 0),
                        float(row["context"] == 1),
                    ]
                ],
                dtype=torch.float64,
            )
            predicted = torch.stack([forward(final, inputs, i)[0] for i in range(3)]).mean(0)
            assert torch.allclose(
                predicted,
                torch.tensor(row["prediction"], dtype=torch.float64),
                atol=1e-10,
                rtol=1e-9,
            )


def audit_run(run: dict[str, Any]) -> dict[str, int]:
    records = {r["id"]: r for r in run["observations"]}
    heads: dict[str, int] = {}
    last_tick = 0
    for identifier, row in records.items():
        payload = {
            k: row[k]
            for k in (
                "position",
                "action",
                "context",
                "successor",
                "evidence",
                "source",
                "tick",
                "version",
            )
        }
        assert digest([row["logical_key"], row["previous"], payload]) == row["checksum"]
        assert row["evidence"] == "observed"
        assert row["previous"] == heads.get(row["logical_key"])
        assert row["tick"] >= last_tick
        last_tick = row["tick"]
        heads[row["logical_key"]] = identifier
    current_records = {identifier: records[identifier] for identifier in heads.values()}
    assert digest([r["checksum"] for r in records.values()]) == run["archive_hash"]
    assert run["initial_model_hash"] == digest(run["initial_weights"])
    updates = 0
    for event in run["trace"]:
        audit_read(event["read"], current_records)
        assert event["evidence"] == "observed"
        assert set(event["sources"]) <= set(event["read"]["selected_ids"])
        assert event["sources"]
        assert math.isfinite(event["loss"]) and event["loss"] >= 0
        updates += 1
    assert updates == run["gradient_steps"]
    assert run["simulator_calls_after"] == run["simulator_calls_before"]
    assert run["archive_hash_after"] == run["archive_hash"]
    assert run["final_model_hash"] == digest(run["final_weights"])
    for point in run["rollout"][1:]:
        assert point["evidence"] == "imagined" and point["sources"]
        assert all(i in records and records[i]["evidence"] == "observed" for i in point["sources"])
    for evaluation in run["evaluations"]:
        squared = []
        for row in evaluation["rows"]:
            error = (
                sum((a - b) ** 2 for a, b in zip(row["prediction"], row["target"], strict=True)) / 2
            )
            squared.append(error)
        assert math.isclose(
            sum(squared) / len(squared), evaluation["mse"], rel_tol=1e-10, abs_tol=1e-10
        )
    gradient_audit(run, records)
    return {
        "updates": updates,
        "model_evaluation_rows": sum(len(e["rows"]) for e in run["evaluations"]),
        "observed_sources": len(records),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    manifest = json.loads((args.results / "manifest.json").read_text())
    for name, checksum in manifest["source_hashes"].items():
        assert (
            hashlib.sha256((args.results / "source-snapshot" / name).read_bytes()).hexdigest()
            == checksum
        ), name
    checks = {}
    for path in sorted(args.results.glob("run-*.json.gz")):
        checks[path.name] = audit_run(json.loads(gzip.decompress(path.read_bytes())))
    assert checks
    reads = 0
    for path in sorted(args.results.glob("retrieval-*.json.gz")):
        data = json.loads(gzip.decompress(path.read_bytes()))
        records = {r["id"]: r for r in data["observations"]}
        for read in data["reads"]:
            audit_read(read, records)
            reads += 1
    report = {
        "all_passed": True,
        "scope": "scalar selected attention, independent functional MLP/SGD replay, observed-source/fork/evaluation integrity",
        "runs": checks,
        "additional_retrieval_reads": reads,
    }
    (args.results / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
