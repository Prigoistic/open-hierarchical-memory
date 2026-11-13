"""Frozen wake/replay/fresh-task comparison with explicit observed provenance."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import statistics
import subprocess
import time
from pathlib import Path
from typing import cast

import torch

from research.persistent_task_memory import Backend
from research.run_minigrid_benchmark import require_versions
from research.run_persistent_tasks import persistent_episode, quality, save_json, save_trace
from research.task_references import RouterCheckpoint, digest
from research.task_replay import ReplayItem, Schedule, deduplicate, episode_items, replay_references
from research.task_store import WorkspaceConfig

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "research/task_replay_protocol.json").read_text())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("A new output directory is required; no evidence is overwritten.")
    require_versions()
    torch.set_num_threads(1)
    out = args.output
    out.mkdir(parents=True)
    (out / "archives").mkdir()
    sources = [
        *sorted((ROOT / "src/open_hierarchical_memory").glob("*.py")),
        *[
            ROOT / "research" / name
            for name in (
                "task_references.py",
                "task_store.py",
                "persistent_task_memory.py",
                "run_persistent_tasks.py",
                "dependency_memory.py",
                "minigrid_benchmark.py",
                "run_minigrid_benchmark.py",
                "run_progress_benchmark.py",
                "persistent_task_protocol.json",
                "task_replay.py",
                "run_task_replay.py",
                "task_replay_protocol.json",
            )
        ],
        ROOT / "scripts/audit_task_replay.py",
        ROOT / "scripts/audit_persistent_tasks.py",
        ROOT / "tests/oracle.py",
        ROOT / "docs/TASK_REPLAY.md",
        ROOT / "uv.lock",
    ]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    for p in sources:
        target = out / "source-snapshot" / p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes())
    save_json(out / "protocol.json", PROTOCOL)
    save_json(
        out / "manifest.json",
        {
            "protocol_hash": digest(PROTOCOL),
            "sources": hashes,
            "git_status": subprocess.check_output(
                ["git", "status", "--short"], cwd=ROOT, text=True
            ),
            "git_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "python": platform.python_version(),
            "versions": require_versions(),
            "scope": PROTOCOL["scope"],
        },
    )
    parent = RouterCheckpoint.load(ROOT / PROTOCOL["parent"])
    random_control = RouterCheckpoint.load(ROOT / PROTOCOL["random_control"])
    original_inputs = {
        name: hashlib.sha256((ROOT / PROTOCOL[name]).read_bytes()).hexdigest()
        for name in ("parent", "random_control", "anchors")
    }
    parent.save(out / "parent-references.json")
    random_control.save(out / "random-references.json")
    groups: dict[str, list[ReplayItem]] = {name: [] for name in PROTOCOL["dataset_order"]}
    collections = []
    old_dir = ROOT / Path(PROTOCOL["anchors"]).parent
    fitting = json.loads((old_dir / "fitting.json").read_text())
    prior_rows = json.loads(gzip.decompress((ROOT / PROTOCOL["anchors"]).read_bytes()))
    prior = {(r["context"], r["step"]): r for r in prior_rows if r["split"] != "comparison"}
    # Reconstruct exact observed source IDs, rather than inventing IDs for stored K rows.
    for source in fitting["collections"]:
        if source["split"] not in ("training", "validation"):
            continue
        path = old_dir / source["file"]
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError("old replay source checksum differs")
        episode = json.loads(gzip.decompress(raw))
        role = "anchor" if source["split"] == "training" else "validation_old"
        items = episode_items(episode, role, PROTOCOL["samples_per_episode"])
        for item in items:
            original = prior[(item.sample.context, item.sample.step)]
            if (
                original["keys"] != item.sample.keys.tolist()
                or original["queries"] != item.sample.queries.tolist()
            ):
                raise ValueError("anchor differs from the frozen parent corpus")
        copied = "anchor-" + path.name
        with (out / copied).open("xb") as stream:
            stream.write(raw)
        groups[role].extend(items)
        collections.append(
            {
                "role": role,
                "root": "experiment",
                "repository_source": str(path.relative_to(ROOT)),
                "file": copied,
                "sha256": source["sha256"],
                "samples": len(items),
            }
        )
    for role, seed_key in (
        ("wake", "wake_seeds"),
        ("validation_new", "validation_seeds"),
        ("comparison", "comparison_seeds"),
    ):
        for env in PROTOCOL["environments"]:
            for seed in PROTOCOL[seed_key]:
                stem = f"collect-{role}-{env}-{seed}"
                episode = persistent_episode(
                    out / "archives" / (stem + ".sqlite"),
                    env,
                    seed,
                    parent,
                    "zha",
                    PROTOCOL["step_cap"],
                )
                # A collection failure remains evidence; never train from an incomplete/error-labelled run.
                artifact = save_trace(out / (stem + ".json.gz"), episode)
                if episode["result"]["error"]:
                    raise RuntimeError({"collection": stem, "error": episode["result"]["error"]})
                items = episode_items(episode, role, PROTOCOL["samples_per_episode"])
                groups[role].extend(items)
                collections.append(
                    {
                        "role": role,
                        "root": "experiment",
                        "environment": env,
                        "seed": seed,
                        "result": episode["result"],
                        "samples": len(items),
                        **artifact,
                    }
                )
                print("Collected", role, env, seed, episode["result"]["success"], flush=True)
    dropped = deduplicate(groups)
    corpus = [dict(item.payload(), id=item.uid) for items in groups.values() for item in items]
    corpus_artifact = save_trace(out / "corpus.json.gz", corpus)
    save_json(
        out / "collections.json",
        {
            "sources": collections,
            "dropped": dropped,
            "retained": {k: len(v) for k, v in groups.items()},
            "original_inputs": original_inputs,
        },
    )
    learned: dict[str, RouterCheckpoint] = {}
    learning = []
    for schedule in PROTOCOL["schedules"]:
        for seed in PROTOCOL["optimizer_seeds"]:
            name = f"{schedule}-{seed}"
            started = time.perf_counter()
            checkpoint, trace = replay_references(
                groups["anchor"] + groups["wake"],
                groups["validation_old"],
                groups["validation_new"],
                parent,
                cast(Schedule, schedule),
                seed=seed,
                steps=PROTOCOL["steps"],
                learning_rate=PROTOCOL["learning_rate"],
            )
            elapsed = time.perf_counter() - started
            checkpoint.save(out / (name + "-references.json"))
            trace["seconds"] = elapsed
            artifact = save_trace(out / (name + "-learning.json.gz"), trace)
            learning.append(
                {
                    "condition": name,
                    "selected_step": checkpoint.selected_step,
                    "initial": trace["history"][0],
                    "selected": next(
                        r for r in trace["history"] if r["step"] == checkpoint.selected_step
                    ),
                    "work": trace["work"],
                    "child_hash": checkpoint.sha256,
                    **artifact,
                }
            )
            learned[name] = checkpoint
            print("Replayed", name, "selected", checkpoint.selected_step, flush=True)
    save_json(out / "learning.json", {"runs": learning})
    models = {"parent": parent, "random": random_control, **learned}
    qualities = {}
    for name, model in models.items():
        cases = quality([i.sample for i in groups["comparison"]], model)
        artifact = save_trace(out / (name + "-quality.json.gz"), cases)
        qualities[name] = {
            "queries": len(cases),
            "mean_kl": statistics.mean(r["pooled_kl"] for r in cases),
            "mean_retained_mass": statistics.mean(r["retained_mass"] for r in cases),
            "mean_keys": statistics.mean(len(r["selected_ids"]) for r in cases),
            **artifact,
        }
    save_json(
        out / "quality.json",
        {
            "scope": "common fresh parent-policy observed prefixes; dense audit is additional work",
            "conditions": qualities,
        },
    )
    configs: list[tuple[str, RouterCheckpoint, Backend, int]] = [
        (name, model, "zha", PROTOCOL["primary_capacity"]) for name, model in models.items()
    ]
    configs += [
        ("exact", parent, "exact", PROTOCOL["primary_capacity"]),
        ("no_recovery", parent, "none", PROTOCOL["primary_capacity"]),
        ("parent-cap96", parent, "zha", 96),
        ("exact-cap96", parent, "exact", 96),
    ]
    runs = []
    workspace = WorkspaceConfig()
    for name, checkpoint, backend, capacity in configs:
        config = WorkspaceConfig(
            capacity=capacity,
            recovery_limit=workspace.recovery_limit,
            half_life=workspace.half_life,
            retire_below=workspace.retire_below,
            max_records=workspace.max_records,
        )
        for env in PROTOCOL["environments"]:
            for seed in PROTOCOL["comparison_seeds"]:
                stem = f"{name}-{env}-{seed}"
                episode = persistent_episode(
                    out / "archives" / (stem + ".sqlite"),
                    env,
                    seed,
                    checkpoint,
                    backend,
                    PROTOCOL["step_cap"],
                    workspace=config,
                )
                artifact = save_trace(out / (stem + ".json.gz"), episode)
                row = {
                    "condition": name,
                    "environment": env,
                    "seed": seed,
                    "backend": backend,
                    "capacity": capacity,
                    "reference_hash": checkpoint.sha256,
                    **episode["result"],
                    "costs": episode["costs"],
                    **artifact,
                }
                runs.append(row)
                save_json(out / ("run-" + stem + ".json"), row)
                print("Retested", name, env, seed, episode["result"]["success"], flush=True)
    for source, checksum in hashes.items():
        if hashlib.sha256((ROOT / source).read_bytes()).hexdigest() != checksum:
            raise RuntimeError("source changed during replay experiment")
    for name, checksum in original_inputs.items():
        if hashlib.sha256((ROOT / PROTOCOL[name]).read_bytes()).hexdigest() != checksum:
            raise RuntimeError("baseline/corpus was changed by replay")
    summary = [
        {
            "condition": name,
            "capacity": cap,
            "successes": sum(r["success"] for r in runs if r["condition"] == name),
            "episodes": sum(r["condition"] == name for r in runs),
            "actions": sum(r["steps"] for r in runs if r["condition"] == name),
            "errors": sum(r["error"] is not None for r in runs if r["condition"] == name),
        }
        for name, _, _, cap in configs
    ]
    save_json(
        out / "report.json",
        {
            "complete": True,
            "protocol_hash": digest(PROTOCOL),
            "corpus_artifact": corpus_artifact,
            "summary": summary,
            "runs": runs,
            "source_hashes_unchanged": True,
            "original_inputs_unchanged": True,
            "claim_boundary": "routing-parameter replay study; no task/quality win assumed, no biological dreaming or speed guarantee",
        },
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
