# Technical X thread

Draft, 14 November 2026. Attach the memory-cloud MP4 to post 1; post the remaining items as replies. Nothing here has been posted to X. Length checks include the numbered prefix and standard shortened URL lengths.

## 1/11

1/ 64 active facts. A full 7×7 view can consume 49.
That leaves 15 slots for history.

I built a maze-memory prototype to inspect what breaks there. Adding observed-path recovery took this cohort from 15/24 to 22/24 solves.

Here’s a run ↓

## 2/11

2/ A useful memory may require several other memories: the corridor leading to a door, the key that opens it, and the cue identifying the right target.

Individually relevant cells can survive while that dependency chain falls out of the active workspace.

## 3/11

3/ Underneath: immutable observations, versioned corrections and Zyphra Hierarchical Attention (ZHA) over numerical keys.

Task inputs are fixed spatial/object features. A shared symbolic planner picks actions; ZHA nominates memory candidates.

## 4/11

4/ ZHA’s chunk score uses reference-conditioned means and entropy:

s_C(q)=max_r[q·μ_C,r/√d + H_C,r]

It approximates chunk log-sum-exp. Top-p traversal selects branches; local thresholds don’t guarantee global mass retention.

https://arxiv.org/abs/2610.42112

## 5/11

5/ I replayed the same planner at the same state with full observed, active and returned memory.

On exposed parent traces, 1,083 stalled decisions had a progress plan with full observed support. That localized an availability failure without changing the planner.

## 6/11

6/ The repair admits connected evidence: seed + observed path + prerequisites + cue. Optional halos are dropped.

A connector can scan the observed-head graph. ZHA seeds stay active/routed, but connecting path facts can be unrouted. That extra graph work is counted.

## 7/11

7/ Fresh comparison: 4 task families × 6 seeds × 5 conditions.

Original: 15/24
Compact bundles: 16/24
Connected ZHA: 22/24
Connected exact: 22/24
Connected graph: 22/24

The gain is connected support. These results don’t show a ZHA-specific advantage.

## 8/11

8/ Separate replay study: 8×30 routing parameters, 64 SGD steps/run, 3 seeds.

Priority replay reduced KL 14.9%, but solves stayed 11/16. Random references still had lower KL.

A better routing surrogate didn’t fix missing planning support.

## 9/11

9/ Forgetting deactivates records; it doesn’t delete originals.

u=(1+log(1+hits))·2^(-age/T)

Age is logical time; hits counts facts returned, not necessarily used. Corrections append versions. Old versions cannot return as current evidence.

## 10/11

10/ Video key: blue=dormant, cyan=active, gold=recovered now (part of active), white ring=returned.

X/Z are observed map coordinates. Height within a band tracks past returns at that location. The fine cloud dots are display samples, not additional memories.

## 11/11

11/ Two connected-policy failures remain. The connector can scan every observed head; this isn’t a sublinear-planning or speedup result.

Next: task-useful retention/replay under longer delays and corrections.

Code + frozen traces:
https://github.com/Prigoistic/open-hierarchical-memory

## Claim and source map

- Active/current sharing and limits: `research/task_store.py`, `research/minigrid_benchmark.py`, `research/persistent_task_memory.py`.
- Numerical ZHA score: `src/open_hierarchical_memory/summaries.py` and `routing.py`. This is the supported shared-reference/no-positional-encoding construction; no full-paper, full-model or RoPE reproduction claim.
- The1,083 decisions are post-hoc same-state probes on exposed parent traces, not new tasks or proof of alternate-episode success: `experiments/task-support-diagnosis-v1/diagnosis.json`.
- Connected support, routed seeds/unrouted connectors and full-head work: `research/task_memory/support.py`; results: `experiments/task-support-v1/SUMMARY.md`.
- The 24 support-study cases are reused across five conditions; they are not 120 independent layouts. All 23 unsuccessful runs remain: 22 external action cutoffs and one official truncation; the connected conditions each retain two failures.
- Replay uses a separate 16-case cohort and parent-policy comparison-prefix corpus; the 14.9% is mean pooled-KL reduction across three optimizer seeds. It is not a task-success improvement or generalization theorem. See `experiments/task-replay-v1/SUMMARY.md`.
- Forgetting utility is an engineering rule, not learned biological salience or a PCAM reproduction. `hits` counts returned facts and is not an action-attribution measurement.
- Cloud positions/colours/selection are source-bound; dense sampling is presentation only. `web/visuals/src/lifecycle-cloud.mjs` and the video legend specify each encoding.
- No novelty, biological dreaming, faster-than-dense or hierarchy-superiority claim. Verify repository visibility before directing a public audience to the code URL.
