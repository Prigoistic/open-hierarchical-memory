"""Evidence mutations exercise the independent numerical/gradient auditor."""

from __future__ import annotations

import copy

import pytest
import torch

from research.run_somna_continuous import evaluate
from research.somna_engine import MemoryEngine
from scripts.audit_somna_continuous import audit_run, digest


@pytest.fixture
def run(tmp_path):
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    engine = MemoryEngine(tmp_path / "evidence.sqlite", capacity=8, bootstrap=24)
    initial = engine._weights()
    archive = engine.state()["archive"]["checksum"]
    calls = engine.work["simulator_calls"]
    engine.start_sleep("uniform", 8, [-0.3, -0.3], 0)
    for _ in range(8):
        engine.sleep_step()
    engine.finish_sleep()
    result = {
        "observations": list(engine.records.values()),
        "archive_hash": archive,
        "archive_hash_after": engine.state()["archive"]["checksum"],
        "initial_weights": initial,
        "initial_model_hash": digest(initial),
        "final_weights": engine._weights(),
        "final_model_hash": engine.model_hash(),
        "trace": copy.deepcopy(engine.sleep["trace"]),
        "gradient_steps": 8,
        "simulator_calls_before": calls,
        "simulator_calls_after": engine.work["simulator_calls"],
        "rollout": engine.sleep["rollout"],
        "evaluations": evaluate(engine, [1201]),
    }
    yield result
    engine.close()
    torch.set_num_threads(old)


def test_independent_functional_gradient_replay_accepts_real_run(run):
    assert audit_run(run)["updates"] == 8


@pytest.mark.parametrize(
    "fault",
    [
        "attention",
        "gradient",
        "source",
        "future_label",
        "loss",
        "evaluation",
        "cold_route",
        "work",
        "rollout",
    ],
)
def test_numerical_and_provenance_faults_are_detected(run, fault):
    broken = copy.deepcopy(run)
    event = broken["trace"][0]
    if fault == "attention":
        event["read"]["prediction"][0] += 0.1
    elif fault == "gradient":
        broken["final_weights"]["0.layers.0.weight"][0][0] += 0.1
        broken["final_model_hash"] = digest(broken["final_weights"])
    elif fault == "source":
        candidate = next(
            r["id"] for r in broken["observations"] if r["id"] not in event["read"]["selected_ids"]
        )
        event["sources"].append(candidate)
    elif fault == "future_label":
        event["read"]["cue"]["expected_successor"] = [0.4, 0.5]
    elif fault == "loss":
        event["loss"] += 0.1
    elif fault == "evaluation":
        evaluation = broken["evaluations"][0]
        evaluation["rows"][0]["prediction"][0] += 0.1
        evaluation["mse"] = sum(
            sum((a - b) ** 2 for a, b in zip(r["prediction"], r["target"], strict=True)) / 2
            for r in evaluation["rows"]
        ) / len(evaluation["rows"])
    elif fault == "cold_route":
        event["read"]["cold_selected_ids"].pop()
    elif fault == "work":
        event["read"]["work"]["raw_pairs"] = 0
    elif fault == "rollout":
        broken["rollout"].append(
            {
                "x": 0.9,
                "y": 0.9,
                "evidence": "imagined",
                "sources": event["sources"][:1],
                "action": [1.0, 0.0],
                "uncertainty": 0.0,
                "model_checkpoint": broken["final_model_hash"],
            }
        )
    with pytest.raises(AssertionError):
        audit_run(broken)
