"""Development-trace CPU profiling; instrumented numbers are not latency claims.

AST wrappers add timing contexts around the existing reference statements in
memory. No numerical expression or production source file is changed. Outputs
and complete routes must match before a component profile is accepted.
"""

import argparse
import ast
import cProfile
import hashlib
import inspect
import json
import platform
import pstats
import subprocess
import textwrap
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import torch

import open_hierarchical_memory.attention as attention_module
import open_hierarchical_memory.routing as routing_module
import open_hierarchical_memory.tree as tree_module
from open_hierarchical_memory import ExecutionMode, HierarchicalIndex, TreeConfig

from .cost_quality import sdpa_inputs, timed_batches
from .fitting import TraceExample

ROOT = Path(__file__).resolve().parents[1]


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class StageTimer:
    def __init__(self):
        self.stack = []
        self.rows = defaultdict(lambda: {"calls": 0, "inclusive_ms": 0.0, "exclusive_ms": 0.0})

    @contextmanager
    def stage(self, name):
        frame = [time.perf_counter_ns(), 0]
        self.stack.append(frame)
        try:
            yield
        finally:
            elapsed = time.perf_counter_ns() - frame[0]
            self.stack.pop()
            row = self.rows[name]
            row["calls"] += 1
            row["inclusive_ms"] += elapsed / 1e6
            row["exclusive_ms"] += (elapsed - frame[1]) / 1e6
            if self.stack:
                self.stack[-1][1] += elapsed


def assigned(statement, name):
    return isinstance(statement, ast.Assign) and any(
        isinstance(t, ast.Name) and t.id == name for t in statement.targets
    )


def wrap(body, name):
    return ast.With(
        items=[
            ast.withitem(
                context_expr=ast.Call(
                    func=ast.Name(id="stage", ctx=ast.Load()),
                    args=[ast.Constant(name)],
                    keywords=[],
                )
            )
        ],
        body=body,
    )


def ranges(body, specifications):
    regions = []
    for label, start, end, extra in specifications:
        first = next(i for i, statement in enumerate(body) if assigned(statement, start))
        last = next(i for i, statement in enumerate(body) if assigned(statement, end)) + extra
        regions.append((first, last, label))
    for first, last, label in sorted(regions, reverse=True):
        body[first : last + 1] = [wrap(body[first : last + 1], label)]
    return body


class Instrument(ast.NodeTransformer):
    def visit_For(self, node):
        self.generic_visit(node)
        target = node.target.id if isinstance(node.target, ast.Name) else None
        if target == "level":
            node.body = ranges(
                node.body,
                [
                    ("candidate_expansion", "candidate_ids", "candidate_ids", 0),
                    ("summary_gather", "summaries", "biases", 0),
                    ("summary_scoring", "scores", "scores", 1),
                ],
            )
        if target == "t":
            node.body = ranges(
                node.body,
                [
                    ("raw_kv_gather", "selected", "values", 0),
                    ("selected_attention", "logits", "value", 1),
                ],
            )
            first = next(
                i
                for i, statement in enumerate(node.body)
                if isinstance(statement, ast.Assign)
                and any(
                    isinstance(t, ast.Subscript)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "output"
                    for t in statement.targets
                )
            )
            node.body[first:] = [wrap(node.body[first:], "result_metadata")]
        return node

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        if node.name == "route":
            first = next(
                i for i, statement in enumerate(node.body) if assigned(statement, "local_start")
            )
            node.body[first:] = [wrap(node.body[first:], "leaf_expansion")]
            node.body = [wrap(node.body, "routing_total")]
        elif node.name == "_top_p":
            node.body = [wrap(node.body, "top_p_selection")]
        elif node.name == "attend":
            first_for = next(
                i for i, statement in enumerate(node.body) if isinstance(statement, ast.For)
            )
            node.body[:first_for] = [wrap(node.body[:first_for], "public_validation_copy_setup")]
            node.body = [wrap(node.body, "attend_total")]
        return node


def instrumented(function, namespace, timer):
    source = textwrap.dedent(inspect.getsource(function))
    syntax = Instrument().visit(ast.parse(source))
    ast.fix_missing_locations(syntax)
    environment = {**namespace, "stage": timer.stage}
    exec(compile(syntax, f"<instrumented-{function.__name__}>", "exec"), environment)
    return environment[function.__name__]


def instrumented_attention(timer):
    top_p = instrumented(routing_module._top_p, vars(routing_module), timer)
    route = instrumented(routing_module.route, {**vars(routing_module), "_top_p": top_p}, timer)
    return instrumented(
        attention_module.HierarchicalIndex.attend, {**vars(attention_module), "route": route}, timer
    )


def cprofile_rows(function):
    profiler = cProfile.Profile()
    profiler.runcall(function)
    stats = pstats.Stats(profiler)
    rows = []
    for (filename, line, name), (
        primitive,
        calls,
        own,
        cumulative,
        _callers,
    ) in stats.stats.items():
        rows.append(
            {
                "file": filename,
                "line": line,
                "function": name,
                "primitive_calls": primitive,
                "calls": calls,
                "exclusive_ms": own * 1000,
                "inclusive_ms": cumulative * 1000,
            }
        )
    return sorted(rows, key=lambda row: row["exclusive_ms"], reverse=True)


@torch.no_grad()
def main():
    from safetensors.torch import load_file

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("retain existing process report")
    torch.set_num_threads(4)
    source_before = {str(p.relative_to(ROOT)): file_hash(p) for p in ROOT.glob("src/**/*.py")}
    study = json.loads((ROOT / "experiments/gpt2-cost-quality-v1/report.json").read_text())
    rows = []
    timing = {"warmup_rounds": 5, "timed_rounds": 50, "order_seed": 831 + args.process}
    for context in (256, 512, 1024):
        positions = tuple(context * i // 4 - 1 for i in (1, 2, 3, 4))
        prepared = []
        for book in study["config"]["splits"]["test"]:
            for offset in study["config"]["window_offsets"]:
                path = ROOT / f".cache/cost-quality-v1/trace-{context}-{book}-{offset}.safetensors"
                tensors = load_file(str(path))
                expected = next(
                    c
                    for c in study["captures"]
                    if c["context"] == context and c["book"] == book and c["offset"] == offset
                )
                if file_hash(path) != expected["trace_sha256"]:
                    raise ValueError("trace identity mismatch")
                sample = TraceExample(
                    f"gutenberg:{book}",
                    offset,
                    tensors["queries"],
                    tensors["keys"],
                    tensors["values"],
                )
                prepared.append(sdpa_inputs(sample, positions))
        for seed in (7, 23, 101):
            checkpoint = (
                ROOT
                / f"experiments/gpt2-cost-quality-v1/references/t{context}-c16-r2-d2-s{seed}.safetensors"
            )
            expected_checkpoint = next(
                f
                for f in study["fitting"]
                if f["context"] == context and f["geometry"] == "c16-r2-d2" and f["seed"] == seed
            )
            if file_hash(checkpoint) != expected_checkpoint["checkpoint_sha256"]:
                raise ValueError("reference checkpoint changed")
            refs = load_file(str(checkpoint))["trained"]
            geometry = TreeConfig(chunk_size=16, depth=2)

            def build(refs=refs, geometry=geometry, prepared=prepared):
                return [
                    HierarchicalIndex(k, v, refs, config=geometry) for _, k, v, _, _ in prepared
                ]

            indexes = build()

            def reference(indexes=indexes, prepared=prepared):
                return [
                    index.attend(
                        q, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=0.9
                    )
                    for index, (q, _, _, visible, _) in zip(indexes, prepared, strict=True)
                ]

            def dense(prepared=prepared):
                return [
                    torch.nn.functional.scaled_dot_product_attention(
                        q, k, v, attn_mask=mask, dropout_p=0.0
                    )
                    for q, k, v, _, mask in prepared
                ]

            expected = reference()
            selected = [
                [
                    (
                        route.query_head,
                        route.query_index,
                        torch.tensor(route.selected_ids, dtype=torch.int64),
                    )
                    for route in result.routes
                ]
                for result in expected
            ]

            def replay(prepared=prepared, selected=selected):
                outputs = []
                for (q, k, v, _, _), routes in zip(prepared, selected, strict=True):
                    output = torch.empty_like(q)
                    for head, pos, ids in routes:
                        keys = k[0, head].index_select(0, ids)
                        values = v[0, head].index_select(0, ids)
                        logits = (keys * q[0, head, pos]).sum(-1) / (q.shape[-1] ** 0.5)
                        output[0, head, pos] = torch.softmax(logits, -1) @ values
                    outputs.append(output)
                return outputs

            for actual, wanted in zip(replay(), expected, strict=True):
                torch.testing.assert_close(actual, wanted.output, atol=1e-10, rtol=1e-9)
            measurements = timed_batches(
                {"reference": reference, "sdpa": dense, "selected_id_replay": replay}, timing
            )
            build_times = timed_batches(
                {"construction": build}, {**timing, "warmup_rounds": 2, "timed_rounds": 5}
            )
            component = None
            if args.process == 0 and seed == 7:
                timer = StageTimer()
                profiled = instrumented_attention(timer)
                actual = [
                    profiled(
                        index,
                        q,
                        visible_counts=visible,
                        mode=ExecutionMode.PAPER_APPROXIMATE,
                        p=0.9,
                    )
                    for index, (q, _, _, visible, _) in zip(indexes, prepared, strict=True)
                ]
                for a, b in zip(actual, expected, strict=True):
                    if a.routes != b.routes:
                        raise AssertionError("instrumentation changed routes")
                    torch.testing.assert_close(a.output, b.output, atol=0, rtol=0)
                builder = StageTimer()

                def summarize(*a, _timer=builder, _fn=tree_module.summarize, **kw):
                    with _timer.stage("leaf_summarization"):
                        return _fn(*a, **kw)

                def merge(*a, _timer=builder, _fn=tree_module.merge, **kw):
                    with _timer.stage("parent_merge"):
                        return _fn(*a, **kw)

                with (
                    patch.object(tree_module, "summarize", summarize),
                    patch.object(tree_module, "merge", merge),
                ):
                    with builder.stage("construction_total"):
                        build()
                component = {
                    "stages": dict(timer.rows),
                    "construction_stages": dict(builder.rows),
                    "reference_cprofile": cprofile_rows(reference),
                    "build_cprofile": cprofile_rows(build),
                    "instrumented_output_and_routes_exactly_equal": True,
                    "scope": "Instrumentation and cProfile overhead included here; not headline latency. Inclusive parent times overlap child times; exclusive times do not.",
                }
            rows.append(
                {
                    "context": context,
                    "seed": seed,
                    "geometry": "c16-r2-d2",
                    "p": 0.9,
                    "query_head_cases": 384,
                    "timing": measurements,
                    "build": build_times,
                    "components": component,
                }
            )
            print(f"Profile process={args.process} context={context} seed={seed}", flush=True)
    if source_before != {str(p.relative_to(ROOT)): file_hash(p) for p in ROOT.glob("src/**/*.py")}:
        raise RuntimeError("numerical core changed during profile")
    result = {
        "process": args.process,
        "git_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "profile_source_sha256": file_hash(Path(__file__)),
        "reference_source_sha256": source_before,
        "study_report_sha256": file_hash(ROOT / "experiments/gpt2-cost-quality-v1/report.json"),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "threads": torch.get_num_threads(),
        "timing_config": timing,
        "rows": rows,
        "scope": "Existing development traces, one frozen GPT-2 layer, CPU float64. Replay excludes routing/validation/metadata and is a diagnostic, not a search implementation or deployable speedup.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
