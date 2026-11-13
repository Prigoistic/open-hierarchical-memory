"""Loopback-only Somna live inspector API with serialized writes and real jobs."""

from __future__ import annotations

import argparse
import fcntl
import json
import mimetypes
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import torch

from research.somna_engine import MemoryEngine, bounded_int, sha
from research.somna_world import context_value, pair

ROOT = Path(__file__).resolve().parents[1]


class Application:
    def __init__(self, archive: Path, web: Path, *, seed: int = 7) -> None:
        self.archive = archive
        self.web = web.resolve()
        self.lock = threading.RLock()
        self.namespace_lock = archive.with_suffix(archive.suffix + ".session.lock").open("a+b")
        try:
            fcntl.flock(self.namespace_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.namespace_lock.close()
            raise ValueError("configured session already has an active controller") from error
        self._closed = False
        self._stop_event = threading.Event()
        try:
            self.initialize_session(archive, seed)
        except BaseException:
            self.namespace_lock.close()
            raise

    def initialize_session(self, archive: Path, seed: int) -> None:
        self.pointer = archive.with_suffix(archive.suffix + ".active.json")
        active = archive
        self.resets = 0
        if self.pointer.exists():
            if self.pointer.stat().st_size > 4096:
                raise ValueError("active-session pointer exceeds supported size")
            descriptor = json.loads(self.pointer.read_text())
            if (
                set(descriptor) != {"format", "filename", "resets", "checksum"}
                or descriptor["format"] != "somna-active-v1"
            ):
                raise ValueError("unsupported active-session pointer")
            checksum = descriptor.pop("checksum")
            if sha(descriptor) != checksum:
                raise ValueError("active-session pointer checksum mismatch")
            filename = descriptor["filename"]
            if (
                not isinstance(filename, str)
                or Path(filename).name != filename
                or not filename.startswith(archive.stem + "-reset-")
                or not filename.endswith(".sqlite")
            ):
                raise ValueError("active-session pointer must name an owned reset archive")
            active = archive.with_name(filename)
            if not active.is_file():
                raise ValueError(
                    "active archive is missing; refusing to silently resume older data"
                )
            self.resets = bounded_int(descriptor["resets"], "resets", 1, 32)
        self.engine = MemoryEngine(active, seed=seed)
        self.latest_state = self.publish(self.engine.state())
        self.worker: threading.Thread | None = None

    def publish(self, state: dict[str, Any]) -> dict[str, Any]:
        state["session"] = {
            "configured_archive": str(self.archive),
            "active_archive": str(self.engine.path),
            "resets": self.resets,
        }
        self.latest_state = state
        return state

    def persist_active(self, destination: Path, resets: int) -> None:
        descriptor = {"format": "somna-active-v1", "filename": destination.name, "resets": resets}
        payload = {**descriptor, "checksum": sha(descriptor)}
        temporary = self.pointer.with_name(self.pointer.name + f".tmp-{time.time_ns()}")
        try:
            with temporary.open("x") as stream:
                json.dump(payload, stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.pointer)
        finally:
            temporary.unlink(missing_ok=True)

    def run_sleep(self, steps: int) -> None:
        try:
            with self.lock:
                if self.engine.router_fit["steps"] == 0 and len(self.engine.heads) >= 16:
                    self.engine.fit_router(8)
                self.publish(self.engine.state())
            for _ in range(steps):
                if self._stop_event.is_set():
                    with self.lock:
                        self.engine.fail_sleep("Application closed; completed updates retained")
                        self.publish(self.engine.state())
                    return
                with self.lock:
                    self.engine.sleep_step()
                    self.publish(self.engine.state())
                time.sleep(0)  # Yield the CPU; no artificial simulation time or progress.
            with self.lock:
                self.publish(self.engine.finish_sleep())
        except Exception as error:
            traceback.print_exc()
            with self.lock:
                self.engine.fail_sleep(str(error))
                self.publish(self.engine.state())

    def operation(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "/api/query": {"position", "mask", "context", "action", "audit"},
            "/api/remember": {"position", "action", "context", "successor", "evidence"},
            "/api/collect": {"count", "context"},
            "/api/forget": {"steps"},
            "/api/restore": {"id"},
            "/api/correct": {"id", "successor"},
            "/api/sleep": {"strategy", "steps", "position", "context"},
            "/api/reset": {"seed"},
        }
        if path not in allowed or set(data) - allowed[path]:
            raise ValueError("unknown endpoint or unsupported request fields")
        with self.lock:
            if self._stop_event.is_set():
                raise RuntimeError("application is closing")
            if self.engine.sleep["busy"]:
                raise RuntimeError(
                    "offline job is running; wait for completion before mutating memory"
                )
            if path == "/api/query":
                return self.publish(self.engine.query(data))
            if path == "/api/remember":
                return self.publish(self.engine.remember(data))
            if path == "/api/collect":
                return self.publish(self.engine.collect(data.get("count", 32), data.get("context")))
            if path == "/api/forget":
                return self.publish(self.engine.forget(data.get("steps", 40)))
            if path == "/api/restore":
                return self.publish(
                    self.engine.restore(bounded_int(data.get("id"), "id", 1, 2**31 - 1))
                )
            if path == "/api/correct":
                return self.publish(
                    self.engine.correct(
                        bounded_int(data.get("id"), "id", 1, 2**31 - 1),
                        pair(data.get("successor"), "successor"),
                    )
                )
            if path == "/api/reset":
                seed = bounded_int(data.get("seed", 7), "seed", 0, 2**31 - 1)
                if self.resets >= 32:
                    raise ValueError(
                        "session reset limit32 reached; restart with a new archive path"
                    )
                destination = self.archive.with_name(
                    f"{self.archive.stem}-reset-{time.time_ns()}.sqlite"
                )
                replacement = MemoryEngine(destination, seed=seed)
                original = self.engine
                original.close()
                try:
                    self.persist_active(destination, self.resets + 1)
                except BaseException:
                    replacement.close()
                    self.engine = MemoryEngine(original.path, bootstrap=0)
                    raise
                self.engine = replacement
                self.resets += 1
                return self.publish(self.engine.state())
            steps = bounded_int(data.get("steps", 80), "steps", 1, 320)
            position = pair(data.get("position", [-0.3, -0.3]), "position")
            context = context_value(data.get("context", 0))
            assert context is not None
            self.engine.start_sleep(data.get("strategy", "mixture"), steps, position, context)
            self.worker = threading.Thread(target=self.run_sleep, args=(steps,), daemon=True)
            self.worker.start()
            return self.publish(self.engine.state())

    def close(self) -> None:
        self._stop_event.set()
        if self.worker is not None:
            self.worker.join(timeout=30)
            if self.worker.is_alive():
                raise RuntimeError(
                    "offline worker has not stopped; configured-session lock is retained"
                )
        with self.lock:
            if self._closed:
                return
            try:
                self.engine.close()
            finally:
                self.namespace_lock.close()
                self._closed = True


def handler(application: Application) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def respond(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            route = urlparse(self.path).path
            if route == "/api/state":
                self.respond(200, application.latest_state)
                return
            target = application.web / ("index.html" if route == "/" else route.lstrip("/"))
            if (
                not target.resolve().is_relative_to(application.web)
                or not target.is_file()
                or target.suffix not in (".html", ".css", ".js", ".woff2", ".ttf", ".svg", ".png")
            ):
                self.respond(404, {"error": "file not found"})
                return
            body = target.read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                self.respond(403, {"error": "cross-origin writes are not accepted"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if (
                    not 0 < length <= 65536
                    or self.headers.get("Content-Type", "").split(";")[0] != "application/json"
                ):
                    raise ValueError("request must be JSON and at most64KiB")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("request must be a JSON object")
                self.respond(200, application.operation(urlparse(self.path).path, data))
            except (ValueError, KeyError) as error:
                self.respond(400, {"error": str(error)})
            except RuntimeError as error:
                self.respond(409, {"error": str(error)})
            except Exception:
                traceback.print_exc()
                self.respond(
                    500, {"error": "internal operation failed; details are in the local server log"}
                )

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("/private/tmp/somna-live.sqlite"))
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--web", type=Path, default=ROOT / "web/somna-live")
    args = parser.parse_args()
    bounded_int(args.port, "port", 1024, 65535)
    torch.set_num_threads(1)
    application = Application(args.archive, args.web, seed=args.seed)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(application))
    print(f"Somna live API: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    finally:
        application.close()
        server.server_close()


if __name__ == "__main__":
    main()
