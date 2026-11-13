# Scientific visual system

The dashboard at `http://127.0.0.1:8792/` now uses a cybernetics instrument composition: a dominant colour-mapped activity field, an adjacent retrieval hierarchy, a narrow navigation/configuration rail and five linked diagnostic plots. There is no branded masthead. One Solve action still starts a fresh maze; both structures follow the same decision. The continuous archive remains a separate optional experiment. See `UNIFIED_DASHBOARD.md` and `evidence/cybernetics-instrument-ui.json` for current verification.

## Activity field and point cloud

Height and colour encode **how many selected-decision-prefix reads returned a fact at each observed location**. Counts accumulate by location, including across revisions of that location; they are not the salience of one immutable fact. The scale is `log(1 + count) / log(1 + peak)`, with a zero-safe denominator. The colour scale reports the real peak, including zero. Original-point picking retains current-head source IDs and exact observed timestamps. Future observations and foreign returned IDs are rejected.

The height field interpolates adjacent observed-cell values on a 6×6 subdivision per cell. Unknown neighbours fall back to that cell's value; no patch is created over unknown cells. The point-cloud mode adds vertical display samples. These meshes/samples are rendering geometry, not additional memories, learned embeddings, an attractor landscape, a fluid simulation or a new numerical result. Observed-cell counts and display-sample counts are separate telemetry. The Canvas fallback renders a flat activity map, reports its actual point count and disables the unavailable point-cloud mode.

Diagnostics show the selected prefix's per-location return density, exact current returned mask, returned-fact history, actual hierarchy occupancy and observed object classes. Object colours have a compact key. All five use the same selected decision as the primary scene. Shared Home/End timeline controls update both cursor and displayed range value. The small cube bounds, backdrop grid, material bloom and camera easing are presentation only.


## Source projections

- **Layers** arranges indexed originals in ordinal slots. Summary coordinates are centroids of their recorded members in that display grid. Upright plates represent actual tree levels. Source bounds, membership and retained parent-child edges come from the recorded routing trace. The desktop atlas uses 24 columns; mobile uses 12.
- **Branches** is a canopy projection of exactly the same node IDs and retained edges. Leaf display slots use a deterministic equal-area spiral; summaries use their members' display centroids. Tube radii encode source membership size. This is a graph layout, not a learned embedding, a biological model, or a new energy landscape.
- **Tree** keeps the earlier Canvas inspection. Traces without recorded membership retain that limited representation. Graph-only/recovery steps remove the unused 3D field and clear its population readout.
- Original points distinguish raw-attended and returned records. The source inspector shows actual node composition and scores. Population bars show expanded/scored counts for this selected read.
- Small channel glyphs encode actual X/Y/object/colour/state values, with channel colour in the legend and normalised magnitude in glyph height. Exact values appear on hover. The graphics count is not the number of originals. The live field similarly exposes actual position/action/use/salience channels.
- Live world planes retain their observed coordinates, context and capped salience. Observed transitions and recalled displacement remain distinct. Missing-coordinate stripes and active replay-source rings preserve their previous source semantics.

## Visible motion and rendering

Three.js provides depth layers, quadratic links, branch tubes, channel glyphs, OrbitControls and a restrained UnrealBloomPass. GSAP animates the entrance, material reveal, view/focus camera transitions and explicit **Replay read** markers. The bounded read replay moves one marker along each recorded connection and stops. It illustrates the selected routing topology; its timing is presentation, not measured compute timing. There is no random particle loop.

Hover/pointer selection and keyboard inspection retain original IDs. Dragging changes the camera; it does not issue a query. Expand opens a full-size scene. Reduced motion skips entrance/replay movement and disables orbit. Canvas can be requested with `?renderer=canvas`; this preference survives address updates. Read-only links accept `step` and `view=layers|structure|tree`.

The shared source is `web/visuals/src`, with pinned dependencies and a reproducible local build. Run `npm test --prefix web/visuals` and `npm run --prefix web/visuals build`; both apps receive identical asset bytes. No runtime CDN is required. Pixel ratio is capped at 1.5. Material and replay tweens are killed when source geometry is replaced. The numerical core, planner, live engine and saved experiment files are unchanged. WebGL buffers are presentation only; numerical execution remains CPU float64.

## Verification

The earlier source/topology suite had 16 passing tests, including atlas membership, exact edges, source fields, portrait identity, finite branch geometry and replay cache invalidation. That milestone's locked Python suite passed 439 tests; lint, formatting, strict typing, JS syntax and existing routing contracts pass. Browser checks cover pointer picking, GSAP route movement and termination, view switching, cue retrieval, desktop/mobile overflow, visible playback, reduced motion, Canvas fallback and explicit observed-graph recovery. The updated evidence is `docs/evidence/observatory-redesign-browser.json`; earlier milestone evidence is retained separately.

The current unified-entry verification is `docs/evidence/unified-dashboard-browser.json`; earlier visual milestones remain separately recorded.

Current verification (13 November 2026): 452 Python tests, 27 visual/motion mapping tests, routing contracts, JS syntax, Ruff/format and strict core plus gateway/solver typing pass. The current browser evidence includes a fresh 95-action Key Corridor solve, four field projections, exact first/final cursor behavior, source keyboard inspection, a 390px control drawer without page overflow and the forced Canvas map. The numerical core, planner and frozen experiment artifacts are unchanged.


## Memory state cloud, 14 November 2026

For persistent task evidence, Memory cloud separates current observed heads into dormant (blue), retained active (cyan), and newly recovered (gold) bands. Recovered heads are a subset of the active workspace, not additional capacity. White rings mark facts actually returned to the planner. The live legend reports dormant, active/capacity, newly recovered and returned counts from the selected read receipt. It never displays the retrieval-frequency colour scale as a lifecycle legend.

X/Z remain observed map coordinates. Height inside each band uses the selected prefix's existing log-scaled location-return field. Dense cloud samples are display interpolation with an original source ID; primary source points, display samples and raw stored versions are distinct. The scene is not an energy landscape, learned embedding or biological salience model. The layer labels and legend state those semantics.

`memory_view=cloud` selects the shareable cloud projection. It survives a fresh solve. Mobile uses a compact two-column legend without horizontal overflow; reduced motion preserves the same data. Canvas disables cloud and hides its categorical legend.

A renderer correction prevents short reads from fading away: entrance opacity animates only on initial load, and transitions between active-world and ordinal-hierarchy coordinate systems snap framing. Same-space explicit projection changes may still ease. Tests cover both directions, consecutive decisions and reduced motion. The live task, numerical router and frozen experimental traces are unchanged.
