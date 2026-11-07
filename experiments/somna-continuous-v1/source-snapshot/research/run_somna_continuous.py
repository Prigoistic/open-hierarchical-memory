"""Fixed partial-cue retrieval and learned offline-consolidation comparison."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import platform
import random
import time
from pathlib import Path
from typing import Any

import torch

from research.somna_engine import MemoryEngine, record_features, sha
from research.somna_world import features, model_inputs, model_targets, observations

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: Any) -> None:
    raw = json.dumps(value, indent=2, allow_nan=False).encode()
    path.write_bytes(gzip.compress(raw, mtime=0) if path.suffix == ".gz" else raw + b"\n")


def evaluate(engine: MemoryEngine, seeds: list[int]) -> list[dict[str, Any]]:
    results = []
    for context in (0, 1):
        rows = [row for seed in seeds for row in observations(seed, 64, context=context)]
        with torch.no_grad():
            predicted = torch.stack([m(model_inputs(rows)) for m in engine.models]).mean(0)
        targets = model_targets(rows)
        records = [
            {
                "position": r["position"],
                "action": r["action"],
                "context": context,
                "prediction": predicted[i].tolist(),
                "target": targets[i].tolist(),
            }
            for i, r in enumerate(rows)
        ]
        results.append(
            {
                "context": context,
                "mse": float((predicted - targets).square().mean()),
                "rows": records,
            }
        )
    return results


def retrieval_study(
    base: MemoryEngine, output: Path, archives: Path, seed: int
) -> list[dict[str, Any]]:
    rng = random.Random(18000)
    heldout = observations(902, 32, context=0) + observations(903, 32, context=1)
    queries = [
        {
            "position": [max(-1.0, min(1.0, v + rng.gauss(0, 0.05))) for v in row["position"]],
            "action": None if j % 6 == 0 else row["action"],
            "context": None if j % 5 == 0 else row["context"],
            "mask": [j % 3 != 0, True],
            "audit": True,
        }
        for j, row in enumerate(heldout)
    ]
    results = []
    for kind in ("random", "fitted"):
        engine = base.fork(archives / f"retrieval-{seed}-{kind}.sqlite")
        if kind == "random":
            engine.references = engine.random_references.clone()
            engine.dirty = True
        reads = []
        knn_errors = []
        full_ids = sorted(engine.heads.values())
        keys = torch.stack(
            [
                torch.zeros(12, dtype=torch.float64),
                *[record_features(engine.records[i]) for i in full_ids],
            ]
        )
        values = torch.cat(
            [
                torch.zeros((1, 2), dtype=torch.float64),
                model_targets([engine.records[i] for i in full_ids]),
            ]
        )
        for value in queries:
            engine.tick += 1
            read = engine._read(value, audit=True, use=False)
            # Strong conventional exact top16 search on the identical full bank.
            scores = keys @ features(value) / math.sqrt(12)
            selected = sorted(
                {0, *torch.argsort(scores, descending=True, stable=True)[:16].tolist()}
            )
            nearest = torch.softmax(scores[selected], dim=0) @ values[selected]
            full = read["dense_audit"]["full_current_prediction"]
            knn_errors.append(
                float(torch.linalg.vector_norm(nearest - torch.tensor(full, dtype=torch.float64)))
            )
            read["exact_knn_audit"] = {
                "prediction": nearest.tolist(),
                "raw_keys_scored": len(full_ids) + 1,
                "selected": len(selected),
                "l2_error_vs_full_dense": knn_errors[-1],
            }
            reads.append(read)
        write_json(
            output / f"retrieval-{seed}-{kind}.json.gz",
            {
                "seed": seed,
                "references": kind,
                "observations": list(engine.records.values()),
                "reads": reads,
                "work": engine.work,
            },
        )
        results.append(
            {
                "seed": seed,
                "references": kind,
                "queries": len(reads),
                "mean_error_vs_hot_dense": sum(r["dense_audit"]["l2_error"] for r in reads)
                / len(reads),
                "mean_error_vs_full_dense": sum(
                    r["dense_audit"]["full_current_error"] for r in reads
                )
                / len(reads),
                "mean_observed_mass_full_archive": sum(
                    r["dense_audit"]["observed_selected_mass_full_archive"] for r in reads
                )
                / len(reads),
                "mean_selected_originals": sum(len(r["selected_ids"]) for r in reads) / len(reads),
                "exact_knn_mean_error_vs_full_dense": sum(knn_errors) / len(knn_errors),
                "work": engine.work.copy(),
            }
        )
        engine.close()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archives", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.archives.exists():
        raise SystemExit("refusing existing result/archive destinations")
    args.output.mkdir(parents=True)
    args.archives.mkdir(parents=True)
    torch.set_num_threads(1)
    protocol = json.loads((ROOT / "research/somna_live_protocol.json").read_text())
    write_json(args.output / "protocol.json", protocol)
    files = [
        "research/somna_engine.py",
        "research/somna_world.py",
        "research/serve_somna.py",
        "research/run_somna_continuous.py",
        "research/somna_live_protocol.json",
        "scripts/audit_somna_continuous.py",
        "tests/test_somna_engine.py",
        "tests/test_somna_http.py",
    ]
    files.extend(
        str(p.relative_to(ROOT)) for p in (ROOT / "src/open_hierarchical_memory").glob("*.py")
    )
    source_hashes = {}
    for name in files:
        raw = (ROOT / name).read_bytes()
        source_hashes[name] = hashlib.sha256(raw).hexdigest()
        target = args.output / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    write_json(
        args.output / "manifest.json",
        {
            "protocol_hash": sha(protocol),
            "source_hashes": source_hashes,
            "python": platform.python_version(),
            "torch": torch.__version__,
            "dtype": "CPU float64",
            "threads": 1,
            "scope": "controlled continuous dynamics; not a learned image encoder or external benchmark",
        },
    )
    summaries = []
    retrieval = []
    conditions = [
        ("none", "zha"),
        ("uniform", "zha"),
        ("priority", "zha"),
        ("coverage", "zha"),
        ("uniform", "dense"),
        ("coverage", "dense"),
        ("discarded_coverage", "zha"),
    ]
    for seed in protocol["training_seeds"]:
        base = MemoryEngine(
            args.archives / f"base-{seed}.sqlite",
            seed=seed,
            capacity=protocol["active_capacity"],
            bootstrap=protocol["observations_per_seed"],
        )
        base.fit_router(8)
        initial_weights = base._weights()
        archive_hash = base.state()["archive"]["checksum"]
        retrieval.extend(retrieval_study(base, args.output, args.archives, seed))
        for strategy, backend in conditions:
            engine = base.fork(args.archives / f"run-{seed}-{strategy}-{backend}.sqlite")
            before = engine.work.copy()
            started = time.perf_counter()
            if strategy != "none":
                engine.start_sleep(
                    "coverage" if strategy == "discarded_coverage" else strategy,
                    protocol["sleep_gradient_steps"],
                    [-0.3, -0.3],
                    0,
                )
                for _ in range(protocol["sleep_gradient_steps"]):
                    engine.sleep_step(backend=backend)
                engine.finish_sleep()
            trained_weights = engine._weights()
            discarded = None
            if strategy == "discarded_coverage":
                discarded = trained_weights
                engine.models.load_state_dict(
                    {
                        name: torch.tensor(value, dtype=torch.float64)
                        for name, value in initial_weights.items()
                    },
                    strict=True,
                )
                engine.trained_steps = 0
                engine.last_loss = None
                engine.sleep["rollout"] = []
                engine.sleep["status"] = "discarded_model_updates"
                engine._commit()
            evaluations = evaluate(engine, protocol["heldout_state_seeds"])
            trace = engine.sleep["trace"]
            run = {
                "seed": seed,
                "strategy": strategy,
                "backend": backend,
                "observations": list(engine.records.values()),
                "archive_hash": archive_hash,
                "archive_hash_after": engine.state()["archive"]["checksum"],
                "initial_weights": initial_weights,
                "initial_model_hash": sha(initial_weights),
                "final_weights": engine._weights(),
                "final_model_hash": engine.model_hash(),
                "trace": trace,
                "gradient_steps": engine.work["gradient_steps"] - before["gradient_steps"],
                "simulator_calls_before": before["simulator_calls"],
                "simulator_calls_after": engine.work["simulator_calls"],
                "rollout": engine.sleep["rollout"],
                "rollout_status": engine.sleep.get("rollout_status"),
                "evaluations": evaluations,
                "work": {key: engine.work[key] - before[key] for key in engine.work},
                "seconds": time.perf_counter() - started,
                "reference_hash": sha(engine.references.tolist()),
            }
            if discarded is not None:
                run["discarded_weights"] = discarded
            assert run["archive_hash_after"] == archive_hash
            final_hash = engine.model_hash()
            engine.close()
            reloaded = MemoryEngine(engine.path, bootstrap=0)
            assert reloaded.model_hash() == final_hash
            assert [e["mse"] for e in evaluate(reloaded, protocol["heldout_state_seeds"])] == [
                e["mse"] for e in evaluations
            ]
            run["restart_equal"] = True
            reloaded.close()
            write_json(args.output / f"run-{seed}-{strategy}-{backend}.json.gz", run)
            row = {
                key: run[key]
                for key in (
                    "seed",
                    "strategy",
                    "backend",
                    "gradient_steps",
                    "work",
                    "seconds",
                    "restart_equal",
                )
            }
            row["common_mse"] = evaluations[0]["mse"]
            row["rare_mse"] = evaluations[1]["mse"]
            summaries.append(row)
            print(seed, strategy, backend, row["common_mse"], row["rare_mse"], flush=True)
        base.close()
    report = {
        "runs": summaries,
        "retrieval": retrieval,
        "scope": "new continuous test positions under same two synthetic vector fields",
        "compute_matching": "same gradient/read limits; actual routing, scheduler, example and recovery costs differ and are reported",
        "claims": "prototype integration; no ZHA speed or trained-reference superiority presumed; no biological dreaming or novelty established",
    }
    write_json(args.output / "report.json", report)
    lines = [
        "# Somna continuous episodic memory and learned replay",
        "",
        "Fixed noisy/partial cues have no unique state or episode identifier. Multiple observations share each cue. Three independent MLPs learn action-conditioned continuous displacement from actual retrieved observed transitions. No simulator is called during offline learning or imagined rollouts.",
        "",
        "| Seed | Policy | Reader | Common MSE | Rare MSE | Gradient steps | Training examples |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for row in summaries:
        lines.append(
            f"| {row['seed']} | {row['strategy']} | {row['backend']} | {row['common_mse']:.6f} | {row['rare_mse']:.6f} | {row['gradient_steps']} | {row['work']['training_examples']} |"
        )
    lines.extend(
        [
            "",
            "Each context MSE covers192 previously unseen continuous states per training seed. Seed901 was used in development and excluded;902/903/904 are fixed comparison states. These share the same synthetic dynamics as training, so this is not transfer to new physics or image learning.",
            "",
            "Uniform, priority and coverage receive the same160 read/update limit, not equal total compute. Priority scans hot prediction errors; coverage scans metadata. Exact dense and exact top16 search over the full current bank are strong retrieval diagnostics on identical features. Full archive and hot dense audits are charged separately. Random-reference and fitted-reference outcomes, including unfavorable comparisons, are retained.",
            "",
            "The discarded-update control pays for coverage replay but reloads initial neural parameters before evaluation. All ordinary checkpoints survive reopening with identical model evaluation. Immutable originals, version heads and all controller metadata persist. Learned rollouts are explicitly imagined and never written as canonical observations; uncertainty/support checks are heuristics, not correctness guarantees.",
            "",
            "See report.json for every measured count and raw .json.gz files for actual selected reads, training sources/losses, model weights, rollouts and held-out predictions. The separate auditor reconstructs scalar softmax reads and independently replays functional MLP/SGD updates. Source snapshots bind the executed code.",
        ]
    )
    (args.output / "SUMMARY.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
