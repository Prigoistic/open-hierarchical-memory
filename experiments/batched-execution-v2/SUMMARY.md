# Profile-driven batched execution experiment

Completed 4 November 2026. This experiment profiles the existing reference and tests a separate batched research implementation without changing any numerical core source file or fitting any model parameters. It uses existing GPT-2 development traces, not a new model-quality holdout.

## What changed

The reference profile identified summary gathering, repeated per-query scoring/selection and raw-KV processing as substantial costs. The prototype packs summary copies, scores only actual candidates across independent queries, and processes selected KV in ragged batches. Sorting/softmax padding is reported separately. The prototype retains the immutable reference snapshot, so its additional storage is included.

The [implementation and fixed comparison protocol](../../docs/EXECUTION_BACKEND.md) describe its supported scope. Detailed traces, custom budgets, dense mode and fallback requests explicitly use the reference engine. Every timing row here confirms `engine=batched`; reference dispatch is not passed off as an optimization result.

## Correctness gates

- All 252 trained geometry/context/seed/threshold combinations (including p=1) pass selected-ID and output checks across 96,768 query/head cases. Selected IDs and logical scoring counts match exactly; maximum absolute output difference is 7.550e-15, within the unchanged `atol=1e-10, rtol=1e-9` tolerance.
- Scored summary slots and selected-key slots match the reference's logical work. No full-tree or full-prefix scoring is hidden behind a sparse mask. Padding affects ordering/softmax and is reported below.
- The local behavior suite passes, including sixty generated batched configurations checked against the independent scalar oracle. Six deliberately broken batched variants are detected, in addition to the ten original core mutations. Batch/GQA isolation, causality, ownership, budgets, p=1, dispatch and scratch limits are covered.
- The original core remains byte-identical to the profiled reference. Instrumented profiling separately checks exact output/route parity before reporting components. These self-checks and independent numerical algorithms are not an external review or a universal correctness proof.

## Measured query latency

Three fresh sequential processes, three fixed reference seeds, five warmups and fifty recorded repetitions per case. CPU float64, four threads. Each time is the arithmetic mean of nine process/seed medians for the complete eight-window batch. All three paths receive matching query layout and prefix masks. p=.90, C16/R2/depth2. There are 384 query/head cases for four-query layouts and 96 for final-query-only calls. These are static-cache workloads, not end-to-end generation.

| Context | Layout | Reference ms | Batched ms | Dense SDPA ms | Gain over reference | Speed ratio vs SDPA |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 256 | 8 separate calls / 4 queries | 22.081 | 9.632 | 0.677 | 2.29x | 0.070x |
| 256 | 1 stacked batch / 4 queries | 21.925 | 8.211 | 0.537 | 2.67x | 0.065x |
| 256 | 8 separate calls / final query | 6.387 | 4.607 | 0.480 | 1.39x | 0.104x |
| 512 | 8 separate calls / 4 queries | 30.593 | 15.574 | 1.133 | 1.96x | 0.073x |
| 512 | 1 stacked batch / 4 queries | 30.512 | 13.495 | 1.004 | 2.26x | 0.074x |
| 512 | 8 separate calls / final query | 10.167 | 6.832 | 0.826 | 1.49x | 0.121x |
| 1024 | 8 separate calls / 4 queries | 41.188 | 22.830 | 2.147 | 1.80x | 0.094x |
| 1024 | 1 stacked batch / 4 queries | 41.406 | 21.172 | 1.971 | 1.96x | 0.093x |
| 1024 | 8 separate calls / final query | 13.862 | 10.303 | 1.606 | 1.35x | 0.156x |

Gain over the old reference is an engineering comparison. Speed ratio vs SDPA is dense time divided by batched time; below one means the prototype is slower than dense. Native SDPA's layout changes with the hierarchical layout, so stacked speed cannot be attributed to sparse routing alone. Detailed tails, process-to-process ratios and raw times are retained.

## Construction, storage and padding

| Context | Layout | Batched build ms | One-use speed ratio vs SDPA | 128-static-use scenario | Owned tensor storage vs reference | Ordering padding | Attention-softmax padding |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 256 | 8 separate calls / 4 queries | 19.684 | 0.0231x | 0.0692x | 1.056x | 1.67x | 2.50x |
| 256 | 1 stacked batch / 4 queries | 19.269 | 0.0196x | 0.0643x | 1.056x | 1.67x | 2.77x |
| 256 | 8 separate calls / final query | 19.608 | 0.0198x | 0.1008x | 1.056x | 1.00x | 1.86x |
| 512 | 8 separate calls / 4 queries | 40.520 | 0.0202x | 0.0713x | 1.060x | 1.64x | 2.86x |
| 512 | 1 stacked batch / 4 queries | 40.425 | 0.0186x | 0.0727x | 1.060x | 1.64x | 3.28x |
| 512 | 8 separate calls / final query | 40.486 | 0.0175x | 0.1155x | 1.060x | 1.00x | 2.04x |
| 1024 | 8 separate calls / 4 queries | 82.976 | 0.0203x | 0.0914x | 1.061x | 1.98x | 3.28x |
| 1024 | 1 stacked batch / 4 queries | 83.401 | 0.0188x | 0.0903x | 1.061x | 1.98x | 3.92x |
| 1024 | 8 separate calls / final query | 84.986 | 0.0169x | 0.1464x | 1.061x | 1.43x | 2.25x |

One use includes full construction. The 128-use scenario amortizes the same static snapshot's build, not an incrementally growing cache. Owned tensor storage includes canonical KV, references and both summary representations; it excludes caller data, Python metadata and scratch. Whole-process RSS includes both backends and data loading, and is not a per-setting inference memory measurement. Stage estimates are not hard process-RSS limits.

## Learning diagnosis remains separate

On the previously inspected test records, random references dominate fitted references in error and counted work at 6/63 fitted points on the original three-threshold grid within the same geometry/context. This is exploratory and not a new statistical result. It does not prove random references are always better; it prevents claiming that fitting consistently improves executed attention. See [every comparison](learning-diagnostic.json). Use validation data and a new sealed cohort for any further duration/data/loss study.

## Artifacts and remaining work

- [Aggregate timings](aggregate.json), [complete real-trace parity](parity.json), [learning diagnostic](learning-diagnostic.json).
- Raw workers: [process 0](process-0.json), [process 1](process-1.json), [process 2](process-2.json). Each records source hashes, dependency/platform metadata, work/padding, raw timings, index costs and explicit engine.
- [Reference component profile](../execution-profile-v1/SUMMARY.md), [core verification](../../docs/evidence/core-verification.json), [batched mutation evidence](../../docs/evidence/batched-mutations.json), [execution plan](../../docs/NEXT_EXPERIMENTS.md).

This remains one layer and contexts within GPT-2's native 1,024 positions. It changes execution, not the learned model or routing quality. No GPU, long-context language, whole-model generation, conservative-error or production-readiness result is implied. Profile any remaining gap before another optimization; preserve unfavorable layouts, build costs and memory. Incremental updates and new precision/backends require independent gates.

## Resource review and operator follow-up

This is the corrected v2 implementation, bound to its recorded source commit. It preflights candidate/leaf counts before ID expansion and applies the declared row/stage limits; the earlier [v1 experiment](../batched-execution-v1/SUMMARY.md) is preserved. The [post-timing operator profile](operator-profile.json) records instrumented self costs separately from the uninstrumented fresh-process comparisons. It does not establish end-to-end kernel efficiency or peak inference memory.
