import concurrent.futures
import gzip
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OLD = ROOT / "experiments/minigrid-development-v2"
TARGET = ROOT / "experiments/dependency-baseline-parity-v1/PARITY_CURRENT_REPLAY.json"
TIMES = {
    "policy_seconds",
    "planning_seconds",
    "index_rebuild_seconds",
    "retrieval_seconds",
    "episode_seconds",
    "dependency_seconds",
}


def normalized(value):
    if isinstance(value, dict):
        return {k: normalized(v) for k, v in value.items() if k not in TIMES}
    if isinstance(value, (list, tuple)):
        return [normalized(v) for v in value]
    return value


def check(path):
    from research.minigrid_benchmark import ObservationPlanner

    torch.set_num_threads(1)
    data = json.loads(gzip.decompress(path.read_bytes()))
    actor = ObservationPlanner(data["reader"], data["capacity"])
    for row in data["trajectory"]:
        obs = {
            **row["observation"],
            "image": np.asarray(row["observation"]["image"], dtype=np.uint8),
        }
        action, decision, added = actor.act(obs)
        assert action == row["action"], (path.name, row["step"], "action")
        assert normalized(decision) == normalized(row["decision"]), (
            path.name,
            row["step"],
            "decision",
            [k for k in decision if normalized(decision[k]) != normalized(row["decision"].get(k))],
        )
        from dataclasses import asdict

        assert normalized([asdict(f) for f in added]) == row["new_facts"], (
            path.name,
            row["step"],
            "versions",
        )
    assert normalized(actor.reader.archive()) == data["archive"], (path.name, "archive")
    return {
        "trace_file": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "steps_checked": len(data["trajectory"]),
        "reader": data["reader"],
        "environment_id": data["environment_id"],
        "seed": data["seed"],
        "passed": True,
    }


if __name__ == "__main__":
    started = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as pool:
        rows = list(pool.map(check, sorted(OLD.glob("episode-*.json.gz"))))
    old_source = OLD / "source-snapshot/research/minigrid_benchmark.py"
    current = ROOT / "research/minigrid_benchmark.py"
    result = {
        "all_passed": True,
        "episodes_checked": len(rows),
        "steps_checked": sum(r["steps_checked"] for r in rows),
        "current_source_sha256": hashlib.sha256(current.read_bytes()).hexdigest(),
        "frozen_reference_source_sha256": hashlib.sha256(old_source.read_bytes()).hexdigest(),
        "reference_directory": str(OLD),
        "checked": "same observation prefix, actions, every decision/query/selected ID/route/work count except timing, added versions and final immutable archive",
        "excluded_timing_fields": sorted(TIMES),
        "episodes": rows,
        "wall_seconds": time.perf_counter() - started,
    }
    TARGET.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "episodes"}, indent=2))
