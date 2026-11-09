# Dependency-preserving memory: independent acceptance contract

Status: design and audit requirements for the new milestone. No new outcome is implied by this contract. The previous fixed and adaptive MiniGrid failures remain evidence; development uses seeds 0/1 and the already exposed 1001–1003 cohort. Fresh seeds 2001–2006 stay untouched until the complete implementation, controls, parameters and source files are frozen.

## What the reader may do

The reader may inspect its own archive of genuinely observed facts and compute an observed topology graph. This is real work: charge archive materialization, semantic scans, graph construction/rebuild, node/edge scans, every BFS traversal, routing, candidate reranking and closure/halo construction. A 96-fact output is a workspace limit, not a bound on archive size, RSS or reader computation.

The common planner receives returned immutable raw facts, the actual current observation and, only in explicitly mask-bearing conditions, the declared observed-known bitmask described below. It must not consume a reader's action, target coordinate, planned route, candidate scores, typed coverage map, hidden simulator state or closure receipt. Receipts are audit/inspection evidence, not a second control channel. Context may contain the observed pose, inventory, mission and current visible facts; it may not introduce a privileged goal, hidden room label or future success signal.

## Explicit knownness interface extension

The user-authorized design adds an ablated 64-by-64 binary mask at fixed relative origin `(-32,-32)`: 512 binary bytes, plus declared JSON transport/version/hash overhead. Every bit must equal whether that cell has actually appeared in the observation prefix. Unseen cells remain zero; coordinates may not wrap or be silently dropped outside the declared bounds. No bitplane, object type, color, passability label, target or action is permitted. Source-head identity is an opaque consistency commitment, not a policy input for choosing actions.

The common planner may use the mask only to avoid treating an omitted but already known cell as an unseen exploration frontier. It may not traverse a mask-only cell, infer its passability or recover its object. Every proposed navigation route must still be supported by returned/current typed facts. Include flat exact-plus-mask and flat ZHA-plus-mask controls alongside all bundle-plus-mask conditions. This changes the interface: resulting claims must say 96 historical raw facts **plus** the explicit mask, not a 96-facts-only memory bound. No-mask legacy policies must retain their actions and evidence selections on the same allowed observation histories.

## Seed nomination and controls

Every seed must identify its nomination source: actual ZHA-selected original, exact-scored original or a declared graph-only rule. Any full-archive landmark/semantic scan capable of finding the mission goal must be explicit. Such a scan can be a useful baseline, but cannot silently supply the supposedly hierarchy-selected endpoint.

Run the identical closure, halo, budget rule and common planner with ZHA seeds, exact seeds and an ordinary graph-only control. Preserve the strongest full observed-memory baseline. Same capacity is not equal cost; compare task outcomes, all archive/graph work, latency and output facts. A graph BFS doing all useful selection is an ordinary graph solution, regardless of whether a ZHA call is also logged. Include a seed perturbation/ablation demonstrating whether seed choice can affect the returned evidence and downstream actions.

## Structural receipts

Each read binds a source-head/version identity and records the input context, nominated seeds, required raw IDs, dependency edges/path witnesses, halo IDs, returned IDs and omissions. Dependency paths must consist only of adjacent actually observed cells with current versions. No unknown cell becomes walkable, and no superseded tile is silently reused. The actual current observation may support a visible cell without consuming an additional historical slot, but that accounting must be explicit and identical across controls.

Locked-door support must identify a matching observed key or the current matching-key inventory and its necessary access evidence. A key known only behind its own locked door is not proof of accessible support. Closed unlocked doors and locked doors with a key are different conditions. Receipts must expose unresolved/circular prerequisites rather than silently treating every known door as open.

`complete` means that the stated path plus one-hop halo requirements are present under the declared observation and budget rules. This is not recursive/global frontier closure: receipts must explicitly report residual known-neighbor omissions beyond that scope. It does not mean the mission is solved, the nominated target is correct, the world is fully known, or a future action is guaranteed to succeed. `overbudget` must expose the omitted support; clipping a path then calling it complete is invalid. Halo support must come from observed cells; an unknown neighbor cannot be manufactured as a wall or floor.

## Required executable challenges

1. Replay every executed action using the pinned official environment; compare both observations, reward and termination exactly. Reconstruct archive versions from visible observations independently.
2. Reject a foreign, future or superseded seed/support ID, a changed raw payload, a nonadjacent edge, a path through unseen cells or a fabricated key prerequisite.
3. Verify every declared complete closure's support is in returned raw facts or justified current-visible support. Verify output capacity, duplicate accounting and truthful overbudget omissions.
4. Test door/key pickup, locked-to-open, wall-to-floor and correction updates so stale graph/index caches cannot survive head changes.
5. Check all scans and traversal receipts against independent event counts. Full-archive graph construction and landmark scans cannot disappear from ZHA's costs.
6. Prohibit a reader from supplying an action or bypassing the common planner. Preserve old policies' actions on fixed development observation histories after optional context injection.
7. Freeze every executed policy/reader/core source, data/environment versions, parameters, conditions and seeds before fresh evaluation. Bind every trace to its frozen source; preserve all failures and reruns.

Passing these checks supports an observation-grounded dependency-memory integration. A ZHA benefit requires a matched comparison against the graph/exact controls. This milestone does not by itself establish trained perception, causal biological memory, dreaming, consolidation, industrial validity or algorithmic novelty.

## Review findings and corrected behavior, 9 November 2026

The review found an unnecessary-lock dependency: when a short route crossed a locked door without an accessible key, the initial reader rejected the target even if an observed unlocked detour existed. The six-cell counterexample has start `(0,0)`, locked door `(1,0)`, goal `(2,0)` and a free detour through `(0,1),(1,1),(2,1)`. Production now prefers an inventory-feasible route before optimistic dependency discovery; the independent graph oracle and regression agree. A key known only behind its own lock remains missing support.

The ordinary graph comparator nominates legitimate observed semantic/frontier endpoints using the same closure and packing, rather than arbitrary-ID/FIFO packing. A further exact-history mask control scores enough originals to exclude all at-most-49 current visible positions while retaining exact top-96 nonvisible history. Its internal 145-seed capacity/filtering is charged separately from its 96 returned-fact limit. This controls reclaiming duplicate-current slots before attributing an effect to graph grouping.

Visible support is free only when the current observation supplies its required information. A remembered sample-role/cue bit absent from the current local view remains historical information even at a visible coordinate. Ordered paths and semantic sample-support IDs make those dependencies explicit. No action, nominated goal or path supplied in a reader receipt is consumed by the common planner; the receipt-canary regression confirms this boundary.

The executable independent auditor is `scripts/audit_dependency_memory.py --results DIR`. It delegates official replay and seed numerical selection to the earlier independent task auditor using an explicitly computed seed-only workspace projection. That projection preserves actual observations/actions/rewards; it is never substituted for the recorded episode. The new auditor separately checks the original packed raw facts, planner navigation/source fields, masks, nomination, ordered routes, key/sample prerequisites, halos, whole-bundle packing, residual omissions and cost events. The input evidence is not modified. This does not amount to a universal noninterference proof or a semantic-correctness certificate.

The 33 reviewer tests pass, including false mask bits/labels/bounds/version/hash/transport size, stale/foreign sources, wrong ordered edges, absent key/sample/halo support, false visible/history exemptions, changed output payloads, false statuses, suppressed residual omissions, incorrect scans/BFS counts and reader action/goal bypass. Ruff and strict mypy pass. Independent current-code replay also reproduces all 9,118 actions plus poses, selected IDs, objectives and goals from 12 stored seed-0 no-mask histories (three readers across four tasks). The owner's broader parity artifact covers 56 old development episodes and 49,612 steps.

Independent set-based prefix reconstruction reproduces the earlier DoorKey diagnostic: adaptive ZHA has 7,634 of 7,680 chosen frontier boundaries consisting solely of omitted known cells, of which 2,542 contain only omitted known obstacles; exact has 6,356 and 3,812 respectively. Both have zero omitted known landmarks. These are per-action diagnostic counts, not unique cells, a proof that every selected action is wrong or a new evaluation cohort.

## Development evidence

All 32 initial bundle-development episodes pass independent replay and structural audit: 6,669 official transitions,5,783 fact versions, 14,685 numerical seed-query routes and 13,299 bundles. Graph succeeds 8/8, recency 7/8 and both hierarchy/exact bundles 6/8; the unfavorable KeyCorridor cases remain preserved.

The 40 preliminary mask-development traces also pass their declared source/work schema. That older snapshot did not record several later scan/materialization/path event categories. The audit reports those omissions rather than silently claiming modern cost coverage for historical evidence.

The final source-bound `dependency-development-v2` cohort passes all 88 episode audits: 41,066 official transitions, 14,258 fact versions, 74,133 seed-query routes, 15,405 dependency reads and13,308 recomputed bundles. All current-schema work categories, raw/mask transport bytes, current-version identities and whole-bundle budgets agree. There are 61 successful episodes across the 11 conditions. This is development evidence on seeds 0/1, not fresh generalization evidence.

## Frozen fresh cohort and claim boundary

The source-frozen `dependency-evaluation-v1` table contains 264 episodes (four official tasks, 11 conditions, fresh seeds 2001–2006), all at 96 returned raw facts and the explicitly declared mask where applicable. No 192-slot cohort was run. Independently recomputing all 44 outcome/cost aggregate rows agrees with the episode table: legacy adaptive 7/24, exact 9/24, full 24/24, none 0/24; flat ZHA+mask 20/24, flat exact+mask 19/24, exact nonvisible history+mask 21/24; bundle ZHA 20/24, bundle exact 19/24, bundle recency 19/24 and ordinary graph 24/24. There are 0 reported errors/cutoffs and 82 official truncations.

These comparisons do not support a ZHA advantage or an aggregate bundle-success gain over the corresponding mask-only controls. They support the importance of the declared knownness interface and the strength of ordinary observed-graph access. Output-fact traffic, graph work, metadata and timing must remain separate; the 96-fact output bound does not bound the reader's complete archive, graph or RSS. The active implementation document was updated with results after execution; its frozen pre-run snapshot remains intact, and executed code hashes still match. The full 264-episode official replay and receipt audit has now passed through the repository's completed verification gate. The [independent attestation](../experiments/dependency-evaluation-v1/INDEPENDENT_AUDIT.json) records 110,470 official transitions, 45,093 observed fact versions, 200,941 seed-query routes, 32,998 dependency reads and 19,173 recomputed bundles, with all declared work categories accounted for. It preserves the original auditor JSON and binds the protocol, input manifest, auditor source and verification log. The separate [aggregate check](../experiments/dependency-evaluation-v1/INDEPENDENT_AGGREGATES.json) independently confirms all 44 outcome and cost rows. All 17 repository verification checks passed, including 382 tests, lint/types and fresh wheel/source-package installations. No additional code or test changes followed this gate.
