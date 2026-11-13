"""Catalog integrity, cohort controls and live support integration."""

from __future__ import annotations

import json
import shutil

from research.persistent_dashboard import ROOT, active_capacity_for, checkpoint_for, run_solve
from research.serve_task_benchmark import TaskCatalog
from research.task_memory.presentation import DATASET, catalog, metadata


def test_catalog_requires_complete_independently_audited_support_cohort(tmp_path):
    source = ROOT / "experiments" / DATASET
    target = tmp_path / "experiments" / DATASET
    target.mkdir(parents=True)
    for n in ("report.json", "protocol.json"):
        shutil.copy(source / n, target / n)
    assert catalog(tmp_path) == ([], [])
    shutil.copy(source / "INDEPENDENT_AUDIT.json", target / "INDEPENDENT_AUDIT.json")
    rows, summary = catalog(tmp_path)
    assert len(rows) == 120 and len(summary) == 20
    r = json.loads((target / "report.json").read_text())
    r["runs"].append(r["runs"][0])
    (target / "report.json").write_text(json.dumps(r))
    assert catalog(tmp_path) == ([], [])


def test_study_metadata_and_source_bound_memory_survive_catalog_adaptation():
    rows, _ = catalog(ROOT)
    r = next(
        r
        for r in rows
        if r["condition"] == "connected_zha" and r["environment"] == "MiniGrid-DoorKey-16x16-v0"
    )
    run = TaskCatalog().run(r["uid"])
    assert run["capacity"] == 64 and run["support_study"]["outcome"]["successes"] == 22
    assert run["support_study"]["graph_control"]["successes"] == 22
    assert all(t["decision"]["dependency"]["active_capacity"] == 64 for t in run["trajectory"])
    assert metadata(ROOT, "parent")["outcome"]["successes"] == 15


def test_live_support_reader_uses_same64_capacity_and_actual_source_receipts(tmp_path):
    packets = []
    method = "persistent_support_connected_zha"
    cp = checkpoint_for(method)
    result = run_solve(
        "MiniGrid-DoorKey-16x16-v0",
        method,
        19002,
        path=tmp_path / "run" / "memory.sqlite",
        checkpoint=cp,
        step_cap=128,
        on_step=lambda row, *_: packets.append(row),
    )
    assert result["result"]["success"] and len(packets) == result["result"]["steps"]
    assert result["memory"]["active_capacity"] == 64
    assert any(t["decision"]["dependency"]["connector"]["attempted"] for t in packets)
    assert all(
        set(t["decision"]["memory_ids"]) <= set(t["decision"]["dependency"]["available_ids"])
        for t in packets
    )
    assert active_capacity_for("persistent_zha") == 96 and active_capacity_for(method) == 64
