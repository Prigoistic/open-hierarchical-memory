# Somna continuous episodic memory and learned replay

Fixed noisy/partial cues have no unique state or episode identifier. Multiple observations share each cue. Three independent MLPs learn action-conditioned continuous displacement from actual retrieved observed transitions. No simulator is called during offline learning or imagined rollouts.

| Seed | Policy | Reader | Common MSE | Rare MSE | Gradient steps | Training examples |
|---|---|---|---:|---:|---:|---:|
| 7 | none | zha | 0.006892 | 0.013586 | 0 | 0 |
| 7 | uniform | zha | 0.000656 | 0.016417 | 160 | 3324 |
| 7 | priority | zha | 0.006322 | 0.005132 | 160 | 3060 |
| 7 | coverage | zha | 0.018503 | 0.000671 | 160 | 2424 |
| 7 | uniform | dense | 0.000278 | 0.018667 | 160 | 7680 |
| 7 | coverage | dense | 0.011902 | 0.001830 | 160 | 7680 |
| 7 | discarded_coverage | zha | 0.006892 | 0.013586 | 160 | 2424 |
| 7 | mixture | zha | 0.002364 | 0.010781 | 160 | 2784 |
| 7 | mixture | dense | 0.000857 | 0.014789 | 160 | 7680 |
| 7 | discarded_mixture | zha | 0.006892 | 0.013586 | 160 | 2784 |
| 23 | none | zha | 0.034860 | 0.039605 | 0 | 0 |
| 23 | uniform | zha | 0.000485 | 0.017077 | 160 | 3528 |
| 23 | priority | zha | 0.001357 | 0.011784 | 160 | 3372 |
| 23 | coverage | zha | 0.014295 | 0.001099 | 160 | 2280 |
| 23 | uniform | dense | 0.000420 | 0.019747 | 160 | 7680 |
| 23 | coverage | dense | 0.007916 | 0.002747 | 160 | 7680 |
| 23 | discarded_coverage | zha | 0.034860 | 0.039605 | 160 | 2280 |
| 23 | mixture | zha | 0.001626 | 0.011278 | 160 | 2832 |
| 23 | mixture | dense | 0.000820 | 0.014415 | 160 | 7680 |
| 23 | discarded_mixture | zha | 0.034860 | 0.039605 | 160 | 2832 |

Each context MSE covers192 previously unseen continuous states per training seed. Earlier901–904 and1201–1203 cohorts are development evidence; this corrected-coordinate run uses fixed1501/1502/1503 states. These share the same synthetic dynamics as training, so this is not transfer to new physics or image learning.

Uniform, priority and coverage receive the same160 read/update limit, not equal total compute. Priority scans hot prediction errors; coverage scans metadata. Exact dense and exact top16 search over the full current bank are strong retrieval diagnostics on identical features. Full archive and hot dense audits are charged separately. Random-reference and fitted-reference outcomes, including unfavorable comparisons, are retained.

The discarded-update control pays for coverage replay but reloads initial neural parameters before evaluation. All ordinary checkpoints survive reopening with identical model evaluation. Immutable originals, version heads and all controller metadata persist. Learned rollouts are explicitly imagined and never written as canonical observations; uncertainty/support checks are heuristics, not correctness guarantees.

See report.json for every measured count and raw .json.gz files for actual selected reads, training sources/losses, model weights, rollouts and held-out predictions. The separate auditor reconstructs scalar softmax reads and independently replays functional MLP/SGD updates. Source snapshots bind the executed code.
