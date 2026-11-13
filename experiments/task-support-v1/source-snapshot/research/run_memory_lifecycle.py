"""Run the fixed lifecycle diagnostic; never tune retention on expected answers."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sqlite3
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from research.lifecycle_fixture import build_stream
from research.memory_lifecycle import Archive, Config, MemorySession, Policy

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "research/memory_lifecycle.py",
    "research/memory_console.py",
    "research/lifecycle_fixture.py",
    "research/run_memory_lifecycle.py",
    "research/memory_lifecycle_protocol.json",
    "tests/test_memory_lifecycle.py",
    "scripts/audit_memory_lifecycle.py",
    "scripts/check_lifecycle_mutations.py",
)


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def quantiles(values: list[int]) -> dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {"median_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    return {
        name: ordered[min(len(ordered) - 1, int(fraction * (len(ordered) - 1)))] / 1e6
        for name, fraction in (("median_ms", 0.5), ("p95_ms", 0.95), ("max_ms", 1.0))
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    phases: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        phases[row["phase"]].append(int(row["correct"]))
    work: Counter[str] = Counter()
    for row in rows:
        work.update(row["work"])
    return {
        "queries": len(rows),
        "correct": sum(row["correct"] for row in rows),
        "hot_correct": sum(row["hot_correct"] for row in rows),
        "archive_correct": sum(row["correct"] and row["source"] == "archive" for row in rows),
        "superseded_answers": sum(row["superseded_answer"] for row in rows),
        "work": dict(sorted(work.items())),
        "comparisons": work["active_scores"] + work["recovery_scores"] + work["replay_scores"],
        "archive_rows": work["recovery_rows"] + work["replay_rows"],
        "phase": {
            phase: {"correct": sum(values), "queries": len(values)}
            for phase, values in sorted(phases.items())
        },
        "query_latency": quantiles([row["query_ns"] for row in rows]),
        "maintenance_total_ms": sum(row["maintenance_ns"] for row in rows) / 1e6,
    }


def run_one(
    events: list[dict[str, Any]],
    protocol: dict[str, Any],
    policy: Policy,
    capacity: int,
    database: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    start = time.perf_counter_ns()
    archive = Archive(
        database, max_records=protocol["max_records"], max_text_chars=protocol["max_text_chars"]
    )
    config = Config(
        **{
            name: protocol[name]
            for name in (
                "recovery_rows",
                "maintenance_rows",
                "maintenance_every",
                "history_queries",
                "half_life",
                "threshold",
            )
        },
        policy=policy,
        capacity=capacity,
    )
    session = MemorySession(archive, config)
    startup_ns = time.perf_counter_ns() - start
    rows = []
    writes = []
    ingest_ns = []
    peak_hot = 0
    peak_hot_payload_bytes = 0
    originals: dict[str, str] = {}
    try:
        for event in events:
            if event["kind"] == "remember":
                before = session.active_ids
                start = time.perf_counter_ns()
                session.remember(event["identifier"], event["key"], event["text"], event["tick"])
                ingest_ns.append(time.perf_counter_ns() - start)
                originals[event["identifier"]] = event["text"]
                writes.append(
                    {
                        "tick": event["tick"],
                        "identifier": event["identifier"],
                        "active_before": before,
                        "active_after": session.active_ids,
                        "ingest_ns": ingest_ns[-1],
                        "archive_records": archive.count,
                    }
                )
            else:
                start = time.perf_counter_ns()
                result = session.query(event["text"], event["tick"], top_k=protocol["top_k"])
                elapsed = time.perf_counter_ns() - start
                hit = result.hits[0] if result.hits else None
                rows.append(
                    {
                        "tick": event["tick"],
                        "phase": event["phase"],
                        "query": event["text"],
                        "expected": event["expected"],
                        "returned": hit.memory.identifier if hit else None,
                        "source": hit.source if hit else None,
                        "score": hit.score if hit else None,
                        "hot_first": result.hot_first,
                        "correct": bool(hit and hit.memory.identifier == event["expected"]),
                        "hot_correct": result.hot_first == event["expected"],
                        "superseded_answer": bool(hit and not archive.current(hit.memory)),
                        "active_before": result.active_before,
                        "active_after": result.active_after,
                        "reactivated": result.reactivated,
                        "evicted": result.evicted,
                        "replay_promoted": result.replay_promoted,
                        "work": asdict(result.work),
                        "query_ns": elapsed,
                        "maintenance_ns": result.maintenance_ns,
                        "recovery_scanned": result.recovery_scanned,
                        "replay_scanned": result.replay_scanned,
                    }
                )
            peak_hot = max(peak_hot, len(session.active))
            peak_hot_payload_bytes = max(peak_hot_payload_bytes, session.active_text_bytes)
            if policy != "full" and len(session.active) > capacity:
                raise RuntimeError("hot capacity violated")
        manifest = [
            (row["identifier"], row["sha256"])
            for row in archive.connection.execute(
                "SELECT identifier, sha256 FROM records ORDER BY sequence"
            )
        ]
        for identifier, text in originals.items():
            if archive.get(identifier).text != text:
                raise RuntimeError("original text was changed")
        final_count = archive.count
    finally:
        archive.close()
    # Reopening verifies every hash/chain and exercises durable original recovery.
    start = time.perf_counter_ns()
    reopened = Archive(
        database, max_records=protocol["max_records"], max_text_chars=protocol["max_text_chars"]
    )
    try:
        for identifier, text in originals.items():
            if reopened.get(identifier).text != text:
                raise RuntimeError("original missing after reopen")
    finally:
        reopened.close()
    reopen_ns = time.perf_counter_ns() - start
    return (
        rows,
        writes,
        {
            **summarize(rows),
            "policy": policy,
            "capacity": capacity,
            "peak_hot_records": peak_hot,
            "peak_hot_utf8_payload_bytes": peak_hot_payload_bytes,
            "archive_records": final_count,
            "archive_file_bytes": database.stat().st_size,
            "originals_reopen_verified": len(originals),
            "archive_manifest_sha256": hashlib.sha256(encoded(manifest)).hexdigest(),
            "startup_ms": startup_ns / 1e6,
            "reopen_validation_ms": reopen_ns / 1e6,
            "ingest_latency": quantiles(ingest_ns),
            "ingest_total_ms": sum(ingest_ns) / 1e6,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archives", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.archives.exists():
        raise SystemExit("refusing existing results or archive directory; preserve prior attempts")
    dirty = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    if dirty:
        raise SystemExit("commit source/protocol before the diagnostic run")
    protocol = json.loads((ROOT / "research/memory_lifecycle_protocol.json").read_text())
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    args.output.mkdir(parents=True)
    args.archives.mkdir(parents=True)
    all_summaries = []
    fixture_hashes = {}
    with (
        (args.output / "queries.jsonl").open("w") as traces,
        (args.output / "ingest.jsonl").open("w") as ingests,
    ):
        for seed in protocol["seeds"]:
            events = build_stream(seed)
            fixture_hashes[str(seed)] = hashlib.sha256(encoded(events)).hexdigest()
            (args.output / f"fixture-{seed}.json").write_bytes(encoded(events) + b"\n")
            for capacity in protocol["capacities"]:
                for policy in protocol["policies"]:
                    run_id = f"seed-{seed}-capacity-{capacity}-{policy}"
                    rows, writes, summary = run_one(
                        events, protocol, policy, capacity, args.archives / f"{run_id}.sqlite"
                    )
                    summary.update(seed=seed, run_id=run_id)
                    all_summaries.append(summary)
                    for row in rows:
                        traces.write(json.dumps({"run_id": run_id, **row}, sort_keys=True) + "\n")
                    for row in writes:
                        ingests.write(json.dumps({"run_id": run_id, **row}, sort_keys=True) + "\n")
                    print(
                        f"{run_id}: {summary['correct']}/{summary['queries']} current-record hits; {summary['comparisons']} comparisons",
                        flush=True,
                    )
    result = {
        "schema": "ohm-memory-lifecycle-result-v1",
        "source_commit": commit,
        "source_tree_clean_at_start": True,
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES
        },
        "protocol": protocol,
        "fixture_sha256": fixture_hashes,
        "python": platform.python_version(),
        "sqlite": sqlite3.sqlite_version,
        "platform": platform.platform(),
        "runs": all_summaries,
        "limitations": [
            "Authored diagnostic fixture, not held-out real-assistant quality",
            "Shared lexical scorer, not ZHA or semantic embeddings",
            "No hyperparameter tuning, no novelty or speed claim",
            "Single process, one lifecycle pass per setting; timing is descriptive",
            "Hot state is bounded; archive, SQLite index and metadata are not compressed away",
            "Controller state is not persistent across restarts",
            "No answerability, mathematical attention-error or factual-correctness certificate",
        ],
    }
    (args.output / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
