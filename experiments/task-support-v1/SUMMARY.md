# Task-useful support recovery, v1

13 November 2026. Fresh comparison of unchanged memory, compact packing and explicit observed-graph path recovery. Source and protocol were frozen before collection. Development used exposed19001–19004 cases; comparison uses seeds 23001–23006 in four official task families. No policy was changed after looking at fresh outcomes.

## Result

| Condition | Solved | Total actions | Scan-stall decisions |
| --- | --- | --- | --- |
| parent | 15/24 | 2800 | 1712 |
| compact | 16/24 | 2684 | 1542 |
| connected_zha | 22/24 | 1564 | 103 |
| connected_exact | 22/24 | 1564 | 103 |
| connected_graph | 22/24 | 1564 | 101 |

Each condition has the same 64-fact active workspace, including current observations, and a 16-fact cold-admission limit per read. All120 episodes complete without runtime errors. The 24 initial environment/pose/mission identities are distinct. The initial-world hash is an evaluator-only check and never enters a reader. This is24 task cases repeated across five conditions, not 120 independent worlds or a significance result.

Connected recovery improves this cohort from 15/24 to 22/24; compact packing alone reaches 16/24. Exact and ordinary graph recovery also reach 22/24, with the same aggregate 1564 actions. The result supports repairing available path support; it does not demonstrate a ZHA-specific advantage, a new navigation algorithm or a speedup. All 31 unsuccessful runs remain explicit 256-action cutoffs.

## Mechanism and costs

Compact bundles retain their seed, real observed paths, prerequisites and semantic cues. Optional one-hop halos are omitted. When no complete progress bundle remains, the connector may inspect every current observed archive head to construct missing path support. With ZHA, nominated seeds come from active or actually routed records; connecting path facts may be outside the routed set. Those extra reads are disclosed and metered.

The planner receives only current/active/explicitly recovered raw facts. Its logic and the numerical attention core are unchanged. The connector's full observed-head graph is additional computation and information access. Equal active capacity is not equal total storage, information processing or compute. Canonical originals, numerical keys and the versioned head cache can grow. Temporary candidate decoding is extra work beyond final admitted facts.

| Condition | Connector attempts | Head rows decoded for connector | Graph build nodes | Graph BFS nodes |
| --- | --- | --- | --- | --- |
| parent | 0 | 0 | 175704 | 160434 |
| compact | 0 | 0 | 171381 | 174820 |
| connected_zha | 187 | 1727 | 131009 | 163540 |
| connected_exact | 187 | 1727 | 131009 | 163792 |
| connected_graph | 187 | 1727 | 129986 | 162066 |

The versioned head cache avoids repeated SQLite materialisation when canonical heads are unchanged; graph search remains charged on each attempt. Correction/version changes invalidate the cache. State-based tests check cached/uncached action, selected-source and controller parity. The separate [component measurement](../../docs/evidence/task-support-cache.json) records 125 repeated reads of 1,024 unchanged heads: 128,000 decoded rows without the cache and zero repeated decoded rows with it, after separately measured first materialisation. Cached serialized payload storage is 120,942 bytes, excluding Python object overhead. This is a narrow cache-component result, not an end-to-end task-speed claim.

## Diagnosis and remaining failures

The preceding [exposed-cohort diagnosis](../task-support-diagnosis-v1/diagnosis.json) identifies 1,083 stalled parent-policy decisions where full observed-prefix support allows the shared planner to progress but active support does not. These are local same-state interventions, not alternate-episode results.

Two Key Corridor cases remain unsuccessful for every connected condition:23003 and 23005. Post-hoc observed-prefix probes find six and 89 active-support-gap decisions respectively. That does not explain all their actions or establish a sole cause. [Retained follow-up diagnosis](POSTHOC_DIAGNOSIS.json) is explicitly post-hoc; these cases are now exposed development evidence, not reusable sealed tests.

## Independent audit

`INDEPENDENT_AUDIT.json` passes all 120 official action replays, 10,176 source-bound decisions, 1,464 routing traces, 63 sampled scalar numerical route cases and 561 connector reads. The auditor checks correction chains, active/cold caps, connector source/seed origins and packed path edges without importing the production reader, features, packing or planner. It is a sampled numerical/source audit, not an exhaustive policy or semantic proof.

## Reproduce and inspect

```sh
make support-study OUTPUT=experiments/task-support-local
make dashboard
```

Choose Run & query → Saved study → Path recovery · fresh seed study. Methods include all five controls. Run solver creates a new official episode with its own local archive; recorded cohort results remain labelled. The demonstrated interface can run arbitrary permitted seeds, while the published study remains the frozen cohort above.

Scientific inputs, checkpoints, source snapshots, complete outcomes and failed traces stay intact. Mutable SQLite archives are ignored. See [the contract](../../docs/TASK_SUPPORT.md) and [current roadmap](../../docs/ROADMAP.md).
