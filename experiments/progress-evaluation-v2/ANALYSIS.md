# Progress-aware retrieval repair: fixed-cohort result

The repair finishes all 24 episodes with ZHA-seeded retrieval; 23 need no full-bank nomination and one uses 16 explicitly metered recovery reads. Matched exact requery+widening finishes 24/24 without that fallback. This is a useful closed-loop liveness repair, not evidence that ZHA beats exact retrieval.

## Complete policy cohort and transport recovery

The decision policies were frozen before their first exposure to seeds 3001–3006. The first 168-case run completed the environment executions but rejected one long control trace at the unchanged 128MiB transport limit, leaving 167 original artifacts and no complete result report. That failed version remains at ../progress-evaluation-v1 with INCOMPLETE_RUN.json. No original raw trace survived for the missing control; its outcome is established only by reexecution.

Only serialization changed: exact actual route events and index layouts are content-addressed and referenced instead of copied. Every frame still records the real observation, action, query, progress state and cumulative work; no model computation is cached or skipped. The SAME sealed policy/cohort was repeated as this v2 dataset, not replaced by easier seeds or counted as a new untouched cohort. SERIALIZATION_PARITY.json verifies every retained observation/action/non-time decision/query/numerical route/selected-ID/work/archive/result across 167 episodes and 25,320 steps exactly. Protected policy/core/controller/lock bytes are identical. The missing 168th has no claimed original parity.

All 168 final artifacts are present: 0 exceptions, 0 external cutoffs, 13 official truncations. The largest expanded trace is 77,310,857 bytes, safely under 134,217,728. TRACE_SIZE_CHECK.json records each actual expanded size. No 192-output-budget condition was run; candidate widening is distinct from the raw planner budget.

| Method | Memory | MultiRoom | DoorKey | KeyCorridor | Total | Full-bank nomination use |
|---|---:|---:|---:|---:|---:|---|
| bundle_zha | 6/6 | 6/6 | 5/6 | 2/6 | 19/24 | 0 episodes / 0 reads |
| bundle_exact | 6/6 | 6/6 | 4/6 | 2/6 | 18/24 | 0 episodes / 0 reads |
| graph | 6/6 | 6/6 | 6/6 | 5/6 | 23/24 | Every read (ordinary graph control) |
| progress_zha | 6/6 | 6/6 | 6/6 | 6/6 | 24/24 | 1 episode / 16 reads |
| progress_exact | 6/6 | 6/6 | 6/6 | 6/6 | 24/24 | 0 episodes / 0 reads |
| cues_zha | 6/6 | 6/6 | 5/6 | 6/6 | 23/24 | 0 episodes / 0 reads |
| cues_exact | 6/6 | 6/6 | 6/6 | 6/6 | 24/24 | 0 episodes / 0 reads |

## What actually unstuck the agent

In the already exposed KeyCorridor 2001 failure, step 90 had seen no new information since 66 and was rotating at (-6,-3). Its observed bank contained 229 current heads, but its 96 selected originals omitted the only reachable true frontier, original 62 at (2,5). No matching key had yet been observed. The fixed-cue controller eventually truncated at 1080.

The repaired trace first changes directional cues at 74; the wanted original is still absent. At 82, joint requery plus candidate widening to 192 retrieves original 62 and the unchanged planner targets (2,5). The run finishes in 143 actions without full-bank nomination. This demonstrates actual changed retrieval/use of previously observed evidence. It does not isolate directional cues from wider candidates as independent causes.

For the fixed policy cohort, no-full-bank-recovery requery+widening (`cues_zha`) reaches 23/24 versus old ZHA bundles 19/24. Its remaining DoorKey 3003 case is retained as a 2560-step truncation; `progress_zha` recovers it using 16 full-bank nomination reads and succeeds. Matched `cues_exact` already reaches 24/24, so hierarchy superiority is not supported. Ordinary graph control fails KeyCorridor 3002 and reaches 23/24; this control is not an optimal planner or universal ceiling.

## Costs and information boundary

All variants retain the previous full-observed-head graph closure/BFS and 512-byte known-only coverage allowance. “No graph fallback” means no switch to ALL observed heads for endpoint nomination; it never means graph-free computation or absence of full-head scans. Approximate p=1 candidate passes are separately charged; no sparse-work claim follows from a fallback-free episode.

The output stays ≤96 immutable raw facts plus the current observation and declared coverage. Requery/widening uses only canonical observed-payload novelty and a 24-pose window; door states returning from history do not falsely count as new knowledge. Full-bank nomination starts only after the declared stall conditions and remains explicit. The reader sees no simulator map, hidden position, future object/key or reward label. The common symbolic planner and original numerical core are unchanged.

| Method | Executed actions | Policy seconds | Extra requery reads | Widened reads | Triggered full-bank nomination reads |
|---|---:|---:|---:|---:|---:|
| bundle_zha | 7690 | 18.529339 | 0 | 0 | 0 |
| bundle_exact | 10171 | 12.328635 | 0 | 0 | 0 |
| graph | 2247 | 3.639857 | 0 | 0 | 0 |
| progress_zha | 1322 | 4.731991 | 101 | 67 | 16 |
| progress_exact | 1337 | 2.075969 | 136 | 96 | 0 |
| cues_zha | 3776 | 17.360490 | 2582 | 2548 | 0 |
| cues_exact | 1337 | 2.170171 | 136 | 96 | 0 |

Policy time includes numerical retrieval, full observed-graph support, progress bookkeeping and in-memory trace construction. Episode time also includes environment work and wire compaction. Two CPU workers with one Torch thread each execute float64. Different trajectories and failure horizons make total seconds unequal-work comparisons; these are not native-attention speedups. Index-owned tensor bytes exclude Python archive/graph/progress/RSS costs.

## Inspectable evidence and remaining limits

Each new route is resolved through routing_events, then its snapshot_id through routing_snapshots. Actual affine/entropy branch scores, p attempts, selected originals, exact span/index order and labeled cue vectors remain present once. Event deduplication reduces retained JSON only: repeated computations and every per-read work occurrence remain counted. Graph-only nomination frames have no fabricated numerical routes and mark cues unused.

Sixteen new tests cover bounded stages, hard recovery, repeated state/corrections, actual observed-only recovery, truthful mask allowance and compact identity/ownership. Together with the unchanged dependency/MiniGrid tests, 66 focused tests pass; Ruff and strict mypy pass. The independently reconstructed development 56 cohort passes all official actions, progress rules, numerical routing, layouts and cost checks. Formal independent audit is a separate gate recorded by the root/reviewer; component success alone is not that result.

This is a small fixed-cohort hand-written symbolic MiniGrid controller with exact egomotion. The joint cue+widening heuristic and explicit source recovery are not biological dreaming, learned salience, general navigation guarantees, industrial validation or algorithmic novelty. The successful wrapper includes ordinary observed-graph work; it is not a standalone ZHA-memory product or a total-memory reduction claim.
