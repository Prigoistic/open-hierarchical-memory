# One memory laboratory

Open `http://127.0.0.1:8792/`. This replaces the separate task/live entry pages. The dashboard shows the recorded hierarchy and the live archive at the same time. The old8791 page redirects here; its API process remains the archive owner. No additional user-facing preview port is needed.

## Navigation

The side rail contains Task and Method, a thumbnail of the recorded navigation, the live record/update counters, Run memory cycle and a shared selection inspector. Run/query and memory details remain collapsed by default. Only Play and Run memory cycle are normal visible buttons on desktop; camera/reset/replay actions are in per-view menus. Both structures is the default layout; either focus option expands one view. On mobile, Controls opens the rail and the structures stack.

The recorded timeline, query pass and selected source stay local to their task trace. The live field has its own cue, archive and learning job. Changing a view never rewinds the selected recorded step. The canonical URL is taken from the controller's actual run identity, not its UI selector labels.

## Implementation

`web/dashboard/` is the single shell. The existing visual controllers run in same-origin view documents, exposing small snapshot/command adapters. Each retains its own DOM and state; only serializable metadata and explicit commands cross the view boundary. Selection messages are accepted only from the two known windows on the dashboard origin. Snapshot data is copied rather than exposing mutable source arrays.

`web/visuals/embedded.css` removes the old surrounding UI and lets both visualizers fill their panels. The side-rail navigation thumbnail copies the actual task canvas. Both old panel code paths and Canvas fallbacks remain available to the shell. The build copies and hashes the embedded style and boot assets alongside the existing shared rendering bundle.

`research/dashboard_gateway.py` forwards a fixed set of live operations to a configured127.0.0.1 service. It requires the exact same dashboard origin for writes, bounded finite JSON objects, bounded replies and the expected live-state schema. It does not use environment proxies, follow redirects, forward arbitrary URLs, or expose reset/remember through this bridge. Errors from live operations remain explicit. This is a local research interface; task archives and the numerical engines are unchanged.

## Visual references

The supplied scientific-wireframe references remain the visual direction. The Three.js editor (`https://threejs.org/editor/`, viewed9November2026) informed the viewport/sidebar proportions and progressive disclosure. Vitessce (`https://vitessce.io/`) informed the use of multiple visible scientific views in one workspace. No code or visual assets were copied from these sites.

## Verification

The browser verification covers one-origin panel loading, timeline control, source picking into the shared inspector, view/focus changes, cue drafts surviving synchronization, a returned partial query and a complete isolated memory cycle. A test archive grew256→288 observations and completed160 learning updates while the recorded task stayed at its selected step. The user's actual archive retained all480 originals and the same source checksum during the dashboard switch.

HTTP tests cover the shell and panel assets, framing policy, same-origin writes, invalid and oversized requests/replies, disabled operations, protocol errors, redirects, outages and response-read timeouts. The locked suite passes439 tests;16 visualization tests and the existing routing contracts pass. Ruff, formatting, strict core typing and the typed gateway check also pass. Detailed source-bound evidence is `docs/evidence/unified-dashboard-browser.json`.
