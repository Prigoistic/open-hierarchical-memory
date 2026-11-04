"""Run isolated semantic faults against lifecycle behavior tests."""

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
CASES = (
    (
        "hot capacity ignored",
        "len(active) >= self.config.capacity",
        "False",
        "test_forgetting_preserves_originals_and_can_recover_them",
    ),
    (
        "archive scan budget ignored",
        "limit = min(rows, self.count)",
        "limit = self.count",
        "test_cyclic_scan_respects_physical_budget_and_has_no_duplicates",
    ),
    (
        "superseded rows accepted",
        "return row is not None and row[0] == record.identifier",
        "return row is not None",
        "test_corrections_append_and_superseded_archive_hits_never_return",
    ),
    (
        "replay falsely counts as actual use",
        "affinity=affinity,",
        "hits=1, affinity=affinity,",
        "test_coverage_replay_breaks_confident_wrong_hot_feedback_without_fake_usage",
    ),
    (
        "forgetting deletes original records",
        "del active[victim]",
        'self.archive.connection.execute("DROP TRIGGER immutable_delete")\n'
        '                self.archive.connection.execute("DELETE FROM heads WHERE identifier=?", (victim,))\n'
        '                self.archive.connection.execute("DELETE FROM records WHERE identifier=?", (victim,))\n'
        "                del active[victim]",
        "test_forgetting_preserves_originals_and_can_recover_them",
    ),
)


def main():
    source = ROOT / "research/memory_lifecycle.py"
    original = source.read_text()
    records = []
    for name, before, after, test in CASES:
        if original.count(before) != 1:
            raise RuntimeError(f"changed mutation anchor: {name}")
        changed = original.replace(before, after)
        ast.parse(changed)
        with tempfile.TemporaryDirectory(prefix="ohm-lifecycle-mutation-") as directory:
            work = Path(directory)
            for folder in ("src", "research", "tests"):
                shutil.copytree(
                    ROOT / folder, work / folder, ignore=shutil.ignore_patterns("__pycache__")
                )
            (work / "research/memory_lifecycle.py").write_text(changed)
            environment = {
                **os.environ,
                "PYTHONPATH": os.pathsep.join([str(work / "src"), str(work)]),
            }
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "-p",
                    "no:cacheprovider",
                    f"tests/test_memory_lifecycle.py::{test}",
                ],
                cwd=work,
                env=environment,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            output = result.stdout + result.stderr
            detected = (
                result.returncode == 1 and "FAILED" in output and "ERROR collecting" not in output
            )
            records.append(
                {
                    "mutation": name,
                    "detected": detected,
                    "test": test,
                    "exit_code": result.returncode,
                    "output_tail": output[-1200:],
                }
            )
            print(f"{name}: {'detected' if detected else 'NOT DETECTED'}", flush=True)
    report = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "all_detected": all(row["detected"] for row in records),
        "cases": records,
    }
    (ROOT / "docs/evidence/lifecycle-mutations.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    return 0 if report["all_detected"] else 1


if __name__ == "__main__":
    sys.exit(main())
