# Reference execution profile

Completed before implementing the batched prototype. Existing development traces, frozen C16/R2/depth2, p=.90, CPU float64, four threads. Three fresh processes, three seeds, five warmups and fifty timed repetitions. Numbers below average nine seed/process medians for eight windows with four query positions each.

| Context | Reference query ms | Dense SDPA ms | Selected-ID replay ms |
| --- | ---: | ---: | ---: |
| 256 | 22.197 | 0.622 | 5.949 |
| 512 | 30.365 | 1.070 | 6.826 |
| 1024 | 40.629 | 2.150 | 9.141 |

Replay receives the actual selected IDs in advance and omits routing, public validation and result metadata. It is a diagnostic only. It remains slower than dense, so optimizing routing alone cannot close the gap in this execution style.

## Instrumented component attribution at 1,024 tokens, seed 7

These are exclusive component times from a separate instrumented call, not headline latency. Every instrumented call first matches exact reference outputs and routes. Inclusive parent times overlap children and must not be added together.

| Stage | Calls | Exclusive ms |
| --- | ---: | ---: |
| public_validation_copy_setup | 8 | 0.265 |
| candidate_expansion | 768 | 0.640 |
| summary_gather | 672 | 12.710 |
| summary_scoring | 672 | 5.490 |
| top_p_selection | 672 | 5.257 |
| leaf_expansion | 384 | 1.976 |
| routing_total | 384 | 3.313 |
| raw_kv_gather | 384 | 6.558 |
| selected_attention | 384 | 6.362 |
| result_metadata | 384 | 1.188 |
| attend_total | 8 | 2.992 |

Summary gathering is the largest isolated measured component, but selected-ID replay also shows significant residual cost. The resulting prototype therefore batches actual candidate scoring and selected attention in addition to packing summary reads. Construction stages and full cProfile call records remain in process 0.

[Process 0](process-0.json), [process 1](process-1.json), [process 2](process-2.json), [prototype results](../batched-execution-v1/SUMMARY.md). Source hashes and the earlier study-report identity are retained in each process report. The numerical core was not edited by profiling.
