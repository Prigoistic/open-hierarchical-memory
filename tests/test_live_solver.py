from __future__ import annotations

import threading
import time

import pytest
import torch

from research.live_solver import LiveSolver, SolverBusyError
from research.run_progress_benchmark import run_episode

CONFIG = {
    "environment": "MiniGrid-KeyCorridorS6R3-v0",
    "reader": "progress_zha",
    "seed": 3002,
    "step_cap": 128,
}


def wait_done(solver, identifier):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        state = solver.snapshot(identifier, 0)
        if state["status"] != "running":
            return state
        time.sleep(0.01)
    pytest.fail("solver did not terminate")


def test_fresh_maze_evidence_is_contiguous_owned_and_references_real_routes():
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    solver = LiveSolver()
    try:
        initial = solver.start(CONFIG)
        identifier = initial["id"]
        done = wait_done(solver, identifier)
        assert done["status"] == "solved" and done["result"]["success"]
        rows, snapshots, events = [], {}, {}
        cursor = 0
        while cursor < done["available"]:
            page = solver.snapshot(identifier, cursor)
            assert page["after"] == cursor
            assert 0 < len(page["trajectory"]) <= 16
            for row in page["trajectory"]:
                assert row["step"] == len(rows)
                for ref in row["decision"]["route"]:
                    route = page["routing_events"][ref["route_ref"]]
                    assert route["snapshot_id"] in page["routing_snapshots"]
                rows.append(row)
            events.update(page["routing_events"])
            snapshots.update(page["routing_snapshots"])
            cursor = page["next"]
        assert len(rows) == 95 and rows[-1]["reward"] > 0
        assert events and snapshots
        page = solver.snapshot(identifier, 0)
        page["trajectory"][0]["decision"]["memory_ids"].append(-100)
        assert -100 not in solver.snapshot(identifier, 0)["trajectory"][0]["decision"]["memory_ids"]
        with pytest.raises(ValueError):
            solver.snapshot(identifier, cursor + 1)
        with pytest.raises(KeyError):
            solver.snapshot("not-this-run", 0)
    finally:
        solver.close()
        torch.set_num_threads(old)


def test_observer_does_not_change_solver_decisions_or_reveal_future_observations():
    packets = []

    def observe(row, snapshots, events):
        assert all(f["observed_step"] <= row["step"] for f in row["new_facts"])
        packets.append(row)

    args = (CONFIG["environment"], CONFIG["reader"], CONFIG["seed"])
    a = run_episode(*args, split="unit", step_cap=8)
    b = run_episode(*args, split="unit", step_cap=8, on_step=observe)
    assert a["archive"] == b["archive"]
    assert len(packets) == 8
    assert [r["action"] for r in a["trajectory"]] == [r["action"] for r in b["trajectory"]]
    assert [r["decision"]["memory_ids"] for r in a["trajectory"]] == [
        r["decision"]["memory_ids"] for r in b["trajectory"]
    ]


def test_one_worker_cancellation_identity_and_new_run_isolation():
    entered, release = threading.Event(), threading.Event()

    def runner(*args, on_step, **kwargs):
        entered.set()
        release.wait(3)
        try:
            on_step({"decision": {"route": []}, "new_facts": []}, {}, {})
        except Exception as error:
            return {
                "result": {
                    "success": False,
                    "error": {"type": type(error).__name__, "message": str(error)},
                }
            }
        return {"result": {"success": False, "error": None, "external_cutoff": True}}

    solver = LiveSolver(runner)
    try:
        first = solver.start(CONFIG)
        assert entered.wait(1)
        with pytest.raises(SolverBusyError):
            solver.start(CONFIG)
        with pytest.raises(KeyError):
            solver.cancel({"id": "other"})
        solver.cancel({"id": first["id"]})
        release.set()
        done = wait_done(solver, first["id"])
        assert done["status"] == "cancelled" and done["available"] == 0
        solver.worker.join()
        second = solver.start(CONFIG)
        assert second["id"] != first["id"] and second["available"] == 0
        with pytest.raises(KeyError):
            solver.snapshot(first["id"], 0)
    finally:
        release.set()
        solver.close()


@pytest.mark.parametrize(
    "key,value",
    [
        ("seed", True),
        ("seed", -1),
        ("seed", 2**31),
        ("step_cap", True),
        ("step_cap", 1025),
        ("reader", "none"),
        ("environment", "unknown"),
    ],
)
def test_invalid_start_never_creates_worker(key, value):
    solver = LiveSolver()
    with pytest.raises(ValueError):
        solver.start({**CONFIG, key: value})
    assert solver.worker is None
    solver.close()


def test_limits_and_runner_failure_are_explicit(monkeypatch):
    import research.live_solver as module

    monkeypatch.setattr(module, "MAX_TRACE_BYTES", 1)
    solver = LiveSolver()
    try:
        first = solver.start({**CONFIG, "step_cap": 1})
        done = wait_done(solver, first["id"])
        assert done["status"] == "limited" and done["reason"] == "Trace budget reached"
        assert done["available"] == 0
    finally:
        solver.close()

    def broken(*args, **kwargs):
        raise RuntimeError("deliberate worker failure")

    solver = LiveSolver(broken)
    try:
        first = solver.start(CONFIG)
        done = wait_done(solver, first["id"])
        assert done["status"] == "failed" and "deliberate" in done["reason"]
    finally:
        solver.close()


def test_cancellation_cannot_publish_a_coincident_success():
    entered, release = threading.Event(), threading.Event()

    def finishing(*args, **kwargs):
        entered.set()
        release.wait(2)
        return {"result": {"success": True, "steps": 1, "error": None}}

    solver = LiveSolver(finishing)
    try:
        ack = solver.start(CONFIG)
        assert entered.wait(1)
        solver.cancel({"id": ack["id"]})
        release.set()
        result = wait_done(solver, ack["id"])
        assert result["status"] == "cancelled"
        assert not result["result"]["success"] and result["result"]["steps"] == 0
    finally:
        release.set()
        solver.close()
