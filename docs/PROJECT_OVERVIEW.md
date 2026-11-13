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

Open the unified Somna dashboard at `http://127.0.0.1:8792/` and press Solve maze for a fresh episode. The hierarchy and task memory share its decisions. Independent archive tools optionally connect to the separate continuous-memory service on8791; its old page redirects to the same dashboard. The separate `neural-fields` repository is an independent dynamical-systems project; its field simulation is not the maze controller.

## 5. Progress-aware retrieval repair

The new progress readers detect repeated poses without novel observed evidence. They add directional queries, widen the nomination pool, and can explicitly escalate to full-observed-head seed selection. All variants still use graph traversal to connect evidence; fallback means changing the seed source. The common planner and numerical ZHA core remain unchanged.

On the fixed 24-episode cohort per method, original ZHA bundles solve 19/24. Query plus widening repair solves 23/24; fallback-enabled repair solves 24/24 with 16 fallback reads in one case. Matched exact solves 24/24 without fallback. This repairs the operational stall without establishing a ZHA advantage.

The inspector exposes actual cues, routing passes, node spans, original facts and recovery transitions. Playback is recorded execution. Shared event/layout banks keep failed controls inspectable under the bounded transport. The same cohort was rerun after a serialization failure with unchanged policies; 167 retained originals have exact decoded parity. See `experiments/progress-evaluation-v2/ANALYSIS.md` and `docs/PROGRESS_RETRIEVAL.md` for the full comparison and missing-original caveat.


## 6. Unified solve workflow

The entry is `http://127.0.0.1:8792/`. Solve maze launches the existing observation-only MiniGrid controller with a bounded worker. Its navigation, hierarchical reads, observed facts, returned memories and planner actions share one cursor. The side rail has one primary start/stop action. Pause/scrub controls affect both structures. Source inspection reports actual original IDs and observation steps; graph recovery is explicit.

Saved examples retain separate labels. The default task memory field now belongs to the maze itself. The independent archive and its continuous neural-learning loop remain available under advanced tools. Solving a maze does not train those separate weights. The numerical controller, ZHA core and frozen experimental artifacts are unchanged; a step observer and bounded incremental transport provide fresh execution evidence. See `docs/UNIFIED_DASHBOARD.md`.


## 7. Persistent task-memory adapter,13 November2026

`research/task_references.py`, `task_store.py` and `persistent_task_memory.py` now connect actual fitted task reference parameters to versioned observed facts, a bounded active workspace and reversible forgetting. Read receipts identify current, active, recovered, evicted and returned sources. Support graphs are restricted to those available payloads; a known-only mask prevents phantom frontier nominations. Original evidence and correction chains remain immutable. The numerical core is unchanged.

This lane is now available in the dashboard as Fitted ZHA · persistent memory, with exact, fixed, random, always-recover and no-recovery controls. The default saved view is labelled development; Run solver creates a fresh episode and an individual local archive. The preserved first comparison has6/8 successes for ZHA versus8/8 exact/no-recovery; the repaired same-cohort development run has8/8 across all six conditions. A delayed-clue diagnostic verifies recovery after restart and correction isolation. Reference fitting improves KL over fixed, but the random control has lower KL; there is no demonstrated ZHA advantage. See `PERSISTENT_TASK_MEMORY.md` and the two versioned experiment summaries. Sleep/consolidation and fresh-seed policy evaluation remain future gates.
