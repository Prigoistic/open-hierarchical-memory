# Somna: observed spatial replay diagnostic

Three fixed evaluation mazes; seed7 is development data. The map is already observed. These results measure navigation from previously untested starting states, not new-map generalization.

| Reader | Replay | Solved | Scheduler comparisons | Summary dot products | Attention pairs |
|---|---|---:|---:|---:|---:|
| dense | none | 1/48 | 0 | 0 | 0 |
| dense | uniform | 1/48 | 0 | 0 | 148224 |
| dense | priority | 48/48 | 147456 | 0 | 148224 |
| zha | none | 1/48 | 0 | 0 | 0 |
| zha | uniform | 1/48 | 0 | 413952 | 6912 |
| zha | priority | 48/48 | 147456 | 413952 | 6912 |

Uniform and priority replay have identical update/read counts, not equal total compute. Priority uses an exhaustive observed-graph residual scan each update and already accesses every exact transition. This is not a retrieval bottleneck. Direct keyed lookup and shortest-path planning are stronger simple controls.

ZHA uses one untrained reference per symbolic state and is expensive despite selecting few raw keys. No speed benefit is claimed. The actual numerical output mixture, with no exact-record fallback, supplies each Bellman update.

The no-update fork preserves wake values. Offline forks update only a durable Q table from observed transitions. Temporary replay state is discarded on checkpoint reload; one reload also passes in a fresh interpreter. No simulator is called during offline replay. This is established Dyna-style value propagation, not a new dreaming algorithm.

Files: protocol.json, manifest.json, report.json, world-*.json, checkpoint-*.json and inspector.html. Dense retrieval audits are separate diagnostic work. Developmental fixture, not an external benchmark.
