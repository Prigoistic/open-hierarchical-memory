"""Independent task-memory evidence audit: no production engine/router imports."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests import oracle  # noqa: E402  # Independent scalar oracle, no production imports.


def sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def load(path: Path, checksum: str) -> Any:
    compressed = path.read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == checksum, "artifact checksum"
    with gzip.open(path, "rb") as stream:
        raw = stream.read(128 * 1024 * 1024 + 1)
    assert len(raw) <= 128 * 1024 * 1024, "trace limit"
    return json.loads(raw)


def features(f: dict[str, Any]) -> list[float]:
    x = [
        2 * fn(frequency * math.pi * coordinate / 128.0)
        for coordinate in (f["x"], f["y"])
        for frequency in (1, 2, 4)
        for fn in (math.cos, math.sin)
    ]
    result = x + [0.0] * 18
    result[12 + f["object"]] = 4.0
    result[23 + f["color"]] = 2.0
    result[-1] = 6.0 * f["cue"]
    return result


def route_check(
    route: dict[str, Any],
    query: list[float],
    heads: dict[int, dict[str, Any]],
    refs: list[list[float]],
    p: float,
    *,
    numeric: bool,
) -> None:
    ids = route["index_fact_ids"]
    assert ids == sorted(heads), "index must contain exactly current observed heads"
    keys = [[0.0] * 30] + [features(heads[i]) for i in ids]
    count = len(keys)
    selected_spans: list[tuple[int, int]] = []
    leaves = []
    for step in route["steps"]:
        level = step["level"]
        span = 4**level
        candidates = []
        for start in range(1, count, span):
            end = start + span
            if end > count:
                continue
            parent_start = 1 + (start - 1) // (span * 4) * (span * 4)
            parent_complete = level < 3 and parent_start + span * 4 <= count
            if parent_complete and not any(a <= start and end <= b for a, b in selected_spans):
                continue
            candidates.append((start - 1) // span)
        assert step["candidates"] == candidates, "candidate frontier/parentless ownership"
        assert len(step["scores"]) == len(candidates)
        if numeric:
            for node, actual in zip(candidates, step["scores"], strict=True):
                start = 1 + node * span
                scores = []
                for ref in refs:
                    mean, bias = oracle.summary(keys[start : start + span], ref)
                    scores.append(oracle.dot(query, mean) / math.sqrt(30) + bias)
                assert math.isclose(max(scores), actual, rel_tol=1e-9, abs_tol=1e-9), (
                    "affine/entropy score"
                )
        ordered = sorted(zip(candidates, step["scores"], strict=True), key=lambda r: (-r[1], r[0]))
        partition = oracle.lse([s for _, s in ordered])
        total = 0.0
        chosen = []
        for node, score in ordered:
            chosen.append(node)
            total += math.exp(score - partition)
            if p < 1 and total >= p:
                break
        selected = step["selected"]
        assert selected == [i for i, _ in ordered[: len(selected)]] and selected, "top-p ordering"
        masses = [math.exp(score - partition) for _, score in ordered]
        # Exactly-on-threshold prefixes can differ by one node between log-domain
        # scalar reductions and native softmax/cumsum. Permit only this1e-12 band.
        assert math.fsum(masses[: len(selected)]) >= p - 1e-12, "top-p mass"
        assert math.fsum(masses[: len(selected) - 1]) <= p + 1e-12, "top-p minimal prefix"
        chosen = selected
        selected_spans = [(1 + i * span, 1 + (i + 1) * span) for i in chosen]
        if level == 1:
            leaves = selected_spans
    expected = {0}
    for start, end in leaves:
        expected.update(range(start, end))
    for start in range(1, count, 4):
        if start + 4 > count:
            expected.update(range(start, count))
    assert route["selected_logical_ids"] == sorted(expected), "leaf/source ownership"
    assert route["selected_fact_ids"] == [ids[i - 1] for i in sorted(expected) if i], (
        "original-ID mapping"
    )


def audit_episode(
    episode: dict[str, Any], checkpoint: dict[str, Any], p: float, *, official: bool = True
) -> dict[str, int]:
    assert episode["reference_hash"] == checkpoint["sha256"], "reference identity"
    assert episode["context"].startswith(
        f"{episode['environment_id']}/seed={episode['seed']}/reset="
    ), "world/frame binding"
    assert (
        f"{episode['environment_id']}/seed={episode['seed']}"
        not in checkpoint["training_contexts"] + checkpoint["validation_contexts"]
    ), "fit/evaluation context overlap"
    assert episode["restart_state_equal"], "restart controller state"
    heads: dict[tuple[int, int], dict[str, Any]] = {}
    originals: list[dict[str, Any]] = []
    previous_available: set[int] = set()
    numerical = 0
    routes_checked = 0
    previous_control: dict[str, Any] = {
        "mission": None,
        "coverage": "",
        "stable_reads": 0,
        "since_attempt": 0,
        "poses": [],
    }
    env = None
    observation = None
    position = (0, 0)
    total_reward = 0.0
    directions = ((1, 0), (0, 1), (-1, 0), (0, -1))
    if official:
        import gymnasium as gym
        import minigrid  # noqa: F401  # Official environment registration only.

        env = gym.make(episode["environment_id"])
        observation, _ = env.reset(seed=episode["seed"])
    try:
        for row in episode["trajectory"]:
            step = row["step"]
            d = row["decision"]
            r = d["dependency"]
            assert (
                r["context_id"] == episode["context"]
                and r["reference_hash"] == checkpoint["sha256"]
            )
            assert d["pose"][:2] == list(position) if official else True, "egomotion"
            if official:
                assert observation is not None
                direction = int(observation["direction"])
                assert d["pose"][2] == direction
                image = observation["image"]
                forward = directions[direction]
                right = directions[(direction + 1) % 4]
                expected = set()
                for vx in range(7):
                    for vy in range(7):
                        obj, color, state = (int(n) for n in image[vx, vy])
                        if obj == 0:
                            continue
                        if (vx, vy) == (3, 6):
                            obj, color, state = 1, 0, 0
                        x = position[0] + forward[0] * (6 - vy) + right[0] * (vx - 3)
                        y = position[1] + forward[1] * (6 - vy) + right[1] * (vx - 3)
                        expected.add((x, y, obj, color, state))
                assert expected == {
                    (f["x"], f["y"], f["object"], f["color"], f["state"])
                    for f in d["current_facts"]
                }, "official partial observation"
            current = {(f["x"], f["y"]): f for f in d["current_facts"]}
            assert all(f["id"] == 0 and f["observed_step"] == step for f in current.values())
            superseded = set()
            for f in row["new_facts"]:
                pos = (f["x"], f["y"])
                previous = heads.get(pos)
                raw = current[pos]
                assert f["id"] == len(originals) + 1 and f["previous"] == (
                    previous["id"] if previous else None
                ), "version chain"
                assert f["observed_step"] == step and all(
                    f[k] == raw[k] for k in ("x", "y", "object", "color", "state")
                ), "observed-only append"
                assert f["first_seen"] == (previous["first_seen"] if previous else step)
                if previous:
                    superseded.add(previous["id"])
                heads[pos] = f
                originals.append(f)
            for pos, raw in current.items():
                assert pos in heads and all(
                    heads[pos][k] == raw[k] for k in ("object", "color", "state")
                ), "current canonical head"
            by_id = {f["id"]: f for f in heads.values()}
            current_ids = [heads[(f["x"], f["y"])]["id"] for f in d["current_facts"]]
            if "recovery_control" in r:
                bits = bytearray(512)
                for x, y in heads:
                    offset = (y + 32) * 64 + x + 32
                    bits[offset // 8] |= 1 << (offset % 8)
                coverage = bytes(bits).hex()
                mission = r["recovery_control"]["mission"]
                if official:
                    assert observation is not None and mission == observation["mission"], (
                        "mission identity"
                    )
                stable = (
                    previous_control["stable_reads"] + 1
                    if previous_control["coverage"] == coverage
                    else 0
                )
                poses = [*previous_control["poses"], d["pose"]][-24:]
                since = previous_control["since_attempt"] + 1
                reason = (
                    "always"
                    if episode["recovery_policy"] == "always"
                    else "new_mission"
                    if mission != previous_control["mission"]
                    else "exploration_stall"
                    if since >= 8
                    and ((stable >= 8 and poses.count(d["pose"]) >= 2) or stable >= 24)
                    else "active_progress"
                )
                expected_control = {
                    "mission": mission,
                    "coverage": coverage,
                    "stable_reads": stable,
                    "since_attempt": 0 if reason != "active_progress" else since,
                    "poses": poses,
                }
                assert (
                    r["recovery_control"] == expected_control and r["recovery_reason"] == reason
                ), "recovery gate/controller state"
                if reason == "active_progress":
                    assert not r["recovered_ids"] and not d["route"], (
                        "deferred recovery performed hidden work"
                    )
                previous_control = expected_control

            assert r["current_ids"] == current_ids
            before = set(r["active_before_recovery"])
            available = set(r["available_ids"])
            recovered = set(r["recovered_ids"])
            assert before <= (previous_available - set(row["retired_ids"]) - superseded) | set(
                current_ids
            ), "hidden cold admission before retrieval"
            assert set(current_ids) <= before, "current perception retention"
            assert available <= before | recovered and recovered.isdisjoint(before), (
                "hidden payload admitted to graph"
            )
            assert available <= set(by_id) and len(available) <= r["active_capacity"]
            assert set(d["memory_ids"]) == set(r["returned_ids"]) <= available, (
                "planner escaped active source set"
            )
            assert all(by_id[f["id"]] == f for f in d["memory_facts"]), "returned source payload"
            assert r["graph_source"] == "active_and_explicitly_recovered_only"
            assert r["work_delta"]["support_graph_build_nodes"] == len(available), (
                "graph did not use exactly available facts"
            )
            if episode["backend"] == "none":
                assert not recovered and not d["route"]
            if episode["backend"] == "zha" and r["recovery_status"] != "budget_exhausted":
                routed = set()
                for route in d["route"]:
                    check_numeric = numerical == 0 and len(by_id) >= 16
                    route_check(
                        route,
                        d["queries"][route["query_index"]],
                        by_id,
                        checkpoint["references"],
                        p,
                        numeric=check_numeric,
                    )
                    numerical += int(check_numeric)
                    routes_checked += 1
                    routed.update(route["selected_fact_ids"])
                assert recovered <= routed, "unrouted cold recovery"
            if episode["backend"] == "exact":
                assert not d["route"]
            previous_available = available
            if official:
                assert env is not None and observation is not None
                action = row["action"]
                assert type(action) is int and 0 <= action <= 6
                if action == 2:
                    front = observation["image"][3, 5]
                    if int(front[0]) in (1, 3, 8) or (int(front[0]) == 4 and int(front[2]) == 0):
                        dx, dy = directions[int(observation["direction"])]
                        position = (position[0] + dx, position[1] + dy)
                observation, reward, done, truncated, _ = env.step(action)
                total_reward += float(reward)
                assert (
                    math.isclose(float(reward), row["reward"], abs_tol=1e-12)
                    and bool(done) == row["terminated"]
                    and bool(truncated) == row["truncated"]
                ), "official action outcome"
                if done or truncated:
                    assert step == len(episode["trajectory"]) - 1
        assert originals == episode["archive"], "immutable archive export"
        result = episode["result"]
        assert result["steps"] == len(episode["trajectory"])
        if official:
            assert math.isclose(result["return"], total_reward, abs_tol=1e-12)
            assert result["success"] == (total_reward > 0 and result["error"] is None)
        return {
            "decisions": len(episode["trajectory"]),
            "routes": routes_checked,
            "numerical_route_cases": numerical,
        }
    finally:
        if env is not None:
            env.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    root = args.results
    report = json.loads((root / "report.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    protocol = json.loads((root / "protocol.json").read_text())
    assert report["complete"] and report["protocol_hash"] == manifest["protocol_hash"] == sha(
        protocol
    )
    for name, checksum in manifest["sources"].items():
        assert (
            hashlib.sha256((root / "source-snapshot" / name).read_bytes()).hexdigest() == checksum
        ), "frozen source identity"
    checkpoints = {}
    for name in ("fixed", "random", "fitted"):
        c = json.loads((root / f"{name}-references.json").read_text())
        checksum = c.pop("sha256")
        assert sha(c) == checksum
        c["sha256"] = checksum
        checkpoints[name] = c
    expected = {
        (condition, env, seed)
        for condition in protocol["conditions"]
        for env in protocol["environments"]
        for seed in protocol["comparison_seeds"]
    }
    actual = {(r["condition"], r["environment"], r["seed"]) for r in report["runs"]}
    assert actual == expected and len(report["runs"]) == len(expected), (
        "incomplete/duplicated comparison cohort"
    )
    stats = {"runs": 0, "decisions": 0, "routes": 0, "numerical_route_cases": 0}
    for run in report["runs"]:
        e = load(root / run["file"], run["sha256"])
        checkpoint = checkpoints[
            {
                "no_recovery": "fixed",
                "always_fixed_zha": "fixed",
                "fixed_zha": "fixed",
                "random_zha": "random",
                "fitted_zha": "fitted",
                "exact": "fixed",
            }[run["condition"]]
        ]
        checked = audit_episode(e, checkpoint, protocol["threshold"])
        stats["runs"] += 1
        for k, v in checked.items():
            stats[k] += v
        assert all(
            run[k] == e["result"][k]
            for k in (
                "success",
                "steps",
                "return",
                "terminated",
                "truncated",
                "external_cutoff",
                "error",
            )
        )
    for summary in report["summary"]:
        runs = [r for r in report["runs"] if r["condition"] == summary["condition"]]
        assert (
            summary["successes"] == sum(r["success"] for r in runs)
            and summary["episodes"] == len(runs)
            and summary["actions"] == sum(r["steps"] for r in runs)
        )
    for d in report["delayed_clue"]:
        trace = load(root / d["file"], d["sha256"])
        for k in (
            "clue_recovered",
            "clue_returned_with_support",
            "superseded_not_returned",
            "original_prefix_unchanged",
            "restored_state_equal",
        ):
            assert trace[k] == d[k]
        assert (
            trace["superseded_not_returned"]
            and trace["original_prefix_unchanged"]
            and trace["restored_state_equal"]
        )
    quality = json.loads((root / "routing-quality.json").read_text())
    corpus = load(root / report["corpus_artifact"]["file"], report["corpus_artifact"]["sha256"])
    fitting = json.loads((root / "fitting.json").read_text())
    for collection in fitting["collections"]:
        source = load(root / collection["file"], collection["sha256"])
        context = f"{collection['environment']}/seed={collection['seed']}"
        wanted = {s["step"]: s for s in corpus if s["context"] == context}
        heads = {}
        for row in source["trajectory"]:
            for f in row["new_facts"]:
                heads[(f["x"], f["y"])] = f
            if row["step"] not in wanted:
                continue
            sample = wanted[row["step"]]
            expected_keys = [[0.0] * 30] + [
                features(f) for f in sorted(heads.values(), key=lambda f: f["id"])
            ]
            assert sample["queries"] == row["decision"]["queries"] and len(sample["keys"]) == len(
                expected_keys
            ), "corpus prefix identity"
            assert all(
                math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)
                for ka, kb in zip(sample["keys"], expected_keys, strict=True)
                for a, b in zip(ka, kb, strict=True)
            ), "corpus keys/future leakage"
    for name in ("training", "validation", "comparison"):
        identities = {s["context"] for s in corpus if s["split"] == name}
        for other in ("training", "validation", "comparison"):
            if name != other:
                assert not identities & {s["context"] for s in corpus if s["split"] == other}, (
                    "corpus context overlap"
                )
    samples = {(s["context"], s["step"]): s for s in corpus if s["split"] == "comparison"}
    mass_cases = 0
    for rows in quality["conditions"].values():
        for row in rows:
            sample = samples[(row["context"], row["step"])]
            q = sample["queries"][row["query"]]
            keys = sample["keys"]
            logits = [oracle.dot(q, k) / math.sqrt(30) for k in keys]
            z = oracle.lse(logits)
            weights = [math.exp(x - z) for x in logits]
            assert math.isclose(
                math.fsum(weights[i] for i in row["selected_ids"]),
                row["retained_mass"],
                rel_tol=1e-9,
                abs_tol=1e-9,
            ), "offline retained mass"
            assert math.isclose(
                math.fsum(sorted(weights, reverse=True)[: len(row["selected_ids"])]),
                row["same_k_oracle_mass"],
                rel_tol=1e-9,
                abs_tol=1e-9,
            )
            mass_cases += 1
    result: dict[str, Any] = {
        "all_passed": True,
        "auditor_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "top_p_roundoff_band": 1e-12,
        **stats,
        "offline_mass_cases": mass_cases,
        "scope": "source/current-head/cold-access lineage, official action replay, up to one independently recomputed affine route case per ZHA episode with a sufficiently large archive read, recorded top-p/leaf ownership, mass and aggregates; not optimizer-trajectory audit or performance certification",
    }
    destination = root / "INDEPENDENT_AUDIT.json"
    if destination.exists():
        previous = json.loads(destination.read_text())
        if previous != result:
            assert {k: v for k, v in previous.items() if k not in ("auditor_sha256", "scope")} == {
                k: v for k, v in result.items() if k not in ("auditor_sha256", "scope")
            }, "existing audit disagrees; preserve prior evidence"
            destination = root / f"INDEPENDENT_AUDIT-{result['auditor_sha256'][:12]}.json"
            if destination.exists():
                assert json.loads(destination.read_text()) == result
            else:
                with destination.open("x") as stream:
                    json.dump(result, stream, indent=2)
                    stream.write("\n")
    else:
        with destination.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
