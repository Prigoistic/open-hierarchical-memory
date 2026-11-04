# Fixed-data training-duration diagnosis

This is a training/validation diagnosis, not a new model-quality test. The same 8,192 unique training tokens, C16/R2/depth2, three initializations, optimizer/lr and validation selection rule are reused. Only the maximum step budget changes: 100/300/1,000. Each arm restarts from its seed; longer training repeats the data. The original 100-step checkpoints reproduce exactly.

The loader refuses test activation requests. No old or fresh test activation is evaluated. Validation both selects checkpoints and supplies the diagnostic metrics, so favorable numbers are not new generalization evidence.

## Validation outcomes at the fixed p=.90 threshold

Errors and work are pooled across the three seeds' 576 validation query/head cases. These dependent observations come from two validation books. KL is the mean selected-checkpoint KL across seeds. Raw records preserve all three original thresholds, per-seed and per-book behavior.

| References / maximum budget | Selected steps | Validation KL | Mean relative error | p95 relative error | Vector work / dense | Selected keys |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| initial_query_samples | — | — | 4.28% | 14.25% | 0.394 | 33.95% |
| random_gaussian | — | — | 4.08% | 10.87% | 0.399 | 34.36% |
| Trained / 100 | 100, 100, 100 | 0.37148 | 4.13% | 13.69% | 0.398 | 34.35% |
| Trained / 300 | 300, 300, 300 | 0.31203 | 3.91% | 10.35% | 0.402 | 34.67% |
| Trained / 1000 | 580, 810, 450 | 0.30806 | 3.82% | 10.48% | 0.401 | 34.63% |

Lower KL is a surrogate improvement. Interpret executed output error and actual work together; identical p does not match cost, and these three budgets do not establish convergence. Data coverage, alternative losses and whole-model effects were not changed or tested.

## Integrity and artifacts

The [audit](audit.json) checks source/trace-record/checkpoint identities, validation checkpoint selection and all 45 aggregate rows from 8,640 raw validation records. The run asserts exact reproduction of the original 100-step references. The training documents are disjoint from validation; [protocol and boundaries](../../docs/TRAINING_DURATION.md) were committed before execution.

[Full report and histories](report.json), [raw validation queries](validation-queries.jsonl.gz), [aggregate outcomes](aggregate.json), [protocol snapshot](protocol.json), [run log](run.log). Small reference checkpoints are retained beside the report. No new backbone model or raw corpus text is bundled.

The next training study must separate duration from unique-data coverage and reserve a new sealed test cohort before a generalization claim. This validation diagnosis does not authorize choosing a favorable test result or treating a layer-error budget as answer correctness.
