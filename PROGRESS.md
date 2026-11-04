# Implementation progress

Last updated: 5 November 2026. This file is the current status; the dated planning documents describe earlier requirements, not completed capabilities.

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
- [ ] L1: fixed lifecycle diagnostic across seven policies, three seeds and two hot capacities, followed by raw-trace/archive audit.
- [ ] M3: persistence, trace inspector and scoped reference release (deferred behind useful execution/quality evidence).
- [ ] M4: numerically conservative bound/checker, if sound and useful.
- [ ] M5: audited positional adapter and closed-loop model conversion.

An adapter must move earlier if required by the selected real-model fixture. The completed GPT-2 adapter uses learned absolute positions; it does not close the RoPE gate. Only the measured routing-reference checkpoints are included; no converted model, GPU feature or checked-mass API is claimed.

## Current evidence

Local suite with research extras: 174 passing pytest cases, including 60 generated routing configurations, 16 high-precision fixtures, native-model capture, fitting and data-isolation checks. Ten targeted core mutations and six additional batched-backend mutations are detected. Ruff, formatting and strict mypy check the package. The current [core verification](docs/evidence/core-verification.json) covers 174 tests plus code checks; the earlier [full verification](docs/evidence/local-verification.json) separately records fresh wheel/source installation checks. See also [mutation evidence](docs/evidence/mutations.json). Without optional research dependencies, GPT-2 adapter tests are explicitly skipped. The original pilot audit checks eight real queries and 27 aggregates; the cost-quality study audit checks 24 real queries, 567 test/63 validation aggregates and 254,016 raw records. These audits do not replace regular tests.

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
