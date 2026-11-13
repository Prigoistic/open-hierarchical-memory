# Task routing replay: implementation contract

13 November 2026. Fixed before new collection or comparison.

The next slice studies experience → offline replay → fresh-task retest. It learns only the eight existing routing reference vectors. Canonical observations, known-coverage bits, graph construction and the symbolic planner remain unchanged. This is routing-parameter adaptation, not learned visual dreaming, a new world model or factual-memory consolidation.

## Reviewed mechanism

A wake episode runs the actual bounded persistent reader and records its observed query/key prefixes. Offline replay updates references against the existing pooled chunk-mass KL objective, starting from the frozen v2 fitted checkpoint. A child checkpoint owns its parameters and records the parent, eligible training/validation contexts, corpus identity, selected step and actual source trace. No evaluation tensor can enter fitting or checkpoint selection. No imagined fact is written to a store.

Schedules are unchanged parent, uniform replay of old anchors plus wake experience, error-prioritized mixed replay, recent-only wake replay, frozen random references, exact recovery and no cold recovery. Priority sampling uses a 10% uniform floor and (KL+1e-6)^0.6; priorities refresh every eight gradient steps and their full extra scoring cost is counted. This is a biased routing-error sampling heuristic, not an unbiased gradient estimator or a reproduction of DQN's PER. Three RNG seeds and identical gradient-step budgets apply to every learned schedule. Raw teacher pairs, priority/validation calls, reference-key pairs, corpus bytes and wall time are extra costs; equal steps do not imply equal compute.

For auditability, use explicit clipped SGD with learning rate 1.0, norm cap 1.0 and 64 updates. Select checkpoints every eight steps by equal-weight old/new validation KL, with the unchanged parent eligible. Old validation probes are exposed retention checks, not unseen evidence. New wake worlds use seeds 17001/17002; validation uses 17003. None appear in the existing task protocols. Fresh comparison uses 19001–19004. All four official MiniGrid families remain, with action cap 256. Primary active capacity is 64 including current perception; parent and exact also run at the existing 96 capacity to show budget headroom. Recovery/ageing rules stay fixed. Every task failure, truncation and cutoff remains in the report.

The old anchor corpus comes from the preserved v2 training prefixes. Its graph-teacher origin is explicit. New replay data comes from the actual parent persistent policy, not that graph teacher. Exact numerical Q/K duplicates are removed in declared anchor-training → wake → old-validation → new-validation → comparison order, independent of outcomes. A fixed parent-policy comparison corpus supplies common offline KL, selected-key and mass measurements; end-to-end comparisons run their own resulting trajectories. The common corpus need not cover every child-policy state.

## Acceptance and source boundaries

- Preserve original archives and baseline checkpoints byte for byte. Learning creates new child files, never mutates the live dashboard's checkpoint.
- Reject future, foreign, superseded-at-prefix and numerically overlapping sources; retain every sample's observed original IDs and collection artifact.
- A child cannot be evaluated in any parent or child training/selection context. No cross-reset raw-map reuse.
- Own all optimizer inputs. A callback receives only independent progress records; no tensor/RNG aliases.
- Persist every gradient update, selected source, sampling probability, norm/clip factor and parameter digest. A scalar auditor checks the SGD algebra for every update and finite differences on sampled gradient coordinates using independent KL construction.
- Independently replay official task actions, source/graph lineage and selected numerical route cases; report the audit's sampling limits.
- Test salience and task performance separately. Better KL is not a task improvement, and equal solve rates do not establish equivalence or a speedup.

The separate continuous neural learner already implements action-conditioned dynamics for its own synthetic world. Importing its weights into relative-coordinate MiniGrid would not supply a justified model target. This slice therefore keeps that engine separate.

Prior art: [Schaul et al., Prioritized Experience Replay](https://arxiv.org/abs/1511.05952) motivates revisiting uniform replay. [Miller, Lundqvist and Bastos, Working Memory 2.0](https://doi.org/10.1016/j.neuron.2018.09.023) motivates distinguishing transient activity from storage; it does not establish that reference-query fitting implements cortical dynamics or human dreaming. No neuroscience or novelty claim is an acceptance criterion.
