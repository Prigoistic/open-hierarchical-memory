# Progress-retrieval comparison

Split evaluation; seeds (3001, 3002, 3003, 3004, 3005, 3006); raw capacity 96. Mask-bearing conditions additionally transport512 binary known bits bytes plus version/identity metadata. No method gets hidden observations.

| Task | Reader | Successes | Mean steps | Truncated | Errors |
|---|---|---:|---:|---:|---:|
| MiniGrid-MemoryS17Random-v0 | bundle_zha | 6/6 | 11.3 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | bundle_exact | 6/6 | 11.3 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | graph | 6/6 | 11.3 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | progress_zha | 6/6 | 11.3 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | progress_exact | 6/6 | 11.3 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | cues_zha | 6/6 | 11.3 | 0 | 0 |
| MiniGrid-MemoryS17Random-v0 | cues_exact | 6/6 | 11.3 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | bundle_zha | 6/6 | 59.8 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | bundle_exact | 6/6 | 59.8 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | graph | 6/6 | 59.8 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | progress_zha | 6/6 | 59.8 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | progress_exact | 6/6 | 59.8 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | cues_zha | 6/6 | 59.8 | 0 | 0 |
| MiniGrid-MultiRoom-N6-v0 | cues_exact | 6/6 | 59.8 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | bundle_zha | 5/6 | 469.5 | 1 | 0 |
| MiniGrid-DoorKey-16x16-v0 | bundle_exact | 4/6 | 883.0 | 2 | 0 |
| MiniGrid-DoorKey-16x16-v0 | graph | 6/6 | 60.5 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | progress_zha | 6/6 | 60.5 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | progress_exact | 6/6 | 58.5 | 0 | 0 |
| MiniGrid-DoorKey-16x16-v0 | cues_zha | 5/6 | 469.5 | 1 | 0 |
| MiniGrid-DoorKey-16x16-v0 | cues_exact | 6/6 | 58.5 | 0 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | bundle_zha | 2/6 | 741.0 | 4 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | bundle_exact | 2/6 | 741.0 | 4 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | graph | 5/6 | 242.8 | 1 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | progress_zha | 6/6 | 88.7 | 0 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | progress_exact | 6/6 | 93.2 | 0 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | cues_zha | 6/6 | 88.7 | 0 | 0 |
| MiniGrid-KeyCorridorS6R3-v0 | cues_exact | 6/6 | 93.2 | 0 | 0 |

All graph scans, prerequisite checks, BFS, path halos and mask serialization are charged. Flat-mask controls isolate the known-coverage extension. ZHA dependence, task performance and total cost are separate questions. No novelty, speedup, biological dreaming or production claim follows from this integration.
