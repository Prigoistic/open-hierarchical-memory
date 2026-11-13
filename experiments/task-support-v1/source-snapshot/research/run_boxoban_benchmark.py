"""Frozen-cohort Boxoban search comparison; no test-label case construction."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import random
import shutil
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import torch

from research.boxoban_benchmark import (
    Case,
    CaseReader,
    Method,
    case_payload,
    digest,
    make_cases,
    parse_levels,
    solve,
    symmetry_key,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    "research/boxoban_benchmark.py",
    "research/run_boxoban_benchmark.py",
    "pyproject.toml",
    "uv.lock",
) + tuple(
    str(p.relative_to(ROOT)) for p in sorted((ROOT / "src/open_hierarchical_memory").glob("*.py"))
)
CONFIGS: tuple[tuple[str, Method, float], ...] = (
    ("matching", "matching", 0.8),
    ("linear", "linear", 0.8),
    ("dense", "dense", 0.8),
    ("top16", "top16", 0.8),
    ("zha-p25", "zha", 0.25),
    ("zha-p50", "zha", 0.5),
    ("random-values", "random_values", 0.8),
)


def load(path: Path) -> Any:
    return json.loads(path.read_text())


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compressed(path: Path, value: Any) -> str:
    with path.open("xb") as file, gzip.GzipFile(fileobj=file, mode="wb", mtime=0) as stream:
        stream.write(json.dumps(value, separators=(",", ":"), allow_nan=False).encode())
    return sha(path)


def data() -> dict[str, Any]:
    manifest = load(ROOT / "data/boxoban/manifest.json")
    for name, info in manifest["files"].items():
        if sha(ROOT / "data/boxoban" / name) != info["sha256"]:
            raise ValueError("Boxoban source checksum mismatch: " + name)
    return {
        split: parse_levels((ROOT / "data/boxoban" / name).read_text(), split)
        for split, name in (
            ("train", "train.txt"),
            ("validation", "validation.txt"),
            ("test", "test.txt"),
            ("hard", "hard.txt"),
        )
    }


def prepare(output: Path) -> None:
    if output.exists():
        raise ValueError("choose a fresh output directory")
    levels = data()
    output.mkdir(parents=True)
    protocol: dict[str, Any] = {
        "schema": "boxoban-protocol-v1",
        "task": "Official four-box Boxoban, fully observed push planning",
        "train_ids": list(range(32)),
        "test_ids": list(range(16)),
        "hard_ids": list(range(16)),
        "case_samples_per_path": 12,
        "teacher": {"expansion_limit": 20000, "wall_seconds": 5.0, "weight": 1.0},
        "expansion_limits": [256, 1024],
        "wall_seconds": 20.0,
        "weight": 1.5,
        "configs": [list(c) for c in CONFIGS],
        "order_seed": 90211,
        "selection": "Both ZHA thresholds fixed before held-out execution. No validation selection. Keep every failure.",
        "scope": "Case-guided classical search diagnostic, not a learned RL/LLM policy or industry deployment validation.",
    }
    write(output / "protocol.json", protocol)
    for source in SOURCES:
        dest = output / "source-snapshot" / source
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / source, dest)
    manifest: dict[str, Any] = {
        "schema": "boxoban-run-v2",
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_hashes": {s: sha(ROOT / s) for s in SOURCES},
        "data_manifest": load(ROOT / "data/boxoban/manifest.json"),
        "protocol_sha256": sha(output / "protocol.json"),
        "python": sys.version,
        "platform": platform.platform(),
        "torch": torch.__version__,
        "numpy": np.__version__,
        "torch_threads": torch.get_num_threads(),
    }
    write(output / "manifest.json", manifest)
    cases: list[Case] = []
    training = []
    for level in levels["train"][:32]:
        result = solve(level, **protocol["teacher"])
        compressed(output / f"train-{level.identifier}.json.gz", result)
        if result["success"]:
            cases.extend(make_cases(level, result, limit=12))
        training.append(
            {
                k: result[k]
                for k in (
                    "level_id",
                    "level_hash",
                    "success",
                    "status",
                    "pushes",
                    "expanded",
                    "wall_seconds",
                )
            }
        )
        print("train", level.identifier, result["status"], result["expanded"], flush=True)
    if not cases:
        raise ValueError("no solved training cases")
    write(output / "training.json", training)
    write(output / "cases.json", case_payload(tuple(cases)))
    blocked = {symmetry_key(level) for level in levels["train"][:32]}
    cohorts: dict[str, list[int]] = {}
    excluded = []
    for split in ("test", "hard"):
        ids = []
        for level in levels[split][:16]:
            identity = symmetry_key(level)
            if identity in blocked:
                excluded.append(
                    {
                        "split": split,
                        "id": level.identifier,
                        "reason": "symmetry/equivalent-player-region duplicate",
                    }
                )
            else:
                ids.append(level.identifier)
                blocked.add(identity)
        cohorts[split] = ids
    write(output / "cohorts.json", {"cohorts": cohorts, "excluded": excluded})
    manifest.update(
        cases_sha256=sha(output / "cases.json"), cohorts_sha256=sha(output / "cohorts.json")
    )
    write(output / "manifest.json", manifest)
    print("frozen", len(cases), "cases; cohorts", cohorts, flush=True)


def verify_frozen(output: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = load(output / "manifest.json")
    for source, expected in manifest["source_hashes"].items():
        if sha(ROOT / source) != expected:
            raise ValueError("source changed after freeze: " + source)
    for name, field in (
        ("protocol.json", "protocol_sha256"),
        ("cases.json", "cases_sha256"),
        ("cohorts.json", "cohorts_sha256"),
    ):
        if sha(output / name) != manifest[field]:
            raise ValueError("frozen input changed: " + name)
    if load(ROOT / "data/boxoban/manifest.json") != manifest["data_manifest"]:
        raise ValueError("data manifest changed after freeze")
    return manifest


def evaluate(output: Path) -> None:
    manifest = verify_frozen(output)
    dest = output / "evaluation"
    dest.mkdir()
    protocol = load(output / "protocol.json")
    bank = load(output / "cases.json")
    if digest(bank["cases"]) != bank["hash"]:
        raise ValueError("case hash mismatch")
    cases = tuple(
        Case(**{**r, "boxes": tuple(r["boxes"]), "feature": tuple(r["feature"])})
        for r in bank["cases"]
    )
    levels = data()
    cohorts = load(output / "cohorts.json")["cohorts"]
    report = []
    rng = random.Random(protocol["order_seed"])
    for split in ("test", "hard"):
        for identifier in cohorts[split]:
            level = next(level for level in levels[split] if level.identifier == identifier)
            for cap in protocol["expansion_limits"]:
                configs = list(CONFIGS)
                rng.shuffle(configs)
                for config, method, p in configs:
                    reader = None if method == "matching" else CaseReader(cases, method, p=p)
                    result = solve(
                        level,
                        reader,
                        expansion_limit=cap,
                        wall_seconds=protocol["wall_seconds"],
                        weight=protocol["weight"],
                    )
                    result.update(config=config, p=p, case_hash=bank["hash"])
                    result["cold_total_seconds"] = result["wall_seconds"] + (
                        0.0 if reader is None else reader.index_build_seconds
                    )
                    name = f"{split}-{identifier}-cap{cap}-{config}.json.gz"
                    checksum = compressed(dest / name, result)
                    row = {
                        k: result[k]
                        for k in (
                            "split",
                            "level_id",
                            "level_hash",
                            "config",
                            "p",
                            "case_hash",
                            "status",
                            "success",
                            "pushes",
                            "expanded",
                            "generated",
                            "wall_seconds",
                            "cold_total_seconds",
                            "read_work",
                            "expansion_limit",
                            "weight",
                        )
                    }
                    row.update(file=name, sha256=checksum)
                    report.append(row)
                    # Keep completed rows if a later process fails; never mark a partial run complete.
                    write(dest / "partial.json", {"complete": False, "runs": report})
                    print(
                        split,
                        identifier,
                        cap,
                        config,
                        result["status"],
                        result["expanded"],
                        round(result["wall_seconds"], 3),
                        flush=True,
                    )
    summary = []
    for split in ("test", "hard"):
        for cap in protocol["expansion_limits"]:
            for config, _, _ in CONFIGS:
                rows = [
                    r
                    for r in report
                    if r["split"] == split and r["expansion_limit"] == cap and r["config"] == config
                ]
                if rows:
                    summary.append(
                        {
                            "split": split,
                            "expansion_limit": cap,
                            "config": config,
                            "n": len(rows),
                            "solved": sum(r["success"] for r in rows),
                            "statuses": dict(Counter(r["status"] for r in rows)),
                            "median_search_seconds": statistics.median(
                                r["wall_seconds"] for r in rows
                            ),
                            "median_cold_seconds": statistics.median(
                                r["cold_total_seconds"] for r in rows
                            ),
                            "total_expanded": sum(r["expanded"] for r in rows),
                            "raw_key_scores": sum(
                                r["read_work"].get("raw_key_scores", 0) for r in rows
                            ),
                            "summary_dot_products": sum(
                                r["read_work"].get("summary_dot_products", 0) for r in rows
                            ),
                        }
                    )
    write(
        dest / "report.json",
        {
            "schema": "boxoban-comparison-v1",
            "complete": True,
            "protocol_hash": manifest["protocol_sha256"],
            "case_hash": bank["hash"],
            "runs": report,
            "summary": summary,
        },
    )
    print(json.dumps(summary, indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("prepare", "evaluate"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    if args.phase == "prepare":
        prepare(args.output)
    else:
        evaluate(args.output)


if __name__ == "__main__":
    main()
