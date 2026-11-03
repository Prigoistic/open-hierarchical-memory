"""One command for the supported local/CI checks; stop on the first failure."""

import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    commands = [
        [sys.executable, "-m", "pytest", "-q"],
        [sys.executable, "-m", "ruff", "check", "."],
        [sys.executable, "-m", "ruff", "format", "--check", "."],
        [sys.executable, "-m", "mypy"],
        [sys.executable, "scripts/check_mutations.py"],
        [sys.executable, "examples/synthetic.py"],
        [sys.executable, "scripts/check_package.py"],
    ]
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
        "scope": "CPU float64 no-RoPE core only; no model/GPU/guarantee validation",
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
    (ROOT / "docs/evidence/local-verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
