"""Real small core traces and state/evidence counterexamples, not benchmark claims."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from scripts.audit_complex_tasks import AuditError, digest, mini_queries
from scripts.audit_progress_retrieval import TreeOracle, audit_episode, expand_wire


@pytest.fixture(scope="module")
def trace() -> dict[str, Any]:
    pytest.importorskip("minigrid")
    from research.run_progress_benchmark import run_episode

    value: dict[str, Any] = json.loads(
        json.dumps(
            run_episode("MiniGrid-MemoryS17Random-v0", "progress_zha", 0, split="unit", step_cap=4)
        )
    )
    assert value["result"]["error"] is None
    return value


def test_real_compact_trace_and_independent_affine_route_oracle(trace: dict[str, Any]) -> None:
    before = copy.deepcopy(trace)
    result = audit_episode(trace)
    assert result["repair_reads_checked"] == 4 and result["hierarchy_routes_checked"] > 0
    assert result["outcome_attribution"] == "no_graph_repair" and result["graph_reads"] == 0
    assert trace == before


@pytest.mark.parametrize(
    "mutation",
    [
        "stage",
        "trigger",
        "history",
        "novelty",
        "streak",
        "fallback",
        "source",
        "budget",
        "cue",
        "cue_used",
        "attempt",
        "repair_cost",
        "source_cost",
        "mask_header",
        "bank_hash",
        "bank_bytes",
    ],
)
def test_false_progress_and_attribution_rejected(trace: dict[str, Any], mutation: str) -> None:
    e = copy.deepcopy(trace)
    d = e["trajectory"][0]["decision"]
    r = d["repair"]
    if mutation == "stage":
        r["stage"] = 3
    elif mutation == "trigger":
        r["trigger"] = "hard_no_information_limit"
    elif mutation == "history":
        r["history"].append([99, 99, 0])
    elif mutation == "novelty":
        r["novel_observed_ids"] = [99999]
    elif mutation == "streak":
        r["no_information_reads"] = 48
    elif mutation == "fallback":
        r["fallback_active"] = True
    elif mutation == "source":
        r["executed_source"] = "full_observed_graph"
    elif mutation == "budget":
        r["candidate_budget"] = 192
    elif mutation == "cue":
        r["cues"][0]["vector"][0] += 1
    elif mutation == "cue_used":
        r["cues"][0]["used"] = False
    elif mutation == "attempt":
        r["attempts"][0]["route_index"] = 9999
    elif mutation == "repair_cost":
        r["work_delta"]["payload_novelty_checks"] += 1
    elif mutation == "source_cost":
        d["work"]["raw_attention_pairs"] += 1
    elif mutation == "mask_header":
        e["coverage_allowance_bytes"] = 0
    elif mutation == "bank_hash":
        next(iter(e["routing_snapshots"].values()))["source_snapshot_label"] = "0" * 64
    elif mutation == "bank_bytes":
        e["costs"]["wire_routing_snapshot_json_bytes"] += 1
    with pytest.raises(AuditError):
        audit_episode(e)


@pytest.mark.parametrize(
    "mutation",
    ["score", "selected_prefix", "logical_id", "output", "span", "original_order", "snapshot"],
)
def test_real_branch_metadata_is_not_a_decorative_tree(
    trace: dict[str, Any], mutation: str
) -> None:
    e = expand_wire(trace)
    row = e["trajectory"][0]
    d = row["decision"]
    heads = sorted(row["new_facts"], key=lambda f: f["id"])
    oracle = TreeOracle()
    oracle.update(heads)
    route = copy.deepcopy(d["route"][0])
    query = d["queries"][route["query_index"]]
    oracle.route(route, query, route["p"], heads)
    if mutation == "score":
        route["steps"][0]["scores"][0] += 0.1
    elif mutation == "selected_prefix":
        route["steps"][0]["selected"] = []
    elif mutation == "logical_id":
        route["selected_logical_ids"].append(9999)
    elif mutation == "output":
        route["attention_output"][0] += 1
    elif mutation == "span":
        route["node_spans"][0]["stop"] += 1
    elif mutation == "original_order":
        route["index_fact_ids"].reverse()
    elif mutation == "snapshot":
        route["snapshot_id"] = "0" * 64
    with pytest.raises(AuditError):
        oracle.route(route, query, route["p"], heads)


def test_bounded_progress_stages_and_observed_graph_attribution() -> None:
    pytest.importorskip("minigrid")
    import torch

    from research.minigrid_benchmark import Fact, ReadContext
    from research.progress_retrieval import ProgressReader

    reader = ProgressReader("progress_zha")
    stages = []
    for step in range(26):
        visible = [Fact(0, 0, 0, 1, 0, 0, step, step), Fact(0, 1, 0, 1, 0, 0, step, step)]
        reader.observe(visible)
        _, routes, receipt, _ = reader.select_with_context(
            torch.tensor(mini_queries([0, 0, 0], "go to the goal"), dtype=torch.float64),
            ReadContext((0, 0), 0, "go to the goal", None, tuple(visible), step),
        )
        repair = receipt["repair"]
        stages.append(repair["stage"])
        assert len(repair["history"]) <= 24
        assert reader.source.name == "zha_adaptive" and reader.source.capacity == 96
        if step >= 24:
            assert not routes and repair["executed_source"] == "full_observed_graph"
            assert repair["fallback_active"] and all(not c["used"] for c in repair["cues"])
    assert stages == [0] * 8 + [1] * 8 + [2] * 8 + [3] * 2


def test_repeated_old_door_payload_is_not_new_information() -> None:
    pytest.importorskip("minigrid")
    import torch

    from research.minigrid_benchmark import Fact, ReadContext
    from research.progress_retrieval import ProgressReader

    reader = ProgressReader("cues_exact")
    novel = []
    for step, state in enumerate((2, 0, 2)):
        visible = [Fact(0, 0, 0, 1, 0, 0, step, step), Fact(0, 1, 0, 4, 0, state, step, step)]
        reader.observe(visible)
        _, _, receipt, _ = reader.select_with_context(
            torch.tensor(mini_queries([0, 0, 0], "go to the goal"), dtype=torch.float64),
            ReadContext((0, 0), 0, "go to the goal", None, tuple(visible), step),
        )
        novel.append(receipt["repair"]["novel_observed_ids"])
    assert novel[0] and novel[1] and novel[2] == []
    assert receipt["repair"]["no_information_reads"] == 1


def test_hard_information_limit_is_bounded_without_pose_repetition() -> None:
    pytest.importorskip("minigrid")
    import torch

    from research.minigrid_benchmark import Fact, ReadContext
    from research.progress_retrieval import ProgressReader

    reader = ProgressReader("progress_exact")
    for step in range(25):
        reader.observe([Fact(0, step, 0, 1, 0, 0, step, step)])
    visible = (Fact(0, 24, 0, 1, 0, 0, 24, 24),)
    reader.select_with_context(
        torch.tensor(mini_queries([24, 0, 0], "go to the goal"), dtype=torch.float64),
        ReadContext((24, 0), 0, "go to the goal", None, visible, 24),
    )
    for stale in range(1, 49):
        step, x = 24 + stale, stale % 25
        visible = (Fact(0, x, 0, 1, 0, 0, step, step),)
        reader.observe(list(visible))
        _, _, receipt, _ = reader.select_with_context(
            torch.tensor(mini_queries([x, 0, 0], "go to the goal"), dtype=torch.float64),
            ReadContext((x, 0), 0, "go to the goal", None, visible, step),
        )
        assert not receipt["repair"]["repeated_pose"]
        assert receipt["repair"]["stage"] != 3 if stale < 48 else receipt["repair"]["stage"] == 3
    assert receipt["repair"]["trigger"] == "hard_no_information_limit"


def test_equal_tensor_snapshot_labels_do_not_alias_original_id_layouts() -> None:
    pytest.importorskip("minigrid")
    import torch

    from research.minigrid_benchmark import Fact, ReadContext
    from research.progress_retrieval import ProgressReader

    reader = ProgressReader("progress_zha")
    layouts = []
    for step, state in enumerate((2, 0, 2)):
        visible = [Fact(0, 0, 0, 1, 0, 0, step, step), Fact(0, 1, 0, 4, 0, state, step, step)]
        reader.observe(visible)
        _, routes, _, _ = reader.select_with_context(
            torch.tensor(mini_queries([0, 0, 0], "go to the goal"), dtype=torch.float64),
            ReadContext((0, 0), 0, "go to the goal", None, tuple(visible), step),
        )
        route = routes[0]
        layouts.append(
            {
                "source_snapshot_label": route["snapshot_id"],
                **{
                    k: route[k]
                    for k in (
                        "index_fact_ids",
                        "node_spans",
                        "chunk_size",
                        "depth",
                        "logical_key_count",
                    )
                },
            }
        )
    assert layouts[0]["source_snapshot_label"] == layouts[2]["source_snapshot_label"]
    assert layouts[0]["index_fact_ids"] != layouts[2]["index_fact_ids"]
    assert digest(layouts[0]) != digest(layouts[2])
