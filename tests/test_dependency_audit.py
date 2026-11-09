"""Independent state/evidence counterexamples; fixtures are not benchmark results."""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from typing import Any

import pytest

from scripts.audit_complex_tasks import AuditError
from scripts.audit_dependency_memory import (
    WORK_KEYS,
    ReferenceGraph,
    audit_dependency_episode,
    audit_mask,
    audit_planner_view,
    seed_projection,
)


@pytest.fixture(scope="module")
def bundle_trace() -> dict[str, Any]:
    pytest.importorskip("minigrid")
    from research.run_dependency_benchmark import run_episode

    value: dict[str, Any] = json.loads(
        json.dumps(
            run_episode(
                "MiniGrid-MemoryS17Random-v0",
                "bundle_zha",
                0,
                split="unit",
                capacity=96,
                step_cap=6,
            )
        )
    )
    assert value["result"]["error"] is None
    return value


def test_actual_seed_routes_and_whole_bundle_evidence(bundle_trace: dict[str, Any]) -> None:
    before = copy.deepcopy(bundle_trace)
    result = audit_dependency_episode(bundle_trace)
    assert result["dependency_reads_checked"] == 6
    assert result["bundles_checked"] > 0 and result["historical_facts_returned"] > 0
    assert result["unrecorded_work_categories"] == [] and bundle_trace == before
    projected = seed_projection(bundle_trace)
    assert projected["reader"] == "zha_adaptive"
    assert (
        projected["trajectory"][0]["decision"]["memory_ids"]
        == bundle_trace["trajectory"][0]["decision"]["dependency"]["seed_ids"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "mask_unseen",
        "mask_label",
        "mask_version",
        "mask_hash",
        "mask_bounds",
        "mask_binary_bytes",
        "mask_transport_cost",
        "context",
        "stale_head",
        "unselected_seed",
        "path_edge",
        "ordered_path",
        "halo",
        "prerequisite",
        "semantic_support",
        "current_exemption",
        "historical_exemption",
        "missing_return",
        "false_complete",
        "hidden_residual",
        "scan_work",
        "bfs_work",
        "global_claim",
        "output_payload",
    ],
)
def test_false_evidence_rejected(bundle_trace: dict[str, Any], mutation: str) -> None:
    episode = copy.deepcopy(bundle_trace)
    decision = episode["trajectory"][0]["decision"]
    receipt = decision["dependency"]
    bundle = receipt["bundles"][0]
    if mutation == "mask_unseen":
        bits = bytearray.fromhex(decision["coverage"]["bits_hex"])
        bits[0] ^= 1
        decision["coverage"]["bits_hex"] = bits.hex()
    elif mutation == "mask_label":
        decision["coverage"]["passability"] = [1]
    elif mutation == "mask_version":
        decision["coverage"]["version"] += 1
    elif mutation == "mask_hash":
        decision["coverage"]["head_hash"] = "0" * 64
    elif mutation == "mask_bounds":
        decision["coverage"]["origin"][0] += 1
    elif mutation == "mask_binary_bytes":
        decision["coverage"]["binary_bytes"] = 511
    elif mutation == "mask_transport_cost":
        receipt["work_delta"]["coverage_json_bytes"] -= 1
    elif mutation == "context":
        receipt["context"]["position"][0] += 1
    elif mutation == "stale_head":
        receipt["source_head_ids"].append(99999)
    elif mutation == "unselected_seed":
        bundle["seed_id"] = 99999
    elif mutation == "path_edge":
        bundle["support_edges"].append([1, 99999])
    elif mutation == "ordered_path":
        bundle["paths"][0].append(99999)
    elif mutation == "halo":
        bundle["halo_ids"].append(99999)
    elif mutation == "prerequisite":
        bundle["prerequisite_ids"].append(99999)
    elif mutation == "semantic_support":
        bundle["semantic_support_ids"].append(99999)
    elif mutation == "current_exemption":
        bundle["current_support_ids"] = []
    elif mutation == "historical_exemption":
        bundle["historical_ids"].append(99999)
    elif mutation == "missing_return":
        receipt["returned_ids"].append(99999)
    elif mutation == "false_complete":
        bundle["status"] = "overbudget"
    elif mutation == "hidden_residual":
        receipt["residual_known_neighbor_omissions"].append([0, 0, 99, 99, 99999])
    elif mutation == "scan_work":
        receipt["work_delta"]["head_scan_items"] += 1
    elif mutation == "bfs_work":
        receipt["work_delta"]["bfs_nodes"] += 1
    elif mutation == "global_claim":
        receipt["closure_scope"] = "complete global map"
    elif mutation == "output_payload":
        later = next(r for r in episode["trajectory"] if r["decision"]["memory_facts"])
        later["decision"]["memory_facts"][0]["object"] = 9
    with pytest.raises(AuditError):
        audit_dependency_episode(episode)


def graph_fixture(
    cells: list[tuple[int, int, int, int, int]], held: list[int] | None = None
) -> tuple[ReferenceGraph, list[dict[str, Any]], dict[str, Any]]:
    facts = [
        {
            "id": i + 1,
            "x": x,
            "y": y,
            "object": obj,
            "color": color,
            "state": state,
            "first_seen": 0,
            "observed_step": 0,
            "previous": None,
            "cue": False,
        }
        for i, (x, y, obj, color, state) in enumerate(cells)
    ]
    context = {
        "position": [0, 0],
        "direction": 0,
        "mission": "go to the goal",
        "inventory": held,
        "step": 0,
        "current_facts": [{**f, "id": 0} for f in facts],
    }
    return ReferenceGraph(facts, context, dict.fromkeys(WORK_KEYS, 0)), facts, context


def test_feasible_unlocked_detour_precedes_false_lock_dependency() -> None:
    pytest.importorskip("minigrid")
    from research.dependency_memory import ObservedGraph
    from research.minigrid_benchmark import Fact, ReadContext

    cells = [
        (0, 0, 1, 0, 0),
        (1, 0, 4, 0, 2),
        (2, 0, 8, 0, 0),
        (0, 1, 1, 0, 0),
        (1, 1, 1, 0, 0),
        (2, 1, 1, 0, 0),
    ]
    reference, facts, context = graph_fixture(cells)
    expected = reference.bundle(3, "goal_landmark")
    assert expected["missing"] == [] and 2 not in expected["path_ids"]
    observed = [Fact(**f) for f in facts]
    ctx = ReadContext(
        (0, 0), 0, context["mission"], None, tuple(Fact(**f) for f in context["current_facts"]), 0
    )
    actual = asdict(
        ObservedGraph(observed, ctx, dict.fromkeys(WORK_KEYS, 0)).bundle(
            observed[2], "goal_landmark"
        )
    )
    assert json.loads(json.dumps(actual)) == expected


def test_key_behind_own_lock_is_not_accessible_support() -> None:
    reference, _, _ = graph_fixture(
        [(0, 0, 1, 0, 0), (1, 0, 4, 0, 2), (2, 0, 1, 0, 0), (3, 0, 8, 0, 0), (2, 1, 5, 0, 0)]
    )
    bundle = reference.bundle(4, "goal_landmark")
    assert (
        bundle["missing"] == ["unreachable_matching_key:2:0"] and bundle["prerequisite_ids"] == []
    )
    with_key, _, _ = graph_fixture(
        [(0, 0, 1, 0, 0), (1, 0, 4, 0, 2), (2, 0, 1, 0, 0), (3, 0, 8, 0, 0)], held=[5, 0]
    )
    assert with_key.bundle(4, "goal_landmark")["missing"] == []


def test_unseen_gap_is_not_a_route() -> None:
    reference, _, _ = graph_fixture([(0, 0, 1, 0, 0), (2, 0, 8, 0, 0)])
    assert reference.bundle(2, "goal_landmark")["missing"] == ["no_observed_route"]


def test_mask_cannot_supply_navigation_through_unreturned_cell() -> None:
    start = {"id": 0, "x": 0, "y": 0, "object": 1, "state": 0, "color": 0}
    target = {"id": 2, "x": 2, "y": 0, "object": 8, "state": 0, "color": 0}
    decision = {
        "pose": [0, 0, 0],
        "inventory": None,
        "memory_ids": [2],
        "memory_facts": [target],
        "current_facts": [start],
        "plan": [[0, 0], [1, 0], [2, 0]],
        "goal_sources": [2],
        "plan_fact_ids": [2],
        "coverage": {"bits_hex": "ff" * 512},
    }
    with pytest.raises(AuditError, match="mask-only"):
        audit_planner_view(decision)


def test_coverage_commits_version_but_never_encodes_labels(bundle_trace: dict[str, Any]) -> None:
    row = bundle_trace["trajectory"][0]
    heads = sorted(row["new_facts"], key=lambda f: f["id"])
    mask = row["decision"]["coverage"]
    assert (
        audit_mask(mask, heads, len(heads))
        == row["decision"]["dependency"]["work_delta"]["coverage_json_bytes"]
    )
    changed = copy.deepcopy(heads)
    changed[0]["object"] = 9
    with pytest.raises(AuditError, match="head/version"):
        audit_mask(mask, changed, len(heads))


def test_strong_flat_history_control_reclaims_current_duplicate_slots() -> None:
    pytest.importorskip("minigrid")
    from research.run_dependency_benchmark import run_episode

    episode: dict[str, Any] = json.loads(
        json.dumps(
            run_episode(
                "MiniGrid-MemoryS17Random-v0",
                "flat_exact_history_mask",
                0,
                split="unit",
                capacity=96,
                step_cap=5,
            )
        )
    )
    assert audit_dependency_episode(episode)["unrecorded_work_categories"] == []
    for row in episode["trajectory"]:
        visible = {(f["x"], f["y"]) for f in row["decision"]["current_facts"]}
        assert all((f["x"], f["y"]) not in visible for f in row["decision"]["memory_facts"])
        assert len(row["decision"]["memory_ids"]) <= 96
    assert seed_projection(episode)["capacity"] == 145


def test_unreachable_landmark_is_explicitly_rejected_not_silently_dropped() -> None:
    reference, _, _ = graph_fixture([(0, 0, 1, 0, 0), (2, 0, 8, 0, 0)])
    assert (2, "goal_landmark") in reference.nominate([1, 2])
    legacy, _, _ = graph_fixture([(0, 0, 1, 0, 0), (2, 0, 8, 0, 0)])
    assert (2, "goal_landmark") not in legacy.nominate([1, 2], modern=False)


def test_common_planner_ignores_reader_action_and_goal_receipt() -> None:
    pytest.importorskip("minigrid")
    import numpy as np

    from research.minigrid_benchmark import Fact, ObservationPlanner, ReadContext

    image = np.zeros((7, 7, 3), dtype=np.uint8)
    image[3, 6] = [1, 0, 0]
    image[3, 5] = [1, 0, 0]
    obs = {"image": image, "direction": 0, "mission": "go to the goal"}
    expected, _, _ = ObservationPlanner("none", 8).act(obs)

    class ReceiptCanary:
        costs: dict[str, int | float] = {}

        def observe(self, visible: list[Fact]) -> list[Fact]:
            return []

        def select_with_context(
            self, queries: Any, context: ReadContext
        ) -> tuple[list[Fact], list[dict[str, Any]], dict[str, Any], None]:
            return (
                [],
                [],
                {"action": (expected + 1) % 3, "goal": [99, 99], "plan": [[99, 99]]},
                None,
            )

        def archive(self) -> list[dict[str, Any]]:
            return []

    actual, decision, _ = ObservationPlanner("none", 8, injected_reader=ReceiptCanary()).act(obs)
    assert actual == expected and decision["goal"] != [99, 99]
    assert decision["plan"] != [[99, 99]] and decision["memory_ids"] == []
