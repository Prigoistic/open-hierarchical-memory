# Somna continuous episodic memory and learned replay

Fixed noisy/partial cues have no unique state or episode identifier. Multiple observations share each cue. Three independent MLPs learn action-conditioned continuous displacement from actual retrieved observed transitions. No simulator is called during offline learning or imagined rollouts.

| Seed | Policy | Reader | Common MSE | Rare MSE | Gradient steps | Training examples |
|---|---|---|---:|---:|---:|---:|
| 7 | none | zha | 0.006798 | 0.014214 | 0 | 0 |
| 7 | uniform | zha | 0.000336 | 0.017317 | 160 | 2952 |
| 7 | priority | zha | 0.000999 | 0.019254 | 160 | 2640 |
| 7 | coverage | zha | 0.002945 | 0.009576 | 160 | 2556 |
| 7 | uniform | dense | 0.000251 | 0.019611 | 160 | 7680 |
| 7 | coverage | dense | 0.000856 | 0.015194 | 160 | 7680 |
| 7 | discarded_coverage | zha | 0.006798 | 0.014214 | 160 | 2556 |
| 23 | none | zha | 0.036998 | 0.042592 | 0 | 0 |
| 23 | uniform | zha | 0.000498 | 0.018349 | 160 | 2964 |
| 23 | priority | zha | 0.002454 | 0.010501 | 160 | 3084 |
| 23 | coverage | zha | 0.000893 | 0.020547 | 160 | 2856 |
| 23 | uniform | dense | 0.000405 | 0.020687 | 160 | 7680 |
| 23 | coverage | dense | 0.000554 | 0.024108 | 160 | 7680 |
| 23 | discarded_coverage | zha | 0.036998 | 0.042592 | 160 | 2856 |

Each context MSE covers192 previously unseen continuous states per training seed. Seed901 was used in development and excluded;902/903/904 are fixed comparison states. These share the same synthetic dynamics as training, so this is not transfer to new physics or image learning.

Uniform, priority and coverage receive the same160 read/update limit, not equal total compute. Priority scans hot prediction errors; coverage scans metadata. Exact dense and exact top16 search over the full current bank are strong retrieval diagnostics on identical features. Full archive and hot dense audits are charged separately. Random-reference and fitted-reference outcomes, including unfavorable comparisons, are retained.

The discarded-update control pays for coverage replay but reloads initial neural parameters before evaluation. All ordinary checkpoints survive reopening with identical model evaluation. Immutable originals, version heads and all controller metadata persist. Learned rollouts are explicitly imagined and never written as canonical observations; uncertainty/support checks are heuristics, not correctness guarantees.

See report.json for every measured count and raw .json.gz files for actual selected reads, training sources/losses, model weights, rollouts and held-out predictions. The separate auditor reconstructs scalar softmax reads and independently replays functional MLP/SGD updates. Source snapshots bind the executed code.
