# Execution profile and batched research backend

4 November 2026. The reference profile and first batched experiment are complete. The first timings are retained under `experiments/batched-execution-v1/`. A resource-preflight revision is now being verified/re-measured as v2; the original numerical core remains unchanged.

## Reference profile

`research/profile_execution.py` uses the fixed C16/R2/depth2, p=.90 checkpoints and the existing four-book development traces. Three fresh processes, three seeds and three contexts; each timing uses five warmups and fifty measured repetitions in seeded interleaved order. The workload is eight independent windows with four quarter-position queries each. Dense SDPA has identical dtype, visibility and data. There is no new quality holdout or reference fitting.

Means of seed/process median batch times:

| Context | Reference query ms | Native SDPA ms | Selected-ID replay ms |
| --- | ---: | ---: | ---: |
| 256 | 22.197 | .622 | 5.949 |
| 512 | 30.365 | 1.070 | 6.826 |
| 1,024 | 40.629 | 2.150 | 9.141 |

Replay receives the original selected IDs in advance and excludes routing/public validation/result metadata. It is a diagnostic, not a search implementation or deployable speedup. Its remaining latency shows that removing routing alone is insufficient in this execution style.

At 1,024, a separate instrumented seed-7 call attributes 12.71ms to summary gathering, 5.49ms to summary scoring, 5.26ms to top-p, 6.56ms to raw-KV gathering and 6.36ms to selected attention. Total instrumented attention is 46.75ms. These times include instrumentation overhead, unlike the uninstrumented timing table. Parent inclusive times overlap child times; use exclusive stage values to avoid double-counting.

The instrumentation inserts timing contexts around the reference's existing statements in memory. It must reproduce exact outputs and complete routes before acceptance; it does not edit production numerical files. cProfile records and instrumented construction stages are retained alongside the raw timings in `experiments/execution-profile-v1/process-*.json`.

## Why the prototype batches more than summary reads

Packed summary reads address the largest isolated component, but the replay diagnostic remains slower than SDPA. Therefore the prototype also batches actual candidate scoring and selected attention, preserving query-local routing decisions. It is a separate `research/batched_execution.py` implementation; the supported float64 core remains byte-identical to the profiled reference.

- Packed tensors hold copies of per-level means/biases. The owned reference snapshot remains immutable. Both representations are counted, and the snapshot budget includes the added copy before allocation. This prototype trades extra storage for simpler batched access; it is not a memory-saving result.
- Only actual complete candidate nodes are gathered/scored. Python metadata still expands the selected children and parentless chunks per query. Empty levels remain empty; no future-containing node enters scoring.
- Per-query top-p ordering is batched with inert negative-infinity padding, stable logical order and explicit p=1 all-node selection. Original raw keys are selected in sorted order, with sink/local-tail handling preserved.
- Selected-key dot products and value accumulations use packed ragged slots. Softmax uses padded logit rows; value accumulation uses `index_add_`. Reference output tolerance remains `atol=1e-10, rtol=1e-9`; no precision conversion is introduced. Physical candidate/key slots and padded ordering/softmax slots are reported separately.
- Detailed traces, explicit custom `QueryBudget`, dense execution or dense-fallback requests execute the reference implementation and return `engine='reference'`. Default approximate calls use `engine='batched'`. Timings must verify the actual engine; reference dispatch is not counted as a batched speed result.
- The default fast path enforces whole-call default node/attention/output limits. A separate stage-tensor estimate rejects oversized work before allocating the stage. This is an estimate for declared tensors, not a hard process-RSS or kernel-scratch guarantee. Python metadata and caller storage remain outside it.

The research result wraps the standard `AttentionResult` in `ExecutionResult`, with an explicit engine and physical-work counters. The numerical core's public API and defaults have not changed. This module is not shipped as a supported installed-package backend.

## Behavior evidence and remaining checks

Thirty-one targeted backend tests include sixty generated configurations against the independent scalar oracle; GQA/head and batch isolation, causal-prefix mutation, uniform ties, p=1 underflow, ownership, output aliases, default budgets, custom-budget/reference dispatch, stage limits and extra storage. Six isolated semantic faults must be detected. The original ten core fault checks remain separate.

Before timing, compare every trained context/geometry/seed from the original study, at all three thresholds plus p=1. Every selected ID must match, outputs must pass the existing tolerance, and physical node/key counts must equal logical reference work. Preserve failures as regressions; do not loosen the gate to obtain a timing result.

## Fixed timing cohort for the prototype

`research/benchmark_batched.py` records three fresh processes with five warmups and fifty timed repetitions. References and geometry stay fixed; no quality selection or training takes place. CPU float64, four threads, eight development windows, contexts 256/512/1024, seeds 7/23/101, C16/R2/depth2, p=.90. Compare contemporaneous reference, batched execution and dense native SDPA.

Report all three layouts separately:

1. Eight separate calls, four query positions per window: directly comparable to the original cost-quality fixture.
2. One stacked batch of eight windows, four positions each: both SDPA and hierarchical paths receive the same stacked layout.
3. Eight separate calls, only the final query per window: decode-shaped static-cache queries, not incremental generation.

Record construction separately for reference and batched indexes, owned tensor bytes, whole-process peak RSS (not per-setting inference peak), physical scoring slots, padding, errors and raw timings. The scratch estimate limit is explicitly 512MiB for this benchmark. Constructor and metadata costs are not hidden. Extra batching does not change the meaning of the query/head cases or make them independent samples.

```sh
uv run --locked --extra research python -m research.profile_execution --process 0 --output experiments/execution-profile-v1/process-0.json
uv run --locked --extra research python scripts/check_batched_mutations.py
uv run --locked --extra research python -m research.benchmark_batched --parity-only --output experiments/batched-execution-v1/parity.json
uv run --locked --extra research python -m research.benchmark_batched --process 0 --output experiments/batched-execution-v1/process-0.json
```

Use process IDs 0/1/2 in separate sequential processes; do not run timing workers concurrently. Existing reports are protected against overwrite. There is no GPU, new model-quality or actual growing-cache result here. Faster than the slow reference is an engineering result; native-SDPA speed and build-inclusive cost must be reported separately. Training effectiveness remains a separate experiment track.

## Resource preflight revision (v2)

Final review of v1 found candidate/leaf Python lists could be expanded before rejecting excessive batched work. V2 computes exact candidate/leaf counts and checks work/stage budgets before expansion. It also caps the fast path at 4,096 query/head rows by default, with an explicit configurable positive `max_query_rows`; rejection occurs before row metadata expansion. Regression tests inject failing expansion callbacks and verify that budget errors precede those callbacks. These limits are not a hard RSS guarantee. The algorithm, references, precision and timed cohort are unchanged. V1 measurements remain historical evidence; v2 must pass full real-trace parity and new fresh-process timings before they describe current code.
