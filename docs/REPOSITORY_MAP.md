# Repository map

The project has one supported numerical library and a research workspace. Physical boundaries follow runtime responsibility; historical experiment snapshots stay intact.

```text
src/open_hierarchical_memory/  Installed, typed CPU float 64 attention API
  summaries.py                Affine summary construction and merge
  tree.py                     Owned immutable KV snapshots
  routing.py                  Hierarchical top-p traversal
  attention.py                Dense/selected-leaf execution
  contracts.py                Inputs, budgets, result states and failures
  training.py                 Differentiable summary-training primitives
research/
  task_memory/                Current task-support work, grouped by responsibility
    support.py                Compact paths and explicit connector recovery
    diagnosis.py              Observed-prefix planning interventions
    run_study.py               Frozen five-condition comparison
    protocol.json              Predeclared seeds, controls and capacities
    presentation.py            Audited study catalog and display metadata
  task_store.py                Versioned observations and active membership
  persistent_task_memory.py    Baseline bounded reader and explicit recovery
  task_references.py           Fitted reference identities and validation
  task_replay.py               Source-bound offline parameter updates
  minigrid_benchmark.py        Common observation-only symbolic planner
  somna_engine.py             Separate continuous dynamics/rehearsal prototype
  serve_task_benchmark.py     Local dashboard and bounded solver service
scripts/                      Independent audits, packaging and verification
web/dashboard/                Unified interface and shared task controls
web/task-lab/                 Task playback, navigation and trace inspection
web/visuals/                  Three.js/GSAP source, locks and renderer tests
tests/                        State, behavior, numerical and corruption checks
experiments/                  Immutable protocols, source snapshots and results
data/boxoban/                 Attributed official puzzle fixtures
docs/                         Component contracts and evidence
var/                          Ignored, user-owned runtime archives
```

The existing flat research modules retain their import paths because previous experiments and entry points use them. New support work is grouped in `research/task_memory/`; this avoids a bulk rename that would obscure scientific diffs or break reproductions. We do not move or reformat frozen `source-snapshot/` trees.

## Entry points

- `make dashboard`: unified local interface on port 8792.
- `make test`: Python and renderer behavior tests.
- `make verify`: full local gate, including clean installed-artifact checks.
- `make support-study OUTPUT=experiments/my-new-support-run`: reproduce the fixed support protocol in a new directory.
- `make replay-study OUTPUT=experiments/my-new-replay-run`: reproduce routing-parameter learning separately.

The package wheel/core sdist contain the numerical API. Clone the repository for experiments, fixtures, research extras and the dashboard. Files under `experiments/*/source-snapshot` are historical executable evidence, not duplicate active modules to edit.

## What is separate

The continuous-world dynamics learner and the MiniGrid task controller have distinct learned targets and evidence. Running a maze does not train the continuous-world networks. The routing replay study updates reference vectors offline; the path-support study changes observed-evidence availability without training a new neural model. Neither is a full language-model conversion or a production assistant.
