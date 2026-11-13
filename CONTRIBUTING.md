# Contributing

Start with [the repository map](docs/REPOSITORY_MAP.md), [current results](docs/PROJECT_OVERVIEW.md) and the contract for the component you are changing. The original engineering plan is historical; later dated contracts supersede its completed gates.

## Setup and validation

Python 3.12 or 3.13, uv, and Node.js are used for development. The committed uv/npm lockfiles define dependency identities.

```sh
uv sync --locked --extra research --extra benchmarks
make test
make verify
```

`make verify` includes independent numerical/task audits, semantic mutation checks and fresh wheel/source installation checks. `make test` is a faster behavior pass. Changes to rendered behavior also need a desktop/mobile browser check; a clear console alone does not validate the workflow.

Only `src/open_hierarchical_memory/` is the installed numerical API. CPU float 64 and explicit approximate/dense semantics are the supported contract. Research readers, local persistence, task controllers and the dashboard run from a Git checkout. Keep new task-memory work in `research/task_memory/`; preserve established imports used by recorded studies.

## Research changes

Declare the hypothesis, dataset/splits, controls, resource accounting and stopping rule before a fresh comparison. Use new experiment directories. Never edit previous traces or source snapshots to improve a result. Record failures and distinguish development seeds from fresh evaluation. Random, exact, graph and unchanged controls remain important even when they outperform a proposed method.

Changes to numerical routing require the independent oracle and negative controls. The independent auditors must not import production feature, summary, routing, packing or policy implementations. Approximate top-p routing does not certify global retained mass or correct task answers.

Original observations are immutable; corrections append versions. A new simulator world/reset gets a new context. Cached evidence must invalidate on correction and preserve source/capacity parity. Imagined rollouts must stay separate from observations.

## Changes and reviews

Keep a pull request focused on one mechanism. Explain the trigger, resulting behavior, evidence and remaining limits. Include the exact validation commands and source/result locations. Update `PROGRESS.md` for a completed milestone. Formatting-only changes to frozen experiments are prohibited.

Our source is Apache 2.0. Third-party assets have separate notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). Do not add credentials, private archives, screenshots containing account details or unlicensed material. Mutable local archives belong under ignored `var/` or an experiment's ignored `archives/` directory.
