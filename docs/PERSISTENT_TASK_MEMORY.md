# Persistent task-memory integration: first slice

13 November 2026. Implementation contract, fixed before the first comparison.

The first slice connects fitted task references, a versioned observed-fact archive, a bounded active workspace and explicit archive recovery to the existing observation-only planner. It is a research adapter, not a replacement for the installed numerical core or the frozen baseline policies.

## Review findings and decisions

- The baseline dependency reader constructs support from every observed head. The new adapter must pass only current observations and active/explicitly recovered historical facts to graph construction. Known-only coverage may remain a separately declared 512-byte channel; it cannot add traversable cells.
- Current relative coordinates are meaningful only inside their declared world/frame/reset context. A context is a versioned namespace, not a task answer or retrieval target. A new simulator reset gets a new namespace. Persistence alone does not establish map transfer between resets/layouts.
- Original observations and correction chains remain immutable. Decay changes active membership, never attention mathematics or canonical payloads. Superseded heads cannot return or train a router.
- The archive index may retain growing key tensors and summaries. Its build reads and owned tensor bytes must be counted. A bounded active set is not a bound on total storage/RSS. The first adapter rebuilds immutable indexes after observed-head changes; incremental updates are a later optimisation.
- References are fitted only on observed training prefixes, selected on disjoint validation contexts and frozen for evaluation. References, features and geometry are checkpoint identities. Loading incompatible coordinates/checkpoints must fail.
- No sleep, neural consolidation or imagined evidence is added in this slice. Those require a declared learned target and a separate fork experiment.

## Deliverables and checks

1. Task-reference fitting/checkpoint API using existing pooled chunk KL, with split/provenance validation and initial-checkpoint eligibility.
2. Single-writer persistent observed-fact store with current heads, active membership, logical age and usage metadata. Restore validates checksums/configuration and preserves corrections.
3. Context-bound reader: bounded active memory, explicit archive ZHA/exact recovery, support packing limited to available facts, metered index/retrieval/graph work and typed resource failures.
4. Reproducible command-line comparison over real MiniGrid observations, plus a delayed-clue/correction/restart diagnostic. Save all failures, per-read source receipts and training/evaluation identities. Original baseline artifacts remain untouched.

Acceptance checks include immutable originals, atomic failed writes, context/future isolation, actual source mapping, no cold payload in graph support without recorded recovery, active/return caps, zero false-use reinforcement during maintenance, restart equivalence, reference invalidation and exact-reader controls. Existing tests and independent numerical oracles remain separate.


## Development refinement after v1

The preserved v1 run exposed a regression with unconditional archive admission: no recovery and exact solved 8/8, while fixed/random/fitted ZHA solved 6/8. References improved pooled KL but did not improve the task outcome. This is not a hierarchy win. Its five delayed-clue controls preserve originals and corrections; all recovery readers retrieve the clue after restart while no recovery does not.

V2 keeps the same exposed comparison seeds and labels itself a development refinement. Recovery occurs on a new mission, or after 8 stable-coverage reads with a repeated pose, or 24 stable-coverage reads regardless, with an 8-read cooldown and 24-pose history. This is an observed-coordinate exploration signal, not semantic novelty or learned salience. Its controller state persists with a checksum and commits with actual-use updates. An always-recover ZHA control isolates the scheduling decision. Current perception remains explicit; only returned historical facts increase hit counts.

The scoped graph also uses the known-only coverage mask to avoid nominating unavailable-but-known neighbours as unexplored frontiers. This adds no cold passability or payload to graph construction. Existing baseline readers keep their original default behavior. The independent audit records a 1e-12 top-p threshold roundoff band after a scalar log-domain reduction selected one fewer node at exactly 0.8 than native softmax/cumsum; no scientific run or core tolerance was changed for that audit repair.


## Completed implementation and results

The lane now runs through both the CLI and the existing dashboard on port 8792. The default method loads the fitted checkpoint; it does not refit during a solve. Each fresh run retains a separate local SQLite archive. Neither the separate continuous neural learner nor the portfolio application was modified.

| Comparison | No recovery | Always fixed ZHA | Gated fixed ZHA | Gated random ZHA | Gated fitted ZHA | Exact |
| --- | --- | --- | --- | --- | --- | --- |
| v1, eight episodes each |8/8|6/8, named `fixed_zha`|not run|6/8, always|6/8, always|8/8, always|
| v2, eight episodes each |8/8|8/8|8/8|8/8|8/8|8/8, gated|

V2 changes both recovery scheduling and known-only frontier handling. The always-recover control also solves 8/8 after the frontier fix, so these results do not establish that gating caused the success recovery. The scoped graph had been nominating unavailable-but-known neighbours as unexplored frontiers; the fix prevents those phantom nominations without revealing their passability. A state-based regression test covers that case. V1 failures and their original frozen implementation remain intact.

The gate reduces unnecessary archive work on this small development cohort: always-fixed ZHA reads 63,602 original key/query pairs plus 240,872 summary dot products and 97,672 rerank pairs; gated-fixed reads 712 original pairs plus 2,296 summary dot products and 902 rerank pairs. These totals follow different executed paths (389 versus393 actions), include no cost conversion, and are not an end-to-end speedup. Gated exact uses 1,086 original pairs with no summary or rerank work. Index construction, database reads, hot scoring, graph construction and BFS are additional recorded costs.

The fitted checkpoint contains 240 trainable reference values (eight vectors with 30 dimensions), selected at step 40 using 48 training and 24 validation prefixes. Forty-seven disjoint comparison prefixes remain after removing one exact Q/K duplicate. Training pooled KL falls 0.007067→0.005186 and validation 0.004930→0.003544. On 105 comparison query cases, fitted mean pooled KL is 0.004354 versus fixed 0.005719; random references score better at 0.000561. Fitted mean dense mass retention is 0.77438 versus fixed 0.77591. Better fitted KL does not establish better task outcomes, global top-p retention or superiority over random references.

The authored delayed-clue diagnostic is separate from official task success: every recovery reader retrieves the dormant key with observed path support after restart; no-recovery cannot. All conditions preserve original payloads, exclude the superseded key version, and restore the tested controller metadata. This is source recovery, not a demonstration of learned consolidation or general task transfer.

Independent audits replay official actions, reconstruct observed sources and hot/cold lineage, check recorded top-p/leaf ownership and recompute selected numerical route cases using a scalar oracle. V1 covers 40 episodes/2,719 decisions and 24 numerical route cases; v2 covers 48 episodes/2,356 decisions and 20 numerical route cases. Each independently checks 315 offline dense-mass cases. The audit is not an independent optimizer-trajectory reproduction, exhaustive route recomputation or performance certificate. V1's first audit needed an explicitly recorded 1e-12 threshold roundoff band; the successful repair did not alter the scientific data. Both audit versions and the frozen original are retained.

## Running it

Use the locked research and benchmark extras:

```sh
uv sync --locked --extra research --extra benchmarks
uv run --locked python -m research.run_persistent_tasks --output experiments/persistent-task-local
uv run --locked python scripts/audit_persistent_tasks.py --results experiments/persistent-task-local
```

The output directory must be new. The current protocol repeats the development comparison; changing seeds or policies requires a newly declared protocol and a new output directory. The runner saves protocol/source hashes before collection, observed-prefix training data, reference checkpoints, all action/read traces, outcomes and local SQLite archives. Compressed traces are durable evidence. Mutable SQLite files under `archives/` are deliberately ignored by Git.

The programmatic entry points are `RouterCheckpoint`/`fit_task_references` in `research/task_references.py`, `WorkspaceConfig`/`TaskStore` in `research/task_store.py`, and `PersistentTaskReader` in `research/persistent_task_memory.py`. Use a fresh context namespace for every world revision/reset/frame. Reopen a fitted archive with the same configuration and checkpoint; its identity mismatch must fail. Close the single writer before another process opens the archive. This backend uses POSIX advisory locking and is a local transactional reference, not a distributed service.

Forgetting is the explicit utility rule `(1 + log1p(hits)) * 2**(-age / half_life)`. Retirement deactivates a head when its utility falls below the threshold; capacity pressure can evict another head. Promotion refreshes recency without inventing a usage hit. Hits count facts actually returned to the planner, not necessarily acted upon. The benchmark advances a logical clock and injects 16 extra ticks every 16 actions. These are declared engineering choices, not fitted biological constants or a PCAM reproduction.

Only active payload capacity is bounded. The canonical archive, key cache, coverage mask and numerical summaries are extra storage; index rebuilding can read every canonical head. Recovery limits are per read. A core budget interruption records incomplete work rather than a fabricated zero count or hidden exact fallback. Persistence restoration checks the memory controller; it does not resume simulator RNG, planner queues or a running episode automatically.

## Remaining research gates

1. Freeze the repaired policy and evaluate untouched task seeds before a policy-generalization claim. This same-cohort development result is insufficient for a public claim of improvement.
2. Stress long delays, adverse corrections, recovery misses and tighter memory caps; compare equally informed exact and graph controls, with all index/metadata/BFS work charged.
3. Test whether fitting helps source retrieval at matched quality and budgets, including random references. The current pilot does not show an advantage.
4. Add incremental indexing only after correctness parity and profiling show it matters.
5. Design a separate observed-transition replay/consolidation experiment, with a learned target, held-out outcomes and no writeback of imagined facts. Sleep, latent visual dreaming and neural consolidation are not implemented in this task adapter.

Dashboard wiring is now complete: see `UNIFIED_DASHBOARD.md` for source-bound lifecycle views, live solves, archive locations and browser checks. Sleep and neural consolidation remain separate research gates.
