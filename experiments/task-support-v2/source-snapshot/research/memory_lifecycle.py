"""Experimental reversible index forgetting, separate from the ZHA numerical core.

The lexical scorer is deliberately simple. Neither score nor recovery is a
correctness certificate. SQLite originals grow; only the hot set is bounded.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from collections import deque
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

Policy = Literal["full", "fifo", "lru", "lfu", "decay", "decay_probe", "decay_replay"]
POLICIES = ("full", "fifo", "lru", "lfu", "decay", "decay_probe", "decay_replay")
STOP = frozenset(
    "a an and are as at be by did do does for from how in is it of on or the to was what which with".split()
)


class LifecycleError(ValueError):
    """Invalid input, unsupported state, integrity failure or exhausted storage."""


def integer(value: int, name: str, minimum: int = 0) -> None:
    if type(value) is not int or not minimum <= value <= 2**63 - 1:
        raise LifecycleError(f"{name} must be an integer in [{minimum}, 2**63-1]")


def terms(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", text.lower())) - STOP


def similarity(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / math.sqrt(len(left) * len(right))


def digest(identifier: str, key: str, text: str, tick: int, previous: str | None) -> str:
    payload = json.dumps([identifier, key, text, tick, previous], ensure_ascii=False).encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class Memory:
    sequence: int
    identifier: str
    key: str
    text: str
    tick: int
    previous: str | None
    sha256: str

    @property
    def tokens(self) -> frozenset[str]:
        return terms(self.text)


class Archive:
    """Single-controller archive. Only explicit new versions change current heads."""

    def __init__(self, path: Path | str, *, max_records: int = 10000, max_text_chars: int = 4096):
        integer(max_records, "max_records", 1)
        integer(max_text_chars, "max_text_chars", 1)
        self.max_records = max_records
        self.max_text_chars = max_text_chars
        self.connection = sqlite3.connect(str(path))
        self.connection.execute("PRAGMA foreign_keys=ON")
        self.connection.row_factory = sqlite3.Row
        try:
            self._initialize()
            self._validate()
        except BaseException:
            self.connection.close()
            raise

    def _initialize(self) -> None:
        tables = {
            row[0]
            for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if tables:
            if tables != {"format", "records", "heads"}:
                raise LifecycleError("unknown archive schema")
            versions = [row[0] for row in self.connection.execute("SELECT version FROM format")]
            if versions != ["ohm-lifecycle-v1"]:
                raise LifecycleError("unknown archive version")
            return
        self.connection.executescript("""
            BEGIN;
            CREATE TABLE format(version TEXT NOT NULL);
            INSERT INTO format VALUES ('ohm-lifecycle-v1');
            CREATE TABLE records(
                sequence INTEGER PRIMARY KEY,
                identifier TEXT UNIQUE NOT NULL,
                key TEXT NOT NULL,
                text TEXT NOT NULL,
                tick INTEGER NOT NULL CHECK(tick >= 0),
                previous TEXT REFERENCES records(identifier),
                sha256 TEXT NOT NULL
            );
            CREATE TABLE heads(key TEXT PRIMARY KEY, identifier TEXT UNIQUE NOT NULL REFERENCES records(identifier));
            CREATE TRIGGER immutable_update BEFORE UPDATE ON records BEGIN SELECT RAISE(ABORT, 'immutable record'); END;
            CREATE TRIGGER immutable_delete BEFORE DELETE ON records BEGIN SELECT RAISE(ABORT, 'immutable record'); END;
            COMMIT;
        """)

    def _validate(self) -> None:
        if self.count > self.max_records:
            raise LifecycleError("archive exceeds max_records")
        expected: dict[str, str] = {}
        last_tick = 0
        for row in self.connection.execute("SELECT * FROM records ORDER BY sequence"):
            record = self._record(row)
            if record.tick < last_tick or record.previous != expected.get(record.key):
                raise LifecycleError("invalid version chain or causal order")
            expected[record.key] = record.identifier
            last_tick = record.tick
        actual = dict(self.connection.execute("SELECT key, identifier FROM heads"))
        if actual != expected:
            raise LifecycleError("current-head identity mismatch")

    def _record(self, row: sqlite3.Row) -> Memory:
        record = Memory(**dict(row))
        self._validate_input(record.identifier, record.key, record.text, record.tick)
        wanted = digest(record.identifier, record.key, record.text, record.tick, record.previous)
        if record.sha256 != wanted:
            raise LifecycleError("record checksum mismatch")
        return record

    def _validate_input(self, identifier: str, key: str, text: str, tick: int) -> None:
        for value, name, limit in (
            (identifier, "identifier", 128),
            (key, "key", 256),
            (text, "text", self.max_text_chars),
        ):
            if not isinstance(value, str) or not value.strip() or len(value) > limit:
                raise LifecycleError(f"invalid {name}")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as error:
                raise LifecycleError(f"{name} must be valid UTF-8") from error
        if not terms(text):
            raise LifecycleError("text needs searchable terms")
        integer(tick, "tick")

    @property
    def count(self) -> int:
        return int(self.connection.execute("SELECT count(*) FROM records").fetchone()[0])

    @property
    def last_tick(self) -> int:
        return int(
            self.connection.execute("SELECT coalesce(max(tick), 0) FROM records").fetchone()[0]
        )

    def put(self, identifier: str, key: str, text: str, tick: int) -> Memory:
        self._validate_input(identifier, key, text, tick)
        if tick < self.last_tick:
            raise LifecycleError("write cannot move time backwards")
        if self.count >= self.max_records:
            raise LifecycleError("archive max_records exhausted")
        previous_row = self.connection.execute(
            "SELECT identifier FROM heads WHERE key=?", (key,)
        ).fetchone()
        previous = previous_row[0] if previous_row else None
        checksum = digest(identifier, key, text, tick, previous)
        try:
            with self.connection:
                cursor = self.connection.execute(
                    "INSERT INTO records(identifier,key,text,tick,previous,sha256) VALUES (?,?,?,?,?,?)",
                    (identifier, key, text, tick, previous, checksum),
                )
                self.connection.execute(
                    "INSERT INTO heads VALUES (?,?) ON CONFLICT(key) DO UPDATE SET identifier=excluded.identifier",
                    (key, identifier),
                )
        except sqlite3.IntegrityError as error:
            raise LifecycleError(f"archive transaction rejected: {error}") from error
        assert cursor.lastrowid is not None
        return Memory(cursor.lastrowid, identifier, key, text, tick, previous, checksum)

    def get(self, identifier: str) -> Memory:
        row = self.connection.execute(
            "SELECT * FROM records WHERE identifier=?", (identifier,)
        ).fetchone()
        if row is None:
            raise LifecycleError("unknown record")
        return self._record(row)

    def current(self, record: Memory) -> bool:
        row = self.connection.execute(
            "SELECT identifier FROM heads WHERE key=?", (record.key,)
        ).fetchone()
        return row is not None and row[0] == record.identifier

    def recent(self, limit: int) -> tuple[Memory, ...]:
        integer(limit, "limit")
        return tuple(
            self._record(row)
            for row in self.connection.execute(
                "SELECT r.* FROM records r JOIN heads h ON r.identifier=h.identifier ORDER BY r.sequence DESC LIMIT ?",
                (limit,),
            )
        )

    def scan(self, cursor: int, rows: int) -> tuple[tuple[Memory, ...], int]:
        """Physical-row budget includes stale/hot rows; at most one archive cycle."""
        integer(cursor, "cursor")
        integer(rows, "rows")
        limit = min(rows, self.count)
        found = list(
            self.connection.execute(
                "SELECT * FROM records WHERE sequence>? ORDER BY sequence LIMIT ?", (cursor, limit)
            )
        )
        if len(found) < limit:
            found.extend(
                self.connection.execute(
                    "SELECT * FROM records WHERE sequence<=? ORDER BY sequence LIMIT ?",
                    (cursor, limit - len(found)),
                )
            )
        records = tuple(self._record(row) for row in found)
        return records, records[-1].sequence if records else cursor

    def close(self) -> None:
        self.connection.close()


@dataclass(frozen=True)
class Config:
    policy: Policy = "decay_replay"
    capacity: int = 8
    recovery_rows: int = 4
    maintenance_rows: int = 8
    maintenance_every: int = 4
    history_queries: int = 8
    half_life: float = 24.0
    threshold: float = 0.45

    def __post_init__(self) -> None:
        if self.policy not in POLICIES:
            raise LifecycleError("unknown policy")
        for name in ("capacity", "maintenance_every", "history_queries"):
            integer(getattr(self, name), name, 1)
        for name in ("recovery_rows", "maintenance_rows"):
            integer(getattr(self, name), name)
        if (
            type(self.half_life) not in (int, float)
            or not math.isfinite(self.half_life)
            or self.half_life <= 0
        ):
            raise LifecycleError("half_life must be finite and positive")
        if (
            type(self.threshold) not in (int, float)
            or not math.isfinite(self.threshold)
            or not 0 < self.threshold <= 1
        ):
            raise LifecycleError("threshold must be in (0,1]")


@dataclass(frozen=True)
class Entry:
    memory: Memory
    tokens: frozenset[str]
    last_access: int
    hits: int = 0
    affinity: float = 0.0
    last_replay: int = 0


@dataclass
class Work:
    active_scores: int = 0
    recovery_rows: int = 0
    recovery_scores: int = 0
    replay_rows: int = 0
    replay_scores: int = 0
    archive_text_bytes: int = 0
    current_head_checks: int = 0
    promotions: int = 0
    evictions: int = 0


@dataclass(frozen=True)
class Hit:
    memory: Memory
    score: float
    source: Literal["hot", "archive"]


@dataclass(frozen=True)
class QueryResult:
    tick: int
    hits: tuple[Hit, ...]
    hot_first: str | None
    active_before: tuple[str, ...]
    active_after: tuple[str, ...]
    reactivated: tuple[str, ...]
    evicted: tuple[str, ...]
    replay_promoted: tuple[str, ...]
    work: Work
    maintenance_ns: int
    recovery_scanned: tuple[str, ...]
    replay_scanned: tuple[str, ...]


class MemorySession:
    """Session-local controller. No target labels or future data enter this API."""

    def __init__(self, archive: Archive, config: Config):
        self.archive = archive
        self.config = config
        self.tick = archive.last_tick
        self.queries = 0
        self.cursor = 0
        self.history: deque[frozenset[str]] = deque(maxlen=config.history_queries)
        limit = archive.max_records if config.policy == "full" else config.capacity
        self.active = {
            record.identifier: Entry(record, record.tokens, record.tick)
            for record in reversed(archive.recent(limit))
        }

    @property
    def active_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self.active))

    @property
    def active_text_bytes(self) -> int:
        return sum(len(entry.memory.text.encode()) for entry in self.active.values())

    def _time(self, tick: int) -> None:
        integer(tick, "tick")
        if tick < self.tick:
            raise LifecycleError("session cannot move time backwards")

    def _priority(self, entry: Entry, now: int) -> tuple[float, int, str]:
        policy = self.config.policy
        if policy == "fifo":
            value = float(entry.memory.sequence)
        elif policy == "lru":
            value = float(entry.last_access)
        elif policy == "lfu":
            value = float(entry.hits)
        else:
            value = (1 + entry.hits) * 2.0 ** (-(now - entry.last_access) / self.config.half_life)
            if policy == "decay_replay":
                value += (
                    0.5
                    * entry.affinity
                    * 2.0 ** (-(now - entry.last_replay) / self.config.half_life)
                )
        return value, entry.last_access, entry.memory.identifier

    def _admit(
        self, active: dict[str, Entry], entry: Entry, now: int, work: Work, evicted: list[str]
    ) -> None:
        identifier = entry.memory.identifier
        if identifier not in active:
            if self.config.policy != "full" and len(active) >= self.config.capacity:
                victim = min(active, key=lambda rid: self._priority(active[rid], now))
                del active[victim]
                evicted.append(victim)
                work.evictions += 1
            work.promotions += 1
        active[identifier] = entry

    def remember(self, identifier: str, key: str, text: str, tick: int) -> Memory:
        self._time(tick)
        record = self.archive.put(identifier, key, text, tick)
        # Archive supersession commits first. The owned controller is the only writer.
        active = {rid: item for rid, item in self.active.items() if item.memory.key != key}
        self._admit(active, Entry(record, record.tokens, tick), tick, Work(), [])
        self.active = active
        self.tick = tick
        return record

    def query(self, text: str, tick: int, *, top_k: int = 1) -> QueryResult:
        self._time(tick)
        integer(top_k, "top_k", 1)
        if not isinstance(text, str) or not text.strip() or len(text) > 512 or not terms(text):
            raise LifecycleError("query needs 1..512 characters and searchable terms")
        if top_k > self.archive.max_records:
            raise LifecycleError("top_k exceeds archive limit")
        try:
            text.encode("utf-8")
        except UnicodeEncodeError as error:
            raise LifecycleError("query must be valid UTF-8") from error
        cue = terms(text)
        # Plan query state locally; failures do not commit cursor/history/hot changes.
        active = dict(self.active)
        history = deque(self.history, maxlen=self.config.history_queries)
        history.append(cue)
        cursor = self.cursor
        work = Work()
        evicted: list[str] = []
        reactivated: list[str] = []
        replay_promoted: list[str] = []
        candidates: dict[str, Hit] = {}
        for rid, entry in list(active.items()):
            work.current_head_checks += 1
            if not self.archive.current(entry.memory):
                del active[rid]
                continue
            work.active_scores += 1
            score = similarity(cue, entry.tokens)
            if score > 0:
                candidates[rid] = Hit(entry.memory, score, "hot")

        def rank() -> list[Hit]:
            return sorted(
                candidates.values(),
                key=lambda hit: (-hit.score, -hit.memory.sequence, hit.memory.identifier),
            )

        hot = rank()
        hot_first = hot[0].memory.identifier if hot else None
        scheduled = (self.queries + 1) % self.config.maintenance_every == 0
        recovery = (
            self.config.recovery_rows if not hot or hot[0].score < self.config.threshold else 0
        )
        if self.config.policy == "decay_probe" and scheduled:
            recovery += self.config.maintenance_rows
        if self.config.policy == "full":
            recovery = 0
        batch, cursor = self.archive.scan(cursor, recovery)
        recovery_scanned = tuple(record.identifier for record in batch)
        work.recovery_rows += len(batch)
        for record in batch:
            work.archive_text_bytes += len(record.text.encode())
            work.current_head_checks += 1
            if record.identifier in active or not self.archive.current(record):
                continue
            work.recovery_scores += 1
            score = similarity(cue, record.tokens)
            if score > 0:
                candidates[record.identifier] = Hit(record, score, "archive")
        hits = tuple(rank()[:top_k])
        for hit in hits:
            rid = hit.memory.identifier
            entry = active.get(rid, Entry(hit.memory, hit.memory.tokens, hit.memory.tick))
            entry = replace(entry, last_access=tick, hits=entry.hits + 1)
            if rid not in active:
                reactivated.append(rid)
            self._admit(active, entry, tick, work, evicted)

        maintenance_ns = 0
        replay_scanned: tuple[str, ...] = ()
        if self.config.policy == "decay_replay" and scheduled:
            maintenance_start = time.perf_counter_ns()
            batch, cursor = self.archive.scan(cursor, self.config.maintenance_rows)
            replay_scanned = tuple(record.identifier for record in batch)
            work.replay_rows += len(batch)
            for record in batch:
                work.archive_text_bytes += len(record.text.encode())
                work.current_head_checks += 1
                if record.identifier in active or not self.archive.current(record):
                    continue
                record_tokens = record.tokens
                scores = [similarity(item, record_tokens) for item in history]
                work.replay_scores += len(scores)
                affinity = max(scores, default=0.0)
                if affinity >= self.config.threshold:
                    entry = Entry(
                        record, record.tokens, record.tick, affinity=affinity, last_replay=tick
                    )
                    self._admit(active, entry, tick, work, evicted)
                    replay_promoted.append(record.identifier)
            maintenance_ns = time.perf_counter_ns() - maintenance_start

        result = QueryResult(
            tick,
            hits,
            hot_first,
            self.active_ids,
            tuple(sorted(active)),
            tuple(reactivated),
            tuple(evicted),
            tuple(replay_promoted),
            work,
            maintenance_ns,
            recovery_scanned,
            replay_scanned,
        )
        self.active = active
        self.history = history
        self.cursor = cursor
        self.tick = tick
        self.queries += 1
        return result
