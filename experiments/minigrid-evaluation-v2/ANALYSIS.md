# Frozen MiniGrid evaluation: result and limits

This is the first untouched-seed evaluation after one development-only, separately labeled adaptive wrapper. Seeds 1001/1002/1003 were fixed before implementation. All 84 episodes, including 56 official truncations, are retained. There were no recorded exceptions or external cutoffs. The source/lock hashes still matched the frozen manifest after execution; see SOURCE_FREEZE_CHECK.json. No policy, feature, reference or controller changes were made after seeing these outcomes.

| Reader | Successes over four tasks |
|---|---:|
| zha | 1/12 |
| zha_adaptive | 3/12 |
| exact | 5/12 |
| recency | 4/12 |
| fifo | 3/12 |
| none | 0/12 |
| full | 12/12 |

Adaptive routing repaired the known development underfill, but the broader held-out benefit did not materialize. It solved Memory 3/3, then failed MultiRoom 0/3 where exact solved 2/3. Every 96-fact bounded reader failed DoorKey and KeyCorridor. Full observed memory solved 12/12 with the identical controller and observations; none solved 0/12. These are three seeds per task, not a broad benchmark ranking.

Memory success is especially limited evidence: adaptive routed the entire observed candidate bank on all 39 Memory actions (mean 49.05 facts), despite making no p=1 call there. The cap exceeded the small bank, so that success does not show sparse selection is necessary. Five actual p=1 full-candidate fallbacks occurred elsewhere (MultiRoom 3, DoorKey 1, KeyCorridor 1); every extra pass and original attention read is charged.

| Task | Adaptive returned facts, mean | Full-candidate actions |
|---|---:|---:|
| MiniGrid-MemoryS17Random-v0 | 49.05 | 39/39 |
| MiniGrid-MultiRoom-N6-v0 | 91.85 | 60/360 |
| MiniGrid-DoorKey-16x16-v0 | 95.90 | 43/7680 |
| MiniGrid-KeyCorridorS6R3-v0 | 95.75 | 40/3240 |

The filled-slot stopping rule guarantees candidate count, not a useful connected planning map or the same top 96 as full-bank exact search. On formal MultiRoom seeds 1001/1002/1003, the first action divergences from exact occur at steps 17/21/26 with identical allowed histories and tracked poses, while both return 96 facts. READ_DIAGNOSTICS.json preserves those complete decision records. This explains a representation/retrieval interface limitation without changing the policy after evaluation.

| Task | Reader | Total policy seconds | Policy ms/action | Hierarchy passes | p=1 passes |
|---|---|---:|---:|---:|---:|
| MiniGrid-MemoryS17Random-v0 | zha | 1.581473 | 0.545 | 2902 | 0 |
| MiniGrid-MemoryS17Random-v0 | zha_adaptive | 0.066778 | 1.712 | 136 | 0 |
| MiniGrid-MemoryS17Random-v0 | exact | 0.015059 | 0.386 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | zha | 0.169644 | 0.471 | 360 | 0 |
| MiniGrid-MultiRoom-N6-v0 | zha_adaptive | 0.621565 | 1.727 | 1011 | 3 |
| MiniGrid-MultiRoom-N6-v0 | exact | 0.171348 | 0.729 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | zha | 4.906450 | 0.639 | 7680 | 0 |
| MiniGrid-DoorKey-16x16-v0 | zha_adaptive | 11.149217 | 1.452 | 17982 | 1 |
| MiniGrid-DoorKey-16x16-v0 | exact | 5.350199 | 0.697 | 0 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | zha | 2.408649 | 0.743 | 3240 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | zha_adaptive | 6.055932 | 1.869 | 9755 | 1 |
| MiniGrid-KeyCorridorS6R3-v0 | exact | 2.190871 | 0.676 | 0 | 0 |

Timing includes reconstruction/index rebuilds and common planning. Total times cover unequal action counts when one method truncates, so they are not matched-compute quality comparisons. The per-action observations likewise have different trajectories. Execution used CPU float64, two concurrent workers and one Torch thread per worker. Adaptive overhead was higher than exact in each task; no speedup claim is supported. Report.json retains raw summary/reference/original/rerank counts and owned index tensor bytes (not total RSS).

The benchmark evaluates fact retrieval inside an observation-only, hand-written symbolic planner. It does not run the separate learned Somna dynamics, dreaming, reversible forgetting or offline consolidation modules. It does not establish neural learning, ZHA necessity, algorithmic novelty or production/industry readiness. A task-relevant hierarchical representation and better memory-to-planning interface remain research work, rather than results already delivered by this cohort.

Independent replay/provenance audit passed all 84 traces: 75,520 official transitions, 10,321 observed fact versions, 89,170 numerical query routes and 43,066 routing passes, including all five p=1 fallbacks. See INDEPENDENT_AUDIT.json. This audit checks recorded evidence and cost accounting; the separate controller isolation tests enforce the policy information boundary.
