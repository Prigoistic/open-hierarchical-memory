# Open Hierarchical Memory

An independent research implementation of the no-positional-encoding construction and routing rules in [Zyphra Hierarchical Attention](https://arxiv.org/abs/2610.42112).

**Development reference, not a production memory system.** Initial scope: immutable snapshots, CPU float64, explicit prefix visibility, and dense or approximate attention. The reference queries are supplied by the caller; no trained checkpoints are bundled. Sparse output has no per-query accuracy guarantee. Original KV entries remain stored.

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

See [progress](PROGRESS.md), the [engineering plan](docs/ENGINEERING_PLAN.md), and [method mapping](docs/METHOD.md). Positional adapters, model-layer training, persistence, the inspector and conservative runtime bounds are separate future gates.

This project is independent and is not affiliated with Zyphra. The paper's authors retain credit for ZHA. No code has been copied from their implementation.

