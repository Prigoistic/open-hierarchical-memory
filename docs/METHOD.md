# Method and supported contract

This is an independent, no-RoPE implementation of ZHA's summary and traversal rules. Read [the original paper](https://arxiv.org/html/2610.42112v1) for the method. The authors receive credit for ZHA. The initial implementation is an inference reference; it is neither trained nor an end-to-end model reproduction.

## Source-to-code map

| Paper method | Implementation | Discriminating evidence |
| --- | --- | --- |
| III-A affine summaries | `summaries.summarize` | Direct raw-key scalar oracle; entropy/bias fixture |
| III-A recursive summaries | `summaries.merge`, `tree.KVSnapshot._build` | Every stored node checked against its original descendant keys; inherited-bias mutation |
| III-C adaptive top-p | `routing.route`, `_top_p` | Independent literal traversal; boundary cases and 60 generated configurations |
| III-C parentless chunks and local/sink keys | `routing.route` | Span-based oracle; parentless and future-prefix mutations |
| III-C head-local final attention | `attention.HierarchicalIndex.attend` | Scalar and 80-digit Decimal output oracles; GQA mutation |

The standalone merge preserves a shared reference identity across levels. It includes child bias in the merge scores and inherited bias in the parent. This reference construction has no RoPE rotation or re-anchoring. Post-RoPE inputs are not validated as a paper-faithful positional adapter.

## Public API

```python
from open_hierarchical_memory import ExecutionMode, HierarchicalIndex, TreeConfig

index = HierarchicalIndex(keys, values, references, config=TreeConfig(chunk_size=4, depth=3))
result = index.attend(
    queries,
    visible_counts=visible_counts,
    mode=ExecutionMode.PAPER_APPROXIMATE,
    p=0.95,
    collect_trace=True,
)
```

- Keys `[B,Hkv,N,D]`, values `[B,Hkv,N,Dv]`, references `[Hkv,R,D]`, queries `[B,Hq,Qlen,D]`.
- CPU float64 only. Reference queries are shared across batch entries. Hq must be divisible by Hkv. Keys include sink key zero. Snapshot inputs are detached and cloned; standalone summary functions preserve autograd but snapshot inference does not.
- Explicit CPU int64 visibility `[B,Qlen]` gives each query's number of eligible prefix keys, between 1 and N. A padded empty prefix is unsupported. Query positions need not be inferred from a rectangular mask.
- Each query head keeps its own selections. Every emitted ID is in its eligible prefix. Queries sharing KV do not share masks.
- Config chunk size is at least two, depth at most 32. This is an explicit compression/support restriction beyond the planning document's initial positive-integer description.
- Mandatory mode choice; unimplemented guarantee modes are rejected. No hidden dropout, normalization, precision cast, score bias or device transfer.
- `p=1` retains all eligible IDs by explicit selection, while still traversing/scoring the tree. Smaller thresholds use floating-point top-p; they do not imply a final global retained-mass fraction. Ties use logical node order.
- Results own their outputs. `node_summary` returns copies. The private underscored representation is not an external mutation API. Concurrent mutation of caller inputs during construction/copy is unsupported.

## Failures and limits

`InputError`, `NumericalError`, and `ResourceLimitError` are failures. The caller never receives a successful partial output from an aborted call. Finite extreme inputs may overflow intermediates; this produces a numerical error, not a claimed answer.

`QueryBudget` applies across the whole call, not separately to each head. It limits scored summaries, evaluated key/query pairs, optional trace nodes and final output tensor bytes. Snapshot limits cover owned tensor bytes and node count; they do not purport to limit Python-object overhead, scratch allocations, total process RSS or hard execution time. Selecting an unsupported budget never silently relaxes it. Exhausting a shared budget can make a later query fail even if it succeeds alone.

Dense fallback is opt-in. Only a routing/trace work-budget failure can trigger it. It uses the same private canonical KV and eligible prefix. Its state and reason are recorded per query. If its attention budget cannot fit, the whole call fails. It does not catch arbitrary exceptions or repair numerical/invalid-input failures. Partial failed-route steps are discarded; spent scoring work remains counted. A call can contain both approximate and dense-fallback query states.

This immutable in-memory milestone has no append, disk load, writer concurrency, cancellation, corrupted-artifact recovery or persistence interface. Those behaviors are not implemented or certified.

## Honest measurements

The synthetic example uses random, untrained references and has substantial attention error. Its retained-mass calculation and dense comparison are offline verification work, not runtime guarantees or free instrumentation. No speed benchmark or model-quality claim is made. The full original KV plus index remains stored. No bound/checker is implemented.

