"""Recompute diagnostics from inert traces and read-only original archives.

No imports from the lifecycle implementation, fixture generator or summarizer.
This is a separate self-review, not an external audit or numerical certificate.
"""

import argparse
import hashlib
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STOPWORDS = set(
    "a an and are as at be by did do does for from how in is it of on or the to was what which with".split()
)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


def score(query, text):
    q = set(re.findall(r"[a-z0-9]+", query.lower())) - STOPWORDS
    k = set(re.findall(r"[a-z0-9]+", text.lower())) - STOPWORDS
    dot = math.fsum(1.0 for word in q if word in k)
    return dot / math.sqrt(len(q) * len(k)) if q and k else 0.0


def check(condition, message):
    if not condition:
        raise RuntimeError(message)


def timing(values):
    ordered = sorted(values)
    return {
        name: ordered[min(len(ordered) - 1, int(f * (len(ordered) - 1)))] / 1e6
        for name, f in (("median_ms", 0.5), ("p95_ms", 0.95), ("max_ms", 1.0))
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--archives", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((args.results / "report.json").read_text())
    protocol = report["protocol"]
    for name, expected in report["source_sha256"].items():
        check(
            hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected,
            f"changed source: {name}",
        )
    queries = defaultdict(list)
    ingests = defaultdict(list)
    for row in map(json.loads, (args.results / "queries.jsonl").read_text().splitlines()):
        queries[row["run_id"]].append(row)
    for row in map(json.loads, (args.results / "ingest.jsonl").read_text().splitlines()):
        ingests[row["run_id"]].append(row)
    checked_queries = 0
    checked_originals = 0
    for run in report["runs"]:
        rid = run["run_id"]
        fixture = json.loads((args.results / f"fixture-{run['seed']}.json").read_text())
        check(
            hashlib.sha256(canonical(fixture)).hexdigest()
            == report["fixture_sha256"][str(run["seed"])],
            "fixture hash",
        )
        records = {
            event["identifier"]: {**event, "sequence": i + 1}
            for i, event in enumerate(event for event in fixture if event["kind"] == "remember")
        }
        check(
            len(queries[rid]) == sum(event["kind"] == "query" for event in fixture), "query count"
        )
        check(len(ingests[rid]) == len(records), "ingest count")
        heads = {}
        active = set()
        cursor = 0
        ordered_records = []
        raw_rows = {row["tick"]: row for row in queries[rid]}
        raw_writes = {row["tick"]: row for row in ingests[rid]}
        histories = []
        work = Counter()
        phase = defaultdict(lambda: [0, 0])
        peak = 0
        peak_payload = 0
        for event in fixture:
            tick = event["tick"]
            if event["kind"] == "remember":
                row = raw_writes[tick]
                check(set(row["active_before"]) == active, f"ingest hot continuity {rid}/{tick}")
                check(row["identifier"] == event["identifier"], "ingest identity")
                heads[event["key"]] = event["identifier"]
                ordered_records.append(event["identifier"])
                check(row["archive_records"] == len(ordered_records), "archive count")
            else:
                row = raw_rows[tick]
                histories.append(event["text"])
                histories = histories[-protocol["history_queries"] :]
                check(
                    row["query"] == event["text"] and row["expected"] == event["expected"],
                    "query identity",
                )
                check(
                    heads[records[event["expected"]]["key"]] == event["expected"],
                    "fixture current label",
                )
                check(set(row["active_before"]) == active, f"query hot continuity {rid}/{tick}")
                hot = [key for key in active if heads[records[key]["key"]] == key]
                recovery = row["recovery_scanned"]
                replay = row["replay_scanned"]
                current_query_number = sum(
                    event2["kind"] == "query" and event2["tick"] <= tick for event2 in fixture
                )
                scheduled = current_query_number % protocol["maintenance_every"] == 0
                extra = (
                    protocol["maintenance_rows"]
                    if scheduled and run["policy"] == "decay_probe"
                    else 0
                )
                check(len(recovery) <= protocol["recovery_rows"] + extra, "recovery budget")
                check(
                    len(replay)
                    <= (
                        protocol["maintenance_rows"]
                        if scheduled and run["policy"] == "decay_replay"
                        else 0
                    ),
                    "replay budget",
                )
                for batch in (recovery, replay):
                    tail = [key for key in ordered_records if records[key]["sequence"] > cursor]
                    prefix = [key for key in ordered_records if records[key]["sequence"] <= cursor]
                    expected_batch = (tail + prefix)[: len(batch)]
                    check(batch == expected_batch, f"physical cursor trace {rid}/{tick}")
                    if batch:
                        cursor = records[batch[-1]]["sequence"]
                candidate_ids = set(hot) | {
                    key for key in recovery if heads[records[key]["key"]] == key
                }
                ranked = sorted(
                    ((key, score(event["text"], records[key]["text"])) for key in candidate_ids),
                    key=lambda pair: (-pair[1], -records[pair[0]]["sequence"], pair[0]),
                )
                ranked = [pair for pair in ranked if pair[1] > 0]
                expected_id = ranked[0][0] if ranked else None
                check(row["returned"] == expected_id, f"independent retrieval {rid}/{tick}")
                check(row["correct"] == (expected_id == event["expected"]), "correctness label")
                check(not row["superseded_answer"], "stale result")
                if expected_id:
                    check(
                        math.isclose(row["score"], ranked[0][1], rel_tol=1e-14), "retrieval score"
                    )
                    check(
                        row["source"] == ("hot" if expected_id in hot else "archive"),
                        "source label",
                    )
                hot_rank = sorted(
                    ((key, score(event["text"], records[key]["text"])) for key in hot),
                    key=lambda pair: (-pair[1], -records[pair[0]]["sequence"], pair[0]),
                )
                hot_first = hot_rank[0][0] if hot_rank and hot_rank[0][1] > 0 else None
                check(
                    row["hot_first"] == hot_first
                    and row["hot_correct"] == (hot_first == event["expected"]),
                    "hot-first label",
                )
                w = row["work"]
                check(w["active_scores"] == len(hot), "active scoring accounting")
                check(
                    w["recovery_rows"] == len(recovery) and w["replay_rows"] == len(replay),
                    "physical-row accounting",
                )
                check(
                    w["archive_text_bytes"]
                    == sum(len(records[key]["text"].encode()) for key in recovery + replay),
                    "payload-byte accounting",
                )
                check(
                    w["recovery_scores"]
                    == sum(
                        key not in hot and heads[records[key]["key"]] == key for key in recovery
                    ),
                    "recovery-score accounting",
                )
                check(
                    w["replay_scores"] <= len(replay) * len(histories), "replay-score upper bound"
                )
                work.update(w)
                phase[event["phase"]][0] += int(row["correct"])
                phase[event["phase"]][1] += 1
                checked_queries += 1
            active = set(row["active_after"])
            check(len(active) == len(row["active_after"]), "duplicate hot identifier")
            check(
                all(
                    key in records
                    and records[key]["tick"] <= tick
                    and heads[records[key]["key"]] == key
                    for key in active
                ),
                "invalid hot record",
            )
            check(run["policy"] == "full" or len(active) <= run["capacity"], "hot capacity")
            peak = max(peak, len(active))
            peak_payload = max(
                peak_payload, sum(len(records[key]["text"].encode()) for key in active)
            )
        rows = queries[rid]
        expected_summary = {
            "queries": len(rows),
            "correct": sum(row["correct"] for row in rows),
            "hot_correct": sum(row["hot_correct"] for row in rows),
            "archive_correct": sum(row["correct"] and row["source"] == "archive" for row in rows),
            "superseded_answers": sum(row["superseded_answer"] for row in rows),
            "comparisons": work["active_scores"] + work["recovery_scores"] + work["replay_scores"],
            "archive_rows": work["recovery_rows"] + work["replay_rows"],
            "work": dict(sorted(work.items())),
            "phase": {
                name: {"correct": pair[0], "queries": pair[1]}
                for name, pair in sorted(phase.items())
            },
            "query_latency": timing([row["query_ns"] for row in rows]),
            "maintenance_total_ms": sum(row["maintenance_ns"] for row in rows) / 1e6,
            "ingest_latency": timing([row["ingest_ns"] for row in ingests[rid]]),
            "ingest_total_ms": sum(row["ingest_ns"] for row in ingests[rid]) / 1e6,
            "peak_hot_records": peak,
            "peak_hot_utf8_payload_bytes": peak_payload,
        }
        check(
            all(run[name] == value for name, value in expected_summary.items()),
            f"summary mismatch {rid}",
        )
        database = args.archives / f"{rid}.sqlite"
        connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        originals = list(connection.execute("SELECT * FROM records ORDER BY sequence"))
        check(
            len(originals)
            == len(records)
            == run["archive_records"]
            == run["originals_reopen_verified"],
            "original count",
        )
        final_heads = {}
        manifest = []
        for original in originals:
            rec = records[original["identifier"]]
            check(
                all(
                    original[name] == rec[name]
                    for name in ("identifier", "key", "text", "tick", "sequence")
                ),
                "original payload changed",
            )
            check(original["previous"] == final_heads.get(rec["key"]), "archive version chain")
            payload = json.dumps(
                [rec["identifier"], rec["key"], rec["text"], rec["tick"], original["previous"]],
                ensure_ascii=False,
            ).encode()
            check(original["sha256"] == hashlib.sha256(payload).hexdigest(), "original hash")
            final_heads[rec["key"]] = rec["identifier"]
            manifest.append([original["identifier"], original["sha256"]])
            checked_originals += 1
        check(
            dict(connection.execute("SELECT key, identifier FROM heads")) == final_heads == heads,
            "final heads",
        )
        check(
            hashlib.sha256(canonical(manifest)).hexdigest() == run["archive_manifest_sha256"],
            "archive manifest",
        )
        connection.close()
    audit = {
        "all_passed": True,
        "scope": "Separate trace/SQLite self-audit, not external validation or generalization evidence",
        "runs": len(report["runs"]),
        "queries": checked_queries,
        "original_records": checked_originals,
        "report_sha256": hashlib.sha256((args.results / "report.json").read_bytes()).hexdigest(),
        "source_commit": report["source_commit"],
    }
    (args.results / "audit.json").write_text(json.dumps(audit, indent=2) + "\n")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
