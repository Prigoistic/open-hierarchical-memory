from __future__ import annotations

import copy

import pytest
import torch

from research.run_persistent_tasks import persistent_episode
from research.task_references import RouterCheckpoint, TaskSample
from research.task_replay import ReplayItem, deduplicate, episode_items, replay_references
from research.task_store import WorkspaceConfig
from scripts.audit_task_replay import audit_learning


def item(context, role, seed):
    generator = torch.Generator().manual_seed(seed)
    keys = torch.randn(14, 30, generator=generator, dtype=torch.float64)
    keys[0] = 0
    queries = torch.randn(2, 30, generator=generator, dtype=torch.float64)
    return ReplayItem(TaskSample(context, 3, queries, keys), role, tuple(range(1, 14)))


def corpus():
    train = [item("old", "anchor", 1), item("wake", "wake", 2)]
    old = [item("old-val", "validation_old", 3)]
    new = [item("new-val", "validation_new", 4)]
    return train, old, new


def test_replay_updates_references_preserves_inputs_and_scalar_audit_checks_gradient():
    training, old, new = corpus()
    parent = RouterCheckpoint.fixed()
    originals = [i.payload() for i in training + old + new]
    updates = []
    checkpoint, trace = replay_references(
        training, old, new, parent, "uniform", seed=7, steps=4, on_update=updates.append
    )
    assert len(trace["updates"]) == 4 and len(updates) == 4
    assert trace["work"]["gradient_calls"] == 4
    assert trace["updates"][-1]["after_hash"] != trace["updates"][0]["before_hash"]
    assert [i.payload() for i in training + old + new] == originals
    source = {i.uid: dict(i.payload(), id=i.uid) for i in training + old + new}
    result = audit_learning(
        trace,
        dict(parent.payload(), sha256=parent.sha256),
        dict(checkpoint.payload(), sha256=checkpoint.sha256),
        source,
    )
    assert result["updates"] == 4 and result["smooth_gradient_coordinates"] > 0
    # A wrong gradient cannot be hidden behind a successful checkpoint/result label.
    bad = copy.deepcopy(trace)
    bad["updates"][0]["gradient"][0][0][0] += 1
    with pytest.raises(AssertionError):
        audit_learning(
            bad,
            dict(parent.payload(), sha256=parent.sha256),
            dict(checkpoint.payload(), sha256=checkpoint.sha256),
            source,
        )
    updates[0]["gradient"][0][0][0] = 999
    assert trace["updates"][0]["gradient"][0][0][0] != 999


def test_replay_is_rng_isolated_reproducible_and_recent_schedule_excludes_anchors():
    training, old, new = corpus()
    before = torch.random.get_rng_state().clone()
    a, ta = replay_references(
        training, old, new, RouterCheckpoint.fixed(), "recent", seed=19, steps=3
    )
    b, tb = replay_references(
        training, old, new, RouterCheckpoint.fixed(), "recent", seed=19, steps=3
    )
    assert a == b and ta == tb
    assert torch.equal(torch.random.get_rng_state(), before)
    assert all(r["role"] == "wake" for r in ta["updates"])
    assert ta["pool_ids"] == [training[1].uid]


def test_priority_sampling_records_real_extra_work_and_has_nonzero_coverage():
    training, old, new = corpus()
    child, trace = replay_references(
        training, old, new, RouterCheckpoint.fixed(), "priority", seed=31, steps=9
    )
    assert trace["work"]["priority_calls"] == 4
    assert len(trace["priority_refreshes"]) == 2
    assert all(p >= 0.1 / 2 for r in trace["priority_refreshes"] for p in r["probabilities"])
    for context in ("old", "wake", "old-val", "new-val"):
        with pytest.raises(ValueError, match="fit/select"):
            child.require_evaluation_context(context)
    child.require_evaluation_context("untouched")


def test_evaluation_roles_contexts_numerical_duplicates_and_bad_sources_fail():
    training, old, new = corpus()
    with pytest.raises(ValueError, match="roles"):
        replay_references([new[0]], old, new, RouterCheckpoint.fixed(), "uniform", seed=7)
    repeated = ReplayItem(
        TaskSample("old", 3, new[0].sample.queries, new[0].sample.keys),
        "validation_new",
        new[0].source_ids,
    )
    with pytest.raises(ValueError, match="contexts overlap"):
        replay_references(training, old, [repeated], RouterCheckpoint.fixed(), "uniform", seed=7)
    duplicate = ReplayItem(
        TaskSample("other", 3, training[0].sample.queries, training[0].sample.keys),
        "validation_new",
        training[0].source_ids,
    )
    with pytest.raises(ValueError, match="numerical overlap"):
        replay_references(training, old, [duplicate], RouterCheckpoint.fixed(), "uniform", seed=7)
    with pytest.raises(ValueError, match="source mapping"):
        ReplayItem(training[0].sample, "anchor", tuple([1] * 13))


def test_declared_deduplication_is_independent_of_outcomes():
    training, old, new = corpus()
    duplicate = ReplayItem(training[0].sample, "wake", training[0].source_ids)
    groups = {
        "anchor": [training[0]],
        "wake": [duplicate, training[1]],
        "validation_old": old,
        "validation_new": new,
    }
    dropped = deduplicate(groups)
    assert dropped["wake"] == 1 and groups["wake"] == [training[1]]


def test_stress_capacity_preserves_observed_source_extraction_and_future_rejection(tmp_path):
    episode = persistent_episode(
        tmp_path / "stress.sqlite",
        "MiniGrid-DoorKey-16x16-v0",
        9001,
        RouterCheckpoint.fixed(),
        "zha",
        12,
        workspace=WorkspaceConfig(capacity=64),
    )
    assert episode["result"]["error"] is None
    assert all(r["decision"]["dependency"]["active_capacity"] == 64 for r in episode["trajectory"])
    samples = episode_items(episode, "wake")
    assert samples and all(i.sample.step <= 11 for i in samples)
    for sample in samples:
        visible = {
            f["id"] for r in episode["trajectory"][: sample.sample.step + 1] for f in r["new_facts"]
        }
        assert set(sample.source_ids) <= visible
    bad = copy.deepcopy(episode)
    bad["trajectory"][0]["new_facts"][0]["observed_step"] = 999
    with pytest.raises(ValueError, match="future"):
        episode_items(bad, "wake")
