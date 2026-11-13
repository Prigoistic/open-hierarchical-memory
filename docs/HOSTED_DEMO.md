# Memory Observatory

Production viewer: https://recall-observatory.vercel.app

The static Vercel site contains every run in the independently audited96-run `task-support-v2` cohort. It uses the same Three.js/GSAP inspector, real source-owned observations, recorded routes, active/dormant/recovered membership, source picking and decision timeline. The opening is Key Corridor25003, repaired ZHA, decision63:229 current observed sources,64 active,165 dormant,6 recovered and11 returned.

Playback is explicitly labelled and independent of solver timing. Hosted controls do not call the fresh-solver API. The continuous-world learner and mutable SQLite stores are not deployed. Runtime archives, credentials, user-owned live sessions and source snapshots are excluded from the allowlisted upload. This is not a persistent multi-user compute service.

The public protocol and full raw aggregate report are linked in the controls. Repository access remains private; no inaccessible public source link is advertised. No repository visibility change or package release was performed.

## Rebuild

From an authorized checkout, run:

```sh
uv run --locked --extra research --extra benchmarks python -m scripts.export_dashboard --output release-assets/new-observatory-export
vercel link --yes --project memory-observatory --cwd release-assets/new-observatory-export
vercel deploy --prebuilt --prod --cwd release-assets/new-observatory-export
```

The exporter refuses to replace an existing output and validates that all audited runs, including failures, are present. It checks source artifacts through the task catalog, replays saved official actions for adaptation and records SHA256 hashes for uploaded files. The Build Output API bundle contains static files and security headers; there are no serverless solver functions.

Vercel's production project domain `recall-observatory.vercel.app` follows future production deployments. Automatic Git deployments are disconnected because the repository root is a Python research project and the static bundle is generated/ignored. Preserve that boundary or configure a deliberate export build before reconnecting Git.

## Verification

509 locked Python tests,41 renderer/motion checks, strict typing, lint/format, the full26-command local gate and clean wheel/source installations pass. The latest96-run study and separate4-run exposed diagnostics pass independent official-action/source/capacity audits. Desktop1440px,390px mobile, keyboard original inspection, Canvas failure inspection, playback progression and no-solver-request checks pass. Hosted CI was not assessed.
