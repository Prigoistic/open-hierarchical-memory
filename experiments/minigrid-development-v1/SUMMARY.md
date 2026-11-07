# Official MiniGrid observation-only memory comparison

Split: development. Seeds: (0, 1). All results and failures retained. Fixed symbolic planner, no learned RL policy. No environment layout or hidden simulator position reaches the actor.

| Environment | Reader | Successes | Mean steps | Truncated | Errors |
|---|---|---:|---:|---:|---:|
| MiniGrid-MemoryS17Random-v0 | zha | 1/2 | 736.0 | 1 | 0 |
| MiniGrid-MemoryS17Random-v0 | exact | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | recency | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | fifo | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | none | 0/2 | 1445.0 | 2 | 0 |
| MiniGrid-MemoryS17Random-v0 | full | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | zha | 0/2 | 120.0 | 2 | 0 |
| MiniGrid-MultiRoom-N6-v0 | exact | 2/2 | 53.5 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | recency | 2/2 | 53.5 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | fifo | 0/2 | 120.0 | 2 | 0 |
| MiniGrid-MultiRoom-N6-v0 | none | 0/2 | 120.0 | 2 | 0 |
| MiniGrid-MultiRoom-N6-v0 | full | 2/2 | 53.5 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | zha | 0/2 | 2560.0 | 2 | 0 |
| MiniGrid-DoorKey-16x16-v0 | exact | 0/2 | 2560.0 | 2 | 0 |
| MiniGrid-DoorKey-16x16-v0 | recency | 0/2 | 2560.0 | 2 | 0 |
| MiniGrid-DoorKey-16x16-v0 | fifo | 0/2 | 2560.0 | 2 | 0 |
| MiniGrid-DoorKey-16x16-v0 | none | 0/2 | 2560.0 | 2 | 0 |
| MiniGrid-DoorKey-16x16-v0 | full | 2/2 | 70.0 | 0 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | zha | 0/2 | 1080.0 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | exact | 0/2 | 1080.0 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | recency | 0/2 | 1080.0 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | fifo | 0/2 | 1080.0 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | none | 0/2 | 1080.0 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | full | 2/2 | 74.0 | 0 | 0 |

All bounded readers share a96-fact slot limit plus the current official partial observation. They retain the same16-pose loop-avoidance history, so none means no episodic recall, not absence of all controller state. Full means all previously observed current facts, not hidden full-layout access. MemoryS17 is a small cue-memory diagnostic and cannot establish a need for hierarchy. The other tasks require exploration and key/door planning; failures also expose limitations of the common controller.

Each compressed episode contains every official observation before/after each action, returned reward/done flags, own tracked pose, immutable observed versions, actual retrieval queries/selected facts/routes and resource counters. Index rebuild time is included in policy latency. Tensor bytes are index-owned bytes, not total RSS. Process concurrency is recorded; these are not speedup measurements.
