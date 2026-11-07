# Complex-task acceptance and review contract

Status: implementation and audit contract, not benchmark results. These tasks can establish a reproducible research integration and measured tradeoffs. They do not establish industrial deployment validation, biological dreaming, algorithmic novelty or a speed benefit merely by being harder than the prior diagnostic.

## Sources and task identity

- [Official Google DeepMind Boxoban levels](https://github.com/google-deepmind/boxoban-levels), pinned implementation input commit `78011d8c86ad423bfb2e1005012393b4c3c24409`. Keep original files, SHA256 values, license and exact level IDs. The official distribution defines train/validation/test cohorts; a fixed small subset must be described as that subset, not the full published benchmark.
- [Farama MiniGrid](https://github.com/Farama-Foundation/Minigrid) and its [environment documentation](https://minigrid.farama.org/environments/minigrid/KeyCorridorEnv/). Pin the installed package version, environment ID, wrappers, constructor options and all episode seeds. A fully observed wrapper changes the information setting and must not be called the original partial-observation benchmark.

Do not select evaluation seeds or puzzle IDs after inspecting solver success, memory advantage, retrieval quality or visual appearance. Retain timeouts, deadlocks, solver exceptions and failures. Development smoke tests use training data. Once an evaluation cohort informs a design change, mark it development evidence and reserve a fresh cohort for the next generalization claim.

## What would establish a useful ZHA contribution

The target is a task-quality versus **total measured cost** comparison on the same available information and fixed memory bank. A genuine hierarchy-mediated decision must be distinguishable from the common planner or controller doing all useful work.

For Boxoban, share legal moves, state equivalence, deadlock rules, base matching heuristic, duplicate handling, expansion caps and time limits across conditions. Compare no episodic memory, random or shuffled case values, dense case attention, exact nearest-case search and ZHA. A small bank may favor exact search; preserve that result. Equal expansions are not equal runtime when one condition performs additional retrieval or construction. A heuristic augmented with learned case estimates is not automatically admissible, and successful solutions are not automatically optimal.

For MiniGrid, compare the same observation-only controller with no episodic memory, bounded exact memory and hierarchical memory. Include an observation-derived map/planner control where the task permits it. A memory task that needs one remembered bit can show memory dependence but cannot establish a need for hierarchical search or scaling. Report per-task failures rather than average away failed task families.

The old original-state identifier shortcut is prohibited in query keys. Training-source IDs may appear in provenance, but they are not query features. A large feature vector is not evidence of learned perception; fixed symbolic encodings must be labeled accordingly.

## Information boundaries and leakage checks

### Boxoban

The full current board is legitimate observed input. Training cases may contain expert solution continuations only when generated from actually solved training puzzles. No test or validation solution, target action, remaining optimal distance, test-search suffix or future outcome enters case construction or query features. Validation can select settings, but must remain excluded from the frozen training case bank unless the final task is explicitly redefined and a fresh test cohort is reserved.

Hash the full puzzle state, including static walls/goals, boxes and player. Detect rotated/reflected duplicates across splits. For push-state search, different player positions in the same reachable free-space region are equivalent; duplicate detection must not rely solely on the literal player marker. Audit all case-source puzzle IDs and hashes against the held-out initial states, not only filenames. A solution copied under a different level ID is still leakage.

### MiniGrid

Policy inputs are the official observation (`image`, `direction`, `mission`), prior allowed observations/actions/rewards and the policy's own state. Full environment `grid`, true `agent_pos`, unobserved goal/key positions, layout seeds used to reconstruct hidden terrain, future simulator states and evaluator success labels are unavailable to the policy. Privileged telemetry may be retained for rendering and independent scoring, but must be carried through a separate evaluator path and never used to correct the policy's pose, update its map or select a memory read.

Store the exact observation before each chosen action. An auditor replays the action sequence using the pinned official environment and compares observations, rewards and termination flags. This establishes trace correctness; it does **not** by itself prove that the policy did not peek at hidden state. Add an information-flow test: the controller accepts no environment handle, and identical allowed observation histories plus RNG state produce identical actions/memory reads even when hidden telemetry differs. Every remembered tile or cue must be attributable to an earlier visible observation.

Online memory after a test episode changes subsequent episodes. Either reset/fork the same training memory before each evaluation episode, or explicitly report a continual online-adaptation protocol with fixed order. Do not silently share test outcomes between conditions.

## Independent state replay

The puzzle auditor must not import the production successor, parser or goal checker. It reconstructs walls, floor, goals, player and boxes from the frozen board and executes each primitive move. It checks adjacency, wall collisions, push destination occupancy, box conservation, reported pushes/moves and the final goal condition. If a stored path uses push macros, include their primitive walking paths so legality can actually be checked. Invalid moves, fabricated intermediate states and falsely claimed success must fail the audit.

The MiniGrid auditor may use the pinned official environment as the independent transition authority, but must not import the production controller. It compares raw observations before every action, action IDs, rewards, termination/truncation and final status. A resource-limited unfinished episode is not a successful terminal episode. An externally imposed cap is distinguished from the environment's own truncation.

## Retrieval, persistence and provenance

Each read binds a memory-bank hash, feature/reference version, query descriptor, selected original IDs, route/work counters and source provenance. Every selected case or observation must exist, belong to an allowed split/earlier observation prefix and be current under its declared version. Unseen or superseded sources are rejected. Optional dense-oracle diagnostics are separate work after the real decision and cannot choose the runtime branch.

When numerical values are reported, retain enough query/key/value information to recompute selected softmax output independently. Weight normalization alone does not establish correct scores, and a matching action alone does not establish that ZHA was used. A negative control must detect an implementation that silently substitutes dense selection or ignores the retrieved guidance.

Durable offline learning is established by changed learned parameters that survive removal of temporary traces and a fresh process. Imagined puzzle or navigation transitions remain predicted evidence; they are not written as observed successes. Corrections invalidate dependent forecasts and derived indexes. Test reset/restart using the same configured path and test concurrent controller ownership, not only direct checkpoint loading.

## Cost and outcome accounting

Retain per-run and per-query counts for environment steps or primitive moves, pushes, expanded/generated states, duplicate/deadlock prunes, raw key comparisons, reference-channel summary comparisons, selected leaves, index construction and rebuilds, fitting, case generation, retrieval latency and wall time. Distinguish logical active capacity from total archive/index/RSS. Construction and reference fitting must not vanish from an end-to-end speed claim. Report warm repeated-query and amortized build scenarios separately.

Predeclare expansion, step, selected-key, route-node, memory and wall-time caps. Resource errors return typed failures, not low-confidence successes. Counters must be nonnegative and agree with raw events; all conditions retain the same externally imposed caps unless explicitly compared as a cost-quality frontier.

## Required negative controls

The auditor must reject copied evidence with an illegal puzzle push, changed final success, mismatched intermediate state, future/foreign memory source, train/test duplicate under symmetry, fabricated observation, changed reward/termination, missing budget failure and inconsistent work total. Run at least one valid solved puzzle and one valid failed/timeout trace; an auditor that accepts only positive examples is insufficient.

## Claims that remain separate

1. Official task integration: pinned real dataset/environment and valid executions.
2. Closed-loop task competence: successful actions on fixed held-out episodes under stated limits.
3. Memory usefulness: controlled improvement versus a memory-free or simple-memory baseline.
4. ZHA usefulness: controlled quality/cost benefit versus exact/dense retrieval on the same memory.
5. Learned continual improvement: persistent parameter change improves later held-out behavior without unacceptable forgetting.
6. Industrial or deployment validity: operational workloads, scale, reliability and costs outside these research tasks.

Passing an earlier item does not establish the later items. Record failed and neutral results as results.

## Independent audit evidence, 8 November 2026

The initial frozen `experiments/boxoban-search-v1` evidence passes the independent auditor: 32 solved training paths, 363 source-bound cases and 448 held-out search runs. The auditor replayed 5,852 actual pushes, reconstructed every logged geometry query and checked 96,517 selected numerical reads. It verified original data and source-snapshot hashes, train/evaluation symmetry exclusions, training suffix provenance, condition completeness, resource counters and report-to-artifact agreement. Separately recomputing all 28 aggregate rows agrees with their underlying traces. Of the 448 evaluation runs, 399 solved and 49 reached the expansion cap; these failures remain in the results. The current small bank does not demonstrate a ZHA speed benefit. Numerical hierarchy construction/routing itself is validated by the separate core oracle tests; this task auditor does not import or rederive that router.

The reusable-reader audit found that search results originally shared a mutable read-log list and cumulative counters. The owner fixed this by returning deep-owned per-search logs and counter deltas. Current code and the regression preserve earlier results when a reader is reused. Shared reader construction time is explicitly lifetime setup.

Every expanded Boxoban state additionally requires an independently legal earlier-parent witness. Expanded priorities are bound to the independently reconstructed matching bound and the logged, clamped recalled output (with the implementation's separately handled initial priority). A negative control supplies a nonzero valid read while leaving the memory-free priority unchanged and must fail. This verifies the priority formula; it does not reconstruct the complete heap-choice order. The owner's separate behavior test that changes guidance and observes changed expansion choices covers whether the live solver actually uses guidance in decisions.

One v1 reproducibility limitation remains: the Boxoban runner freezes its two research scripts and dependency files, but does not hash every numerical-core source file at the phase boundary. Its manifest records Git commit `621deb9c85815147d3081bb0fcc61d2ece16cc9c`, and the independent review verified that the numerical-core tree was clean against that commit. This supports reconstruction of the current result; the existing guard would still miss a later uncommitted core edit between preparation and evaluation. Future freezes should include core-source hashes. Do not rewrite the existing snapshot to conceal this limitation.

The original v1 evaluator also validates raw files against the current dataset manifest without requiring that manifest to equal the frozen one. A simultaneous change to a raw file and its current manifest would evade that original phase-boundary guard. The independent artifact audit instead compares every raw file against the frozen run manifest and passes the existing v1 data. Future evaluators should explicitly bind both manifests. This is an existing-guard limitation, not evidence that this run used changed data.

The owner subsequently repaired both guards for future runs: every numerical-core Python source enters `SOURCES`, and the current data manifest must equal the frozen one. Independent execution of the core/data-manifest tampering regression and the guidance-changes-expansion behavior regression passes (two tests). The existing v1 snapshot remains unchanged.

Initial MiniGrid development evidence is separate from held-out results. The four seed-0 full-memory traces solve Memory, MultiRoom, DoorKey and KeyCorridor in 15, 53, 75 and 62 steps. Four independent ZHA runs at capacity 96 and a 512-step development cap fail all four: Memory 512, MultiRoom 120 (official truncation), DoorKey 512 and KeyCorridor 512. Both positive and negative traces pass official-environment replay, observation-derived tile projection, archive/version provenance, query reconstruction, selected attention-output and event-counter checks. The ZHA traces and audit results are preserved under `/private/tmp/research-review-somna/minigrid-dev-review/`; no held-out seed was used in this independent diagnostic. These results establish valid executions and a real retrieval bottleneck, not a memory-performance improvement. If the controller or features change, these numbers describe this development snapshot only.

The auditor permits only numerical ties within `1e-9` when comparing MiniGrid scalar-score ranking with backend matrix reductions; it still rejects omitted candidates with a larger score gap. This avoids treating harmless floating-point tie order as an implementation defect. It does not relax source identity, visibility, freshness, capacities or task outcomes.

The source-bound `experiments/minigrid-development-v1` comparison subsequently passes the independent audit for all 48 episodes: 42,195 official steps, 5,965 observed fact versions and 19,456 hierarchical query routes. There are 19 successful episodes across all readers; ZHA succeeds in 1 of 8, exact and recency in 4 of 8 each, FIFO in 2 of 8, no episodic memory in 0 of 8, and full observed memory in 8 of 8. These are development seeds 0 and 1, not held-out generalization evidence. The comparison exposes real shortcomings rather than a hierarchy win. In Memory seed 0, the first divergent action occurs at step 3 with identical observation histories: ZHA returns only 38 of 54 available facts despite a capacity of 96, omits corridor-floor connections and scans; full memory retains the connected corridor and walks toward it. No storage-capacity pressure is needed to trigger this failure. Sparse retrieval preserving planner connectivity is an open implementation/design requirement.

A separately named `zha_adaptive` reader widens only when its accumulated actually routed candidate union cannot fill the declared active slots. Its fixed schedule is `.4/.6/.8/.95/1.0`; every pass, summary comparison, selected attention pair and exact rerank within that union is charged. The auditor verifies attempt numbering, the schedule, justified widening/stopping, current source IDs, numerical outputs and explicit full-original coverage at `p=1`. Development v2 passes all 56 trace audits: 49,612 transitions, 7,071 fact versions, 64,219 query routes, 31,327 routing passes and one full-candidate fallback. Adaptive solves 4 of 8 development episodes, matching exact recall; full solves 8 of 8. Prior failure traces remain preserved.

The frozen formal `experiments/minigrid-evaluation-v2` cohort also passes all 84 independent trace audits: 75,520 transitions, 10,321 observed fact versions, 89,170 numerical query routes, 43,066 routing passes and five verified full-candidate fallbacks. Each reader has 12 episodes (four task families, seeds 1001–1003). Outcomes are fixed ZHA 1/12, adaptive ZHA 3/12, exact 5/12, recency 4/12, FIFO 3/12, no episodic memory 0/12 and full observed memory 12/12. All failures are retained; no episode errors or external cutoffs occurred. Adaptive fails all three formal MultiRoom episodes despite solving both development seeds. This supports a valid integration and a real failure analysis, not a ZHA advantage or broad competence claim. The cohort is small and these task runs do not train a policy or establish dreaming/consolidation benefits.

Run the artifact auditor with `python scripts/audit_complex_tasks.py --results experiments/boxoban-search-v1` or `--minigrid PATH_TO_FROZEN_MINIGRID_DIRECTORY`. Its negative controls include illegal pushes, invented intermediate states, incorrect goals, premature resource failures, wrong numerical reads, foreign/future/stale source IDs, rehashed foreign case provenance, wrong training suffixes, train/test symmetry duplicates, fabricated observations/rewards/history and inconsistent work. Auditor fixtures are verification inputs, not benchmark results.
