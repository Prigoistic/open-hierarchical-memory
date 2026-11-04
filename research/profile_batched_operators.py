"""Separate post-timing operator diagnosis; these times are not speed claims."""

import json
from pathlib import Path

import torch

from open_hierarchical_memory import ExecutionMode, TreeConfig

from .batched_execution import BatchedHierarchicalIndex
from .benchmark_batched import compare, load_references, load_samples
from .cost_quality import sdpa_inputs
from .profile_execution import file_hash

ROOT = Path(__file__).resolve().parents[1]


@torch.no_grad()
def main():
    output = ROOT / "experiments/batched-execution-v1/operator-profile.json"
    if output.exists():
        raise FileExistsError("preserve existing operator diagnosis")
    torch.set_num_threads(4)
    study = json.loads((ROOT / "experiments/gpt2-cost-quality-v1/report.json").read_text())
    context = 1024
    samples = load_samples(study, context)
    refs = load_references(study, context, "c16-r2-d2", 7)
    records = []
    for layout in ("separate_four_queries", "stacked_four_queries", "separate_last_query"):
        positions = (1023,) if layout == "separate_last_query" else (255, 511, 767, 1023)
        prepared = [sdpa_inputs(sample, positions) for sample in samples]
        if layout == "stacked_four_queries":
            prepared = [
                tuple(torch.cat([p[i] for p in prepared], dim=0) for i in range(4))
                + (prepared[0][4],)
            ]
        indexes = [
            BatchedHierarchicalIndex(
                k,
                v,
                refs,
                config=TreeConfig(chunk_size=16, depth=2),
                max_stage_tensor_bytes=512 * 1024 * 1024,
            )
            for _, k, v, _, _ in prepared
        ]
        for index, item in zip(indexes, prepared, strict=True):
            compare(index, [item], 0.9)

        def execute(indexes=indexes, prepared=prepared):
            return [
                index.attend(q, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=0.9)
                for index, (q, _, _, visible, _) in zip(indexes, prepared, strict=True)
            ]

        for _ in range(5):
            execute()
        with torch.profiler.profile(
            activities=[torch.profiler.ProfilerActivity.CPU],
            record_shapes=True,
            profile_memory=True,
        ) as profile:
            execute()
        events = [
            {
                "operator": event.key,
                "count": event.count,
                "self_cpu_ms": event.self_cpu_time_total / 1000,
                "inclusive_cpu_ms": event.cpu_time_total / 1000,
                "self_cpu_memory_bytes": event.self_cpu_memory_usage,
                "input_shapes": event.input_shapes,
            }
            for event in profile.key_averages(group_by_input_shape=True)
        ]
        records.append(
            {
                "context": context,
                "seed": 7,
                "layout": layout,
                "operators": sorted(events, key=lambda e: e["self_cpu_ms"], reverse=True),
            }
        )
    output.write_text(
        json.dumps(
            {
                "scope": "One instrumented post-timing call per layout. Operator self time/memory is diagnostic; includes profiling overhead and is not uninstrumented latency or inference peak RSS.",
                "backend_source_sha256": file_hash(ROOT / "research/batched_execution.py"),
                "torch": torch.__version__,
                "threads": torch.get_num_threads(),
                "records": records,
            },
            indent=2,
        )
        + "\n"
    )
    for row in records:
        print(
            row["layout"],
            [(e["operator"], round(e["self_cpu_ms"], 3)) for e in row["operators"][:5]],
        )


if __name__ == "__main__":
    main()
