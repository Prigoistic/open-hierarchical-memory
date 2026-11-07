"""Behavior tests independent of maze display and summary reports."""

import inspect
import json
import math
from dataclasses import asdict, replace

import pytest
import torch

from research.somna_spatial import (
    GAMMA,
    EpisodeIndex,
    Transition,
    digest,
    evaluate,
    key_for,
    load_checkpoint,
    make_world,
    offline_fork,
    save_checkpoint,
    target,
    wake_checkpoint,
)


@pytest.fixture(autouse=True)
def one_thread():
    original = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(original)


def test_immutable_seeded_world_and_connected_known_map():
    for seed in (7, 23, 101):
        world = make_world(seed, 7)
        assert world == make_world(seed, 7)
        reached = {world.goal}
        while True:
            expanded = reached | {r.state for r in world.transitions if r.successor in reached}
            if expanded == reached:
                break
            reached = expanded
        assert reached == set(range(len(world.cells)))
        assert len(world.transitions) == 4 * (len(world.cells) - 1)
    assert make_world(7) != make_world(23)


def test_attention_values_match_independent_scalar_subset_oracle():
    world = make_world(7, 7)
    bank = EpisodeIndex(world.transitions, len(world.cells), world.goal)
    row = world.transitions[8]
    for backend in ("dense", "zha"):
        result = bank.read(row.state, row.action, backend)
        query = key_for(row.state, row.action, bank.states).tolist()
        keys = bank.keys[0, 0].tolist()
        values = bank.values[0, 0].tolist()
        selected = result["selected_ids"]
        scores = [
            sum(x * y for x, y in zip(keys[i], query, strict=True)) / math.sqrt(len(query))
            for i in selected
        ]
        weights = [math.exp(s - max(scores)) for s in scores]
        expected = [
            sum(w * values[i][j] for w, i in zip(weights, selected, strict=True)) / sum(weights)
            for j in range(bank.states + 1)
        ]
        assert result["probabilities"] + [result["reward"]] == pytest.approx(expected, abs=1e-12)
    sparse = bank.read(row.state, row.action, "zha")
    assert len(sparse["selected_ids"]) < len(world.transitions) + 1
    assert sparse["steps"]


def test_bellman_update_respects_terminal_and_actual_mixture():
    q = torch.tensor([[1.0, 2.0, 3.0, 4.0], [9.0, 9.0, 9.0, 9.0]], dtype=torch.float64)
    assert target(q, [0.25, 0.75], 0.5, 1) == pytest.approx(0.5 + GAMMA)
    assert target(q, [0.0, 1.0], 1.0, 1) == 1.0


def test_forks_share_wake_and_archive_without_mutating_inputs(tmp_path):
    world = make_world(23, 7)
    bank = EpisodeIndex(world.transitions, len(world.cells), world.goal)
    checkpoint = wake_checkpoint(world.transitions, bank.states, bank.goal)
    frozen = checkpoint.clone()
    before = digest([asdict(r) for r in world.transitions])
    forks = [
        offline_fork(bank, checkpoint, policy, "zha", updates=128, seed=3)
        for policy in ("none", "uniform", "priority")
    ]
    assert torch.equal(checkpoint, frozen)
    assert before == bank.archive_hash == digest([asdict(r) for r in world.transitions])
    assert len({f["initial_checkpoint_hash"] for f in forks}) == 1
    assert forks[0]["q"] == checkpoint.tolist()
    assert forks[0]["records"] == []
    for fork in forks[1:]:
        assert fork["updates"] == 128
        assert len(fork["records"]) == 128
        assert fork["environment_calls_during_offline"] == 0
        for event in fork["records"]:
            actual = world.transitions[event["evidence_id"] - 1]
            assert (actual.state, actual.action) == (event["state"], event["action"])
        path = tmp_path / f"{fork['policy']}.json"
        save_checkpoint(path, fork)
        assert set(json.loads(path.read_text())) == {
            "archive_hash",
            "representation",
            "checkpoint_hash",
            "q",
        }
        restored = load_checkpoint(path, bank.archive_hash)
        assert evaluate(world, restored) == evaluate(world, fork["q"])
    assert forks[2]["work"]["scheduler_comparisons"] == 128 * len(world.transitions)


def test_priority_propagates_observed_terminal_reward_without_future_labels():
    # Chain 0 -> 1 -> 2; wake ordering prevents reward reaching state zero.
    rows = (Transition(1, 0, 1, 1, 0.0), Transition(2, 1, 1, 2, 1.0))
    bank = EpisodeIndex(rows, 3, 2)
    q = wake_checkpoint(rows, 3, 2)
    assert q[0, 1] == 0
    result = offline_fork(bank, q, "priority", "dense", updates=2)
    assert result["q"][0][1] == pytest.approx(GAMMA, abs=1e-10)
    assert "world" not in inspect.signature(offline_fork).parameters
    assert "evaluation_starts" not in inspect.signature(offline_fork).parameters


def test_corrupt_or_cross_archive_checkpoint_rejected(tmp_path):
    world = make_world(7, 5)
    bank = EpisodeIndex(world.transitions, len(world.cells), world.goal)
    q = wake_checkpoint(world.transitions, bank.states, bank.goal)
    result = offline_fork(bank, q, "none", "dense")
    path = tmp_path / "checkpoint.json"
    save_checkpoint(path, result)
    with pytest.raises(FileExistsError):
        save_checkpoint(path, result)
    with pytest.raises(ValueError, match="mismatch"):
        load_checkpoint(path, "wrong")
    payload = json.loads(path.read_text())
    payload["q"][0][0] += 1
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="hash"):
        load_checkpoint(path, bank.archive_hash)


@pytest.mark.parametrize(
    "modification",
    [{"evidence": "imagined"}, {"reward": float("nan")}, {"action": True}, {"identifier": 0}],
)
def test_archive_rejects_untrusted_evidence_and_indexes(modification):
    world = make_world(7, 5)
    rows = (replace(world.transitions[0], **modification),) + world.transitions[1:]
    with pytest.raises(ValueError):
        EpisodeIndex(rows, len(world.cells), world.goal)


def test_exact_and_sparse_decisions_ignore_sub_tolerance_softmax_spill():
    world = make_world(7, 7)
    bank = EpisodeIndex(world.transitions, len(world.cells), world.goal)
    q = wake_checkpoint(world.transitions, bank.states, bank.goal)
    dense = offline_fork(bank, q, "uniform", "dense", updates=64, seed=19)
    sparse = offline_fork(bank, q, "uniform", "zha", updates=64, seed=19)
    assert evaluate(world, dense["q"])["successes"] == evaluate(world, sparse["q"])["successes"]


@pytest.mark.parametrize("updates", [-1, True, 4097])
def test_offline_budget_rejected(updates):
    world = make_world(7, 5)
    bank = EpisodeIndex(world.transitions, len(world.cells), world.goal)
    q = wake_checkpoint(world.transitions, bank.states, bank.goal)
    with pytest.raises(ValueError, match="updates"):
        offline_fork(bank, q, "uniform", "zha", updates=updates)
