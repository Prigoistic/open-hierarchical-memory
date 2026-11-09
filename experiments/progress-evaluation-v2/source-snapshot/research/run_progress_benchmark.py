"""Progress-retrieval repair experiments with explicit graph fallback controls."""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import json
import platform
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, cast

import torch

from research.dependency_memory import (
    MAX_BUNDLES,
    DependencyName,
    DependencyReader,
)
from research.minigrid_benchmark import ObservationPlanner, serial_observation
from research.progress_retrieval import (
    CANDIDATE_BUDGET,
    CUE_AFTER,
    GRAPH_AFTER,
    HARD_GRAPH_AFTER,
    HISTORY_LIMIT,
    PROGRESS_READERS,
    WIDEN_AFTER,
    ProgressName,
    ProgressReader,
)
from research.run_minigrid_benchmark import ENVIRONMENTS, environment, require_versions

ROOT = Path(__file__).resolve().parents[1]
BASELINES = ("bundle_zha", "bundle_exact", "graph")
CONDITIONS = (*BASELINES, *PROGRESS_READERS)
DEVELOPMENT_SEEDS = (0, 1)
FRESH_SEEDS = (3001, 3002, 3003, 3004, 3005, 3006)
EXPOSED_SEEDS = (2001, 2002, 2003, 2004, 2005, 2006)
PROTOCOL = {
    "version": "progress-cues-widening-compact-events-v4",
    "development_seeds": DEVELOPMENT_SEEDS,
    "evaluation_seeds": FRESH_SEEDS,
    "previously_exposed_seeds": EXPOSED_SEEDS,
    "progress": {
        "history_limit": HISTORY_LIMIT,
        "cue_after": CUE_AFTER,
        "widen_after": WIDEN_AFTER,
        "graph_after_repeated": GRAPH_AFTER,
        "hard_graph_after": HARD_GRAPH_AFTER,
        "candidate_budget": CANDIDATE_BUDGET,
        "fallback": "full observed graph until new canonical payload; not a ZHA win",
    },
    "environments": ENVIRONMENTS,
    "conditions": CONDITIONS,
    "capacity": 96,
    "current_observation_exempt": True,
    "mask": {
        "origin": [-32, -32],
        "shape": [64, 64],
        "bytes": 512,
        "contains": "observed-known only; no object or passability",
    },
    "max_nominated_bundles": MAX_BUNDLES,
    "closure": "observed path plus accessible observed matching-key prerequisites and one-hop known-neighbor halo; no global frontier-closure claim",
    "packing": "whole historical support set union or explicit rejection; no coverage fallback",
    "graph_control": "all observed current heads eligible; same mission/frontier ranking and closure as retrieval seeds",
    "cue_controls": "cues_zha/exact never use graph fallback; progress_zha/exact share identical observable progress rules",
    "official_versions": {"minigrid": "3.1.0", "gymnasium": "1.4.0"},
    "external_step_cap": 4096,
    "scope": "hand-written partial-observation controller;96 raw facts plus explicit512-byte known mask where declared; not neural learning/dreaming/novelty",
}


def run_episode(
    identifier: str,
    reader: str,
    seed: int,
    *,
    split: str,
    capacity: int = 96,
    step_cap: int = 4096,
    factory: Callable[[str], Any] = environment,
) -> dict[str, Any]:
    if (
        identifier not in ENVIRONMENTS
        or reader not in CONDITIONS
        or split not in ("development", "diagnostic", "evaluation", "unit")
    ):
        raise ValueError("unsupported dependency episode")
    if type(seed) is not int or type(step_cap) is not int or not 1 <= step_cap <= 4096:
        raise ValueError("invalid episode seed/budget")
    torch.set_num_threads(1)
    injected = (
        ProgressReader(cast(ProgressName, reader), capacity)
        if reader in PROGRESS_READERS
        else DependencyReader(cast(DependencyName, reader), capacity)
    )
    actor = ObservationPlanner("none", capacity, injected_reader=injected)
    trajectory: list[dict[str, Any]] = []
    routing_snapshots: dict[str, dict[str, Any]] = {}
    routing_events: dict[str, dict[str, Any]] = {}
    reward_sum = 0.0
    error = None
    terminated = truncated = False
    env = None
    started = time.perf_counter()
    try:
        env = factory(identifier)
        observation, _ = env.reset(seed=seed)
        for step in range(step_cap):
            before = serial_observation(observation)
            action, decision, added = actor.act(observation)
            if "repair" in decision.get("dependency", {}):
                repair = decision["dependency"].pop("repair")
                for route in decision["route"]:
                    source_snapshot_label = route.pop("snapshot_id")
                    layout = {
                        key: route.pop(key)
                        for key in (
                            "index_fact_ids",
                            "node_spans",
                            "chunk_size",
                            "depth",
                            "logical_key_count",
                        )
                    }
                    layout["source_snapshot_label"] = source_snapshot_label
                    snapshot_id = hashlib.sha256(
                        json.dumps(layout, sort_keys=True, separators=(",", ":")).encode()
                    ).hexdigest()
                    route["snapshot_id"] = snapshot_id
                    if (
                        snapshot_id in routing_snapshots
                        and routing_snapshots[snapshot_id] != layout
                    ):
                        raise ValueError("routing snapshot identity changed")
                    routing_snapshots[snapshot_id] = layout
                repair["attempts"] = [
                    {
                        "route_index": i,
                        "cue_label": repair["cues"][route["query_index"]]["label"],
                        "query_index": route["query_index"],
                        "attempt": route["attempt"],
                        "p": route["p"],
                        "snapshot_id": route["snapshot_id"],
                    }
                    for i, route in enumerate(decision["route"])
                ]
                event_refs = []
                for route in decision["route"]:
                    route_ref = hashlib.sha256(
                        json.dumps(
                            route, sort_keys=True, separators=(",", ":"), allow_nan=False
                        ).encode()
                    ).hexdigest()
                    if route_ref in routing_events and routing_events[route_ref] != route:
                        raise ValueError("routing event identity changed")
                    routing_events[route_ref] = route
                    event_refs.append({"route_ref": route_ref})
                decision["route"] = event_refs
                decision["repair"] = repair
                decision["queries"] = [cue["vector"] for cue in repair["cues"]]
            observation, reward, terminated, truncated, _ = env.step(action)
            reward_sum += float(reward)
            trajectory.append(
                {
                    "step": step,
                    "observation": before,
                    "new_facts": [asdict(f) for f in added],
                    "decision": decision,
                    "action": action,
                    "reward": float(reward),
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                    "next_observation": serial_observation(observation),
                }
            )
            if terminated or truncated:
                break
    except Exception as caught:
        error = {
            "type": type(caught).__name__,
            "message": str(caught),
            "traceback": traceback.format_exc(),
        }
    finally:
        if env is not None:
            env.close()
    return {
        "environment_id": identifier,
        "seed": seed,
        "split": split,
        "reader": reader,
        "capacity": capacity,
        "feature_version": "minigrid-observed-semantic-position-v1",
        "coverage_allowance_bytes": 512,
        "archive": actor.reader.archive(),
        "routing_snapshots": routing_snapshots,
        "routing_events": routing_events,
        "trajectory": trajectory,
        "result": {
            "success": reward_sum > 0,
            "return": reward_sum,
            "steps": len(trajectory),
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "external_cutoff": not terminated and not truncated and error is None,
            "error": error,
        },
        "costs": {
            **actor.reader.costs,
            "wire_routing_event_count": len(routing_events),
            "wire_routing_event_json_bytes": len(
                json.dumps(routing_events, separators=(",", ":")).encode()
            ),
            "wire_routing_snapshot_count": len(routing_snapshots),
            "wire_routing_snapshot_json_bytes": len(
                json.dumps(routing_snapshots, separators=(",", ":")).encode()
            ),
            "planning_seconds": sum(row["decision"]["planning_seconds"] for row in trajectory),
            "policy_seconds": sum(row["decision"]["policy_seconds"] for row in trajectory),
            "episode_seconds": time.perf_counter() - started,
        },
        "controller_scope": "same symbolic planner; optional known-only mask suppresses omitted-known frontier neighbors, never adds traversal",
    }


def save_episode(output: Path, configuration: tuple[str, str, int, str, int]) -> dict[str, Any]:
    identifier, reader, seed, split, capacity = configuration
    episode = run_episode(identifier, reader, seed, split=split, capacity=capacity)
    episode["protocol_hash"] = json.loads((output / "manifest.json").read_text())["protocol_hash"]
    filename = f"episode-{identifier}-{reader}-{seed}.json.gz"
    raw = json.dumps(episode, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) >= 128 * 1024 * 1024:
        raise ValueError("expanded trace exceeds128MiB inspector/audit contract")
    data = gzip.compress(raw, mtime=0)
    (output / filename).write_bytes(data)
    print(
        identifier,
        reader,
        seed,
        episode["result"]["success"],
        episode["result"]["steps"],
        "error" if episode["result"]["error"] else "",
        flush=True,
    )
    return {
        "environment_id": identifier,
        "reader": reader,
        "seed": seed,
        **episode["result"],
        "costs": episode["costs"],
        "trace_file": filename,
        "sha256": hashlib.sha256(data).hexdigest(),
        "expanded_bytes": len(raw),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--split", choices=("development", "diagnostic", "evaluation"), required=True
    )
    parser.add_argument("--readers", nargs="+", choices=CONDITIONS, default=list(CONDITIONS))
    parser.add_argument(
        "--environments", nargs="+", choices=ENVIRONMENTS, default=list(ENVIRONMENTS)
    )
    parser.add_argument("--capacity", type=int, choices=(96,), default=96)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 4:
        raise SystemExit("fresh output and1–4 workers required")
    versions = require_versions()
    args.output.mkdir(parents=True)
    seeds = (
        DEVELOPMENT_SEEDS
        if args.split == "development"
        else EXPOSED_SEEDS
        if args.split == "diagnostic"
        else FRESH_SEEDS
    )
    protocol = {
        **PROTOCOL,
        "split": args.split,
        "selected_seeds": seeds,
        "selected_readers": args.readers,
        "selected_environments": args.environments,
        "capacity": args.capacity,
        "workers": args.workers,
    }
    raw_protocol = json.dumps(protocol, indent=2, sort_keys=True).encode()
    (args.output / "protocol.json").write_bytes(raw_protocol + b"\n")
    names = [
        "research/progress_retrieval.py",
        "research/run_progress_benchmark.py",
        "research/dependency_memory.py",
        "research/run_dependency_benchmark.py",
        "research/minigrid_benchmark.py",
        "research/run_minigrid_benchmark.py",
        "tests/test_progress_retrieval.py",
        "docs/PROGRESS_RETRIEVAL.md",
        "uv.lock",
    ]
    names.extend(
        str(path.relative_to(ROOT)) for path in (ROOT / "src/open_hierarchical_memory").glob("*.py")
    )
    hashes = {}
    for name in names:
        data = (ROOT / name).read_bytes()
        hashes[name] = hashlib.sha256(data).hexdigest()
        target = args.output / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = {
        "protocol_hash": hashlib.sha256(raw_protocol).hexdigest(),
        "source_hashes": hashes,
        "versions": versions,
        "python": platform.python_version(),
        "dtype": "CPU float64",
        "torch_threads_per_worker": 1,
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    configurations = [
        (env, reader, seed, args.split, args.capacity)
        for env in args.environments
        for reader in args.readers
        for seed in seeds
    ]
    started = time.perf_counter()
    if args.workers == 1:
        episodes = [save_episode(args.output, config) for config in configurations]
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
            jobs = [pool.submit(save_episode, args.output, config) for config in configurations]
            episodes = [job.result() for job in jobs]
    summaries = []
    for env in args.environments:
        for reader in args.readers:
            rows = [
                row for row in episodes if row["environment_id"] == env and row["reader"] == reader
            ]
            summaries.append(
                {
                    "environment_id": env,
                    "reader": reader,
                    "successes": sum(row["success"] for row in rows),
                    "episodes": len(rows),
                    "mean_steps": sum(row["steps"] for row in rows) / len(rows),
                    "mean_return": sum(row["return"] for row in rows) / len(rows),
                    "errors": sum(row["error"] is not None for row in rows),
                    "truncations": sum(row["truncated"] for row in rows),
                    "cutoffs": sum(row["external_cutoff"] for row in rows),
                    "costs": {
                        name: sum(row["costs"][name] for row in rows) for name in rows[0]["costs"]
                    },
                }
            )
    changed = [
        name
        for name, expected in hashes.items()
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected
    ]
    report = {
        "protocol": protocol,
        "episodes": episodes,
        "summaries": summaries,
        "source_changed_during_run": changed,
        "wall_seconds_including_output": time.perf_counter() - started,
        "claim_scope": PROTOCOL["scope"],
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# Progress-retrieval comparison",
        "",
        f"Split {args.split}; seeds {seeds}; raw capacity {args.capacity}. Mask-bearing conditions additionally transport512 binary known bits bytes plus version/identity metadata. No method gets hidden observations.",
        "",
        "| Task | Reader | Successes | Mean steps | Truncated | Errors |",
        "|---|---|---:|---:|---:|---:|",
    ]
    lines += [
        f"| {r['environment_id']} | {r['reader']} | {r['successes']}/{r['episodes']} | {r['mean_steps']:.1f} | {r['truncations']} | {r['errors']} |"
        for r in summaries
    ]
    lines += [
        "",
        "All graph scans, prerequisite checks, BFS, path halos and mask serialization are charged. Flat-mask controls isolate the known-coverage extension. ZHA dependence, task performance and total cost are separate questions. No novelty, speedup, biological dreaming or production claim follows from this integration.",
    ]
    (args.output / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    if changed and args.split == "evaluation":
        raise SystemExit("frozen source changed during formal run")


if __name__ == "__main__":
    main()
