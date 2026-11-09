# Dependency-memory comparison

Split evaluation; seeds (2001, 2002, 2003, 2004, 2005, 2006); raw capacity 96. Mask-bearing conditions additionally transport512 binary known bits bytes plus version/identity metadata. No method gets hidden observations.

| Task | Reader | Successes | Mean steps | Truncated | Errors |
|---|---|---:|---:|---:|---:|
| MiniGrid-MemoryS17Random-v0 | zha_adaptive | 6/6 | 11.5 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | exact | 6/6 | 11.5 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | full | 6/6 | 11.5 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | none | 0/6 | 1445.0 | 6 | 0 |
| MiniGrid-MemoryS17Random-v0 | flat_zha_mask | 6/6 | 11.5 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | flat_exact_mask | 6/6 | 11.5 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | flat_exact_history_mask | 6/6 | 11.5 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | bundle_zha | 6/6 | 11.5 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | bundle_exact | 6/6 | 11.5 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | bundle_recency | 6/6 | 11.5 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | graph | 6/6 | 11.5 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | zha_adaptive | 1/6 | 107.0 | 5 | 0 |
| MiniGrid-MultiRoom-N6-v0 | exact | 3/6 | 86.5 | 3 | 0 |
| MiniGrid-MultiRoom-N6-v0 | full | 6/6 | 62.3 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | none | 0/6 | 120.0 | 6 | 0 |
| MiniGrid-MultiRoom-N6-v0 | flat_zha_mask | 6/6 | 62.3 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | flat_exact_mask | 5/6 | 69.8 | 1 | 0 |
| MiniGrid-MultiRoom-N6-v0 | flat_exact_history_mask | 6/6 | 62.3 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | bundle_zha | 6/6 | 62.3 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | bundle_exact | 5/6 | 69.8 | 1 | 0 |
| MiniGrid-MultiRoom-N6-v0 | bundle_recency | 5/6 | 69.8 | 1 | 0 |
| MiniGrid-MultiRoom-N6-v0 | graph | 6/6 | 62.3 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | zha_adaptive | 0/6 | 2560.0 | 6 | 0 |
| MiniGrid-DoorKey-16x16-v0 | exact | 0/6 | 2560.0 | 6 | 0 |
| MiniGrid-DoorKey-16x16-v0 | full | 6/6 | 63.0 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | none | 0/6 | 2560.0 | 6 | 0 |
| MiniGrid-DoorKey-16x16-v0 | flat_zha_mask | 6/6 | 47.3 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | flat_exact_mask | 6/6 | 49.0 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | flat_exact_history_mask | 5/6 | 479.5 | 1 | 0 |
| MiniGrid-DoorKey-16x16-v0 | bundle_zha | 6/6 | 47.7 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | bundle_exact | 6/6 | 49.0 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | bundle_recency | 6/6 | 55.3 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | graph | 6/6 | 63.0 | 0 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | zha_adaptive | 0/6 | 1080.0 | 6 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | exact | 0/6 | 1080.0 | 6 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | full | 6/6 | 73.7 | 0 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | none | 0/6 | 1080.0 | 6 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | flat_zha_mask | 2/6 | 738.5 | 4 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | flat_exact_mask | 2/6 | 738.5 | 4 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | flat_exact_history_mask | 4/6 | 402.2 | 2 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | bundle_zha | 2/6 | 738.5 | 4 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | bundle_exact | 2/6 | 738.5 | 4 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | bundle_recency | 2/6 | 739.7 | 4 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | graph | 6/6 | 73.7 | 0 | 0 |

All graph scans, prerequisite checks, BFS, path halos and mask serialization are charged. Flat-mask controls isolate the known-coverage extension. ZHA dependence, task performance and total cost are separate questions. No novelty, speedup, biological dreaming or production claim follows from this integration.
