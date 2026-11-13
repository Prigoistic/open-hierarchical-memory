"""Run a prespecified, frozen-GPT-2 layer experiment on a local CPU.

Only the explicit preparation command performs network downloads. This runner
loads pinned local artifacts, validates the capture, fits on training data,
selects on validation KL, then evaluates the untouched test split.
"""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import time
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file
from transformers import GPT2Model, GPT2TokenizerFast

from open_hierarchical_memory import TreeConfig

from .fitting import TraceExample, fit_references, mean_loss
from .gpt2_capture import capture_gpt2, parameter_hash
from .metrics import aggregate, evaluate_routes
from .prepare_gpt2 import book_body
from .protocol import validate_protocol

ROOT = Path(__file__).resolve().parents[1]


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_hashes() -> dict[str, str]:
    paths = [
        *ROOT.glob("src/**/*.py"),
        *ROOT.glob("research/*.py"),
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    ]
    return {str(path.relative_to(ROOT)): file_hash(path) for path in sorted(paths)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/gpt2-layer5-pilot-v1")
    args = parser.parse_args()
    output = args.output.resolve()
    if (output / "report.json").exists():
        raise FileExistsError(
            "final report exists; choose another output rather than overwrite results"
        )
    started = time.perf_counter()
    config_bytes = (ROOT / "research/gpt2_pilot.json").read_bytes()
    config = json.loads(config_bytes)
    manifest = json.loads((ROOT / "research/gpt2_data_manifest.json").read_text())
    validate_protocol(config, manifest)
    torch.set_num_threads(config["cpu_threads"])
    geometry = TreeConfig(chunk_size=config["chunk_size"], depth=config["depth"])
    positions = tuple(config["query_positions"])
    cache = ROOT / ".cache/gpt2-pilot"
    model_path = Path((cache / "model_path.txt").read_text())
    if (
        model_path.name != config["model_revision"]
        or file_hash(model_path / "model.safetensors") != manifest["model_weights_sha256"]
    ):
        raise ValueError("model revision/weights mismatch against pinned preparation manifest")
    output.mkdir(parents=True, exist_ok=True)
    protocol_path = output / "protocol.json"
    if protocol_path.exists() and protocol_path.read_bytes() != config_bytes:
        raise ValueError("partial run belongs to another protocol")
    protocol_path.write_bytes(config_bytes)
    code_before = source_hashes()
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True
    ).stdout
    source_dirty = subprocess.run(
        [
            "git",
            "status",
            "--porcelain",
            "--",
            "src",
            "research",
            "tests",
            "scripts",
            "pyproject.toml",
            "uv.lock",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    if source_dirty:
        raise RuntimeError("commit the protocol and experiment code before running the pilot")
    tokenizer = GPT2TokenizerFast.from_pretrained(model_path, local_files_only=True)
    model, loading_info = GPT2Model.from_pretrained(
        model_path,
        local_files_only=True,
        use_safetensors=True,
        attn_implementation="eager",
        torch_dtype=torch.float32,
        output_loading_info=True,
    )
    if any(loading_info.get(field) for field in ("missing_keys", "mismatched_keys", "error_msgs")):
        raise RuntimeError(f"pretrained backbone was not completely restored: {loading_info}")
    model.eval().requires_grad_(False)
    frozen_before = parameter_hash(model)
    split_samples = {name: [] for name in config["splits"]}
    capture_checks = []
    for doc in manifest["documents"]:
        raw = (cache / f"book-{doc['book_id']}.txt").read_bytes()
        if hashlib.sha256(raw).hexdigest() != doc["raw_sha256"]:
            raise ValueError("raw corpus bytes changed after pinning")
        body = book_body(raw.decode("utf-8-sig"))
        if hashlib.sha256(body.encode()).hexdigest() != doc["body_sha256"]:
            raise ValueError("corpus extraction changed after pinning")
        tokens = tokenizer.encode(
            body[: config["text_character_limit"]], add_special_tokens=False, verbose=False
        )
        for offset in config["window_offsets"]:
            ids = tokens[offset : offset + config["context_tokens"]]
            if len(ids) != config["context_tokens"]:
                raise ValueError(f"prespecified window unavailable for book {doc['book_id']}")
            capture = capture_gpt2(
                model, torch.tensor([ids], dtype=torch.int64), layer=config["layer"]
            )
            sample = TraceExample(
                f"gutenberg:{doc['book_id']}", offset, capture.queries, capture.keys, capture.values
            )
            split_samples[doc["split"]].append(sample)
            capture_checks.append(
                {
                    "document_id": sample.document_id,
                    "split": doc["split"],
                    "offset": offset,
                    "token_ids_sha256": hashlib.sha256(
                        torch.tensor(ids, dtype=torch.int64).numpy().tobytes()
                    ).hexdigest(),
                    "native_weight_max_abs_error": capture.native_weight_max_abs_error,
                    "native_output_max_abs_error": capture.native_output_max_abs_error,
                }
            )
            save_file(
                {
                    "queries": sample.queries.contiguous(),
                    "keys": sample.keys.contiguous(),
                    "values": sample.values.contiguous(),
                },
                str(cache / f"trace-{doc['book_id']}-{offset}.safetensors"),
                metadata={
                    "model_revision": config["model_revision"],
                    "layer": str(config["layer"]),
                    "split": doc["split"],
                },
            )
            print(
                f"Captured {doc['split']} book={doc['book_id']} offset={offset} max_output_error={capture.native_output_max_abs_error:.3g}",
                flush=True,
            )
    if len({record["token_ids_sha256"] for record in capture_checks}) != len(capture_checks):
        raise ValueError("duplicate token windows across the prespecified corpus")
    if parameter_hash(model) != frozen_before:
        raise RuntimeError("backbone changed during capture")
    # All seeds finish fitting/selection before test data is evaluated.
    fits = []
    for seed in config["seeds"]:
        fit = fit_references(
            split_samples["train"],
            split_samples["validation"],
            seed=seed,
            count=config["reference_count"],
            steps=config["steps"],
            learning_rate=config["learning_rate"],
            gradient_limit=config["gradient_norm_limit"],
            validation_every=config["validation_every_steps"],
            positions=positions,
            geometry=geometry,
        )
        fits.append((seed, fit))
        save_file(
            {
                "references": fit.references.contiguous(),
                "initial_references": fit.initial_references.contiguous(),
                "random_references": fit.random_references.contiguous(),
            },
            str(output / f"references-seed-{seed}.safetensors"),
            metadata={
                "model_revision": config["model_revision"],
                "layer": str(config["layer"]),
                "selected_step": str(fit.selected_step),
            },
        )
        print(f"Selected seed={seed} step={fit.selected_step} using validation only", flush=True)
    results = []
    dense_equivalence = []
    with (output / "query-metrics.jsonl").open("w") as stream:
        for seed, fit in fits:
            restored = load_file(str(output / f"references-seed-{seed}.safetensors"))
            for name, expected in [
                ("references", fit.references),
                ("initial_references", fit.initial_references),
                ("random_references", fit.random_references),
            ]:
                torch.testing.assert_close(restored[name], expected, rtol=0, atol=0)
            variants = {
                "initial_query_samples": restored["initial_references"],
                "random_gaussian": restored["random_references"],
                "trained": restored["references"],
            }
            for variant, refs in variants.items():
                test_kl = mean_loss(split_samples["test"], refs, positions, geometry)
                for p in config["routing_thresholds"]:
                    records = evaluate_routes(split_samples["test"], refs, positions, geometry, p)
                    row = {
                        "seed": seed,
                        "variant": variant,
                        "p": p,
                        "test_pooled_kl": test_kl,
                        "metrics": aggregate(records),
                        "per_document": {
                            name: aggregate(
                                [record for record in records if record["document_id"] == name]
                            )
                            for name in sorted({s.document_id for s in split_samples["test"]})
                        },
                    }
                    results.append(row)
                    for record in records:
                        stream.write(
                            json.dumps(
                                {"seed": seed, "variant": variant, "p": p, **record},
                                allow_nan=False,
                            )
                            + "\n"
                        )
                    print(
                        f"Evaluated seed={seed} {variant} p={p} retained={row['metrics']['retained_mass']['mean']:.4f} selected={row['metrics']['selected_key_fraction']['mean']:.4f}",
                        flush=True,
                    )
            exact = evaluate_routes(split_samples["test"], fit.references, positions, geometry, 1.0)
            dense_equivalence.append(
                {
                    "seed": seed,
                    "max_l2_error": max(r["attention_l2_error"] for r in exact),
                    "queries_checked": len(exact),
                }
            )
    frozen_after = parameter_hash(model)
    if frozen_after != frozen_before or any(
        p.requires_grad or p.grad is not None for p in model.parameters()
    ):
        raise RuntimeError("frozen backbone identity/gradient check failed")
    if source_hashes() != code_before:
        raise RuntimeError("experiment source changed while running; refusing final report")
    report = {
        "schema_version": 1,
        "scope": config["scope"],
        "config": config,
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "manifest": manifest,
        "git_revision": revision,
        "working_tree_dirty_at_start": bool(dirty),
        "source_tree_dirty_at_start": bool(source_dirty),
        "source_sha256": code_before,
        "dependencies": {
            name: importlib.metadata.version(name)
            for name in ["torch", "transformers", "tokenizers", "safetensors", "numpy"]
        },
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_threads": torch.get_num_threads(),
        "elapsed_seconds": time.perf_counter() - started,
        "teacher_dtype": "float32",
        "model_loading_info": loading_info,
        "checkpoint_reload_verified": True,
        "captured_dtype": "float64 (explicit conversion)",
        "position_convention": "GPT-2 learned absolute embeddings, no rotary reference re-anchoring required",
        "backbone_parameters": sum(p.numel() for p in model.parameters()),
        "trainable_parameters_per_run": fits[0][1].references.numel(),
        "frozen_backbone_sha256_before": frozen_before,
        "frozen_backbone_sha256_after": frozen_after,
        "backbone_unchanged": True,
        "capture_checks": capture_checks,
        "sample_counts": {name: len(samples) for name, samples in split_samples.items()},
        "unique_training_tokens": len(split_samples["train"]) * config["context_tokens"],
        "fitting": [
            {
                "seed": seed,
                "selected_step": fit.selected_step,
                "history": list(fit.history),
                "checkpoint_sha256": file_hash(output / f"references-seed-{seed}.safetensors"),
            }
            for seed, fit in fits
        ],
        "test_results": results,
        "dense_equivalence": dense_equivalence,
        "query_metrics_sha256": file_hash(output / "query-metrics.jsonl"),
        "limitations": [
            "One layer of one small pretrained model; no full-model conversion or generation quality evaluation.",
            "Only two held-out books; no statistical significance or broad generalization claim.",
            "Held out from router fitting, not necessarily from GPT-2 pretraining.",
            "Same routing thresholds do not imply matched sparsity; report actual selected fractions.",
            "All dense comparisons are offline work, not free runtime telemetry or certified error bounds.",
            "No GPU, kernel-speed or paper benchmark reproduction claim.",
        ],
    }
    temporary = output / "report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(output / "report.json")
    print(f"Completed {output / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
