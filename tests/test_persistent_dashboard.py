from __future__ import annotations

import copy
import gzip
import json
import shutil
from pathlib import Path

import pytest

from research.live_solver import LiveSolver
from research.persistent_dashboard import DATASET, ROOT, PersistentTrace, adapt_recorded
from research.run_persistent_tasks import persistent_episode
from research.serve_task_benchmark import TaskCatalog
from research.task_references import RouterCheckpoint
from research.task_store import TaskStore, WorkspaceConfig
from tests.test_live_solver import wait_done


def sample():
    path = ROOT / "experiments" / DATASET / "fitted_zha-MiniGrid-KeyCorridorS6R3-v0-9001.json.gz"
    return json.loads(gzip.decompress(path.read_bytes()))


def test_saved_adapter_retains_source_outcomes_and_checks_actual_action_replay():
    original = sample()
    before = copy.deepcopy(original)
    view = adapt_recorded(original, "persistent_zha")
    assert original == before
    assert view["result"] == original["result"] and len(view["trajectory"]) == 78
    assert view["observation_provenance"].startswith("official")
    assert view["routing_snapshots"] and view["routing_events"]
    for row, raw in zip(view["trajectory"], original["trajectory"], strict=True):
        assert row["decision"]["memory_ids"] == raw["decision"]["memory_ids"]
        assert row["decision"]["dependency"] == raw["decision"]["dependency"]
        assert len(row["observation"]["image"]) == 7
        for ref in row["decision"]["route"]:
            event = view["routing_events"][ref["route_ref"]]
            layout = view["routing_snapshots"][event["snapshot_id"]]
            assert set(event["selected_fact_ids"]) <= set(layout["index_fact_ids"])
    broken = sample()
    broken["trajectory"][0]["reward"] = 99
    with pytest.raises(ValueError, match="replay differs"):
        adapt_recorded(broken, "persistent_zha")


def test_trace_cannot_publish_cold_or_future_sources_as_active():
    value = sample()
    row = copy.deepcopy(value["trajectory"][0])
    row["decision"]["dependency"]["available_ids"].append(900000)
    with pytest.raises(ValueError, match="boundary"):
        PersistentTrace("persistent_zha").row(row)
    row = copy.deepcopy(value["trajectory"][0])
    row["new_facts"][0]["observed_step"] = 1
    with pytest.raises(ValueError, match="future"):
        PersistentTrace("persistent_zha").row(row)
    row = copy.deepcopy(value["trajectory"][0])
    row["decision"]["route"][0]["index_fact_ids"][-1] = 900000
    with pytest.raises(ValueError, match="mapping"):
        PersistentTrace("persistent_zha").row(row)


def test_persistent_observer_does_not_change_actions_sources_or_store_state(tmp_path):
    checkpoint = RouterCheckpoint.fixed()
    packets = []
    args = ("MiniGrid-DoorKey-16x16-v0", 9001, checkpoint, "zha", 8)
    a = persistent_episode(tmp_path / "a.sqlite", *args)
    b = persistent_episode(tmp_path / "b.sqlite", *args, on_step=packets.append)
    assert a["archive"] == b["archive"]
    assert a["controller_state"] == b["controller_state"]
    assert len(packets) == 8
    assert [r["action"] for r in a["trajectory"]] == [r["action"] for r in b["trajectory"]]
    assert [r["decision"]["memory_ids"] for r in a["trajectory"]] == [
        r["decision"]["memory_ids"] for r in b["trajectory"]
    ]


def checkpoint_root(root: Path):
    dest = root / "experiments" / DATASET
    dest.mkdir(parents=True)
    shutil.copy(ROOT / "experiments" / DATASET / "fitted-references.json", dest)


def test_fresh_persistent_solver_uses_fitted_checkpoint_and_retains_reopenable_archive(tmp_path):
    checkpoint_root(tmp_path)
    solver = LiveSolver(root=tmp_path)
    try:
        ack = solver.start(
            {
                "environment": "MiniGrid-KeyCorridorS6R3-v0",
                "reader": "persistent_zha",
                "seed": 9001,
                "step_cap": 128,
            }
        )
        done = wait_done(solver, ack["id"])
        assert done["status"] == "solved" and done["available"] == 78
        assert done["memory"]["reference_kind"] == "fitted"
        assert done["memory"]["restart_state_equal"] and done["memory"]["active"] <= 96
        directory = tmp_path / "var/task-solves" / ack["id"]
        checkpoint = RouterCheckpoint.load(directory / "references.json")
        store = TaskStore(directory / "memory.sqlite", config=WorkspaceConfig(), router=checkpoint)
        assert store.count == done["memory"]["originals"]
        store.close()
        assert json.loads((directory / "result.json").read_text())["result"]["success"]
        rows = []
        while len(rows) < done["available"]:
            page = solver.snapshot(ack["id"], len(rows))
            for row in page["trajectory"]:
                assert row["decision"]["dependency"]["reference_hash"] == checkpoint.sha256
                for ref in row["decision"]["route"]:
                    event = page["routing_events"][ref["route_ref"]]
                    assert event["snapshot_id"] in page["routing_snapshots"]
            rows += page["trajectory"]
        assert any(r["decision"]["dependency"]["recovered_ids"] for r in rows)
        assert any(r["decision"]["dependency"]["evicted_ids"] for r in rows)
        assert any(
            r["decision"]["dependency"]["recovery_status"] == "deferred_active_progress"
            and not r["decision"]["route"]
            for r in rows
        )
    finally:
        solver.close()


def test_training_context_and_missing_checkpoint_fail_before_worker_creation(tmp_path):
    checkpoint_root(tmp_path)
    solver = LiveSolver(root=tmp_path)
    config = {
        "environment": "MiniGrid-DoorKey-16x16-v0",
        "reader": "persistent_zha",
        "seed": 0,
        "step_cap": 8,
    }
    with pytest.raises(ValueError, match="fit/select"):
        solver.start(config)
    assert solver.worker is None
    solver.close()
    (tmp_path / "experiments" / DATASET / "fitted-references.json").unlink()
    solver = LiveSolver(root=tmp_path)
    with pytest.raises(ValueError, match="checkpoint is unavailable"):
        solver.start({**config, "seed": 9001})
    assert solver.worker is None
    solver.close()


def test_catalog_exposes_complete_persistent_cohort_and_preserves_original_files():
    catalog = TaskCatalog()
    rows = [r for r in catalog.catalog()["runs"] if r["dataset"] == DATASET]
    assert len(rows) == 48 and len({r["uid"] for r in rows}) == 48
    chosen = next(r for r in rows if r["reader"] == "persistent_zha")
    path = ROOT / "experiments" / DATASET / chosen["file"]
    before = path.read_bytes()
    view = catalog.run(chosen["uid"])
    assert view["reader"] == "persistent_zha" and view["task"] == "minigrid"
    assert path.read_bytes() == before


def test_published_capacity_transitions_exclude_superseded_versions():
    source = sample()
    view = adapt_recorded(source, "persistent_zha")
    previous = set()
    heads = {}
    for row in view["trajectory"]:
        for f in row["new_facts"]:
            heads[(f["x"], f["y"])] = f["id"]
        current = set(heads.values())
        active = set(row["decision"]["dependency"]["available_ids"])
        evicted = set(row["lifecycle"]["capacity_evicted_ids"])
        assert (previous - active) & current <= evicted | set(row["retired_ids"])
        assert not set(row["lifecycle"]["superseded_active_ids"]) & current
        previous = active
    # Observation admission evictions are visible even when archive recovery is idle.
    assert any(
        r["lifecycle"]["capacity_evicted_ids"] and not r["decision"]["dependency"]["recovered_ids"]
        for r in view["trajectory"]
    )
