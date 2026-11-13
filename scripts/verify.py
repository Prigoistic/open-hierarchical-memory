"""One command for the supported local/CI checks; stop on the first failure."""

import argparse
import importlib.metadata
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("full", "core"),
        default="full",
        help="full includes clean package installations; core runs everyday numerical/code checks",
    )
    arguments = parser.parse_args()
    commands = [
        [sys.executable, "-m", "pytest", "-q"],
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        [sys.executable, "-m", "mypy"],
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "research/memory_lifecycle.py",
            "research/lifecycle_fixture.py",
            "research/run_memory_lifecycle.py",
            "research/memory_console.py",
        ],
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "research/somna_spatial.py",
            "research/run_somna_spatial.py",
            "scripts/audit_somna_spatial.py",
        ],
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "research/somna_world.py",
            "research/somna_engine.py",
            "research/serve_somna.py",
            "research/run_somna_continuous.py",
            "research/run_somna_direct_control.py",
            "scripts/audit_somna_continuous.py",
        ],
        [
            sys.executable,
            "scripts/audit_somna_continuous.py",
            "--results",
            "experiments/somna-continuous-v4",
        ],
        [
            sys.executable,
            "scripts/audit_somna_continuous.py",
            "--results",
            "experiments/somna-direct-control-v1",
        ],
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--explicit-package-bases",
            "research/boxoban_benchmark.py",
            "research/run_boxoban_benchmark.py",
            "research/minigrid_benchmark.py",
            "research/run_minigrid_benchmark.py",
            "research/serve_task_benchmark.py",
            "research/dependency_memory.py",
            "research/run_dependency_benchmark.py",
            "research/progress_retrieval.py",
            "research/run_progress_benchmark.py",
            "research/diagnose_dependency_failures.py",
            "scripts/audit_complex_tasks.py",
            "scripts/audit_dependency_memory.py",
            "scripts/audit_progress_retrieval.py",
        ],
        [
            sys.executable,
            "scripts/audit_complex_tasks.py",
            "--results",
            "experiments/boxoban-search-v1",
        ],
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--follow-imports=silent",
            "research/task_references.py",
            "research/task_store.py",
            "research/persistent_task_memory.py",
            "research/run_persistent_tasks.py",
            "research/persistent_dashboard.py",
            "research/live_solver.py",
            "scripts/audit_persistent_tasks.py",
        ],
        [
            sys.executable,
            "scripts/audit_persistent_tasks.py",
            "--results",
            "experiments/persistent-task-v1",
        ],
        [
            sys.executable,
            "scripts/audit_persistent_tasks.py",
            "--results",
            "experiments/persistent-task-v2",
        ],
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--follow-imports=silent",
            "research/task_replay.py",
            "research/run_task_replay.py",
            "scripts/audit_task_replay.py",
            "research/replay_dashboard.py",
        ],
        [
            sys.executable,
            "-m",
            "scripts.audit_task_replay",
            "--results",
            "experiments/task-replay-v1",
        ],
        [sys.executable, "scripts/check_lifecycle_mutations.py"],
        [sys.executable, "scripts/check_mutations.py"],
        [sys.executable, "examples/synthetic.py"],
    ]
    benchmark_extra = importlib.util.find_spec("minigrid") is not None
    if benchmark_extra:
        commands.append(
            [
                sys.executable,
                "scripts/audit_complex_tasks.py",
                "--minigrid",
                "experiments/minigrid-evaluation-v2",
            ]
        )
        commands.append(
            [
                sys.executable,
                "scripts/audit_dependency_memory.py",
                "--results",
                "experiments/dependency-evaluation-v1",
            ]
        )
        commands.append(
            [
                sys.executable,
                "scripts/audit_progress_retrieval.py",
                "--results",
                "experiments/progress-evaluation-v2",
            ]
        )
    node_runtime = shutil.which("node")
    if node_runtime:
        commands.append([node_runtime, "scripts/check_task_routing.cjs"])
    if arguments.profile == "full":
        commands.append([sys.executable, "scripts/check_package.py"])
    checks = []
    for command in commands:
        # Avoid embedding the machine-specific Python path in committed evidence.
        label = ("node " if command[0] == node_runtime else "python ") + " ".join(command[1:])
        print(f"\nChecking: {label}", flush=True)
        run = subprocess.run(command, cwd=ROOT, check=False)
        checks.append({"command": label, "exit_code": run.returncode})
        if run.returncode:
            break
    result = {
        "scope": "CPU float64 no-RoPE core, separate lifecycle, symbolic spatial replay and continuous learned-memory behavior and official planning-task artifacts; no full-model/GPU/industry/guarantee validation",
        "profile": arguments.profile,
        "official_minigrid_audit_enabled": benchmark_extra,
        "frontend_routing_checks_enabled": node_runtime is not None,
        "package_installations_checked": arguments.profile == "full"
        and len(checks) == len(commands)
        and checks[-1]["exit_code"] == 0,
        "hosted_ci_status": "not_assessed",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ("torch", "numpy", "pytest", "hypothesis", "ruff", "mypy")
        },
        "all_passed": len(checks) == len(commands)
        and all(check["exit_code"] == 0 for check in checks),
        "checks": checks,
    }
    filename = (
        "local-verification.json" if arguments.profile == "full" else "core-verification.json"
    )
    (ROOT / "docs/evidence" / filename).write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
