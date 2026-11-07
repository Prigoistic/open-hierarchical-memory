# Somna: retrieval and offline consolidation

7 November 2026. Working project name, not a cleared product name. Existing repository and Python package remain `open-hierarchical-memory` / `open_hierarchical_memory`. This is an independent research project; ZHA belongs to its paper's authors.

## First implemented slice

The [spatial diagnostic](../experiments/somna-spatial-v2/SUMMARY.md) connects the actual numerical attention index to observed spatial episodes and persistent tabular updates. Its [inspector](../experiments/somna-spatial-v2/inspector.html) shows recorded values, selected original episodes and hierarchy decisions. It does not replace the installed numerical core or the separately documented lexical lifecycle experiment.

Each seeded 11 by 11 maze contains 49 accessible states and 192 observed state/action transitions. All transitions are collected before the comparison. A single order-dependent wake pass initializes a Q table. Identical frozen episodes and wake values are forked into no-update, uniform replay and exhaustive residual-priority replay conditions. Uniform and priority perform 256 numerical reads and Bellman updates each. Sixteen starting positions are tested afterward in the same known map. Three separately generated fixed evaluation mazes are distinct from development seed7; these are still authored diagnostic worlds, not a public benchmark or new-layout transfer test.

The archive contains only observed tuples `(state, action, successor, reward, evidence_id)`. No future answers or evaluation starts enter the replay API. Original tuples are frozen and hashed. The offline phase accepts the episode bank and wake checkpoint, with no simulator handle. Reward is one on entering the known terminal goal and zero otherwise. This is a fully observed symbolic task; no perceptual model has been trained.

## Equations and semantics

Keys concatenate a one-hot state with a one-hot action, both scaled by16. Values concatenate a one-hot successor and observed reward. A mandatory zero sink occupies raw key zero. ZHA selects raw keys through the existing affine summary hierarchy, with chunk8, depth2 and p=.8. The research adapter supplies one untrained state-basis reference per state. Its large reference cost is part of the result, not hidden behind sparse leaf counts.

For selected original indices S, the actual read is `softmax(q K_S^T / sqrt(d)) V_S`. There is no exact-record fallback or lookup after routing. The returned value mixture defines predicted successor probabilities and expected reward. A replay update overwrites one table entry with:

`Q(s,a) <- expected_reward + .95 * sum_x predicted_probability(x) * max_b Q(x,b)`

The goal continuation is explicitly zero. The zero sink contributes no successor/reward; probabilities can therefore be slightly subnormalized. CPU float64 values are retained. For action decisions and scheduler ties only, candidates within1e-10 of the largest value are tied in deterministic action/archive order. This declared decision band prevents negligible dense-softmax spill from changing a nominally tied policy. Early development exposed exactly that false appearance of a sparse advantage; the fixed protocol removes it. It is not a change to attention arithmetic.

Uniform replay samples observed state/action queries with a fixed RNG. Priority recomputes absolute Bellman residuals over **every exact observed transition** before each query, then reads its chosen query through the configured reader. This is an expensive residual scheduler, not an efficient prioritized-sweeping implementation. It already accesses exact transition identities, so the task is not a retrieval bottleneck. A dictionary lookup and ordinary graph planner are stronger simple alternatives. The independent audit confirms every test start is graph-reachable; the exact planner ceiling is48/48. No novelty or necessity of ZHA follows from reaching that ceiling.

## Results and interpretation

Across three fixed evaluation mazes, wake/no-update and uniform replay solve1/48 starts; residual-priority solves48/48 with either dense or ZHA reads. This is propagation of an already observed terminal reward through an already observed graph. Uniform's failure at this budget is preserved. It does not show new knowledge, dream insight, unseen affordances or biological consolidation.

The sparse reader includes the exact observed episode on576/576 audited queries and selects9 of193 raw keys per query. Maximum successor-probability disagreement with dense is below2.7e-14 on those queries. These favorable identity results depend on the idealized basis encoding. Each ZHA read nevertheless scores11 summary nodes across49 reference channels:539 summary dot products plus9 raw attention pairs versus193 raw pairs for dense. On this run ZHA also takes longer. Sparse leaves do not establish less total computation.

Priority performs147,456 extra observed-graph residual comparisons over the three evaluation worlds. Equal read/update counts are **not equal compute**. Index build, owned tensor bytes, scheduler work, query times and separate dense audit work are recorded. Timing is descriptive of this small local CPU run, not a benchmark speed claim.

Only Q values and representation/archive identities are persisted in inert JSON checkpoints; replay frames and temporary reads are omitted. All24 checkpoint round trips preserve values/evaluation, including one verified fresh interpreter restart. This is persistent **tabular** consolidation. There is no neural parameter training in this slice. Canonical observations are not deleted, decayed or rewritten; forgetting still belongs to the earlier separate lifecycle prototype.

## Prior art and theory grounding

- [ZHA v2](https://arxiv.org/html/2610.42112v2): numerical hierarchical summaries and query-dependent raw-key selection. This adapter uses the already tested no-positional-encoding subset; it is not a full paper reproduction, transformer conversion or certified omitted-mass method. The paper's distinction between sparse per-query reads and retaining the full KV bank is directly relevant to separating deactivation from deletion.
- [Sutton, Dyna (1991)](https://doi.org/10.1145/122344.122377): integrating learning and planning from an environment model predates this project. Our symbolic replay belongs to that established family.
- [Moore and Atkeson, Prioritized Sweeping (1993)](https://publications.ri.cmu.edu/prioritized-sweeping-reinforcement-learning-with-less-data-and-less-real-time): prioritized model-based updates are established prior art. Our exhaustive residual scans are intentionally simpler and more costly than predecessor-queue sweeping.
- [Miller, Lundqvist and Bastos, Working Memory 2.0 (2018)](https://bpb-us-e1.wpmucdn.com/sites.mit.edu/dist/7/1739/files/2025/06/Miller-Lundqvist-Bastos-WM-20.pdf): motivates separating active content, temporary traces and control. It does not imply that this Q table or scheduler replicates brain activity or sleep.
- [DreamerV3](https://danijar.com/project/dreamerv3/): learned world models and imagined policy improvement are strong existing approaches. This slice deliberately has no learned latent dynamics, visual decoder or imagined observations, and should not be described as a Dreamer reproduction.

The [earlier research synthesis](WORKING_MEMORY_2_AND_LATENT_DREAMING.md) keeps biological observations, operational hypotheses and future learned-latent experiments separate.

## Claims ledger

| Claim | Status |
| --- | --- |
| Numerical ZHA output actually supplies offline targets | Implemented and independently audited |
| Durable values survive discarding temporary replay state | Tested local JSON checkpoint round trips and fresh process |
| Priority beats uniform at the fixed update budget | Measured on three fixed known maps; more scheduler compute |
| ZHA is useful or faster than direct/dense lookup here | Not supported; this task permits direct keys and sparse work is worse |
| New forgetting, learned visual dreaming or neural consolidation | Not implemented |
| Novel algorithm, biological replication or public performance result | Not established |

## Next discriminating experiment

The next task must remove the direct-key shortcut before optimizing retrieval. Use ambiguous partial spatial cues with many observed episodes per cue, context-dependent outcomes and a large dormant archive. A query must lack a unique state/action identifier. Freeze one encoder, one action-conditioned dynamics checkpoint and one experience bank across fork comparisons. Keep contradictory versions and predicted rollouts explicitly labeled; never turn imagined transitions into observations.

First compare dense attention, direct keyed lookup where possible, conventional exact/ANN search and the hierarchy on the **same representation**. Measure correct evidence recovery, false-neighbor rate, rare-clue retention, construction/rebuild/storage and total work, not only selected leaves. Fit references on training worlds; select settings on validation worlds before sealed evaluation worlds. Random references remain a necessary control. A hierarchy that loses or costs more is a negative result to keep.

Only after the read mechanism passes that gate, compare uniform replay, residual/priority replay, rare-coverage mixing and retrieval-conditioned nonverbal rollout consolidation under matched measured budgets. Fixed experience, no new simulator calls during strict offline processing, frozen encoder/dynamics, uncertainty/provenance checks and a no-durable-update ablation are required. Test genuinely new goals/layouts and old-task retention, not just new starts on a known map. The candidate contribution is a falsifiable combination of recoverable dormant evidence, representation-aware maintenance and auditable offline improvement; whether it adds value over established baselines remains open.

## Reproduce and verify

```sh
uv run --locked --extra research python -m pytest -q tests/test_somna_spatial.py tests/test_somna_audit.py
uv run --locked --extra research python -m mypy --strict research/somna_spatial.py research/run_somna_spatial.py scripts/audit_somna_spatial.py
uv run --locked --extra research python -m research.run_somna_spatial --output experiments/somna-spatial-new
uv run --locked --extra research python scripts/audit_somna_spatial.py --results experiments/somna-spatial-new
uv run --locked --extra research python scripts/verify.py --profile core
```

The runner refuses existing destinations and records source/protocol hashes, frozen source copies, losslessly compressed raw query records and checkpoints. V1 is retained as the initial desktop viewer; v2 reruns the identical numerical protocol with a readable stacked mobile canvas. The audit validates each run against its own preserved source snapshot. The independent auditor imports no production numerical code. It recomputes selected softmax/Bellman updates, scheduling, frame values, graph reachability, final policies and work from raw records. Its numerical agreement is tested over this declared fixture domain, not a general proof. No network is used by the experiment. A Linux CPU run uses the same lock and commands; GPU execution remains a separately validated backend gate.
