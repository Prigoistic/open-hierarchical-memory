from __future__ import annotations

import gzip
import hashlib
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from research.serve_task_benchmark import TaskCatalog, TaskServer


def fixture(root: Path) -> tuple[TaskCatalog, Path]:
    base = root / "experiments/boxoban-search-v1/evaluation"
    base.mkdir(parents=True)
    path = base / "sample.json.gz"
    path.write_bytes(
        gzip.compress(json.dumps({"success": False, "status": "expansion_limit"}).encode())
    )
    report = {
        "complete": True,
        "summary": [],
        "runs": [{"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}],
    }
    (base / "report.json").write_text(json.dumps(report))
    return TaskCatalog(root), path


def test_catalog_only_publishes_complete_runs(tmp_path: Path) -> None:
    catalog, path = fixture(tmp_path)
    assert catalog.run("boxoban:sample.json.gz")["status"] == "expansion_limit"
    report = path.parent / "report.json"
    value = json.loads(report.read_text())
    value["complete"] = False
    report.write_text(json.dumps(value))
    assert not catalog.catalog()["runs"]


def test_inspector_rejects_unknown_or_tampered_artifacts(tmp_path: Path) -> None:
    catalog, path = fixture(tmp_path)
    with pytest.raises(KeyError):
        catalog.run("boxoban:../../pyproject.toml")
    path.write_bytes(b"not the original artifact")
    with pytest.raises(ValueError, match="checksum"):
        catalog.run("boxoban:sample.json.gz")


def test_inspector_http_is_read_only_and_does_not_serve_arbitrary_files(tmp_path: Path) -> None:
    fixture(tmp_path)
    server = TaskServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(address + "/api/catalog") as response:
            assert len(json.load(response)["runs"]) == 1
            assert response.headers["X-Content-Type-Options"] == "nosniff"
        for suffix in [
            "/../pyproject.toml",
            "/api/run?id=../../pyproject.toml",
            "/api/run?id=a&id=b",
        ]:
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(address + suffix)
        request = urllib.request.Request(address + "/api/reset", data=b"{}", method="POST")
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        assert error.value.code == 405
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
