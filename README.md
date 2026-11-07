# Open Hierarchical Memory

An independent research implementation of the no-positional-encoding construction and routing rules in [Zyphra Hierarchical Attention](https://arxiv.org/abs/2610.42112).

**Development reference, not a production memory system.** Initial scope: immutable snapshots, CPU float64, explicit prefix visibility, and dense or approximate attention. The core accepts caller-supplied reference queries. Small fitted-reference checkpoints from a scoped GPT-2 layer pilot are available under `experiments/`; they are not a converted model. Sparse output has no per-query accuracy guarantee. Original KV entries remain stored.

```sh
uv sync --locked
uv run pytest
uv run python examples/synthetic.py
```

For everyday local verification, independent of GitHub-hosted compute:

```sh
uv run --locked python scripts/verify.py --profile core
```

This runs tests, lint, formatting, strict typing, semantic mutation checks and the synthetic example. It writes a separate core report and does not claim package-installation or hosted-CI validation. The default `full` profile also checks fresh wheel/source installs and remains required for release and packaging changes. Its offline installation checks require the locked dependencies to be cached; after cache removal, `uv sync --locked --reinstall` repopulates that cache.

The example uses synthetic data and reports offline attention-error measurements. It does not reproduce model-quality or speed results from the paper.

See [progress](PROGRESS.md), the [engineering plan](docs/ENGINEERING_PLAN.md), and [method mapping](docs/METHOD.md). RoPE adapters, persistence, the inspector, conservative runtime bounds and closed-loop model conversion remain separate gates.

This project is independent and is not affiliated with Zyphra. The paper's authors retain credit for ZHA. No code has been copied from their implementation.

## Measured layer pilot

The [frozen GPT-2 pilot](experiments/gpt2-layer5-pilot-v1/SUMMARY.md) fits only 6,144 routing-reference parameters per seed. Held-out pooled KL improves in all three seeds. At threshold 0.73, mean attention-output L2 error is 11.9% lower than the untrained sampled-query initialization at nearly equal selected-key fractions. The random-reference baseline is close, and higher-threshold results are mixed. This covers one layer, 256-token contexts and two test books; it establishes no whole-model quality or speed claim.

The [protocol, optional research setup and reproduction commands](docs/GPT2_PILOT.md) distinguish native-capture checks from real pretrained-model measurements. Research dependencies are optional: `uv sync --locked --extra research`. Include `--extra research` in subsequent `uv run --locked` commands to retain them; without the extra, optional GPT-2 adapter tests are skipped explicitly.


## Geometry and context study

The [preregistered cost-quality study](experiments/gpt2-cost-quality-v1/SUMMARY.md) covers seven geometries, three native GPT-2 context lengths and four new test books. Validation-selected settings meet the fixed layer-error budgets and reduce counted vector work. The current CPU reference is still substantially slower than native dense PyTorch SDPA; this is no speedup result. The [protocol](docs/COST_QUALITY.md), complete grid, individual timings, index costs and independent audit are retained.


## Execution and training diagnosis

A separate [batched CPU research prototype](experiments/batched-execution-v2/SUMMARY.md) preserves selected IDs and output tolerance across 96,768 real query/head cases. It improves on the slow reference but remains slower than native dense SDPA; all layouts, construction/storage costs and corrected resource preflight are documented. The supported numerical core is unchanged. A [fixed-data duration study](experiments/training-duration-diagnostic-v1/SUMMARY.md) diagnoses train/validation behavior only and makes no new held-out quality claim.


## Experimental forgetting and recovery

A separate [lifecycle prototype](docs/MEMORY_LIFECYCLE.md) preserves immutable original records in SQLite, limits a hot set, and compares usage decay, bounded recovery and recent-cue replay against simpler policies. A local JSON-lines interface accepts your own records. This lane currently uses lexical retrieval; it does not add semantic embeddings, ZHA-backed persistent memory or an LLM assistant. Original storage grows, and session-use metadata resets on restart. The [fixed diagnostic](experiments/memory-lifecycle-v1/SUMMARY.md) improves overall access with replay but fails most delayed rare-fact queries. It is not a public benchmark, reliable-assistant result or novelty claim.


## Somna: spatial replay inspector

Somna is the working name for the separate memory and offline-consolidation research lane. Its first [implemented diagnostic](docs/SOMNA.md) connects actual numerical ZHA reads to frozen observed spatial episodes and persistent tabular value updates. Open the [self-contained inspector](experiments/somna-spatial-v2/inspector.html) for recorded replay, hierarchy selection and policy outcomes. The [fixed known-map comparison](experiments/somna-spatial-v2/SUMMARY.md) finds residual scheduling useful for value propagation, but ZHA adds cost and is unnecessary for this direct-key task. This is a tested integration foundation, not learned visual dreaming, a new algorithm or a speed result. The existing package/API name is unchanged.
