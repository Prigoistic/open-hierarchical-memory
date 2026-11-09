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


@pytest.mark.parametrize("dataset", ["dependency-evaluation-v1", "progress-evaluation-v1"])
def test_dependency_catalog_requires_complete_declared_cohort(tmp_path: Path, dataset: str) -> None:
    base = tmp_path / "experiments" / dataset
    base.mkdir(parents=True)
    path = base / "episode-example.json.gz"
    path.write_bytes(
        gzip.compress(
            json.dumps(
                {
                    "result": {"success": False},
                    "trajectory": [],
                    "seed": 2001,
                    "reader": "bundle_zha",
                    "costs": {"episode_seconds": 0.1},
                }
            ).encode()
        )
    )
    report = {
        "protocol": {
            "selected_environments": ["MiniGrid-KeyCorridorS6R3-v0"],
            "selected_readers": ["bundle_zha"],
            "selected_seeds": [2001, 2002],
            "external_step_cap": 4096,
        },
        "summaries": [],
        "episodes": [
            {
                "trace_file": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "environment_id": "MiniGrid-KeyCorridorS6R3-v0",
                "seed": 2001,
                "reader": "bundle_zha",
                "steps": 0,
                "costs": {
                    "episode_seconds": 0.1,
                    "raw_attention_pairs": 0,
                    "exact_score_pairs": 0,
                    "rerank_pairs": 0,
                    "summary_dot_products": 0,
                },
            }
        ],
    }
    target = base / "report.json"
    target.write_text(json.dumps(report))
    catalog = TaskCatalog(tmp_path)
    assert catalog.catalog()["runs"] == []
    report["episodes"] *= 2
    target.write_text(json.dumps(report))
    assert catalog.catalog()["runs"] == []  # Duplicate seed cannot fill missing cohort member.
    report["episodes"] = report["episodes"][:1]
    report["protocol"]["selected_seeds"] = [2001]
    target.write_text(json.dumps(report))
    row = catalog.catalog()["runs"][0]
    result = catalog.run(row["uid"])
    assert result["dataset"] == dataset
    assert result["config"] == "bundle_zha" and result["success"] is False
    path.write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="checksum"):
        catalog.run(row["uid"])


def test_inspector_enforces_expanded_bound_even_for_checksummed_gzip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    catalog, path = fixture(tmp_path)
    actual_size = len(gzip.decompress(path.read_bytes()))
    monkeypatch.setattr("research.serve_task_benchmark.MAX_EXPANDED_TRACE_BYTES", actual_size)
    assert catalog.run("boxoban:sample.json.gz")["success"] is False
    monkeypatch.setattr("research.serve_task_benchmark.MAX_EXPANDED_TRACE_BYTES", actual_size - 1)
    with pytest.raises(ValueError, match="expanded artifact too large"):
        catalog.run("boxoban:sample.json.gz")


def test_oversized_trace_http_response_explains_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, path = fixture(tmp_path)
    monkeypatch.setattr(
        "research.serve_task_benchmark.MAX_EXPANDED_TRACE_BYTES",
        len(gzip.decompress(path.read_bytes())) - 1,
    )
    server = TaskServer(("127.0.0.1", 0), tmp_path)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}/api/run?id=boxoban:sample.json.gz"
            )
        assert error.value.code == 413
        assert "compact evaluation" in json.load(error.value)["error"]
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def test_inspector_serves_only_bundled_visual_assets(tmp_path: Path) -> None:
    fixture(tmp_path)
    web = tmp_path / "web/task-lab"
    web.mkdir(parents=True)
    (web / "spatial.bundle.js").write_bytes(b"bundled visual renderer")
    (web / "spatial.css").write_bytes(b".spatial-stage{}")
    server = TaskServer(("127.0.0.1", 0), tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = f"http://127.0.0.1:{server.server_port}"
    try:
        for path, content, mime in [
            ("/spatial.bundle.js", b"bundled visual renderer", "text/javascript"),
            ("/spatial.css", b".spatial-stage{}", "text/css"),
        ]:
            with urllib.request.urlopen(address + path) as response:
                assert response.read() == content
                assert response.headers["Content-Type"] == mime
                assert response.headers["X-Content-Type-Options"] == "nosniff"
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(address + "/web/visuals/node_modules/three/package.json")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
