# Progress-aware retrieval: independent review

The repaired controller completes the fixed 24-task cohort with both hierarchical and exact seed retrieval. This establishes a narrow observation-bound recovery result, without establishing an advantage for ZHA, graph-free navigation, learned cognition or sublinear total cost. Policies were developed on exposed seeds and frozen before seeds 3001–3006; the same fixed cohort was rerun only to recover serialization, as described below.

## Confirmed historical diagnosis

The `?task=maze` shortcut originally selected the old `minigrid-evaluation-v2` MultiRoom-N6 seed 1001/adaptive trace at cursor 17. Independent inspection confirmed a real recorded failure: zero reward, 120 actions and official truncation. It alternated poses `(5,2,0)` and `(5,2,1)` with right/left turns, an `explore` objective, 96 recalled facts and no late new facts. This was a historical stalled replay, rather than a live simulator freezing. The inspector must label historical and updated cohorts explicitly.

## State and attribution contract

The independent auditor reconstructs payload novelty from actually observed immutable records, excluding new record IDs/timestamps from semantic novelty. Revisiting an old door state cannot reset a stall counter. It independently reconstructs the bounded 24-pose window, no-information streak, stage transition, trigger, fallback latch and each work delta.

Cue changes after 8 reads, widening after 16, repeated-stall fallback after 24 and hard no-information fallback after 48 are distinct stages. The 192-candidate stage does not change the 96 historical raw planner-fact limit. This is a joint cue-and-widening repair; the experiments do not isolate a directional-cue-only effect. Candidate limits do not imply that every raw hierarchy score/read is bounded by 192; real passes, selected attention pairs and reranks remain charged. Archive and official episode limits remain explicit.

The `cues_zha` and `cues_exact` controls disable the explicit full-observed-head **seed fallback**. They still construct and scan an observed graph for dependency closure, as do the progress variants. Therefore `graph_fallback_reads == 0`, the auditor's `no_graph_repair` label and its `successful_without_graph` count mean only that stage-3 seed fallback was not used. They do not mean graph-free execution or sublinear total computation.

Every episode using any stage-3 seed recovery is hybrid/fallback-assisted, not hierarchy-only success. Matched exact progress variants, unchanged old bundle policies and the ordinary graph comparator use the same seeds. Graph seed recovery remains a separate metered source; the controls do not establish a hierarchy-specific gain.

The unchanged common planner receives only actual current observations, returned immutable typed facts and the declared 512-byte known-only mask. Repair receipts, serialized banks and branch pictures are logging outputs rather than additional action/goal/route inputs. The mask has no object/passability labels and cannot create movement edges. Every path and key/sample/halo support obeys the existing structural and whole-bundle budget contract.

## Numerical routing and display contract

Retain actual labeled effective query vectors, per-threshold routes, source-index order, original IDs, branch scores, true core node spans, selected numerical outputs and use/source labels. A graph-only step must have no invented numerical route; constructed unused cues must be labeled unused. Old failures must not be overwritten or displayed as updated/live execution.

The independent numerical oracle reconstructs affine/entropy summaries from raw observed keys and fixed references using NumPy, without importing production summary/tree/routing code. It checks each branch's topology, affine scores, top-p prefix, final raw original IDs, selected output and tensor snapshot identity. The same content-addressed event can recur, but every occurrence is checked against that step's actual query and observation prefix. Legacy controls retain their prior audit scope; these enriched numerical-display checks apply to the new variants.

Official environment replay and independently reconstructed immutable fact versions check the observation boundary. The structural oracle checks mask identity, source nomination, ordered paths, locked-door/key prerequisites, one-hop supports, whole-bundle packing, residual known-neighbor omissions and declared work. These are structural receipts, not semantic-completeness certificates.

Twenty-eight independent tests cover a real official-environment trace; false progress, novelty, source, budget, work and mask metadata; modified branch scores and selected IDs; incorrect spans/snapshot labels; bounded stages; and recurring old door payloads. The direct final development audit passed all 56 episodes and 9,039 official transitions, including 3,782 repaired reads and 35 explicit seed-fallback reads.

## Defects preserved and repaired

Independent review found an incorrect zero-byte mask allowance on old baseline headers, although those conditions used the known-only mask. The header was corrected to 512 bytes for every condition. Earlier failed-metadata traces remain preserved.

Redundant layout/route copies produced development artifacts above 473 MB, exceeding the 128 MiB transport limit. A canonical content-hashed layout bank removes repeated source order and spans. Its identity includes original fact IDs: a core tensor snapshot label can repeat when door payloads return while immutable record IDs change, so that label alone cannot identify the layout. Subsequent exact event deduplication preserves ordered route occurrences and computation counters. This is serialization compression, rather than cached inference.

## Fixed-cohort execution and recovery

The first formal directory, `progress-evaluation-v1`, is incomplete. It retains 167 traces; no-fallback ZHA DoorKey seed 3003 exceeded the expanded transport limit. Its missing raw artifact and retained hashes are recorded in `INCOMPLETE_RUN.json`; it is not a passed cohort.

Recovery changed serialization and supporting tests/docs only. Protected policy, planner, dependency, core and lockfile bytes remain identical to the first freeze. The same sealed policies and seeds were rerun as `progress-evaluation-v2`, rather than presenting another untouched cohort. The formerly oversized control still officially truncates after 2,560 actions, now in a 77,312,254-byte artifact. It was not dropped or tuned into success. There is no original trace for its parity claim; only the later execution validates it.

The full gate's independent audit passed all 168 episodes and 27,880 official transitions. It reconstructed 7,772 repaired reads, 63,910 enriched hierarchy route occurrences and 2,169,576 affine branch scores. Its exact stdout is retained in the audit attestation; the formal audit was not redundantly executed.

A separate independent decoder compared every one of the 167 retained original traces, covering 25,320 actions. Every non-time observation, action, decision, query, numerical route, selection, work counter, immutable archive and result agrees exactly. Original compressed hashes remain unchanged. Only the protocol identity, serialization-bank metadata/costs and elapsed timings are excluded. All protected policy/core/controller/lock bytes also agree. The missing 168th episode is expressly excluded from this parity claim.

Independent arithmetic recomputed all 28 summary rows, every summary cost and outcome from the raw-hash-bound episode table. The completed cohort contains 168 episodes, no errors or external cutoffs, 155 successes and 13 official truncations; its largest expanded artifact is 77,310,857 bytes:

| Reader | Successes / 24 | Explicit seed-fallback scope |
| --- | ---: | --- |
| Old bundle ZHA | 19 | No progress fallback |
| Old bundle exact | 18 | No progress fallback |
| Ordinary observed graph | 23 | Graph is the seed source |
| Progress ZHA | 24 | 23 without fallback; 1 hybrid, 16 full-bank reads |
| Progress exact | 24 | No full-bank fallback |
| Joint repair ZHA, no fallback | 23 | Fallback disabled |
| Joint repair exact, no fallback | 24 | Fallback disabled |

The matched exact control is at least as successful. This supports progress-aware retrieval repairing the observed stalls, without showing a hierarchy-specific success or speed gain. Six seeds per task and a hand-written controller support a limited benchmark result rather than general navigation reliability. Future policy changes require a new freeze and fresh evaluation cohort.

## Evidence

The following attestations are post-run verification, separate from the pre-run policy freeze:

- [Independent full-cohort audit](../experiments/progress-evaluation-v2/INDEPENDENT_AUDIT.json)
- [Independent aggregate arithmetic](../experiments/progress-evaluation-v2/INDEPENDENT_AGGREGATES.json)
- [Independent 167-trace decoded parity](../experiments/progress-evaluation-v2/INDEPENDENT_PARITY.json)
- [Owner serialization parity receipt](../experiments/progress-evaluation-v2/SERIALIZATION_PARITY.json)
- [Preserved incomplete first run](../experiments/progress-evaluation-v1/INCOMPLETE_RUN.json)
- [Protected-byte equality before recovery](../experiments/progress-serialization-preflight-v1/POLICY_EQUALITY.json)

All executed source, parameters, conditions and seeds remain frozen. Every error, truncation, failed repair and fallback-assisted success is preserved. No novelty, learned cognition, biological dreaming, general navigation or speed claim follows merely from a successful repaired episode.
