# Official MiniGrid observation-only memory comparison

Implementation/development protocol. Formal seeds1001/1002/1003 remain untouched until source review/freeze. Development uses0/1. This is a fixed symbolic planner, not RL training, a ZHA superiority result or industry validation.

## Official tasks and pinned versions

MiniGrid3.1.0, Gymnasium1.4.0 and pygame-ce2.5.8 are installed through the optional `benchmarks` extra. The selected official tasks and their normal rewards/time limits are unmodified:

- [MemoryS17Random](https://minigrid.farama.org/environments/minigrid/MemoryEnv/): sample-object matching after a corridor. It can require only one bit and cannot establish hierarchy necessity.
- [MultiRoomN6](https://minigrid.farama.org/environments/minigrid/MultiRoomEnv/): explore connected rooms and open doors to the goal.
- [DoorKey16x16](https://minigrid.farama.org/environments/minigrid/DoorKeyEnv/): find a key, unlock a door and reach the goal.
- [KeyCorridorS6R3](https://minigrid.farama.org/environments/minigrid/KeyCorridorEnv/): explore rooms for a key, then pick up the mission object behind its locked door.

Success means actual positive returned reward. Termination, truncation, exceptions and any external cutoff are reported separately. A4096-action safety cap exceeds these tasks' official limits. Obstructed box tasks are excluded because their mechanics are not implemented. Failures are never replaced by easier tasks or changed rewards.

## Information boundary

The actor receives only official `image`, `direction` and `mission`. It never receives an environment handle, hidden map, simulator position, hidden key/goal or future data. Returned `info` is not forwarded. The7x7x3 uint8 image is the standard symbolic partial observation, not learned pixel perception.

The actor tracks its own relative origin and deterministic turns/moves using the previous observed front cell's passability. The official compass checks that update; mismatch fails rather than invoking an oracle correction. Inventory is decoded from the official own-cell carried-object encoding. This assumes the selected static tasks' movement rules, not real-world localization.

Each action reconstructs a temporary planning map from current visible cells and selected historical facts. There is no persistent planner map, remembered cue identity or cached path outside the reader. All methods share a16-pose/orientation loop-avoidance deque, so `none` means no episodic recall, not zero controller state. The reader privately owns canonical observations and current-version heads. Current-view facts cannot inherit old cue labels through this archive in the no-memory condition.

## Shared controller and readers

The same mission-aware symbolic controller handles BFS navigation, frontier exploration, key pickup, door opening and inventory drops for every reader. Memory sample-role classification is an explicit observed-topology heuristic: sample-room objects have orthogonal free neighbors, whereas choice markers sit in a straight corridor. This is hand-designed task knowledge, not a hidden `success_pos` label or learned recognition.

| Reader | Historical evidence provided to the same planner |
|---|---|
| zha | Hierarchy candidates, exact reranking only within that selected union, at most96 facts |
| zha_adaptive | Separately labeled bounded multi-pass routing wrapper, up to96 facts; widens only on candidate-slot coverage |
| exact | Identical features, full-bank exact scoring and top96 |
| recency | Most recently seen96 current facts |
| fifo | Earliest96 current facts |
| none | No historical facts |
| full | All previously observed current facts, never unseen simulator cells |

The slot limit excludes the current visible observation. Archives and indexes grow; this is not a total-RSS bound. Full observed memory is a strong comparator, not an optimal-policy oracle. Its failures are retained.

Query/key features combine distributed trigonometric relative positions, object/color classes and an observed sample-role indicator. They contain no coordinate/state-ID onehot or answer label. Eight fixed, untrained semantic/spatial reference vectors are declared in source. No trained-reference advantage or whole ZHA-paper reproduction is claimed.

Fixed `zha` uses the existing CPU float64 no-positional-encoding core, chunk4/depth3/p=.4. Original selected fact IDs drive planning. The numerical selected-attention output is an audited diagnostic; averages of categorical cell encodings are not treated as a map. Exact scoring of unselected facts never repairs its result. Per-level p gives no global retained-mass or decision guarantee.

`zha_adaptive` is a separate development-informed wrapper. It accumulates actual routed originals while trying p=.4/.6/.8/.95/1.0, stopping once their union covers min(96, number of current observed facts). It never consults planner connectivity, reward, a hidden map or unselected-key scores. Reranking uses only that union. All routing passes, summaries and original attention pairs are charged. A p=1 pass is labeled and counted as a full-candidate fallback, not sparse work or an efficiency win. Both fixed and adaptive readers remain in every comparison.

The preserved initial48-episode cohort is `experiments/minigrid-development-v1`: fixed ZHA solved1/8, exact96 and recency96 solved4/8, FIFO2/8, no-memory0/8, full observed8/8. On Memory seed0 at decision3, fixed ZHA returned38 of54 observed facts despite a96-slot budget and dropped four corridor floor cells, disconnecting the planning graph before capacity pressure. The full reader walked toward the sample; ZHA scanned in place. This observable retrieval failure motivated the separate wrapper. DoorKey and KeyCorridor also failed for bounded exact/recency, so underfilling is not the only limitation. These development outcomes are not held-out evidence, and all failed traces/source snapshots are retained.

## Protocol and evidence

Development0/1 may be used to diagnose implementation and routing failures. Preserve all earlier attempts. Freeze source/protocol before formal1001/1002/1003 execution, and do not tune on formal outcomes. A later defect correction requires retaining the failed version and declaring a subsequent cohort separately.

Record actual success, return, steps, done/truncation/cutoff/error counts and every seed outcome. Index rebuilds are included in policy latency; count reference-channel scores, raw attention pairs, reranking/exact score pairs and owned index tensor bytes. These bytes exclude archive/Python/RSS overhead. SDK startup and worker concurrency are recorded; no speedup is inferred.

Compressed episodes contain both official observations around each action, rewards/done flags, tracked pose/inventory, immutable fact versions, recall IDs/payloads, numeric query vectors, routes/selected numerical output, proposed plans and cumulative work. Evidence must be observed by the decision time. Hashes bind protocol, source, lock and versions. This permits independent replay/provenance audit and a read-only task viewer.

```sh
uv sync --locked --extra research --extra benchmarks
uv run --locked --extra research --extra benchmarks python -m pytest -q tests/test_minigrid_benchmark.py
uv run --locked --extra research --extra benchmarks python -m research.run_minigrid_benchmark --split development --output experiments/minigrid-development-v1 --workers 2
```

Run from `/Users/priyamghosh/Documents/GitHub/open-hierarchical-memory`. After review, the same runner supports `--split evaluation` into a fresh directory. Existing outputs are refused. Official integration tests may skip without the optional dependency; that is not benchmark validation.
