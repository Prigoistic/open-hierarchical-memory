"""Reproducible fitted-reference / persistent-workspace integration comparison.

Uses real official MiniGrid observations. The authored delayed-clue diagnostic
is reported separately and never used to fit/select references.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import platform
import subprocess
import time
import traceback
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import torch

from open_hierarchical_memory import ExecutionMode, HierarchicalIndex
from research.minigrid_benchmark import (
    Fact,
    ObservationPlanner,
    ReadContext,
    query_vectors,
    serial_observation,
)
from research.persistent_task_memory import Backend, PersistentTaskReader, RecoveryPolicy
from research.run_minigrid_benchmark import environment, require_versions
from research.run_progress_benchmark import run_episode
from research.task_references import (
    GEOMETRY,
    RouterCheckpoint,
    TaskSample,
    digest,
    fit_task_references,
    sample_loss,
)
from research.task_store import TaskStore, WorkspaceConfig

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = json.loads((ROOT / "research/persistent_task_protocol.json").read_text())


def world_id(env: str, seed: int) -> str:
    return f"{env}/seed={seed}"


def collect(env: str, seed: int, step_cap: int) -> tuple[dict[str, Any], list[TaskSample]]:
    episode = run_episode(env, "graph", seed, split="diagnostic", step_cap=step_cap)
    if episode["result"]["error"]:
        raise RuntimeError(episode["result"]["error"])
    rows = episode["trajectory"]
    steps = sorted(
        {
            int((len(rows) - 1) * i / (PROTOCOL["samples_per_episode"] - 1))
            for i in range(PROTOCOL["samples_per_episode"])
        }
    )
    heads: dict[tuple[int, int], Fact] = {}
    samples = []
    for row in rows:
        for raw in row["new_facts"]:
            f = Fact(**raw)
            heads[f.position] = f
        if row["step"] in steps:
            samples.append(
                TaskSample.observed(
                    world_id(env, seed),
                    row["step"],
                    sorted(heads.values(), key=lambda f: f.id),
                    torch.tensor(row["decision"]["queries"], dtype=torch.float64),
                )
            )
    return episode, samples


def save_json(path: Path, value: Any) -> None:
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def save_trace(path: Path, value: Any) -> dict[str, Any]:
    raw = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    if len(raw) > 128 * 1024 * 1024:
        raise ValueError("experiment trace exceeds128MiB")
    data = gzip.compress(raw, mtime=0)
    with path.open("xb") as stream:
        stream.write(data)
    return {
        "file": path.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "expanded_bytes": len(raw),
    }


def quality(samples: list[TaskSample], checkpoint: RouterCheckpoint) -> list[dict[str, Any]]:
    rows = []
    for s in samples:
        checkpoint.require_evaluation_context(s.context)
        refs = checkpoint.tensor()
        index = HierarchicalIndex(s.keys[None, None], s.keys[None, None], refs, config=GEOMETRY)
        result = index.attend(
            s.queries[None, None],
            visible_counts=torch.full((1, len(s.queries)), len(s.keys), dtype=torch.int64),
            mode=ExecutionMode.PAPER_APPROXIMATE,
            p=PROTOCOL["threshold"],
            collect_trace=True,
        )
        dense = torch.softmax(s.queries @ s.keys.T / (30**0.5), dim=-1)
        for route in result.routes:
            weights = dense[route.query_index]
            ids = list(route.selected_ids)
            oracle = torch.argsort(weights, descending=True, stable=True)[: len(ids)]
            rows.append(
                {
                    "context": s.context,
                    "step": s.step,
                    "query": route.query_index,
                    "reference_hash": checkpoint.sha256,
                    "selected_ids": ids,
                    "visible_keys": len(s.keys),
                    "retained_mass": float(weights[ids].sum()),
                    "same_k_oracle_mass": float(weights[oracle].sum()),
                    "summary_nodes": route.scored_nodes,
                    "pooled_kl": float(sample_loss(s, refs)),
                }
            )
    return rows


def persistent_episode(
    path: Path,
    env_id: str,
    seed: int,
    checkpoint: RouterCheckpoint,
    backend: Backend,
    step_cap: int,
    *,
    recovery_policy: RecoveryPolicy = "on_stall",
    workspace: WorkspaceConfig | None = None,
    on_step: Callable[[dict[str, Any]], None] | None = None,
    reader_factory: Callable[[TaskStore, str], PersistentTaskReader] | None = None,
) -> dict[str, Any]:
    if workspace is not None and not isinstance(workspace, WorkspaceConfig):
        raise ValueError("workspace must be a validated WorkspaceConfig")
    if path.exists():
        raise ValueError("a simulator reset requires a fresh episode archive/context")
    # An explicit reset epoch prevents stale post-interaction facts crossing a reset.
    checkpoint.require_evaluation_context(world_id(env_id, seed))
    namespace = world_id(env_id, seed) + "/reset=0/frame=episode-origin"
    config = workspace if workspace is not None else WorkspaceConfig(**PROTOCOL["workspace"])
    store = TaskStore(path, config=config, router=checkpoint)
    reader = (
        reader_factory(store, namespace)
        if reader_factory is not None
        else PersistentTaskReader(
            store,
            namespace,
            backend=backend,
            threshold=PROTOCOL["threshold"],
            recovery_policy=recovery_policy,
        )
    )
    actor = ObservationPlanner("none", injected_reader=reader)
    env = None
    rows = []
    reward_sum = 0.0
    error = None
    terminated = truncated = False
    started = time.perf_counter()
    try:
        env = environment(env_id)
        obs, _ = env.reset(seed=seed)
        for step in range(step_cap):
            retired = (
                reader.fade(PROTOCOL["ageing"]["additional_ticks"])
                if step and step % PROTOCOL["ageing"]["every_actions"] == 0
                else []
            )
            before = serial_observation(obs)
            action, decision, added = actor.act(obs)
            obs, reward, terminated, truncated, _ = env.step(action)
            reward_sum += float(reward)
            rows.append(
                {
                    "step": step,
                    "observation": before,
                    "action": action,
                    "reward": float(reward),
                    "terminated": bool(terminated),
                    "truncated": bool(truncated),
                    "retired_ids": retired,
                    "new_facts": [asdict(f) for f in added],
                    "decision": decision,
                }
            )
            if on_step is not None:
                on_step(rows[-1])
            if terminated or truncated:
                break
    except Exception as caught:
        error = {
            "type": type(caught).__name__,
            "message": str(caught),
            "traceback": traceback.format_exc(),
        }
    finally:
        if env is not None:
            env.close()
        originals = reader.archive()
        state = store.state(namespace)
        active = [f.id for f in store.heads(namespace, active=True, tag="export_payload_rows")]
        reader._sync_costs()
        costs = reader.costs.copy()
        store.close()
    # Restart verifies the stored observation/current-head/controller state, not simulator state.
    reopened = TaskStore(path, config=config, router=checkpoint)
    restart_state = reopened.state(namespace)
    reopened.close()
    return {
        "environment_id": env_id,
        "seed": seed,
        "workspace": asdict(config),
        "context": namespace,
        "backend": backend,
        "recovery_policy": recovery_policy,
        "reference_kind": checkpoint.kind,
        "reference_hash": checkpoint.sha256,
        "trajectory": rows,
        "archive": originals,
        "active_ids": active,
        "controller_state": state,
        "restart_state_equal": restart_state == state,
        "result": {
            "success": reward_sum > 0 and error is None,
            "steps": len(rows),
            "return": reward_sum,
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "external_cutoff": not terminated and not truncated and error is None,
            "error": error,
        },
        "costs": costs,
        "episode_seconds": time.perf_counter() - started,
        "scope": "fresh official environment; common symbolic planner; bounded available-graph support; no offline neural updates",
    }


def delayed_clue(path: Path, checkpoint: RouterCheckpoint, backend: Backend) -> dict[str, Any]:
    config = WorkspaceConfig(capacity=8, recovery_limit=4)
    namespace = "authored-delayed-clue/world0/frame0"
    store = TaskStore(path, config=config, router=checkpoint)
    reader = PersistentTaskReader(
        store, namespace, backend=backend, threshold=PROTOCOL["threshold"]
    )

    def f(x: int, y: int, kind: int = 1, step: int = 0, color: int = 0) -> Fact:
        return Fact(0, x, y, kind, color, 0, step, step)

    clue = reader.observe([f(i, 0, 5 if i == 3 else 1) for i in range(4)])[-1]
    reader.observe([f(10 + i, 10, step=1) for i in range(8)])
    retired = reader.fade(128)
    raw = [f(i, 0, step=2) for i in range(3)]
    reader.observe(raw)
    before = reader.archive()
    before_state = store.state(namespace)
    store.close()
    store = TaskStore(path, config=config, router=checkpoint)
    reader = PersistentTaskReader(
        store, namespace, backend=backend, threshold=PROTOCOL["threshold"]
    )
    restored_state_equal = store.state(namespace) == before_state
    c = ReadContext((0, 0), 0, "pick up the red key", None, tuple(raw), 2)
    selected, routes, receipt, _ = reader.select_with_context(query_vectors((0, 0), c.mission), c)
    changed = [f(i, 0, 5 if i == 3 else 1, step=3, color=1 if i == 3 else 0) for i in range(4)]
    reader.observe(changed)
    c2 = ReadContext((0, 0), 0, c.mission, None, tuple(changed), 3)
    selected2, routes2, receipt2, _ = reader.select_with_context(
        query_vectors((0, 0), c2.mission), c2
    )
    after = reader.archive()
    store.close()
    return {
        "scope": "authored source-recovery diagnostic, not official-task success or training data",
        "backend": backend,
        "reference_hash": checkpoint.sha256,
        "clue_id": clue.id,
        "retired_ids": retired,
        "restored_state_equal": restored_state_equal,
        "clue_recovered": clue.id in receipt["recovered_ids"],
        "clue_returned_with_support": clue.id in [f.id for f in selected],
        "receipt": receipt,
        "routes": routes,
        "correction_receipt": receipt2,
        "correction_routes": routes2,
        "superseded_not_returned": clue.id not in [f.id for f in selected2],
        "original_prefix_unchanged": after[: len(before)] == before,
        "original_count": len(after),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(
            "A fresh output directory is required; prior evidence is never overwritten."
        )
    require_versions()
    torch.set_num_threads(1)
    out = args.output
    out.mkdir(parents=True)
    (out / "archives").mkdir()
    (out / "source-snapshot").mkdir()
    sources = [
        *sorted((ROOT / "src/open_hierarchical_memory").glob("*.py")),
        *[
            ROOT / "research" / name
            for name in (
                "task_references.py",
                "task_store.py",
                "persistent_task_memory.py",
                "run_persistent_tasks.py",
                "persistent_task_protocol.json",
                "dependency_memory.py",
                "minigrid_benchmark.py",
                "run_progress_benchmark.py",
                "run_minigrid_benchmark.py",
            )
        ],
        ROOT / "uv.lock",
        ROOT / "scripts/audit_persistent_tasks.py",
        ROOT / "tests/oracle.py",
    ]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    for p in sources:
        target = out / "source-snapshot" / p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes())
    save_json(out / "protocol.json", PROTOCOL)
    save_json(
        out / "manifest.json",
        {
            "protocol_hash": digest(PROTOCOL),
            "sources": hashes,
            "python": platform.python_version(),
            "platform": platform.platform(),
            "git_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "git_status": subprocess.check_output(
                ["git", "status", "--short"], cwd=ROOT, text=True
            ),
            "versions": require_versions(),
            "scope": PROTOCOL["scope"],
        },
    )
    training: list[TaskSample] = []
    validation: list[TaskSample] = []
    heldout: list[TaskSample] = []
    collections = []
    for split, seeds, target in (
        ("training", PROTOCOL["training_seeds"], training),
        ("validation", PROTOCOL["validation_seeds"], validation),
        ("comparison", PROTOCOL["comparison_seeds"], heldout),
    ):
        for env in PROTOCOL["environments"]:
            for seed in seeds:
                episode, samples = collect(env, seed, PROTOCOL["step_cap"])
                target.extend(samples)
                artifact = save_trace(out / f"collected-{split}-{env}-{seed}.json.gz", episode)
                collections.append(
                    {
                        "split": split,
                        "environment": env,
                        "seed": seed,
                        "samples": len(samples),
                        "result": episode["result"],
                        **artifact,
                    }
                )
                print("Collected", split, env, seed, len(samples), flush=True)
    # Numerical duplicate filtering is fixed by protocol and uses no outcome labels.
    seen: set[str] = set()
    duplicate_counts: dict[str, int] = {}
    for name, samples in (
        ("training", training),
        ("validation", validation),
        ("comparison", heldout),
    ):
        kept = []
        for sample in samples:
            fingerprint = digest([sample.queries.tolist(), sample.keys.tolist()])
            if fingerprint not in seen:
                seen.add(fingerprint)
                kept.append(sample)
        duplicate_counts[name] = len(samples) - len(kept)
        samples[:] = kept
    # Evaluation tensors are never passed to the fitter.
    fitted, history = fit_task_references(
        training,
        validation,
        steps=PROTOCOL["fitting_steps"],
        seed=PROTOCOL["fitting_seed"],
        learning_rate=PROTOCOL["fitting_learning_rate"],
    )
    fixed = RouterCheckpoint.fixed()
    pool = torch.cat([s.queries for s in training])
    generator = torch.Generator().manual_seed(PROTOCOL["fitting_seed"])
    random_values = pool.mean(0) + torch.randn(
        8, 30, generator=generator, dtype=torch.float64
    ) * pool.std(0)
    random_checkpoint = RouterCheckpoint(
        tuple(tuple(float(x) for x in row) for row in random_values.tolist()),
        "random",
        tuple(sorted({s.context for s in training})),
    )
    for name, checkpoint in (("fixed", fixed), ("random", random_checkpoint), ("fitted", fitted)):
        checkpoint.save(out / f"{name}-references.json")
    save_json(
        out / "fitting.json",
        {
            "history": history,
            "duplicate_numerical_samples_removed": duplicate_counts,
            "training_samples": len(training),
            "validation_samples": len(validation),
            "comparison_samples": len(heldout),
            "selected_step": fitted.selected_step,
            "reference_hash": fitted.sha256,
            "collections": collections,
        },
    )
    corpus_artifact = save_trace(
        out / "observed-prefix-corpus.json.gz",
        [
            {
                "context": s.context,
                "step": s.step,
                "queries": s.queries.tolist(),
                "keys": s.keys.tolist(),
                "split": split,
            }
            for split, items in (
                ("training", training),
                ("validation", validation),
                ("comparison", heldout),
            )
            for s in items
        ],
    )
    metrics = {
        name: quality(heldout, checkpoint)
        for name, checkpoint in (
            ("fixed", fixed),
            ("random", random_checkpoint),
            ("fitted", fitted),
        )
    }
    save_json(
        out / "routing-quality.json",
        {
            "scope": "offline full-prefix dense teacher audit; not free online work",
            "conditions": metrics,
        },
    )
    conditions: list[tuple[str, RouterCheckpoint, Backend]] = [
        ("no_recovery", fixed, "none"),
        ("always_fixed_zha", fixed, "zha"),
        ("fixed_zha", fixed, "zha"),
        ("random_zha", random_checkpoint, "zha"),
        ("fitted_zha", fitted, "zha"),
        ("exact", fixed, "exact"),
    ]
    runs = []
    diagnostic = []
    for name, checkpoint, backend in conditions:
        for env in PROTOCOL["environments"]:
            for seed in PROTOCOL["comparison_seeds"]:
                stem = f"{name}-{env}-{seed}"
                result = persistent_episode(
                    out / "archives" / f"{stem}.sqlite",
                    env,
                    seed,
                    checkpoint,
                    backend,
                    PROTOCOL["step_cap"],
                    recovery_policy="always" if name == "always_fixed_zha" else "on_stall",
                )
                artifact = save_trace(out / f"{stem}.json.gz", result)
                runs.append(
                    {
                        "condition": name,
                        "environment": env,
                        "seed": seed,
                        **result["result"],
                        "restart_state_equal": result["restart_state_equal"],
                        "recovery_policy": result["recovery_policy"],
                        "costs": result["costs"],
                        **artifact,
                    }
                )
                save_json(out / f"run-{stem}.json", runs[-1])
                print(name, env, seed, result["result"], flush=True)
        d = delayed_clue(out / "archives" / f"delayed-{name}.sqlite", checkpoint, backend)
        artifact = save_trace(out / f"delayed-{name}.json.gz", d)
        diagnostic.append(
            {
                "condition": name,
                **{
                    k: d[k]
                    for k in (
                        "clue_recovered",
                        "clue_returned_with_support",
                        "superseded_not_returned",
                        "original_prefix_unchanged",
                        "restored_state_equal",
                    )
                },
                **artifact,
            }
        )
    for path, checksum in hashes.items():
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != checksum:
            raise RuntimeError("Source changed during experiment")
    summary = [
        {
            "condition": name,
            "successes": sum(r["success"] for r in runs if r["condition"] == name),
            "episodes": sum(r["condition"] == name for r in runs),
            "errors": sum(r["error"] is not None for r in runs if r["condition"] == name),
            "actions": sum(r["steps"] for r in runs if r["condition"] == name),
        }
        for name, _, _ in conditions
    ]
    save_json(
        out / "report.json",
        {
            "protocol_hash": digest(PROTOCOL),
            "complete": True,
            "corpus_artifact": corpus_artifact,
            "summary": summary,
            "runs": runs,
            "delayed_clue": diagnostic,
            "source_hashes_unchanged": True,
            "claim_boundary": "developmental integration; all failures retained; no sleep, cross-layout transfer, speedup or hierarchy-superiority claim",
        },
    )
    print(json.dumps({"summary": summary, "delayed_clue": diagnostic}, indent=2), flush=True)


if __name__ == "__main__":
    main()
