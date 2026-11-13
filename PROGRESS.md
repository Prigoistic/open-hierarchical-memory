# Implementation progress

Last updated: 8 November 2026. This file is the current status; the dated planning documents describe earlier requirements, not completed capabilities.

## Goal

Build a useful, readable independent ZHA research reference, then real model-layer experiments and a trace inspector. Keep paper approximation separate from any new guarantee. Publish only claims backed by evidence. Following the user's 5 November direction, add a separate bounded forgetting/recovery research lane while preserving the verified attention core. The lifecycle prototype does not imply a persistent semantic-memory product or converted model.

## Milestones

- [x] M0: engineering plan, counterexamples and supported-contract review.
- [x] M1 implementation: owned CPU float64 snapshots, affine summaries, recursive tree, causal/head-local router, selected attention and explicit budget failures/fallback.
- [x] M1 local verification: independent scalar oracle, high-precision output oracle, generated cases, isolation/ownership/boundary tests and targeted semantic mutation checks.
- [x] M1 installed-release-artifact evidence: wheel and source distribution in fresh offline environments.
- [ ] M1 hosted CI evidence: GitHub reports startup failure before jobs/logs; static workflow validation passes.
- [x] M2: reference-only fitting, native pretrained GPT-2 capture, three-seed held-out layer pilot, checkpoint reloads and post-run scalar-oracle audit. See [measured results](experiments/gpt2-layer5-pilot-v1/SUMMARY.md).
- [x] M2b: seven geometries, three contexts, three seeds, four fresh held-out books; 63 fits, 567 test configurations, 189 native-SDPA timing comparisons, preserved raw measurements and independent audit. See [results](experiments/gpt2-cost-quality-v1/SUMMARY.md).
- [x] M2c: component profile, separately tested batched CPU prototype, resource-preflight review and corrected fresh-process timings; all original numerical core bytes preserved.
- [x] M2d: fixed-data training-duration diagnosis on train/validation only, with exact 100-step reproduction and audited raw validation records.
- [x] L0: separate append-only SQLite archive, bounded hot set, correction chains, usage decay, coverage replay and local JSON-lines interface; 58 lifecycle behavior cases and five targeted semantic faults.
- [x] L1: fixed lexical lifecycle diagnostic across seven policies, three seed permutations and two hot capacities, plus raw-trace/read-only-archive audit. Delayed rare-fact recovery remains poor; no assistant-quality claim.
- [x] S0: separate Somna symbolic spatial replay integration, numerical reader/target path, persisted values, raw trace inspector and independent evidence audit.
- [x] S1: live partial-cue continuous memory, actual dormant-bank hierarchy, bounded workspace/reversible retirement, persistent correction/controller state, learned dynamics and asynchronous observed-step inspector API.
- [x] S2: fixed continuous-learning comparisons, random/dense/exact-neighbor and ordinary-replay controls, functional-gradient/trajectory audit and independent counterexample review.
- [x] T0: official Boxoban and observation-only MiniGrid comparisons, actual-trace inspector, independent provenance/transition/cost audits and preserved unfavorable outcomes.
- [ ] M3: persistence, trace inspector and scoped reference release (deferred behind useful execution/quality evidence).
- [ ] M4: numerically conservative bound/checker, if sound and useful.
- [ ] M5: audited positional adapter and closed-loop model conversion.

An adapter must move earlier if required by the selected real-model fixture. The completed GPT-2 adapter uses learned absolute positions; it does not close the RoPE gate. Only the measured routing-reference checkpoints are included; no converted model, GPU feature or checked-mass API is claimed.

## Current evidence

Local suite with research and benchmark extras: 324 passing pytest cases, including 20 earlier Somna spatial/evidence cases and41 live-engine, HTTP and independent-audit cases; the earlier attention/lifecycle suite includes 60 generated routing configurations, 16 high-precision fixtures, native-model capture, fitting and data-isolation checks. Ten targeted core mutations and six additional batched-backend mutations are detected. Ruff, formatting and strict mypy check the package. The latest [full verification](docs/evidence/local-verification.json) covers 324 tests, task audits and fresh wheel/source installations. The earlier [core-only record](docs/evidence/core-verification.json) preserves its narrower 235-test run. See also [mutation evidence](docs/evidence/mutations.json). Without optional research dependencies, GPT-2 adapter tests are explicitly skipped. The original pilot audit checks eight real queries and 27 aggregates; the cost-quality study audit checks 24 real queries, 567 test/63 validation aggregates and 254,016 raw records. These audits do not replace regular tests.

Hosted verification has not passed. The corrected workflow passes official actionlint 1.7.12 (checksum-verified distribution). The user confirmed an account-side restriction prevents hosted jobs from starting. Development can continue using the local core profile below. See [the run](https://github.com/Prigoistic/open-hierarchical-memory/actions/runs/41708001430) and [separate workflow evidence](docs/evidence/workflow-validation.json). Local success does not establish hosted CI success.

```sh
uv sync --locked --extra research
uv run --locked --extra research python scripts/verify.py
```

For normal code changes when hosted compute is unavailable:

```sh
uv run --locked --extra research python scripts/verify.py --profile core
```

The core profile writes `docs/evidence/core-verification.json`, preserving the full-profile report. It includes numerical tests and semantic mutations but explicitly excludes package-installation checks. Full verification is still required for release or packaging changes. No self-hosted runner, public repository exposure or account-setting changes are needed for this local workflow.

The numerical domain is CPU float64 with finite, moderate test inputs. Proposed core tolerance remains `atol=1e-10, rtol=1e-9`; passing cases do not constitute a universal numerical proof. Approximate routing can have substantial error. The scoped accuracy measurements in the pilot are offline observations, not universal guarantees. No speedup, production-readiness, firstness or semantic-correctness guarantee is claimed.

## Engineering gate coverage

| Plan gates | Current state |
| --- | --- |
| V01–03, V05–11 | Implemented for the documented no-RoPE in-memory support contract; local oracle/regression evidence |
| V12–14 | Input/ownership/budget/fallback cases covered; disk corruption, cancellation and mutable-cache recovery are unavailable, not passed |
| V04, V15, V18–21 | RoPE, index persistence, bounds and inspector gates remain open |
| V16–17 | Reference-gradient exclusion, pooled-KL oracle, fitting selection, frozen native captures and three-seed held-out pilot pass for the documented GPT-2 layer scope; whole-model conversion remains open |
| V22 | Wheel and source distribution installed and exercised from fresh local environments; no package registry release |

## Review decisions

1. The repository name is `open-hierarchical-memory`; import namespace is `open_hierarchical_memory` instead of the plan's placeholder `open_zha`.
2. Keep the first remote private while validation and research work continue. No public launch or PyPI upload.
3. Preflight selected-key/dense work budgets before allocating large ID collections. Budget failure is not a low-confidence success.
4. Do not accept p=1 equality as sole routing evidence; test sparse behavior and require tests to catch a dense shortcut.
5. Stable summary construction and input ownership do not create a runtime error certificate.
6. The synthetic example intentionally reports its actual, imperfect retained mass and attention error. Random reference queries are not presented as trained behavior.

## Next work

The cost-quality study is complete. Validation selected C16/R2/depth2 at p=.90 for all contexts. On fresh test books, mean layer-relative errors are 2.23%, 2.99% and 3.84%, with p95 below 9%; all pass the fixed diagnostic budgets. Counted QK+AV vector work falls to .622/.496/.393 of dense. These counts omit sorting, softmax, memory traffic and framework overhead.

The reference remains slower than native dense SDPA: at 1,024 tokens, eight-window batch query times are 41.47ms versus 2.44ms, excluding the additional 85.09ms index build. No measured speed benefit or model-quality claim is supported. At the same selected geometry/threshold, random references have lower mean output error than fitted references, but selected-key costs differ; fitting superiority is not established.

Execution profiling and the first batched experiment are now complete. The prototype remains research code, with explicit reference dispatch for traces/custom budgets/dense execution; it does not change the installed core API. See [current corrected-backend results](experiments/batched-execution-v2/SUMMARY.md), [reference profile](experiments/execution-profile-v1/SUMMARY.md) and [implementation contract](docs/EXECUTION_BACKEND.md). All 252 configurations pass exact selected-ID and output-tolerance checks across 96,768 query/head cases; maximum absolute output difference is about 7.55e-15. The original numerical core remains byte-identical. All three layouts and index/padding/memory costs are retained.

The first version's excessive-work ID expansion was found during resource review, fixed with count preflight and a query-row cap, regression-tested, and remeasured as v2. V1 remains historical evidence. A gain over the slow reference is not a speedup over native SDPA. Operator diagnostics point to indexed gathering/copying as remaining costs; assess locality/fusion before another execution change. Do not hide padding, extra storage or mandatory metadata/validation.

The [fixed-data duration diagnosis](experiments/training-duration-diagnostic-v1/SUMMARY.md) repeats 100/300/1,000-step budgets on the same training/validation corpus. Original 100-step references reproduce exactly. Longer budgets reduce validation error modestly at slightly greater counted work; validation is also used for checkpoint selection, so this is not new generalization evidence. The selected 1,000-budget checkpoints occur at 450/580/810 steps. Next training work must distinguish unique-data coverage from duration and reserve a new sealed cohort.

Continue using the [experiment plan](docs/NEXT_EXPERIMENTS.md), with these measured outcomes. New precision/GPU kernels, a real long-context adapter, incremental updates and closed-loop generation remain separate gates. No practical dense-attention speed benefit or whole-model quality claim has been established.

The successful study is bound to commit `dc8b5c7`; the prior serialization-only failure at `bb44d48` is preserved. There are 254,016 raw validation/test records, 63 reference checkpoints, 60 verified native captures and 24 independent scalar checks spanning all geometries/contexts. Protocol, corpus and validation choices were fixed before test evaluation.

The completed M2 run is bound to preregistration commit `421e2bce01e6c6b515fa5017ec90c2314f39bf6e`. All three seeds lower held-out pooled KL; at threshold 0.73, mean output L2 error falls 11.9% versus sampled-query initialization. Backbone hashes stay identical; native capture and saved-checkpoint reload checks pass. All 5,184 query records, 27 configuration aggregates, small reference checkpoints and a measured plot are saved under `experiments/gpt2-layer5-pilot-v1/`. These are one-layer, 256-token, two-test-book observations, not paper benchmark reproduction.

## Findings corrected during implementation

- Enforced work limits before materializing selected-ID collections, including dense fallback.
- A flattened requirements export could not reuse all cached wheels during fresh offline installation. The installation check now populates each fresh environment directly from `uv.lock` without installing the editable project, then installs the built artifact. An isolated Python import verifies that the source checkout is not masking a packaging failure.
- The actual random-reference example retains about 45–48% of dense attention mass at its chosen routing setting. This is reported as imperfect untrained behavior, not hidden by choosing a favorable example or represented as model quality.
- The first hosted run rejected a runner-only context used in a job-level environment field. The workflow now uses a literal workspace cache path, following GitHub's context availability rules. Hosted verification remains pending until an actual run passes.

## Separate lifecycle lane: source freeze

The restored forgetting/recovery direction is scoped in [the lifecycle contract](docs/MEMORY_LIFECYCLE.md). The new experimental `research/memory_lifecycle.py` uses a shared lexical scorer to isolate retention, not the ZHA router. Original records are immutable and survive reopening; only the hot set is bounded. Session-use metadata is not persistent. Corrections use explicit keys; semantic contradiction detection, replay-based model training, hierarchy maintenance and a real assistant remain open.

The fixed diagnostic protocol and source are committed before execution. Seven policies include full-memory, FIFO/LRU/LFU, decayed access, scheduled query probing and coverage replay. Replay must pay its row reads, comparisons and latency; it is not presumed superior. The authored stream is a mechanism diagnostic, not a sealed quality evaluation.

Verified before execution: `UV_CACHE_DIR=/private/tmp/ohm-m2-uv-cache uv run --locked --offline --extra research python scripts/verify.py --profile core` passes 174 tests, Ruff, formatting, strict typing of seven installed-core and four lifecycle modules, all ten core semantic faults and all five lifecycle faults. The first verification stopped on an unused audit variable; it was removed and the complete command rerun successfully. No package or workflow changes require fresh wheel/hosted checks. Hosted CI remains blocked by the existing billing restriction.

## Lifecycle diagnostic outcome

The [v1 result](experiments/memory-lifecycle-v1/SUMMARY.md) is bound to source freeze `dda4d4b`. All 42 runs preserve 80 originals each and their 8/16 hot limits. The separate audit verifies 5,376 queries and 3,360 original-record instances. At capacity 16, replay retrieves 90/128 current records overall, query-time probing 46/128 and decay alone 32/128. Replay uses about 59.3% more comparisons than probing and has higher descriptive p50/p95 query latency. Crucially it retrieves only 4/24 delayed rare queries, versus 0/24 for the two non-replay bounded comparators. Capacity-8 replay also misses all delayed queries. The aggregate improvement is not reliable cold recovery.

All three permutations have identical aggregate hit counts; this authored diagnostic is now development data, not three independent real datasets. There is no ZHA speed, semantic-memory or assistant-quality result. Next: stronger query-aware recovery/cue specificity under matched budgets and new stream structures, then a separately validated hierarchical semantic adapter. Do not ship the current controller behind a claimed reliable assistant. Controller metadata persistence, consolidation and associative dynamics remain open. The original numerical core and package are unchanged.

Reproduction and audit commands are in `docs/MEMORY_LIFECYCLE.md`. Final source verification passes 174 tests, Ruff/formatting, strict typing and all ten core/five lifecycle faults. Three copied-evidence faults are detected, and an actual local CLI subprocess correction/restart flow passes. No paid compute, new service, public release or workflow change was made.


## Somna: first observed-spatial integration

The user authorized a separate ZHA/memory research workstream alongside neural-fields. Somna is a working title; repository/package names are unchanged. The [theory and claims contract](docs/SOMNA.md) maps the implementation to ZHA, Dyna, prioritized replay and Working Memory 2.0 and states the remaining learned-latent/dreaming gates. No novel algorithm, brain replication, speedup or production readiness is claimed.

`research/somna_spatial.py` connects the actual numerical ZHA index to immutable observed spatial transitions. The returned selected-attention mixture supplies each offline Bellman target without exact-record fallback. Identical wake values and archive hashes branch into no-update, uniform replay and exhaustive residual-priority scheduling. Only persistent tabular Q values are consolidated; this does not implement learned neural parameters, forgetting, a visual encoder or latent imagination. No simulator/future evaluation labels enter the offline API.

The [v2 fixed run](experiments/somna-spatial-v2/SUMMARY.md) preserves three evaluation mazes plus separate development seed7. On known maps from previously untested starts, priority solves48/48 versus1/48 for both wake/no-update and uniform at256 updates per world. Both dense and ZHA have the same results. Priority additionally scans147,456 exact observed transitions, so equal update/read counts are not equal compute. Its complete canonical access and unique state/action keys mean ZHA is unnecessary in this task; ordinary keyed lookup/graph planning is a strong ceiling. The independent graph audit confirms all48 starts are reachable. The gain is ordinary reward/value propagation, not unseen-layout transfer or new affordances.

Across576 evaluation transition queries, ZHA selects the correct observed episode and successor every time, using9/193 raw keys per read. Maximum probability disagreement with dense is below2.7e-14. This relies on costly idealized one-hot keys and49 untrained state-basis references. Each read also computes539 summary dot products; measured execution is slower than dense. An initial false uniform-sparse advantage was traced to negligible softmax spill altering exact greedy ties. The fixed protocol declares a1e-10 decision/scheduler tie band, without changing attention arithmetic, and preserves the negative efficiency result.

V1 retains the original desktop inspector; v2 reruns the same numerical protocol with a readable stacked mobile canvas and playback controls above the visualization. Every frame is audited against raw values and routing records. Frozen source snapshots and protocol hashes accompany both versions; raw JSON is losslessly gzip-compressed with checksums. A fresh compressed-output reproduction in `/private/tmp/somna-current-reproduction` matches all fixed outcomes and work counts. Twenty-four inert JSON checkpoint round trips, including a fresh-interpreter reload, preserve persistent values after temporary replay state is discarded.

Verification: the expanded locked `scripts/verify.py --profile core` passes194 pytest cases, Ruff/format, strict mypy on7 installed-core,4 lifecycle and3 Somna/audit modules, all10 core and5 lifecycle semantic faults and the synthetic reference. Five additional Somna corruption controls detect target, selected-ID, original-archive, rendered-frame and work-total faults. The independent scalar auditor imports no numerical core and checks4,096 actual read/updates, recorded frames, frozen hashes, scheduling, work, final policies and graph reachability per version. The installed numerical core is byte-identical to the prior HEAD. No packaging/workflow changes require a new wheel/hosted run; hosted CI remains blocked by the previously confirmed account restriction.

Root-agent browser checks passed desktop and390px mobile: selectors, recorded stepping, frame slider, dense193/193/zero-summary state, disabled no-update playback and report links; no global horizontal overflow or browser errors observed. This verifies the shown flow, not all browsers or accessibility. The local preview is `http://127.0.0.1:8781/inspector.html`. No public release, deployment or paid service was created.

Next gate: ambiguous partial cues and many possible episodes without direct state identity, fixed learned representation/model, stronger exact/ANN baselines, bounded actual read/maintenance budgets and sealed new goals/layouts before claiming useful dormant-memory search or retrieval-conditioned imagination.


## Somna: live continuous memory and learned offline rehearsal

The [live operating guide](docs/SOMNA_LIVE.md) describes the implemented architecture, state boundaries, API, source grounding and limits. The root agent owns the live browser UI under `web/somna-live`; the new Python service serves it on loopback8791. It publishes immutable completed-step snapshots during actual neural training. No short recording is replayed as live progress.

Continuous partial cues have no state/episode identifier or expected-answer field. Multiple observations share cues. Actual ZHA traversal over all current dormant observations drives bounded reactivation, supplemented by separately charged16-row coverage pages. A second hierarchy reads the default48-record workspace. Explicit current-version heads exclude superseded originals from both indexes and model training. Raw pairs, reference-channel scoring, index rows/nodes/time/owned tensor bytes, recovery, scheduling, neural examples and dense audits are metered. Active limits do not bound total archive/RSS.

Observed tuples, explicit correction chains, usage/refresh metadata, cursors, neural weights and references persist together. Reversible forgetting retires active execution entries without deleting originals. Three action-conditioned MLPs learn actual observed transitions selected through memory; predicted rollouts have source/checkpoint provenance and remain separate from canonical observations. Their uncertainty/support gates are heuristics, not correctness certificates. The initial dynamics model is untrained, so improvements show offline acquisition from stored experience rather than preservation of an already trained skill.

The [corrected-coordinate v4 study](experiments/somna-continuous-v4/SUMMARY.md) preserves20 forks across two observed-data/model seeds. Each context tests192 new continuous states. Mixed replay improves common and rare MSE relative to initial parameters in both seeds; for seed7, common .006892→.002364 and rare .013586→.010781. Pure coverage favors rare motion at the cost of common motion; uniform favors common motion. Discarded-update controls return exactly to initial predictions. Exact top16 full-bank search approximates the dense teacher better than the bounded pipeline, and fitted references do not consistently improve outcomes. The [ordinary uniform observed-replay control](experiments/somna-direct-control-v1/report.json) learns common motion better while retaining less rare-context accuracy than the fixed mixture. Equal gradient/read limits are not equal compute or equal examples. No dominance, hierarchy necessity, novelty, biological dreaming or speed benefit is claimed. Dense learning controls vary the hot read; dormant traversal is held fixed. Full-bank dense/exact-neighbor diagnostics and ordinary replay provide separate unbounded controls.

V1 retains page-only cold recovery, v2 adds the dormant hierarchy, v3 adds the fixed1:3 rare/uniform mixture and v4 corrects the independently discovered nonperiodic-boundary alias. Earlier state cohorts became development evidence; v4 uses fixed1501/1502/1503 states. All prior snapshots and unfavorable outcomes remain. Historical snapshot sources bind numerical reproduction and are not the current live server release.

Independent review reproduced four correctness issues and confirmed their fixes at the recorded source hashes: -1/+1 cue aliasing, obsolete stored imagined paths after correction/rejection, reset restarting the old archive, and concurrent ownership during a reset pointer transition. The [review evidence](docs/evidence/somna-independent-review.json) includes actual before/after outcomes and fresh-process state/model hash equality. Current half/integer-frequency coordinates are injective over the clamped domain and versioned. Old reference coordinates/indexes migrate explicitly. Corrections clear forecasts and block stale model prediction until a fresh fit. A checksummed atomic active-session pointer makes the same CLI path resume the reset session. Separate POSIX locks protect the configured namespace across resets and each physical archive. Application.close() stops its worker before releasing ownership. Pointer-write failure restores the old controller. Regression tests cover the exact paused-reset interleaving and transaction rollback.

Final local verification:235 pytest cases pass; Ruff and formatting pass; strict mypy covers7 installed-core,4 lifecycle,3 earlier Somna and6 new live/control/audit modules. The ordinary core/lifecycle semantic faults still fail as intended. Nine new evidence faults detect attention, gradients, sources, future labels, loss, evaluation, cold routing, work and fabricated trajectories. Independent auditors reconstruct3,200 actual ensemble SGD steps,8,448 held-out model predictions,256 additional retrieval diagnostics and learned rollout transitions across the final study plus ordinary control. Cross-fork checks bind the same observed banks, initial weights and evaluation inputs. No simulator is called during offline updates; a test makes such calls fail. Restart, interrupted jobs, maximum2,048-record budgets, current-version exclusion and owned state are tested. Installed numerical core bytes, dependencies and packaging are unchanged; hosted CI retains the previously confirmed account restriction. No paid infrastructure, public release or deployment was created.


## 8 November 2026 — live browser integration

The live UI is installed and verified against the final backend. Screenshots and returned-state evidence are bound to source hashes in `docs/evidence/live-ui-verification.json`. Desktop at 1512×982 and mobile at 390×844 were visually inspected; neither has global horizontal overflow. Local Geist fonts retain their OFL license.

The UI now renders separate dormant and active hierarchies, actual selected source edges, partial-cue spans, versioned record inspection, reversible restoration and learned paths with separate imagined provenance. Browser actions verified a ZHA partial read, dormant restoration without changing original count/checksum, appended correction with stale-source exclusion and forecast invalidation, then a fresh 160-update memory cycle. The browser observed 17 distinct progress counts from 0 to 160; weights changed, 234 observed source IDs contributed, and a ten-step learned path completed. A further 80-update job verified that replay markers follow the actual read rather than the manual cursor. Phone and desktop displays were inspected after that correction.

Final UI checks: Node `--check web/somna-live/app.js`, Prettier `--check` for its HTML/CSS/JS and `git diff --check`. Backend checks remain the 235-test locked core gate, typing/lint/mutation checks and independent numerical evidence audits. No public release or speed/novelty claim is made. Use `uv run --locked --extra research python -m research.serve_somna --archive /tmp/somna-live.sqlite --port 8791` and open `http://127.0.0.1:8791/`. A configured-session pointer resumes reset-created archives; do not run multiple controllers against the same archive.

## 8 November 2026 — official complex planning tasks

Implemented and executed two separate retrieval-in-planning benchmarks. These test ZHA-backed evidence selection inside shared classical controllers, not a trained LLM agent, biological dreaming, the separate neural-dynamics learner or industrial deployment readiness.

- Official Google DeepMind Boxoban: pinned source/license, 32 solved training puzzles, 363 source-bound cases, 32 distinct held-out puzzles, seven reader configurations and two expansion budgets (448 runs). Exact legal pushes, reachability, static dead squares, safe blocked-square pruning, matching bounds and weighted A* are shared. No state-ID keys or test solutions enter retrieval. All 49 failed evaluations remain.
- Official MiniGrid 3.1.0 / Gymnasium 1.4.0: MemoryS17Random, MultiRoomN6, DoorKey16 and KeyCorridorS6R3. The actor receives only official partial observations and its own action/compass history. Recalled facts plus current visible cells rebuild each planning view; no hidden full-map cache or true simulator pose enters it. Seven readers share the controller, 96 historical slots and 16-pose history. Development seeds 0/1 precede untouched evaluation seeds 1001–1003.
- The separately labeled adaptive ZHA wrapper widens candidate selection only when it underfills slots. Every pass and p=1 fallback is counted. Fixed-p ZHA and all simple baselines remain. No success, connectivity oracle or future data triggers widening.
- A read-only loopback inspector at port 8792 displays actual puzzle routes, hypothetical search states, official maze observations, selected facts/cases, costs and same-condition comparisons. Desktop and 390px layouts and source/outcome changes were verified through browser actions. Raw benchmark evidence remains separate from the viewer.

### Measured outcome

The ordinary Boxoban test subset is a ceiling control: all conditions solve 16/16. At 1,024 expansions on the hard subset, geometric search solves 14/16 while dense, exact top16 and both ZHA thresholds solve 15/16. ZHA is slower. The scalar case target is weak (346/363 gaps zero); small ranking changes, including shuffled targets, alter individual near-budget outcomes. This is not established semantic insight or a hierarchy benefit.

Formal MiniGrid (three seeds per task, 84 total episodes): fixed ZHA 1/12, adaptive 3/12, exact 5/12, recency 4/12, FIFO 3/12, none 0/12, full observed memory 12/12. Adaptive repairs a development underfill but does not generalize the MultiRoom gain; every bounded reader fails DoorKey/KeyCorridor. All 56 truncations are preserved, with no exceptions or external cutoffs. Five p=1 fallbacks were independently verified. Adaptive Memory reads the entire small candidate bank on all 39 actions, so its 3/3 there is not a sparse-scaling result. First same-history MultiRoom action divergences persist even when both exact and adaptive return 96 facts.

### Validation and corrected findings

Full locked verification with research and benchmark extras passes **324 tests**, active-code Ruff/format, strict typing, existing mutations, both prior neural-evidence audits, the new puzzle/maze auditors, and fresh isolated wheel/source installations. The benchmark extra also passed a fresh installed-wheel official-environment reset/step smoke check. Hosted CI remains the previously documented account-side restriction; local verification is not hosted success.

The independent task auditor checked 5,852 legal puzzle pushes, 96,517 scalar case reads and 79,961 recorded search priorities. It separately replayed all 84 formal MiniGrid episodes: 75,520 official transitions, 10,321 fact versions, 89,170 query routes and 43,066 routing passes. Controller isolation and corrupted-evidence tests complement these artifact audits; the auditor does not reconstruct complete heap ordering or reprove the mathematical router.

Independent review found a reader-reuse alias/cumulative-counter bug, fixed before the Boxoban freeze with an exact state regression. It later found two v1 freeze omissions: individual numerical-core files were not prefrozen, and evaluation trusted the current data manifest. Current v1 data/core match the recorded sources and are separately attested; these limitations remain in its summary. The future runner now freezes every core module, compares the frozen data manifest and rejects tampering. Original snapshots/results were preserved. Frozen source copies are intentionally excluded from active-code linting; their exact bytes are evidence, not files to reformat. A behavior regression verifies that recalled guidance changes actual selected search states.

Commands and result records: `experiments/boxoban-search-v1/SUMMARY.md`, `experiments/minigrid-evaluation-v2/ANALYSIS.md`, `docs/ZHA_TASK_REVIEW.md`, and `docs/evidence/local-verification.json`. The standard `scripts/verify.py` gate now includes the new typed modules and task audits. Numerical core bytes remain unchanged. No public release, deployment or performance claim was made.

Next research gate: task-relevant evidence bundles and a retrieval-to-planning interface that preserves required dependencies, compared with equally informed exact/map baselines at matched quality and total cost. Simply increasing maze size, returning more slots or using a larger machine does not establish that contribution.

## 9 November 2026 — observed coverage and dependency-preserving retrieval

Implemented a separately tested observation-to-planning adapter. It supplies whole raw-fact bundles containing nominated landmarks, observed adjacent routes, accessible matching-key/cue prerequisites and one-hop observed-neighbor support. Missing prerequisites and overbudget unions produce explicit rejection receipts. The common planner consumes returned raw facts, current observation and a separately declared observed-known mask; it never consumes the reader's proposed action, nominated target or route receipt.

The fixed 64x64 mask transports 512 binary bytes plus counted JSON/version/hash overhead. It only suppresses exploration frontiers made from previously observed but omitted cells. It cannot supply object labels, passability or movement through absent facts. Capacity remains 96 returned historical facts plus this additional channel; full archive/graph storage and computation are not bounded by that capacity. New controls include unchanged adaptive/exact/full/none policies, flat ZHA/exact plus mask, exact historical-only selection, three identically packed bundle seed readers and ordinary all-observed graph nomination. No new dependency, lockfile, numerical-core, model or GPU change was required.

### Fresh result and limitations

After development and independent source review, froze all executed policy/reader/core sources and the protocol before evaluating seeds 2001–2006. The 264-episode cohort contains four tasks and 11 conditions. Original adaptive ZHA solves 7/24, flat ZHA plus mask 20/24, and ZHA bundles 20/24. Exact mask solves 19/24, exact historical-only mask 21/24 and exact bundles 19/24. Recency bundles solve 19/24. Full observed memory and ordinary graph bundles each solve 24/24; none solves 0/24. All 82 official truncations remain, with zero exceptions or external cutoffs.

Paired controls show 13 mask rescues for ZHA and 10 for exact with no solved-case losses. Bundles add no success gain over either corresponding flat-mask reader. Exact bundle actions match its flat-mask control in all 24 cases; ZHA matches 22. Graph actions match full observed memory in all 24 cases. Bundles reduce raw facts crossing the planner boundary, but pay full graph/BFS and receipt costs. Different action counts and histories prevent matched-compute speed claims. This establishes a useful coverage-interface repair and a bounded-output graph integration, not ZHA superiority, new navigation theory or dreaming in MiniGrid.

### Verification

The full locked verification gate passes all 17 checks: 382 tests, Ruff/format, strict mypy, both mutation suites, previous numerical/neural/official-task audits, the new independent formal audit and fresh wheel/source installations. The new audit verifies all 264 episodes, 110,470 official transitions, 45,093 observed fact versions, 200,941 seed-query routes, 32,998 dependency reads and 19,173 recomputed bundles. No declared work category is missing. Fifty component/legacy tests and 33 independent counterexample tests cover coverage semantics, stale/future IDs, false support/prerequisites, corrupt receipts, unreachable gaps, key accessibility, budgets, correction invalidation and information-channel isolation. Numerical-core bytes remain identical to the previous commit.

The inspector now exposes every completed dependency cohort, omitted-known outlines, packed support edges, local completeness/rejection receipts, per-read graph work and explicit legends. Browser evidence verifies reader switching, actual timeline pixel changes, fresh source identities, mobile390 without overflow and no browser errors. Actual expanded traces reached 71,228,119 bytes; the endpoint now enforces a bounded 128MiB expansion allowance, still requiring safe catalog paths, checksums and a 16MiB compressed limit. An exact-boundary regression and an HTTP200 fetch of the largest real artifact verify the fix.

An independent post-hoc prefix diagnosis reproduces the omitted-known frontier problem. All 56 old no-mask development episodes (49,612 observation steps) reproduce every action and non-time decision/query/selection/work/version field. Independent review additionally checks set-based diagnosis and a separate legacy replay. The early audit-reference mismatch came from legacy versus current unreachable-landmark receipts; it was fixed in the version-aware auditor before formal validation, with original artifacts retained. The earlier development snapshots remain historical evidence.

Use `uv run --locked --extra research --extra benchmarks python -m research.serve_task_benchmark --port 8792` and open `http://127.0.0.1:8792/?task=dependencies`. See `docs/PROJECT_OVERVIEW.md`, `docs/DEPENDENCY_REVIEW.md`, `experiments/dependency-evaluation-v1/ANALYSIS.md` and the source-bound browser/audit evidence. The standard verification command includes the new typed modules and independent formal audit. No public push, release or deployment was performed; hosted CI was not reclassified as successful.

## 9 November 2026 — progress-aware retrieval and inspector cleanup

Fixed an operational gap in the separately named progress readers: repeated poses and no novel observed payload now trigger directional queries, a wider 192-candidate pool and, when permitted, explicit full-observed-head seed recovery. The common planner, numerical core and original controls remain unchanged. Returned historical facts remain capped at 96 plus the 512-byte observed-known mask. Every variant still builds an observed graph for dependency closure; 'without fallback' does not mean graph-free or sublinear.

The fixed 168-run cohort covers four tasks, seven conditions and seeds3001–3006. Original bundleZHA solves 19/24, exact 18/24 and graph 23/24. Query+widening repair solves 23/24 for ZHA and 24/24 for exact. Fallback-enabled ZHA solves 24/24, with 16 full-bank reads in one episode; exact needs none. All 13 official truncations remain; no exceptions/cutoffs. This supports recovery from the demonstrated stall, not a ZHA advantage, isolated cue effect, speedup or new algorithm.

A first-pass transport failure is retained with 167 artifacts and an incomplete-run receipt. The wire-only same-cohort rerun changed no policy or seeds. All 167 retained cases match 25,320 decoded non-time steps; the missing 168th raw artifact cannot be claimed identical. Content-hashed event/layout banks retain every occurrence and work count. Maximum expanded trace77,310,857bytes fits the unchanged 128MiB bound. Source tensor labels remain separate from versioned layout identity.

Rebuilt the UI around the maze, recorded cue/pass and actual hierarchy layers. True core spans and original IDs drive node inspection and connectors; historical traces without metadata receive no invented links. Full-bank recovery explicitly replaces the unused hierarchy. Added recovery jumps, simpler task/run controls, visible mobile playback and an advanced counter/receipt panel. Removed repetitive copy. Historical/development runs remain distinct from current evaluation playback.

Oversized artifacts receive a recoverable HTTP 413 response; failed loads clear stale evidence and disable playback. Browser checks verify both layouts, cue/node inspection, recovery jumps, real graph-fallback display, mobile390 without overflow, and loading-error recovery. Node contracts check span/edge membership, returned/raw distinction, compact references and future/missing-source rejection.

Full verification passes all 19 checks: 428 tests, Ruff/format, strict typing, mutation suites, previous artifact audits, the new independent numerical/progress audit, Node routing contracts and fresh wheel/source installations. The new audit checks all 168 episodes, 27,880 official transitions, 7,772 repaired reads, 63,910 hierarchy-route occurrences and 2,169,576 affine scores. Independent aggregation and decoded 167-case parity attestations agree. Core/planner bytes remain unchanged. Detailed source-bound browser evidence is saved separately.

Results and operating details: `experiments/progress-evaluation-v2/ANALYSIS.md`, `SERIALIZATION_PARITY.json`, `docs/PROGRESS_RETRIEVAL.md`, the independent review and `docs/evidence/progress-inspector-browser.json`. Open `http://127.0.0.1:8792/?task=maze`. No public push/release or change to the separate neural-fields/live-learning application.


## 9 November 2026 — shared scientific spatial renderer

Applied the user's layered scientific references to the live memory field and recorded hierarchy with a shared, locally served Three.js0.187.0/OrbitControls + GSAP3.15.1 renderer. The existing Python apps and Canvas fallbacks remain. New interaction includes orbit/pan/zoom, source hover lenses, original-record/node inspection, Home/Focus read, fullscreen and reduced-motion behavior. Neither camera animation nor graphics buffers change the numerical engine, retrieval policy, planner or archived experiment data.

Live planes encode actual context and capped salience; arrows encode observed transitions and a separately marked recalled displacement. Partial cues use stripes without exposing unknown coordinates. Violet rings identify only actual sources of an active replay update. Recorded hierarchy levels use real source spans and observed group centroids, with exact kept edges and a separate returned/raw distinction. Graph decisions hide the unused hierarchy; traces without spans keep their limited original representation. Cache keys include archive/environment identity. Fixed responsive framing after discovering that larger later hierarchies could be clipped.

Verification: 429 Python tests, 11 visual-mapping tests, existing Node routing contracts, Ruff and format (148 files), strict mypy (7 files), both app syntax checks, fresh pinned npm installation with scripts disabled and reproducible bundles/styles all pass. Desktop1440 and mobile390 checks cover actual pointer selection, partial retrieval, camera drag without accidental query, node keyboard inspection, Layers/Tree switching, fullscreen, reduced motion, forced Canvas and automatic WebGL failure. Verified graph-only display and the explicit recovery at DoorKey16 seed3003 step79. Clean browser sessions have no unhandled errors. Live tests used an isolated archive on8793; the user's8791 process/archive was not restarted or reset.

Design meanings, rebuilding and limits are in `docs/SCIENTIFIC_VISUALS.md`; source-bound checks are in `docs/evidence/scientific-visuals-browser.json`. This is a presentation improvement, not evidence of speedup, learned spatial embeddings or new experimental outcomes. No public push or release.


## 9 November 2026 — observatory composition and visible motion

The user rejected the first spatial UI as sparse and visually unlike the supplied references. Rebuilt the task layout around a large central scene, compact navigation and a source inspector; aligned the live console's frame and typography. Upright source-value plates and a separate canopy projection preserve real original IDs, recorded span membership, scores and kept edges. Added channel glyphs with exact-value hover/legends, population bars, quadratic connections, branch tube geometry and restrained bloom. These are display projections, not learned representations or new model dynamics.

GSAP now supplies visible staged entrance/material reveal, bounded read-path replay and camera/focus/view transitions. Browser samples verify movement and termination on actual recorded edges. No decorative simulation loop or measured-compute-timing claim. Fixed replay-source cache invalidation, source-population clearing at graph recovery, portrait atlas identity and Canvas preference preservation. Read-only links retain selected step/view. Playback fits the 1600×900 desktop viewport; mobile390 has no horizontal overflow.

Verification passes 429 Python tests, 16 source-mapping tests, existing routing contracts, JS syntax, Ruff/format and strict mypy. Browser checks cover point picking after transformed projection, both 3D views, orbit/focus, reduced motion, Canvas fallback, graph recovery and live partial retrieval in an isolated archive. The live8791 server, algorithms and experimental recordings remain unchanged. A browser wait with incorrect expected hint text was cancelled; the isolated archive confirms the correct [false,true] query, eight read originals and all256 sources retained. Actual IAB automation was unavailable; browser verification used Chromium. The 34.2-second MP4 is an actual UI recording.

See `docs/SCIENTIFIC_VISUALS.md` and `docs/evidence/observatory-redesign-browser.json`. No public push or release.


## 9 November 2026 — one unified dashboard

Replaced the separate task/live entry pages with one workspace on8792. Both existing structures are visible by default, with larger viewport areas, a narrow control rail, the actual navigation thumbnail, a shared source inspector and focus layouts. Only Play and Run memory cycle are default visible workflow buttons. Secondary run/query settings and camera actions are behind disclosures. The prior8791 page redirects to this same dashboard. The archive API process remains the existing owner; no database reset or engine restart was needed.

The same-origin view modules expose explicit snapshot/command adapters and retain separate experiment state. Changing observation/projection views preserves the recorded timeline. Canonical run URLs come from actual controller identities. A bounded loopback gateway forwards only the approved live operations; task artifacts remain read-only. Origin checks, finite JSON/body limits, protocol/schema checks, reply limits, disabled operations, proxy/redirect exclusion and typed read-timeout/outage errors have regression coverage. This unifies the UI, not the numerical experiments or their provenance.

Browser checks verify both connected panels, reduced default controls, timeline/projection/focus commands, source picking into the common inspector, cue draft persistence, an actual returned partial query, the mobile control drawer and a complete isolated live-memory cycle. The isolated archive grew256→288 and completed160 learning updates; the selected recorded task stayed unchanged. The user's live archive retains480 originals and the identical source checksum across migration. At390px there is no horizontal overflow; focus view uses a389×691 frame.

Final checks:439 Python tests,16 visual tests, existing Node routing contracts, JS syntax, Ruff/format and strict core/gateway typing all pass. Browser error histories are empty. The rendering bundle, embedded style and shared boot assets match their build manifest in both view modules. No numerical-core, planner or frozen-evidence changes; no public push/release. The visual references were the supplied scientific figures, Vitessce's multi-view approach and the Three.js editor's viewport/sidebar proportions; no external code or assets were copied.

See `docs/UNIFIED_DASHBOARD.md`, `docs/evidence/unified-dashboard-browser.json` and the current root dashboard. Earlier milestone evidence remains separate.


## 9 November 2026 — one Solve action, one task memory

The user found the two start paths conceptually disconnected. Replaced the default recorded-playback/independent-cycle pairing with a fresh MiniGrid solve. The hierarchy, navigation inset, observed/returned memory field and Observe / Retrieve / Plan / Act receipt share that solve's selected decision. Saved examples retain source labels. Camera/query settings remain disclosed; the continuous archive is now an explicitly independent advanced view. There is no claim that the maze trains the separate neural-learning engine.

Added a post-action observer to the existing runner and a bounded single-worker service with finite same-origin JSON commands, incremental pages, owned route/layout banks, run identities, cancellation, explicit failures/cutoffs and refresh recovery. Neither the planner nor the numerical retrieval policy changed. The UI auto-plays published decisions at a separate configurable display pace. The field uses current observed heads and exact returned IDs, rejects future facts and invalid source references, and shows categorical observed/returned layers rather than fabricated salience. Source inspection is shared, including keyboard access. Boxoban recordings remain available; fresh solves support the four MiniGrid families.

The four task checks at seed3002/cap512 solve in14,63,58 and95 actions respectively. These are workflow diagnostics, not new benchmark superiority/generalization claims. Browser checks verify real start, paced3→7 progression over1.2s, matching memory/cursor identity, original inspection, stop after9 computed actions, a fresh DoorKey restart solving in58, refresh recovery, Canvas completion, optional archive access and390px mobile without overflow. The archive owner process was not restarted; its1024 originals and checksum remain unchanged across the main dashboard switch. Early missing-label and fallback/pacing defects found in testing were fixed; final fresh-browser errors are empty.

Validation:452 Python tests;17 visual mapping tests; Node routing contracts; JS syntax; Ruff/format154 files; strict mypy core7 and gateway/solver2 files all pass. No numerical-core, planner, retrieval-policy or frozen-evidence changes; no public push. See `docs/UNIFIED_DASHBOARD.md` and `docs/evidence/task-solve-dashboard.json`.


## 10 November 2026 — quieter instrument UI and smooth navigation

Moved the maze to the top of a wider rail, increased its display height144→240px and replaced scaled bitmap copying with direct full-resolution controller painting. Simplified neutral chrome/type/separators, subdued semantic colours/line opacity, exposed human-readable planner objectives, and added a faint antialiased3D context floor. Shared labels avoid collisions. The grid is view context, never experiment data.

Camera bounds ease without returning to home orientation. A bundled, independently tested pose tween uses only adjacent observations from the same episode; scrubs, source changes and reduced motion remain exact. Rendering is animation-frame driven and idle navigation avoids repainting. This changes presentation only. The active8792 and8791 owners were not restarted; the original solve can still be resumed. GitHub primary references were Drei Grid and Three.js dynamic draw-range; no code was copied or React/dependency added.

Validation passes452 Python tests,21 visual/motion tests, routing contracts, Ruff/format154 files, strict mypy7 core and2 gateway/solver files, plus JS syntax. Browser checks verify intermediate render positions,16 exact reduced-motion samples, Canvas fallback,390px no-overflow/action fit, source picking, focus layouts and a fresh95-action solve. Early extraction/loading defects were caught in QA and repaired. Final main/reduced/Canvas sessions have no errors. No FPS or numerical performance claim. The next persistent-task wake/replay/forget experiment remains proposed, not implemented by this UI pass.

See `docs/UNIFIED_DASHBOARD.md` and `docs/evidence/refined-observatory-ui.json`. No scientific implementation changes or public push.


## 13 November 2026 — cybernetics instrument and unbranded workspace

Replaced the prior neutral observatory shell with the user's dense scientific instrument direction: dominant height-field/point-cloud activity, a retained hierarchy viewport, black backgrounds, spectral colours, wireframe bounds, compact telemetry and five source-linked diagnostics. Retrieval-frequency height/colour use only reads through the selected decision, accumulated per observed location. Dense geometry remains separate from original source counts, and source selection retains real current-head IDs. Zero counts, invalid prefix counts, future observations, foreign IDs, interpolation bounds and immutable ownership have six new visual tests. The numerical core, planner, solver and frozen recordings are unchanged.

Removed the complete SOMNA masthead/top strip at the user's request. Moved layout selection into the rail; kept the mobile drawer accessible without a top bar. Fixed cross-browser Home/End timeline cursor/value agreement discovered in QA, zero-peak reporting, compact layer labels, unavailable-view diagnostic clearing and truthful Canvas labels/counts. The maze remains sticky at the top of the rail.

Validation: 452 locked Python tests, 27 visual/motion tests, routing contracts, JS syntax, Ruff/format154 files, strict core7 and gateway/solver2 files pass. Browser verification covers a fresh Key Corridor seed3002 solve (95 actions), first/final shared decisions, four field projections, keyboard original inspection, the 390px drawer/focus layout with390px document width, and the forced Canvas map. The browser emits an unattributed MutationObserver error on some reloads; no MutationObserver occurs in served app sources and the completed application flows were checked directly. Its origin remains unresolved; it is recorded as a browser console error rather than a clean-console claim. Final screenshot shows the header-free workspace; temporary QA tabs were closed and the viewport override reset.

See `docs/SCIENTIFIC_VISUALS.md`, `docs/UNIFIED_DASHBOARD.md` and `docs/evidence/cybernetics-instrument-ui.json`. The8792 service was started for this session; no continuous archive backend was started or reset. No public push or release.


## 13 November 2026 — persistent task memory and fitted references

Reviewed the numerical ZHA contract, hand-set task references, full-observed graph support and separate continuous learner before implementation. Added a separate CLI adapter with240 genuinely optimized reference values (eight30-dimensional queries), versioned immutable observed facts, single-writer transactional storage, a96-fact active workspace including current observations, usage/age retirement and explicit ZHA/exact cold recovery. Superseded versions cannot return; a new reset/frame requires a new context. Original evidence remains stored. Graph packing is restricted to active/explicitly recovered payloads, with separately declared known-only coordinate coverage. Index rebuild reads, owned tensors, hot scoring, archive retrieval/reranking and graph/BFS work are metered. A budget interruption is visible and cannot silently trigger exact search.

The preserved v1 comparison contains40 official episodes: no recovery/exact solve8/8 each, while fixed/random/fitted ZHA solve6/8 each. Investigation found that scoped support could nominate unavailable-but-known neighbours as unexplored frontiers. V2 adds the known-only frontier correction plus a persisted coordinate-coverage/pose recovery gate and an always-recover control. All48 v2 episodes solve. Always-recover ZHA also solves8/8, so gating alone is not shown to cause success recovery. Gating sharply reduces archive work on these paths, but this is not a speedup or ZHA-superiority result. V2 deliberately reuses exposed v1 seeds and is labelled development; untouched-seed policy validation remains open.

Fitting uses train seeds0/1, validation2, comparison9001/9002:48/24/47 numerical prefixes after one duplicate removal,40 optimizer steps. Train KL falls0.007067→0.005186; validation0.004930→0.003544. Comparison fitted KL0.004354 improves on fixed0.005719, while random is better at0.000561. Fitted retention is slightly below fixed; task success is unchanged. The delayed-clue diagnostic separately demonstrates recovery with observed path support after reopen, immutable originals and correction isolation; no-recovery cannot retrieve the dormant clue. It is authored, not another held-out benchmark.

Independent auditing imports no production router/feature/summary construction, replays official actions and checks source/current-head/hot-cold lineage, recorded top-p ownership, sampled affine numerics and offline mass. V1 covers2,719 decisions/3,930 routes/24 numerical cases; v2 covers2,356 decisions/864 routes/20 numerical cases;315 mass cases each. V1's frozen exact-threshold auditor required an explicitly documented1e-12 roundoff band after native/scalar reductions disagreed at exactly0.8. Scientific data/core were not changed; the original successful audit and current versioned re-audit both remain. The audit does not reproduce the optimizer trajectory or certify performance.

Validation passes `python scripts/verify.py --profile core`:475 locked Python tests, Ruff/format, strict core and research typing, semantic mutation checks, existing task audits and both new audits (21 commands). `node --test web/visuals/test/*.test.mjs` passes27 checks. `git diff --check` passes. New state/behavior tests cover rollback, immutable ownership, source/correction/future/context isolation, single writer, restart, budget failure without fallback, active-only graph construction, gate persistence and phantom frontiers. No installed-core/package/UI files were changed. Source/protocol snapshots and all negative outcomes are retained; mutable SQLite archives are ignored by Git.

Use `python -m research.run_persistent_tasks --output experiments/persistent-task-local` with a new output directory and locked research/benchmark extras, then `python scripts/audit_persistent_tasks.py --results experiments/persistent-task-local`. The current8792 dashboard still uses the previous readers. This task adapter has no sleep, learned consolidation or imagined writeback; those and dashboard wiring remain subsequent gates. See `docs/PERSISTENT_TASK_MEMORY.md`, both versioned `SUMMARY.md` files and `docs/evidence/persistent-task-integration.json`. No public push or release.


## 13 November 2026 — dashboard integration of persistent task memory

Connected the existing Solve workflow to the reviewed persistent task reader. Fitted reference vectors now load from the frozen v2 checkpoint, with fixed/random/always/exact/no-cold controls in the same Method menu. Saved development evidence is the default entry; Run solver runs a fresh official episode. Each run retains an individual SQLite archive, reference checkpoint and completion record under ignored `var/task-solves/<id>/`. The independent continuous-memory service and its archives were not started, reset or changed.

A presentation adapter owns and bounds published rows, deduplicates route/layout banks and checks current-head/active/recovered source identity before publication. Complete-chunk node extents come from the declared geometry; actual scores/kept nodes remain those of the router. The observer now publishes official pre-action observations; parity tests preserve actions, selected sources and controller state. Saved v2 images are reconstructed by official saved-action replay with reward/termination checks. No frozen experimental bytes or numerical-core formulas changed.

Added active/dormant/recovered planes, source rings, checkpoint/gate/work provenance and lifecycle telemetry while retaining the current scientific aesthetic. When no archive query occurs, the secondary view displays actual active payloads, labelled Archive idle, instead of a stale or invented routing animation. Observation-driven evictions are derived from adjacent active sets and separated from superseded corrections; explicit age/read events remain intact. Tests caught an incorrect expectation that this particular maze must show age retirement; it instead shows capacity evictions, now reported truthfully. Missing checkpoint errors fail visibly without fallback. UI method switches clear stale run links; completed-run refresh restores its selected decision and same worker evidence.

A fresh fitted Key Corridor seed 9001 run solves in 78 actions, retains 245 originals and 96 active facts, and passes completion reopen validation. Browser decision 58 matches 96 active / 92 dormant / 16 recovered / 31 returned. Temporal rewind returns decision 0 to 35 active / 0 dormant. The memory-event button finds actual events; exact-reader selection reports zero summary dots and no fabricated tree. Mobile 390px has 390px document width and an accessible Run action. Reduced motion suppresses trace replay; Canvas reports the same lifecycle counts. Browser errors are empty in these verification sessions. These are workflow diagnostics on exposed seeds, not fresh generalization or performance evidence.

Validation: 482 Python tests, Ruff/format, strict typing (including new adapter/solver), semantic mutation checks, historical and persistent independent audits all pass through the 21-command core gate. The 33 Node visual/motion tests, JS syntax checks, pinned renderer rebuild and `git diff --check` pass. `research/persistent_dashboard.py`, `docs/UNIFIED_DASHBOARD.md` and `docs/evidence/persistent-dashboard.json` describe source boundaries, archive paths and restart limitations. The integrated service is running on the usual 8792 address. No package changes, public push or release; sleep/consolidation remains outside this integration.
