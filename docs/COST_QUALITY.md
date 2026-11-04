# Preregistered cost-quality study

Status: completed on 4 November 2026. The protocol and implementation were committed before fitting or test evaluation. See the [measured results](../experiments/gpt2-cost-quality-v1/SUMMARY.md). The completed original pilot remains immutable under `experiments/gpt2-layer5-pilot-v1/`.

## Question and scope

Can a different tree geometry reduce query work at a fixed layer-approximation budget, and does this CPU reference execute it faster than dense PyTorch SDPA? These are separate questions. Lower work counts do not establish lower latency. The current Python reference is not an optimized GPU backend.

Paper: [Subquadratic Attention with a Hierarchical Tree-Structured Indexer](https://arxiv.org/abs/2610.42112). The method map remains pinned to [v1](https://arxiv.org/html/2610.42112v1); readers can also consult [v2](https://arxiv.org/html/2610.42112v2). This experiment is not a reproduction of the paper's larger-model results or modeled GPU speedups.

## Fixed design

`research/cost_quality_protocol.json` and `research/cost_quality_manifest.json` are the authoritative settings and byte identities. Both must be committed before execution. The runner records that commit and source hashes and rejects changes during execution.

- Same pinned pretrained GPT-2 backbone as the first pilot, layer 5, frozen float32 teacher; explicit float64 captured Q/K/V and reference execution. Native attention probabilities and preprojection outputs are verified at each capture using the existing adapter tolerances.
- Contexts 256, 512 and 1,024, within GPT-2's native positional range. Two nonoverlapping windows per document at offsets 4096 and 12288 after Gutenberg-wrapper removal. Four queries per window at quarter positions: e.g. 255/511/767/1023 for 1,024. This is neither full prefill nor growing-cache decode.
- Geometries: original C4/R8/depth2 plus C16 and C32, each with R2/R4/R8 and depth2. Levels with no completed nodes remain empty and are reported; C32/depth2 has no complete second-level node within these context lengths.
- Seeds 7/23/101, 100 Adam steps per context/geometry/seed, lr .01, gradient norm limit 1, validation every 10 steps; initial checkpoint remains eligible. Only reference vectors are optimized. This is a fixed small budget, not convergence evidence or an equal-parameter comparison.
- Routing thresholds .73/.90/.95; fitted, sampled-query initialization and distribution-matched random references are all retained for test comparisons.

Training books: 11/84/1342/1661. Validation: 98/2701. New test books: 345/1260/174/768. Test IDs and body hashes must differ from every original-pilot document, including the previous test books. Public-book holdout is relative to reference fitting, not necessarily GPT-2 pretraining. Nested contexts reuse prefixes; do not count them as independent documents or multiply their unique training-token counts.

All context/geometry/seed fits and validation selections finish before any new test activation is captured. Hash-bound `selection-before-test.json` records the choices and checkpoint identities. Test metrics from every predefined setting are then reported descriptively; there is no test-based retuning or winner replacement.

## Selection and quality

Relative error is `norm(sparse_output - dense_output) / max(norm(dense_output), 1e-12)` per query/head. For each context, pool all three seeds' validation records. Eligible pairs have mean relative L2 <= .05 and p95 <= .20. Among them, select the smallest mean query-key plus attention-value vector-work ratio, breaking ties by geometry ID and threshold. No eligible pair means no selection. These thresholds are layer diagnostics, not a guarantee about generated answers or perplexity.

The proxy counts `R * scored_summary_nodes + 2 * selected_keys`, divided by `2 * visible_keys`, for this fixture's equal key/value dimensions. It counts reference dot products, original-key dot products and value-vector accumulations. It omits softmax, sorting, metadata, launches, byte traffic and Python overhead. A separate query-key score ratio excludes value accumulations. Neither is a complete FLOP estimate or a speed prediction.

Also retain absolute output error, full and non-sink retained mass, selected keys, scored nodes, per-book metrics and the maximum mass attainable with the same number of keys (dense top-K oracle). The oracle is offline work; it maximizes retained mass, not output accuracy. All raw query records are gzip JSONL with deterministic headers. Heads, windows and seeds are dependent; no statistical-significance claim is supported by four test books.

## Timing and storage

For every fitted configuration/seed/threshold, benchmark the eight test windows as a batch of Python calls. Query/key/value preparation and explicit prefix masks are constructed outside the timed region for both paths. Dense uses CPU float64 `scaled_dot_product_attention` with zero dropout, checked against a separate dense formula. Hierarchical execution includes its public validation, copying, routing, gathering, attention and required result metadata; optional detailed tracing is off. No dense quality oracle runs inside either timed path.

Four CPU threads, three warmup rounds, seven measured rounds, seeded randomized interleaving. Save individual times, median and p95. Tree construction has a separate warmup and three recorded builds; it includes owned input copies, content hashing and all summary construction. The build figure excludes retirement of old indexes and is not a hard latency guarantee.

Report build-inclusive cost for one use, and hypothetical amortization across 16 or 128 calls against the same static snapshot. These are scenario calculations, not actual incremental decoding; increasing cache sizes are not implemented. Separately report owned index tensor bytes including the full original KV and references, original-KV tensor bytes, node counts and active levels. These omit caller copies, Python objects, scratch allocations and full process memory. Whole-process peak RSS is recorded separately and includes capture/training; it is not a per-setting inference measurement.

## Reproduction

```sh
uv sync --locked --extra research
# Requires the already prepared pinned GPT-2 pilot model cache.
uv run --locked --extra research python -m research.prepare_cost_quality
# Commit the prepared protocol, manifest and source before the numerical run.
uv run --locked --extra research python scripts/verify.py --profile core
uv run --locked --extra research python -m research.run_cost_quality
```

Only preparation downloads public documents; the experiment uses local files. Raw texts, full traces and model weights stay in ignored `.cache/`. A run refuses nonempty output or an existing trace destination; preserve/archive prior partial runs and trace caches before a rerun rather than overwriting evidence. There is no automatic resume. No registry publication or public launch is authorized by running this study.

## Decision

First inspect whether validated configurations reduce vector work without exhausting the error budget, then inspect actual SDPA-relative latency with index costs. A speed ratio below one is a slowdown and must be reported. Even a passing layer budget does not close the whole-model gate. A faster backend or long-context adapter follows only if measured work/quality results justify the investment. Inspector and persistence work are deferred behind this experiment.

## Preflight failure record

The first run at preregistration commit `bb44d48` stopped on its first training-window capture because safetensors rejected a noncontiguous projection view. No fitting, validation selection or test capture/evaluation occurred. The fix packs trace tensors before serialization and adds a noncontiguous-view round-trip test; numerical formulas, corpus, geometry grid and selection thresholds are unchanged. The failed attempt and log are preserved in `experiments/gpt2-cost-quality-v1-preflight-failed/`. A new committed source revision is required before restarting.

## Post-run artifacts

After the recorded trace cache is available, run `uv run --locked --extra research python -m scripts.audit_cost_quality` to check all raw aggregates, identities, choices and 24 independent scalar routes. Then run `uv run --locked --extra research python -m scripts.summarize_cost_quality` for the descriptive report and grid CSV. Render the figure in an isolated plotting environment with `uv run --isolated --no-project --python 3.12 --with matplotlib==3.10.1 python scripts/plot_cost_quality.py`. These post-run tools do not fit or replace validation choices. Preserve the numerical source commit for reproducing the original run.
