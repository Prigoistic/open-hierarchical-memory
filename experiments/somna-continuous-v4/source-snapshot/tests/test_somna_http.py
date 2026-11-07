"""Real loopback requests exercise asynchronous jobs and request boundaries."""

from __future__ import annotations

import json
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
import torch

from research.serve_somna import Application, handler


@pytest.fixture
def api(tmp_path):
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>Test inspector</title>")
    app = Application(tmp_path / "memory.sqlite", web)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler(app))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield app, f"http://127.0.0.1:{server.server_port}"
    if app.worker is not None:
        app.worker.join(timeout=20)
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()
    app.engine.close()
    torch.set_num_threads(old)


def request(base, path, data=None, origin=None):
    headers = {"Content-Type": "application/json"}
    if origin is not None:
        headers["Origin"] = origin
    req = Request(
        base + path, data=None if data is None else json.dumps(data).encode(), headers=headers
    )
    try:
        with urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def test_real_http_query_validation_and_static_boundary(api):
    app, base = api
    status, initial = request(base, "/api/state")
    assert status == 200 and initial["archive"]["total"] == 256
    status, queried = request(
        base, "/api/query", {"position": [0.1, 0.2], "context": 1, "mask": [False, True]}
    )
    assert status == 200 and queried["query"]["route"]
    assert queried["query"]["dense_audit"]["extra_pairs"] > 0
    for payload in ({"id": 1}, {"position": [float("nan"), 0.0]}, {"mask": [1, True]}):
        assert request(base, "/api/query", payload)[0] == 400
    assert request(base, "/api/forget", {"steps": 10}, origin="https://outside.example")[0] == 403
    assert request(base, "/../../memory.sqlite")[0] == 404
    assert app.engine.state()["archive"]["total"] == 256
    assert request(base, "/api/forget", {"steps": 128})[1]["archive"]["hot"] == 0
    assert request(base, "/api/restore", {"id": 1})[0] == 200
    assert request(base, "/api/state")[1]["archive"]["hot"] == 1


def test_async_offline_job_exposes_real_intermediate_progress(api):
    app, base = api
    initial_hash = app.engine.model_hash()
    status, starting = request(
        base,
        "/api/sleep",
        {"strategy": "uniform", "steps": 80, "position": [-0.3, -0.3], "context": 0},
    )
    assert status == 200 and starting["sleep"]["busy"]
    lengths = []
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        _, state = request(base, "/api/state")
        lengths.append(len(state["sleep"]["trace"]))
        if not state["sleep"]["busy"]:
            break
        time.sleep(0.01)
    assert not state["sleep"]["busy"], state["sleep"]
    assert state["sleep"]["status"] == "complete"
    assert state["sleep"]["error"] is None
    assert state["model"]["trained_steps"] == 80
    assert state["model"]["checkpoint_hash"] != initial_hash
    assert lengths == sorted(lengths)
    assert any(0 < n < 80 for n in lengths), lengths
    assert len(state["sleep"]["rollout"]) > 1


def test_busy_job_rejects_other_mutations_without_losing_originals(api):
    app, _ = api
    initial = app.engine.state()["archive"]
    app.engine.start_sleep("uniform", 1, [0.0, 0.0], 0)
    for endpoint, data in (
        ("/api/reset", {"seed": 2}),
        ("/api/collect", {"count": 1}),
        ("/api/query", {"position": [0.0, 0.0]}),
    ):
        with pytest.raises(RuntimeError, match="running"):
            app.operation(endpoint, data)
    assert app.engine.state()["archive"] == initial
    app.engine.fail_sleep("test cancellation")


def test_reset_resumes_the_active_session_on_the_same_launch_path(tmp_path):
    archive = tmp_path / "default.sqlite"
    web = tmp_path / "web"
    web.mkdir()
    app = Application(archive, web)
    app.operation("/api/reset", {"seed": 19})
    app.operation(
        "/api/remember",
        {
            "position": [0.1, 0.2],
            "action": [1.0, 0.0],
            "context": 0,
            "successor": [0.2, 0.3],
            "evidence": "observed",
        },
    )
    app.operation(
        "/api/sleep", {"strategy": "uniform", "steps": 8, "position": [0.0, 0.0], "context": 0}
    )
    app.worker.join(timeout=10)
    expected = app.engine.state()
    active = app.engine.path
    app.engine.close()
    restarted = Application(archive, web)
    assert restarted.engine.seed == 19
    assert restarted.engine.path == active
    assert restarted.engine.state() == expected
    assert restarted.latest_state["session"]["active_archive"] == str(active)
    assert restarted.latest_state["session"]["configured_archive"] == str(archive)
    assert archive.exists() and active.exists()
    restarted.engine.close()


def test_pointer_write_failure_restores_the_previous_controller(tmp_path, monkeypatch):
    archive = tmp_path / "default.sqlite"
    web = tmp_path / "web"
    web.mkdir()
    app = Application(archive, web)
    expected = app.engine.state()

    def fail_replace(*args):
        raise OSError("injected pointer failure")

    monkeypatch.setattr("research.serve_somna.os.replace", fail_replace)
    with pytest.raises(OSError, match="injected"):
        app.operation("/api/reset", {"seed": 19})
    assert app.engine.path == archive
    assert app.engine.state() == expected
    assert not app.pointer.exists()
    app.engine.close()
