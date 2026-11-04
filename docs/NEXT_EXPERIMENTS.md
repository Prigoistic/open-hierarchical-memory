# Next experiments after the CPU cost-quality study

Planning record: 4 November 2026. This document proposes the next work; it does not report new profiling, a faster backend or new model-quality results. The original engineering plan and verified core contracts remain in force.

## What the measured results establish

The [completed study](../experiments/gpt2-cost-quality-v1/SUMMARY.md) uses one frozen GPT-2 layer, four new test books, three seeds and native contexts up to 1,024. Its validation-selected configuration is C16/R2/depth2, p=.90 at all three lengths. The nominal second level is empty at 256 tokens; it becomes active at larger contexts.

| Observation | Supported interpretation | Still unresolved |
| --- | --- | --- |
| At 1,024: mean output error 3.84%, p95 8.70% | This layer passes the prespecified approximation budget on these books | Whole-model perplexity, generation, other layers/domains and long-context quality |
| Counted QK+AV vector work is .393 of dense | Fewer counted vector operations are needed in this fixture | Complete FLOPs, bytes moved, padded work, and actual speed |
| Eight-window query batch: hierarchical 41.47ms, native SDPA 2.44ms | Current hierarchical reference is about 17x slower, excluding build | Which components dominate and how much is removable |
| Full batch index build adds 85.09ms; owned index tensors are 1.066x raw KV | Construction and extra storage cannot be omitted | Incremental maintenance and per-setting peak inference memory |
| At the chosen 1,024 setting: random error 3.53%, fitted 3.84%; work .395 versus .393 | Random is a strong comparator even at nearly equal counted work | Whether the small fitting budget improves a cost-matched quality frontier |
| Validation KL falls throughout the chosen fits; all select step 100 | The declared surrogate improves within the fixed budget | Convergence, distribution coverage, and downstream routing benefit |

The selected geometry reduces arithmetic work while the current execution remains slow. This does not establish that the method must be fast after optimization. Likewise, random's lower error at one threshold does not prove that training is useless. Both need discriminating experiments.

The [paper, v2](https://arxiv.org/html/2610.42112v2) reports a much larger conversion/training regime and models optimized GPU latency in Section V/Appendix D. Our method map remains pinned to v1. Before claiming full v2 conformance, record a method/training delta review; do not silently change the existing experiments or use modeled GPU speed as measured evidence for this code.

## Immediate work: explain execution cost

Freeze numerical behavior and reference checkpoints. Use the existing traces for implementation diagnostics; they are now development/regression evidence, not a fresh quality holdout.

1. Record uninstrumented end-to-end timings with contemporaneous dense SDPA, identical input shapes, visibility, dtype, threads, warmup and hardware. Separate construction, query execution and actual static-reuse scenarios. Repeat across fresh processes, preserving raw observations and reporting median/tails and run-to-run spread. Seven repetitions in the previous sweep are descriptive, not a strong tail-latency estimate.
2. Run an instrumented profile separately: public validation/copying, candidate expansion, summary gathering/scoring, sort/softmax/top-p, raw-KV gathering, selected attention, and result-metadata construction. Avoid double-counting nested profiler events. The instrumented profile is diagnostic; headline latency comes from uninstrumented calls.
3. Replay the actual router's selected IDs, excluding routing from a separate diagnostic, to test whether selected attention plus gathering is itself competitive. Label excluded work explicitly; this replay is not a deployable search or a speedup result. Measure index construction separately from both paths.
4. Compare the timing breakdown with operation and memory counts. Attribute a bottleneck only after measurement; Python/framework overhead, sorting, gathering and metadata are hypotheses today.

Deliverable: a component-cost table and profiler artifacts tied to the current commit, plus a decision about the first concrete optimization. If eliminating a candidate component could not materially improve total latency, do not prioritize it merely because it is easy to optimize.

At the current 1,024 workload, query-only parity requires approximately 17x improvement. The proposed 1.5x-over-SDPA target would require query time around 1.63ms, roughly 25.5x below this reference, before construction. This is a decision target, not a prediction. A 2x cleanup of the reference would be an engineering improvement, not a practical dense-attention win.

## Backend experiment: preserve routing, change execution

After profiling, change one dominant component at a time. Keep the current CPU float64 implementation and scalar oracle unchanged as references.

Candidate representation: packed per-level mean/bias tensors and span metadata, instead of assembling stacks from individual Python node objects per query. Batch independent heads/queries where it reduces measured overhead. Gather actual selected KV in a compact or length-bucketed representation where useful.

Do not vectorize by scoring the entire lower tree after pruning, or by filling a dense full-prefix mask and counting only logical nonzeros as executed work. Candidate padding and length buckets can erase sparsity; record physical/padded slots alongside logical selected nodes. A simpler flat computation can be retained as an explicitly labeled baseline, not called the same sublinear traversal.

Behavior gates:

- Preserve causal-prefix boundaries, sink/local tails, parentless chunks, per-head decisions and deterministic logical-ID tie ordering.
- On the supported float64 fixtures and frozen real traces, match selected IDs and compare scores/outputs against the reference and independent oracle. Investigate near-tie differences explicitly; do not quietly widen tolerances or change tie rules.
- Preserve tensor ownership, budget preflight, finite-input handling, typed failures, p=1 completeness, and rejection of unsupported inputs. No successful partial outputs.
- Compare equivalent API contracts. If a compact result format or low-level execution API avoids materializing Python traces, declare it explicitly and report conversion/inspection costs separately. Do not silently drop required metadata or validation from one side of a comparison.
- Add behavior-based regressions for new packing, masking and batch/head paths. Existing scalar/generated/negative-control tests remain required.

Performance gate: report improvements over the old reference and over native SDPA separately, including construction, actual reuse and memory. A result faster only than the old reference is not a dense-attention speedup. Preserve unfavorable shapes and measurements. No float32/BF16 or GPU support is implied by a float64 CPU refactor; each needs separate evidence.

## Training experiment: establish a cost-matched benefit

Keep backend changes fixed while investigating the learning result. Current fitting uses 100 steps and only 8,192 unique training tokens at the largest context; this is a deliberately small pilot. All three selected fits choose the last step, which motivates a duration check but does not establish undertraining.

First use train/validation data to:

1. Plot KL and executed output-error/work curves together across saved steps. Lower chunk KL is a surrogate result, not necessarily better sparse attention output.
2. Compare fitted, sampled-query and random references over the same permitted threshold grid. Compare error at matched actual work, and work at matched error, rather than threshold equality. Report all seeds and tail errors.
3. Diagnose reference norms/spread, head-level failure concentration, near-zero output norms, sink dependence and the gap to the same-key-count dense mass oracle. The oracle measures achievable mass, not the minimum possible output error.
4. If needed, prespecify a small study separating optimizer duration from unique-data coverage. Keep optimizer/settings fixed when changing data, and data fixed when changing duration. Do not simultaneously change the loss, model, precision and initialization.

Gate: consistent improvement over strong untrained comparators on a cost/error frontier using validation selection and a new sealed test cohort. Report pooled and per-document/per-seed behavior; neighboring queries and heads are not independent experimental units. If learning remains unnecessary at this scope, report that result and keep the strongest simple baseline.

## Then test the regime and application

1. **Systems scaling:** use prespecified synthetic Q/K/V sizes beyond 1,024 to test packing, tree depth, memory and latency. Include concentrated and diffuse/adversarial cases. Label these as systems tests; they are not long-context language evidence or proof of natural sparsity. Preflight memory budgets before allocation.
2. **Real longer contexts:** choose a genuinely supported pretrained model, a resource estimate and an audited positional adapter. Never stretch GPT-2 beyond its native positions and label it normal pretrained behavior. Add new layers/domains and failure categories rather than extrapolating from one literary layer.
3. **Incremental maintenance:** append keys, complete only affected chunks and propagate completed parents. Compare incremental states/routes to rebuilds at every boundary; test stale references, failure recovery and visibility. Measure actual growing-cache cost, not an assumed static amortization factor.
4. **Closed-loop model quality:** replace attention progressively and measure held-out language loss/perplexity, retrieval and generation. Use matched hardware/batching and report whole-model latency separately from attention latency. Preserve exact adapter/mask/scaling semantics.

The application gate is repeated actual latency improvement at a quality budget fixed before evaluation, including mandatory index work and realistic memory. The proposed 1.5x target can be missed; a missed target is a measured outcome, not a reason to change the evaluation after seeing test data.

## Priorities and stop rules

Now: component profiling, then a measured parity-preserving backend experiment. Training diagnosis is a separate track, not a simultaneous rewrite. CPU experiments need not wait for hosted CI billing to be resolved.

Defer custom GPU kernels until work/traffic profiles and a resource estimate justify them. Defer dashboard polish, database adapters, forgetting, conservative bounds and public launch. Keep the repository private; publication, outreach or paid compute needs its own applicable authorization.

If favorable operation counts do not translate into a useful latency region, maintain an honest independent reference and inspector rather than promising acceleration. Before a public release, recheck current official/related implementations and claims; do not assert firstness from an old availability check.

While reading the paper, focus on III-A/III-C for invariant-preserving execution, III-B/Appendix B for the training assumptions, and V/Appendix D for the distinction between counted work, memory traffic and modeled latency. Record questions against these experiments; reading does not require committing to every proposed stage now.

## Execution update

Component profiling, the first independently tested batched prototype and corrected v2 timings are complete; see [execution results](../experiments/batched-execution-v2/SUMMARY.md). A fixed-data duration diagnosis is also complete; see [validation-only results](../experiments/training-duration-diagnostic-v1/SUMMARY.md). These close the first diagnostic/engineering steps, not the practical SDPA-speed, long-context or whole-model gates. Future work should use these results rather than repeat the initial plan as if unexecuted.


## Scope update: 5 November 2026

The user restored the broader forgetting/recovery direction and authorized implementation. This supersedes the blanket forgetting deferral for the separately scoped [lifecycle diagnostic](MEMORY_LIFECYCLE.md). Keep the attention core and its unclosed performance/model gates unchanged. First test durable originals, bounded hot retention, explicit correction versions and charged coverage replay against simple policies and a scheduled-query-probe ablation. The lexical lifecycle fixture cannot establish ZHA, semantic-memory or assistant performance.

The completed [lifecycle v1 diagnostic](../experiments/memory-lifecycle-v1/SUMMARY.md) improves aggregate hits with replay but mostly misses delayed rare facts. Do not optimize its headline aggregate or count seed permutations as new cohorts. Compare query-aware cold recovery and unconditional bounded probes under matched work, with newly prespecified stream structures, before a semantic/hierarchical adapter or assistant integration. Preserve the failed phases and all archive/maintenance costs.
