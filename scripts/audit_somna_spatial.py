"""Independent scalar audit of raw Somna outputs; imports no numerical core."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def close(actual: float, expected: float) -> None:
    if not math.isfinite(actual) or not math.isclose(
        actual, expected, rel_tol=1e-10, abs_tol=1e-10
    ):
        raise AssertionError(f"raw numerical mismatch: {actual} vs {expected}")


def audit_world(entry: dict[str, Any]) -> dict[str, int]:
    world = entry["world"]
    episodes = world["transitions"]
    states = len(world["cells"])
    goal = world["goal"]
    assert digest(episodes) == entry["archive_hash"]
    # Independent reachability / exact graph-planning ceiling.
    distance = {goal: 0}
    while True:
        expanded = dict(distance)
        for row in episodes:
            if row["successor"] in distance:
                expanded[row["state"]] = min(
                    expanded.get(row["state"], states * 4), distance[row["successor"]] + 1
                )
        if expanded == distance:
            break
        distance = expanded
    assert all(s in distance for s in world["evaluation_starts"])
    assert len(distance) == states
    updates_checked = 0
    routes_checked = 0
    for fork in entry["forks"]:
        assert fork["archive_hash"] == entry["archive_hash"]
        assert fork["initial_checkpoint_hash"] == digest(entry["initial_q"])
        assert fork["environment_calls_during_offline"] == 0
        q = [row[:] for row in entry["initial_q"]]
        rng = random.Random(world["seed"] + 40)
        assert len(fork["records"]) == fork["updates"]
        assert fork["frames"][0]["q"] == q and fork["frames"][0]["iteration"] == 0
        frame_index = 1
        for iteration, record in enumerate(fork["records"], 1):
            row = episodes[record["evidence_id"] - 1]
            assert (record["state"], record["action"]) == (row["state"], row["action"])
            assert row["evidence"] == "observed"
            values = [max(actions) for actions in q]
            values[goal] = 0.0
            if fork["policy"] == "uniform":
                assert row == episodes[rng.randrange(len(episodes))]
                assert record["scheduler_comparisons"] == 0
            else:
                errors = [
                    abs(r["reward"] + 0.95 * values[r["successor"]] - q[r["state"]][r["action"]])
                    for r in episodes
                ]
                chosen = next(i for i, v in enumerate(errors) if v >= max(errors) - 1e-10)
                assert row == episodes[chosen]
                assert record["scheduler_comparisons"] == len(episodes)
            selected = record["selected_ids"]
            assert len(selected) == len(set(selected)) and 0 in selected
            assert all(type(i) is int and 0 <= i <= len(episodes) for i in selected)
            if fork["backend"] == "dense":
                assert selected == list(range(len(episodes) + 1))
                assert record["steps"] == []
            else:
                # Validate leaf materialization against recorded hierarchy decisions.
                level_one = next(s for s in record["steps"] if s["level"] == 1)
                expected = {0}
                for group in level_one["selected"]:
                    expected.update(range(1 + group * 8, 1 + (group + 1) * 8))
                expected.update(range(1 + len(episodes) // 8 * 8, len(episodes) + 1))
                assert selected == sorted(expected)
                assert record["scored_nodes"] == sum(len(s["candidates"]) for s in record["steps"])
            assert record["summary_dot_products"] == record["scored_nodes"] * states
            assert record["attention_pairs"] == len(selected)
            logits = [
                0.0
                if i == 0
                else 256.0
                * (
                    (episodes[i - 1]["state"] == row["state"])
                    + (episodes[i - 1]["action"] == row["action"])
                )
                / math.sqrt(states + 4)
                for i in selected
            ]
            weights = [math.exp(v - max(logits)) for v in logits]
            denominator = sum(weights)
            probabilities = [0.0] * states
            reward = 0.0
            for identifier, weight in zip(selected, weights, strict=True):
                if identifier:
                    observation = episodes[identifier - 1]
                    probabilities[observation["successor"]] += weight / denominator
                    reward += weight / denominator * observation["reward"]
            for actual, expected_p in zip(record["probabilities"], probabilities, strict=True):
                close(actual, expected_p)
            close(record["reward"], reward)
            close(record["before"], q[row["state"]][row["action"]])
            expected_value = reward + 0.95 * sum(
                p * v for p, v in zip(probabilities, values, strict=True)
            )
            close(record["after"], expected_value)
            close(record["delta"], record["after"] - record["before"])
            q[row["state"]][row["action"]] = record["after"]
            assert record["iteration"] == iteration
            if iteration % 8 == 0 or iteration == fork["updates"]:
                frame = fork["frames"][frame_index]
                assert frame["q"] == q and frame["read"] == record
                assert frame["iteration"] == iteration
                frame_index += 1
            updates_checked += 1
            routes_checked += 1
        assert frame_index == len(fork["frames"])
        assert q == fork["q"] and digest(q) == fork["checkpoint_hash"]
        for name, total in fork["work"].items():
            assert total == sum(row[name] for row in fork["records"])
        # Policy evaluation independent of production evaluator.
        lookup = {(r["state"], r["action"]): r["successor"] for r in episodes}
        successes = 0
        for trial in fork["evaluation"]["paths"]:
            state = trial["start"]
            path = [state]
            seen: set[int] = set()
            while state != goal and state not in seen and len(path) <= 4 * states:
                seen.add(state)
                action = next(a for a, v in enumerate(q[state]) if v >= max(q[state]) - 1e-10)
                state = lookup[state, action]
                path.append(state)
            assert path == trial["path"] and (state == goal) == trial["success"]
            successes += state == goal
        assert successes == fork["evaluation"]["successes"]
        assert len(fork["evaluation"]["paths"]) == fork["evaluation"]["trials"]
    return {
        "updates_checked": updates_checked,
        "routes_checked": routes_checked,
        "graph_planner_successes": len(world["evaluation_starts"]),
        "canonical_records": len(episodes),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.results / "manifest.json").read_text())
    root = Path(__file__).resolve().parents[1]
    for name, checksum in manifest["source_hashes"].items():
        frozen = args.results / "source-snapshot" / name
        source = frozen if frozen.exists() else root / name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == checksum, name
    paths = sorted([*args.results.glob("world-*.json"), *args.results.glob("world-*.json.gz")])
    checks = {
        p.name: audit_world(
            json.loads(gzip.decompress(p.read_bytes()) if p.suffix == ".gz" else p.read_bytes())
        )
        for p in paths
    }
    assert len(checks) == 4
    report = {
        "all_passed": True,
        "scope": "independent scalar selected-attention, Bellman, scheduler, work, frozen-source and graph-ceiling audit",
        "worlds": checks,
    }
    (args.results / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
