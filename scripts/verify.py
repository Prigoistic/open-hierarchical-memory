"""One command for the supported local/CI checks; stop on the first failure."""

import argparse
import importlib.metadata
import json
import platform
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
        [sys.executable, "scripts/check_lifecycle_mutations.py"],
        [sys.executable, "scripts/check_mutations.py"],
        [sys.executable, "examples/synthetic.py"],
    ]
    if arguments.profile == "full":
        commands.append([sys.executable, "scripts/check_package.py"])
    checks = []
    for command in commands:
        # Avoid embedding the machine-specific Python path in committed evidence.
        label = "python " + " ".join(command[1:])
        print(f"\nChecking: {label}", flush=True)
        run = subprocess.run(command, cwd=ROOT, check=False)
        checks.append({"command": label, "exit_code": run.returncode})
        if run.returncode:
            break
    result = {
        "scope": "CPU float64 no-RoPE core, separate lifecycle and symbolic spatial replay behavior; no model/GPU/guarantee validation",
        "profile": arguments.profile,
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
