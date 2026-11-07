# Official Boxoban search comparison

Completed 8 November 2026. This is a fixed subset of 32 distinct held-out puzzles, seven configurations and two budgets: 448 runs, not 448 independent puzzles. All 32 training puzzles were solved; their source-validated solution paths supply 363 cases.

| Cohort | Expansion cap | Reader | Solved | Median search ms | Median cold ms |
|---|---:|---|---:|---:|---:|
| test | 256 | matching | 16/16 | 3.13 | 3.13 |
| test | 256 | linear | 16/16 | 6.85 | 7.40 |
| test | 256 | dense | 16/16 | 7.71 | 8.15 |
| test | 256 | top16 | 16/16 | 8.94 | 9.37 |
| test | 256 | zha-p25 | 16/16 | 14.90 | 18.20 |
| test | 256 | zha-p50 | 16/16 | 15.45 | 18.65 |
| test | 256 | random-values | 16/16 | 7.72 | 8.68 |
| test | 1024 | matching | 16/16 | 3.19 | 3.19 |
| test | 1024 | linear | 16/16 | 6.91 | 7.49 |
| test | 1024 | dense | 16/16 | 7.44 | 7.87 |
| test | 1024 | top16 | 16/16 | 9.00 | 9.47 |
| test | 1024 | zha-p25 | 16/16 | 15.30 | 18.55 |
| test | 1024 | zha-p50 | 16/16 | 16.45 | 19.64 |
| test | 1024 | random-values | 16/16 | 7.92 | 8.44 |
| hard | 256 | matching | 10/16 | 19.53 | 19.53 |
| hard | 256 | linear | 10/16 | 37.22 | 37.81 |
| hard | 256 | dense | 11/16 | 44.89 | 45.35 |
| hard | 256 | top16 | 11/16 | 47.17 | 47.62 |
| hard | 256 | zha-p25 | 10/16 | 67.55 | 70.79 |
| hard | 256 | zha-p50 | 11/16 | 82.69 | 86.14 |
| hard | 256 | random-values | 10/16 | 46.98 | 47.49 |
| hard | 1024 | matching | 14/16 | 19.71 | 19.71 |
| hard | 1024 | linear | 14/16 | 38.36 | 38.95 |
| hard | 1024 | dense | 15/16 | 41.39 | 41.84 |
| hard | 1024 | top16 | 15/16 | 44.01 | 44.47 |
| hard | 1024 | zha-p25 | 15/16 | 72.28 | 75.58 |
| hard | 1024 | zha-p50 | 15/16 | 81.48 | 84.77 |
| hard | 1024 | random-values | 14/16 | 41.96 | 42.49 |

The ordinary unfiltered subset is a ceiling control: all readers solve 16/16. At 1,024 expansions on the official hard subset, geometric search solves 14/16; dense, exact top16 and both ZHA thresholds solve 15/16. Ridge and shuffled-target controls each solve 14/16. ZHA scores fewer original keys but is slower than dense retrieval and geometric search on this CPU implementation. Exact methods match its strongest task result. No speed advantage, hierarchy necessity, algorithmic novelty or statistically established general benefit follows.

The case signal is weak: 346 of 363 training cases have zero extra push cost above the exact geometric bound; 17 have a gap of two. The shuffled-target control also changes which individual near-budget puzzles succeed. These observations do not establish semantic planning insight. A revised representation or training distribution needs a fresh held-out cohort; this cohort is now observed evidence.

Every condition shares legal pushes, reachable-player regions, static reverse-push dead squares, proven blocked 2×2 configurations, a box-goal assignment lower bound and weighted A* with weight 1.5. Cases only estimate extra push cost to reorder the queue. They do not validate moves, provide test solutions or imply an admissible augmented heuristic. The same-case ridge control has no query-time retrieval. Shuffled values retain keys but permute target costs. Fixed local geometric features contain no puzzle/state IDs. ZHA uses eight untrained training-feature references, chunk 8 / depth 2, p=.25/.50 and a 128 selected-pair cap.

All expanded candidates, validated primitive move sequences, source IDs, numerical reads and failures remain in the compressed traces. Search latency includes features, retrieval, search and diagnostic trace collection/copy. Cold time adds reader construction/model fitting; counters distinguish original-key scores, value reads and reference-channel summary dots. These instrumented one-pass timings are not a production-kernel benchmark. The search cap is 256 or 1,024 expansions with a 20-second wall guard. A retrieval-budget error is a failed search, without hidden exact fallback; work consumed inside a failed call is explicitly unknown.

The independent auditor checked 32 training paths, 448 evaluation traces, 363 source-bound cases, 5,852 legal pushes and 96,517 scalar attention reads. All 49 failed evaluations remain. Sparse routing conformance is covered by the separate core tests, rather than rederived by this artifact audit. Independent review found and fixed an evidence-ownership bug when reusing a reader before this source freeze; a regression verifies per-run deep copies and counter differences.

Source and cohort hashes were frozen before held-out execution. Train/test duplicates under rotations, reflections and equivalent player regions were excluded. Pinned official data and its Apache 2.0 license are in `data/boxoban/`. This is an established research-puzzle integration, not validation of an industrial deployment.

```sh
uv run --locked --extra research --extra benchmarks python -m research.run_boxoban_benchmark prepare --output experiments/boxoban-fresh
uv run --locked --extra research --extra benchmarks python -m research.run_boxoban_benchmark evaluate --output experiments/boxoban-fresh
uv run --locked --extra research --extra benchmarks python scripts/audit_complex_tasks.py --results experiments/boxoban-fresh
uv run --locked --extra research --extra benchmarks python -m research.serve_task_benchmark --port 8792
```

The supplied inspector defaults to the reviewed v1 artifact. The runner refuses existing destinations and checks source/input identity before evaluation. Official source: [Google DeepMind Boxoban](https://github.com/google-deepmind/boxoban-levels), commit `78011d8c86ad423bfb2e1005012393b4c3c24409`.

A source-freeze limitation was found after the run: v1 copied and hashed the two research modules and dependency lock, but omitted individual numerical-core files. Its recorded Git HEAD identifies the unchanged committed core; `post-run-core-identity.json` verifies those bytes after execution and explicitly records that timing. It is not presented as a pre-execution core freeze. The future runner now freezes every core source file and has a regression that rejects a changed attention implementation before evaluation. V1's original snapshots/results remain intact.

The original evaluator also checked data against the current fixture manifest without comparing that manifest to the frozen copy. Independent auditing confirms v1's data still match every frozen hash. The future runner now requires current/frozen data-manifest equality, with a regression for post-freeze manifest changes. These are reproducibility repairs; the v1 numerical results and original frozen sources are preserved.
