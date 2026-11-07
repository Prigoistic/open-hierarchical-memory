"""Fixed symbolic-spatial diagnostic, preserving every fork and measurement."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch

from research.somna_spatial import (
    DECISION_TOLERANCE,
    EpisodeIndex,
    digest,
    evaluate,
    load_checkpoint,
    make_world,
    offline_fork,
    save_checkpoint,
    wake_checkpoint,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL: dict[str, Any] = {
    "version": 1,
    "development_world": 7,
    "evaluation_worlds": [193, 271, 367],
    "width": 11,
    "updates": 256,
    "gamma": 0.95,
    "routing_p": 0.8,
    "chunk_size": 8,
    "depth": 2,
    "references": "one untrained basis reference per symbolic state",
    "decision_tolerance": DECISION_TOLERANCE,
    "claim": "known-map navigation from previously untested starts; no unseen-layout transfer",
    "budget": "uniform/priority receive same read and update counts; scheduler and routing work differ",
}


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def retrieval_audit(world: Any, bank: EpisodeIndex) -> dict[str, Any]:
    """Dense teacher is separate offline audit work, not free telemetry."""
    records = []
    for episode in world.transitions:
        dense = bank.read(episode.state, episode.action, "dense")
        sparse = bank.read(episode.state, episode.action, "zha")
        records.append(
            {
                "evidence_id": episode.identifier,
                "exact_episode_selected": episode.identifier in sparse["selected_ids"],
                "predicted_successor_correct": max(
                    range(bank.states), key=lambda i: sparse["probabilities"][i]
                )
                == episode.successor,
                "max_probability_error_vs_dense": max(
                    abs(a - b)
                    for a, b in zip(dense["probabilities"], sparse["probabilities"], strict=True)
                ),
                "selected": sparse["attention_pairs"],
                "scored_nodes": sparse["scored_nodes"],
                "summary_dot_products": sparse["summary_dot_products"],
                "dense_pairs": dense["attention_pairs"],
                "dense_seconds": dense["seconds"],
                "zha_seconds": sparse["seconds"],
            }
        )
    return {
        "records": records,
        "queries": len(records),
        "exact_episode_selected": sum(r["exact_episode_selected"] for r in records),
        "successor_correct": sum(r["predicted_successor_correct"] for r in records),
        "max_probability_error": max(r["max_probability_error_vs_dense"] for r in records),
        "work": {
            name: sum(r[name] for r in records)
            for name in ("selected", "scored_nodes", "summary_dot_products", "dense_pairs")
        },
        "seconds": {
            name: sum(r[name] for r in records) for name in ("dense_seconds", "zha_seconds")
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing to overwrite an existing run")
    args.output.mkdir(parents=True)
    torch.set_num_threads(1)
    write_json(args.output / "protocol.json", PROTOCOL)
    files = [
        "research/somna_spatial.py",
        "research/run_somna_spatial.py",
        "research/somna_inspector.html",
        "tests/test_somna_spatial.py",
    ]
    files += [
        str(p.relative_to(ROOT)) for p in (ROOT / "src/open_hierarchical_memory").glob("*.py")
    ]
    manifest = {
        "protocol_hash": digest(PROTOCOL),
        "source_hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files
        },
        "python": platform.python_version(),
        "torch": torch.__version__,
        "threads": 1,
        "dtype": "CPU float64",
        "publication": "private local research diagnostic",
        "seed7_status": "development world used before fixed evaluation worlds",
    }
    write_json(args.output / "manifest.json", manifest)
    for name in files:
        frozen = args.output / "source-snapshot" / name
        frozen.parent.mkdir(parents=True, exist_ok=True)
        frozen.write_bytes((ROOT / name).read_bytes())
    worlds: list[dict[str, Any]] = []
    for seed in [PROTOCOL["development_world"], *PROTOCOL["evaluation_worlds"]]:
        world = make_world(seed, PROTOCOL["width"])
        bank = EpisodeIndex(world.transitions, len(world.cells), world.goal)
        initial = wake_checkpoint(world.transitions, bank.states, bank.goal)
        entry: dict[str, Any] = {
            "world": asdict(world),
            "archive_hash": bank.archive_hash,
            "initial_q": initial.tolist(),
            "initial_evaluation": evaluate(world, initial.tolist()),
            "snapshot_bytes": bank.index.info.owned_tensor_bytes,
            "build_seconds": bank.build_seconds,
            "retrieval_audit": retrieval_audit(world, bank),
            "forks": [],
        }
        for backend in ("dense", "zha"):
            for policy in ("none", "uniform", "priority"):
                fork = offline_fork(
                    bank, initial, policy, backend, updates=PROTOCOL["updates"], seed=seed + 40
                )
                fork["evaluation"] = evaluate(world, fork["q"])
                checkpoint = args.output / f"checkpoint-{seed}-{backend}-{policy}.json"
                save_checkpoint(checkpoint, fork)
                reloaded = load_checkpoint(checkpoint, bank.archive_hash)
                assert evaluate(world, reloaded) == fork["evaluation"]
                fork["checkpoint_reload_equal"] = reloaded == fork["q"]
                entry["forks"].append(fork)
                print(
                    seed,
                    backend,
                    policy,
                    fork["evaluation"]["successes"],
                    "/",
                    fork["evaluation"]["trials"],
                    flush=True,
                )
        write_json(args.output / f"world-{seed}.json", entry)
        worlds.append(entry)
    check = worlds[-1]["forks"][-1]
    checkpoint = (
        args.output.resolve() / f"checkpoint-{worlds[-1]['world']['seed']}-zha-priority.json"
    )
    code = "import sys; from pathlib import Path; from research.somna_spatial import load_checkpoint,digest; print(digest(load_checkpoint(Path(sys.argv[1]),sys.argv[2])))"
    process = subprocess.run(
        [sys.executable, "-c", code, str(checkpoint), check["archive_hash"]],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert process.stdout.strip() == check["checkpoint_hash"]
    rows = []
    for backend in ("dense", "zha"):
        for policy in ("none", "uniform", "priority"):
            selected = [
                f
                for w in worlds[1:]
                for f in w["forks"]
                if f["backend"] == backend and f["policy"] == policy
            ]
            rows.append(
                {
                    "backend": backend,
                    "policy": policy,
                    "successes": sum(f["evaluation"]["successes"] for f in selected),
                    "trials": sum(f["evaluation"]["trials"] for f in selected),
                    "work": {
                        name: sum(f["work"][name] for f in selected)
                        for name in (
                            "scheduler_comparisons",
                            "scored_nodes",
                            "summary_dot_products",
                            "attention_pairs",
                        )
                    },
                    "offline_seconds": sum(f["offline_seconds"] for f in selected),
                }
            )
    report = {
        "evaluation_worlds": PROTOCOL["evaluation_worlds"],
        "development_world_excluded": True,
        "rows": rows,
        "checkpoint_roundtrips": 24,
        "fresh_process_checkpoint_verified": True,
        "environment_calls_during_offline": 0,
        "graph_planner_ceiling": "all starts reachable; independently checked in audit",
        "limitation": "same known maps, idealized symbolic encoding, expensive basis references and exhaustive residual scans; not latent dreaming, forgetting, neural consolidation or ZHA speedup",
    }
    write_json(args.output / "report.json", report)
    viewer_worlds = [
        {
            **{k: v for k, v in entry.items() if k != "retrieval_audit"},
            "forks": [{k: v for k, v in f.items() if k != "records"} for f in entry["forks"]],
        }
        for entry in worlds
    ]
    payload = json.dumps(
        {"protocol": PROTOCOL, "report": report, "worlds": viewer_worlds},
        separators=(",", ":"),
        allow_nan=False,
    ).replace("</", "<\\/")
    template = (ROOT / "research/somna_inspector.html").read_text()
    (args.output / "inspector.html").write_text(template.replace("__SOMNA_DATA__", payload))
    lines = [
        "# Somna: observed spatial replay diagnostic",
        "",
        "Three fixed evaluation mazes; seed7 is development data. The map is already observed. These results measure navigation from previously untested starting states, not new-map generalization.",
        "",
        "| Reader | Replay | Solved | Scheduler comparisons | Summary dot products | Attention pairs |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['backend']} | {row['policy']} | {row['successes']}/{row['trials']} | {row['work']['scheduler_comparisons']} | {row['work']['summary_dot_products']} | {row['work']['attention_pairs']} |"
        )
    lines.extend(
        [
            "",
            "Uniform and priority replay have identical update/read counts, not equal total compute. Priority uses an exhaustive observed-graph residual scan each update and already accesses every exact transition. This is not a retrieval bottleneck. Direct keyed lookup and shortest-path planning are stronger simple controls.",
            "",
            "ZHA uses one untrained reference per symbolic state and is expensive despite selecting few raw keys. No speed benefit is claimed. The actual numerical output mixture, with no exact-record fallback, supplies each Bellman update.",
            "",
            "The no-update fork preserves wake values. Offline forks update only a durable Q table from observed transitions. Temporary replay state is discarded on checkpoint reload; one reload also passes in a fresh interpreter. No simulator is called during offline replay. This is established Dyna-style value propagation, not a new dreaming algorithm.",
            "",
            "Files: protocol.json, manifest.json, report.json, world-*.json, checkpoint-*.json and inspector.html. Dense retrieval audits are separate diagnostic work. Developmental fixture, not an external benchmark.",
        ]
    )
    (args.output / "SUMMARY.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
