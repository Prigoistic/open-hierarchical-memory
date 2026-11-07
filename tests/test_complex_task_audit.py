"""Auditor counterexamples use small explicit fixtures, not benchmark claims."""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import pytest

from scripts.audit_complex_tasks import (
    AuditError,
    Position,
    audit_boxoban,
    audit_directory,
    audit_minigrid,
    audit_read,
    digest,
    features,
    lower_bound,
    parse_board,
    parse_source,
    replay,
    symmetry,
)


def solved_fixture() -> dict[str, Any]:
    return {
        "schema": "boxoban-search-v1",
        "split": "train",
        "level_id": 0,
        "level_hash": digest({"rows": ["######", "#@$ .#", "######"]}),
        "rows": ["######", "#@$ .#", "######"],
        "method": "matching",
        "status": "solved",
        "success": True,
        "pushes": 2,
        "moves": "RR",
        "path": [
            {"player": 7, "boxes": [8], "pushes": 0, "moves_from_previous": ""},
            {"player": 8, "boxes": [9], "pushes": 1, "moves_from_previous": "R"},
            {"player": 9, "boxes": [10], "pushes": 2, "moves_from_previous": "R"},
        ],
        "expanded": 3,
        "expansion_limit": 8,
        "wall_seconds": 0.01,
        "wall_limit": 1.0,
        "weight": 1.5,
        "expanded_trace": [
            {"player": 7, "boxes": [8], "pushes": 0, "frontier": 0, "priority": 2.0},
            {"player": 8, "boxes": [9], "pushes": 1, "frontier": 0, "priority": 2.5},
            {"player": 9, "boxes": [10], "pushes": 2, "frontier": 0, "priority": 2.0},
        ],
        "reads": [],
        "read_work": {},
    }


def test_valid_primitive_replay_and_push_macro_accounting() -> None:
    run = solved_fixture()
    assert audit_boxoban(run)["pushes_checked"] == 2
    board = parse_board(run["rows"])
    final, count = replay(board, "RR")
    assert final.boxes == board.goals and count == 2
    assert lower_bound(board, Position(board.player, board.boxes)) == 2
    assert len(features(board, Position(board.player, board.boxes))) == 83


@pytest.mark.parametrize(
    "mutation",
    [
        "illegal_push",
        "fake_state",
        "fake_expansion",
        "priority",
        "fake_success",
        "extra_push_macro",
        "wrong_hash",
        "wrong_push_count",
        "wrong_root",
    ],
)
def test_rejects_corrupted_state_evidence(mutation: str) -> None:
    run = solved_fixture()
    if mutation == "illegal_push":
        run["path"][-1]["moves_from_previous"] = "RR"
    elif mutation == "fake_state":
        run["path"][1]["boxes"] = [10]
    elif mutation == "fake_expansion":
        run["expanded_trace"][0]["player"] = 9
    elif mutation == "priority":
        run["expanded_trace"][1]["priority"] += 1.0
    elif mutation == "fake_success":
        run["status"] = "exhausted"
    elif mutation == "extra_push_macro":
        run["path"] = [run["path"][0], {**run["path"][-1], "moves_from_previous": "RR"}]
    elif mutation == "wrong_hash":
        run["level_hash"] = "forged"
    elif mutation == "wrong_push_count":
        run["pushes"] = 1
    elif mutation == "wrong_root":
        run["path"][0]["moves_from_previous"] = "R"
    with pytest.raises(AuditError):
        audit_boxoban(run)


def test_valid_resource_failure_and_fabricated_failure_rejection() -> None:
    run = solved_fixture()
    run.update(
        status="expansion_limit",
        success=False,
        pushes=None,
        moves="",
        path=[],
        expansion_limit=3,
    )
    assert audit_boxoban(run)["success"] is False
    run["expansion_limit"] = 4
    with pytest.raises(AuditError, match="premature"):
        audit_boxoban(run)
    run.update(status="wall_timeout", wall_seconds=0.5)
    with pytest.raises(AuditError, match="premature"):
        audit_boxoban(run)


def test_scalar_read_and_negative_value_selection_work_controls() -> None:
    cases = [{"feature": [1.0, 0.0], "remaining_pushes": 3, "lower_bound": 1}]
    # Equal scores give an independently obvious mean including the zero sink.
    read = {
        "query": [0.0, 1.0],
        "selected_ids": None,
        "selected_count": 2,
        "raw_key_scores": 2,
        "summary_dot_products": 0,
        "value": 1.0,
    }
    audit_read(read, cases, "dense")
    for changed in (
        {"value": 1.1},
        {"raw_key_scores": 1},
        {"selected_count": 1},
        {"selected_ids": [1]},
    ):
        with pytest.raises(AuditError):
            audit_read({**read, **changed}, cases, "dense")
    audit_read({**read, "selected_ids": [0, 1]}, cases, "zha")
    with pytest.raises(AuditError, match="missing selected"):
        audit_read(read, cases, "zha")


def test_query_observation_and_total_work_provenance() -> None:
    run = solved_fixture()
    board = parse_board(run["rows"])
    query = features(board, Position((2, 1), frozenset({(3, 1)})))
    read = {
        "player": 8,
        "boxes": [9],
        "query": query,
        "selected_ids": None,
        "selected_count": 2,
        "raw_key_scores": 2,
        "summary_dot_products": 0,
        "value": 0.0,
    }
    cases = [{"feature": query, "remaining_pushes": 1, "lower_bound": 1}]
    run.update(
        method="dense",
        reads=[read],
        read_work={
            "calls": 1,
            "failed_calls": 0,
            "failed_query_work_unknown": 0,
            "raw_key_scores": 2,
            "raw_value_reads": 2,
            "summary_dot_products": 0,
        },
    )
    assert audit_boxoban(run, cases)["reads_checked"] == 1
    # A nonzero retrieved gap must enter the search priority, not just its log.
    guided = copy.deepcopy(run)
    cases_nonzero = [{**cases[0], "remaining_pushes": 2}]
    logit = sum(x * x for x in query) / math.sqrt(len(query))
    gap = 1 / (1 + math.exp(-logit))
    guided["reads"][0]["value"] = gap
    with pytest.raises(AuditError, match="priority ignores"):
        audit_boxoban(guided, cases_nonzero)
    guided["expanded_trace"][1]["priority"] += 1.5 * gap
    assert audit_boxoban(guided, cases_nonzero)["priorities_checked"] == 3
    wrong = copy.deepcopy(run)
    wrong["reads"][0]["query"][0] += 0.01
    with pytest.raises(AuditError, match="query provenance"):
        audit_boxoban(wrong, cases)
    wrong = copy.deepcopy(run)
    wrong["read_work"]["calls"] = 2
    with pytest.raises(AuditError, match="read-call"):
        audit_boxoban(wrong, cases)


def test_source_parser_preserves_spaces_and_symmetry_equivalent_start() -> None:
    levels = parse_source(
        "; 0\n#######\n#@ $ .#\n#     #\n#######\n\n; 1\n#######\n#  $ .#\n#@    #\n#######\n"
    )
    assert len(levels) == 2 and symmetry(levels[0]) == symmetry(levels[1])
    mirrored = parse_board([row[::-1] for row in levels[0].rows])
    assert symmetry(levels[0]) == symmetry(mirrored)


def test_auditor_is_independent_of_production_simulator() -> None:
    # Guard against a later refactor accidentally turning this into self-validation.
    source = (Path(__file__).resolve().parents[1] / "scripts/audit_complex_tasks.py").read_text()
    assert "from research.boxoban" not in source and "import research.boxoban" not in source
    assert "from open_hierarchical_memory" not in source
    assert json.loads(json.dumps(solved_fixture())) == solved_fixture()


def write_bundle(root: Path, corruption: str | None = None) -> tuple[Path, Path]:
    """Tiny self-contained artifact fixture, with hashes recomputed after mutation.

    Rehashing makes semantic controls exercise provenance rather than merely
    tripping the outer checksum check. These boards are not performance evidence.
    """
    output, data = root / "output", root / "data"
    output.mkdir()
    data.mkdir()
    (output / "evaluation").mkdir()
    (output / "source-snapshot").mkdir()
    (output / "source-snapshot/review.py").write_text("# inert fixture\n")

    def write(path: Path, value: Any) -> str:
        raw = json.dumps(value, sort_keys=True).encode()
        if path.suffix == ".gz":
            raw = gzip.compress(raw, mtime=0)
        path.write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    train = solved_fixture()
    board = parse_board(train["rows"])
    feature = features(board, Position(board.player, board.boxes))
    case = {
        "split": "train",
        "level_id": 0,
        "level_hash": train["level_hash"],
        "player": 7,
        "boxes": [8],
        "remaining_pushes": 2,
        "lower_bound": 2.0,
        "feature": feature,
    }
    if corruption == "foreign_case":
        case["split"] = "test"
    elif corruption == "false_suffix":
        case["remaining_pushes"] = 3
    elif corruption == "case_geometry":
        case["feature"][0] += 0.1
    bank = {
        "schema": "boxoban-cases-v1",
        "feature_version": "boxoban-local-geometry-v1",
        "cases": [case],
        "hash": digest([case]),
    }
    evaluation = copy.deepcopy(train)
    evaluation["rows"] = ["######", "#@$ .#", "#    #", "######"]
    if corruption == "duplicate_board":
        evaluation["rows"] = train["rows"]
    evaluation.update(
        split="test",
        level_hash=digest({"rows": evaluation["rows"]}),
        config="matching",
        p=0.8,
        case_hash=bank["hash"],
        weight=1.5,
    )
    if corruption == "protocol_weight":
        evaluation["weight"] = 2.0
    protocol = {
        "train_ids": [0],
        "configs": [["matching", "matching", 0.8]],
        "expansion_limits": [8],
        "weight": 1.5,
        "wall_seconds": 1.0,
    }
    manifest: dict[str, Any] = {
        "data_manifest": {"files": {}},
        "source_hashes": {
            "review.py": hashlib.sha256(
                (output / "source-snapshot/review.py").read_bytes()
            ).hexdigest()
        },
    }
    for split in ("train", "validation", "test", "hard"):
        path = data / (split + ".txt")
        rows = train["rows"] if split == "train" else evaluation["rows"]
        path.write_text("; 0\n" + "\n".join(rows) + "\n")
        manifest["data_manifest"]["files"][path.name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
        }
    manifest["protocol_sha256"] = write(output / "protocol.json", protocol)
    manifest["cohorts_sha256"] = write(
        output / "cohorts.json", {"cohorts": {"test": [0], "hard": []}}
    )
    manifest["cases_sha256"] = write(output / "cases.json", bank)
    write(output / "train-0.json.gz", train)
    checksum = write(output / "evaluation/test.json.gz", evaluation)
    write(
        output / "evaluation/report.json",
        {"complete": True, "runs": [{"file": "test.json.gz", "sha256": checksum}]},
    )
    write(output / "manifest.json", manifest)
    return output, data


def test_directory_audit_binds_cases_and_results_to_frozen_sources(
    tmp_path: Path,
) -> None:
    output, data = write_bundle(tmp_path)
    result = audit_directory(output, data)
    assert result["evaluation_runs"] == result["cases_checked"] == 1


@pytest.mark.parametrize(
    "corruption",
    [
        "foreign_case",
        "false_suffix",
        "case_geometry",
        "duplicate_board",
        "protocol_weight",
    ],
)
def test_rehashed_false_provenance_is_rejected(tmp_path: Path, corruption: str) -> None:
    output, data = write_bundle(tmp_path, corruption)
    with pytest.raises(AuditError):
        audit_directory(output, data)


@pytest.fixture(scope="module")
def minigrid_trace() -> dict[str, Any]:
    pytest.importorskip("minigrid", reason="official environment extra not installed")
    from research.run_minigrid_benchmark import run_episode

    # Bounded development fixture only, never reserve/evaluate a held-out seed.
    result: dict[str, Any] = json.loads(
        json.dumps(
            run_episode(
                "MiniGrid-MemoryS17Random-v0",
                "zha",
                0,
                split="unit",
                capacity=8,
                step_cap=6,
            )
        )
    )
    return result


def test_official_minigrid_replay_and_observation_bound_routes(
    minigrid_trace: dict[str, Any],
) -> None:
    result = audit_minigrid(minigrid_trace)
    assert result["steps_checked"] == 6 and result["routes_checked"] == 18
    assert not result["success"]


@pytest.mark.parametrize(
    "mutation",
    [
        "observation",
        "reward",
        "false_success",
        "future_fact",
        "foreign_memory",
        "version_chain",
        "current_view",
        "history",
        "query",
        "softmax",
        "work",
        "episode_cost",
        "action",
    ],
)
def test_minigrid_auditor_rejects_false_evidence(
    minigrid_trace: dict[str, Any], mutation: str
) -> None:
    episode = copy.deepcopy(minigrid_trace)
    row = episode["trajectory"][0]
    if mutation == "observation":
        row["observation"]["direction"] = (row["observation"]["direction"] + 1) % 4
    elif mutation == "reward":
        row["reward"] = 0.5
    elif mutation == "false_success":
        episode["result"]["success"] = True
    elif mutation == "future_fact":
        row["new_facts"][0]["observed_step"] = 2
    elif mutation == "foreign_memory":
        row["decision"]["memory_ids"].append(9999)
    elif mutation == "version_chain":
        row["new_facts"][0]["previous"] = 9999
    elif mutation == "current_view":
        row["decision"]["current_facts"][0]["object"] = 8
    elif mutation == "history":
        row["decision"]["recent_history"].append([99, 99, 0])
    elif mutation == "query":
        row["decision"]["queries"][0][0] += 0.1
    elif mutation == "softmax":
        row["decision"]["route"][0]["attention_output"][0] += 0.1
    elif mutation == "work":
        row["decision"]["work"]["raw_attention_pairs"] += 1
    elif mutation == "episode_cost":
        episode["costs"]["raw_attention_pairs"] += 1
    elif mutation == "action":
        row["action"] = 7
    with pytest.raises(AuditError):
        audit_minigrid(episode)


@pytest.fixture(scope="module")
def adaptive_trace() -> dict[str, Any]:
    pytest.importorskip("minigrid", reason="official environment extra not installed")
    from research.run_minigrid_benchmark import run_episode

    result: dict[str, Any] = json.loads(
        json.dumps(
            run_episode(
                "MiniGrid-MemoryS17Random-v0",
                "zha_adaptive",
                0,
                split="unit",
                capacity=96,
                step_cap=4,
            )
        )
    )
    return result


def test_adaptive_routes_are_observed_accumulated_and_all_passes_charged(
    adaptive_trace: dict[str, Any],
) -> None:
    result = audit_minigrid(adaptive_trace)
    assert result["routing_passes"] > result["steps_checked"]
    assert result["routes_checked"] == result["routing_passes"] * 3


@pytest.mark.parametrize(
    "mutation", ["attempt", "threshold", "early_stop", "extra_pass", "pass_cost"]
)
def test_adaptive_auditor_rejects_unjustified_or_uncharged_widening(
    adaptive_trace: dict[str, Any], mutation: str
) -> None:
    episode = copy.deepcopy(adaptive_trace)
    row = episode["trajectory"][0]
    routes = row["decision"]["route"]
    assert len(routes) >= 6
    if mutation == "attempt":
        routes[-1]["attempt"] += 1
    elif mutation == "threshold":
        routes[-1]["p"] = 0.9
    elif mutation == "early_stop":
        del routes[-3:]
    elif mutation == "extra_pass":
        extra = copy.deepcopy(routes[-3:])
        attempt = extra[0]["attempt"] + 1
        for route in extra:
            route.update(attempt=attempt, p=(0.4, 0.6, 0.8, 0.95, 1.0)[attempt])
        routes.extend(extra)
    elif mutation == "pass_cost":
        row["decision"]["work"]["routing_passes"] = 0
    with pytest.raises(AuditError):
        audit_minigrid(episode)
