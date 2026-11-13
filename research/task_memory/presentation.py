"""Read-only catalog/summary adapter for independently audited support trials."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from research.replay_dashboard import read_json

DATASET = "task-support-v1"
DATASETS = (DATASET, "task-support-v2")
PREFIX = "persistent_support_"


def catalog(root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows, summaries = [], []
    for dataset in DATASETS:
        r, s = _catalog(root, dataset)
        rows.extend(r)
        summaries.extend(s)
    return rows, summaries


def _catalog(root: Path, dataset: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = root / "experiments" / dataset
    if not (base / "report.json").exists() or not (base / "INDEPENDENT_AUDIT.json").exists():
        return [], []
    report = read_json(base / "report.json")
    audit = read_json(base / "INDEPENDENT_AUDIT.json")
    p = read_json(base / "protocol.json")
    expected = {
        (c, e, s) for c in p["conditions"] for e in p["environments"] for s in p["comparison_seeds"]
    }
    actual = {(r["condition"], r["environment"], r["seed"]) for r in report["runs"]}
    if (
        not report.get("complete")
        or not audit.get("all_passed")
        or audit["runs"] != len(expected)
        or actual != expected
        or len(report["runs"]) != len(expected)
    ):
        return [], []
    rows = []
    for r in report["runs"]:
        c = r["costs"]
        method = PREFIX + r["condition"]
        rows.append(
            {
                **r,
                "uid": "minigrid:" + dataset + ":" + r["file"],
                "task": "minigrid",
                "dataset": dataset,
                "environment_id": r["environment"],
                "reader": method,
                "config": method,
                "split": r["environment"] + "/" + dataset,
                "level_id": r["seed"],
                "expansion_limit": p["step_cap"],
                "expanded": r["steps"],
                "pushes": None,
                "wall_seconds": None,
                "read_work": {
                    "raw_key_scores": c["archive_raw_pairs"] + c["archive_rerank_pairs"],
                    "summary_dot_products": c["archive_summary_dot_products"],
                },
            }
        )
    summary = []
    for e in p["environments"]:
        for c in p["conditions"]:
            subset = [r for r in rows if r["environment"] == e and r["condition"] == c]
            summary.append(
                {
                    "task": "minigrid",
                    "dataset": dataset,
                    "environment_id": e,
                    "reader": PREFIX + c,
                    "episodes": len(subset),
                    "successes": sum(r["success"] for r in subset),
                }
            )
    return rows, summary


def metadata(root: Path, condition: str, dataset: str = DATASET) -> dict[str, Any]:
    report = read_json(root / "experiments" / dataset / "report.json")
    return {
        "condition": condition,
        "outcome": next(r for r in report["summary"] if r["condition"] == condition),
        "parent": next(
            r
            for r in report["summary"]
            if r["condition"] == ("connected_zha" if dataset == "task-support-v2" else "parent")
        ),
        "graph_control": next(
            r
            for r in report["summary"]
            if r["condition"]
            == ("repaired_graph" if dataset == "task-support-v2" else "connected_graph")
        ),
        "scope": "fresh 24-case comparison; ordinary graph and exact recovery are equally informed controls; no ZHA-specific success advantage",
    }
