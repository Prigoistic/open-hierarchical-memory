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

## Unified local dashboard

Open **http://127.0.0.1:8792/**, choose a maze and press **Solve maze**. The navigation, ZHA hierarchy, task memory field and decision receipt follow one fresh episode and one shared timeline. The former8791 page redirects here.

```sh
uv run --locked --extra benchmarks python -m research.serve_task_benchmark --port 8792
```

The initial example and historical recordings remain labelled. Independent archive tools can optionally connect to `python -m research.serve_somna --port 8791`; this separate continuous-learning experiment is not required to solve mazes. See [the dashboard guide](docs/UNIFIED_DASHBOARD.md).

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


## Somna live memory laboratory

The current [live engine and operating guide](docs/SOMNA_LIVE.md) uses ambiguous continuous partial cues, a hierarchy over dormant observations, bounded active memory, reversible retirement, durable corrections and genuinely learned action-conditioned dynamics. Offline jobs expose completed neural updates while they run; predicted rollouts remain separate from observed data. Launch `uv run --locked --extra research python -m research.serve_somna --archive /tmp/somna-live.sqlite --port 8791` and open `http://127.0.0.1:8791/`.

The [corrected-coordinate comparison](experiments/somna-continuous-v4/SUMMARY.md) and [ordinary replay control](experiments/somna-direct-control-v1/report.json) retain both learning gains and unfavorable comparisons. This is an inspectable research prototype, with fixed structured features and synthetic continuous dynamics. It does not establish a new algorithm, biological dreaming, general visual reasoning or a ZHA speed advantage. Earlier symbolic and page-only diagnostics remain dated historical evidence.

## Official maze and puzzle experiments

The [Boxoban comparison](experiments/boxoban-search-v1/SUMMARY.md) runs case-guided classical search on 32 distinct held-out official puzzles, with seven readers and two budgets. The [MiniGrid comparison](experiments/minigrid-evaluation-v2/ANALYSIS.md) runs the same observation-only symbolic controller across four official tasks and seven memory readers. These isolate retrieval inside planning; they do not run a trained LLM/RL policy or the separate Somna dreaming/consolidation experiment.

The result is not a ZHA win: on hard Boxoban at 1,024 expansions, both ZHA settings match dense/exact retrieval at 15/16 versus geometric search's 14/16, with higher CPU latency. On held-out MiniGrid, adaptive ZHA solves 3/12 versus exact 5/12 and full observed memory 12/12. All failures, extra passes and full-candidate fallbacks remain visible. See the [independent review](docs/ZHA_TASK_REVIEW.md) for audit scope and corrected engineering findings.

```sh
uv sync --locked --extra research --extra benchmarks
uv run --locked --extra research --extra benchmarks python -m research.serve_task_benchmark --port 8792
uv run --locked --extra research --extra benchmarks python scripts/verify.py
```

Open `http://127.0.0.1:8792/` for puzzle solutions, hypothetical search probes and recalled source cases, or `http://127.0.0.1:8792/?task=maze` for the recorded maze observations and reconstructed recall map. This read-only inspector uses checked experimental artifacts. It does not replay a canned demonstration as live model execution. The benchmark extra pins MiniGrid 3.1.0; the official Boxoban source and Apache 2.0 license are retained under `data/boxoban/`.


## Dependency-preserving maze memory

The [implementation overview](docs/PROJECT_OVERVIEW.md) separates the numerical ZHA engine, live Somna learner and symbolic task adapters. The [dependency-memory protocol](docs/DEPENDENCY_MEMORY.md) tests a concrete interface change: return a landmark together with its observed route and prerequisites, and separately supply a 512-byte observed-known mask. The mask suppresses invented exploration frontiers; it does not reveal omitted cell contents or create a navigable path.

Flat ZHA/exact mask controls, exact historical-only selection, identical bundle packing with different seed readers, and an ordinary observed-graph control separate those effects. Archive scans, graph building, BFS, packing and metadata transport are explicitly counted. A 96-fact workspace is not a total-memory or computational bound. The [independent review](docs/DEPENDENCY_REVIEW.md) states the acceptance contract and evidence limitations.

Open `http://127.0.0.1:8792/?task=dependencies` after launching the inspector above to compare the completed fresh cohort. Recall maps distinguish omitted known cells, accepted bundle support and the shared planner's route. Receipts can be inspected per action; they certify only their stated local support requirements.

The [fresh six-seed comparison](experiments/dependency-evaluation-v1/SUMMARY.md) contains 264 episodes. Coverage raises adaptive ZHA from 7/24 to 20/24; ZHA bundles remain 20/24, historical-only exact selection reaches 21/24, and observed-graph bundles/full memory reach 24/24. The result supports correcting the coverage interface; it does not establish a hierarchy or bundling advantage. All 82 official truncations are retained. Graph computation and the additional mask remain explicit costs.

## Progress-aware retrieval repair

The [fixed-cohort comparison](experiments/progress-evaluation-v2/ANALYSIS.md) addresses repeated retrieval without useful new evidence. Bounded directional queries and candidate widening raise ZHA bundles from 19/24 to 23/24. Explicit full-bank seed recovery reaches 24/24, using 16 fallback reads in one case; matched exact reaches 24/24 without fallback. All methods still use observed-graph dependency closure. This is an operational repair, not a demonstrated hierarchy advantage.

The [operating guide](docs/PROGRESS_RETRIEVAL.md) records the unchanged planner/core, budgets, stages and serialization recovery. The first incomplete run remains; the complete same-cohort rerun preserves all 167 retained cases without policy tuning. Open `http://127.0.0.1:8792/?task=maze` for the cleaned maze/hierarchy view, named cues, pass selection, node inspection and recovery-stage playback. Detailed counters remain under the inspector.
