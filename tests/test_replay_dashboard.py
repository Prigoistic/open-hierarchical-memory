from __future__ import annotations

import json
import shutil

import pytest

from research.persistent_dashboard import ROOT
from research.replay_dashboard import DATASET, catalog, metadata
from research.serve_task_benchmark import TaskCatalog


def test_replay_catalog_requires_complete_audited_cohort(tmp_path):
    source = ROOT / "experiments" / DATASET
    target = tmp_path / "experiments" / DATASET
    target.mkdir(parents=True)
    for name in ("report.json", "protocol.json"):
        shutil.copy(source / name, target / name)
    assert catalog(tmp_path) == ([], [])
    shutil.copy(source / "INDEPENDENT_AUDIT.json", target / "INDEPENDENT_AUDIT.json")
    rows, summary = catalog(tmp_path)
    assert len(rows) == 240 and summary
    value = json.loads((target / "report.json").read_text())
    value["runs"].pop()
    (target / "report.json").write_text(json.dumps(value))
    assert catalog(tmp_path) == ([], [])


def test_recorded_replay_view_uses_real_capacity_and_keeps_training_worlds_separate():
    c = TaskCatalog()
    rows = [r for r in c.catalog()["runs"] if r["dataset"] == DATASET]
    row = next(r for r in rows if r["condition"] == "uniform-7")
    view = c.run(row["uid"])
    assert view["capacity"] == 64
    learning = view["replay"]["learning"]
    assert learning["steps"] == 64 and len(learning["sources"]) == 64
    assert all(str(row["seed"]) not in s["context"] for s in learning["sources"])
    assert view["replay"]["outcome"]["successes"] == 11
    assert view["replay"]["outcome"]["episodes"] == 16
    assert all(r["decision"]["dependency"]["active_capacity"] == 64 for r in view["trajectory"])
    assert metadata(ROOT, "exact")["learning"] is None
    assert metadata(ROOT, "parent-cap96")["outcome"]["capacity"] == 96


def test_replay_curve_cannot_silently_load_a_tampered_learning_trace(tmp_path):
    source = ROOT / "experiments" / DATASET
    target = tmp_path / "experiments" / DATASET
    target.mkdir(parents=True)
    for name in ("report.json", "quality.json", "parent-references.json", "learning.json"):
        shutil.copy(source / name, target / name)
    run = next(
        r
        for r in json.loads((target / "learning.json").read_text())["runs"]
        if r["condition"] == "uniform-7"
    )
    (target / run["file"]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        metadata(tmp_path, "uniform-7")
