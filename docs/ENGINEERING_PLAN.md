# Open ZHA: engineering and release plan

Date: 3 November 2026. Status: reviewed implementation plan, not a shipped library.

The user authorized planning, repeated verification and careful engineering procedures. This document defines the contracts that implementation must satisfy. The companion checks exercise mathematical assumptions and deliberately broken alternatives. They do not test a ZHA package, a trained model, GPU kernels or an end-to-end application. None of those has been built in this planning pass.

## 1. Release decision

Build an independent, paper-referenced ZHA implementation with reproducible experiments and a trace inspector. Release a small, understandable research tool before expanding it into a serving system. Timing is useful, but a deadline never overrides a failed correctness gate.

Three capabilities have separate acceptance decisions:

| Capability | First public version | Acceptance standard |
| --- | --- | --- |
| Reference implementation of the paper's router | Yes, after core gates | Method mapping, independent oracle, sparse-path tests and documented departures |
| Captured model-layer experiment and inspector | Yes, after trace gates | Real reproducible traces, held-out evaluation, no invented measurements |
| Conservative skipped-mass checking with fallback | Experimental extension, excluded until its own gates pass | Complete frontier accounting, audited numerical bounds, explicit failure state |

Implementing a theoretical bound with ordinary floating-point arithmetic is not enough to call it certified. A CPU planning probe or an observed low miss rate does not establish a runtime guarantee.

Defer arbitrary vector-database adapters, online forgetting, MCP, custom GPU kernels, full serving integration and complete model conversion. Each changes the contract or adds an independent reliability problem. Support them only through later, separately measured milestones. An official Zyphra release would trigger a comparison and maintenance decision; it would not justify a race to post unverified claims.

## 2. Evidence and terminology

### Verified source anchors

| Source | What it establishes | What it does not establish |
| --- | --- | --- |
| [ZHA paper, v1, §§III-A–C](https://arxiv.org/html/2610.42112v1#S3) | Learned affine summaries, recursive construction, top-p traversal, final attention on selected original KV | Correctness of our future implementation |
| [ZHA paper, §III-B and Appendix B](https://arxiv.org/html/2610.42112v1) | Conversion requires training; small parameter count does not eliminate backbone compute | A cheap, successful tiny-model conversion |
| [ZHA paper, §V and limitations](https://arxiv.org/html/2610.42112v1) | Speed modeling and explicitly qualified extrapolations | Measured speedups from our code |
| [Zyphra announcement](https://www.zyphra.com/our-work/zyphra-hierarchical-attention) | Primary public explanation and announcement date | A permanent absence of official code |
| [LSA code](https://github.com/Prefrontal-AI/latent-sparse-attention) | A separate public hierarchical sparse-attention implementation exists | Equivalence between LSA and ZHA |
| [Quest code](https://github.com/mit-han-lab/Quest) | Prior use of coordinate min/max key metadata | Novelty or sufficient tightness of our proposed bound |
| [PyTorch SDPA](https://docs.pytorch.org/docs/stable/generated/torch.nn.functional.scaled_dot_product_attention.html) | API mask, scale, GQA and dropout semantics | Bitwise equality among backends |
| [PyTorch numerical accuracy](https://docs.pytorch.org/docs/stable/notes/numerical_accuracy.html) | Reduction/backend/platform numerical differences | A deterministic error bound for a particular kernel |
| [Hypothesis](https://hypothesis.readthedocs.io/en/latest/) | Tool for generated and stateful tests | Proof from a passing sample of inputs |
| [Safetensors](https://huggingface.co/docs/safetensors/en/index) | Non-pickle tensor persistence option | Safe resource consumption for arbitrarily large files |

The hosted research brief was read as a proposal, not as evidence for novelty, safety, licensing, benchmark results or implementation availability. Its proposed formula is examined below. Naming and company-product decisions need not block this independent research tool.

Terminology:

- **Dense reference:** evaluates every eligible key under our stated attention definition. It is not a guarantee of correct language-model answers or real-arithmetic identity.
- **Paper approximate:** follows the specified approximate router. It has no per-query tolerance guarantee.
- **Observed omitted mass:** measured by a dense offline oracle. Obtaining it requires the oracle computation; it is not free production telemetry.
- **Analytic mass bound:** an inequality under stated mathematical assumptions.
- **Numerically checked mass bound:** a runtime bound whose conservative arithmetic and metadata have separately passed the bound gate.
- **Fallback:** evaluates all eligible keys from the same validated snapshot, within the documented numerical tolerance. It can fail because of invalid inputs or resource limits.

## 3. Supported contract for v0.1

The implementation target is Python with a small PyTorch core. Select and lock concrete dependency versions at implementation time; record the exact resolved versions in each run. Avoid speculative abstractions for unsupported backends.

### Inputs

- Q shape `[B, Hq, Qlen, D]`; K `[B, Hkv, N, D]`; V `[B, Hkv, N, Dv]`.
- Explicit prefix visibility count per batch/query; counts must be integers in `[1, N]`. Padding is excluded. An empty eligible set returns a typed error; it never fabricates a zero-valued successful attention result.
- Standard contiguous GQA head mapping, with `Hq % Hkv == 0`. MHA is the equal-head case. Query heads sharing KV may share physical loads, but keep independent routing decisions and attention masks.
- Finite real inputs, matching devices and supported dtypes; `D`, `Dv`, reference count and chunk size must be positive and within configured allocation limits. Tree depth and node count are bounded before allocation. Reject booleans masquerading as integer configuration values.
- Initial attention definition: scaled dot products with causal-prefix visibility and no dropout or other additive attention bias. Reject unsupported score modifiers instead of silently ignoring them.
- The low-level core consumes Q/K in a declared coordinate system. The first numerical milestone uses no positional encoding. Model-specific RoPE reference rotations/re-anchoring require a separate adapter gate before that configuration is called paper-faithful. Merely supplying post-RoPE K does not implement the paper's reference-rotation construction.
- Caller must explicitly choose `mode="dense"` or `mode="paper_approximate"`. No silent choice of approximate semantics. The future checked mode is unavailable until its gate passes.

### Numerical support

- First correctness target: CPU float64, deterministic ordering, dropout exactly zero.
- Initial proposed release tolerance on the declared finite test domain: output maximum absolute error `<= 1e-10 + 1e-9 * max(abs(reference))` against the independent oracle. This is a proposed test threshold, not a measured outcome or universal error bound.
- GPU, float32 and reduced precision have separate, recorded tolerances and support gates. A failing tolerance is investigated, not silently widened. New tolerances require a reason, an error distribution and regression fixtures.
- `p` is finite and in `(0, 1]`. The documented `p=1` mode retains every eligible key explicitly, including keys with negligible/underflowed probability. This is an exact-selection boundary condition, not proof that sparse routing is correct.
- Tie-break equal routing scores by stable logical node ID. Prefer numerically stable log-sum-exp, entropy and accumulation. Record accumulation dtype. Do not clamp or normalize user inputs without an explicit transform in the experiment manifest.
- Do not promise bitwise reproducibility across different devices, kernels or library versions.

### Ownership and state

Use private, owned tensor copies for immutable snapshots; do not expose writable aliases. A frozen Python dataclass does not make its tensor members immutable. Mutable/zero-copy cache views are unsupported initially.

Each snapshot binds KV identity, visibility convention, reference-query checkpoint, coordinate system, summary formula version and geometry. Loaded metadata must match those identities before use. Reference-query changes require rebuilding affected summaries. Initial snapshots are read-only; append/update/concurrent-writer support is a later state-machine milestone.

Validate complete structure on build/load. Avoid secretly rescanning the entire cache on every query while advertising sublinear routing. If a future zero-copy interface makes mutation detection unavoidable, include that cost and state the weaker ownership contract.

## 4. Method conformance checklist

Keep a source-to-code map with function names and tests. Preserve reference-query identity, summary bias/entropy, merge arithmetic, causal chunk boundaries and head separation. The merge must recover direct summarization when a common unrotated reference is used; re-anchored summaries need only satisfy the appropriate lower-bound property. Mandatory eligible sink/local keys and complete parentless chunks must remain covered. No future-containing summary may influence an earlier query's decision.

At every routing step, record the candidate frontier, scores, chosen nodes and rejected nodes. Lower-level selection is conditional on the surviving frontier: `p=0.95` at every level does not imply 95% global dense mass retention. Match approximate output to independently computed attention on the selected raw leaves, even when those leaves differ from the dense top-p set.

Reject unsupported model configurations explicitly. A no-RoPE or one-layer reference can be released under that scope; it must not be described as a reproduction of all paper configurations.

## 5. Code structure and design rules

Proposed separate project layout, not additions to the portfolio application:

```text
src/open_zha/
  contracts.py          # validated configuration, result states and error types
  summaries.py          # summary construction and merging; tensor math only
  tree.py               # owned snapshot construction and structural invariants
  routing.py            # query/head-local candidate selection; no file IO
  attention.py          # selected-leaf evaluation and public dispatch
  trace.py              # versioned, bounded, inert trace records
  artifacts.py          # safe tensor/JSON manifests and checked loading
  training.py           # reference-query KL training, added after core gate
  adapters/             # only adapters with explicit supported contracts
  experimental/         # optional bound/fallback extension after its gate
tests/
  oracle/               # independently written scalar/high-precision oracle
  properties/           # generated invariants and stored regression cases
  negative_controls/    # known-broken variants that tests must detect
  integration/          # artifact, CLI and supported-adapter flows
benchmarks/             # timed measurement runner, separate from verification
examples/               # small reproducible public fixtures
docs/                   # method map, limitations, contribution and release records
```

Keep modules cohesive; do not create a generic plugin framework, database layer or inheritance hierarchy for one backend. Core mathematical functions have explicit inputs/outputs and no hidden global caches, RNG, network calls or filesystem writes. IO, plotting and experiment orchestration stay outside the numerical core.

Use typed immutable metadata and small enums. Do not represent every state with optional booleans whose contradictory combinations are accepted. Public boundaries validate; internal kernels rely on established invariants and check non-finite outputs. Provide one intended public API and test it from an installed wheel, not just from the source directory.

Avoid blanket exception-to-success conversion, catch-and-ignore, mutable default arguments, manual device guessing, hidden dtype casts, forced global RNG seeds and configuration values dispersed among scripts. Expected recoverable failures have typed reasons. Unexpected exceptions remain failures with useful diagnostics.

Use Ruff, a declared strict type-checking scope, pytest and Hypothesis. Exclude only genuinely dynamic third-party boundaries with documented adapters. Coverage is diagnostic; the release gate is the invariant matrix and the ability to kill the negative controls, not a high percentage alone.

## 6. Result and failure semantics

A successful result carries `requested_mode`, `executed_mode`, snapshot ID, route configuration, selected logical leaf IDs (or a trace reference), counts, numerical backend/dtype and diagnostics. Approximate execution cannot set a passed-tolerance flag.

Use discriminated result states:

| State | Meaning | Required evidence |
| --- | --- | --- |
| `DENSE_REFERENCE` | All eligible keys evaluated | Validated canonical snapshot, correct mask and finite completed output |
| `PAPER_APPROXIMATE` | Paper router selected a subset | Selected IDs and attention over exactly those IDs; no guarantee implied |
| `CHECKED_MASS` — later only | Conservative upper bound meets the requested mass tolerance | Valid supported bound arithmetic, full frontier accounting and snapshot identity |
| `DENSE_FALLBACK` | A recoverable routing/checking condition triggered dense evaluation | Completed dense evaluation on the same canonical inputs plus fallback reason |
| Typed error / no output | Contract, integrity, execution or resource failure | Explicit error category; no partial output passed off as success |

`DENSE_FALLBACK` identifies the actual backend used. Dense fallback must be independently tested; it is not an escape hatch around invalid Q/K/V. When the raw snapshot is untrusted or corrupted, no fallback result is valid.

Recoverable index failures can discard and rebuild the index or use dense computation only if canonical KV and all required semantics remain independently valid. An unknown model adapter, contradictory visibility metadata, non-finite canonical input, checksum mismatch affecting raw data, or unsupported score modifier causes a typed error.

Resource budgets cover candidate expansion, route scratch, trace size and dense fallback. If dense computation cannot finish within those limits, return a resource error. Never return the last partial result with a success label. Timeouts are cooperative at supported boundaries; no hard real-time or guaranteed GPU preemption claim.

## 7. Bound extension: assumptions, derivation and limits

This is our proposed extension, not a result claimed by Zyphra. It starts with ordinary scaled dot-product logits `s_i = q·k_i / sqrt(D)`, finite keys and no additional score bias. A new attention score function requires a new derivation.

For an unvisited node C, store the coordinate minima `a_j`, maxima `b_j` and the number `n_C` of its original eligible keys. Every descendant logit satisfies

```text
s_i <= u_C(q) = sum_j max(q_j a_j, q_j b_j) / sqrt(D)
F_C(q) = log sum_{i in C} exp(s_i) <= U_C(q) = log(n_C) + u_C(q).
```

The lower affine summary is useful for prioritization; its local gap to this upper bound is not a calibrated probability of error. To bound total omitted mass, keep a frontier of pruned subtrees covering every omitted original key. For clarity and auditability the frontier is a disjoint partition, not a bag of overlapping ancestors and descendants.

For evaluated set S, define `Z_S = sum_{i in S} exp(s_i)` and `B = sum_{C in frontier} exp(U_C(q))`. Then, in real arithmetic,

```text
delta = Z_omitted / (Z_S + Z_omitted) <= B / (Z_S + B).
```

Use log-domain calculations; overflow or an inconclusive interval is not a passed check. In conservative arithmetic use an upper enclosure `B_hi` and lower enclosure `Z_S_lo`, producing an upward-enclosed ratio. When that cannot be established, the checker is inconclusive and expands/falls back. A single `nextafter` on the final float is not sufficient to cover accumulated dot-product, logarithm, exponentiation and reduction error.

If every eligible value has L2 norm at most M, renormalized selected attention satisfies `||o_dense - o_selected||_2 <= 2 M delta` in real arithmetic. This is an absolute, one-head attention-output bound. Compute a conservative eligible value-norm bound and account separately for numerical evaluation error before claiming an output tolerance. It is not a token, sentence, factual-correctness or full-model guarantee. Teacher-forced captured-layer behavior does not establish closed-loop generation behavior.

Checked mode follows this procedure:

1. Validate requested tolerance, supported arithmetic, ownership and score semantics.
2. Use the approximate router to propose the first evaluated set.
3. Account for every remaining eligible leaf in the pruned frontier, including drops from earlier levels.
4. Evaluate a conservative global bound. If sufficiently tight, return `CHECKED_MASS` with its scope and tolerance.
5. Otherwise expand promising unresolved nodes and recompute accounting. Bound checks cost work and must be timed.
6. At the configured expansion limit, attempt dense evaluation on the same canonical snapshot within resource limits.
7. If dense evaluation cannot complete, return a typed failure, never a false pass.

Release blockers for this extension: stale extrema/counts, unaccounted branches, future-key visibility leakage, inconsistent scaling/coordinates, quantization error, unsupported additive biases, interval-library behavior, and loose bounds causing frequent dense fallback. Conservativeness can destroy efficiency. The worst case remains dense work; a tolerance check does not confer unconditional sublinear runtime.

The first prototype may export an **analytic bound estimate** for research, but must mark its numerical guarantee as unavailable. `CHECKED_MASS` stays disabled until the arithmetic and accounting gates pass. Omit the feature from launch if those gates take longer.

## 8. Verification matrix

All rows below are requirements for future implementation, not tests that have already passed.

| ID | Invariant or failure to exercise | Independent check | Gate |
| --- | --- | --- | --- |
| V01 | Complete leaf coverage and non-overlapping logical spans | Independently enumerate original eligible IDs | Core |
| V02 | Summary scale, bias and entropy are correct | Direct scalar formula and high-precision small fixtures | Core |
| V03 | Shared-reference recursive merge matches direct summary | Compare means/biases over multiple depths and uneven boundaries | Core |
| V04 | Rotated/re-anchored summaries satisfy the declared contract | Adapter-specific dense reference; exact and lower-bound cases distinguished | Adapter |
| V05 | Sparse top-p expansion follows the specified candidate frontier | Independent literal traversal, including ties and orphan chunks | Core |
| V06 | Selected attention equals attention over selected IDs | Independent scalar gather/softmax/value sum | Core |
| V07 | p=1 retains all eligible IDs, even with underflow | Structural selection assertion and output oracle; test sparse path separately | Core |
| V08 | No causal future leakage | Mutate future K/V; earlier decisions/output and causal trace fields stay unchanged | Core |
| V09 | Decode uses the correct visibility offset | One query with many eligible keys; explicit prefix mask, not an upper-left rectangular default | Core |
| V10 | Head and batch isolation | Single-example vs batch, batch permutation and head-local adversarial perturbation | Core |
| V11 | Boundary handling | N near C^l, partial chunk, one key, tree deeper than sequence, padding | Core |
| V12 | Invalid inputs fail explicitly | NaN/Inf, incompatible dtype/device/shape, bad visibility and invalid thresholds | Core |
| V13 | Immutable identity and safe fallback | Change caller tensors after construction; mismatched checkpoint/metadata/manifest | Core |
| V14 | Failures cannot become successful partial results | Inject route error, cancelled operation, trace overflow and failed dense fallback | Core |
| V15 | Reproducible persistence | Save/load comparison, unknown schema rejection, truncation and interrupted writes | Artifact |
| V16 | Training updates only reference queries | Frozen-backbone hashes, nonzero finite reference gradients and targeted finite differences away from max ties | Training |
| V17 | Training objective matches the declared target | Independently pool dense teacher probabilities at every eligible tree level | Training |
| V18 | Bound frontier covers all omitted eligible leaves | Independent set partition and dense omitted-mass oracle | Bound |
| V19 | Numerical upper bound is truly conservative on its declared domain | Directed/interval arithmetic audit and high-precision adversarial differential tests | Bound |
| V20 | Fallback and budget exhaustion are honest | Force a loose bound and a no-budget case; assert different correct statuses | Bound |
| V21 | Inspector reflects actual core execution | Export/replay identity, linked selected IDs and independent metric recomputation | Trace |
| V22 | Public API works from release artifact | Clean installed wheel, documented example, no source-tree imports or hidden network | Package |

Mandatory negative controls: drop merge bias, swap GQA heads, omit a pruned ancestor, use stale extrema, invert a mask, use upper-left decode causality, deliberately skip a relevant branch, label a budget failure as passed, and bypass sparse routing at p=1. The corresponding tests must fail for these broken alternatives. A gate with no working negative control does not establish that its test is discriminating.

Do not test sparse routing by demanding it returns exactly the same set as dense top-p at p<1. Approximation can select a different set. Test conformance, actual mass/error and downstream effects separately. Do not assume selected-set inclusion or quality is monotonic under every threshold/configuration change unless independently established.

## 9. Experiments and benchmarking procedure

### Fixture ladder

1. Hand-computable scalar cases and deliberately adversarial synthetic keys.
2. Randomized property cases with persisted failing examples.
3. Public, license-compatible text through a pinned frozen model, capturing Q/K/V and positional metadata from one declared layer.
4. Reference-query fitting on training documents; evaluation on held-out documents, with document hashes and split membership saved before tuning.
5. Adapter-level and eventually closed-loop full-model evaluation after sufficient compute is available.

Captured dense-model activations support a model-layer experiment only. Multiple heads/queries and more than a single favorable prompt are required. Compare reference fitting with random and simple untrained reference-query baselines. Report all prespecified query categories: concentrated, diffuse, distant rare fact, repeated/conflicting keys, recency-heavy and out-of-distribution.

Model selection is an explicit dependency: use a suitable native no-RoPE configuration for the initial faithful construction, or complete V04 for the chosen positional adapter before calling that real-model experiment paper-faithful. If captured post-RoPE tensors are routed with a fixed, unrotated reference construction instead, label it a methodological variant and list the departure. Do not postpone the adapter gate until after publishing a fidelity claim.

### Measurement contract

Separate the correctness runner, detailed trace recorder and performance runner. Offline dense verification is deliberately expensive and excluded from production-path timings, but its cost is reported separately. State when the core performs bound verification and count that cost within checked-mode timing.

Report total query latency and its components: tree construction/update where applicable, routing, ordering, gathering, selected attention, bound evaluation and fallback. Include full KV storage, summary metadata, bounds, owned copies and temporary buffers. Count scored summaries separately from scored original keys. Do not describe both as the same FLOP or byte cost.

Use matched hardware/dtype, attention semantics, batch/query lengths and backend settings. Record compilation, warm-up and host/device synchronization. Report p50/p95/p99 and sample count, throughput, peak memory, all fallback counts, retained mass, max/median/p95 output error and per-case failures. Ratios involving a near-zero reference output use an absolute metric. Provide raw run records and all seeds. Show where the prototype is slower than dense.

Baseline ladder: independent dense oracle for correctness, optimized dense SDPA for speed, a declared simple sparse baseline, and LSA/Quest only when their supported configurations allow a fair comparison. RAPTOR is not a like-for-like attention-speed baseline. Do not quote an unavailable comparison as a win.

Prespecify the evaluation cohort and tolerances before running headline comparisons. Do not tune on held-out prompts or publish only best-of-many geometry/sparsity sweeps. One successful synthetic retrieval is not a RULER, LongBench or full-model reproduction.

### Run record

Every run stores commit and dirty-state hashes; dependency lock hash; command/config hash; input/model/tokenizer revision; dataset/split hashes; reference checkpoint; coordinate conventions; Q/K/V shapes; snapshot ID; seeds; hardware; dtype and backend; mode; tolerance definition; warm-up/repetitions; raw measurements; unsupported cases and failures. A result without this record is exploratory and cannot support a headline claim.

## 10. Engineering operating procedures

### SOP-A: implement one behavior

1. Read the relevant paper paragraph and contract. Add a source-to-function entry and write the independent expected result.
2. Add the smallest state/behavior test and its failing negative control.
3. Implement the behavior with no unrelated feature expansion.
4. Run targeted checks, then the core invariant suite, type checking and lint.
5. Inspect the diff for accidental casts, masking changes, hidden state and exception swallowing. Store any counterexample as a regression.
6. Update support/limitations and the claim ledger if behavior changed.

### SOP-B: revise after a failure

Capture seed, inputs, exact config, status and environment. Minimize the counterexample. Determine whether the cause is specification, implementation, arithmetic, measurement or unsupported input. Correct the relevant layer and rerun the discriminating test before broader checks. Do not fix a failure by deleting the case, widening tolerances without evidence or switching to an easier dataset.

### SOP-C: artifacts and data

Use inert JSON plus non-pickle tensor files, bounded sizes and explicit schemas. Validate dimensions/counts before allocation; reject unknown major schema versions. Verify file identity and checkpoint/config consistency. Checksums detect accidental changes, not malicious authorship. Do not deserialize arbitrary Python objects or enable unreviewed remote model code.

For each supported local filesystem, write a temporary complete artifact, flush/sync, atomically publish it and test interruption recovery. Readers see a valid previous snapshot or a valid new one, not an incomplete mix. Do not claim crash safety on untested filesystems. Do not add a database or automatic schema migration in v0.1.

Only redistributable, deliberately selected public fixtures go in the repository/demo. Model activations and traces can expose input data. Local paths, tokens, private research or user prompts must not enter a public example. The inspector consumes bounded inert trace records; no arbitrary code, HTML evaluation or URL fetching from a trace.

### SOP-D: pre-release review loop

1. **Method pass:** source-to-code map, sparse-path behavior, coordinate assumptions and supported scope.
2. **Failure pass:** adversarial fixtures, injected faults, ownership/causality/head isolation and honest result states.
3. **Evidence pass:** clean package installation, reproducible runs, benchmark accounting, trace identity and claim-to-artifact audit.
4. For each finding, change the contract/code and repeat the affected passes. If a critical/high correctness issue remains, do not tag the release.

Keep a dated review log of findings, fixes and rerun evidence. These passes are self-review unless a named independent reviewer actually participates. Do not describe a second script or another pass by the same author as external validation.

### SOP-E: release and incident handling

Build wheel and source distribution from one clean commit. Install both into clean environments and run documented examples. Supported hardware/backend combinations must have evidence; absent GPU runs mean GPU support and speed claims remain unverified. Check source attribution, copied-code licenses and distributed model/data permissions. A license on our code does not establish rights to third-party artifacts or a patent opinion.

Create a release bundle with tests, known failures, support matrix, benchmark manifest, claim ledger and changelog. Review the actual launch wording against it. Recheck code availability and closely related work at publication time before saying anything about firstness. Publishing the repository/package or contacting authors is a separate action; no automatic outreach is authorized by this plan.

If a correctness problem is found after release: reproduce it, add a regression, mark the affected version/mode, correct visible claims, publish a scoped fix/release note, and keep the failing evidence accessible. Prefer disabling an untrusted mode to silently returning results. Do not erase negative results or imply unaffected configurations were audited when they were not.

## 11. Milestones and stop rules

These are dependency-ordered milestones, not delivery promises. Dates and compute estimates follow the first profiling run.

| Milestone | Deliverable | Exit gate | Stop/reduce scope when |
| --- | --- | --- | --- |
| M0: contract and fixtures | This plan, independent oracle design, support boundaries | No unresolved contradiction in supported semantics | Bound or adapter scope is being treated as already demonstrated |
| M1: mathematical core | Summaries, tree, literal sparse router and selected attention | V01–03, V05–14 plus passing negative controls | Causality, isolation or coverage is wrong |
| M2: real layer experiment | Pinned public model traces and held-out reference fitting | V16–17, real trace provenance, error distributions | Compute is unavailable, capture is incomplete or held-out behavior collapses |
| M3: reference release | Installable package, trace inspector, honest measurements | V15, V21–22; complete release evidence and limitations | Demo is detached from execution or clean installation fails |
| M4: checked extension | Conservative accounting, arithmetic and fallback | V18–20 and bound-specific review | Bounds are unsound or provide no useful sparse operating region |
| M5: supported model conversion | One audited adapter and closed-loop evaluation | V04 plus model-quality and resource results | Layer-only evidence is being used for whole-model claims |

M3 may ship without M4 or M5. That is an explicitly scoped reference release, not an unfinished guarantee hidden behind a flag. If M4 falls back for most realistic queries, publish the result and keep it a research experiment. Do not make false speed claims to compensate.

V04 can move earlier than M5 when M2's chosen model requires it. M5 adds closed-loop conversion; it is not permission to defer a positional correctness dependency of an earlier milestone. Obtaining a suitable pinned, redistributable fixture and its resource estimate is required before promising M2/M3 timing.

## 12. Public claims ledger

| Claim | Evidence required | Current status |
| --- | --- | --- |
| Independent ZHA reference implementation, within named supported configurations | Method map, code, oracle results and declared departures | Planned; no package exists |
| Runs on captured activations from model X, layer Y | Reproducible capture/run, revisions and split manifest | Planned |
| Output agrees with dense when all eligible keys are selected, within tolerance | Structural coverage and independent numerical check | Planned |
| Sparse routing has a measured error/cost trade-off | Prespecified held-out cohort, raw results including failures | Planned |
| Checked omitted-mass tolerance | Numerically conservative bound implementation and frontier/metadata validation | Blocked pending implementation and bound gate |
| Exact/dense fallback is used when needed | Forced fallback and exhaustion tests, same-snapshot identity | Planned |
| Faster than baseline on hardware/workload X | Complete end-to-end timing and matched quality/support | Unmeasured |
| First open ZHA implementation | Fresh public-release search; absolute firstness may still be unknowable | Unestablished; omit from launch |
| Guarantees correct answers / zero hallucinations | Not implied by this project | Do not claim |
| Reproduces the full paper / production-ready / works with any model or database | Broad evidence absent from this scope | Do not claim |
| Compresses away the original KV cache | Contradicts this planned retained-leaf design | Do not claim |

A launch post may say only what its attached evidence establishes. Suggested future scope after M3 passes: “An independent ZHA reference implementation with reproducible model-layer experiments and a debugger for inspecting routing and attention error.” This sentence is proposed copy, not a statement of completed work.

## 13. Planning-pass verification status

The executed checks and findings are in `REVIEW_LOG.md` and `verification/results.json`. They cover mathematical contract probes and discriminating counterexamples only. The implementation gates above remain unexecuted. No library, model, website, package, repository or launch post was published in this planning pass.
