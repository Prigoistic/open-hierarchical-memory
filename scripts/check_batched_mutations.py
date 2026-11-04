"""Isolated semantic faults for the research backend, separate from core tests."""

import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    (
        "wrong GQA mapping",
        "kv_heads = row_heads // (heads // info.kv_heads)",
        "kv_heads = row_heads % info.kv_heads",
        "test_batched_sparse_routes_and_outputs_match_independent_oracle",
    ),
    (
        "missing parentless chunks",
        "| set(range(parented, full))",
        "| set(range(parented, parented))",
        "test_batched_boundaries_and_uniform_score_ties[18]",
    ),
    (
        "future complete nodes influence prefix",
        "full = (visible[row] - 1) // chunk**level",
        "full = (info.key_count - 1) // chunk**level",
        "test_batched_ownership_prefix_and_independent_output_storage",
    ),
    (
        "p1 cumulative underflow",
        "if p == 1:",
        "if False:",
        "test_batched_p1_still_scores_nodes_and_retains_underflowed_keys",
    ),
    (
        "fast path attention budget ignored",
        "if key_slots > limits.max_attention_pairs:",
        "if False and key_slots > limits.max_attention_pairs:",
        "test_batched_fast_path_enforces_whole_call_default_limits[max_attention_pairs]",
    ),
    (
        "summary biases dropped",
        "+ selected_biases",
        "+ torch.zeros_like(selected_biases)",
        "test_batched_sparse_routes_and_outputs_match_independent_oracle",
    ),
]


def main():
    source = ROOT / "research/batched_execution.py"
    original = source.read_text()
    records = []
    for name, before, after, test in CASES:
        if original.count(before) != 1:
            raise RuntimeError(f"changed mutation anchor: {name}")
        changed = original.replace(before, after)
        ast.parse(changed)
        with tempfile.TemporaryDirectory(prefix="ohm-batched-mutation-") as directory:
            work = Path(directory)
            for folder in ("src", "research", "tests"):
                shutil.copytree(
                    ROOT / folder, work / folder, ignore=shutil.ignore_patterns("__pycache__")
                )
            (work / "research/batched_execution.py").write_text(changed)
            environment = {
                **os.environ,
                "PYTHONPATH": os.pathsep.join([str(work / "src"), str(work)]),
            }
            run = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", f"tests/test_batched_execution.py::{test}"],
                cwd=work,
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            output = run.stdout + run.stderr
            killed = run.returncode == 1 and "FAILED" in output and "ERROR collecting" not in output
            records.append(
                {
                    "mutation": name,
                    "detected": killed,
                    "test": test,
                    "exit_code": run.returncode,
                    "baseline_source_sha256": hashlib.sha256(original.encode()).hexdigest(),
                    "result_tail": output[-1000:],
                }
            )
            print(f"{'DETECTED' if killed else 'NOT DETECTED'}: {name}", flush=True)
    (ROOT / "docs/evidence/batched-mutations.json").write_text(
        json.dumps(
            {
                "scope": "Six targeted research-backend faults, not exhaustive proof. Core mutation evidence remains separate.",
                "all_detected": all(r["detected"] for r in records),
                "records": records,
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if all(r["detected"] for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
