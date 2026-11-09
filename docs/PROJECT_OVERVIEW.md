# What is implemented

This repository has a shared attention implementation and several separately tested research adapters. They should not be mistaken for one finished general-purpose agent.

## 1. The ZHA engine

`src/open_hierarchical_memory/` builds a tree over numerical key/value arrays. Each node summarizes a group of observations using reference-query-dependent tensors. A query scores summaries, traverses selected branches, and evaluates attention on the selected original records. Summaries are numerical arrays, rather than Markdown files. Original records remain available.

The implementation supports explicit approximate or dense execution, causal visibility, CPU float64, resource limits and trace inspection. The GPT-2 experiments captured real attention-layer data and fitted routing references. They did not convert a complete language model into this memory system.

## 2. The live Somna memory lab

`research/somna_engine.py` combines the retriever with an immutable, versioned SQLite archive and a smaller active workspace. A memory can become inactive while its original evidence stays recoverable. Corrections append a new version and invalidate obsolete learned forecasts.

Offline replay selects observed transitions and updates three small neural networks that predict action-conditioned changes in a two-dimensional world. Those learned weights persist across restart. Short predicted paths have separate imagined provenance; they are not saved as observed facts. This is the concrete implementation behind the current rehearsal/imagination demonstration.

## 3. The harder planning tests

`research/minigrid_benchmark.py` supplies historical facts to an observation-only symbolic maze controller. The controller sees the official partial image, mission and compass; its planning map is reconstructed from current observations and returned memory. ZHA chooses evidence, while the common planner chooses actions.

`research/boxoban_benchmark.py` retrieves solved training examples to guide a shared box-pushing search. The solver handles legal moves, deadlocks and search budgets. Returned examples influence search priority.

These benchmarks isolate retrieval and planning. They do not execute the separate Somna neural-learning loop. Previous results found no ZHA quality/cost advantage: adaptive maze retrieval solved 3/12 versus exact 5/12 and full observed memory 12/12. Hard-puzzle retrieval matched exact methods while adding CPU cost.

## 4. What the current change addresses

The new adapter preserves relationships among evidence: a landmark, its observed route, and prerequisites such as a matching key for a locked door. A separately metered observed-coverage summary prevents omitted known cells from being mistaken for unexplored space. Flat exact and graph-based controls receive the same information and allowance.

The frozen fresh evaluation contains 264 episodes: four tasks, eleven conditions and six new seeds. Original adaptive ZHA solves 7/24; adding observed coverage solves 20/24. ZHA bundles also solve 20/24, so bundling adds no aggregate success gain over its coverage-only control. Exact historical-only selection plus coverage solves 21/24. Ordinary observed-graph bundles and full observed memory each solve 24/24. All 82 official truncations remain, with no exceptions or external cutoffs.

The demonstrated improvement is the coverage interface. These results do not establish ZHA superiority, a speedup or a new navigation algorithm. The graph reader scans its observed archive; the 96-fact limit applies to returned historical facts, with a separately charged mask. See `experiments/dependency-evaluation-v1/` for frozen source, protocol, every trace and the comparison. Earlier results and failures remain separate in `experiments/`.

Use the live memory lab at `http://127.0.0.1:8791/` and the recorded task inspector at `http://127.0.0.1:8792/`. The separate `neural-fields` repository is an independent dynamical-systems project; its field simulation is not the maze controller.
