from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pytest
import torch

from research.dashboard_gateway import MemoryGateway
from research.serve_somna import Application, handler
from research.serve_task_benchmark import ROOT, TaskServer


@pytest.fixture
def dashboard(tmp_path):
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    web = tmp_path / "web"
    web.mkdir()
    app = Application(tmp_path / "isolated.sqlite", web)
    memory = ThreadingHTTPServer(("127.0.0.1", 0), handler(app))
    memory_thread = threading.Thread(target=memory.serve_forever, daemon=True)
    memory_thread.start()
    board = TaskServer(("127.0.0.1", 0), ROOT, memory_port=memory.server_port)
    thread = threading.Thread(target=board.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{board.server_port}"
    yield app, base
    board.shutdown()
    board.server_close()
    thread.join()
    memory.shutdown()
    memory.server_close()
    memory_thread.join()
    app.close()
    torch.set_num_threads(old)


def post(base, path, data, *, origin="same", mime="application/json"):
    headers = {"Content-Type": mime}
    if origin is not None:
        headers["Origin"] = base if origin == "same" else origin
    req = Request(base + path, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=10) as response:
            return response.status, json.load(response)
    except HTTPError as error:
        return error.code, json.load(error)


def test_one_origin_serves_dashboard_and_both_embeddable_panels(dashboard):
    _, base = dashboard
    with urlopen(base + "/") as response:
        body = response.read().decode()
        assert "Somna / Memory laboratory" in body
        assert 'id="task-frame"' in body and 'id="memory-frame"' in body
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    for path in ["/task/", "/live/"]:
        with urlopen(base + path) as response:
            assert b"panel-boot.js" in response.read()
            assert "frame-ancestors 'self'" in response.headers["Content-Security-Policy"]
    for path in [
        "/dashboard.js",
        "/dashboard.css",
        "/task/embedded.css",
        "/live/embedded.css",
        "/live/fonts/geist-regular.ttf",
    ]:
        with urlopen(base + path) as response:
            assert response.status == 200
    with pytest.raises(HTTPError):
        urlopen(base + "/live/../../research/somna_engine.py")


def test_live_query_preserves_source_archive_through_dashboard(dashboard):
    app, base = dashboard
    before = app.engine.state()["archive"]["checksum"]
    with urlopen(base + "/api/memory/state") as response:
        assert json.load(response)["archive"]["total"] == 256
    status, result = post(
        base,
        "/api/memory/query",
        json.dumps({"position": [0.1, -0.2], "context": 1, "mask": [False, True]}).encode(),
    )
    assert status == 200
    assert result["query"]["cue"]["mask"] == [False, True]
    assert result["query"]["cue"]["context"] == 1
    assert result["query"]["selected_ids"]
    assert result["archive"]["checksum"] == before
    assert app.engine.state()["archive"]["checksum"] == before


def test_dashboard_writes_reject_foreign_missing_origin_and_invalid_body(dashboard):
    app, base = dashboard
    before = app.engine.state()["revision"]
    for origin in [None, "http://outside.example", "null"]:
        assert post(base, "/api/memory/collect", b'{"count":1}', origin=origin)[0] == 403
    for data in [b"[]", b"null", b'{"position":[NaN,0]}', b"x" * 65537]:
        assert post(base, "/api/memory/query", data)[0] == 400
    assert post(base, "/api/memory/query", b"{}", mime="text/plain")[0] == 400
    assert app.engine.state()["revision"] == before


def test_task_artifacts_and_unexposed_memory_operations_remain_read_only(dashboard):
    app, base = dashboard
    before = app.engine.state()["archive"]["checksum"]
    for path in [
        "/api/reset",
        "/api/run",
        "/api/memory/reset",
        "/api/memory/remember",
        "/api/memory/query?target=outside",
        "/api/memory/../reset",
    ]:
        assert post(base, path, b"{}")[0] == 405
    assert app.engine.state()["archive"]["checksum"] == before


def test_gateway_refuses_nonlocal_configuration_and_reports_outage(monkeypatch):
    for port in [True, 1, 65536, "8791"]:
        with pytest.raises(ValueError):
            MemoryGateway(port)

    def unavailable(*args, **kwargs):
        raise URLError("test outage")

    monkeypatch.setattr("research.dashboard_gateway._LOCAL_OPENER.open", unavailable)
    status, body = MemoryGateway().request("state")
    assert status == 503 and "unavailable" in json.loads(body)["error"]
    assert MemoryGateway().request("https://outside.example")[0] == 405


@pytest.mark.parametrize(
    "status,data,limit,expected",
    [
        (200, b'{"schema":"somna-live-v1"}', 100, 200),
        (200, b'{"unexpected":"service"}', 100, 502),
        (302, b"{}", 100, 502),
        (200, b"x" * 101, 100, 502),
    ],
)
def test_gateway_rejects_wrong_protocol_redirects_and_oversized_reply(
    monkeypatch, status, data, limit, expected
):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, count):
            return data[:count]

    response = Response()
    response.status = status
    monkeypatch.setattr(
        "research.dashboard_gateway._LOCAL_OPENER.open", lambda *args, **kwargs: response
    )
    monkeypatch.setattr("research.dashboard_gateway.MAX_REPLY", limit)
    assert MemoryGateway().request("state")[0] == expected


def test_gateway_response_read_timeout_is_a_typed_unavailable_result(monkeypatch):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, count):
            raise TimeoutError("test stalled response")

    monkeypatch.setattr(
        "research.dashboard_gateway._LOCAL_OPENER.open", lambda *args, **kwargs: Response()
    )
    assert MemoryGateway().request("state")[0] == 503


def test_solve_http_origin_validation_and_incremental_cursor(dashboard):
    _, base = dashboard
    config = {
        "environment": "MiniGrid-KeyCorridorS6R3-v0",
        "reader": "progress_zha",
        "seed": 3002,
        "step_cap": 1,
    }
    body = json.dumps(config).encode()
    assert post(base, "/api/solve", body, origin=None)[0] == 403
    assert post(base, "/api/solve", body, origin="http://outside.test")[0] == 403
    assert post(base, "/api/solve", b'{"seed":true}')[0] == 400
    status, ack = post(base, "/api/solve", body)
    assert status == 200 and ack["schema"] == "somna-solve-v1"
    with urlopen(base + "/api/solve?id=" + ack["id"] + "&after=0") as response:
        page = json.load(response)
        assert page["id"] == ack["id"] and page["after"] == 0
    assert post(base, "/api/solve/cancel", json.dumps({"id": ack["id"]}).encode())[0] == 200
    with pytest.raises(HTTPError):
        urlopen(base + "/api/solve?id=unknown&after=0")
