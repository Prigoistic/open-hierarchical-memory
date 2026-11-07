# Somna continuous episodic memory and learned replay

Fixed noisy/partial cues have no unique state or episode identifier. Multiple observations share each cue. Three independent MLPs learn action-conditioned continuous displacement from actual retrieved observed transitions. No simulator is called during offline learning or imagined rollouts.

| Seed | Policy | Reader | Common MSE | Rare MSE | Gradient steps | Training examples |
|---|---|---|---:|---:|---:|---:|
| 7 | none | zha | 0.006752 | 0.014854 | 0 | 0 |
| 7 | uniform | zha | 0.000625 | 0.017840 | 160 | 2784 |
| 7 | priority | zha | 0.004250 | 0.007301 | 160 | 2364 |
| 7 | coverage | zha | 0.020306 | 0.000498 | 160 | 2232 |
| 7 | uniform | dense | 0.000276 | 0.020192 | 160 | 7680 |
| 7 | coverage | dense | 0.010175 | 0.002185 | 160 | 7680 |
| 7 | discarded_coverage | zha | 0.006752 | 0.014854 | 160 | 2232 |
| 7 | mixture | zha | 0.002308 | 0.011613 | 160 | 2580 |
| 7 | mixture | dense | 0.000714 | 0.015659 | 160 | 7680 |
| 7 | discarded_mixture | zha | 0.006752 | 0.014854 | 160 | 2580 |
| 23 | none | zha | 0.037550 | 0.043495 | 0 | 0 |
| 23 | uniform | zha | 0.000426 | 0.018692 | 160 | 3060 |
| 23 | priority | zha | 0.002662 | 0.009743 | 160 | 2820 |
| 23 | coverage | zha | 0.009956 | 0.002635 | 160 | 2484 |
| 23 | uniform | dense | 0.000376 | 0.021111 | 160 | 7680 |
| 23 | coverage | dense | 0.004795 | 0.006747 | 160 | 7680 |
| 23 | discarded_coverage | zha | 0.037550 | 0.043495 | 160 | 2484 |
| 23 | mixture | zha | 0.001256 | 0.013204 | 160 | 2724 |
| 23 | mixture | dense | 0.000794 | 0.016516 | 160 | 7680 |
| 23 | discarded_mixture | zha | 0.037550 | 0.043495 | 160 | 2724 |

Each context MSE covers192 previously unseen continuous states per training seed. V1/v2 states901–904 are development data for this follow-up;1201/1202/1203 are fixed v3 comparison states. These share the same synthetic dynamics as training, so this is not transfer to new physics or image learning.

Uniform, priority and coverage receive the same160 read/update limit, not equal total compute. Priority scans hot prediction errors; coverage scans metadata. Exact dense and exact top16 search over the full current bank are strong retrieval diagnostics on identical features. Full archive and hot dense audits are charged separately. Random-reference and fitted-reference outcomes, including unfavorable comparisons, are retained.

The discarded-update control pays for coverage replay but reloads initial neural parameters before evaluation. All ordinary checkpoints survive reopening with identical model evaluation. Immutable originals, version heads and all controller metadata persist. Learned rollouts are explicitly imagined and never written as canonical observations; uncertainty/support checks are heuristics, not correctness guarantees.

See report.json for every measured count and raw .json.gz files for actual selected reads, training sources/losses, model weights, rollouts and held-out predictions. The separate auditor reconstructs scalar softmax reads and independently replays functional MLP/SGD updates. Source snapshots bind the executed code.
