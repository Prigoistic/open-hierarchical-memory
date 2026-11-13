"""Bounded loopback bridge for the unified UI; numerical engines remain separate."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MEMORY_WRITES = frozenset({"query", "collect", "forget", "sleep", "restore", "correct"})
MAX_BODY = 65536
MAX_REPLY = 16 * 1024 * 1024


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


_LOCAL_OPENER = build_opener(ProxyHandler({}), _NoRedirect())


class MemoryGateway:
    def __init__(self, port: int = 8791) -> None:
        if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
            raise ValueError("memory port must be a loopback service port")
        self.base = f"http://127.0.0.1:{port}"

    def request(self, operation: str, payload: bytes | None = None) -> tuple[int, bytes]:
        if (payload is None and operation != "state") or (
            payload is not None and operation not in MEMORY_WRITES
        ):
            return 405, b'{"error":"Unsupported memory operation"}'
        req = Request(
            self.base + "/api/" + operation,
            data=payload,
            headers={"Content-Type": "application/json", "Origin": self.base},
        )
        try:
            try:
                response = _LOCAL_OPENER.open(req, timeout=20)
            except HTTPError as error:
                response = error
            with response:
                status, data = response.status, response.read(MAX_REPLY + 1)
        except (URLError, TimeoutError, OSError):
            return (
                503,
                b'{"error":"Live memory service is unavailable. Start research.serve_somna on the configured memory port."}',
            )
        if 300 <= status < 400:
            return 502, b'{"error":"Live memory redirects are not accepted"}'
        if len(data) > MAX_REPLY:
            return 502, b'{"error":"Live memory response exceeds the dashboard limit"}'
        try:
            value = json.loads(data)
            if not isinstance(value, dict) or (
                status == 200 and value.get("schema") != "somna-live-v1"
            ):
                raise ValueError("object required")
            return status, json.dumps(value, allow_nan=False).encode()
        except (ValueError, UnicodeDecodeError):
            return 502, b'{"error":"Live memory returned an invalid response"}'
