"""Measure unchanged-version head materialisation only, not solver speed."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from research.minigrid_benchmark import Fact
from research.task_memory.support import SupportTaskReader
from research.task_references import digest
from research.task_store import TaskStore, WorkspaceConfig


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise SystemExit("Use a new evidence path")
    records = []
    expected = None
    with tempfile.TemporaryDirectory(prefix="ohm-head-cache-") as temp:
        for cached in (False, True):
            store = TaskStore(Path(temp) / f"{cached}.sqlite", config=WorkspaceConfig(capacity=64))
            reader = SupportTaskReader(
                store, "cache-component/world0", backend="none", cache_heads=cached
            )
            for y in range(-16, 16):
                reader.observe([Fact(0, x, y, 1, 0, 0, y + 16, y + 16) for x in range(-16, 16)])
            version = store.state(reader.context)["version"]
            t = time.perf_counter()
            first = reader._heads(version)
            build = time.perf_counter() - t
            identity = digest([asdict(f) for f in first])
            if expected is None:
                expected = identity
            assert identity == expected
            before = store.work["index_payload_rows"]
            trials = []
            for _ in range(5):
                t = time.perf_counter()
                for _ in range(25):
                    heads = reader._heads(version)
                trials.append(time.perf_counter() - t)
                assert digest([asdict(f) for f in heads]) == expected
            records.append(
                {
                    "cache": cached,
                    "heads": 1024,
                    "repeated_calls": 125,
                    "trial_calls": 25,
                    "first_materialisation_seconds": build,
                    "trial_seconds": trials,
                    "median_trial_seconds": statistics.median(trials),
                    "repeated_decoded_rows": store.work["index_payload_rows"] - before,
                    "serialized_cache_payload_bytes_peak": reader.work[
                        "connector_cache_payload_bytes_peak"
                    ],
                    "source_identity": identity,
                }
            )
            store.close()
    result = {
        "scope": "component-only repeated unchanged-version observed-head materialisation; includes first materialisation separately; excludes router, graph search, planner and whole-task execution; not an end-to-end speed claim",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "support_source_sha256": hashlib.sha256(
            Path(__file__).with_name("support.py").read_bytes()
        ).hexdigest(),
        "records": records,
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
