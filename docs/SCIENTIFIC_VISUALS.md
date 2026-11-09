# Scientific visual system

The current single dashboard at `http://127.0.0.1:8792/` shows the recorded hierarchy and live memory field together. A narrow side rail contains run selection, navigation, memory actions and source inspection. Only the two primary workflow buttons are visible by default; detailed settings and camera actions are disclosed on demand. Focus layouts expand either structure. See `UNIFIED_DASHBOARD.md` for the integration and source boundaries.

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

The current source/topology suite has 16 passing tests, including atlas membership, exact edges, source fields, portrait identity, finite branch geometry and replay cache invalidation. The locked Python suite passes 439 tests; lint, formatting, strict typing, JS syntax and existing routing contracts pass. Browser checks cover pointer picking, GSAP route movement and termination, view switching, cue retrieval, desktop/mobile overflow, visible playback, reduced motion, Canvas fallback and explicit observed-graph recovery. The updated evidence is `docs/evidence/observatory-redesign-browser.json`; earlier milestone evidence is retained separately.

The current unified-entry verification is `docs/evidence/unified-dashboard-browser.json`; earlier visual milestones remain separately recorded.
