# Local release preparation

14 November 2026. Research code and assets are verified locally; the recorded viewer is deployed on Vercel. No package release or repository visibility change was performed.

- Supported package/API scope is explicit; research/dashboard remain checkout tools.
- New support work is grouped in `research/task_memory/`; established imports and immutable source snapshots remain intact.
- Root README now leads with the working demonstration, controls, limitations and reproducible commands.
- Contribution, security, licensing and current-roadmap documents are present.
- Core source distribution excludes the large research artifacts, data and browser bundles. Wheel and sdist both install into fresh locked environments and exercise the public sparse path.
- 509 Python and 41 renderer/motion tests pass. Full 26-command local gate, independent historical/current audits and strict typing pass.
- Official actionlint 1.7.12 validates the workflow; its downloaded artifact was checked against the official release checksum. Hosted CI was not run/assessed in this pass. The workflow now installs the benchmark/research extras required by its tests.
- Desktop/mobile browser checks cover source counts, original/connected controls,64-fact capacity and a fresh 81-action solve. The X assets are draft material.

Remaining research limits are in [ROADMAP.md](ROADMAP.md); publishing is distinct from local verification. No firstness, GPU/whole-model performance, ZHA superiority or production-readiness claim is made.

The original two Key Corridor regressions now solve in99/151 actions. The fresh96-run comparison still solves22/24 for each method; all failures are retained. See [repair results](../experiments/task-support-v2/SUMMARY.md) and [hosted scope](HOSTED_DEMO.md).
