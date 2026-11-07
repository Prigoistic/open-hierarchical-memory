"""Continuous-memory behavior, numerical oracles and persistent learning gates."""

from __future__ import annotations

import copy
import json
import math
import sqlite3

import pytest
import torch

from research.somna_engine import MemoryEngine, sha
from research.somna_world import features, model_inputs, model_targets, observations


@pytest.fixture(autouse=True)
def one_thread():
    original = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(original)


@pytest.fixture
def engine(tmp_path):
    instance = MemoryEngine(tmp_path / "memory.sqlite", seed=7, capacity=16, bootstrap=64)
    yield instance
    instance.close()


def scalar_features(position, action=None, context=None, mask=(True, True)):
    vector = []
    for x, visible in zip(position, mask, strict=True):
        vector.extend(
            [
                3 * fn(frequency * math.pi * x) if visible else 0.0
                for frequency in (1, 2)
                for fn in (math.cos, math.sin)
            ]
        )
    vector.extend([0.0, 0.0] if action is None else [4 * x for x in action])
    vector.extend([0.0, 0.0] if context is None else [6.0 * (context == i) for i in (0, 1)])
    return vector


def test_partial_cue_encoding_has_no_episode_identity():
    data = {"position": [0.23, -0.41], "action": [1.0, 0.0], "context": 1, "mask": [False, True]}
    assert features(data).tolist() == pytest.approx(scalar_features(**data), abs=1e-14)
    other = {**data, "position": [-0.72, -0.41]}
    assert torch.equal(features(data), features(other))
    with pytest.raises(ValueError, match="identifiers"):
        features({**data, "id": 9})


def test_numerical_reader_matches_independent_selected_softmax(engine):
    state = engine.query(
        {"position": [0.21, -0.18], "mask": [False, True], "context": None, "action": None}
    )
    read = state["query"]
    vector = scalar_features(
        **{k: read["cue"][k] for k in ("position", "mask", "action", "context")}
    )
    scores = [0.0]
    deltas = [[0.0, 0.0]]
    for identifier in read["selected_ids"]:
        row = engine.records[identifier]
        key = scalar_features(row["position"], row["action"], row["context"])
        scores.append(sum(a * b for a, b in zip(key, vector, strict=True)) / math.sqrt(12))
        deltas.append([b - a for a, b in zip(row["position"], row["successor"], strict=True)])
    weights = [math.exp(x - max(scores)) for x in scores]
    expected = [
        sum(w * d[j] for w, d in zip(weights, deltas, strict=True)) / sum(weights) for j in (0, 1)
    ]
    assert read["prediction"] == pytest.approx(expected, abs=1e-12)
    assert len(read["ranked"]) > 1
    assert read["route"]
    assert read["dense_audit"]["extra_pairs"] == state["archive"]["hot"] + 1
    assert read["dense_audit"]["full_current_extra_pairs"] == state["archive"]["current"] + 1
    assert state["work"]["full_audit_pairs"] == 65


def test_forgetting_is_reversible_and_versions_never_reappear(engine):
    checksum = engine.state()["archive"]["checksum"]
    total = len(engine.records)
    retired = engine.forget(128)
    assert retired["archive"]["hot"] == 0
    assert retired["archive"]["total"] == total
    assert retired["archive"]["checksum"] == checksum
    restored = engine.restore(1)
    assert restored["nodes"][0]["hot"]
    query = engine.query({"position": [0.0, 0.0], "context": 1})
    assert 0 < query["archive"]["hot"] <= engine.capacity
    assert query["work"]["cold_rows"] == 16
    old = engine.records[1]
    corrected = engine.correct(1, [0.2, 0.3])
    new_id = corrected["archive"]["total"]
    assert engine.records[1] == old
    assert engine.records[new_id]["previous"] == 1
    assert engine.records[new_id]["version"] == 2
    assert corrected["archive"]["current"] == total
    assert corrected["archive"]["total"] == total + 1
    with pytest.raises(ValueError):
        engine.restore(1)
    for _ in range(6):
        state = engine.query(
            {"position": old["position"], "context": old["context"], "action": old["action"]}
        )
        assert 1 not in state["query"]["selected_ids"]
        assert 1 not in state["query"]["index_ids"]
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        engine.db.execute("DELETE FROM observations WHERE id=1")
    engine.db.rollback()


def test_state_is_owned_and_invalid_commands_do_not_mutate(engine):
    state = engine.state()
    state["sleep"]["busy"] = True
    state["work"]["restores"] = 999
    assert not engine.sleep["busy"] and engine.work["restores"] == 0
    original = engine.state()
    for operation in (
        lambda: engine.restore(99999),
        lambda: engine.collect(True),
        lambda: engine.forget(-1),
        lambda: engine.query({"position": [float("nan"), 0]}),
        lambda: engine.query({"position": [0.0, 0.0]}, backend="unknown"),
    ):
        with pytest.raises(ValueError):
            operation()
        assert engine.state() == original


def test_lifecycle_and_model_restart_and_same_checkpoint_forks(engine, tmp_path):
    engine.query({"position": [0.2, 0.3], "context": 1})
    fork = engine.fork(tmp_path / "fork.sqlite")
    assert fork.state() == engine.state()
    initial_hash = fork.model_hash()
    canonical = fork.state()["archive"]["checksum"]
    simulator_calls = fork.work["simulator_calls"]
    fork.start_sleep("coverage", 24, [-0.3, -0.3], 0)
    for _ in range(24):
        fork.sleep_step()
    complete = fork.finish_sleep()
    assert fork.model_hash() != initial_hash
    assert engine.model_hash() == initial_hash
    assert complete["archive"]["checksum"] == canonical
    assert fork.work["simulator_calls"] == simulator_calls
    assert fork.trained_steps == 24
    for event in complete["sleep"]["trace"]:
        assert set(event["sources"]) <= set(event["read"]["selected_ids"])
        assert event["evidence"] == "observed"
        assert all(fork.records[i]["evidence"] == "observed" for i in event["sources"])
    snapshot = fork.state()
    fork.close()
    restarted = MemoryEngine(tmp_path / "fork.sqlite", bootstrap=0)
    assert restarted.state() == snapshot
    assert restarted.cursor == snapshot["query"]["work"].get("cursor", restarted.cursor)
    restarted.close()


def test_ensemble_learning_improves_unseen_continuous_states_without_simulator_calls(engine):
    evaluation = observations(901, 64, context=0)

    def mse():
        with torch.no_grad():
            predicted = torch.stack([m(model_inputs(evaluation)) for m in engine.models]).mean(0)
        return float((predicted - model_targets(evaluation)).square().mean())

    before = mse()
    engine.start_sleep("uniform", 80, [-0.3, -0.3], 0)
    calls = engine.work["simulator_calls"]
    for _ in range(80):
        engine.sleep_step()
    engine.finish_sleep()
    assert mse() < before
    assert engine.work["simulator_calls"] == calls


def test_imagination_is_predicted_and_cannot_write_observations(engine):
    checksum = engine.state()["archive"]["checksum"]
    assert len(engine.rollout([0.0, 0.0], 0)) == 1
    assert engine.sleep["rollout_status"].startswith("rejected")
    engine.start_sleep("uniform", 40, [-0.3, -0.3], 0)
    for _ in range(40):
        engine.sleep_step()
    state = engine.finish_sleep()
    for point in state["sleep"]["rollout"][1:]:
        assert point["evidence"] == "imagined"
        assert point["sources"]
        assert point["model_checkpoint"] == engine.model_hash()
        assert all(engine.records[i]["evidence"] == "observed" for i in point["sources"])
    assert engine.state()["archive"]["checksum"] == checksum
    invalid = copy.deepcopy(engine.records[1])
    invalid["evidence"] = "imagined"
    payload = {
        k: invalid[k]
        for k in (
            "position",
            "action",
            "context",
            "successor",
            "evidence",
            "source",
            "tick",
            "version",
        )
    }
    with pytest.raises(ValueError, match="observed"):
        engine._validate_observation(payload)


def test_trained_references_are_versioned_and_no_worse_on_selection_validation(engine):
    initial = engine.references.clone()
    metadata = engine.fit_router(4)
    assert metadata["validation_loss"] <= metadata["initial_validation_loss"]
    assert torch.equal(engine.random_references, initial)
    assert metadata["reference_hash"] == sha(engine.references.tolist())
    assert metadata["selected_step"] <= 4
    read = engine.query({"position": [0.2, 0.3], "context": 0})["query"]
    assert read["reference_hash"] == metadata["reference_hash"]


def test_corrupt_persisted_original_is_rejected(tmp_path):
    path = tmp_path / "bad.sqlite"
    engine = MemoryEngine(path, bootstrap=16)
    engine.close()
    db = sqlite3.connect(path)
    db.execute("DROP TRIGGER original_no_update")
    payload = json.loads(db.execute("SELECT payload FROM observations WHERE id=1").fetchone()[0])
    payload["successor"][0] += 0.01
    db.execute("UPDATE observations SET payload=? WHERE id=1", (json.dumps(payload),))
    db.commit()
    db.close()
    with pytest.raises(ValueError, match="checksum"):
        MemoryEngine(path, bootstrap=0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("position", [2.0, 0.0]),
        ("action", [True, 0.0]),
        ("context", True),
        ("evidence", "imagined"),
        ("successor", [float("inf"), 0.0]),
    ],
)
def test_invalid_external_observation_is_atomic(engine, field, value):
    observation = {
        "position": [0.1, 0.2],
        "action": [1.0, 0.0],
        "context": 0,
        "successor": [0.3, 0.2],
        "evidence": "observed",
    }
    before = engine.state()
    observation[field] = value
    with pytest.raises(ValueError):
        engine.remember(observation)
    assert engine.state() == before


def test_external_observations_are_not_unique_key_shortcuts(engine):
    before = engine.state()["archive"]["total"]
    value = {
        "position": [0.1, 0.2],
        "action": [1.0, 0.0],
        "context": 0,
        "successor": [0.3, 0.2],
        "evidence": "observed",
    }
    engine.remember(value)
    engine.remember({**value, "successor": [0.31, 0.19]})
    assert engine.state()["archive"]["total"] == before + 2
    assert engine.records[before + 1]["source"] == "user-observation"
    assert engine.records[before + 2]["previous"] is None
    assert engine.records[before + 1]["logical_key"] != engine.records[before + 2]["logical_key"]
    assert engine.work["simulator_calls"] == 64
