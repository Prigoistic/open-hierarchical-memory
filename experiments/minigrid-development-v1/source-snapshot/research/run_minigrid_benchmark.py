"""Official partial-observation MiniGrid episodes; all outcomes and failures retained."""

from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import hashlib
import importlib
import importlib.metadata
import json
import platform
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch

from research.minigrid_benchmark import (
    FEATURE_VERSION,
    READERS,
    ObservationPlanner,
    ReaderName,
    serial_observation,
)

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENTS = (
    "MiniGrid-MemoryS17Random-v0",
    "MiniGrid-MultiRoom-N6-v0",
    "MiniGrid-DoorKey-16x16-v0",
    "MiniGrid-KeyCorridorS6R3-v0",
)
DEVELOPMENT_SEEDS = (0, 1)
EVALUATION_SEEDS = (1001, 1002, 1003)
PROTOCOL: dict[str, Any] = {
    "version": "minigrid-observation-only-v1",
    "development_seeds": DEVELOPMENT_SEEDS,
    "evaluation_seeds": EVALUATION_SEEDS,
    "environments": ENVIRONMENTS,
    "readers": READERS,
    "capacity": 96,
    "controller_history": 16,
    "feature_version": FEATURE_VERSION,
    "routing": {
        "chunk_size": 4,
        "depth": 3,
        "p": 0.4,
        "references": "eight fixed untrained semantic/spatial references",
    },
    "official_versions": {"minigrid": "3.1.0", "gymnasium": "1.4.0"},
    "external_step_cap": 4096,
    "policy_input": "only official image/direction/mission plus own egomotion and16-pose history; no environment handle",
    "scope": "fixed symbolic observation-aware planner; not RL training or industry validation",
}


def require_versions() -> dict[str, str]:
    versions = {
        name: importlib.metadata.version(name)
        for name in ("minigrid", "gymnasium", "pygame-ce", "torch", "numpy")
    }
    for name, expected in PROTOCOL["official_versions"].items():
        if versions[name] != expected:
            raise ValueError(f"protocol requires{name}=={expected}; found{versions[name]}")
    return versions


def environment(identifier: str) -> Any:
    """Only dynamic SDK boundary. Its returned handle never reaches the actor."""
    importlib.import_module("minigrid")
    gym = importlib.import_module("gymnasium")
    return gym.make(identifier)


def run_episode(
    identifier: str,
    reader: ReaderName,
    seed: int,
    *,
    split: str,
    capacity: int = 96,
    step_cap: int = 4096,
    factory: Callable[[str], Any] = environment,
) -> dict[str, Any]:
    if (
        identifier not in ENVIRONMENTS
        or reader not in READERS
        or split not in ("development", "evaluation", "unit")
    ):
        raise ValueError("unsupported episode configuration")
    if type(seed) is not int or type(step_cap) is not int or not 1 <= step_cap <= 4096:
        raise ValueError("invalid seed/action budget")
    torch.set_num_threads(1)
    actor = ObservationPlanner(reader, capacity)
    trajectory: list[dict[str, Any]] = []
    errors = None
    terminated = truncated = False
    reward_sum = 0.0
    started = time.perf_counter()
    env = None
    try:
        env = factory(identifier)
        observation, _ = env.reset(seed=seed)
        for step in range(step_cap):
            before = serial_observation(observation)
            action, decision, additions = actor.act(observation)
            observation, reward, terminated, truncated, _ = env.step(action)
            reward_sum += float(reward)
            trajectory.append(
                {
                    "step": step,
                    "observation": before,
                    "new_facts": [asdict(fact) for fact in additions],
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
    except Exception as error:
        errors = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
    finally:
        if env is not None:
            env.close()
    elapsed = time.perf_counter() - started
    return {
        "environment_id": identifier,
        "seed": seed,
        "split": split,
        "reader": reader,
        "capacity": capacity,
        "feature_version": FEATURE_VERSION,
        "archive": actor.reader.archive(),
        "trajectory": trajectory,
        "result": {
            "success": reward_sum > 0,
            "return": reward_sum,
            "steps": len(trajectory),
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "external_cutoff": not terminated and not truncated and errors is None,
            "error": errors,
        },
        "costs": {
            **actor.reader.costs,
            "planning_seconds": sum(row["decision"]["planning_seconds"] for row in trajectory),
            "policy_seconds": sum(row["decision"]["policy_seconds"] for row in trajectory),
            "episode_seconds": elapsed,
        },
        "controller_scope": "same task-aware partial-observation planner for all readers; bounded16-pose loop avoidance; no learned policy",
    }


def episode_file(identifier: str, reader: str, seed: int) -> str:
    return f"episode-{identifier}-{reader}-{seed}.json.gz"


def save_episode(
    output: Path, configuration: tuple[str, ReaderName, int, str, int]
) -> dict[str, Any]:
    identifier, reader, seed, split, capacity = configuration
    episode = run_episode(identifier, reader, seed, split=split, capacity=capacity)
    episode["protocol_hash"] = json.loads((output / "manifest.json").read_text())["protocol_hash"]
    payload = json.dumps(episode, separators=(",", ":"), allow_nan=False).encode()
    path = output / episode_file(identifier, reader, seed)
    path.write_bytes(gzip.compress(payload, mtime=0))
    result = {
        "environment_id": identifier,
        "reader": reader,
        "seed": seed,
        **episode["result"],
        "costs": episode["costs"],
        "trace_file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    print(
        identifier,
        reader,
        seed,
        result["success"],
        result["steps"],
        "error" if result["error"] else "",
        flush=True,
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--split", choices=("development", "evaluation"), required=True)
    parser.add_argument(
        "--environments", nargs="+", choices=ENVIRONMENTS, default=list(ENVIRONMENTS)
    )
    parser.add_argument("--readers", nargs="+", choices=READERS, default=list(READERS))
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    if args.output.exists() or not 1 <= args.workers <= 4:
        raise SystemExit("fresh output and1–4 workers required")
    versions = require_versions()
    args.output.mkdir(parents=True)
    seeds = DEVELOPMENT_SEEDS if args.split == "development" else EVALUATION_SEEDS
    protocol = {
        **PROTOCOL,
        "split": args.split,
        "selected_environments": args.environments,
        "selected_readers": args.readers,
        "selected_seeds": seeds,
        "workers": args.workers,
    }
    raw_protocol = json.dumps(protocol, indent=2, sort_keys=True).encode()
    (args.output / "protocol.json").write_bytes(raw_protocol + b"\n")
    files = [
        "research/minigrid_benchmark.py",
        "research/run_minigrid_benchmark.py",
        "tests/test_minigrid_benchmark.py",
        "docs/MINIGRID_BENCHMARK.md",
        "uv.lock",
    ]
    files.extend(
        str(p.relative_to(ROOT)) for p in (ROOT / "src/open_hierarchical_memory").glob("*.py")
    )
    source_hashes = {}
    for name in files:
        data = (ROOT / name).read_bytes()
        source_hashes[name] = hashlib.sha256(data).hexdigest()
        target = args.output / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    manifest = {
        "protocol_hash": hashlib.sha256(raw_protocol).hexdigest(),
        "source_hashes": source_hashes,
        "versions": versions,
        "python": platform.python_version(),
        "dtype": "CPU float64",
        "torch_threads_per_worker": 1,
        "note": "policy never receives environment handle or hidden simulator telemetry",
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    configurations = [
        (identifier, reader, seed, args.split, 96)
        for identifier in args.environments
        for reader in args.readers
        for seed in seeds
    ]
    started = time.perf_counter()
    if args.workers == 1:
        episodes = [save_episode(args.output, configuration) for configuration in configurations]
    else:
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as pool:
            jobs = [
                pool.submit(save_episode, args.output, configuration)
                for configuration in configurations
            ]
            episodes = [job.result() for job in jobs]
    summaries = []
    for identifier in args.environments:
        for reader in args.readers:
            rows = [
                e for e in episodes if e["environment_id"] == identifier and e["reader"] == reader
            ]
            summaries.append(
                {
                    "environment_id": identifier,
                    "reader": reader,
                    "successes": sum(row["success"] for row in rows),
                    "episodes": len(rows),
                    "mean_return": sum(row["return"] for row in rows) / len(rows),
                    "mean_steps": sum(row["steps"] for row in rows) / len(rows),
                    "truncations": sum(row["truncated"] for row in rows),
                    "cutoffs": sum(row["external_cutoff"] for row in rows),
                    "errors": sum(row["error"] is not None for row in rows),
                    "costs": {
                        name: sum(row["costs"][name] for row in rows) for name in rows[0]["costs"]
                    },
                }
            )
    report = {
        "protocol": protocol,
        "episodes": episodes,
        "summaries": summaries,
        "wall_seconds_including_output": time.perf_counter() - started,
        "claims": "standard tasks, fixed symbolic controller; no ZHA speed, novelty, necessity or industry-validation claim",
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = [
        "# Official MiniGrid observation-only memory comparison",
        "",
        f"Split: {args.split}. Seeds: {seeds}. All results and failures retained. Fixed symbolic planner, no learned RL policy. No environment layout or hidden simulator position reaches the actor.",
        "",
        "| Environment | Reader | Successes | Mean steps | Truncated | Errors |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in summaries:
        lines.append(
            f"| {row['environment_id']} | {row['reader']} | {row['successes']}/{row['episodes']} | {row['mean_steps']:.1f} | {row['truncations']} | {row['errors']} |"
        )
    lines.extend(
        [
            "",
            "All bounded readers share a96-fact slot limit plus the current official partial observation. They retain the same16-pose loop-avoidance history, so none means no episodic recall, not absence of all controller state. Full means all previously observed current facts, not hidden full-layout access. MemoryS17 is a small cue-memory diagnostic and cannot establish a need for hierarchy. The other tasks require exploration and key/door planning; failures also expose limitations of the common controller.",
            "",
            "Each compressed episode contains every official observation before/after each action, returned reward/done flags, own tracked pose, immutable observed versions, actual retrieval queries/selected facts/routes and resource counters. Index rebuild time is included in policy latency. Tensor bytes are index-owned bytes, not total RSS. Process concurrency is recorded; these are not speedup measurements.",
        ]
    )
    (args.output / "SUMMARY.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
