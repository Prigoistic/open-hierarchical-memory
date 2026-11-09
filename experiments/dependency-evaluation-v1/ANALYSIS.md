# Fresh dependency-memory evaluation

The observed-known coverage channel repairs a real memory-interface failure. Dependency bundles do not add a task-success gain beyond the same-seed mask-only controls in this cohort. Ordinary full-observed graph access remains the strongest bounded-output control; no ZHA advantage is demonstrated.

This source-frozen run contains all 264 episodes: four official tasks, 11 declared conditions and fresh seeds 2001–2006 (six per task). The default limit is 96 returned raw facts plus actual current observation. Mask-bearing methods additionally receive 512 binary bytes of observed-known bits plus version/identity metadata; they are not 96-slot-only systems. There were 0 exceptions, 0 external cutoffs and 82 official truncations. No 192-budget condition was run.

| Reader | Memory | MultiRoom | DoorKey | KeyCorridor | Total |
|---|---:|---:|---:|---:|---:|
| zha_adaptive | 6/6 | 1/6 | 0/6 | 0/6 | 7/24 |
| exact | 6/6 | 3/6 | 0/6 | 0/6 | 9/24 |
| full | 6/6 | 6/6 | 6/6 | 6/6 | 24/24 |
| none | 0/6 | 0/6 | 0/6 | 0/6 | 0/24 |
| flat_zha_mask | 6/6 | 6/6 | 6/6 | 2/6 | 20/24 |
| flat_exact_mask | 6/6 | 5/6 | 6/6 | 2/6 | 19/24 |
| flat_exact_history_mask | 6/6 | 6/6 | 5/6 | 4/6 | 21/24 |
| bundle_zha | 6/6 | 6/6 | 6/6 | 2/6 | 20/24 |
| bundle_exact | 6/6 | 5/6 | 6/6 | 2/6 | 19/24 |
| bundle_recency | 6/6 | 5/6 | 6/6 | 2/6 | 19/24 |
| graph | 6/6 | 6/6 | 6/6 | 6/6 | 24/24 |

## What changed and what did not

Adding only the known-coverage mask to flat adaptive ZHA rescues 13 episodes without losing a previously solved episode (7/24 to 20/24). The same mask rescues 10 for exact (9/24 to 19/24), also without losses. These paired comparisons use the same seeds and old raw selection; the new mask prevents a known-but-omitted neighbor from being treated as a new exploration frontier. It adds no object/passability label or movement edge. This is the demonstrated causal interface improvement, not evidence that graph bundling or hierarchy caused it.

Bundle ZHA and its flat-mask control have identical success/failure outcomes on all 24 cases; their action traces match 22/24. Exact bundles and flat exact+mask have identical outcomes AND complete action sequences on all 24. The historical-only exact mask control reaches 21/24, exceeding bundle ZHA 20/24. Reclaiming visible duplicate slots is therefore an essential control, not a free benefit to attribute to bundling. Detailed paired flags and first action divergences are preserved in PAIRWISE_CONTROLS.json.

The ordinary graph control reaches 24/24 with exactly the same actions as the full-observed-memory control on every episode. It nominates from all observed heads and performs full observed-graph/BFS work. This supports the correctness/usefulness of the declared bounded raw-output interface on these tasks, but it is not sublinear access, a reduced total-memory agent or a necessary contribution from ZHA.

## Actual cost and failures

All mask reads charge full observed-head materialization, source scan, head commitment, bit writes and binary/JSON serialization. Bundle readers also charge graph maps/builds, semantic nomination, prerequisite scans, BFS calls/nodes/edges, route reconstruction, halo lookups and packing. Receipts count per-read and cumulative work. The source retrieval counters distinguish hierarchy summary/raw/rerank work from exact scoring. Owned index tensor bytes do not include Python graph/archive/RSS.

| Reader | Total policy seconds | Total executed actions | BFS edge checks | Raw planner facts returned |
|---|---:|---:|---:|---:|
| zha_adaptive | 33.714872 | 22551 | 0 | 2154394 |
| exact | 13.106153 | 22428 | 0 | 2142586 |
| full | 0.609440 | 1263 | 0 | 194305 |
| none | 6.928798 | 31230 | 0 | 0 |
| flat_zha_mask | 11.930404 | 5158 | 0 | 484666 |
| flat_exact_mask | 6.066914 | 5213 | 0 | 489946 |
| flat_exact_history_mask | 6.936672 | 5733 | 0 | 529471 |
| bundle_zha | 12.611620 | 5160 | 2340880 | 14750 |
| bundle_exact | 6.316547 | 5213 | 2334385 | 14284 |
| bundle_recency | 6.035923 | 5258 | 2456011 | 14923 |
| graph | 1.538734 | 1263 | 826206 | 38721 |

Timing includes source selection/rebuilds, all adapter work and the common planner; it excludes environment reset/stepping and trace gzip. Those costs remain separately recorded. Execution used CPU float64, two concurrent workers and one Torch thread per worker. Different failure rates produce different action counts and observation histories, so total timings are not matched-compute speed comparisons. On equal successful action traces, graph control still performs more work than full observed memory, and hierarchy has no demonstrated practical speed benefit here.

Hierarchy/exact bundle failures remain concentrated in KeyCorridor (2/6 each). Graph access solves 6/6. The missing endpoint/frontier information selected by the retrieval interface is not repaired merely by adding local dependencies to retrieved seeds. Source-reference/representation learning is separate research work; this run did not train it. Source controls and all unfavorable cases are retained.

Real formal graph receipts include 27 whole-bundle budget rejections (12 MultiRoom, 6 DoorKey, 9 KeyCorridor), rather than silently clipping support. Missing-prerequisite receipts also remain; a rejected bundle can coexist with other complete packed bundles in the same read. Halo completeness applies only to declared observed paths, not the whole reachable component. Residual known-neighbor omissions are explicitly recorded and handled by the known-only mask.

## Evidence and claim boundary

SOURCE_FREEZE_CHECK.json records that all sources still matched at computation completion. The active protocol document is updated after the run to link these results; its frozen pre-evaluation snapshot remains unchanged. No policy, feature, planner, reference, budget, condition or seed was changed after formal outcomes were seen. Every compressed trace binds protocol and source identities and includes both official partial observations, actual rewards/done flags, canonical versions, input context, routes/seeds, raw support witnesses, coverage and work receipts.

Legacy parity is executable at ../dependency-baseline-parity-v1/replay_legacy.py. Current no-mask code reproduces every action, non-time decision/query/selected-ID/route/work field, added version and final archive from 56 frozen development episodes /49,612 recorded observation steps. Fifty component/legacy tests plus the independent reviewer counterexample suite check the information boundary and structural cases. Independent official replay audit is recorded separately once complete; absence of an audit result must not be interpreted as a pass.

This is a hand-written observation-aware symbolic controller with exact egomotion and symbolic 7x7 MiniGrid perception. It does not establish learned perception, robust robot localization, the separate Somna dreaming/consolidation modules, biological mechanisms, algorithmic novelty, industry validation or hierarchy necessity. A 96-fact output limit leaves the full canonical archive and observed graph inside the reader. No GPU/model training, paid cloud service or public release was used.
