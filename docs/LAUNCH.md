# X launch draft and assets

Prepared 13 November 2026. Draft only: no X post, public visibility change, release tag or package publication has been made in this pass.

## Main post

my maze agent remembered the key. it forgot how to get there.

built a visual debugger for memory, forgetting and hierarchical recall.

keeping path evidence together: 15/24 → 22/24 solves, same 64-fact workspace.

here's what a run looks like ↓

## First reply

The useful result is connected evidence: ordinary graph recovery and exact search matched ZHA here.

120 runs across 24 fresh task cases, all failures retained. Shared symbolic planner in MiniGrid, not an LLM benchmark.

Code + reproduction: https://github.com/Prigoistic/open-hierarchical-memory

## Second reply

Added replay that updates the routing weights.

It lowered routing KL by 14.9%, but didn't solve extra mazes. A better training metric wasn't enough.

The connector can scan the observed archive. Its graph work and storage are extra; 64 facts is the active workspace cap.

## Video

`release-assets/task-memory-demo.mp4` is a continuous 1920×1080 H.264 capture of a fresh Key Corridor solve, seed 23004, Connected ZHA, 64 active facts, 81 actions. It shows paced decision playback from an actual fresh worker execution; its duration is not a solver-throughput measurement. The clip is trimmed from one continuous capture, with no repeated sequence, synthetic telemetry or staged counter changes.

Generated MP4/build files stay outside Git to keep the repository manageable. `release-assets/demo.json` records source video/output hashes and the local completion identity. The retained dashboard screenshot is `docs/media/task-support-desktop.png`; it shows a source-bound connector event from the same task/seed.

For a new capture, start the local dashboard, select the method/task, set new-run seed 23004 and 128 actions, leave playback at Follow decisions, record the browser at1920×1080, then press Run solver. A25–30s segment covers the 81 displayed decisions. Keep the FRESH label and source/work disclosure visible. Check the output with ffprobe and inspect frames around the connector event.

## Publication review

The15/24→22/24 result describes the frozen support comparison, not a broader benchmark or a ZHA-specific win. The three connected controls have equal aggregate solves/actions. There are24 distinct initial world/pose/mission identities, not 120 independent layouts. The two failures and raw traces are retained.

The Git checkout contains scientific evidence and separate third-party notices; the numerical package is smaller and scoped. Review repository visibility and the prepared assets before publishing. Do not present this draft's code URL as publicly accessible until visibility is confirmed.
