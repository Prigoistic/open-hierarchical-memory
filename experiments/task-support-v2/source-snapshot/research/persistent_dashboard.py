"""Presentation adapter for persistent task runs, without changing read decisions.

Fresh solves retain one local SQLite archive per reset. Saved experimental traces
are adapted in memory only; their frozen files and source identities stay intact.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from research.minigrid_benchmark import serial_observation
from research.persistent_task_memory import Backend, RecoveryPolicy
from research.run_minigrid_benchmark import environment
from research.run_persistent_tasks import persistent_episode
from research.task_memory.run_study import run as run_support_study
from research.task_memory.run_repairs import run as run_support_repairs
from research.task_references import GEOMETRY, RouterCheckpoint, digest

ROOT = Path(__file__).resolve().parents[1]
DATASET = "persistent-task-v2"
# UI method -> original frozen condition, checkpoint, archive reader, recovery schedule.
METHODS: dict[str, tuple[str, str, Backend, RecoveryPolicy]] = {
    "persistent_zha": ("fitted_zha", "fitted", "zha", "on_stall"),
    "persistent_fixed": ("fixed_zha", "fixed", "zha", "on_stall"),
    "persistent_random": ("random_zha", "random", "zha", "on_stall"),
    "persistent_always": ("always_fixed_zha", "fixed", "zha", "always"),
    "persistent_exact": ("exact", "fixed", "exact", "on_stall"),
    "persistent_none": ("no_recovery", "fixed", "none", "on_stall"),
}

METHODS.update(
    {
        "persistent_support_" + condition: (
            "support_" + condition,
            "fitted",
            "exact"
            if condition.endswith("exact")
            else "none"
            if condition.endswith("graph")
            else "zha",
            "on_stall",
        )
        for condition in (
            "parent",
            "compact",
            "connected_zha",
            "connected_exact",
            "connected_graph",
            "repaired_zha",
            "repaired_exact",
            "repaired_graph",
        )
    }
)


def active_capacity_for(method: str) -> int:
    if method not in METHODS:
        raise ValueError("unsupported persistent method")
    return 64 if method.startswith("persistent_support_") else 96


def checkpoint_for(method: str, root: Path = ROOT) -> RouterCheckpoint:
    name = METHODS[method][1]
    return RouterCheckpoint.load(root / "experiments" / DATASET / f"{name}-references.json")


class PersistentTrace:
    """Owned UI rows and deduplicated routing banks tied to original source IDs."""

    def __init__(self, method: str) -> None:
        self.method = method
        self.heads: dict[tuple[int, int], dict[str, Any]] = {}
        self.next_step = 0
        self.previous_active: set[int] = set()
        self.snapshots: dict[str, Any] = {}
        self.events: dict[str, Any] = {}

    def row(self, original: dict[str, Any]) -> dict[str, Any]:
        row = copy.deepcopy(original)
        if row["step"] != self.next_step:
            raise ValueError("noncontiguous persistent evidence")
        heads = self.heads.copy()
        for fact in row["new_facts"]:
            if fact["observed_step"] > row["step"] or fact["id"] <= 0:
                raise ValueError("future or invalid persistent source")
            heads[(fact["x"], fact["y"])] = fact
        ids_in_prefix = {f["id"] for f in heads.values()}
        decision = row["decision"]
        receipt = decision["dependency"]
        if receipt.get("graph_source") != "active_and_explicitly_recovered_only":
            raise ValueError("persistent evidence has an unsupported support boundary")
        if len(receipt["available_ids"]) > receipt["active_capacity"]:
            raise ValueError("persistent trace exceeds its active capacity")
        if (
            not set(receipt["available_ids"]) <= ids_in_prefix
            or not set(receipt["recovered_ids"]) <= set(receipt["available_ids"])
            or decision["memory_ids"] != receipt["returned_ids"]
            or not set(decision["memory_ids"]) <= set(receipt["available_ids"])
        ):
            raise ValueError("persistent read escaped its observed/active boundary")
        refs = []
        for raw in decision["route"]:
            # Budget failures are explicit in the receipt, never a made-up hierarchy.
            if raw.get("status") == "budget_exhausted":
                continue
            route = copy.deepcopy(raw)
            ids = route.pop("index_fact_ids")
            if (
                ids != sorted(ids_in_prefix)
                or len(ids) != len(set(ids))
                or any(type(i) is not int or i <= 0 for i in ids)
            ):
                raise ValueError("invalid archive source mapping")
            if any(i not in ids for i in route["selected_fact_ids"]):
                raise ValueError("attended fact outside its archive snapshot")
            # The core's complete-chunk layout is deterministic. These extents
            # describe existing nodes; no summary scores or edges are invented.
            layout = {
                "index_fact_ids": ids,
                "node_spans": [
                    {
                        "level": level,
                        "index": i,
                        "start": 1 + i * GEOMETRY.chunk_size**level,
                        "stop": 1 + (i + 1) * GEOMETRY.chunk_size**level,
                    }
                    for level in range(1, GEOMETRY.depth + 1)
                    for i in range(len(ids) // GEOMETRY.chunk_size**level)
                ],
                "chunk_size": GEOMETRY.chunk_size,
                "depth": GEOMETRY.depth,
                "logical_key_count": len(ids) + 1,
                "source_snapshot_label": route["snapshot_id"],
                "span_provenance": "complete-chunk extents from declared geometry",
            }
            for step in route["steps"]:
                extents = {s["index"] for s in layout["node_spans"] if s["level"] == step["level"]}
                if not set(step["candidates"]) <= extents:
                    raise ValueError("route refers to an absent summary node")
            snapshot_id = digest(layout)
            self.snapshots[snapshot_id] = layout
            route.update(
                snapshot_id=snapshot_id, attempt=0, p=0.8, used=True, decision_source=self.method
            )
            ref = digest(route)
            self.events[ref] = route
            refs.append({"route_ref": ref})
        decision["route"] = refs
        active = set(receipt["available_ids"])
        # Observation admission may evict payloads before the read receipt starts.
        # Derive that visible state transition, excluding corrected source versions.
        removed = (self.previous_active - active) & ids_in_prefix
        retired = set(row.get("retired_ids", []))
        row["lifecycle"] = {
            "capacity_evicted_ids": sorted((removed - retired) | set(receipt["evicted_ids"])),
            "age_retired_ids": sorted(retired),
            "superseded_active_ids": sorted(self.previous_active - ids_in_prefix),
            "provenance": "adjacent published active sets plus explicit retirement/read receipts",
        }
        self.previous_active = active
        self.heads, self.next_step = heads, self.next_step + 1
        return row


def adapt_recorded(value: dict[str, Any], method: str) -> dict[str, Any]:
    result = copy.deepcopy(value)
    trace = PersistentTrace(method)
    rows = value["trajectory"]
    if len(rows) > 1024:
        raise ValueError("saved persistent solve exceeds the viewer step limit")
    # Original v2 traces retain actions, not image arrays. Reconstruct actual
    # egocentric observations with official action replay, never from a hidden map.
    if rows and "observation" not in rows[0]:
        env = environment(value["environment_id"])
        try:
            obs, _ = env.reset(seed=value["seed"])
            rebuilt = []
            for original in rows:
                row = copy.deepcopy(original)
                row["observation"] = serial_observation(obs)
                obs, reward, ended, truncated, _ = env.step(row["action"])
                if (float(reward), bool(ended), bool(truncated)) != (
                    row["reward"],
                    row["terminated"],
                    row["truncated"],
                ):
                    raise ValueError("saved task action replay differs from its source")
                rebuilt.append(row)
            rows = rebuilt
        finally:
            env.close()
        result["observation_provenance"] = "official environment replay of saved actions"
    result["trajectory"] = [trace.row(row) for row in rows]
    result.update(
        reader=method,
        capacity=value.get("workspace", {}).get("capacity", 96),
        split="diagnostic",
        routing_snapshots=trace.snapshots,
        routing_events=trace.events,
    )
    return result


def run_solve(
    environment: str,
    method: str,
    seed: int,
    *,
    path: Path,
    checkpoint: RouterCheckpoint,
    step_cap: int,
    on_step: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], None],
) -> dict[str, Any]:
    _, _, backend, policy = METHODS[method]
    path.parent.mkdir(parents=True, exist_ok=False)
    checkpoint.save(path.parent / "references.json")
    trace = PersistentTrace(method)

    def publish(row: dict[str, Any]) -> None:
        packet = trace.row(row)
        on_step(packet, trace.snapshots, trace.events)

    if method.startswith("persistent_support_"):
        support_runner = (
            run_support_repairs
            if method.startswith("persistent_support_repaired_")
            else run_support_study
        )
        result = support_runner(
            method.removeprefix("persistent_support_"),
            path,
            environment,
            seed,
            checkpoint,
            cap=step_cap,
            on_step=publish,
        )
    else:
        result = persistent_episode(
            path,
            environment,
            seed,
            checkpoint,
            backend,
            step_cap,
            recovery_policy=policy,
            on_step=publish,
        )
    result["memory"] = {
        "archive_id": path.parent.name,
        "originals": len(result["archive"]),
        "active": len(result["active_ids"]),
        "active_capacity": active_capacity_for(method),
        "restart_state_equal": result["restart_state_equal"],
        "reference_kind": checkpoint.kind,
        "reference_hash": checkpoint.sha256,
        "costs": result["costs"],
    }
    # Small completion record, no simulator-resume claim or imagined writeback.
    with (path.parent / "result.json").open("x") as stream:
        json.dump(
            {
                "environment": environment,
                "seed": seed,
                "method": method,
                "result": result["result"],
                "memory": result["memory"],
            },
            stream,
            allow_nan=False,
            indent=2,
        )
    return result
