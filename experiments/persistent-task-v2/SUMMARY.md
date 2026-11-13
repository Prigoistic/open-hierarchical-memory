# Persistent task memory v2

13 November 2026. CPU float64 research adapter with the same observation-only symbolic planner. These are integration results, not a trained language model, biological dreaming or a ZHA speed claim.

| Condition | Solved | Actions | Errors | Original pairs | Summary dots | Rerank pairs |
| --- | --- | --- | --- | --- | --- | --- |
|no_recovery|8/8|395|0|0|0|0|
|always_fixed_zha|8/8|389|0|63602|240872|97672|
|fixed_zha|8/8|393|0|712|2296|902|
|random_zha|8/8|393|0|708|2296|942|
|fitted_zha|8/8|393|0|712|2296|910|
|exact|8/8|393|0|1086|0|0|

Four official MiniGrid environments, seeds 9001 and 9002, action cap 256, active capacity 96 including current observations, recovery cap 16, reference count 8, chunk4/depth3, p=0.8. Archive/key/index memory and graph work are additional costs. Per-run totals reflect different trajectories and are not a matched-latency benchmark.

## Reference fitting

48 training prefixes, 24 validation, 47 comparison; optimizer step 40 selected on validation only. Train seeds 0/1, validation 2. Corpus and checkpoints are saved. The eight 30-dimensional reference vectors are actual optimized parameters; structured task features remain hand-designed.

| References | Mean pooled KL | Mean retained dense mass | Mean selected keys |
| --- | --- | --- | --- |
|fixed|0.005718874|0.775911|63.229|
|random|0.000561452|0.768786|61.705|
|fitted|0.004354208|0.774381|63.076|

These offline dense-teacher computations are additional audit work. Lower fitted KL than fixed does not imply higher mass retention or task success; the random control has lower KL than either. Local top-p is not a global dense-mass guarantee.

## Delayed-clue diagnostic

A separate authored sequence retires a key/path, closes and reopens its archive, asks for the old clue, and later corrects the key colour. Every recovery condition returns the original key with observed support; no recovery cannot. All originals remain unchanged, superseded keys are excluded and tested controller state restores. This diagnostic is not a held-out maze benchmark.

## Interpretation and provenance

This is a development refinement of exposed v1 seeds. All 48 episodes solve, including the always-recover ZHA control. The result establishes operation on these cases; it does not isolate gating as the cause of success recovery, show superiority over exact/no-recovery or validate unseen policy generalization.

The always-recover control executes many more archive reads than the gated controls. The gate is an explicit coordinate-coverage/pose heuristic, not learned semantic salience. Exact and gated ZHA have identical aggregate actions; index construction, summary scoring, reranking and graph work remain separately counted.

The manifest freezes source/protocol identities before execution. `report.json` contains all outcomes and costs; `*.json.gz` contains source traces, `fitting.json`/`routing-quality.json` record fitting and offline audits, and `INDEPENDENT_AUDIT*.json` record independent check scope. The audit checks official action replay, source/hot-cold lineage, top-p ownership and selected scalar numerical cases; it does not reproduce the optimization trajectory or certify performance.

Mutable archives remain local under ignored `archives/`. Reusing a directory is refused. See `../../docs/PERSISTENT_TASK_MEMORY.md` for the API, exact commands, validation and remaining gates.
