# Project agreements

Read PROGRESS.md and docs/ENGINEERING_PLAN.md before extending scope. Keep the independent scalar oracle independent of production summaries, tree construction and routing. Preserve causal visibility, batch/head isolation, explicit approximate semantics, immutable tensor ownership and typed failure states.

Use CPU float64 until another backend has its own evidence. Never call an ordinary floating-point estimate a certified bound. No whole-model, speedup, firstness or production-readiness claims without corresponding evidence. Do not add network activity to the numerical core. Record test commands and remaining gates in PROGRESS.md after each milestone.

Before committing, run the locked tests, Ruff and strict mypy. Verify an installed wheel for packaging changes. No public releases or package publication without the user's authorization.
