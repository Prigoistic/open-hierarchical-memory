# Progress repairs: fresh comparison

14 November 2026. Source, protocol and checkpoint were frozen before this comparison. The source snapshot preserves the evaluated implementation; subsequent type-only/import-order cleanup does not alter policy behavior.

| Condition | Solved | Actions | Scan-stall decisions |
| --- | ---: | ---: | ---: |
| Original connected ZHA | 22/24 | 1597 | 216 |
| Repaired ZHA | 22/24 | 1615 | 218 |
| Repaired exact | 22/24 | 1640 | 18 |
| Repaired graph | 22/24 | 1665 | 19 |

Four official MiniGrid families, six fresh seeds25001–25006, four conditions:96 runs over24 distinct initial world/pose/mission identities. All8 unsuccessful runs reach the external256-action cutoff; no runtime errors. Each condition solves6/6 Key Corridor,6/6 MultiRoom and6/6 Memory cases, and4/6 DoorKey cases. Failing DoorKey identities differ across controls. No cohort-wide success gain, speed advantage or ZHA-specific benefit is established.

The independent audit replays all96 official action sequences and checks6,517 source-bound decisions,1,060 routes,44 sampled scalar numerical routes and432 connector reads. This is not a proof of policy optimality or general semantic correctness.

## Repair mechanism

Occupied-hand pickup now seeks a reachable observed drop site; the reader explicitly admits supporting facts. When an otherwise valid path cannot fit the current view's64-fact active budget or16-fact cold-admission limit, the reader can admit a contiguous path prefix and identify its admitted endpoint as a waypoint. The planner uses only returned facts and current observations. Missing keys, locked doors, stale corrections and numerical budget failures cannot be bypassed through a waypoint.

The connector may inspect the full observed archive, and graph drop-site nomination and prefix checks are extra charged work. This is a symbolic planning/interface repair, not a learned forgetting policy, task-level consolidation or biological dreaming. The current observations continue to count toward64 active facts. The archive/cache/index are additional storage.

The original failing seeds23003/23005 are separate exposed development diagnostics: the original policy fails at256 actions and the repaired policy solves in99/151. See the separate `task-support-repair-diagnostics-v1` records. Those outcomes are not included in this fresh cohort.

All raw results, failures, protocol, references and source snapshots are retained. These cases are now exposed; further tuning needs a new evaluation cohort.

Reproduce with `uv run --locked --extra research --extra benchmarks python -m research.task_memory.run_repairs --output experiments/task-support-local-repairs`, then `uv run --locked --extra research --extra benchmarks python -m scripts.audit_task_support --results experiments/task-support-local-repairs`.
