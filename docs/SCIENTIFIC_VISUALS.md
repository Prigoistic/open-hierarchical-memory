# Scientific visual system

The supplied references guide the visual treatment: layered volumes, fine wireframes, discrete luminous points, narrow annotations and close inspection on black. They are aesthetic references, not experimental evidence. The interface remains a research instrument: every plotted point and connection must have an inspectable source.

## Shared renderer

`web/visuals/src/scene.mjs` supplies the locally bundled Three.js renderer, OrbitControls and GSAP camera transitions for the live memory and recorded task labs. `models.mjs` converts source records into presentation geometry; it has no simulation, retrieval, planner or numerical-backend role. The Python numerical engines remain CPU float64. WebGL buffers are presentation geometry only.

Rebuild from the pinned lock with `npm ci --prefix web/visuals --ignore-scripts`, then `npm run --prefix web/visuals build`. Run mapping checks with `npm test --prefix web/visuals`. Identical bundle and CSS bytes are copied into both existing static apps. `build-manifest.json` records versions and hashes. Runtime rendering makes no CDN requests. Dependency and license details are in `web/visuals/THIRD_PARTY.md`.

## Visual meaning

- Cyan and rust distinguish the two observed contexts. Gold marks selected raw evidence. Violet outlines identify the recorded sources of an active offline replay update.
- In the live field, horizontal coordinates are the recorded positions; context selects a plane; height encodes salience capped at 2. Tiny arrows show observed transitions. The separate white arrow shows the recalled displacement only when the position and context are fully specified.
- One missing coordinate becomes a stripe. Read links originate on that stripe at the selected record's available coordinate. A fully missing position gets no fabricated point or crossing; unknown context marks both planes. Hidden coordinates are never disclosed by a prediction arrow.
- In the recorded hierarchy, original points use source positions divided by 8 for display. Summary points sit at the centroid of their recorded member facts; height is the actual tree level. These centroids are a visual projection, not model embeddings or a learned energy landscape. Connections are exactly the retained parent-child edges from recorded spans. White outlines distinguish returned facts from raw-attended originals.
- Dormant/pruned records are dim. Graph-only and graph-recovery decisions display the existing explicit text instead of an unused hierarchy. Historical traces lacking source spans retain their limited Canvas representation.

## Interaction and motion

Drag to orbit, wheel or pinch to zoom, and use Home, Focus read or Expand. Orbit is opt-in and never starts automatically. GSAP animates only the camera and view focus; records never drift or fire for decoration. Selecting or hovering a point reveals its original ID and actual metadata. Existing keyboard inspection and cue controls remain available. A drag must not submit a query.

Camera framing adapts to the available viewport and source bounds. Manual camera movement is preserved across data updates. Rendering sleeps when the scene is hidden or offscreen; geometry, materials, controls and observers have explicit disposal. Pixel ratio is capped at 2. Reduced-motion preferences disable orbit and make view changes immediate. `?renderer=canvas` forces the existing renderer; a failed WebGL initialization also selects Canvas.

## Verification

Mapping tests cover immutable source ownership, original IDs, true centroids/edges, masking, archive identity, actual replay sources and separation of observed transitions from recalled prediction. HTTP tests cover only the two newly whitelisted assets. Browser checks cover desktop and 390px layouts, source selection, partial queries, real pointer dragging, keyboard inspection, Layers/Tree switching, fullscreen, reduced motion, graph fallback and both Canvas paths.

The saved browser evidence is `docs/evidence/scientific-visuals-browser.json`. These are presentation checks, not new retrieval-quality, performance or biological claims. Existing experiment reports and model/planner source were not changed.
