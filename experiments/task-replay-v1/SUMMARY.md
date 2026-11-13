# Observed task routing replay, v1

13 November 2026. Frozen experience → offline parameter replay → fresh-task retest. All scientific source/protocol files were fixed before collection. The existing dashboard default checkpoint and all canonical baseline observations remain unchanged.

## Measured outcome

Replay updates the eight 30-dimensional reference vectors and improves the tested pooled-KL objective, but does not improve task success on this cohort. All 64-slot conditions solve 11/16; unchanged/exact 96-slot controls solve 13/16. This is not a hierarchy or replay win.

| Condition | Active/support capacity | Solved | Actions | Runtime errors |
| --- | --- | --- | --- | --- |
| parent | 64 | 11/16 | 1724 | 0 |
| random | 64 | 11/16 | 1724 | 0 |
| uniform-7 | 64 | 11/16 | 1724 | 0 |
| uniform-19 | 64 | 11/16 | 1724 | 0 |
| uniform-31 | 64 | 11/16 | 1724 | 0 |
| priority-7 | 64 | 11/16 | 1724 | 0 |
| priority-19 | 64 | 11/16 | 1724 | 0 |
| priority-31 | 64 | 11/16 | 1724 | 0 |
| recent-7 | 64 | 11/16 | 1724 | 0 |
| recent-19 | 64 | 11/16 | 1724 | 0 |
| recent-31 | 64 | 11/16 | 1724 | 0 |
| exact | 64 | 11/16 | 1724 | 0 |
| no_recovery | 64 | 11/16 | 1714 | 0 |
| parent-cap96 | 96 | 13/16 | 1313 | 0 |
| exact-cap96 | 96 | 13/16 | 1313 | 0 |

All 71 failures are retained external 256-action cutoffs; there are no hidden exceptions or official truncations. Four official MiniGrid environments use fresh seeds 19001–19004. Three optimizer seeds reuse those same 16 task cases; they are not 48 independent layouts. Different RNG seeds do not guarantee distinct underlying maze geometry, and no significance claim is made.

## Learning and query quality

| References | Mean fresh-prefix pooled KL | Retained dense mass | Selected keys |
| --- | --- | --- | --- |
| parent | 0.004539914 | 0.783937 | 54.000 |
| random | 0.000554327 | 0.778046 | 52.926 |
| uniform-7 | 0.004203352 | 0.783995 | 53.979 |
| uniform-19 | 0.004191973 | 0.783995 | 53.979 |
| uniform-31 | 0.004102020 | 0.783995 | 53.979 |
| priority-7 | 0.003800330 | 0.783376 | 53.916 |
| priority-19 | 0.003903405 | 0.783376 | 53.916 |
| priority-31 | 0.003889120 | 0.783376 | 53.916 |
| recent-7 | 0.004139508 | 0.783995 | 53.979 |
| recent-19 | 0.004170879 | 0.783995 | 53.979 |
| recent-31 | 0.004174719 | 0.783995 | 53.979 |

The common query corpus contains 190 query cases collected by the unchanged parent policy. It is separate from fitting and checkpoint selection, but need not cover every child-policy state. Dense teacher mass is additional offline work. Local top-p thresholds do not guarantee global retained mass.

- uniform: mean KL 8.24% below the unchanged parent across three optimizer seeds.
- priority: mean KL 14.88% below the unchanged parent across three optimizer seeds.
- recent: mean KL 8.33% below the unchanged parent across three optimizer seeds.

Frozen random references have substantially lower KL than the parent or replay models, despite slightly lower retained mass and the same task solve rate. The error-prioritized schedule improves KL more than uniform replay, but consumes additional full-pool priority scoring and does not improve task success. The study does not establish an end-to-end speed or compute advantage.

| Replay run | Selected update | Initial old/new validation mean | Selected mean | Gradient losses | Priority losses | Dense teacher pairs |
| --- | --- | --- | --- | --- | --- | --- |
| uniform-7 | 64 | 0.004105769 | 0.003746648 | 64 | 0 | 108557 |
| uniform-19 | 64 | 0.004105769 | 0.003756734 | 64 | 0 | 108846 |
| uniform-31 | 64 | 0.004105769 | 0.003631734 | 64 | 0 | 107662 |
| priority-7 | 64 | 0.004105769 | 0.003369651 | 64 | 752 | 296519 |
| priority-19 | 64 | 0.004105769 | 0.003476443 | 64 | 752 | 298112 |
| priority-31 | 64 | 0.004105769 | 0.003444473 | 64 | 752 | 297510 |
| recent-7 | 64 | 0.004105769 | 0.003714554 | 64 | 0 | 108483 |
| recent-19 | 64 | 0.004105769 | 0.003737318 | 64 | 0 | 107574 |
| recent-31 | 64 | 0.004105769 | 0.003749367 | 64 | 0 | 109017 |

Each schedule performs 64 actual clipped-SGD updates, starting from the same fitted parent, with a new independent RNG. Initial weights are eligible for validation selection. Every run selected 64 and changed the selected reference values. This changes routing parameters only. There is no factual-memory writeback, world-model learning or biological dreaming. Equal update counts do not imply equal compute.

## Data and audit

Retained corpus samples by role: `{'anchor': 48, 'wake': 46, 'validation_old': 24, 'validation_new': 20, 'comparison': 84}`. Deterministic numerical duplicate removals: `{'anchor': 0, 'wake': 2, 'validation_old': 0, 'validation_new': 4, 'comparison': 12}`. Old anchors/validation come from the v2 observed-prefix corpus; their graph-teacher origin is explicit. New wake/validation worlds use the actual parent persistent policy, seeds 17001/17002 and 17003 respectively. Old validation is an exposed retention check. It is not fresh unseen evidence.

The independent audit passed 576 recorded update-algebra/work/sampling checks, 54 sampled smooth finite-difference gradient coordinates (none skipped), 240 official task replays, 25,028 source-bound decisions, 180 independently recomputed route cases and 2,090 dense-mass cases. It also reconstructs corpus provenance from the original observed prefixes. This is a sampled numerical audit, not an exhaustive gradient or semantic-correctness proof.

Failed initial direct-file invocation of the auditor was an import-path issue; the supported entry point is `python -m scripts.audit_task_replay`. No scientific data or fitting code was changed after the run. The frozen auditor is the same source used for the successful module invocation.

## Inspect and reproduce

Open the existing dashboard, Run & query → Saved study → Routing replay · fresh seed study. Select a method/optimizer seed and task seed. The training curve is recorded learning on other wake episodes; its points are never projected as memories in the retest maze. This study is read only. The default Persistent memory study still supports fresh live solves.

```sh
uv run --locked --extra benchmarks --extra research python -m research.run_task_replay --output experiments/task-replay-local
uv run --locked --extra benchmarks --extra research python -m scripts.audit_task_replay --results experiments/task-replay-local
```

Use a new output directory. The runner never overwrites prior evidence. Mutable SQLite archives are local under ignored `archives/`; frozen checkpoints, source snapshots, training traces and all outcomes are included. See `../../docs/TASK_REPLAY.md` for the predeclared mechanism and boundaries.

The next discriminating work is diagnosing unavailable path/prerequisite support and query-memory usefulness under matched budgets. The exact-reader result gives no evidence that another routing-KL improvement alone will fix these task failures. The larger workspace/support-budget control demonstrates headroom on two cases, without isolating the precise cause of the remaining failures.
