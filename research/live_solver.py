"""One bounded, cancellable fresh MiniGrid run with append-only visual evidence.

This wraps the existing observation-only benchmark; it never opens the separate
continuous-memory database or writes to frozen benchmark artifacts.
"""

from __future__ import annotations

import copy
import json
import secrets
import threading
import time
from collections.abc import Callable
from typing import Any

from research.run_minigrid_benchmark import ENVIRONMENTS
from research.run_progress_benchmark import CONDITIONS, run_episode

MAX_TRACE_BYTES = 64 * 1024 * 1024
MAX_STEPS = 1024
MAX_SECONDS = 90.0


class SolverBusyError(ValueError):
    """Another solve still owns the local worker."""


class StopEpisode(RuntimeError):
    """Cooperative stop at the next complete observation/action boundary."""


class LiveSolver:
    def __init__(self, runner: Callable[..., dict[str, Any]] = run_episode) -> None:
        self.runner = runner
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.worker: threading.Thread | None = None
        self.job: dict[str, Any] | None = None
        self.closed = False
        self.size = 0
        self.started = 0.0

    def start(self, value: dict[str, Any]) -> dict[str, Any]:
        if set(value) != {"environment", "reader", "seed", "step_cap"}:
            raise ValueError("environment, reader, seed and step_cap are required")
        environment, reader, seed, cap = (
            value["environment"],
            value["reader"],
            value["seed"],
            value["step_cap"],
        )
        if environment not in ENVIRONMENTS or reader not in CONDITIONS:
            raise ValueError("unsupported live maze or reader")
        if type(seed) is not int or not 0 <= seed < 2**31:
            raise ValueError("seed must be an integer in [0, 2147483647]")
        if type(cap) is not int or not 1 <= cap <= MAX_STEPS:
            raise ValueError("step_cap must be in [1, 1024]")
        with self.lock:
            if self.closed:
                raise ValueError("solver is closed")
            if self.worker and self.worker.is_alive():
                raise SolverBusyError("A solve is running. Stop it before starting another.")
            self.stop.clear()
            self.size = 0
            self.started = time.monotonic()
            self.job = {
                "id": secrets.token_hex(16),
                "status": "running",
                "config": dict(value),
                "trajectory": [],
                "routing_snapshots": {},
                "routing_events": {},
                "result": None,
                "reason": None,
            }
            initial = self.snapshot(self.job["id"], 0)
            self.worker = threading.Thread(target=self._run, name="maze-solve", daemon=True)
            self.worker.start()
            return initial

    def _check_stop(self) -> None:
        if self.stop.is_set():
            raise StopEpisode("Stopped by request")
        if time.monotonic() - self.started > MAX_SECONDS:
            raise StopEpisode("Wall time budget reached")

    def _append(
        self, row: dict[str, Any], snapshots: dict[str, Any], events: dict[str, Any]
    ) -> None:
        self._check_stop()
        # Runner owns its objects. Publish independent immutable-by-ownership copies.
        with self.lock:
            assert self.job is not None
            new_snapshots = {
                k: v for k, v in snapshots.items() if k not in self.job["routing_snapshots"]
            }
            new_events = {k: v for k, v in events.items() if k not in self.job["routing_events"]}
            addition = {"row": row, "snapshots": new_snapshots, "events": new_events}
            size = len(json.dumps(addition, allow_nan=False, separators=(",", ":")).encode())
            if self.size + size > MAX_TRACE_BYTES:
                raise StopEpisode("Trace budget reached")
            owned = copy.deepcopy(addition)
            self.job["trajectory"].append(owned["row"])
            self.job["routing_snapshots"].update(owned["snapshots"])
            self.job["routing_events"].update(owned["events"])
            self.size += size

    def _run(self) -> None:
        assert self.job is not None
        config = self.job["config"]
        try:
            result = self.runner(
                config["environment"],
                config["reader"],
                config["seed"],
                split="diagnostic",
                step_cap=config["step_cap"],
                on_step=self._append,
            )
            with self.lock:
                assert self.job is not None
                outcome = result["result"]
                err = outcome.get("error")
                reason: str | None
                # Stop/error beats any coincident terminal reward.
                if self.stop.is_set():
                    status, reason = "cancelled", "Stopped by request"
                elif err:
                    status = "limited" if err["type"] == "StopEpisode" else "failed"
                    reason = err["message"]
                else:
                    status = "solved" if outcome["success"] else "limited"
                    reason = (
                        None
                        if outcome["success"]
                        else (
                            "Action budget reached"
                            if outcome["external_cutoff"]
                            else "Episode ended without success"
                        )
                    )
                published = copy.deepcopy(outcome)
                published["success"] = status == "solved"
                published["steps"] = len(self.job["trajectory"])
                self.job.update(status=status, reason=reason, result=published)
        except Exception as error:
            with self.lock:
                assert self.job is not None
                self.job.update(status="failed", reason=f"{type(error).__name__}: {error}")

    def snapshot(self, identifier: str, after: int) -> dict[str, Any]:
        with self.lock:
            if not self.job or identifier != self.job["id"]:
                raise KeyError("Unknown solve. Start a new run.")
            rows = self.job["trajectory"]
            if type(after) is not int or not 0 <= after <= len(rows):
                raise ValueError("Invalid evidence cursor")
            # Bounded incremental pages. Every route reference carries its own
            # source layout; clients do not have to race separate artifact loads.
            page = rows[after : after + 16]
            event_ids = {
                route["route_ref"]
                for row in page
                for route in row["decision"]["route"]
                if "route_ref" in route
            }
            events = {k: self.job["routing_events"][k] for k in event_ids}
            snapshot_ids = {event["snapshot_id"] for event in events.values()}
            return copy.deepcopy(
                {
                    "schema": "somna-solve-v1",
                    "id": identifier,
                    "status": self.job["status"],
                    "reason": self.job["reason"],
                    "config": self.job["config"],
                    "after": after,
                    "next": after + len(page),
                    "available": len(rows),
                    "trajectory": page,
                    "routing_events": events,
                    "routing_snapshots": {
                        k: self.job["routing_snapshots"][k] for k in snapshot_ids
                    },
                    "result": self.job["result"],
                }
            )

    def cancel(self, value: dict[str, Any]) -> dict[str, Any]:
        if set(value) != {"id"}:
            raise ValueError("one solve id required")
        with self.lock:
            if not self.job or value["id"] != self.job["id"]:
                raise KeyError("Unknown solve")
            self.stop.set()
            return self.snapshot(value["id"], len(self.job["trajectory"]))

    def close(self) -> None:
        with self.lock:
            self.closed = True
            self.stop.set()
        if self.worker:
            self.worker.join(timeout=3)
