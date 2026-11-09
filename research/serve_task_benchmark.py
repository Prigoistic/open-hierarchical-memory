"""Read-only loopback inspector for completed, checksum-bound task traces."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MAX_EXPANDED_TRACE_BYTES = 128 * 1024 * 1024


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
            raise ValueError("compressed artifact too large")
        raw = path.read_bytes()
        if len(raw) > 16 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("invalid artifact size or checksum")
        with gzip.open(path, "rb") as stream:
            decoded = stream.read(MAX_EXPANDED_TRACE_BYTES + 1)
        if len(decoded) > MAX_EXPANDED_TRACE_BYTES:
            raise ValueError("expanded artifact too large")
        result: dict[str, Any] = json.loads(decoded)
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
                wall_seconds=result["costs"]["episode_seconds"],
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

    def __init__(self, address: tuple[str, int], root: Path = ROOT):
        self.catalog = TaskCatalog(root)
        self.root = root
        super().__init__(address, TaskHandler)


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
            "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        route = urlsplit(self.path)
        try:
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
                    "/": ("web/task-lab/index.html", "text/html; charset=utf-8"),
                    "/style.css": ("web/task-lab/style.css", "text/css"),
                    "/app.js": ("web/task-lab/app.js", "text/javascript"),
                    "/geist.ttf": ("web/somna-live/fonts/geist-regular.ttf", "font/ttf"),
                    "/geist-semibold.ttf": ("web/somna-live/fonts/geist-semibold.ttf", "font/ttf"),
                }
                if route.path not in allowed:
                    raise KeyError("unknown route")
                filename, mime = allowed[route.path]
                self.send(200, (self.server.root / filename).read_bytes(), mime)
                return
            self.send(200, json.dumps(result, allow_nan=False).encode(), "application/json")
        except KeyError:
            self.send(404, b'{"error":"Unknown run or route"}', "application/json")
        except (ValueError, OSError):
            self.send(
                400, b'{"error":"Benchmark artifact is unavailable or invalid"}', "application/json"
            )

    def do_POST(self) -> None:
        self.send(405, b'{"error":"This inspector is read only"}', "application/json")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8792)
    args = parser.parse_args()
    server = TaskServer(("127.0.0.1", args.port))
    print(f"Benchmark inspector: http://127.0.0.1:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
