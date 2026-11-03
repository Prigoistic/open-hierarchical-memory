"""Run real regression tests against isolated, deliberately broken core copies.

Never edits the checkout under test. A syntax/import/collection failure does not
count as detecting a semantic mutation. No external mutation framework needed.
"""

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
PACKAGE = "src/open_hierarchical_memory/"
CASES = [
    (
        "lost inherited merge bias",
        "summaries.py",
        "+ (weights * biases).sum(dim=0)",
        "+ torch.zeros_like(biases[0])",
        "test_merge_preserves_bias_for_identical_zero_keys",
    ),
    (
        "incorrect GQA head mapping",
        "attention.py",
        "kv_head = h // (heads // info.kv_heads)",
        "kv_head = h % info.kv_heads",
        "test_literal_sparse_routing_discriminates_heads",
    ),
    (
        "missing parentless chunks",
        "routing.py",
        "| set(range(parented, full))",
        "| set(range(parented, parented))",
        "test_boundary_and_parentless_chunks[18]",
    ),
    (
        "future summaries influence prefix",
        "routing.py",
        "full_counts = [(visible - 1) // chunk**level for level in range(1, depth + 1)]",
        "full_counts = [len(nodes) for nodes in levels]",
        "test_prefix_queries_cannot_see_future_values_or_summaries",
    ),
    (
        "p1 rounded cumulative probability",
        "routing.py",
        "if p == 1.0:",
        "if False:",
        "test_p1_retains_all_ids_and_still_exercises_tree",
    ),
    (
        "p1 dense shortcut hides broken traversal",
        "routing.py",
        "depth = len(levels)",
        "return tuple(range(visible)), ()\n    depth = len(levels)",
        "test_p1_retains_all_ids_and_still_exercises_tree",
    ),
    (
        "caller value mutation changes snapshot",
        "tree.py",
        "self._values = values.detach().clone(memory_format=torch.contiguous_format)",
        "self._values = values.detach()",
        "test_owned_snapshot_survives_caller_and_inspection_mutation",
    ),
    (
        "caller budget silently ignored",
        "attention.py",
        "budget = budget if budget is not None else QueryBudget()",
        "budget = QueryBudget()",
        "test_resource_failure_is_not_a_successful_partial_result",
    ),
]


def main() -> int:
    records = []
    for name, filename, before, after, test in CASES:
        source = ROOT / PACKAGE / filename
        text = source.read_text()
        if text.count(before) != 1:
            raise RuntimeError(f"mutation anchor changed: {name}")
        changed = text.replace(before, after)
        ast.parse(changed)
        with tempfile.TemporaryDirectory(prefix="ohm-mutation-") as directory:
            work = Path(directory)
            shutil.copytree(ROOT / "src", work / "src")
            shutil.copytree(
                ROOT / "tests", work / "tests", ignore=shutil.ignore_patterns("__pycache__")
            )
            (work / PACKAGE / filename).write_text(changed)
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(work / "src")
            command = [sys.executable, "-m", "pytest", "-q", f"tests/test_core.py::{test}"]
            run = subprocess.run(
                command,
                cwd=work,
                env=environment,
                text=True,
                capture_output=True,
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
                    "returncode": run.returncode,
                    "baseline_source_sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "result_tail": output[-900:],
                }
            )
            print(f"{'DETECTED' if killed else 'NOT DETECTED'}: {name}", flush=True)
    result = {
        "scope": "eight targeted semantic mutations; not exhaustive mutation coverage",
        "all_detected": all(record["detected"] for record in records),
        "records": records,
    }
    destination = ROOT / "docs/evidence/mutations.json"
    destination.write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["all_detected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
