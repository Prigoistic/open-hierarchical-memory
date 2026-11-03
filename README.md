# Open Hierarchical Memory

An independent research implementation of the no-positional-encoding construction and routing rules in [Zyphra Hierarchical Attention](https://arxiv.org/abs/2610.42112).

**Development reference, not a production memory system.** Initial scope: immutable snapshots, CPU float64, explicit prefix visibility, and dense or approximate attention. The core accepts caller-supplied reference queries. Small fitted-reference checkpoints from a scoped GPT-2 layer pilot are available under `experiments/`; they are not a converted model. Sparse output has no per-query accuracy guarantee. Original KV entries remain stored.

```sh
uv sync --locked
uv run pytest
uv run python examples/synthetic.py
```

For everyday local verification, independent of GitHub-hosted compute:

```sh
uv run --locked python scripts/verify.py --profile core
```

This runs tests, lint, formatting, strict typing, semantic mutation checks and the synthetic example. It writes a separate core report and does not claim package-installation or hosted-CI validation. The default `full` profile also checks fresh wheel/source installs and remains required for release and packaging changes. Its offline installation checks require the locked dependencies to be cached; after cache removal, `uv sync --locked --reinstall` repopulates that cache.

The example uses synthetic data and reports offline attention-error measurements. It does not reproduce model-quality or speed results from the paper.

See [progress](PROGRESS.md), the [engineering plan](docs/ENGINEERING_PLAN.md), and [method mapping](docs/METHOD.md). RoPE adapters, persistence, the inspector, conservative runtime bounds and closed-loop model conversion remain separate gates.

This project is independent and is not affiliated with Zyphra. The paper's authors retain credit for ZHA. No code has been copied from their implementation.

## Measured layer pilot

The [frozen GPT-2 pilot](experiments/gpt2-layer5-pilot-v1/SUMMARY.md) fits only 6,144 routing-reference parameters per seed. Held-out pooled KL improves in all three seeds. At threshold 0.73, mean attention-output L2 error is 11.9% lower than the untrained sampled-query initialization at nearly equal selected-key fractions. The random-reference baseline is close, and higher-threshold results are mixed. This covers one layer, 256-token contexts and two test books; it establishes no whole-model quality or speed claim.

The [protocol, optional research setup and reproduction commands](docs/GPT2_PILOT.md) distinguish native-capture checks from real pretrained-model measurements. Research dependencies are optional: `uv sync --locked --extra research`. Include `--extra research` in subsequent `uv run --locked` commands to retain them; without the extra, optional GPT-2 adapter tests are skipped explicitly.
