"""Read-only presentation of the completed routing replay study."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
from typing import Any

DATASET = "task-replay-v1"
PREFIX = "persistent_replay_"


def read_json(path: Path, checksum: str | None = None) -> Any:
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("replay presentation artifact too large")
    raw = path.read_bytes()
    if checksum is not None and hashlib.sha256(raw).hexdigest() != checksum:
        raise ValueError("replay presentation checksum differs")
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as stream:
            raw = stream.read(128 * 1024 * 1024 + 1)
        if len(raw) > 128 * 1024 * 1024:
            raise ValueError("expanded replay artifact too large")
    return json.loads(raw)


def catalog(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = root / "experiments" / DATASET
    if not (base / "report.json").exists() or not (base / "INDEPENDENT_AUDIT.json").exists():
        return [], []
    report = read_json(base / "report.json")
    if not report.get("complete") or not read_json(base / "INDEPENDENT_AUDIT.json").get(
        "all_passed"
    ):
        return [], []
    protocol = read_json(base / "protocol.json")
    learned = {
        f"{schedule}-{seed}"
        for schedule in protocol["schedules"]
        for seed in protocol["optimizer_seeds"]
    }
    conditions = {
        "parent",
        "random",
        "exact",
        "no_recovery",
        "parent-cap96",
        "exact-cap96",
    } | learned
    expected = {
        (c, e, s)
        for c in conditions
        for e in protocol["environments"]
        for s in protocol["comparison_seeds"]
    }
    actual = {(r["condition"], r["environment"], r["seed"]) for r in report["runs"]}
    if actual != expected or len(report["runs"]) != len(expected):
        return [], []
    rows = []
    for r in report["runs"]:
        c = r["costs"]
        method = PREFIX + r["condition"]
        rows.append(
            {
                **r,
                "uid": "minigrid:" + DATASET + ":" + r["file"],
                "task": "minigrid",
                "dataset": DATASET,
                "environment_id": r["environment"],
                "reader": method,
                "config": method,
                "split": r["environment"] + "/" + DATASET,
                "level_id": r["seed"],
                "expansion_limit": protocol["step_cap"],
                "expanded": r["steps"],
                "pushes": None,
                "wall_seconds": None,
                "read_work": {
                    "raw_key_scores": c["archive_raw_pairs"] + c["archive_rerank_pairs"],
                    "summary_dot_products": c["archive_summary_dot_products"],
                },
            }
        )
    summaries = []
    for env in protocol["environments"]:
        for condition in conditions:
            subset = [
                r for r in report["runs"] if r["environment"] == env and r["condition"] == condition
            ]
            summaries.append(
                {
                    "task": "minigrid",
                    "dataset": DATASET,
                    "environment_id": env,
                    "reader": PREFIX + condition,
                    "episodes": len(subset),
                    "successes": sum(r["success"] for r in subset),
                }
            )
    return rows, summaries


def metadata(root: Path, condition: str) -> dict[str, Any]:
    base = root / "experiments" / DATASET
    report = read_json(base / "report.json")
    quality = read_json(base / "quality.json")["conditions"].get(condition)
    parent = read_json(base / "parent-references.json")
    result = {
        "condition": condition,
        "outcome": next(r for r in report["summary"] if r["condition"] == condition),
        "parent_outcome": next(
            r
            for r in report["summary"]
            if r["condition"] == ("parent-cap96" if condition.endswith("cap96") else "parent")
        ),
        "source": "completed recorded routing replay study",
        "parent_hash": parent["sha256"],
        "quality": quality,
        "learning": None,
        "scope": "learning used other observed wake worlds; this maze is a fresh-seed retest",
    }
    record = next(
        (r for r in read_json(base / "learning.json")["runs"] if r["condition"] == condition), None
    )
    if record is not None:
        trace = read_json(base / record["file"], record["sha256"])
        items = read_json(
            base / report["corpus_artifact"]["file"], report["corpus_artifact"]["sha256"]
        )
        by_id = {i["id"]: i for i in items}
        result["learning"] = {
            "schedule": trace["schedule"],
            "seed": trace["seed"],
            "steps": trace["steps"],
            "selected_step": trace["selected_step"],
            "parameters_changed": trace["selected_parameters_changed"],
            "history": trace["history"],
            "work": trace["work"],
            "child_hash": trace["child_hash"],
            "sources": [
                {
                    "step": u["step"],
                    "sample_id": u["sample_id"],
                    "role": u["role"],
                    "context": by_id[u["sample_id"]]["context"],
                    "source_step": by_id[u["sample_id"]]["step"],
                    "source_count": len(by_id[u["sample_id"]]["source_ids"]),
                    "loss": u["loss"],
                }
                for u in trace["updates"]
            ],
        }
    return result
