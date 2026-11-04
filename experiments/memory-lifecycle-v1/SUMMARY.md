# Reversible forgetting and coverage replay: diagnostic v1

Completed 5 November 2026. Source and fixed protocol were committed at `dda4d4bf275e8d60643ebffcf8068c3f911b6625` before execution. This is a lexical lifecycle mechanism diagnostic on authored text, not ZHA-backed persistent semantic memory, an LLM evaluation or a new-algorithm result.

## Main finding

Coverage replay improves overall current-record retrieval in this fixture, but fails most delayed rare-fact queries. At capacity 16, replay gets 90/128 overall versus 46/128 for scheduled current-query probing and 32/128 for decay alone. It does about 59.3% more lexical comparisons than query probing. Its mean per-run p50/p95 query times are also higher than that baseline. Cold recovery remains unresolved; do not integrate this policy into an assistant as reliable memory.

All three seed permutations have identical aggregate hit counts. They reorder one small recipe; they are not three independent real-world datasets, and no confidence interval or generalization claim is justified.

## Full comparison

Every row is one 128-query stream per seed; reported accuracy pools three permutations (384 queries). Comparisons, archive rows and timing quantiles are arithmetic means across the three runs. Time includes replay inside the query. Timing is descriptive: one sequential pass per setting, with no controlled repeated-process speed study.

| Hot capacity | Policy | Correct / queries | Accuracy | Comparisons / run | Archive rows / run | Mean run p50 / p95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 8 | full | 384/384 | 100.0% | 7168.0 | 0.0 | 0.252 / 0.362 |
| 8 | fifo | 33/384 | 8.6% | 1032.0 | 8.0 | 0.047 / 0.066 |
| 8 | lru | 33/384 | 8.6% | 1032.0 | 8.0 | 0.051 / 0.115 |
| 8 | lfu | 78/384 | 20.3% | 1024.0 | 0.0 | 0.049 / 0.065 |
| 8 | decay | 69/384 | 18.0% | 1024.0 | 0.0 | 0.048 / 0.074 |
| 8 | decay_probe | 120/384 | 31.2% | 1229.0 | 256.0 | 0.072 / 0.192 |
| 8 | decay_replay | 174/384 | 45.3% | 2728.0 | 256.0 | 0.053 / 0.175 |
| 16 | full | 384/384 | 100.0% | 7168.0 | 0.0 | 0.258 / 0.365 |
| 16 | fifo | 33/384 | 8.6% | 2056.0 | 8.0 | 0.080 / 0.151 |
| 16 | lru | 33/384 | 8.6% | 2056.0 | 8.0 | 0.078 / 0.122 |
| 16 | lfu | 96/384 | 25.0% | 2048.0 | 0.0 | 0.081 / 0.117 |
| 16 | decay | 96/384 | 25.0% | 2048.0 | 0.0 | 0.078 / 0.112 |
| 16 | decay_probe | 138/384 | 35.9% | 2213.0 | 256.0 | 0.084 / 0.170 |
| 16 | decay_replay | 270/384 | 70.3% | 3525.3 | 256.0 | 0.128 / 0.302 |

The full-memory reference holds up to 72 current records; its repeated capacity rows are the same unbounded-hot reference measured separately. Every policy preserves all 80 originals, including eight superseded versions. All SQLite files are 45,056 bytes in this run. An 8/16-record hot cap is not an 8/16-record total-storage claim. UTF-8 payload bytes exclude tokens, Python objects, SQLite indexes/pages, metadata and OS caches.

## Delayed rare-fact failure

| Hot capacity | Policy | Delayed queries correct / total | Late-revisit queries correct / total |
| --- | --- | ---: | ---: |
| 8 | full | 72/72 | 144/144 |
| 8 | decay | 0/72 | 45/144 |
| 8 | decay_probe | 0/72 | 54/144 |
| 8 | decay_replay | 0/72 | 57/144 |
| 16 | full | 72/72 | 144/144 |
| 16 | decay | 0/72 | 72/144 |
| 16 | decay_probe | 0/72 | 72/144 |
| 16 | decay_replay | 12/72 | 102/144 |

At capacity 16, replay recovers only 4/24 delayed rare queries per permutation (16.7%); at capacity 8 it recovers none. Shared lexical scaffolding gives wrong hot records scores above the fallback threshold. Recovery then does not run, and replay often favors repeated topics or broadly matching records. This is observed failure of this scorer/controller/fixture combination, not evidence that all replay or hierarchy methods fail. Source labels are never available to the controller.

## Behavior and evidence

- 174 local tests pass, including 58 lifecycle cases and generated sequences. Ruff/formatting, seven-core-module and four-lifecycle-module strict typing pass. Five lifecycle and ten core semantic faults are caught. Installed numerical-core source bytes are unchanged.
- All 42 runs respect the hot cap. The separate audit checks 5,376 query traces, 3,360 original-record instances across separate archives (80 originals per run), source/config/fixture identity, physical cursor traces, retrieval ranking, aggregates, bytes, correction chains and read-only archive originals. This is self-review, not external validation.
- Three evidence faults (wrong correctness label, scan accounting and source identity) are caught on temporary copies.
- A separate subprocess CLI round trip stores a correction, retrieves the current record and reopens the same database with both originals intact. Session-use metadata resets, as declared.
- No superseded records are returned. This follows explicit keyed version tracking; no semantic contradiction detection or general factual-answer guarantee is demonstrated.
- Recovery/replay row counts include stale and already-hot rows. Replay and probe use the same scheduled allowance, not equal compute: replay scores recent history and incurs more comparisons.
- Query-work promotions/evictions are query and replay events only. Write operations have separate raw hot-state traces and latency. No per-insert operation-count saving is claimed.
- Hosted CI remains blocked by the existing billing restriction. These are local results, not a green hosted run.

## Decision

Keep the prototype and all unfavorable results. Before model integration, test stronger query-aware recovery and cue specificity against unconditional bounded probing, with matched total budgets and new stream structures. The current three permutations are now development fixtures. A ZHA/hierarchical semantic adapter, persisted controller state, real longitudinal assistant evaluation and consolidation/associative dynamics remain separate unimplemented milestones. Replaying this archive does not train model weights.

## Artifacts

[Protocol](../../docs/MEMORY_LIFECYCLE.md), [raw report](report.json), [query traces](queries.jsonl), [write traces](ingest.jsonl), [audit](audit.json), [integration/fault checks](integration-checks.json). Authored fixtures: [7](fixture-7.json), [23](fixture-23.json), [101](fixture-101.json). Original SQLite files remain in ignored `.cache/memory-lifecycle-v1/`; reproduce using fresh directories and the source commit, never overwrite this run.
