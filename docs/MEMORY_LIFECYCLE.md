# Memory lifecycle experiment

Protocol dated 5 November 2026. This is a separately scoped research lane, authorized after the attention-only plan. It does not modify the installed ZHA core or claim a new algorithm.

## Question and initial boundary

Can a bounded active memory, with usage decay and small coverage-replay passes, recover dormant project facts without silently losing originals? Does replay improve delayed retrieval enough to justify its maintenance work compared with simpler policies and query-time probing?

First isolate lifecycle behavior with a shared deterministic lexical cosine scorer. This is intentionally not a semantic embedding, trained ZHA router, LLM, PCAM simulation, attention certificate or external benchmark. The authored project-session stream is a diagnostic fixture, not held-out evidence of real assistant quality. A genuine model/embedding adapter and real longitudinal evaluation remain later gates.

## Contract

- SQLite holds immutable original records and explicit supersession chains. Updating a fact appends a new record; current-head metadata changes transactionally. No policy deletes original records. This is reversible index forgetting, not privacy erasure or bounded total storage.
- A bounded in-memory hot set caches current records and lexical terms. Policies never see expected answers, future events or scenario labels. Record keys identify correction chains; query retrieval does not receive those keys.
- Queries and writes use nondecreasing logical time. All new records are admitted, evicting an existing hot record if needed. Query results reinforce access counters; these count returned records, not proven usefulness or correctness. Replay does not increment actual-use counts.
- Ordinary recovery is triggered by a fixed lexical-score threshold. It inspects at most a fixed number of physical archive rows using a cyclic cursor. It can miss relevant material and can fail on a confidently wrong hot result. It is not a completeness check.
- Coverage replay, after every fixed number of queries, inspects another bounded row batch regardless of hot-result confidence. It scores current dormant rows against a bounded recent-query history, promotes matching candidates, and charges every comparison and record read. It does not learn model parameters or rewrite original facts.
- The time-decay policy ranks hot entries using `(1 + actual_hits) * 2**(-age_since_actual_access / half_life)`. The replay variant adds a decaying recent-cue term. This is a transparent heuristic, not a PCAM derivation or novelty claim.
- Replay and recovery share one archive cursor. Superseded and already-hot rows still consume their physical scan slots. No hidden full-archive search is allowed in the timed query path. Full-memory is an explicitly unbounded-hot reference.
- All policies filter superseded records before returning results. A zero outdated-answer count is a structural property of explicit correction keys, not evidence of natural-language contradiction detection.
- Originals survive reopening. Hot entries, use counters, history and cursor are session-local and restart from the most recent current records. There is one writer/controller per archive; cross-process mutation, controller-state persistence and concurrent sessions are unsupported.
- Validate size limits and hashes on open. Inserts and head replacement are one transaction. Tests exercise rollback and reopening on the local filesystem; no universal crash-safety or malicious-database security claim is made.

## Fixed comparison

Use seeds 7/23/101, capacities 8/16, top-1 retrieval, recovery 4 rows, maintenance 8 rows every 4 queries, recent history 8, half-life 24 logical steps, promotion/low-score threshold 0.45. Fixture recipes and configuration are committed before running results.

Policies: full-memory, FIFO, LRU, LFU, decayed usage, decayed usage plus scheduled current-query probes, and decayed usage plus coverage replay. The probe ablation has the same configured maintenance row allowance as replay but scores only the current query. Replay can do more comparisons because it uses recent history; count those costs, never call the two equal-compute experiments.

Fixture phases: original project facts; repeated early queries; unrelated writes; delayed revisits interleaved with distractors; explicit corrections; late revisits. All policies consume the identical ordered stream for each seed. No fitting or tuning follows these diagnostic results. Ingest source is deliberately authored public-safe text. Nothing is read from private papers, browsing history or user conversations.

Report per-seed/capacity/policy and pooled counts: top-1 current-record accuracy, phase-level accuracy, hot-first hits, dormant recoveries, superseded results, physical archive rows and bytes read, lexical comparisons, promotions/evictions, archive count/file size, peak hot count, ingest and query latency distributions, and replay maintenance time. Full query latency includes replay. Startup and shutdown/checkpoint work are separate. Bytes are UTF-8 payload reads, not disk/DRAM traffic; SQLite pages, Python object overhead and OS caches are not measured as hot-memory bytes.

## Verification and decisions

Test immutable sources, correction visibility, transaction rollback, restart recovery, causal time, deterministic tie ordering, hot capacity, actual bounded scans, empty/invalid inputs, replay without false usage reinforcement, and absence of answer-label inputs. Check ranking with an independent scalar formula. Run generated state sequences against a simple current-record model and semantic negative controls for destructive forgetting, ignored budgets and stale corrections.

Keep raw event traces and source/config/fixture hashes. Independently recompute report aggregates from traces. Preserve failures and unfavorable comparisons. A replay win on this fixture would justify a stronger test, not public performance or novelty claims. If current-query probing is better, retain it as the stronger baseline. Next: controller-state persistence and a separately audited hierarchical retrieval adapter, then actual longitudinal model tasks under a resource budget.

## Local prototype interface

Run from this repository:

```sh
uv run --locked python -m research.memory_console --archive /tmp/ohm-memory-demo.sqlite --capacity 8
```

Send one JSON object per line. Only the declared fields are accepted; target labels and scenario metadata are rejected. For example:

```json
{"operation":"remember","identifier":"helix-1","key":"helix/deployment","text":"Helix deploys to the cedar cluster.","tick":1}
{"operation":"remember","identifier":"helix-2","key":"helix/deployment","text":"Helix now deploys to the maple cluster.","tick":2}
{"operation":"query","text":"Helix deployment cluster","tick":3}
{"operation":"status"}
```

An explicit key links versions; the system does not infer that two differently keyed statements contradict each other. Query time includes lifecycle maintenance. Inspect `recovery_scanned`, `replay_scanned`, `replay_promoted`, `reactivated`, `evicted` and `work` in responses. Replay is scheduled every four queries by default; it is not guaranteed to recover a target. `status` explicitly states that controller state is session-local. Exit with EOF; reopen the same archive to recover original records. This is a local experimental interface, not a running assistant or network service.

Reproduce the diagnostic with fresh destinations:

```sh
uv run --locked python -m research.run_memory_lifecycle --output experiments/memory-lifecycle-v1 --archives .cache/memory-lifecycle-v1
uv run --locked python scripts/audit_memory_lifecycle.py --results experiments/memory-lifecycle-v1 --archives .cache/memory-lifecycle-v1
```

The runner requires a clean source tree and refuses existing output/archive paths. Keep prior attempts and use a new versioned destination rather than overwrite results. Verification: `uv run --locked --extra research python scripts/verify.py --profile core` now includes lifecycle strict typing and five isolated semantic-fault checks.
