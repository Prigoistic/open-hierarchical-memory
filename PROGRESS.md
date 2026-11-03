# Implementation progress

Last updated: 4 November 2026. This file is the current status; the dated planning documents describe earlier requirements, not completed capabilities.

## Goal

Build a useful, readable independent ZHA research reference, then real model-layer experiments and a trace inspector. Keep paper approximation separate from any new guarantee. Publish only claims backed by evidence. Avoid expanding into a generic memory product before the core is verified.

## Milestones

- [x] M0: engineering plan, counterexamples and supported-contract review.
- [x] M1 implementation: owned CPU float64 snapshots, affine summaries, recursive tree, causal/head-local router, selected attention and explicit budget failures/fallback.
- [x] M1 local verification: independent scalar oracle, high-precision output oracle, generated cases, isolation/ownership/boundary tests and targeted semantic mutation checks.
- [x] M1 installed-release-artifact evidence: wheel and source distribution in fresh offline environments.
- [ ] M1 hosted CI evidence: GitHub reports startup failure before jobs/logs; static workflow validation passes.
- [ ] M2: implementation and protocol prepared; native capture/objective/split tests pass; three-seed pretrained-model pilot pending.
- [ ] M3: persistence, trace inspector and scoped reference release.
- [ ] M4: numerically conservative bound/checker, if sound and useful.
- [ ] M5: audited positional adapter and closed-loop model conversion.

An adapter must move earlier if required by the selected real-model fixture. No unverified model checkpoint, GPU feature or checked-mass API has been added to make the checklist look complete.

## Current evidence

Local suite with research extras: 70 pytest cases, including 60 generated routing configurations, 16 high-precision fixtures, native-model capture, fitting and data-isolation checks. Ten targeted semantic mutations are detected. Ruff, formatting and strict mypy check the package. See [the verification report](docs/evidence/local-verification.json) and [mutation evidence](docs/evidence/mutations.json) after running the verification command.

Hosted verification has not passed. The corrected workflow passes official actionlint 1.7.12 (checksum-verified distribution). The user confirmed an account-side restriction prevents hosted jobs from starting. Development can continue using the local core profile below. See [the run](https://github.com/Prigoistic/open-hierarchical-memory/actions/runs/41708001430) and [separate workflow evidence](docs/evidence/workflow-validation.json). Local success does not establish hosted CI success.

```sh
uv sync --locked
uv run --locked python scripts/verify.py
```

For normal code changes when hosted compute is unavailable:

```sh
uv run --locked python scripts/verify.py --profile core
```

The core profile writes `docs/evidence/core-verification.json`, preserving the full-profile report. It includes numerical tests and semantic mutations but explicitly excludes package-installation checks. Full verification is still required for release or packaging changes. No self-hosted runner, public repository exposure or account-setting changes are needed for this local workflow.

The numerical domain is CPU float64 with finite, moderate test inputs. Proposed core tolerance remains `atol=1e-10, rtol=1e-9`; passing cases do not constitute a universal numerical proof. Approximate routing can have substantial error. No accuracy, speedup, production-readiness, firstness or semantic-correctness guarantee is claimed.

## Engineering gate coverage

| Plan gates | Current state |
| --- | --- |
| V01–03, V05–11 | Implemented for the documented no-RoPE in-memory support contract; local oracle/regression evidence |
| V12–14 | Input/ownership/budget/fallback cases covered; disk corruption, cancellation and mutable-cache recovery are unavailable, not passed |
| V04, V15, V18–21 | RoPE, index persistence, bounds and inspector gates remain open |
| V16–17 | Reference-gradient exclusion, independent pooled-KL oracle and fitting-selection tests pass; pretrained-model pilot pending |
| V22 | Wheel and source distribution installed and exercised from fresh local environments; no package registry release |

## Review decisions

1. The repository name is `open-hierarchical-memory`; import namespace is `open_hierarchical_memory` instead of the plan's placeholder `open_zha`.
2. Keep the first remote private while validation and research work continue. No public launch or PyPI upload.
3. Preflight selected-key/dense work budgets before allocating large ID collections. Budget failure is not a low-confidence success.
4. Do not accept p=1 equality as sole routing evidence; test sparse behavior and require tests to catch a dense shortcut.
5. Stable summary construction and input ownership do not create a runtime error certificate.
6. The synthetic example intentionally reports its actual, imperfect retained mass and attention error. Random reference queries are not presented as trained behavior.

## Next work

Run the committed GPT-2 layer pilot using local verification. Hosted-CI availability is not a dependency of this experiment. See docs/GPT2_PILOT.md for the prespecified protocol, model revision, corpus split and interpretation limits.

## Findings corrected during implementation

- Enforced work limits before materializing selected-ID collections, including dense fallback.
- A flattened requirements export could not reuse all cached wheels during fresh offline installation. The installation check now populates each fresh environment directly from `uv.lock` without installing the editable project, then installs the built artifact. An isolated Python import verifies that the source checkout is not masking a packaging failure.
- The actual random-reference example retains about 45–48% of dense attention mass at its chosen routing setting. This is reported as imperfect untrained behavior, not hidden by choosing a favorable example or represented as model quality.
- The first hosted run rejected a runner-only context used in a job-level environment field. The workflow now uses a literal workspace cache path, following GitHub's context availability rules. Hosted verification remains pending until an actual run passes.
