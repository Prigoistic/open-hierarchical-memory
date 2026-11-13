"""Preregistered CPU cost-quality study; test starts after validation selection.

All numerical data, model weights and fitting settings are explicitly pinned.
No quality oracle runs inside the latency measurement. This is not a model
conversion, growing-cache decoder or GPU-kernel benchmark.
"""

import argparse
import gzip
import hashlib
import importlib.metadata
import json
import platform
import resource
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import torch
from safetensors.torch import load_file, save_file
from transformers import GPT2Model, GPT2TokenizerFast

from open_hierarchical_memory import TreeConfig

from .cost_quality import (
    aggregate_quality,
    benchmark_routes,
    choose_on_validation,
    positions_for,
    quality_records,
    save_trace,
    validate_study,
)
from .fitting import TraceExample, fit_references
from .gpt2_capture import capture_gpt2, parameter_hash
from .prepare_gpt2 import book_body
from .run_gpt2_pilot import file_hash, source_hashes

ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def gzip_jsonl(path: Path):
    # Fixed mtime and empty header name keep raw measurements reproducible.
    with path.open("xb") as stream:
        with gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=0) as compressed:

            def emit(record):
                compressed.write((json.dumps(record, allow_nan=False) + "\n").encode())

            yield emit


def committed_identity(config_bytes: bytes, manifest: dict) -> str:
    dirty = subprocess.check_output(
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
    )
    if dirty:
        raise RuntimeError("commit all experiment sources, protocol and manifest before running")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if (
        subprocess.check_output(
            ["git", "show", f"{revision}:research/cost_quality_protocol.json"], cwd=ROOT
        )
        != config_bytes
    ):
        raise RuntimeError("protocol does not match committed source")
    if (
        json.loads(
            subprocess.check_output(
                ["git", "show", f"{revision}:research/cost_quality_manifest.json"], cwd=ROOT
            )
        )
        != manifest
    ):
        raise RuntimeError("manifest does not match committed source")
    return revision


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/gpt2-cost-quality-v1")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(
            "nonempty output directory; choose a fresh output, do not replace a run"
        )
    config_bytes = (ROOT / "research/cost_quality_protocol.json").read_bytes()
    config = json.loads(config_bytes)
    manifest = json.loads((ROOT / "research/cost_quality_manifest.json").read_text())
    validate_study(config, manifest)
    revision = committed_identity(config_bytes, manifest)
    code_before = source_hashes()
    torch.set_num_threads(config["timing"]["cpu_threads"])
    started = time.perf_counter()
    output.mkdir(parents=True, exist_ok=True)
    (output / "protocol.json").write_bytes(config_bytes)
    cache = ROOT / ".cache/cost-quality-v1"
    model_path = Path((cache / "model_path.txt").read_text())
    if (
        model_path.name != config["model_revision"]
        or file_hash(model_path / "model.safetensors") != manifest["model_weights_sha256"]
    ):
        raise ValueError("model identity mismatch")
    tokenizer = GPT2TokenizerFast.from_pretrained(model_path, local_files_only=True)
    model, loading = GPT2Model.from_pretrained(
        model_path,
        local_files_only=True,
        use_safetensors=True,
        attn_implementation="eager",
        torch_dtype=torch.float32,
        output_loading_info=True,
    )
    if any(
        loading.get(name)
        for name in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")
    ):
        raise RuntimeError(f"pretrained loading was not complete: {loading}")
    if max(config["contexts"]) > model.config.n_positions:
        raise ValueError("context exceeds native pretrained position range")
    model.eval().requires_grad_(False)
    frozen_before = parameter_hash(model)
    captures = []
    token_hashes = {context: set() for context in config["contexts"]}

    def capture_split(context, split):
        samples = []
        for doc in manifest["documents"]:
            if doc["split"] != split:
                continue
            raw = (cache / f"book-{doc['book_id']}.txt").read_bytes()
            body = book_body(raw.decode("utf-8-sig"))
            if (
                hashlib.sha256(raw).hexdigest() != doc["raw_sha256"]
                or hashlib.sha256(body.encode()).hexdigest() != doc["body_sha256"]
            ):
                raise ValueError("corpus bytes/extraction changed")
            tokens = tokenizer.encode(
                body[: config["text_character_limit"]], add_special_tokens=False, verbose=False
            )
            for offset in config["window_offsets"]:
                ids = tokens[offset : offset + context]
                if len(ids) != context:
                    raise ValueError("unavailable prespecified window")
                token_tensor = torch.tensor([ids], dtype=torch.int64)
                digest = hashlib.sha256(token_tensor.numpy().tobytes()).hexdigest()
                if digest in token_hashes[context]:
                    raise ValueError("repeated token window across documents or splits")
                token_hashes[context].add(digest)
                capture = capture_gpt2(model, token_tensor, layer=config["layer"])
                sample = TraceExample(
                    f"gutenberg:{doc['book_id']}",
                    offset,
                    capture.queries,
                    capture.keys,
                    capture.values,
                )
                destination = cache / f"trace-{context}-{doc['book_id']}-{offset}.safetensors"
                if destination.exists():
                    raise FileExistsError(
                        "trace cache already exists; archive the old run before rerunning"
                    )
                save_trace(sample, destination)
                captures.append(
                    {
                        "context": context,
                        "split": split,
                        "book": doc["book_id"],
                        "offset": offset,
                        "token_ids_sha256": digest,
                        "trace_sha256": file_hash(destination),
                        "native_weight_max_abs_error": capture.native_weight_max_abs_error,
                        "native_output_max_abs_error": capture.native_output_max_abs_error,
                    }
                )
                samples.append(sample)
            print(f"Captured context={context} {split} book={doc['book_id']}", flush=True)
        return samples

    # A sealed test split is not captured/evaluated until every choice is fixed.
    fits = {}
    fitting_rows, validation_rows, selections = [], [], []
    checkpoints = output / "references"
    checkpoints.mkdir()
    with gzip_jsonl(output / "validation-queries.jsonl.gz") as emit:
        for context in config["contexts"]:
            training = capture_split(context, "train")
            validation = capture_split(context, "validation")
            positions = positions_for(config, context)
            candidates = []
            for item in config["geometries"]:
                geometry = TreeConfig(chunk_size=item["chunk_size"], depth=item["depth"])
                pooled = {p: [] for p in config["routing_thresholds"]}
                for seed in config["seeds"]:
                    fit = fit_references(
                        training,
                        validation,
                        seed=seed,
                        count=item["reference_count"],
                        steps=config["steps"],
                        learning_rate=config["learning_rate"],
                        gradient_limit=config["gradient_norm_limit"],
                        validation_every=config["validation_every_steps"],
                        positions=positions,
                        geometry=geometry,
                    )
                    path = checkpoints / f"t{context}-{item['id']}-s{seed}.safetensors"
                    save_file(
                        {
                            "trained": fit.references,
                            "initial_query_samples": fit.initial_references,
                            "random_gaussian": fit.random_references,
                        },
                        str(path),
                    )
                    restored = load_file(str(path))
                    for key, value in [
                        ("trained", fit.references),
                        ("initial_query_samples", fit.initial_references),
                        ("random_gaussian", fit.random_references),
                    ]:
                        torch.testing.assert_close(restored[key], value, atol=0, rtol=0)
                    fits[context, item["id"], seed] = path
                    fitting_rows.append(
                        {
                            "context": context,
                            "geometry": item["id"],
                            "seed": seed,
                            "selected_step": fit.selected_step,
                            "history": list(fit.history),
                            "checkpoint": str(path.relative_to(output)),
                            "checkpoint_sha256": file_hash(path),
                        }
                    )
                    for p in config["routing_thresholds"]:
                        records = quality_records(
                            validation,
                            restored["trained"],
                            positions,
                            geometry,
                            p,
                            config["selection"]["relative_l2_denominator_floor"],
                        )
                        pooled[p].extend(records)
                        for record in records:
                            emit(
                                {
                                    "context": context,
                                    "geometry": item["id"],
                                    "seed": seed,
                                    "p": p,
                                    "split": "validation",
                                    **record,
                                }
                            )
                for p, records in pooled.items():
                    row = {
                        "context": context,
                        "geometry": item["id"],
                        "p": p,
                        "split": "validation",
                        "seeds": config["seeds"],
                        "metrics": aggregate_quality(records),
                    }
                    validation_rows.append(row)
                    candidates.append(row)
                print(f"Validated context={context} geometry={item['id']}", flush=True)
            selections.append(choose_on_validation(candidates, config, context))
    selection_record = {
        "source_revision": revision,
        "selections": selections,
        "rule": config["selection"],
        "test_capture_started": False,
        "checkpoint_hashes": {row["checkpoint"]: row["checkpoint_sha256"] for row in fitting_rows},
    }
    selection_bytes = (json.dumps(selection_record, indent=2, allow_nan=False) + "\n").encode()
    selection_path = output / "selection-before-test.json"
    selection_path.write_bytes(selection_bytes)
    print(f"ALL VALIDATION CHOICES FROZEN: {selections}", flush=True)
    # No fitting, configuration selection or optimizer calls below this boundary.
    test_rows, benchmark_rows, dense_checks = [], [], []
    with gzip_jsonl(output / "test-queries.jsonl.gz") as emit:
        for context in config["contexts"]:
            test = capture_split(context, "test")
            positions = positions_for(config, context)
            for item in config["geometries"]:
                geometry = TreeConfig(chunk_size=item["chunk_size"], depth=item["depth"])
                for seed in config["seeds"]:
                    restored = load_file(str(fits[context, item["id"], seed]))
                    for variant, refs in restored.items():
                        for p in config["routing_thresholds"]:
                            records = quality_records(
                                test,
                                refs,
                                positions,
                                geometry,
                                p,
                                config["selection"]["relative_l2_denominator_floor"],
                            )
                            identifiers = {
                                "context": context,
                                "geometry": item["id"],
                                "seed": seed,
                                "variant": variant,
                                "p": p,
                                "split": "test",
                            }
                            for record in records:
                                emit({**identifiers, **record})
                            test_rows.append(
                                {
                                    **identifiers,
                                    "metrics": aggregate_quality(records),
                                    "per_document": {
                                        doc: aggregate_quality(
                                            [r for r in records if r["document_id"] == doc]
                                        )
                                        for doc in sorted({s.document_id for s in test})
                                    },
                                }
                            )
                            if variant == "trained":
                                timing = benchmark_routes(
                                    test, refs, positions, geometry, p, config["timing"]
                                )
                                benchmark_rows.append({**identifiers, **timing})
                    # Full selection checked for every geometry, one seed only;
                    # seed-independent p=1 route completeness is already tested.
                    if seed == config["seeds"][0]:
                        exact = quality_records(
                            test,
                            restored["trained"],
                            positions,
                            geometry,
                            1.0,
                            config["selection"]["relative_l2_denominator_floor"],
                        )
                        if any(r["selected_keys"] != r["visible_keys"] for r in exact):
                            raise AssertionError("p=1 omitted keys")
                        dense_checks.append(
                            {
                                "context": context,
                                "geometry": item["id"],
                                "cases": len(exact),
                                "maximum_l2": max(r["attention_l2_error"] for r in exact),
                            }
                        )
                    print(f"Tested context={context} geometry={item['id']} seed={seed}", flush=True)
    frozen_after = parameter_hash(model)
    if frozen_after != frozen_before or any(
        p.grad is not None or p.requires_grad for p in model.parameters()
    ):
        raise RuntimeError("backbone identity/gradient invariant failed")
    if source_hashes() != code_before or selection_path.read_bytes() != selection_bytes:
        raise RuntimeError("source or frozen choices changed while running")
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report = {
        "schema_version": 1,
        "scope": config["scope"],
        "config": config,
        "manifest": manifest,
        "git_revision": revision,
        "source_sha256": code_before,
        "config_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "selection_sha256": hashlib.sha256(selection_bytes).hexdigest(),
        "dependencies": {
            n: importlib.metadata.version(n)
            for n in ["torch", "transformers", "numpy", "safetensors"]
        },
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_threads": torch.get_num_threads(),
        "elapsed_seconds": time.perf_counter() - started,
        "whole_process_peak_rss_bytes": peak if platform.system() == "Darwin" else peak * 1024,
        "peak_rss_scope": "Whole capture/fitting/evaluation process high-water mark; not per-configuration inference peak memory.",
        "model_loading_info": loading,
        "teacher_dtype": "float32",
        "reference_dtype": "float64",
        "frozen_backbone_sha256_before": frozen_before,
        "frozen_backbone_sha256_after": frozen_after,
        "backbone_unchanged": True,
        "test_started_after_all_validation_selection": True,
        "captures": captures,
        "fitting": fitting_rows,
        "validation_grid": validation_rows,
        "selections": selections,
        "test_grid": test_rows,
        "benchmarks": benchmark_rows,
        "dense_equivalence": dense_checks,
        "raw_measurement_sha256": {
            name: file_hash(output / name)
            for name in ("validation-queries.jsonl.gz", "test-queries.jsonl.gz")
        },
        "limitations": [
            "One layer, GPT-2 contexts up to its native 1024 positions, short literary windows only.",
            "Four new test books; dependent heads/windows/seeds do not establish statistical significance.",
            "CPU float64 reference with Python overhead, not an optimized GPU result.",
            "Selected-key and vector-work ratios omit sorting, softmax, traffic, Python and other overhead.",
            "Static snapshot reuse is a scenario calculation, not incremental autoregressive decode.",
            "Same-key top-K oracle maximizes retained mass, not output accuracy, and uses dense offline work.",
            "Layer-relative-error thresholds are diagnostics, not perplexity or generation quality guarantees.",
            "No tested geometry is chosen or retuned on test results; all grid results are descriptive.",
        ],
    }
    temporary = output / "report.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    temporary.replace(output / "report.json")
    print(f"Completed {output / 'report.json'}", flush=True)


if __name__ == "__main__":
    main()
