from __future__ import annotations

import copy
import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from open_hierarchical_memory import ResourceLimitError
from research.boxoban_benchmark import (
    Case,
    CaseReader,
    Geometry,
    State,
    features,
    make_cases,
    parse_levels,
    reachable,
    replay,
    solve,
    successors,
    symmetry_key,
)

SIMPLE = "; 0\n######\n#    #\n# @$ #\n#  . #\n######\n"


def test_push_solution_and_training_chain() -> None:
    level = parse_levels(SIMPLE, "train")[0]
    r = solve(level, weight=1)
    assert r["success"] and r["pushes"] == 1
    assert set(replay(level, r["moves"]).boxes) == set(level.goals)
    cases = make_cases(level, r)
    assert len(cases) == 2 and cases[0].remaining_pushes == 1
    bad = copy.deepcopy(r)
    bad["path"][-1]["moves_from_previous"] = "UU"
    with pytest.raises(ValueError):
        make_cases(level, bad)
    with pytest.raises(ValueError):
        make_cases(replace(level, split="test"), r)


def test_exact_dead_square_and_assignment() -> None:
    level = parse_levels(SIMPLE, "train")[0]
    g = Geometry(level)
    assert g.lower_bound(level.initial.boxes) == 1
    assert 7 in g.dead and level.goals[0] not in g.dead
    assert not g.blocked_square(level.initial.boxes)
    for state, segment in successors(level, level.initial, g):
        assert replay(level, segment) == state
        assert g.lower_bound(level.initial.boxes) <= 1 + g.lower_bound(state.boxes)


def test_illegal_moves_and_invalid_boards_rejected() -> None:
    level = parse_levels(SIMPLE, "train")[0]
    for moves in ["UUU", "RRR", "Q"]:
        with pytest.raises(ValueError):
            replay(level, moves)
    for text in ["garbage", "; 0\n##\n#@#\n", "; 0\n###\n#@#\n###\n"]:
        with pytest.raises(ValueError):
            parse_levels(text, "train")


def test_region_canonicalization_and_symmetries() -> None:
    level = parse_levels(SIMPLE, "train")[0]
    mirrored = replace(
        level, initial=replace(level.initial, player=next(iter(reachable(level, level.initial))))
    )
    assert symmetry_key(level) == symmetry_key(mirrored)
    lines = tuple(row[::-1] for row in level.rows)
    flipped = parse_levels("; 0\n" + "\n".join(lines) + "\n", "test")[0]
    assert symmetry_key(level) == symmetry_key(flipped)


def bank(count: int) -> tuple[Case, ...]:
    return tuple(
        Case("train", i, str(i), 0, (1,), 3 + i % 3, 2, (2.0, math.sin(i), math.cos(i), 1.0))
        for i in range(count)
    )


@pytest.mark.parametrize("method", ["dense", "top16", "zha", "random_values"])
def test_selected_attention_matches_independent_numpy(method: str) -> None:
    reader = CaseReader(bank(96), method, p=0.5)  # type: ignore[arg-type]
    query = np.array([2.0, 0.3, 0.2, 1.0], dtype=np.float64)
    value = reader.estimate(query, parse_levels(SIMPLE, "train")[0].initial)
    row = reader.logs[-1]
    ids = list(range(97)) if row["selected_ids"] is None else row["selected_ids"]
    keys = reader.keys.numpy()[ids]
    values = reader.values.numpy()[ids]
    logits = np.sum(keys * query, axis=1) / 2
    weights = np.exp(logits - np.max(logits))
    weights /= weights.sum()
    assert value == pytest.approx(float(weights @ values), abs=1e-12)
    assert reader.work()["raw_value_reads"] == len(ids)
    if method == "zha":
        assert len(ids) < 97 and reader.work()["summary_dot_products"] > 0


def test_sparse_budget_failure_is_not_a_solve_or_fallback() -> None:
    reader = CaseReader(bank(160), "zha", p=1)
    with pytest.raises(ResourceLimitError):
        reader.estimate(
            np.array([2.0, 0.3, 0.2, 1.0], dtype=np.float64),
            parse_levels(SIMPLE, "train")[0].initial,
        )
    assert reader.failed_calls == 1 and reader.work()["failed_query_work_unknown"] == 1


def test_search_limits_are_honest() -> None:
    level = parse_levels(SIMPLE, "train")[0]
    r = solve(level, expansion_limit=1)
    assert not r["success"] and r["status"] == "expansion_limit" and not r["path"]
    r = solve(level, wall_seconds=1e-15)
    assert not r["success"] and r["status"] == "wall_timeout"
    for cap in [0, True, 100001]:
        with pytest.raises(ValueError):
            solve(level, expansion_limit=cap)


def test_real_training_fixture_solution_and_fixed_feature_dimension() -> None:
    level = parse_levels(Path("data/boxoban/train.txt").read_text(), "train")[0]
    r = solve(level, expansion_limit=1000, weight=1)
    assert r["success"] and r["pushes"] == 12
    assert set(replay(level, r["moves"]).boxes) == set(level.goals)
    simple = parse_levels(SIMPLE, "train")[0]
    assert (
        features(level, level.initial, Geometry(level)).shape
        == features(simple, simple.initial, Geometry(simple)).shape
    )
    cases = make_cases(level, r)
    assert all(c.level_hash == level.identity for c in cases)
    reader = CaseReader(cases, "linear")
    assert math.isfinite(
        reader.estimate(features(level, level.initial, Geometry(level)), level.initial)
    )
    assert reader.raw_key_scores == 0


def test_no_memory_does_not_consult_case_bank(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = CaseReader(bank(4), "matching")

    def forbidden(*args: object) -> float:
        raise AssertionError("matching baseline must not query memory")

    monkeypatch.setattr(reader, "estimate", forbidden)
    assert solve(parse_levels(SIMPLE, "train")[0], reader)["success"]
    assert not reader.logs


def test_reader_reuse_returns_owned_per_run_evidence() -> None:
    level = parse_levels(";0\n######\n#@$ .#\n######\n", "train")[0]
    reader = CaseReader(make_cases(level, solve(level, weight=1)), "dense")
    first = solve(level, reader)
    before = copy.deepcopy(first)
    second = solve(level, reader)
    assert first == before
    assert first["read_work"]["calls"] == second["read_work"]["calls"] == 1
    assert len(first["reads"]) == len(second["reads"]) == 1
    second["reads"][0]["query"][0] = -9000
    assert first == before and reader.logs[0]["query"][0] != -9000


def test_retrieved_guidance_changes_selected_search_states(monkeypatch: pytest.MonkeyPatch) -> None:
    level = parse_levels(Path("data/boxoban/train.txt").read_text(), "train")[0]
    bank_cases = make_cases(level, solve(level, weight=1))
    reader = CaseReader(bank_cases, "dense")

    def perturb(feature: object, state: State) -> float:
        return 40.0 if state.boxes[0] % 2 else 0.0

    monkeypatch.setattr(reader, "estimate", perturb)
    guided = solve(level, reader, expansion_limit=30)
    plain = solve(level, expansion_limit=30)
    assert [r["boxes"] for r in guided["expanded_trace"]] != [
        r["boxes"] for r in plain["expanded_trace"]
    ]


def test_frozen_core_tampering_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import research.run_boxoban_benchmark as runner

    monkeypatch.setattr(runner, "ROOT", tmp_path)
    source = tmp_path / "src/open_hierarchical_memory/attention.py"
    source.parent.mkdir(parents=True)
    source.write_text("original attention source")
    output = tmp_path / "out"
    output.mkdir()
    for name in ["protocol.json", "cases.json", "cohorts.json"]:
        (output / name).write_text("{}")
    manifest = {"source_hashes": {"src/open_hierarchical_memory/attention.py": runner.sha(source)}}
    data_manifest = tmp_path / "data/boxoban/manifest.json"
    data_manifest.parent.mkdir(parents=True)
    data_manifest.write_text("{}")
    manifest["data_manifest"] = {}
    for filename, field in [
        ("protocol.json", "protocol_sha256"),
        ("cases.json", "cases_sha256"),
        ("cohorts.json", "cohorts_sha256"),
    ]:
        manifest[field] = runner.sha(output / filename)
    (output / "manifest.json").write_text(json.dumps(manifest))
    assert runner.verify_frozen(output)
    data_manifest.write_text('{"changed": true}')
    with pytest.raises(ValueError, match="data manifest changed"):
        runner.verify_frozen(output)
    data_manifest.write_text("{}")
    source.write_text("changed attention implementation")
    with pytest.raises(ValueError, match="source changed"):
        runner.verify_frozen(output)
