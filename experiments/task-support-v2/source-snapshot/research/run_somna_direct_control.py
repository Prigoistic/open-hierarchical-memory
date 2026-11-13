"""Strong ordinary observed-replay control for the preserved v4 cohort.

No hierarchy is used. This additional diagnostic does not create fresh test data.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import random
from pathlib import Path
from typing import Any

import torch
from torch import nn

from research.somna_engine import Dynamics, sha
from research.somna_world import model_inputs, model_targets

ROOT = Path(__file__).resolve().parents[1]


def ordinary_replay(
    rows: list[dict[str, Any]], initial: dict[str, Any], *, steps: int, seed: int
) -> tuple[nn.ModuleList, list[dict[str, Any]]]:
    if not rows or type(steps) is not int or not 1 <= steps <= 320:
        raise ValueError("invalid observed replay budget")
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(seed)
        models = nn.ModuleList([Dynamics().double() for _ in range(3)])
    models.load_state_dict(
        {name: torch.tensor(value, dtype=torch.float64) for name, value in initial.items()},
        strict=True,
    )
    rng = random.Random(seed + 201)
    trace = []
    for step in range(steps):
        batch = rng.sample(rows, min(16, len(rows)))
        inputs, targets = model_inputs(batch), model_targets(batch)
        losses = []
        for model in models:
            model.zero_grad(set_to_none=True)
            objective = (model(inputs) - targets).square().mean()
            objective.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0, error_if_nonfinite=True)
            with torch.no_grad():
                for parameter in model.parameters():
                    assert parameter.grad is not None
                    parameter.add_(parameter.grad, alpha=-0.06)
            losses.append(float(objective.detach()))
        trace.append(
            {
                "step": step + 1,
                "sources": [row["id"] for row in batch],
                "loss": sum(losses) / 3,
                "evidence": "observed",
                "reader": "ordinary_direct_observed",
            }
        )
    return models, trace


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("refusing existing control destination")
    args.output.mkdir(parents=True)
    torch.set_num_threads(1)
    files = [
        "research/run_somna_direct_control.py",
        "research/somna_engine.py",
        "research/somna_world.py",
        "scripts/audit_somna_continuous.py",
    ]
    hashes = {}
    for name in files:
        raw = (ROOT / name).read_bytes()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        target = args.output / "source-snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    summaries = []
    for seed in (7, 23):
        source = args.source / f"run-{seed}-none-zha.json.gz"
        original = json.loads(gzip.decompress(source.read_bytes()))
        assert sha(original["initial_weights"]) == original["initial_model_hash"]
        models, trace = ordinary_replay(
            original["observations"], original["initial_weights"], steps=160, seed=seed
        )
        evaluations = []
        for evaluation in original["evaluations"]:
            rows = evaluation["rows"]
            with torch.no_grad():
                predicted = torch.stack([model(model_inputs(rows)) for model in models]).mean(0)
            targets = torch.tensor([row["target"] for row in rows], dtype=torch.float64)
            evaluated = [{**row, "prediction": predicted[i].tolist()} for i, row in enumerate(rows)]
            evaluations.append(
                {
                    "context": evaluation["context"],
                    "mse": float((predicted - targets).square().mean()),
                    "rows": evaluated,
                }
            )
        final = {name: value.detach().tolist() for name, value in models.state_dict().items()}
        run = {
            **{
                key: original[key]
                for key in (
                    "observations",
                    "archive_hash",
                    "archive_hash_after",
                    "initial_weights",
                    "initial_model_hash",
                    "simulator_calls_before",
                    "simulator_calls_after",
                )
            },
            "seed": seed,
            "strategy": "ordinary_uniform_minibatch",
            "backend": "direct_observed",
            "gradient_steps": 160,
            "trace": trace,
            "final_weights": final,
            "final_model_hash": sha(final),
            "rollout": [],
            "evaluations": evaluations,
            "work": {
                "observed_rows_read": 160 * 16,
                "training_examples": 160 * 16 * 3,
                "gradient_steps": 160,
                "raw_pairs": 0,
                "summary_dot_products": 0,
            },
            "comparison_scope": "additional ordinary replay diagnostic on the already evaluated v4 state cohort; no lifecycle or retrieval claim",
        }
        (args.output / f"run-{seed}-ordinary.json.gz").write_bytes(
            gzip.compress(json.dumps(run, allow_nan=False).encode(), mtime=0)
        )
        summaries.append(
            {
                "seed": seed,
                "common_mse": evaluations[0]["mse"],
                "rare_mse": evaluations[1]["mse"],
                "work": run["work"],
            }
        )
        print(summaries[-1], flush=True)
        hashes[str(source.resolve())] = hashlib.sha256(source.read_bytes()).hexdigest()
    # Inputs outside this source tree are bound separately, not resolved as code.
    code = {name: value for name, value in hashes.items() if not name.startswith("/")}
    inputs = {name: value for name, value in hashes.items() if name.startswith("/")}
    (args.output / "manifest.json").write_text(
        json.dumps(
            {
                "source_hashes": code,
                "input_hashes": inputs,
                "scope": "ordinary supervised replay control; same observed inputs and initial weights as v4; unbounded canonical access",
            },
            indent=2,
        )
        + "\n"
    )
    (args.output / "report.json").write_text(
        json.dumps(
            {
                "rows": summaries,
                "note": "same160 gradient steps, sixteen uniformly sampled observed transitions per step, no hierarchy; actual example/read costs differ from retrieval-conditioned replay",
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
