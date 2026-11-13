"""Persistent continuous episodic memory and bounded, provenance-aware learning.

Research CPU float64 engine. The installed attention core remains unchanged.
Cold/active limits are execution limits, not a bound on total archive/RSS.
"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import random
import sqlite3
import time
from pathlib import Path
from typing import Any

import torch
from torch import nn

from open_hierarchical_memory import (
    ExecutionMode,
    HierarchicalIndex,
    QueryBudget,
    TreeConfig,
)
from open_hierarchical_memory.training import pooled_chunk_kl
from research.somna_world import (
    ACTIONS,
    FEATURE_VERSION,
    context_value,
    cue,
    features,
    model_inputs,
    model_targets,
    observations,
    pair,
)

FORMAT = "somna-continuous-v1"
WORK_NAMES = (
    "raw_pairs",
    "summary_dot_products",
    "cold_rows",
    "scheduler_observations",
    "gradient_steps",
    "training_examples",
    "dense_audit_pairs",
    "full_audit_pairs",
    "index_builds",
    "simulator_calls",
    "restores",
    "reference_steps",
    "cold_raw_pairs",
    "cold_summary_dot_products",
    "cold_index_builds",
    "hot_index_key_rows",
    "hot_index_summary_nodes",
    "cold_index_key_rows",
    "cold_index_summary_nodes",
    "reference_teacher_pairs",
    "reference_summary_blocks",
)


def sha(value: Any) -> str:
    value = json.loads(json.dumps(value, allow_nan=False))
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def bounded_int(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low},{high}]")
    return value


def record_features(row: dict[str, Any]) -> torch.Tensor:
    return features({name: row[name] for name in ("position", "action", "context")})


class Dynamics(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(6, 24), nn.Tanh(), nn.Linear(24, 24), nn.Tanh(), nn.Linear(24, 2)
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        output: torch.Tensor = self.layers(inputs)
        return output


class MemoryEngine:
    """Single writer/controller, externally serialized by the local server lock."""

    def __init__(
        self, path: Path, *, seed: int = 7, capacity: int = 48, bootstrap: int = 256
    ) -> None:
        bounded_int(seed, "seed", 0, 2**31 - 1)
        bounded_int(capacity, "capacity", 8, 128)
        bounded_int(bootstrap, "bootstrap", 0, 512)
        self.path = path
        self.lock_file = path.with_suffix(path.suffix + ".lock").open("a+b")
        try:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.lock_file.close()
            raise ValueError("archive already has an active controller") from error
        try:
            self.db = sqlite3.connect(str(path), check_same_thread=False)
        except BaseException:
            self.lock_file.close()
            raise
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.index: HierarchicalIndex | None = None
        self.index_ids: list[int] = []
        self.dirty = True
        self.cold_dirty = True
        self.cold_index: HierarchicalIndex | None = None
        self.cold_ids: list[int] = []
        self.records: dict[int, dict[str, Any]] = {}
        self.heads: dict[str, int] = {}
        self.hot: dict[int, dict[str, Any]] = {}
        self.metadata: dict[int, dict[str, Any]] = {}
        self.seed = seed
        self.capacity = capacity
        self.tick = 0
        self.revision = 0
        self.cursor = 0
        self.last_query: dict[str, Any] | None = None
        self.sleep: dict[str, Any] = {
            "busy": False,
            "strategy": None,
            "trace": [],
            "rollout": [],
            "error": None,
            "status": "idle",
        }
        self.work = dict.fromkeys(WORK_NAMES, 0)
        self.maintenance: dict[str, Any] = {
            "hot_build_seconds": 0.0,
            "cold_build_seconds": 0.0,
            "hot_last_owned_bytes": 0,
            "cold_last_owned_bytes": 0,
        }
        self.trained_steps = 0
        self.model_invalidated = False
        self.last_loss: float | None = None
        self.router_fit: dict[str, Any] = {"steps": 0, "train_loss": None, "validation_loss": None}
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(seed)
            self.models = nn.ModuleList([Dynamics().double() for _ in range(3)])
        self.references = (
            torch.randn(
                (1, 8, 12), generator=torch.Generator().manual_seed(seed), dtype=torch.float64
            )
            * 2
        )
        self.random_references = self.references.clone()
        try:
            self._initialize()
            if self.db.execute("SELECT COUNT(*) FROM session").fetchone()[0]:
                self._load()
            else:
                self._commit()
                if bootstrap:
                    self.collect(bootstrap)
        except BaseException:
            self.db.close()
            self.lock_file.close()
            raise

    def _initialize(self) -> None:
        tables = {
            r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if tables:
            if tables != {"observations", "heads", "session"}:
                raise ValueError("unsupported archive schema")
            return
        self.db.executescript("""
            BEGIN;
            CREATE TABLE observations(id INTEGER PRIMARY KEY, logical_key TEXT NOT NULL, previous INTEGER REFERENCES observations(id), payload TEXT NOT NULL, checksum TEXT NOT NULL);
            CREATE TABLE heads(logical_key TEXT PRIMARY KEY,id INTEGER UNIQUE REFERENCES observations(id));
            CREATE TABLE session(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL,checksum TEXT NOT NULL);
            CREATE TRIGGER original_no_update BEFORE UPDATE ON observations BEGIN SELECT RAISE(ABORT,'immutable observation'); END;
            CREATE TRIGGER original_no_delete BEFORE DELETE ON observations BEGIN SELECT RAISE(ABORT,'immutable observation'); END;
            COMMIT;
        """)

    def _weights(self) -> dict[str, Any]:
        return {name: value.detach().tolist() for name, value in self.models.state_dict().items()}

    def model_hash(self) -> str:
        return sha(self._weights())

    def _bundle(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "feature_version": FEATURE_VERSION,
            "seed": self.seed,
            "capacity": self.capacity,
            "tick": self.tick,
            "revision": self.revision,
            "cursor": self.cursor,
            "hot": list(self.hot),
            "metadata": self.metadata,
            "work": self.work,
            "index_maintenance": self.maintenance,
            "last_query": self.last_query,
            "sleep": self.sleep,
            "trained_steps": self.trained_steps,
            "model_invalidated": self.model_invalidated,
            "last_loss": self.last_loss,
            "weights": self._weights(),
            "references": self.references.tolist(),
            "random_references": self.random_references.tolist(),
            "router_fit": self.router_fit,
        }

    def _commit(self) -> None:
        bundle = self._bundle()
        try:
            with self.db:
                self.db.execute(
                    "INSERT INTO session(id,payload,checksum) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,checksum=excluded.checksum",
                    (json.dumps(bundle, allow_nan=False), sha(bundle)),
                )
        except BaseException:
            self.db.rollback()
            if self.db.execute("SELECT COUNT(*) FROM session").fetchone()[0]:
                self._load()
            raise

    def _load(self) -> None:
        row = self.db.execute("SELECT payload,checksum FROM session WHERE id=1").fetchone()
        if len(row[0]) > 16 * 1024 * 1024:
            raise ValueError("session exceeds supported size")
        data = json.loads(row[0])
        if (
            sha(data) != row[1]
            or data.get("format") != FORMAT
            or data.get("feature_version") not in ("continuous-harmonic-cue-v1", FEATURE_VERSION)
        ):
            raise ValueError("session checksum or format mismatch")
        if self.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] > 2048:
            raise ValueError("archive exceeds supported capacity")
        coordinate_changed = data.get("feature_version") != FEATURE_VERSION
        self.records = {}
        expected_heads: dict[str, int] = {}
        previous_tick = 0
        for record in self.db.execute("SELECT * FROM observations ORDER BY id"):
            payload = json.loads(record["payload"])
            if sha([record["logical_key"], record["previous"], payload]) != record["checksum"]:
                raise ValueError("observation checksum mismatch")
            self._validate_observation(payload)
            if (
                record["previous"] != expected_heads.get(record["logical_key"])
                or payload["tick"] < previous_tick
            ):
                raise ValueError("invalid causal correction chain")
            previous_tick = payload["tick"]
            expected_heads[record["logical_key"]] = record["id"]
            self.records[record["id"]] = {
                **payload,
                "id": record["id"],
                "logical_key": record["logical_key"],
                "previous": record["previous"],
                "checksum": record["checksum"],
            }
        self.heads = dict(self.db.execute("SELECT logical_key,id FROM heads"))
        if self.heads != expected_heads:
            raise ValueError("head identity mismatch")
        data.setdefault(
            "model_invalidated",
            any(r["source"] == "user-correction" for r in self.records.values()),
        )
        for name in (
            "seed",
            "capacity",
            "tick",
            "revision",
            "cursor",
            "work",
            "last_query",
            "sleep",
            "trained_steps",
            "model_invalidated",
            "last_loss",
            "router_fit",
        ):
            setattr(self, name, data[name])
        self.metadata = {int(k): v for k, v in data["metadata"].items()}
        bounded_int(self.seed, "seed", 0, 2**31 - 1)
        bounded_int(self.capacity, "capacity", 8, 128)
        bounded_int(self.tick, "tick", previous_tick, 2**63 - 1)
        bounded_int(self.cursor, "cursor", 0, 2**63 - 1)
        bounded_int(self.trained_steps, "trained_steps", 0, 2**63 - 1)
        self.maintenance = data.get("index_maintenance", self.maintenance)
        for name in WORK_NAMES:
            self.work.setdefault(name, 0)
        if set(self.metadata) != set(self.records) or set(self.work) != set(WORK_NAMES):
            raise ValueError("persisted metadata identities do not match archive")
        for meta in self.metadata.values():
            if set(meta) != {"uses", "last_use", "last_refresh"}:
                raise ValueError("invalid controller metadata")
            bounded_int(meta["uses"], "uses", 0, 2**63 - 1)
            bounded_int(meta["last_use"], "last_use", 0, self.tick)
            bounded_int(meta["last_refresh"], "last_refresh", 0, self.tick)
        for value in self.work.values():
            bounded_int(value, "work", 0, 2**63 - 1)
        current = set(self.heads.values())
        if len(data["hot"]) > self.capacity or any(
            i not in current or i not in self.metadata for i in data["hot"]
        ):
            raise ValueError("invalid persisted hot set")
        self.hot = {i: self.metadata[i] for i in data["hot"]}
        weights = {
            name: torch.tensor(value, dtype=torch.float64)
            for name, value in data["weights"].items()
        }
        if any(not bool(torch.isfinite(v).all()) for v in weights.values()):
            raise ValueError("nonfinite model checkpoint")
        self.models.load_state_dict(weights, strict=True)
        self.references = torch.tensor(data["references"], dtype=torch.float64)
        self.random_references = torch.tensor(data["random_references"], dtype=torch.float64)
        if self.references.shape != (1, 8, 12) or not bool(torch.isfinite(self.references).all()):
            raise ValueError("invalid reference checkpoint")
        if self.sleep["busy"]:
            self.sleep.update(
                busy=False,
                status="interrupted",
                error="Process stopped during offline work; completed parameter updates retained.",
            )
        if coordinate_changed:
            self.references = (
                torch.randn(
                    (1, 8, 12),
                    generator=torch.Generator().manual_seed(self.seed),
                    dtype=torch.float64,
                )
                * 2
            )
            self.random_references = self.references.clone()
            self.router_fit = {
                "steps": 0,
                "train_loss": None,
                "validation_loss": None,
                "status": "invalidated by injective coordinate migration",
            }
            self.last_query = None
            self.sleep["rollout"] = []
            self.sleep["rollout_status"] = (
                "invalidated by coordinate migration; routing indexes will be rebuilt"
            )
        self.dirty = True
        self.cold_dirty = True

    @staticmethod
    def _validate_observation(row: dict[str, Any]) -> None:
        if set(row) != {
            "position",
            "action",
            "context",
            "successor",
            "evidence",
            "source",
            "tick",
            "version",
        }:
            raise ValueError("unsupported observation fields")
        pair(row["position"], "position")
        pair(row["action"], "action")
        pair(row["successor"], "successor")
        context_value(row["context"])
        bounded_int(row["tick"], "tick", 0, 2**63 - 1)
        bounded_int(row["version"], "version", 1, 1000)
        if row["evidence"] != "observed" or row["source"] not in (
            "controlled-simulator-v1",
            "user-correction",
            "user-observation",
        ):
            raise ValueError("canonical archive accepts observed evidence only")

    def _score(self, identifier: int) -> float:
        meta = self.metadata[identifier]
        return float(
            (1.0 + math.log1p(meta["uses"]))
            * 2 ** (-(self.tick - max(meta["last_use"], meta["last_refresh"])) / 32.0)
        )

    def _promote(self, identifier: int, *, used: bool = False) -> None:
        if identifier not in set(self.heads.values()):
            raise ValueError("superseded observations cannot be activated")
        meta = self.metadata[identifier]
        if used:
            meta["uses"] += 1
            meta["last_use"] = self.tick
        else:
            meta["last_refresh"] = self.tick
        if identifier not in self.hot:
            if len(self.hot) == self.capacity:
                victim = min(
                    self.hot, key=lambda i: (self._score(i), self.metadata[i]["last_refresh"], i)
                )
                del self.hot[victim]
            self.hot[identifier] = meta
            self.dirty = True

    def _append(self, value: dict[str, Any], logical_key: str | None = None) -> int:
        key = logical_key or f"observation-{len(self.records) + 1}"
        previous = self.heads.get(key)
        payload = {
            **value,
            "tick": self.tick,
            "version": 1 if previous is None else self.records[previous]["version"] + 1,
        }
        self._validate_observation(payload)
        checksum = sha([key, previous, payload])
        cursor = self.db.execute(
            "INSERT INTO observations(logical_key,previous,payload,checksum) VALUES(?,?,?,?)",
            (key, previous, json.dumps(payload, allow_nan=False), checksum),
        )
        identifier = int(cursor.lastrowid or 0)
        self.db.execute(
            "INSERT INTO heads(logical_key,id) VALUES(?,?) ON CONFLICT(logical_key) DO UPDATE SET id=excluded.id",
            (key, identifier),
        )
        self.records[identifier] = {
            **payload,
            "id": identifier,
            "logical_key": key,
            "previous": previous,
            "checksum": checksum,
        }
        self.heads[key] = identifier
        self.metadata[identifier] = {"uses": 0, "last_use": self.tick, "last_refresh": self.tick}
        if previous is not None:
            self.hot.pop(previous, None)
        self._promote(identifier)
        self.dirty = True
        self.cold_dirty = True
        return identifier

    def collect(self, count: int, context: int | None = None) -> dict[str, Any]:
        bounded_int(count, "count", 1, 128 if self.records else 512)
        context_value(context, optional=True)
        if len(self.records) + count > 2048:
            raise ValueError("archive limit2048 reached; originals are never silently deleted")
        collected = observations(self.seed, count, context=context, offset=len(self.records))
        for row in collected:
            self.tick += 1
            self._append(row)
        self.work["simulator_calls"] += count
        self.last_query = None
        self.revision += 1
        self._commit()
        return self.state()

    def remember(self, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict) or set(value) != {
            "position",
            "action",
            "context",
            "successor",
            "evidence",
        }:
            raise ValueError(
                "remember requires only an observed position/action/context/successor tuple"
            )
        if len(self.records) >= 2048:
            raise ValueError("archive limit2048 reached")
        payload = {
            "position": pair(value["position"], "position"),
            "action": pair(value["action"], "action"),
            "context": context_value(value["context"]),
            "successor": pair(value["successor"], "successor"),
            "evidence": value["evidence"],
            "source": "user-observation",
        }
        self._validate_observation({**payload, "tick": self.tick + 1, "version": 1})
        self.tick += 1
        self._append(payload)
        self.last_query = None
        self.revision += 1
        self._commit()
        return self.state()

    def correct(self, identifier: int, successor: list[float]) -> dict[str, Any]:
        bounded_int(identifier, "id", 1, 2**31 - 1)
        position = pair(successor, "successor")
        if identifier not in set(self.heads.values()):
            raise ValueError("correction must target a current observed record")
        original = self.records[identifier]
        if len(self.records) >= 2048 or original["version"] >= 1000:
            raise ValueError("archive or correction-version limit reached")
        self.tick += 1
        self._append(
            {
                "position": original["position"],
                "action": original["action"],
                "context": original["context"],
                "successor": position,
                "evidence": "observed",
                "source": "user-correction",
            },
            original["logical_key"],
        )
        self.last_query = None
        self.model_invalidated = True
        self.sleep["rollout"] = []
        self.sleep["rollout_status"] = "invalidated: observed correction"
        self.sleep["status"] = "invalidated"
        self.revision += 1
        self._commit()
        return self.state()

    def forget(self, steps: int) -> dict[str, Any]:
        bounded_int(steps, "steps", 1, 512)
        self.tick += steps
        self.last_query = None
        for identifier in list(self.hot):
            if self._score(identifier) < 0.5:
                del self.hot[identifier]
                self.dirty = True
        self.revision += 1
        self._commit()
        return self.state()

    def restore(self, identifier: int) -> dict[str, Any]:
        bounded_int(identifier, "id", 1, 2**31 - 1)
        if identifier not in set(self.heads.values()):
            raise ValueError("only current observations can be restored")
        self.tick += 1
        self._promote(identifier)
        self.last_query = None
        self.work["restores"] += 1
        self.revision += 1
        self._commit()
        return self.state()

    def _rebuild(self) -> None:
        if not self.dirty:
            return
        started = time.perf_counter()
        self.index_ids = sorted(self.hot)
        if not self.index_ids:
            self.index = None
            return
        keys = torch.stack(
            [
                torch.zeros(12, dtype=torch.float64),
                *[record_features(self.records[i]) for i in self.index_ids],
            ]
        )
        values = torch.stack(
            [
                torch.zeros(2, dtype=torch.float64),
                *[model_targets([self.records[i]])[0] for i in self.index_ids],
            ]
        )
        self.index = HierarchicalIndex(
            keys[None, None],
            values[None, None],
            self.references,
            config=TreeConfig(chunk_size=4, depth=2),
        )
        self.work["index_builds"] += 1
        self.work["hot_index_key_rows"] += len(self.index_ids) + 1
        self.work["hot_index_summary_nodes"] += len(self.index.info.spans)
        self.maintenance["hot_build_seconds"] += time.perf_counter() - started
        self.maintenance["hot_last_owned_bytes"] = self.index.info.owned_tensor_bytes
        self.dirty = False

    def _cold_read(self, vector: torch.Tensor) -> dict[str, Any]:
        if self.cold_dirty:
            started = time.perf_counter()
            self.cold_ids = sorted(self.heads.values())
            keys = torch.stack(
                [
                    torch.zeros(12, dtype=torch.float64),
                    *[record_features(self.records[i]) for i in self.cold_ids],
                ]
            )
            values = torch.cat(
                [
                    torch.zeros((1, 2), dtype=torch.float64),
                    model_targets([self.records[i] for i in self.cold_ids]),
                ]
            )
            self.cold_index = HierarchicalIndex(
                keys[None, None],
                values[None, None],
                self.references,
                config=TreeConfig(chunk_size=4, depth=3),
            )
            self.cold_dirty = False
            self.work["cold_index_builds"] += 1
            self.work["cold_index_key_rows"] += len(self.cold_ids) + 1
            self.work["cold_index_summary_nodes"] += len(self.cold_index.info.spans)
            self.maintenance["cold_build_seconds"] += time.perf_counter() - started
            self.maintenance["cold_last_owned_bytes"] = self.cold_index.info.owned_tensor_bytes
        assert self.cold_index is not None
        result = self.cold_index.attend(
            vector[None, None, None],
            visible_counts=torch.tensor([[len(self.cold_ids) + 1]], dtype=torch.int64),
            mode=ExecutionMode.PAPER_APPROXIMATE,
            p=0.25,
            budget=QueryBudget(max_attention_pairs=128, max_scored_nodes=512, max_trace_nodes=512),
            collect_trace=True,
        )
        route = result.routes[0]
        identifiers = [self.cold_ids[i - 1] for i in route.selected_ids if i]
        identifiers.sort(key=lambda i: (-float(record_features(self.records[i]) @ vector), i))
        recovered = [i for i in identifiers if i not in self.hot][:4]
        for identifier in recovered:
            self._promote(identifier)
        self.work["cold_raw_pairs"] += len(route.selected_ids)
        self.work["cold_summary_dot_products"] += route.scored_nodes * 8
        return {
            "status": "approximate",
            "route": [
                {
                    "level": step.level,
                    "candidates": [n.index for n in step.candidates],
                    "selected": [n.index for n in step.selected],
                    "scores": list(step.scores),
                }
                for step in route.steps
            ],
            "selected_ids": [self.cold_ids[i - 1] for i in route.selected_ids if i],
            "index_ids": self.cold_ids[:],
            "raw_pairs": len(route.selected_ids),
            "summary_dot_products": route.scored_nodes * 8,
            "recovered": recovered,
            "snapshot_id": self.cold_index.info.snapshot_id,
        }

    def _scan(self, vector: torch.Tensor) -> list[int]:
        # Physical archive rows, including superseded/hot ones, consume budget.
        rows = self.db.execute(
            "SELECT id FROM observations WHERE id>? ORDER BY id LIMIT 16", (self.cursor,)
        ).fetchall()
        if not rows:
            self.cursor = 0
            rows = self.db.execute("SELECT id FROM observations ORDER BY id LIMIT 16").fetchall()
        self.work["cold_rows"] += len(rows)
        if rows:
            self.cursor = rows[-1][0]
        current = set(self.heads.values())
        candidates = [r[0] for r in rows if r[0] in current and r[0] not in self.hot]
        candidates.sort(key=lambda i: (-float(record_features(self.records[i]) @ vector), i))
        for identifier in candidates[:4]:
            self._promote(identifier)
        return candidates[:4]

    def _read(
        self, value: dict[str, Any], *, backend: str = "zha", audit: bool = False, use: bool = True
    ) -> dict[str, Any]:
        data = cue(value)
        if backend not in ("zha", "dense"):
            raise ValueError("unsupported reader")
        vector = features(data)
        cold_before = self.work["cold_rows"]
        recovered = self._scan(vector)
        cold = self._cold_read(vector)
        recovered = sorted(set(recovered) | set(cold["recovered"]))
        self._rebuild()
        if self.index is None:
            raise ValueError("no current observed episodes are available")
        started = time.perf_counter()
        result = self.index.attend(
            vector[None, None, None],
            visible_counts=torch.tensor([[len(self.index_ids) + 1]], dtype=torch.int64),
            mode=ExecutionMode.PAPER_APPROXIMATE if backend == "zha" else ExecutionMode.DENSE,
            p=0.8,
            collect_trace=True,
        )
        elapsed = time.perf_counter() - started
        route = result.routes[0]
        logical = list(route.selected_ids)
        ids = [self.index_ids[i - 1] for i in logical if i]
        selected_keys = torch.stack(
            [
                torch.zeros(12, dtype=torch.float64)
                if not i
                else record_features(self.records[self.index_ids[i - 1]])
                for i in logical
            ]
        )
        weights = torch.softmax(selected_keys @ vector / math.sqrt(12), dim=0).tolist()
        ranked = sorted(
            [
                {"id": self.index_ids[i - 1], "weight": w}
                for i, w in zip(logical, weights, strict=True)
                if i
            ],
            key=lambda x: (-x["weight"], x["id"]),
        )
        if use:
            for row in ranked[:3]:
                self._promote(row["id"], used=True)
        self.work["raw_pairs"] += len(logical)
        self.work["summary_dot_products"] += route.scored_nodes * 8
        dense_audit = None
        if audit:
            dense = self.index.attend(
                vector[None, None, None],
                visible_counts=torch.tensor([[len(self.index_ids) + 1]], dtype=torch.int64),
                mode=ExecutionMode.DENSE,
            )
            full_ids = sorted(self.heads.values())
            full_keys = torch.stack(
                [
                    torch.zeros(12, dtype=torch.float64),
                    *[record_features(self.records[i]) for i in full_ids],
                ]
            )
            full_values = torch.cat(
                [
                    torch.zeros((1, 2), dtype=torch.float64),
                    model_targets([self.records[i] for i in full_ids]),
                ]
            )
            full_weights = torch.softmax(full_keys @ vector / math.sqrt(12), dim=0)
            full_output = full_weights @ full_values
            self.work["dense_audit_pairs"] += len(self.index_ids) + 1
            self.work["full_audit_pairs"] += len(full_ids) + 1
            mass = sum(
                float(full_weights[j + 1])
                for j, identifier in enumerate(full_ids)
                if identifier in ids
            )
            dense_audit = {
                "prediction": dense.output[0, 0, 0].tolist(),
                "l2_error": float(torch.linalg.vector_norm(dense.output - result.output)),
                "extra_pairs": len(self.index_ids) + 1,
                "full_current_prediction": full_output.tolist(),
                "full_current_error": float(
                    torch.linalg.vector_norm(full_output - result.output[0, 0, 0])
                ),
                "full_current_extra_pairs": len(full_ids) + 1,
                "observed_selected_mass_full_archive": mass,
                "scope": "offline dense diagnostic; not a runtime certificate",
            }
        return {
            "cue": data,
            "feature_version": FEATURE_VERSION,
            "backend": backend,
            "selected_ids": ids,
            "ranked": ranked,
            "route": [
                {
                    "level": s.level,
                    "candidates": [n.index for n in s.candidates],
                    "selected": [n.index for n in s.selected],
                    "scores": list(s.scores),
                }
                for s in route.steps
            ],
            "prediction": result.output[0, 0, 0].tolist(),
            "recovered": recovered,
            "snapshot_id": self.index.info.snapshot_id,
            "reference_hash": sha(self.references.tolist()),
            "dense_audit": dense_audit,
            "work": {
                "raw_pairs": len(logical),
                "summary_dot_products": route.scored_nodes * 8,
                "cold_rows": self.work["cold_rows"] - cold_before,
                "seconds": elapsed,
            },
            "index_ids": self.index_ids[:],
            "cold_route": cold["route"],
            "cold_selected_ids": cold["selected_ids"],
            "cold_index_ids": cold["index_ids"],
            "cold_status": cold["status"],
            "cold_work": {
                "raw_pairs": cold["raw_pairs"],
                "summary_dot_products": cold["summary_dot_products"],
            },
        }

    def query(self, value: dict[str, Any], *, backend: str = "zha") -> dict[str, Any]:
        data = cue(value)
        if backend not in ("zha", "dense") or not self.heads:
            raise ValueError("unsupported reader or empty observed archive")
        self.tick += 1
        self.last_query = self._read(data, backend=backend, audit=data["audit"])
        self.revision += 1
        self._commit()
        return self.state()

    @torch.no_grad()
    def predict(
        self, position: list[float], action: list[float], context: int
    ) -> tuple[list[float], float]:
        if self.model_invalidated:
            raise ValueError(
                "model was invalidated by an observed correction; rebuild before prediction"
            )
        row = {
            "position": pair(position, "position"),
            "action": pair(action, "action"),
            "context": context_value(context),
        }
        outputs = torch.stack([model(model_inputs([row]))[0] for model in self.models])
        return outputs.mean(0).tolist(), float(outputs.std(0, unbiased=False).max())

    def fit_router(self, steps: int = 12) -> dict[str, Any]:
        """Training/validation cues derive only from observed data, never evaluation labels."""
        bounded_int(steps, "reference steps", 1, 32)
        ids = sorted(self.heads.values())
        if len(ids) < 16:
            raise ValueError("at least16 observations needed to fit references")
        keys = torch.stack(
            [torch.zeros(12, dtype=torch.float64), *[record_features(self.records[i]) for i in ids]]
        )[None]
        rng = random.Random(self.seed + 8101)
        queries = []
        for i in range(12):
            row = self.records[rng.choice(ids)]
            value = {
                "position": [max(-1.0, min(1.0, x + rng.gauss(0, 0.04))) for x in row["position"]],
                "action": row["action"],
                "context": row["context"],
                "mask": [i % 3 != 0, True],
            }
            queries.append(features(value))
        train, validation = torch.stack(queries[:8])[None], torch.stack(queries[8:])[None]
        references = self.references.detach().clone().requires_grad_(True)

        def loss(q: torch.Tensor) -> torch.Tensor:
            self.work["reference_teacher_pairs"] += q.shape[1] * keys.shape[1]
            self.work["reference_summary_blocks"] += q.shape[1] * sum(
                (keys.shape[1] - 1) // (4**level) for level in (1, 2)
            )
            return pooled_chunk_kl(
                q,
                keys,
                references,
                visible_counts=torch.full((q.shape[1],), keys.shape[1], dtype=torch.int64),
                chunk_size=4,
                depth=2,
            )

        initial_train = float(loss(train).detach())
        initial_validation = float(loss(validation).detach())
        best = self.references.clone()
        best_validation = initial_validation
        selected_step = 0
        history = []
        for step in range(steps):
            objective = loss(train)
            objective.backward()  # type: ignore[no-untyped-call]  # PyTorch Tensor stub boundary
            with torch.no_grad():
                if references.grad is None or not bool(torch.isfinite(references.grad).all()):
                    raise ValueError("invalid routing gradient")
                references.add_(references.grad.clamp(-5, 5), alpha=-0.3)
                references.grad.zero_()
                val = float(loss(validation))
                if val < best_validation:
                    best, best_validation = references.detach().clone(), val
                    selected_step = step + 1
            history.append(
                {"step": step + 1, "train_loss": float(objective.detach()), "validation_loss": val}
            )
            self.work["reference_steps"] += 1
        with torch.no_grad():
            references.copy_(best)
            selected_train_loss = float(loss(train))
        self.references = best
        self.dirty = True
        self.cold_dirty = True
        self.router_fit = {
            "steps": self.router_fit["steps"] + steps,
            "initial_train_loss": initial_train,
            "initial_validation_loss": initial_validation,
            "train_loss": selected_train_loss,
            "selected_step": selected_step,
            "validation_loss": best_validation,
            "history": history,
            "train_cues": 8,
            "validation_cues": 4,
            "scope": "observed-bank query augmentation; external heldout queries stay outside engine",
            "reference_hash": sha(best.tolist()),
            "random_reference_hash": sha(self.random_references.tolist()),
        }
        self.revision += 1
        self._commit()
        return copy.deepcopy(self.router_fit)

    def start_sleep(self, strategy: str, steps: int, position: list[float], context: int) -> None:
        if self.sleep["busy"]:
            raise RuntimeError("offline work is already running")
        if strategy not in ("uniform", "priority", "coverage", "mixture"):
            raise ValueError("strategy must be uniform, priority, coverage or mixture")
        bounded_int(steps, "steps", 1, 320)
        pair(position, "position")
        context_value(context)
        if not self.heads:
            raise ValueError("collect observed experience first")
        if self.model_invalidated:
            with torch.random.fork_rng(devices=[]):
                torch.manual_seed(self.seed)
                self.models = nn.ModuleList([Dynamics().double() for _ in range(3)])
            self.trained_steps = 0
            self.last_loss = None
            self.model_invalidated = False
        self.sleep = {
            "busy": True,
            "strategy": strategy,
            "trace": [],
            "rollout": [],
            "error": None,
            "status": "training",
            "steps": steps,
            "position": position[:],
            "context": context,
            "initial_checkpoint_hash": self.model_hash(),
            "archive_hash": sha([r["checksum"] for r in self.records.values()]),
            "initial_work": self.work.copy(),
            "rollout_status": "not_started",
        }
        self.revision += 1
        self._commit()

    def sleep_step(self, *, backend: str = "zha") -> dict[str, Any]:
        if not self.sleep["busy"]:
            raise RuntimeError("offline job was not started")
        step = len(self.sleep["trace"])
        strategy = self.sleep["strategy"]
        current = sorted(self.heads.values())
        rng = random.Random(self.seed + self.trained_steps * 719 + step)
        scheduler = 0
        if strategy == "uniform" or (strategy == "mixture" and step % 4 != 0):
            seed_id = rng.choice(current)
        elif strategy in ("coverage", "mixture"):
            # Rare context and stale-use coverage are explicit, charged metadata scans.
            counts = {c: sum(self.records[i]["context"] == c for i in current) for c in (0, 1)}
            seed_id = min(
                current,
                key=lambda i: (
                    counts[self.records[i]["context"]],
                    self.metadata[i]["last_refresh"],
                    self.metadata[i]["uses"],
                    i,
                ),
            )
            self.metadata[seed_id]["last_refresh"] = self.tick
            scheduler = len(current)
        else:
            candidates = sorted(self.hot) or current[:16]
            rows = [self.records[i] for i in candidates]
            with torch.no_grad():
                error = (self.models[0](model_inputs(rows)) - model_targets(rows)).square().mean(1)
            seed_id = candidates[int(error.argmax())]
            scheduler = len(candidates)
        self.work["scheduler_observations"] += scheduler
        original = self.records[seed_id]
        value = {
            "position": [max(-1.0, min(1.0, v + rng.gauss(0, 0.06))) for v in original["position"]],
            "action": original["action"],
            "context": original["context"],
            "mask": [step % 4 != 0, True],
            "audit": False,
        }
        self.tick += 1
        read = self._read(value, backend=backend, audit=False, use=False)
        selected = [r["id"] for r in read["ranked"][:16]]
        if not selected:
            raise ValueError("hierarchy returned no observed training sources")
        rows = [self.records[i] for i in selected]
        inputs, targets = model_inputs(rows), model_targets(rows)
        losses = []
        for model in self.models:
            model.zero_grad(set_to_none=True)
            objective = (model(inputs) - targets).square().mean()
            if not bool(torch.isfinite(objective)):
                raise ValueError("nonfinite dynamics training loss")
            objective.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0, error_if_nonfinite=True)
            with torch.no_grad():
                for parameter in model.parameters():
                    if parameter.grad is None:
                        raise ValueError("missing model gradient")
                    parameter.add_(parameter.grad, alpha=-0.06)
            losses.append(float(objective.detach()))
        self.trained_steps += 1
        self.work["gradient_steps"] += 1
        self.work["training_examples"] += len(rows) * 3
        self.last_loss = sum(losses) / len(losses)
        self.last_query = {**read, "purpose": "observed-replay-training"}
        event = {
            "step": step + 1,
            "loss": self.last_loss,
            "sources": selected,
            "seed_cue": cue(value),
            "selected_count": len(read["selected_ids"]),
            "scheduler_observations": scheduler,
            "query_work": read["work"],
            "model_steps": self.trained_steps,
            "evidence": "observed",
            "read": read,
        }
        self.sleep["trace"].append(event)
        self.revision += 1
        self._commit()
        return copy.deepcopy(event)

    def rollout(
        self, position: list[float], context: int, *, horizon: int = 10
    ) -> list[dict[str, Any]]:
        start = pair(position, "position")
        context_value(context)
        bounded_int(horizon, "horizon", 1, 16)
        points: list[dict[str, Any]] = [
            {
                "x": start[0],
                "y": start[1],
                "evidence": "query_seed",
                "uncertainty": 0.0,
                "sources": [],
            }
        ]
        self.sleep["rollout_status"] = "completed"
        if self.model_invalidated:
            self.sleep["rollout_status"] = (
                "rejected: observed correction invalidated the model; a fresh offline fit is required"
            )
            self.sleep["rollout"] = points
            return copy.deepcopy(points)
        if self.trained_steps < 16:
            self.sleep["rollout_status"] = "rejected: model has fewer than16 learned updates"
            self.sleep["rollout"] = points
            return copy.deepcopy(points)
        current = start
        for _ in range(horizon):
            predictions = [
                (list(action), *self.predict(current, list(action), context)) for action in ACTIONS
            ]
            action, delta, spread = min(
                predictions,
                key=lambda p: sum((v + d - 0.72) ** 2 for v, d in zip(current, p[1], strict=True)),
            )
            read = self._read(
                {"position": current, "action": action, "context": context, "audit": False},
                use=False,
            )
            sources = [
                r["id"] for r in read["ranked"] if self.records[r["id"]]["context"] == context
            ][:6]
            support = min(
                (math.dist(current, self.records[i]["position"]) for i in sources), default=math.inf
            )
            predicted = [a + b for a, b in zip(current, delta, strict=True)]
            if spread > 0.08 or support > 0.7 or any(abs(v) > 1 for v in predicted):
                self.sleep["rollout_status"] = (
                    f"rejected: spread={spread:.4f}, observed support distance={support:.4f}, domain_valid={all(abs(v) <= 1 for v in predicted)}"
                )
                break
            current = predicted
            points.append(
                {
                    "x": current[0],
                    "y": current[1],
                    "evidence": "imagined",
                    "uncertainty": spread,
                    "sources": sources,
                    "action": action,
                    "model_checkpoint": self.model_hash(),
                }
            )
        self.sleep["rollout"] = points
        return copy.deepcopy(points)

    def finish_sleep(self) -> dict[str, Any]:
        self.rollout(self.sleep["position"], self.sleep["context"])
        self.sleep.update(busy=False, status="complete", checkpoint_hash=self.model_hash())
        self.revision += 1
        self._commit()
        return self.state()

    def fail_sleep(self, message: str) -> None:
        self.sleep.update(busy=False, status="error", error=message)
        self.revision += 1
        self._commit()

    def state(self) -> dict[str, Any]:
        current = set(self.heads.values())
        nodes = [
            {
                "id": i,
                "x": r["position"][0],
                "y": r["position"][1],
                "next_x": r["successor"][0],
                "next_y": r["successor"][1],
                "ax": r["action"][0],
                "ay": r["action"][1],
                "context": r["context"],
                "hot": i in self.hot,
                "current": i in current,
                "uses": self.metadata[i]["uses"],
                "salience": self._score(i),
                "version": r["version"],
                "evidence": "observed",
                "previous": r["previous"],
            }
            for i, r in self.records.items()
        ]
        return copy.deepcopy(
            {
                "schema": "somna-live-v1",
                "revision": self.revision,
                "tick": self.tick,
                "seed": self.seed,
                "archive": {
                    "total": len(self.records),
                    "current": len(current),
                    "hot": len(self.hot),
                    "cold": len(current - set(self.hot)),
                    "capacity": self.capacity,
                    "checksum": sha([r["checksum"] for r in self.records.values()]),
                },
                "nodes": nodes,
                "query": self.last_query,
                "model": {
                    "trained_steps": self.trained_steps,
                    "invalidated_by_correction": self.model_invalidated,
                    "loss": self.last_loss,
                    "checkpoint_hash": self.model_hash(),
                    "architecture": "three independent6→24→24→2 tanh MLPs; continuous action-conditioned deltas",
                    "router_fit": self.router_fit,
                },
                "sleep": self.sleep,
                "work": self.work.copy(),
                "indexes": self.maintenance.copy(),
                "limitations": [
                    "controlled continuous state; no learned image encoder",
                    "logical active limit, growing total archive/RSS",
                    "ensemble spread is a heuristic, not calibrated confidence",
                    "no speed or biological dreaming claim",
                ],
            }
        )

    def fork(self, destination: Path) -> MemoryEngine:
        if self.sleep["busy"]:
            raise ValueError("finish or stop the offline job before forking")
        if destination.exists():
            raise ValueError("refusing to overwrite a fork checkpoint")
        self._commit()
        target_db = sqlite3.connect(str(destination))
        try:
            self.db.backup(target_db)
        finally:
            target_db.close()
        return MemoryEngine(destination, bootstrap=0)

    def close(self) -> None:
        try:
            self._commit()
        finally:
            self.db.close()
            self.lock_file.close()
