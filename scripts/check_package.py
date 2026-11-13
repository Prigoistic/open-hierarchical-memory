"""Build and install wheel and sdist into two fresh, offline environments."""

import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SMOKE = """
import json, pathlib, sys
import torch
import open_hierarchical_memory as ohm
from open_hierarchical_memory import HierarchicalIndex, TreeConfig, ExecutionMode
assert pathlib.Path(ohm.__file__).is_relative_to(sys.prefix), ohm.__file__
keys=torch.zeros((1,1,9,1),dtype=torch.float64)
values=torch.arange(9,dtype=torch.float64).reshape(1,1,9,1)
index=HierarchicalIndex(keys,values,torch.zeros((1,1,1),dtype=torch.float64),config=TreeConfig(chunk_size=2,depth=2))
result=index.attend(torch.zeros((1,1,1,1),dtype=torch.float64),visible_counts=torch.tensor([[9]]),mode=ExecutionMode.PAPER_APPROXIMATE,p=1,collect_trace=True)
assert result.routes[0].selected_ids==tuple(range(9))
assert len(result.routes[0].steps)==2
assert abs(result.output.item()-4)<1e-10
print(json.dumps({'installed_import':True,'dense_equivalent_smoke':True,'sparse_path_exercised':True}))
"""


def run(
    arguments: list[str], *, capture: bool = False, environment: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments, cwd=ROOT, check=True, text=True, capture_output=capture, env=environment
    )


def main() -> int:
    records = []
    with tempfile.TemporaryDirectory(prefix="ohm-package-") as directory:
        work = Path(directory)
        run(["uv", "build", "--offline", "--out-dir", str(work / "dist")])
        wheels = list((work / "dist").glob("*.whl"))
        sdists = list((work / "dist").glob("*.tar.gz"))
        if len(wheels) != 1 or len(sdists) != 1:
            raise RuntimeError("expected one wheel and one source distribution")
        with zipfile.ZipFile(wheels[0]) as archive:
            names = archive.namelist()
            assert "open_hierarchical_memory/py.typed" in names
            assert any(name.endswith("/LICENSE") for name in names)
            assert not any(
                name.startswith(("research/", "web/", "experiments/", "data/")) for name in names
            )
        with tarfile.open(sdists[0]) as archive:
            members = archive.getnames()
            assert not any(
                "/experiments/" in name
                or "/data/" in name
                or "/web/" in name
                or "/research/" in name
                for name in members
            )
            assert sum(m.size for m in archive.getmembers()) < 2 * 1024 * 1024, (
                "core source artifact unexpectedly large"
            )
        for number, distribution in enumerate([*wheels, *sdists]):
            environment = work / f"environment-{number}"
            install_environment = os.environ.copy()
            install_environment["UV_PROJECT_ENVIRONMENT"] = str(environment)
            # Use exact locked artifact identities, not a flattened requirements
            # resolver. Do not install the editable source project in this env.
            run(
                [
                    "uv",
                    "sync",
                    "--locked",
                    "--offline",
                    "--no-dev",
                    "--no-install-project",
                    "--python",
                    sys.executable,
                ],
                environment=install_environment,
            )
            python = str(environment / "bin/python")
            run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    python,
                    "--offline",
                    "--no-deps",
                    str(distribution),
                ]
            )
            completed = run([python, "-I", "-c", SMOKE], capture=True)
            record = json.loads(completed.stdout)
            record["distribution"] = distribution.name
            records.append(record)
            print(f"Installed-artifact check passed: {distribution.name}", flush=True)
    (ROOT / "docs/evidence/installations.json").write_text(
        json.dumps(
            {"records": records, "scope": "two clean offline installs on the local CPU platform"},
            indent=2,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
