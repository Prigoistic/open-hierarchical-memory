# Dependency-memory comparison

Split development; seeds (0, 1); raw capacity 96. Mask-bearing conditions additionally transport512 binary known bits bytes plus version/identity metadata. No method gets hidden observations.

| Task | Reader | Successes | Mean steps | Truncated | Errors |
|---|---|---:|---:|---:|---:|
| MiniGrid-MemoryS17Random-v0 | zha_adaptive | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | exact | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | full | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | none | 0/2 | 1445.0 | 2 | 0 |
| MiniGrid-MemoryS17Random-v0 | flat_zha_mask | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | flat_exact_mask | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | flat_exact_history_mask | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | bundle_zha | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | bundle_exact | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | bundle_recency | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | graph | 2/2 | 13.0 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | zha_adaptive | 2/2 | 55.5 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | exact | 2/2 | 53.5 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | full | 2/2 | 53.5 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | none | 0/2 | 120.0 | 2 | 0 |
| MiniGrid-MultiRoom-N6-v0 | flat_zha_mask | 2/2 | 53.5 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | flat_exact_mask | 2/2 | 53.5 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | flat_exact_history_mask | 2/2 | 53.5 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | bundle_zha | 2/2 | 53.5 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | bundle_exact | 2/2 | 53.5 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | bundle_recency | 2/2 | 53.5 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | graph | 2/2 | 53.5 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | zha_adaptive | 0/2 | 2560.0 | 2 | 0 |
| MiniGrid-DoorKey-16x16-v0 | exact | 0/2 | 2560.0 | 2 | 0 |
| MiniGrid-DoorKey-16x16-v0 | full | 2/2 | 70.0 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | none | 0/2 | 2560.0 | 2 | 0 |
| MiniGrid-DoorKey-16x16-v0 | flat_zha_mask | 2/2 | 62.0 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | flat_exact_mask | 2/2 | 63.0 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | flat_exact_history_mask | 1/2 | 1312.5 | 1 | 0 |
| MiniGrid-DoorKey-16x16-v0 | bundle_zha | 2/2 | 62.0 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | bundle_exact | 2/2 | 63.0 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | bundle_recency | 2/2 | 64.0 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | graph | 2/2 | 70.0 | 0 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | zha_adaptive | 0/2 | 1080.0 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | exact | 0/2 | 1080.0 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | full | 2/2 | 74.0 | 0 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | none | 0/2 | 1080.0 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | flat_zha_mask | 0/2 | 1080.0 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | flat_exact_mask | 0/2 | 1080.0 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | flat_exact_history_mask | 1/2 | 571.0 | 1 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | bundle_zha | 0/2 | 1080.0 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | bundle_exact | 0/2 | 1080.0 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | bundle_recency | 1/2 | 575.5 | 1 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | graph | 2/2 | 74.0 | 0 | 0 |

All graph scans, prerequisite checks, BFS, path halos and mask serialization are charged. Flat-mask controls isolate the known-coverage extension. ZHA dependence, task performance and total cost are separate questions. No novelty, speedup, biological dreaming or production claim follows from this integration.
