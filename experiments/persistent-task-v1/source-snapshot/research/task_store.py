"""Single-writer canonical task observations and reversible active membership.

A context identifies one world revision and coordinate frame. A simulator reset
must use a new context: this store does not infer cross-reset world equivalence.
"""

from __future__ import annotations

import fcntl
import json
import math
import sqlite3
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

from research.minigrid_benchmark import FEATURE_VERSION, Fact
from research.task_references import RouterCheckpoint, digest, identity

FORMAT = "persistent-task-v1"


@dataclass(frozen=True)
class WorkspaceConfig:
    capacity: int = 96
    recovery_limit: int = 16
    half_life: float = 32.0
    retire_below: float = 0.5
    max_records: int = 8192

    def __post_init__(self) -> None:
        for name, low, high in (
            ("capacity", 4, 192),
            ("recovery_limit", 0, 192),
            ("max_records", 1, 65536),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"invalid {name}")
        if self.recovery_limit > self.capacity:
            raise ValueError("recovery limit exceeds active capacity")
        if (
            type(self.half_life) not in (int, float)
            or not math.isfinite(self.half_life)
            or self.half_life <= 0
            or type(self.retire_below) not in (int, float)
            or not math.isfinite(self.retire_below)
            or not 0 <= self.retire_below <= 1
        ):
            raise ValueError("invalid decay configuration")


def valid_raw(visible: list[Fact]) -> None:
    if (
        not isinstance(visible, list)
        or not 1 <= len(visible) <= 49
        or len({f.position for f in visible if isinstance(f, Fact)}) != len(visible)
    ):
        raise ValueError("expected1..49 unique current observations")
    for f in visible:
        if (
            not isinstance(f, Fact)
            or f.id != 0
            or any(
                type(v) is not int
                for v in (f.x, f.y, f.object, f.color, f.state, f.observed_step, f.first_seen)
            )
            or not -32 <= f.x < 32
            or not -32 <= f.y < 32
            or not 1 <= f.object <= 10
            or not 0 <= f.color <= 5
            or not 0 <= f.state <= 2
            or not 0 <= f.first_seen <= f.observed_step
            or type(f.cue) is not bool
            or f.previous is not None
        ):
            raise ValueError("invalid raw observed fact")
    if len({f.observed_step for f in visible}) != 1:
        raise ValueError("observation batch spans multiple steps")


class TaskStore:
    """SQLite is the transactional reference backend, not an index-speed claim."""

    def __init__(
        self,
        path: Path,
        *,
        config: WorkspaceConfig | None = None,
        router: RouterCheckpoint | None = None,
    ) -> None:
        self.path, self._config = path, config or WorkspaceConfig()
        self._router = router or RouterCheckpoint.fixed()
        self.work = dict.fromkeys(
            (
                "startup_rows",
                "index_payload_rows",
                "active_payload_rows",
                "recovery_payload_rows",
                "current_payload_rows",
                "export_payload_rows",
                "observation_lookups",
                "metadata_rows",
                "write_attempts",
            ),
            0,
        )
        self.lock = path.with_suffix(path.suffix + ".lock").open("a+b")
        try:
            fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.lock.close()
            raise ValueError("task archive already has an active writer") from error
        try:
            self.db = sqlite3.connect(path)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA foreign_keys=ON")
            self._initialize()
            self._validate()
        except BaseException:
            if hasattr(self, "db"):
                self.db.close()
            self.lock.close()
            raise

    @property
    def router(self) -> RouterCheckpoint:
        return self._router

    @property
    def config(self) -> WorkspaceConfig:
        return self._config

    def _initialize(self) -> None:
        tables = {
            r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        expected = {"meta", "contexts", "records", "heads"}
        metadata = {
            "format": FORMAT,
            "features": FEATURE_VERSION,
            "workspace": asdict(self.config),
            "router": self.router.sha256,
        }
        if tables:
            if tables != expected:
                raise ValueError("incompatible task archive schema")
            row = self.db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()
            if row is None or json.loads(row[0]) != metadata:
                raise ValueError("incompatible task archive configuration/reference identity")
            return
        self.db.executescript("""
            BEGIN;
            CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE contexts(name TEXT PRIMARY KEY,data TEXT NOT NULL,sha256 TEXT NOT NULL);
            CREATE TABLE records(id INTEGER PRIMARY KEY,context TEXT NOT NULL REFERENCES contexts(name),x INTEGER NOT NULL,y INTEGER NOT NULL,previous INTEGER REFERENCES records(id),data TEXT NOT NULL,sha256 TEXT NOT NULL);
            CREATE TABLE heads(context TEXT NOT NULL REFERENCES contexts(name),x INTEGER NOT NULL,y INTEGER NOT NULL,id INTEGER UNIQUE NOT NULL REFERENCES records(id),active INTEGER NOT NULL CHECK(active IN(0,1)),hits INTEGER NOT NULL CHECK(hits>=0),last_use INTEGER NOT NULL CHECK(last_use>=0),PRIMARY KEY(context,x,y));
            CREATE INDEX active_heads ON heads(context,active);
            CREATE INDEX records_context ON records(context,id);
            CREATE TRIGGER immutable_update BEFORE UPDATE ON records BEGIN SELECT RAISE(ABORT,'immutable task observation'); END;
            CREATE TRIGGER immutable_delete BEFORE DELETE ON records BEGIN SELECT RAISE(ABORT,'immutable task observation'); END;
            COMMIT;
        """)
        with self.db:
            self.db.execute(
                "INSERT INTO meta VALUES('identity',?)", (json.dumps(metadata, sort_keys=True),)
            )

    def _decode(self, row: sqlite3.Row, tag: str) -> Fact:
        self.work[tag] += 1
        data = json.loads(row["data"])
        if row["sha256"] != digest([row["context"], data]):
            raise ValueError("task observation checksum mismatch")
        try:
            fact = Fact(**data)
            valid_raw([replace(fact, id=0, previous=None)])
        except (TypeError, KeyError) as error:
            raise ValueError("invalid task record payload") from error
        if (
            fact.id != row["id"]
            or fact.previous != row["previous"]
            or fact.position != (row["x"], row["y"])
        ):
            raise ValueError("task observation identity mismatch")
        return fact

    def _validate(self) -> None:
        if self.count > self.config.max_records:
            raise ValueError("task archive exceeds configured record limit")
        triggers = {
            r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
        }
        if not {"immutable_update", "immutable_delete"} <= triggers:
            raise ValueError("missing immutable-observation triggers")
        expected: dict[tuple[str, int, int], int] = {}
        last_step: dict[str, int] = {}
        for row in self.db.execute("SELECT * FROM records ORDER BY id"):
            fact = self._decode(row, "startup_rows")
            k = (row["context"], fact.x, fact.y)
            if fact.previous != expected.get(k) or fact.observed_step < last_step.get(
                row["context"], -1
            ):
                raise ValueError("invalid task version chain/causal order")
            expected[k] = fact.id
            last_step[row["context"]] = fact.observed_step
        actual = {
            (r["context"], r["x"], r["y"]): r["id"] for r in self.db.execute("SELECT * FROM heads")
        }
        if actual != expected:
            raise ValueError("task current-head identity mismatch")
        for row in self.db.execute("SELECT name FROM contexts"):
            context = row[0]
            state = self.state(context)
            if state["last_step"] < last_step.get(context, -1):
                raise ValueError("task state predates observations")
            heads = list(self.db.execute("SELECT * FROM heads WHERE context=?", (context,)))
            if sum(r["active"] for r in heads) > self.config.capacity or any(
                r["last_use"] > state["clock"] for r in heads
            ):
                raise ValueError("invalid persisted active metadata")
            bits = bytearray(512)
            for h in heads:
                index = (h["y"] + 32) * 64 + h["x"] + 32
                bits[index // 8] |= 1 << (index % 8)
            if bytes(bits).hex() != state["coverage"]:
                raise ValueError("task coverage differs from observed coordinates")

    @property
    def count(self) -> int:
        return int(self.db.execute("SELECT count(*) FROM records").fetchone()[0])

    def bind(self, context: str) -> None:
        identity(context)
        if self.db.execute("SELECT 1 FROM contexts WHERE name=?", (context,)).fetchone():
            return
        if self.db.execute("SELECT count(*) FROM contexts").fetchone()[0] >= 128:
            raise ValueError("task context limit reached")
        state = {
            "clock": 0,
            "last_step": -1,
            "version": 0,
            "coverage": bytes(512).hex(),
            "visible": [],
        }
        with self.db:
            self.db.execute(
                "INSERT INTO contexts VALUES(?,?,?)",
                (context, json.dumps(state), digest([context, state])),
            )

    def state(self, context: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT data,sha256 FROM contexts WHERE name=?", (context,)
        ).fetchone()
        if row is None:
            raise ValueError("unknown task context")
        state: dict[str, Any] = json.loads(row[0])
        if (
            row[1] != digest([context, state])
            or set(state) != {"clock", "last_step", "version", "coverage", "visible"}
            or any(
                type(state[k]) is not int or not 0 <= state[k] <= 2**53
                for k in ("clock", "version")
            )
            or type(state["last_step"]) is not int
            or state["last_step"] < -1
            or not isinstance(state["coverage"], str)
            or len(bytes.fromhex(state["coverage"])) != 512
        ):
            raise ValueError("task controller state integrity failure")
        return state

    def _save_state(self, context: str, state: dict[str, Any]) -> None:
        if state["clock"] > 2**53:
            raise ValueError("logical clock exhausted")
        self.db.execute(
            "UPDATE contexts SET data=?,sha256=? WHERE name=?",
            (json.dumps(state, allow_nan=False), digest([context, state]), context),
        )

    def _admit(self, context: str, ids: list[int], clock: int) -> list[int]:
        # One batch admission reserves its slots; sequential promotions cannot evict each other.
        reserved = list(dict.fromkeys(ids))[: self.config.capacity]
        old = list(
            self.db.execute(
                "SELECT id,hits,last_use FROM heads WHERE context=? AND active=1", (context,)
            )
        )
        self.work["metadata_rows"] += len(old)
        remaining = sorted(
            (r for r in old if r["id"] not in reserved),
            key=lambda r: (-self._utility(r, clock), -r["last_use"], r["id"]),
        )
        keep = set(reserved + [r["id"] for r in remaining[: self.config.capacity - len(reserved)]])
        evicted = [r["id"] for r in old if r["id"] not in keep]
        for identifier in evicted:
            self.db.execute(
                "UPDATE heads SET active=0 WHERE context=? AND id=?", (context, identifier)
            )
        for identifier in reserved:
            changed = self.db.execute(
                "UPDATE heads SET active=1,last_use=? WHERE context=? AND id=?",
                (clock, context, identifier),
            ).rowcount
            if changed != 1:
                raise ValueError("admission references a foreign/superseded observation")
        return evicted

    def _utility(self, row: sqlite3.Row, clock: int) -> float:
        return float(
            (1 + math.log1p(row["hits"]))
            * 2.0 ** (-(clock - row["last_use"]) / self.config.half_life)
        )

    def observe(self, context: str, visible: list[Fact]) -> list[Fact]:
        valid_raw(visible)
        state = self.state(context)
        if visible[0].observed_step < state["last_step"]:
            raise ValueError("observation cannot rewind its world/frame context")
        state["clock"] += 1
        state["last_step"] = visible[0].observed_step
        state["visible"] = [asdict(f) for f in visible]
        bits = bytearray.fromhex(state["coverage"])
        added, current = [], []
        with self.db:
            next_id = int(
                self.db.execute("SELECT coalesce(max(id),0)+1 FROM records").fetchone()[0]
            )
            count = self.count
            for f in visible:
                row = self.db.execute(
                    "SELECT r.* FROM records r JOIN heads h ON h.id=r.id WHERE h.context=? AND h.x=? AND h.y=?",
                    (context, f.x, f.y),
                ).fetchone()
                self.work["observation_lookups"] += 1
                previous = self._decode(row, "current_payload_rows") if row else None
                same = previous is not None and (previous.object, previous.color) == (
                    f.object,
                    f.color,
                )
                cue = f.cue or bool(same and previous and previous.cue)
                if previous is not None and (
                    previous.object,
                    previous.color,
                    previous.state,
                    previous.cue,
                ) == (f.object, f.color, f.state, cue):
                    current.append(previous.id)
                else:
                    if count >= self.config.max_records:
                        raise ValueError("task record limit reached")
                    record = replace(
                        f,
                        id=next_id,
                        previous=previous.id if previous else None,
                        first_seen=previous.first_seen if previous else f.observed_step,
                        cue=cue,
                    )
                    payload = asdict(record)
                    self.db.execute(
                        "INSERT INTO records VALUES(?,?,?,?,?,?,?)",
                        (
                            record.id,
                            context,
                            record.x,
                            record.y,
                            record.previous,
                            json.dumps(payload),
                            digest([context, payload]),
                        ),
                    )
                    self.db.execute(
                        "INSERT INTO heads VALUES(?,?,?,?,0,0,?) ON CONFLICT(context,x,y) DO UPDATE SET id=excluded.id,active=0,hits=0,last_use=excluded.last_use",
                        (context, f.x, f.y, record.id, state["clock"]),
                    )
                    state["version"] = record.id
                    added.append(record)
                    current.append(record.id)
                    next_id += 1
                    count += 1
                    self.work["write_attempts"] += 1
                index = (f.y + 32) * 64 + f.x + 32
                bits[index // 8] |= 1 << (index % 8)
            state["coverage"] = bytes(bits).hex()
            self._admit(context, list(reversed(current)), state["clock"])
            self._save_state(context, state)
        return added

    def heads(
        self, context: str, *, active: bool = False, tag: str = "index_payload_rows"
    ) -> list[Fact]:
        if tag not in self.work:
            raise ValueError("unknown payload accounting channel")
        rows = self.db.execute(
            "SELECT r.* FROM records r JOIN heads h ON h.id=r.id WHERE h.context=?"
            + (" AND h.active=1" if active else "")
            + " ORDER BY r.id",
            (context,),
        )
        return [self._decode(r, tag) for r in rows]

    def current(self, context: str, positions: list[tuple[int, int]]) -> list[Fact]:
        result = []
        for x, y in positions:
            row = self.db.execute(
                "SELECT r.* FROM records r JOIN heads h ON h.id=r.id WHERE h.context=? AND h.x=? AND h.y=?",
                (context, x, y),
            ).fetchone()
            if row is None:
                raise ValueError("current observation has no canonical source")
            result.append(self._decode(row, "current_payload_rows"))
        return result

    def fetch(self, context: str, ids: list[int]) -> list[Fact]:
        result = []
        for identifier in dict.fromkeys(ids):
            row = self.db.execute(
                "SELECT r.* FROM records r JOIN heads h ON h.id=r.id WHERE h.context=? AND h.id=?",
                (context, identifier),
            ).fetchone()
            if row is None:
                raise ValueError("recovery requested foreign/superseded observation")
            result.append(self._decode(row, "recovery_payload_rows"))
        return result

    def promote(self, context: str, ids: list[int]) -> list[int]:
        state = self.state(context)
        with self.db:
            evicted = self._admit(context, ids, state["clock"])
            self._save_state(context, state)
        return evicted

    def use(self, context: str, ids: list[int]) -> None:
        state = self.state(context)
        with self.db:
            state["clock"] += 1
            for identifier in ids:
                if (
                    self.db.execute(
                        "UPDATE heads SET hits=hits+1,last_use=? WHERE context=? AND id=? AND active=1",
                        (state["clock"], context, identifier),
                    ).rowcount
                    != 1
                ):
                    raise ValueError("returned fact is outside active current memory")
            self._save_state(context, state)

    def fade(self, context: str, ticks: int) -> list[int]:
        if type(ticks) is not int or not 0 <= ticks <= 1000000:
            raise ValueError("invalid ageing interval")
        state = self.state(context)
        state["clock"] += ticks
        rows = list(
            self.db.execute(
                "SELECT id,hits,last_use FROM heads WHERE context=? AND active=1", (context,)
            )
        )
        self.work["metadata_rows"] += len(rows)
        retired = [
            r["id"] for r in rows if self._utility(r, state["clock"]) < self.config.retire_below
        ]
        with self.db:
            for identifier in retired:
                self.db.execute(
                    "UPDATE heads SET active=0 WHERE context=? AND id=?", (context, identifier)
                )
            self._save_state(context, state)
        return retired

    def export(self, context: str) -> list[dict[str, Any]]:
        """Explicit evaluator export; never called during planning."""
        return [
            asdict(self._decode(row, "export_payload_rows"))
            for row in self.db.execute(
                "SELECT * FROM records WHERE context=? ORDER BY id", (context,)
            )
        ]

    def close(self) -> None:
        self.db.close()
        self.lock.close()
