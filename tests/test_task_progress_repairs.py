"""Behavioral regressions for occupied hands and bounded path admission."""

import copy
from pathlib import Path

import pytest
import torch

from research.minigrid_benchmark import Fact, ObservationPlanner
from research.run_persistent_tasks import persistent_episode
from research.task_memory.run_study import layout_identity
from research.task_memory.support import SupportTaskReader
from research.task_references import RouterCheckpoint
from research.task_store import WorkspaceConfig
from scripts.audit_task_support import audit_episode


def test_occupied_hands_seek_a_reachable_drop_site_instead_of_futile_pickup():
    cells = [
        Fact(i + 1, x, y, obj, 0, 0, 0, 0)
        for i, (x, y, obj) in enumerate(
            [(0, 0, 1), (1, 0, 6), (-1, 0, 1), (-2, 0, 1), (0, 1, 2), (0, -1, 2)]
        )
    ]
    view = {f.position: f for f in cells}
    actor = ObservationPlanner("none", progress_repairs=True)
    actor.direction = 0
    action, objective, *_ = actor._plan(view, (5, 0), "pick up the red ball")
    assert action != 3 and objective == "drop-for-pickup"
    # No reachable vacancy: report a scan, never a successful-looking pickup.
    view = {p: f for p, f in view.items() if p[0] >= 0}
    action, objective, *_ = actor._plan(view, (5, 0), "pick up the red ball")
    assert action == 1 and objective == "scan-for-drop-space"


@pytest.mark.parametrize("seed,expected", [(23003, 99), (23005, 151)])
def test_exposed_key_corridor_failures_complete_with_audited_bounded_evidence(
    tmp_path, seed, expected
):
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        cp = RouterCheckpoint.load(Path("experiments/persistent-task-v2/fitted-references.json"))
        e = persistent_episode(
            tmp_path / "episode.sqlite",
            "MiniGrid-KeyCorridorS6R3-v0",
            seed,
            cp,
            "zha",
            256,
            workspace=WorkspaceConfig(capacity=64, recovery_limit=16),
            reader_factory=lambda s, c: SupportTaskReader(s, c, progress_repairs=True),
            progress_repairs=True,
        )
        assert e["result"]["success"] and e["result"]["steps"] == expected
        assert all(
            not (r["action"] == 3 and r["decision"]["inventory"] is not None)
            for r in e["trajectory"]
        )
        e["condition"] = "repaired_zha"
        e["evaluator_layout_identity"] = layout_identity(e["environment_id"], seed)
        result = audit_episode(e, {**cp.payload(), "sha256": cp.sha256})
        assert result["decisions"] == expected
        if seed == 23005:
            assert any(
                t["decision"]["objective"] == "follow-observed-waypoint" for t in e["trajectory"]
            )
            bad = copy.deepcopy(e)
            receipt = next(
                t["decision"]["dependency"]
                for t in bad["trajectory"]
                if t["decision"]["dependency"]["waypoint_id"]
            )
            receipt["waypoint_id"] = 999999
            with pytest.raises(AssertionError, match="waypoint"):
                audit_episode(bad, {**cp.payload(), "sha256": cp.sha256}, official=False)
    finally:
        torch.set_num_threads(old)
