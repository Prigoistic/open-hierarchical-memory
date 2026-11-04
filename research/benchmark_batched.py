"""Parity and fresh-process timing for the explicitly experimental CPU backend.

Existing test traces are development fixtures. No references are fitted or
chosen here. All original trained geometries are parity-checked; timing uses
the previously validation-selected geometry in three declared query layouts.
"""

import argparse
import json
import platform
import resource
import subprocess
from pathlib import Path

import torch

from open_hierarchical_memory import ExecutionMode, HierarchicalIndex, TreeConfig

from .batched_execution import BatchedHierarchicalIndex
from .cost_quality import sdpa_inputs, timed_batches
from .fitting import TraceExample
from .profile_execution import file_hash

ROOT = Path(__file__).resolve().parents[1]


def load_samples(study, context):
    from safetensors.torch import load_file

    samples = []
    for book in study["config"]["splits"]["test"]:
        for offset in study["config"]["window_offsets"]:
            path = ROOT / f".cache/cost-quality-v1/trace-{context}-{book}-{offset}.safetensors"
            expected = next(
                c
                for c in study["captures"]
                if c["context"] == context and c["book"] == book and c["offset"] == offset
            )
            if file_hash(path) != expected["trace_sha256"]:
                raise ValueError("trace identity mismatch")
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


def load_references(study, context, geometry, seed):
    from safetensors.torch import load_file

    fit = next(
        f
        for f in study["fitting"]
        if f["context"] == context and f["geometry"] == geometry and f["seed"] == seed
    )
    path = ROOT / "experiments/gpt2-cost-quality-v1" / fit["checkpoint"]
    if file_hash(path) != fit["checkpoint_sha256"]:
        raise ValueError("checkpoint identity mismatch")
    return load_file(str(path))["trained"]


def compare(index, prepared, p):
    maximum = 0.0
    counters = {
        "scored_summary_slots": 0,
        "selected_key_slots": 0,
        "ordering_slots": 0,
        "attention_softmax_slots": 0,
    }
    queries = 0
    for q, _, _, visible, _ in prepared:
        expected = index._reference.attend(
            q, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=p
        )
        actual = index.attend(q, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=p)
        if actual.engine != "batched" or actual.routes != expected.routes:
            raise AssertionError("batched engine or route parity failed")
        torch.testing.assert_close(actual.output, expected.output, atol=1e-10, rtol=1e-9)
        maximum = max(maximum, float((actual.output - expected.output).abs().max()))
        if actual.scored_summary_slots != sum(
            r.scored_nodes for r in expected.routes
        ) or actual.selected_key_slots != sum(len(r.selected_ids) for r in expected.routes):
            raise AssertionError("physical scoring includes extra or missing nodes/keys")
        for key in counters:
            counters[key] += getattr(actual, key)
        queries += len(actual.routes)
    return {"maximum_output_abs_difference": maximum, "query_head_cases": queries, **counters}


@torch.no_grad()
def parity(study):
    rows = []
    for context in study["config"]["contexts"]:
        samples = load_samples(study, context)
        prepared = [
            sdpa_inputs(s, tuple(context * i // 4 - 1 for i in (1, 2, 3, 4))) for s in samples
        ]
        for geometry in study["config"]["geometries"]:
            for seed in study["config"]["seeds"]:
                refs = load_references(study, context, geometry["id"], seed)
                config = TreeConfig(chunk_size=geometry["chunk_size"], depth=geometry["depth"])
                for p in [*study["config"]["routing_thresholds"], 1.0]:
                    maximum = 0.0
                    counters = {}
                    cases = 0
                    for item in prepared:
                        _, k, v, _, _ = item
                        index = BatchedHierarchicalIndex(k, v, refs, config=config)
                        row = compare(index, [item], p)
                        maximum = max(maximum, row["maximum_output_abs_difference"])
                        cases += row["query_head_cases"]
                        for key in (
                            "scored_summary_slots",
                            "selected_key_slots",
                            "ordering_slots",
                            "attention_softmax_slots",
                        ):
                            counters[key] = counters.get(key, 0) + row[key]
                    rows.append(
                        {
                            "context": context,
                            "geometry": geometry["id"],
                            "seed": seed,
                            "p": p,
                            "maximum_output_abs_difference": maximum,
                            "query_head_cases": cases,
                            **counters,
                        }
                    )
                print(f"Parity context={context} geometry={geometry['id']} seed={seed}", flush=True)
    return {
        "configurations": rows,
        "maximum_output_abs_difference": max(r["maximum_output_abs_difference"] for r in rows),
        "query_head_cases": sum(r["query_head_cases"] for r in rows),
        "selected_ids_equal": True,
        "physical_scored_nodes_and_keys_equal": True,
    }


@torch.no_grad()
def measure(study, process):
    rows = []
    timing = {"warmup_rounds": 5, "timed_rounds": 50, "order_seed": 831 + process}
    for context in study["config"]["contexts"]:
        samples = load_samples(study, context)
        for seed in study["config"]["seeds"]:
            refs = load_references(study, context, "c16-r2-d2", seed)
            config = TreeConfig(chunk_size=16, depth=2)
            for layout in ("separate_four_queries", "stacked_four_queries", "separate_last_query"):
                positions = (
                    (context - 1,)
                    if layout == "separate_last_query"
                    else tuple(context * i // 4 - 1 for i in (1, 2, 3, 4))
                )
                prepared = [sdpa_inputs(sample, positions) for sample in samples]
                if layout == "stacked_four_queries":
                    prepared = [
                        tuple(torch.cat([p[i] for p in prepared], dim=0) for i in range(4))
                        + (prepared[0][4],)
                    ]

                def build_reference(prepared=prepared, refs=refs, config=config):
                    return [
                        HierarchicalIndex(k, v, refs, config=config) for _, k, v, _, _ in prepared
                    ]

                def build_batched(prepared=prepared, refs=refs, config=config):
                    return [
                        BatchedHierarchicalIndex(
                            k, v, refs, config=config, max_stage_tensor_bytes=512 * 1024 * 1024
                        )
                        for _, k, v, _, _ in prepared
                    ]

                reference = build_reference()
                batched = build_batched()
                stats = []
                for index, item in zip(batched, prepared, strict=True):
                    stats.append(compare(index, [item], 0.9))

                def call_reference(indexes=reference, prepared=prepared):
                    return [
                        idx.attend(
                            q, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=0.9
                        )
                        for idx, (q, _, _, visible, _) in zip(indexes, prepared, strict=True)
                    ]

                def call_batched(indexes=batched, prepared=prepared):
                    return [
                        idx.attend(
                            q, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=0.9
                        )
                        for idx, (q, _, _, visible, _) in zip(indexes, prepared, strict=True)
                    ]

                def call_dense(prepared=prepared):
                    return [
                        torch.nn.functional.scaled_dot_product_attention(
                            q, k, v, attn_mask=mask, dropout_p=0.0
                        )
                        for q, k, v, _, mask in prepared
                    ]

                timings = timed_batches(
                    {"reference": call_reference, "batched": call_batched, "sdpa": call_dense},
                    timing,
                )
                builds = timed_batches(
                    {"reference": build_reference, "batched": build_batched},
                    {**timing, "warmup_rounds": 1, "timed_rounds": 3},
                )
                rows.append(
                    {
                        "context": context,
                        "seed": seed,
                        "layout": layout,
                        "p": 0.9,
                        "geometry": "c16-r2-d2",
                        "timing": timings,
                        "construction": builds,
                        "reference_owned_tensor_bytes": sum(
                            i.info.owned_tensor_bytes for i in reference
                        ),
                        "batched_owned_tensor_bytes": sum(
                            i.info.owned_tensor_bytes for i in batched
                        ),
                        "maximum_output_abs_difference": max(
                            s["maximum_output_abs_difference"] for s in stats
                        ),
                        **{
                            key: sum(s[key] for s in stats)
                            for key in (
                                "query_head_cases",
                                "scored_summary_slots",
                                "selected_key_slots",
                                "ordering_slots",
                                "attention_softmax_slots",
                            )
                        },
                        "engine": "batched",
                    }
                )
                print(
                    f"Timed process={process} context={context} seed={seed} layout={layout}",
                    flush=True,
                )
    return {"timing_config": timing, "rows": rows}


@torch.no_grad()
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process", type=int)
    parser.add_argument("--parity-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("retain existing benchmark report")
    if not args.parity_only and args.process is None:
        parser.error("--process is required for timing")
    torch.set_num_threads(4)
    source_paths = [
        *ROOT.glob("src/**/*.py"),
        ROOT / "research/batched_execution.py",
        Path(__file__),
    ]
    before = {str(p.relative_to(ROOT)): file_hash(p) for p in source_paths}
    study_path = ROOT / "experiments/gpt2-cost-quality-v1/report.json"
    study = json.loads(study_path.read_text())
    data = parity(study) if args.parity_only else measure(study, args.process)
    if before != {str(p.relative_to(ROOT)): file_hash(p) for p in source_paths}:
        raise RuntimeError("implementation changed during benchmark")
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = {
        "git_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_sha256": before,
        "study_report_sha256": file_hash(study_path),
        "process": args.process,
        "parity_only": args.parity_only,
        "platform": platform.platform(),
        "torch": torch.__version__,
        "threads": torch.get_num_threads(),
        "whole_process_peak_rss_bytes": peak if platform.system() == "Darwin" else peak * 1024,
        "scope": "CPU float64 development traces; no new model-quality, GPU or incremental-decode evidence. Parity gates precede timings. Actual batched-engine slots and padding are reported. Whole-process RSS is not per-case inference memory.",
        **data,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
