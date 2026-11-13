"""Post-hoc planning interventions using only each recorded observed prefix.

The shared symbolic planner is reused for functional probes; this is a
local source-availability diagnosis, not an independent policy certificate.
"""

from __future__ import annotations

import argparse
from collections import Counter, deque
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.minigrid_benchmark import Fact, KnownCoverage, ObservationPlanner
from research.replay_dashboard import read_json
from research.run_persistent_tasks import save_json
from research.task_references import digest


def inspect_episode(episode: dict[str, Any]) -> dict[str, Any]:
    heads: dict[tuple[int, int], Fact] = {}
    counts: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    actor = ObservationPlanner("none")
    for row in episode["trajectory"]:
        d = row["decision"]
        r = d["dependency"]
        for raw in row["new_facts"]:
            f = Fact(**raw)
            if f.observed_step != row["step"] or f.previous != (
                heads[f.position].id if f.position in heads else None
            ):
                raise ValueError("invalid observed prefix/correction")
            heads[f.position] = f
        by_id = {f.id: f for f in heads.values()}
        if not set(r["available_ids"]) <= set(by_id):
            raise ValueError("unknown/future active source")
        if any(by_id.get(f["id"]) != Fact(**f) for f in d["memory_facts"]):
            raise ValueError("returned payload differs from current prefix")
        bits = bytearray(512)
        for f in heads.values():
            k = (f.y + 32) * 64 + f.x + 32
            bits[k // 8] |= 1 << (k % 8)
        coverage = KnownCoverage(
            bytes(bits), r["source_version"], digest([asdict(f) for f in heads.values()])
        )
        actor.position = tuple(d["pose"][:2])
        actor.direction = d["pose"][2]
        actor.recent = deque(map(tuple, d["recent_history"]), maxlen=16)
        current = [Fact(**f) for f in d["current_facts"]]
        mission = row["observation"]["mission"]
        plans = {}
        views = {
            "full": list(heads.values()),
            "active": [by_id[i] for i in r["available_ids"]],
            "returned": [Fact(**f) for f in d["memory_facts"]],
        }
        for label, facts in views.items():
            view = {f.position: f for f in facts}
            view.update({f.position: f for f in current})
            plans[label] = actor._plan(
                view,
                tuple(d["inventory"]) if d["inventory"] else None,
                mission,
                known_coverage=coverage,
            )
        if plans["returned"][1] != d["objective"] or plans["returned"][0] != row["action"]:
            raise ValueError("recorded planner replay mismatch")
        counts["decisions"] += 1
        if d["objective"] == "scan-no-reachable-frontier":
            category = (
                "full_observed_support_still_stalls"
                if plans["full"][1] == d["objective"]
                else "active_support_gap"
                if plans["active"][1] == d["objective"]
                else "packing_gap"
            )
            counts[category] += 1
            if len(examples) < 8 and category != "full_observed_support_still_stalls":
                full_path = plans["full"][4]
                examples.append(
                    {
                        "step": row["step"],
                        "category": category,
                        "counterfactual_objective": plans["full"][1],
                        "full_path_ids": [heads[p].id for p in full_path],
                        "inactive_path_ids": [
                            heads[p].id for p in full_path if heads[p].id not in r["available_ids"]
                        ],
                        "scope": "same-state observed-prefix intervention; not a complete alternate episode",
                    }
                )
    return {"counts": dict(counts), "examples": examples}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    report = read_json(args.source / "report.json")
    rows = []
    for r in report["runs"]:
        if r["condition"] != "parent":
            continue
        e = read_json(args.source / r["file"], r["sha256"])
        rows.append(
            {
                "environment": r["environment"],
                "seed": r["seed"],
                "success": r["success"],
                "source_sha256": r["sha256"],
                **inspect_episode(e),
            }
        )
    total: Counter[str] = Counter()
    for r in rows:
        total.update(r["counts"])
    save_json(
        args.output,
        {
            "source_report": digest(report),
            "counts": dict(total),
            "episodes": rows,
            "scope": "post-hoc diagnosis of exposed parent-policy traces; full observed prefixes only; shared planner probes are not fresh evaluation",
        },
    )
    print(dict(total))


if __name__ == "__main__":
    main()
