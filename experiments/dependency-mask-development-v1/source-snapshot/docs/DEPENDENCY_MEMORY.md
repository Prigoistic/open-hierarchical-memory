# Dependency memory: protocol and scope

This is an engineering hypothesis about the memory-to-planning interface, not a novel navigation algorithm. Development seeds are0/1; exposed1001–1003 are diagnostic only. Fresh2001–2006 are declared before development and remain untouched until review and source freeze. Default raw-fact budget96; an optional192 diagnostic is separate.

A flat subset can omit a previously observed wall and invent a frontier. Filling96 slots did not guarantee a useful connected map. This milestone separates coverage metadata from dependency grouping.

## Explicit channels and controls

Legacy adaptive ZHA, exact, full observed and no-memory conditions preserve old behavior. Each mask condition additionally receives fixed64x64 observed-known bits (512 binary bytes), version and source-head commitment. This contains no object/passability label. Its sole planner use suppresses a frontier neighbor known to have been observed but omitted. It cannot add traversal, objects, cues or actions. Binary and actual JSON transport are counted separately.

The common planner constructs routes only from current visible cells and returned raw facts. ReadContext contains own relative pose, mission, observed inventory, raw current cells and step. The planner does not consume closure receipts, nominated goals or dependency paths.

- Legacy `zha_adaptive`, `exact`, `full`, `none`: old no-mask controls.
- `flat_zha_mask`, `flat_exact_mask`: identical original selected facts plus coverage; primary mask-only ablations.
- `flat_exact_history_mask`: exact top96 after excluding current visible positions. Source scores enough originals (budget+49) to fill96 historical slots; filtering is charged. This controls reclaiming visible duplicates before attributing gains to bundles.
- `bundle_zha`, `bundle_exact`, `bundle_recency`: corresponding selected originals nominate endpoints; identical closure and packing.
- `graph`: all observed heads eligible for the same semantic/frontier nomination, closure and packing. This is ordinary observed-graph access, not weakened FIFO.

All full-head scans, graph builds, semantic/prerequisite checks, BFS nodes/edges, halos, packing and mask serialization are charged. Full-graph computation may dominate hierarchy work. This is96 returned raw facts PLUS coverage, not96 total-memory slots or a sublinear guarantee. Python graph/archive/RSS costs are not represented by owned index-tensor bytes.

## Closure contract

At most8 endpoints use the shared mission-role/true-observed-frontier ordering. Endpoints must be actual ZHA originals, exact-scored originals, recency originals or declared graph nominations. An unselected hierarchy endpoint is not silently supplied by a semantic full-map scan.

Paths use observed adjacent traversable cells, ending adjacent to interaction objects. Prefer a feasible current-inventory path; optimistic locked-door routes discover prerequisites only when needed. Matching keys must be reachable without unsupported locks, including their own lock. Missing/cyclic support rejects the bundle. Closed unlocked doors differ from locked doors.

Paths receive one-hop observed-neighbor halos. This is not global frontier closure; receipts list residual known-neighbor omissions. The explicit known-only mask suppresses those invented frontiers across all mask methods. Only canonical current versions support bundles. Current visible support is exempt from historical slots only when it supplies the required information. Pack the entire remaining support union under budget or record required IDs, omissions and rejection. No clipping, macro-edge compression, fabricated walls or full-map fallback.

## Evidence

Record both official observations around every action, reward/done flags, canonical versions, context, source-head identity, seed/query/route provenance, closure witnesses, packed IDs, mask bits and per-read/cumulative work. Freeze source, lock, versions, conditions and seeds before evaluation; never overwrite artifacts. Preserve old no-mask action traces on development observations. Test coverage semantics, versions, accessible/cyclic keys, stale-door updates, whole-bundle budgets, raw connectivity, seed perturbation and receipt mutations. Independently replay official transitions and reconstruct observation-prefix evidence.

This symbolic adapter does not establish learned perception, Somna dreaming/consolidation, biological mechanisms, industry readiness or ZHA advantage. Report exact/graph controls, failures, metadata and total graph work. Existing topological-navigation prior art includes [Spatial Semantic Hierarchy](https://www.cs.utexas.edu/ftp/qsim/papers/Kuipers-aij-00.pdf) and [Neural Topological SLAM](https://openaccess.thecvf.com/content_CVPR_2020/html/Chaplot_Neural_Topological_SLAM_for_Visual_Navigation_CVPR_2020_paper.html).
