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
- [ ] M3: persistence, trace inspector and scoped reference release (deferred behind useful execution/quality evidence).
- [ ] M4: numerically conservative bound/checker, if sound and useful.
- [ ] M5: audited positional adapter and closed-loop model conversion.

An adapter must move earlier if required by the selected real-model fixture. The completed GPT-2 adapter uses learned absolute positions; it does not close the RoPE gate. Only the measured routing-reference checkpoints are included; no converted model, GPU feature or checked-mass API is claimed.

## Current evidence

Local suite with research extras: 235 passing pytest cases, including 20 earlier Somna spatial/evidence cases and41 live-engine, HTTP and independent-audit cases; the earlier attention/lifecycle suite includes 60 generated routing configurations, 16 high-precision fixtures, native-model capture, fitting and data-isolation checks. Ten targeted core mutations and six additional batched-backend mutations are detected. Ruff, formatting and strict mypy check the package. The current [core verification](docs/evidence/core-verification.json) covers 235 tests plus code checks; the earlier [full verification](docs/evidence/local-verification.json) separately records fresh wheel/source installation checks. See also [mutation evidence](docs/evidence/mutations.json). Without optional research dependencies, GPT-2 adapter tests are explicitly skipped. The original pilot audit checks eight real queries and 27 aggregates; the cost-quality study audit checks 24 real queries, 567 test/63 validation aggregates and 254,016 raw records. These audits do not replace regular tests.

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
