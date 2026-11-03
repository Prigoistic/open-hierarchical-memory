# Frozen GPT-2 layer pilot

This experiment tests model-activation capture, reference-query fitting and held-out routing evaluation. It is a small teacher-forced layer experiment. It does not reproduce the ZHA paper's model sizes, training budget, long-context benchmarks, kernels or generation quality.

## Protocol fixed before training

The committed `research/gpt2_pilot.json` is the protocol. The runner requires the experiment source/protocol tree to be committed and records its revision plus source hashes. It refuses to overwrite a completed report or publish a final report if experiment source changes during execution.

Model: [openai-community/gpt2](https://huggingface.co/openai-community/gpt2), revision `607a30d783dfa663caf39e06633721c8d4cfcd7e`, MIT. The model is loaded from safetensors with CPU float32 weights. Its parameters are frozen. The numerical reference receives an explicit float64 conversion of the captured Q/K/V. GPT-2 uses learned absolute positions; there is no rotary reference re-anchoring in this adapter.

Layer: 5, zero-based. Context: 256 tokens per window. Windows begin at token offsets 4096 and 12288 after removing the Gutenberg wrapper; input text is limited to its first 200,000 characters before tokenization. Supervised query positions: 63, 127, 191, 255. Context windows do not overlap within a document.

| Split | Gutenberg books |
| --- | --- |
| Training | 11 (Alice), 84 (Frankenstein), 1342 (Pride and Prejudice), 1661 (Sherlock Holmes) |
| Validation | 98 (A Tale of Two Cities), 2701 (Moby Dick) |
| Test | 74 (Tom Sawyer), 2600 (War and Peace) |

Raw and extracted-body SHA256 hashes are in `research/gpt2_data_manifest.json`. Exact repeated document content and repeated selected token windows are rejected. Held-out means excluded from reference-query optimization; these books may have occurred in GPT-2's original pretraining. No claim about novel foundation-model test data is made. Only two test books are used, so no broad generalization or statistical-significance conclusion is supported.

Tree geometry: chunk 4, depth 2, eight references per head. Seeds: 7, 23, 101. Each run starts with references sampled from supervised training queries, using a private seeded generator. Adam optimizes only reference queries for 100 single-window steps at learning rate 0.01, with gradient norm limited to 1.0. All initializations and settings are fixed before test evaluation.

The objective matches dense attention mass pooled into complete chunks at every level. The sink and incomplete tail use exact mass. It sums over levels and averages over query positions and heads. Input Q/K is detached; only the references receive gradients. For this fixed no-RoPE construction, direct summaries of a complete node equal recursively merged summaries in real arithmetic. The objective uses direct summaries to vectorize the training calculation.

Checkpoint selection evaluates validation KL every 10 steps. The initial checkpoint remains eligible; ties do not replace it. All seeds finish fitting and checkpoint selection before the test split is evaluated. Baselines are the untrained sampled-query initialization and untrained distribution-matched random references. Both use training information only.

## Adapter checks

Q/K/V are captured from the model's packed projection. Before accepting a trace, reconstruct its dense causal attention and compare against both native eager attention probabilities and the native attention output immediately before the output projection. Declared maximum absolute tolerances account for the explicit float32-to-float64 comparison: `3e-6` for weights and `3e-5` for outputs. Unsupported scaling, cross-attention, unfrozen/training mode, or a missing capture is rejected.

Hooks are removed in `finally`, including when the model fails. Captured tensors are cloned outside inference mode so they can safely be used as frozen constants during reference backpropagation. All backbone parameter bytes are hashed before capture and after fitting/evaluation; equality and absence of backbone gradients are required.

## Measurements

Evaluate the selected checkpoints and both untrained baselines at routing thresholds 0.73, 0.90 and 0.95. Record each query's actual retained dense attention mass, retained non-sink mass, attention-output L2 error, selected-key fraction and scored-summary count. Report individual books and aggregate means/medians/p95, along with all seeds. Query-level measurements are retained in JSONL.

Threshold equality is not sparsity equality. A higher-quality result that reads more keys is a cost/quality trade-off, not an automatic routing improvement. Dense-oracle comparisons and KL measurement are offline evaluation work; they do not provide a runtime certificate. Additional p=1 checks verify selected-ID completeness and numerical agreement with dense attention on the test activations.

This pilot makes no kernel-speed, whole-model perplexity, benchmark-score or semantic-correctness claim. Capturing activations from an unchanged dense backbone does not measure errors accumulated by closed-loop sparse generation.

## Reproduction

```sh
uv sync --locked --extra research
uv run --locked --extra research python -m research.prepare_gpt2
uv run --locked --extra research python scripts/verify.py
uv run --locked --extra research python -m research.run_gpt2_pilot
```

Preparation explicitly downloads the pinned model and public texts into ignored `.cache/gpt2-pilot/`; the numerical core has no network activity. The runner uses local files only. If source bytes change against the pinned manifest, preparation fails rather than silently substituting data. For a controlled source refresh, version and commit a new protocol/manifest before running a new experiment.

Raw texts, model weights and full activation caches are not committed. The small trained-reference checkpoints, protocol, source/data identities and measured reports can be kept in `experiments/`. Completed reports are protected against accidental overwrite; use `--output` for a distinct rerun.

## Validation scope

The regular tests check the pooled objective against a scalar oracle, reference gradients against finite differences, backbone-gradient exclusion, future-token isolation, holdout separation, deterministic fitting and initial-checkpoint eligibility. Optional adapter tests use a small random GPT-2 solely to check capture mechanics; the pilot itself loads the real pretrained checkpoint. Research dependencies are optional, so an environment without them explicitly skips those adapter tests.

The independent semantic-mutation checks include accidentally differentiating the teacher and reversing KL direction. They establish that the corresponding regression tests discriminate these faults; they are not a proof of all possible training correctness properties.
