"""Independent observed-source / connector / official-action evidence checks.

Does not import production reader, packing, feature or planner code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from scripts.audit_persistent_tasks import audit_episode as audit_parent
from scripts.audit_persistent_tasks import load, route_check, sha

DIRECTIONS = ((1, 0), (0, 1), (-1, 0), (0, -1))


def audit_episode(
    e: dict[str, Any], checkpoint: dict[str, Any], *, official: bool = True
) -> dict[str, int]:
    if e["condition"] == "parent":
        return audit_parent(e, checkpoint, 0.8, official=official)
    assert e["reference_hash"] == checkpoint["sha256"] and e["restart_state_equal"]
    assert (
        f"{e['environment_id']}/seed={e['seed']}"
        not in checkpoint["training_contexts"] + checkpoint["validation_contexts"]
    )
    heads: dict[tuple[int, int], dict[str, Any]] = {}
    originals: list[dict[str, Any]] = []
    previous: set[int] = set()
    pos = (0, 0)
    reward_sum = 0.0
    numeric = 0
    routes = 0
    connectors = 0
    env = None
    obs = None
    if official:
        import gymnasium as gym
        import minigrid  # noqa: F401

        env = gym.make(e["environment_id"])
        obs, _ = env.reset(seed=e["seed"])
        initial: Any = env.unwrapped
        assert (
            sha(
                [
                    e["environment_id"],
                    initial.grid.encode().tolist(),
                    list(map(int, initial.agent_pos)),
                    int(initial.agent_dir),
                    obs["mission"],
                ]
            )
            == e["evaluator_layout_identity"]
        )
    try:
        for row in e["trajectory"]:
            d = row["decision"]
            r = d["dependency"]
            step = row["step"]
            assert r["context_id"] == e["context"] and r["reference_hash"] == checkpoint["sha256"]
            if official:
                assert obs is not None and d["pose"] == [*pos, int(obs["direction"])]
                dr = int(obs["direction"])
                fwd = DIRECTIONS[dr]
                right = DIRECTIONS[(dr + 1) % 4]
                expected = set()
                for x in range(7):
                    for y in range(7):
                        ob, col, st = map(int, obs["image"][x, y])
                        if ob == 0:
                            continue
                        if (x, y) == (3, 6):
                            ob, col, st = 1, 0, 0
                        expected.add(
                            (
                                pos[0] + fwd[0] * (6 - y) + right[0] * (x - 3),
                                pos[1] + fwd[1] * (6 - y) + right[1] * (x - 3),
                                ob,
                                col,
                                st,
                            )
                        )
                assert expected == {
                    (f["x"], f["y"], f["object"], f["color"], f["state"])
                    for f in d["current_facts"]
                }, "official observation"
            current = {(f["x"], f["y"]): f for f in d["current_facts"]}
            superseded = set()
            for f in row["new_facts"]:
                point = f["x"], f["y"]
                old = heads.get(point)
                assert f["id"] == len(originals) + 1 and f["previous"] == (
                    old["id"] if old else None
                )
                assert f["first_seen"] == (old["first_seen"] if old else step)
                assert f["observed_step"] == step and all(
                    f[k] == current[point][k] for k in ("object", "color", "state")
                )
                if old:
                    superseded.add(old["id"])
                heads[point] = f
                originals.append(f)
            by_id = {f["id"]: f for f in heads.values()}
            current_ids = [heads[f["x"], f["y"]]["id"] for f in d["current_facts"]]
            assert current_ids == r["current_ids"]
            assert all(
                all(heads[p][k] == f[k] for k in ("object", "color", "state"))
                and f["observed_step"] == step
                and f["id"] == 0
                for p, f in current.items()
            )
            before = set(r["active_before_recovery"])
            available = set(r["available_ids"])
            cold = set(r["recovered_ids"])
            returned = set(r["returned_ids"])
            assert before <= (previous - set(row["retired_ids"]) - superseded) | set(current_ids), (
                "hidden pre-recovery payload"
            )
            assert set(current_ids) <= before and set(current_ids) <= available
            assert (
                available <= before | cold and available <= set(by_id) and cold.isdisjoint(before)
            )
            assert (
                len(available) <= e["workspace"]["capacity"]
                and len(cold) <= e["workspace"]["recovery_limit"]
            )
            assert returned == set(d["memory_ids"]) <= available and all(
                by_id[f["id"]] == f for f in d["memory_facts"]
            )
            routed = set()
            for route in d["route"]:
                if route.get("status") == "budget_exhausted":
                    assert not r["connector"]["attempted"]
                    continue
                check = numeric == 0 and len(by_id) >= 16
                route_check(
                    route,
                    d["queries"][route["query_index"]],
                    by_id,
                    checkpoint["references"],
                    0.8,
                    numeric=check,
                )
                numeric += int(check)
                routes += 1
                routed.update(route["selected_fact_ids"])
            connector = r["connector"]
            if connector["attempted"]:
                connectors += 1
                assert connector["source_ids"] == sorted(by_id), "connector source prefix"
                seeds = set(connector["seed_ids"])
                assert seeds <= before | routed if e["backend"] == "zha" else seeds == set(by_id)
                assert set(connector["recovered_ids"]) == cold, "connector cold provenance"
            elif e["backend"] == "zha":
                assert cold <= routed, "unrouted cold admission"
            else:
                assert e["backend"] != "none" or not cold
            complete = set()
            for b in r["bundles"]:
                assert b["seed_id"] in by_id
                required = (
                    {b["seed_id"]}
                    | set(b["path_ids"])
                    | set(b["prerequisite_ids"])
                    | set(b["semantic_support_ids"])
                )
                assert required == set(b["required_ids"]) <= set(by_id), "compact support union"
                if b["status"] != "complete":
                    continue
                if b["kind"] == "waypoint":
                    assert e.get("progress_repairs") and r["progress_repairs"], (
                        "undeclared repair policy"
                    )
                    assert b["seed_id"] == r["waypoint_id"] and b["seed_id"] in returned, (
                        "waypoint admission"
                    )
                    original = next(
                        (
                            x
                            for x in r["bundles"]
                            if x["seed_id"] == b["requested_seed_id"]
                            and x["status"] == "overbudget"
                        ),
                        None,
                    )
                    assert original is not None and len(b["paths"]) == 1, "waypoint origin"
                    prefix = b["paths"][0]
                    assert len(prefix) >= 2 and original["paths"][0][: len(prefix)] == prefix, (
                        "waypoint prefix"
                    )
                    assert b["seed_id"] == prefix[-1], "waypoint endpoint"
                assert not b["missing"]
                for path in b["paths"]:
                    if path:
                        assert (by_id[path[0]]["x"], by_id[path[0]]["y"]) == tuple(d["pose"][:2]), (
                            "path origin"
                        )
                    for a, z in zip(path, path[1:], strict=False):
                        f, g = by_id[a], by_id[z]
                        assert abs(f["x"] - g["x"]) + abs(f["y"] - g["y"]) == 1, "path edge"
                    assert all(by_id[i]["object"] in (1, 3, 4, 8) for i in path), (
                        "path traversability"
                    )
                assert set(b["historical_ids"]) == required - set(current_ids)
                assert set(b["path_ids"]) == {i for path in b["paths"] for i in path}, "path union"
                assert {tuple(edge) for edge in b["support_edges"]} == {
                    tuple(edge) for path in b["paths"] for edge in zip(path, path[1:], strict=False)
                }, "support edges"
                for i in b["path_ids"]:
                    door = by_id[i]
                    if door["object"] == 4 and door["state"] == 2:
                        held = (
                            d["inventory"] is not None
                            and d["inventory"][0] == 5
                            and d["inventory"][1] == door["color"]
                        )
                        assert held or any(
                            by_id[k]["object"] == 5 and by_id[k]["color"] == door["color"]
                            for k in b["prerequisite_ids"]
                        ), "locked-door prerequisite"
                complete.update(b["historical_ids"])
            assert complete == returned, "packed bundle union"
            if e.get("progress_repairs"):
                admitted = {(by_id[i]["x"], by_id[i]["y"]): by_id[i] for i in returned}
                admitted.update(current)
                assert all(tuple(p) in admitted for p in d["plan"]), "planner used unadmitted path"
                if row["action"] == 3:
                    assert d["inventory"] is None, "pickup with occupied hands"
                if d["objective"] == "follow-observed-waypoint":
                    assert r["waypoint_id"] in returned and d["goal_sources"] == [
                        r["waypoint_id"]
                    ], "planner waypoint source"
            previous = available
            if official:
                assert obs is not None and env is not None
                action = row["action"]
                assert type(action) is int and 0 <= action <= 6
                if action == 2:
                    front = obs["image"][3, 5]
                    if int(front[0]) in (1, 3, 8) or (int(front[0]) == 4 and int(front[2]) == 0):
                        dx, dy = DIRECTIONS[int(obs["direction"])]
                        pos = (pos[0] + dx, pos[1] + dy)
                obs, reward, done, trunc, _ = env.step(action)
                reward_sum += float(reward)
                assert (
                    math.isclose(float(reward), row["reward"], abs_tol=1e-12)
                    and bool(done) == row["terminated"]
                    and bool(trunc) == row["truncated"]
                ), "official action"
                if done or trunc:
                    assert step == len(e["trajectory"]) - 1
        assert originals == e["archive"] and e["result"]["steps"] == len(e["trajectory"])
        if official:
            assert math.isclose(e["result"]["return"], reward_sum, abs_tol=1e-12)
            assert e["result"]["success"] == (reward_sum > 0 and e["result"]["error"] is None)
        return {
            "decisions": len(e["trajectory"]),
            "routes": routes,
            "numerical_route_cases": numeric,
            "connector_reads": connectors,
        }
    finally:
        if env is not None:
            env.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results", type=Path, required=True)
    args = p.parse_args()
    root = args.results
    report = json.loads((root / "report.json").read_text())
    protocol = json.loads((root / "protocol.json").read_text())
    manifest = json.loads((root / "manifest.json").read_text())
    checkpoint = json.loads((root / "references.json").read_text())
    assert report["complete"] and report["protocol_hash"] == manifest["protocol_hash"] == sha(
        protocol
    )
    assert checkpoint["sha256"] == sha({k: v for k, v in checkpoint.items() if k != "sha256"})
    for name, checksum in manifest["sources"].items():
        assert (
            hashlib.sha256((root / "source-snapshot" / name).read_bytes()).hexdigest() == checksum
        ), "source snapshot"
    expected = {
        (c, e, s)
        for c in protocol["conditions"]
        for e in protocol["environments"]
        for s in protocol["comparison_seeds"]
    }
    actual = {(r["condition"], r["environment"], r["seed"]) for r in report["runs"]}
    assert actual == expected and len(report["runs"]) == len(expected), "cohort coverage"
    counts = {
        "runs": 0,
        "decisions": 0,
        "routes": 0,
        "numerical_route_cases": 0,
        "connector_reads": 0,
    }
    for row in report["runs"]:
        episode = load(root / row["file"], row["sha256"])
        assert (
            episode["result"] == {k: row[k] for k in episode["result"]}
            and episode["workspace"] == protocol["workspace"]
        )
        stats = audit_episode(episode, checkpoint)
        for k, v in stats.items():
            counts[k] += v
        counts["runs"] += 1
    result = {
        "all_passed": True,
        **counts,
        "scope": "official actions, observed/correction/source/capacity lineage, connector seed origins, packed path edges and sampled scalar routing; not a full policy or semantic proof",
    }
    path = root / "INDEPENDENT_AUDIT.json"
    if path.exists():
        assert json.loads(path.read_text()) == result
    else:
        path.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
