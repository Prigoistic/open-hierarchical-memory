# Fixed-data duration diagnosis

Completed on 4 November 2026; protocol prepared before execution. See [audited results](../experiments/training-duration-diagnostic-v1/SUMMARY.md). This is a training/validation diagnosis, not a new held-out model-quality experiment. It is separate from execution optimization.

The original cost-quality study found that, at the validation-selected C16/R2/depth2, p=.90 setting, random references have lower test output error than fitted references at nearly equal counted work. All nine chosen fits select the final step of their 100-step budget while validation KL continues to improve. These observations motivate a duration check; they do not establish undertraining or prove learning is unnecessary.

`research/diagnose_training_duration.py` fixes context 1,024, layer 5, C16/R2/depth2, seeds 7/23/101, and maximum budgets 100/300/1,000. Every arm restarts from the same seeded sampled-query initialization and data order, using the original Adam lr .01, clipping 1.0 and validation every ten steps. The initial checkpoint remains eligible; lowest validation KL selects a checkpoint within each budget. The 100-step result must exactly reproduce the prior saved checkpoint before any expanded-budget result is accepted.

Use only the previously captured training books 11/84/1342/1661 and validation books 98/2701, with the same two windows and four quarter queries per window. There are 8,192 unique training tokens at this context. Longer duration repeats data; do not describe it as more unique training data or paper-scale training. Trace hashes are verified before deserialization. The loader refuses the test split before file access; no test activation is loaded/evaluated by this script.

For each validation-selected checkpoint, measure validation output error, tails, non-sink retention and actual vector work across the original .73/.90/.95 threshold grid. Preserve the sampled-query and random baselines. Compare error/work together; equal thresholds are not equal cost. Retain all histories and small reference checkpoints. Both checkpoint selection and these diagnostics use validation, so a favorable result is not new generalization evidence.

```sh
uv run --locked --extra research python -m research.diagnose_training_duration
```

Commit source/protocol before running, keep existing output rather than overwrite, and run only after CPU timing workers have finished. The numerical core/fitting implementation stays fixed; this experiment changes only the declared step budget. A subsequent unique-data coverage or new loss study requires its own fixed protocol and a new sealed test cohort for final claims. No new whole-model, inference-speed or learning-superiority claim is implied by completing this diagnosis.
