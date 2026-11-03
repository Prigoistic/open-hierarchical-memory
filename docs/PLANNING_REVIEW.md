# Engineering plan review

Date: 3 November 2026. Reviewer: Codex self-review. No independent external review was performed.

## Executed evidence

Command, from this directory:

```sh
python3 verification/probe_contracts.py
```

Result: 12 test methods passed; 950 generated cases across the sandwich, merge and global-mass/output checks; 10 deliberately broken alternatives or interpretations were detected. Small-case Decimal oracles use 80-digit working precision and preserve the exact binary input floats with `Decimal.from_float`, avoiding a change of inputs through decimal string conversion. The script and environment are hashed/recorded in `verification/results.json`.

This is a planning audit. It does not exercise a production tree, full routing implementation, trained model, CUDA backend, package, persistence implementation or inspector. Passing checks with numerical tolerances do not certify conservative floating-point arithmetic.

## Pass 1: paper and mathematical contract

| Finding | Severity if shipped | Resolution in the plan | Evidence |
| --- | --- | --- | --- |
| Normalized lower estimates can dramatically overstate actual retained mass | Critical for a claimed guarantee | Approximate state has no passed-tolerance flag; checked mode requires global omitted-mass accounting | Estimated retained mass 0.9803921569 versus true 0.0045194746 in a two-branch example |
| Per-level top-p is conditional on surviving candidates | High for a misleading recall claim | Global mass measured separately; no interpretation of p as final retained mass | Exact uniform two-level p=0.95 example retains 0.9025 globally |
| Recursive biases are part of the summary, not decoration | High for method fidelity | Direct-versus-recursive fixture and missing-bias negative control | 150 shared-reference merge cases; largest observed error 2.66e-15 |
| Changing references during recursive construction need not recover a direct tangent | High for wrong proof or model adaptation | Distinguish shared-reference exact merge from general affine lower bound; positional adapter gate | 100 mixed-reference cases; observed lower-bound gap up to 7.152 |
| Attention mass does not establish semantic answer correctness | Critical for public overclaim | Scope of every bound is one attention calculation; closed-loop model evaluation is separate | Mathematical error bound and explicit assumptions in the plan |

## Pass 2: numerical and failure behavior

| Finding | Severity if shipped | Resolution in the plan | Evidence |
| --- | --- | --- | --- |
| A valid real-arithmetic bound can be non-conservative in ordinary floats | Critical for a literal runtime certificate | Checked mode unavailable until conservative arithmetic is implemented and audited | Minimum observed computed mass-bound slack was -1.1102e-16; tolerated by the planning tests, insufficient for certification |
| Affine lower-bound evaluation can also overshoot by rounding | High for a literal sandwich claim | Lower estimates are prioritization signals; interval/enclosure work needed for a numerical theorem | Largest observed lower excess 4.44e-16; the node upper bound also fell below its oracle by up to 2.22e-16 |
| Naive cumulative probability reaches p=1 before selecting all keys | High for a misleading dense-equivalence test | Explicit all-ID selection at p=1, plus independent sparse-path verification | `[0, -1000]` logits select one ID in the deliberately broken implementation |
| Stale extrema can yield a false skipped-mass guarantee | Critical | Owned immutable snapshots; reference and KV identity binding; reject unsafe state | Negative control changes a key from 0 to 100 without updating metadata |
| An omitted earlier-pruned branch invalidates global accounting | Critical | A complete disjoint frontier is validated against all eligible leaves | Missing, overlapping and future-ID controls rejected; hidden high-mass branch exposes false bound |
| Non-square upper-left causality can be wrong for offset decode | Critical | Explicit prefix mask and visibility count; adapter-specific tests | Three visible equal-logit values average to 11; the wrong one-query mask returns 1 |
| Dense fallback cannot repair invalid canonical inputs or a resource failure | High | Same validated raw snapshot required; no output on unsuccessful fallback | Result-state and injected-failure tests specified; implementation not yet run |

No rounding issue was fixed by adding an arbitrary epsilon and calling it certified. They remain blockers for checked mode. The analytic inequality itself is not contradicted by the floating-point counterexample.

## Pass 3: architecture, evaluation and release

| Finding | Risk | Resolution |
| --- | --- | --- |
| A p=1 shortcut can let a broken sparse router pass | False confidence | Add literal sparse-path oracle and broken-router negative control |
| A frozen dataclass still contains writable tensor aliases | Silent metadata invalidation | Own private cloned tensors; prohibit mutable zero-copy snapshots initially |
| Post-RoPE Q/K capture alone does not implement reference re-anchoring | Fidelity claim ahead of evidence | Native no-RoPE configuration or early V04 adapter gate; otherwise explicitly label a variant |
| Layer capture is teacher-forced and does not represent sparse closed-loop generation | Overstated model capability | Separate M2 from M5 and prevent whole-model quality claims at M2 |
| Dense offline checking or browser animation can dominate timing | Invalid speed comparison | Verification, trace recording and performance runners have distinct measured scopes |
| KV ownership copies and index metadata can disappear from a headline memory figure | Understated costs | Report total peak memory, construction cost and retained original KV |
| Broad adapters and stateful mutation multiply unsupported combinations | Slow and fragile first release | Read-only snapshots and a small support matrix first |
| Bound novelty and first-open-source claims are not established | Avoidable public correction | Claim ledger blocks both; cite primary prior work and recheck release status |
| A lockfile or high test coverage can be mistaken for correctness | Procedural checkbox without behavior evidence | Release gates require concrete invariant, negative-control and installed-artifact results |

## Decisions revised during the loop

1. Require an explicit execution mode instead of silently choosing approximation.
2. Keep checked mass guarantees out of v0.1 unless their separate gate passes.
3. Specify typed failure when dense fallback cannot complete; no success-shaped partial output.
4. Make p=1 selection structural and state why this cannot validate p<1 routing.
5. Add a positional-construction dependency before any real-model fidelity claim.
6. Separate the analytic bound, numerical enclosures, observed offline measurements and semantic correctness.
7. Keep implementation and release status explicitly unexecuted despite passing planning probes.

## Outstanding implementation gates

All V01–V22 checks in the engineering plan remain unexecuted against a real package. This audit gives a more defensible specification; it does not establish that a system is fail-safe or ready to post. GPU behavior, actual compute cost, bound usefulness, complete paper fidelity and independent review remain unverified.

The next concrete step is M1: implement and verify the mathematical core. Any launch language must wait for the evidence corresponding to that release's scope.
