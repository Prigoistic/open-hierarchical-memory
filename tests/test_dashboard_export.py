"""Static hosting keeps failures, provenance and the recorded-only boundary."""

import json
from pathlib import Path

import pytest

from scripts import export_dashboard as export


def fixture(root: Path, monkeypatch, *, passed=True):
    base = root / "experiments" / export.DATASET
    base.mkdir(parents=True)
    for name, content in {
        "INDEPENDENT_AUDIT.json": {"all_passed": passed, "runs": 1},
        "report.json": {"complete": True, "runs": [{"success": False}], "summary": []},
        "protocol.json": {"scope": "test"},
    }.items():
        (base / name).write_text(json.dumps(content))
    (root / "index.html").write_text('<html lang="en"><title>Memory instrument</title></html>')
    monkeypatch.setattr(export, "ASSETS", {"index.html": "index.html"})

    class Catalog:
        def __init__(self, root):
            pass

        def catalog(self):
            return {
                "runs": [{"dataset": export.DATASET, "uid": "../../private", "success": False}],
                "summary": [{"reader": "historical"}, {"dataset": export.DATASET}],
            }

        def run(self, uid):
            assert uid == "../../private"
            return {"result": {"success": False}, "original_source_ids": [1, 2]}

    monkeypatch.setattr(export, "TaskCatalog", Catalog)


def test_export_keeps_failed_run_and_uses_owned_hash_paths(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch)
    output = tmp_path / "output"
    result = export.export(output, tmp_path)
    site = output / ".vercel/output/static"
    catalog = json.loads((site / "data/catalog.json").read_text())
    row = catalog["runs"][0]
    assert result["runs"] == 1 and not row["success"]
    assert row["artifact"].startswith("/recordings/") and ".." not in row["artifact"]
    payload = json.loads((site / row["artifact"].lstrip("/")).read_text())
    assert not payload["result"]["success"] and payload["original_source_ids"] == [1, 2]
    assert 'data-hosted="recorded"' in (site / "index.html").read_text()
    assert not list(site.rglob("*.sqlite"))
    with pytest.raises(ValueError, match="existing"):
        export.export(output, tmp_path)


def test_unaudited_cohort_cannot_be_exported(tmp_path, monkeypatch):
    fixture(tmp_path, monkeypatch, passed=False)
    with pytest.raises(ValueError, match="audited"):
        export.export(tmp_path / "output", tmp_path)
    assert not (tmp_path / "output").exists()
