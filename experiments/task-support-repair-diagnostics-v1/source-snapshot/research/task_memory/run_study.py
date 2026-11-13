"""Frozen matched-capacity evaluation of task-useful observed support."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

import torch

from research.persistent_task_memory import Backend
from research.run_minigrid_benchmark import environment, require_versions
from research.run_persistent_tasks import persistent_episode, save_json, save_trace
from research.task_memory.support import SupportTaskReader
from research.task_references import RouterCheckpoint, digest
from research.task_store import WorkspaceConfig

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = json.loads((Path(__file__).with_name("protocol.json")).read_text())


def run(
    condition: str,
    path: Path,
    env: str,
    seed: int,
    checkpoint: RouterCheckpoint,
    *,
    cap: int = 256,
    on_step: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if condition not in PROTOCOL["conditions"]:
        raise ValueError("unsupported support condition")
    backend: Backend = (
        "exact"
        if condition == "connected_exact"
        else "none"
        if condition == "connected_graph"
        else "zha"
    )

    def factory(store: Any, context: str) -> SupportTaskReader:
        return SupportTaskReader(
            store,
            context,
            backend=backend,
            support_mode="compact" if condition == "compact" else "connected",
            cache_heads=PROTOCOL["cache_heads"],
        )

    result = persistent_episode(
        path,
        env,
        seed,
        checkpoint,
        backend,
        cap,
        workspace=WorkspaceConfig(**PROTOCOL["workspace"]),
        reader_factory=None if condition == "parent" else factory,
        on_step=on_step,
    )
    result["condition"] = condition
    return result


def layout_identity(env_id: str, seed: int) -> str:
    # Evaluator-only identity. This environment is never passed to a reader.
    env = environment(env_id)
    try:
        obs, _ = env.reset(seed=seed)
        state = env.unwrapped
        return digest(
            [
                env_id,
                state.grid.encode().tolist(),
                list(map(int, state.agent_pos)),
                int(state.agent_dir),
                obs["mission"],
            ]
        )
    finally:
        env.close()


def main(
    *, protocol: dict[str, Any] = PROTOCOL, runner: Callable[..., dict[str, Any]] = run
) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    out = args.output
    if out.exists():
        raise SystemExit("Use a new output directory; prior evidence is never overwritten")
    require_versions()
    torch.set_num_threads(1)
    out.mkdir(parents=True)
    (out / "archives").mkdir()
    files = (
        sorted((ROOT / "src/open_hierarchical_memory").glob("*.py"))
        + sorted((ROOT / "research").glob("*.py"))
        + sorted((ROOT / "research/task_memory").glob("*.py"))
        + [
            *sorted((ROOT / "research/task_memory").glob("*.json")),
            ROOT / "research/persistent_task_protocol.json",
            ROOT / "scripts/audit_task_support.py",
            ROOT / "scripts/audit_persistent_tasks.py",
            ROOT / "tests/oracle.py",
            ROOT / "docs/TASK_SUPPORT.md",
            ROOT / "uv.lock",
        ]
    )
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    for source in files:
        target = out / "source-snapshot" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
    save_json(out / "protocol.json", protocol)
    checkpoint = RouterCheckpoint.load(ROOT / protocol["checkpoint"])
    checkpoint.save(out / "references.json")
    save_json(
        out / "manifest.json",
        {
            "protocol_hash": digest(protocol),
            "sources": hashes,
            "versions": require_versions(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "git_status": subprocess.check_output(["git", "status", "--short"], text=True),
        },
    )
    identities = {
        (env, seed): layout_identity(env, seed)
        for env in protocol["environments"]
        for seed in protocol["comparison_seeds"]
    }
    rows = []
    for condition in protocol["conditions"]:
        for env in protocol["environments"]:
            for seed in protocol["comparison_seeds"]:
                stem = f"{condition}-{env}-{seed}"
                e = runner(
                    condition,
                    out / "archives" / f"{stem}.sqlite",
                    env,
                    seed,
                    checkpoint,
                    cap=protocol["step_cap"],
                )
                e["evaluator_layout_identity"] = identities[env, seed]
                artifact = save_trace(out / f"{stem}.json.gz", e)
                row = {
                    "condition": condition,
                    "environment": env,
                    "seed": seed,
                    **e["result"],
                    "costs": e["costs"],
                    "scan_stalls": sum(
                        t["decision"]["objective"] == "scan-no-reachable-frontier"
                        for t in e["trajectory"]
                    ),
                    "layout_identity": identities[env, seed],
                    **artifact,
                }
                rows.append(row)
                save_json(out / f"run-{stem}.json", row)
                print(condition, env, seed, e["result"], flush=True)
    for path, checksum in hashes.items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != checksum:
            raise RuntimeError("source changed during experiment")
    summary = []
    for c in protocol["conditions"]:
        subset = [r for r in rows if r["condition"] == c]
        work: Counter[str] = Counter()
        for r in subset:
            work.update(
                {
                    k: v
                    for k, v in r["costs"].items()
                    if not k.endswith("seconds") and "peak" not in k
                }
            )
        summary.append(
            {
                "condition": c,
                "episodes": len(subset),
                "successes": sum(r["success"] for r in subset),
                "actions": sum(r["steps"] for r in subset),
                "scan_stalls": sum(r["scan_stalls"] for r in subset),
                "errors": sum(r["error"] is not None for r in subset),
                "work": dict(work),
            }
        )
    save_json(
        out / "report.json",
        {
            "complete": True,
            "protocol_hash": digest(protocol),
            "summary": summary,
            "runs": rows,
            "unique_initial_worlds": len(set(identities.values())),
            "source_hashes_unchanged": True,
            "scope": protocol["scope"],
        },
    )
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
