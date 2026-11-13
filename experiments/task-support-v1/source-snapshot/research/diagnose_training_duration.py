"""Fixed-data training-duration diagnosis on TRAIN/VALIDATION ONLY.

No new generalization result: the validation set selects checkpoints and is
reused for diagnosis. Never load/evaluate the old or a new test activation here.
"""

import gzip
import json
import platform
import subprocess
from pathlib import Path

import torch

from open_hierarchical_memory import TreeConfig

from .cost_quality import aggregate_quality, quality_records
from .fitting import TraceExample, fit_references
from .profile_execution import file_hash

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = {
    "context": 1024,
    "geometry": "c16-r2-d2",
    "chunk_size": 16,
    "depth": 2,
    "references": 2,
    "seeds": [7, 23, 101],
    "durations": [100, 300, 1000],
    "learning_rate": 0.01,
    "gradient_limit": 1.0,
    "validation_every": 10,
    "positions": [255, 511, 767, 1023],
    "thresholds": [0.73, 0.9, 0.95],
    "cpu_threads": 4,
    "scope": "Fixed-data duration diagnosis on existing training/validation data. No test evaluation, new holdout or inference-quality claim.",
}


def load_split(study, split, root=ROOT):
    if split not in ("train", "validation"):
        raise ValueError("duration diagnosis accepts training/validation only")
    from safetensors.torch import load_file

    samples = []
    for book in study["config"]["splits"][split]:
        for offset in study["config"]["window_offsets"]:
            path = root / f".cache/cost-quality-v1/trace-1024-{book}-{offset}.safetensors"
            expected = next(
                c
                for c in study["captures"]
                if c["context"] == 1024 and c["book"] == book and c["offset"] == offset
            )
            if file_hash(path) != expected["trace_sha256"]:
                raise ValueError("training/validation trace identity mismatch")
            tensors = load_file(str(path))
            samples.append(
                TraceExample(
                    f"gutenberg:{book}",
                    offset,
                    tensors["queries"],
                    tensors["keys"],
                    tensors["values"],
                )
            )
    return samples


def main():
    from safetensors.torch import load_file, save_file

    output = ROOT / "experiments/training-duration-diagnostic-v1"
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("retain existing duration diagnosis")
    protocol_source = Path(__file__)
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain", "--", "src", "research", "tests", "scripts"],
        cwd=ROOT,
        text=True,
    )
    if dirty:
        raise RuntimeError("commit experiment source before duration diagnosis")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    torch.set_num_threads(PROTOCOL["cpu_threads"])
    study_path = ROOT / "experiments/gpt2-cost-quality-v1/report.json"
    study = json.loads(study_path.read_text())
    training, validation = load_split(study, "train"), load_split(study, "validation")
    if {s.document_id for s in training} & {s.document_id for s in validation}:
        raise ValueError("overlapping development splits")
    code = {
        str(p.relative_to(ROOT)): file_hash(p)
        for p in [
            *ROOT.glob("src/**/*.py"),
            ROOT / "research/fitting.py",
            ROOT / "research/cost_quality.py",
            ROOT / "research/metrics.py",
            protocol_source,
        ]
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "protocol.json").write_text(json.dumps(PROTOCOL, indent=2) + "\n")
    geometry = TreeConfig(chunk_size=16, depth=2)
    positions = tuple(PROTOCOL["positions"])
    rows = []
    raw_records = []
    for seed in PROTOCOL["seeds"]:
        for steps in PROTOCOL["durations"]:
            fit = fit_references(
                training,
                validation,
                seed=seed,
                count=2,
                steps=steps,
                learning_rate=0.01,
                gradient_limit=1.0,
                validation_every=10,
                positions=positions,
                geometry=geometry,
            )
            if steps == 100:
                prior = (
                    ROOT
                    / f"experiments/gpt2-cost-quality-v1/references/t1024-c16-r2-d2-s{seed}.safetensors"
                )
                prior_metadata = next(
                    f
                    for f in study["fitting"]
                    if f["context"] == 1024 and f["geometry"] == "c16-r2-d2" and f["seed"] == seed
                )
                if file_hash(prior) != prior_metadata["checkpoint_sha256"]:
                    raise ValueError("original checkpoint identity mismatch")
                torch.testing.assert_close(
                    fit.references, load_file(str(prior))["trained"], atol=0, rtol=0
                )
            path = output / f"references-s{seed}-steps{steps}.safetensors"
            save_file({"trained": fit.references.contiguous()}, str(path))
            variants = {"trained": fit.references}
            if steps == 100:
                variants.update(
                    initial_query_samples=fit.initial_references,
                    random_gaussian=fit.random_references,
                )
            quality = []
            for variant, refs in variants.items():
                for p in PROTOCOL["thresholds"]:
                    records = quality_records(validation, refs, positions, geometry, p, 1e-12)
                    raw_records.extend(
                        {
                            "seed": seed,
                            "maximum_steps": steps,
                            "training_steps_applied": fit.selected_step
                            if variant == "trained"
                            else 0,
                            "variant": variant,
                            "p": p,
                            **record,
                        }
                        for record in records
                    )
                    quality.append(
                        {
                            "variant": variant,
                            "p": p,
                            "split": "validation",
                            "metrics": aggregate_quality(records),
                            "per_document": {
                                name: aggregate_quality(
                                    [r for r in records if r["document_id"] == name]
                                )
                                for name in sorted({s.document_id for s in validation})
                            },
                        }
                    )
            rows.append(
                {
                    "seed": seed,
                    "maximum_steps": steps,
                    "selected_step": fit.selected_step,
                    "history": list(fit.history),
                    "checkpoint": path.name,
                    "checkpoint_sha256": file_hash(path),
                    "quality": quality,
                }
            )
            print(
                f"Duration diagnosis seed={seed} budget={steps} selected={fit.selected_step}",
                flush=True,
            )
    if code != {name: file_hash(ROOT / name) for name in code}:
        raise RuntimeError("duration source changed during run")
    raw_path = output / "validation-queries.jsonl.gz"
    with raw_path.open("xb") as stream:
        with gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as compressed:
            for record in raw_records:
                compressed.write((json.dumps(record, allow_nan=False) + "\n").encode())
    report = {
        "protocol": PROTOCOL,
        "git_revision": revision,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "raw_validation_sha256": file_hash(raw_path),
        "source_sha256": code,
        "study_report_sha256": file_hash(study_path),
        "torch": torch.__version__,
        "cpu_threads": torch.get_num_threads(),
        "unique_training_tokens": len(training) * 1024,
        "training_documents": sorted({s.document_id for s in training}),
        "validation_documents": sorted({s.document_id for s in validation}),
        "test_evaluated": False,
        "prior_100_step_checkpoints_reproduced_exactly": True,
        "fits": rows,
        "limitations": [
            "Validation selects checkpoints and diagnoses outcomes; it is not a new test set.",
            "Only optimizer duration changes; no independent data-coverage test or whole-model inference.",
            "The p grid is coarse; identical p does not match actual key counts or vector work.",
        ],
    }
    temporary = output / "report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(output / "report.json")


if __name__ == "__main__":
    main()
