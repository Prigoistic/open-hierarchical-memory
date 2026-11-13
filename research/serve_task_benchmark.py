"""Unified local dashboard: read-only task evidence and a bounded live-memory bridge."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from research import replay_dashboard
from research.dashboard_gateway import MAX_BODY, MEMORY_WRITES, MemoryGateway
from research.live_solver import LiveSolver, SolverBusyError
from research.persistent_dashboard import DATASET, METHODS, adapt_recorded
from research.task_memory import presentation as support_presentation

ROOT = Path(__file__).resolve().parents[1]
MAX_EXPANDED_TRACE_BYTES = 128 * 1024 * 1024


class TraceTooLargeError(ValueError):
    """A valid local artifact exceeds the bounded viewer transport."""


class TaskCatalog:
    def __init__(self, root: Path = ROOT):
        self.root = root

    def catalog(self) -> dict[str, Any]:
        runs: list[dict[str, Any]] = []
        summaries: list[dict[str, Any]] = []
        path = self.root / "experiments/boxoban-search-v1/evaluation/report.json"
        if path.exists():
            report = json.loads(path.read_text())
            if report.get("complete"):
                runs.extend(
                    {
                        **r,
                        "uid": "boxoban:" + r["file"],
                        "task": "boxoban",
                        "dataset": "boxoban-search-v1",
                    }
                    for r in report["runs"]
                )
                summaries.extend({"task": "boxoban", **r} for r in report["summary"])
        reports = [
            *(self.root / "experiments").glob("minigrid-*/report.json"),
            *(self.root / "experiments").glob("dependency-*/report.json"),
            *(self.root / "experiments").glob("progress-*/report.json"),
        ]
        for path in sorted(reports):
            report = json.loads(path.read_text())
            if "episodes" not in report or "protocol" not in report:
                continue
            protocol = report["protocol"]
            if not all(
                k in protocol
                for k in (
                    "selected_environments",
                    "selected_readers",
                    "selected_seeds",
                    "external_step_cap",
                )
            ):
                continue
            expected = (
                len(protocol["selected_environments"])
                * len(protocol["selected_readers"])
                * len(protocol["selected_seeds"])
            )
            identities = {(r["environment_id"], r["reader"], r["seed"]) for r in report["episodes"]}
            declared = {
                (environment, reader, seed)
                for environment in protocol["selected_environments"]
                for reader in protocol["selected_readers"]
                for seed in protocol["selected_seeds"]
            }
            if len(report["episodes"]) != expected or identities != declared:
                continue
            dataset = path.parent.name
            for r in report["episodes"]:
                costs = r["costs"]
                runs.append(
                    {
                        **r,
                        "uid": "minigrid:" + dataset + ":" + r["trace_file"],
                        "task": "minigrid",
                        "dataset": dataset,
                        "file": r["trace_file"],
                        "split": r["environment_id"] + "/" + dataset,
                        "level_id": r["seed"],
                        "config": r["reader"],
                        "expansion_limit": protocol["external_step_cap"],
                        "expanded": r["steps"],
                        "pushes": None,
                        "wall_seconds": costs["episode_seconds"],
                        "read_work": {
                            "raw_key_scores": costs["raw_attention_pairs"]
                            + costs["exact_score_pairs"]
                            + costs["rerank_pairs"],
                            "summary_dot_products": costs["summary_dot_products"],
                        },
                    }
                )
            summaries.extend(
                {"task": "minigrid", "dataset": dataset, **r} for r in report["summaries"]
            )
        path = self.root / "experiments" / DATASET / "report.json"
        if path.exists():
            report = json.loads(path.read_text())
            protocol = json.loads(path.with_name("protocol.json").read_text())
            persistent_expected = {
                (c, e, seed)
                for c in protocol["conditions"]
                for e in protocol["environments"]
                for seed in protocol["comparison_seeds"]
            }
            actual = {(r["condition"], r["environment"], r["seed"]) for r in report["runs"]}
            if (
                report.get("complete")
                and actual == persistent_expected
                and len(report["runs"]) == len(persistent_expected)
            ):
                method_for = {spec[0]: name for name, spec in METHODS.items()}
                for r in report["runs"]:
                    costs = r["costs"]
                    runs.append(
                        {
                            **r,
                            "uid": "minigrid:" + DATASET + ":" + r["file"],
                            "task": "minigrid",
                            "dataset": DATASET,
                            "environment_id": r["environment"],
                            "reader": method_for[r["condition"]],
                            "config": method_for[r["condition"]],
                            "split": r["environment"] + "/" + DATASET,
                            "level_id": r["seed"],
                            "expansion_limit": protocol["step_cap"],
                            "expanded": r["steps"],
                            "pushes": None,
                            "wall_seconds": None,
                            "read_work": {
                                "raw_key_scores": costs["archive_raw_pairs"]
                                + costs["archive_rerank_pairs"],
                                "summary_dot_products": costs["archive_summary_dot_products"],
                            },
                        }
                    )
                for env in protocol["environments"]:
                    for condition in protocol["conditions"]:
                        rows = [
                            r
                            for r in report["runs"]
                            if r["environment"] == env and r["condition"] == condition
                        ]
                        summaries.append(
                            {
                                "task": "minigrid",
                                "dataset": DATASET,
                                "environment_id": env,
                                "reader": method_for[condition],
                                "episodes": len(rows),
                                "successes": sum(r["success"] for r in rows),
                            }
                        )
        replay_rows, replay_summary = replay_dashboard.catalog(self.root)
        runs.extend(replay_rows)
        summaries.extend(replay_summary)
        support_rows, support_summary = support_presentation.catalog(self.root)
        runs.extend(support_rows)
        summaries.extend(support_summary)
        return {"schema": "task-catalog-v1", "runs": runs, "summary": summaries}

    def run(self, uid: str) -> dict[str, Any]:
        row = next((r for r in self.catalog()["runs"] if r["uid"] == uid), None)
        if row is None:
            raise KeyError("unknown run")
        name = str(row["file"])
        if Path(name).name != name:
            raise ValueError("invalid artifact name")
        base = self.root / "experiments" / row["dataset"]
        if row["task"] == "boxoban":
            base = base / "evaluation"
        path = base / name
        if path.stat().st_size > 16 * 1024 * 1024:
            raise TraceTooLargeError("compressed artifact too large")
        raw = path.read_bytes()
        if len(raw) > 16 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("invalid artifact size or checksum")
        with gzip.open(path, "rb") as stream:
            decoded = stream.read(MAX_EXPANDED_TRACE_BYTES + 1)
        if len(decoded) > MAX_EXPANDED_TRACE_BYTES:
            raise TraceTooLargeError("expanded artifact too large")
        result: dict[str, Any] = json.loads(decoded)
        if row["dataset"] in (DATASET, replay_dashboard.DATASET, support_presentation.DATASET):
            result = adapt_recorded(result, row["reader"])
        if row["dataset"] == replay_dashboard.DATASET:
            result["replay"] = replay_dashboard.metadata(self.root, row["condition"])
        if row["dataset"] == support_presentation.DATASET:
            result["support_study"] = support_presentation.metadata(self.root, row["condition"])
        result["task"] = row["task"]
        result["dataset"] = row["dataset"]
        result["catalog_split"] = row.get("split")
        if row["task"] == "minigrid":
            result.update(
                success=result["result"]["success"],
                level_id=result["seed"],
                config=result["reader"],
                method=result["reader"],
                expansion_limit=row["expansion_limit"],
                expanded=len(result["trajectory"]),
                pushes=None,
                wall_seconds=result["costs"].get(
                    "episode_seconds", result.get("episode_seconds", 0)
                ),
            )
        return result

    def bank(self) -> dict[str, Any]:
        base = self.root / "experiments/boxoban-search-v1"
        bank: dict[str, Any] = json.loads((base / "cases.json").read_text())
        boards = {}
        for identifier in sorted({c["level_id"] for c in bank["cases"]}):
            with gzip.open(base / f"train-{identifier}.json.gz", "rt") as stream:
                boards[str(identifier)] = json.load(stream)["rows"]
        return {**bank, "boards": boards}


class TaskServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], root: Path = ROOT, *, memory_port: int = 8791):
        self.memory = MemoryGateway(memory_port)
        self.solver = LiveSolver(root=root)
        self.catalog = TaskCatalog(root)
        self.root = root
        super().__init__(address, TaskHandler)

    def server_close(self) -> None:
        self.solver.close()
        super().server_close()


class TaskHandler(BaseHTTPRequestHandler):
    server: TaskServer

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def send(self, status: int, body: bytes, mime: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-src 'self'; frame-ancestors "
            + ("'self'" if urlsplit(self.path).path.startswith(("/task/", "/live/")) else "'none'"),
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        route = urlsplit(self.path)
        try:
            if route.path == "/api/solve":
                args = parse_qs(route.query)
                if set(args) != {"id", "after"} or any(len(v) != 1 for v in args.values()):
                    raise ValueError("one id and after cursor required")
                result = self.server.solver.snapshot(args["id"][0], int(args["after"][0]))
                self.send(200, json.dumps(result, allow_nan=False).encode(), "application/json")
                return
            if route.path == "/api/memory/state" and not route.query:
                status, body = self.server.memory.request("state")
                self.send(status, body, "application/json")
                return
            if route.path == "/api/catalog":
                result = self.server.catalog.catalog()
            elif route.path == "/api/run":
                args = parse_qs(route.query)
                if set(args) != {"id"} or len(args["id"]) != 1 or len(args["id"][0]) > 256:
                    raise ValueError("one bounded id is required")
                result = self.server.catalog.run(args["id"][0])
            elif route.path == "/api/bank":
                result = self.server.catalog.bank()
            else:
                allowed = {
                    "/": ("web/dashboard/index.html", "text/html; charset=utf-8"),
                    "/dashboard.css": ("web/dashboard/style.css", "text/css"),
                    "/dashboard.js": ("web/dashboard/app.js", "text/javascript"),
                    "/style.css": ("web/task-lab/style.css", "text/css"),
                    "/app.js": ("web/task-lab/app.js", "text/javascript"),
                    "/routing.js": ("web/task-lab/routing.js", "text/javascript"),
                    "/spatial.bundle.js": ("web/task-lab/spatial.bundle.js", "text/javascript"),
                    "/spatial.css": ("web/task-lab/spatial.css", "text/css"),
                    "/geist.ttf": ("web/somna-live/fonts/geist-regular.ttf", "font/ttf"),
                    "/geist-semibold.ttf": ("web/somna-live/fonts/geist-semibold.ttf", "font/ttf"),
                }
                for prefix, folder in [("task", "task-lab"), ("live", "somna-live")]:
                    allowed[f"/{prefix}/"] = (
                        f"web/{folder}/index.html",
                        "text/html; charset=utf-8",
                    )
                    for asset, mime in [
                        ("app.js", "text/javascript"),
                        ("style.css", "text/css"),
                        ("spatial.bundle.js", "text/javascript"),
                        ("spatial.css", "text/css"),
                        ("embedded.css", "text/css"),
                        ("panel-boot.js", "text/javascript"),
                    ]:
                        allowed[f"/{prefix}/{asset}"] = (f"web/{folder}/{asset}", mime)
                allowed["/task/routing.js"] = ("web/task-lab/routing.js", "text/javascript")
                for weight in ["regular", "semibold"]:
                    allowed[f"/live/fonts/geist-{weight}.ttf"] = (
                        f"web/somna-live/fonts/geist-{weight}.ttf",
                        "font/ttf",
                    )
                if route.path not in allowed:
                    raise KeyError("unknown route")
                filename, mime = allowed[route.path]
                self.send(200, (self.server.root / filename).read_bytes(), mime)
                return
            self.send(200, json.dumps(result, allow_nan=False).encode(), "application/json")
        except TraceTooLargeError:
            self.send(
                413,
                b'{"error":"This historical trace is too large for the inspector. Choose a compact evaluation run."}',
                "application/json",
            )
        except KeyError:
            self.send(404, b'{"error":"Unknown run or route"}', "application/json")
        except (ValueError, OSError):
            self.send(
                400, b'{"error":"Benchmark artifact is unavailable or invalid"}', "application/json"
            )

    def do_POST(self) -> None:
        route = urlsplit(self.path)
        operation = route.path.removeprefix("/api/memory/")
        if (
            route.path not in {"/api/solve", "/api/solve/cancel"}
            and (not route.path.startswith("/api/memory/") or operation not in MEMORY_WRITES)
        ) or route.query:
            self.send(
                405,
                b'{"error":"Task evidence is read only; unsupported operation"}',
                "application/json",
            )
            return
        host = self.headers.get("Host", "")
        if (
            host
            not in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}
            or self.headers.get("Origin") != "http://" + host
        ):
            self.send(
                403,
                b'{"error":"Dashboard writes require the same loopback origin"}',
                "application/json",
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if (
                not 0 < length <= MAX_BODY
                or self.headers.get("Content-Type", "").split(";")[0] != "application/json"
            ):
                raise ValueError("bounded JSON required")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict):
                raise ValueError("object required")
            payload = json.dumps(value, allow_nan=False).encode()
        except (ValueError, UnicodeDecodeError):
            self.send(
                400,
                b'{"error":"Request must be a finite JSON object of at most 64 KiB"}',
                "application/json",
            )
            return
        if route.path in {"/api/solve", "/api/solve/cancel"}:
            try:
                result = (
                    self.server.solver.start(value)
                    if route.path == "/api/solve"
                    else self.server.solver.cancel(value)
                )
                self.send(200, json.dumps(result, allow_nan=False).encode(), "application/json")
            except SolverBusyError as error:
                self.send(409, json.dumps({"error": str(error)}).encode(), "application/json")
            except KeyError:
                self.send(404, b'{"error":"Unknown solve"}', "application/json")
            except (ValueError, TypeError) as error:
                self.send(400, json.dumps({"error": str(error)}).encode(), "application/json")
            return
        status, body = self.server.memory.request(operation, payload)
        self.send(status, body, "application/json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8792)
    parser.add_argument("--memory-port", type=int, default=8791)
    args = parser.parse_args()
    server = TaskServer(("127.0.0.1", args.port), memory_port=args.memory_port)
    print(f"Somna dashboard: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
