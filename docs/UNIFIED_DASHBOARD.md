# One task, one evidence timeline

Open `http://127.0.0.1:8792/`. Select a maze and method, then **Solve maze**. This launches a fresh official MiniGrid episode. The navigation inset, hierarchy, observed-memory field and Observe / Retrieve / Plan / Act receipt all follow that episode's selected decision. The initial saved example is labelled separately. The two structures no longer require independent start actions.

## Reading the views

The hierarchy shows one selected cue and routing pass. Its raw-attention count can differ from the total returned memory: the planner combines multiple cues/passes and dependency support. The memory field shows current observed heads at the same step. Cyan is observed memory, gold is returned memory, and purple marks facts used in the current plan. Vertical layers distinguish observed and returned facts; their height is not learned salience or confidence. Selecting a point shows its original ID and observation step. Unknown cells are never filled from the simulator's hidden layout.

Playback starts automatically when the first real decision arrives. The single timeline pauses or scrubs both structures together. Computation can finish ahead of playback; the status explicitly reports actions computed. Playback speed changes display pacing, not solver execution speed. The top layout selector expands either structure; camera actions remain in the view menus. Mobile Controls opens the same rail.

Four maze families are supported: MemoryS17Random, MultiRoomN6, DoorKey16x16 and KeyCorridorS6R3. Supported fresh readers are progress/cues ZHA or exact, dependency-bundle ZHA or exact, and the observed-graph comparison. Progress recovery is labelled when it uses the observed graph. This remains the existing hand-written observation-aware planner with hierarchical retrieval, not a trained neural maze policy. Saved Boxoban cases remain inspectable; they are not advertised as fresh maze solves or assigned invented spatial-memory evidence.

## Independent archive

Independent archive tools remains collapsed. It can switch the right view to the existing continuous-memory archive and access its separate collect/fade/learn/query operations. This is an explicitly different experiment. No maze action claims to train its weights, consolidate its memories, or add observations to its database. The default task flow never contacts or resets that archive. The8791 page still redirects to the dashboard; its existing API process remains the archive owner.

## Solver lifecycle

`research/live_solver.py` owns one worker and one latest run. It invokes the existing `run_progress_benchmark.run_episode` with an optional post-action evidence observer. The observer does not change selection, planning or simulator inputs. Completed decisions, route events and their source layouts are copied into a bounded append-only run. No frozen experiment files are overwritten.

Same-origin JSON POST `/api/solve` starts a run with an allowlisted environment/reader, integer seed and action cap of1–1024. Only one worker is admitted; a second start gets409. POST `/api/solve/cancel` stops the matching run cooperatively after the current decision. GET `/api/solve?id=…&after=…` returns at most16 contiguous decisions with the route events and layouts they reference. The evidence cursor and original source IDs are preserved across incremental transport. The URL retains the solve ID, so refresh resumes that run rather than starting a duplicate. A server restart expires in-memory runs and is reported explicitly.

Execution is bounded by the requested actions, a90-second cooperative wall budget and64MiB of retained trace data. No hard preemption is claimed inside a single numerical operation. Typed states are running, solved, limited, cancelled and failed. Cancellation/error cannot publish successful completion. Model errors, cutoffs and failures retain the valid evidence already published. A failed evidence poll offers retry without launching another worker. Shutdown requests cancellation and joins the worker for up to3seconds.

## Components

`web/dashboard/` coordinates the workflow and renders the task memory with the existing Three.js/GSAP bundle or Canvas fallback. `web/task-lab/` retains the existing hierarchy/observation controller and adds owned evidence, fresh-run initialization and append adapters. Task frame messages are accepted only from that known same-origin window. `taskMemoryModel` checks temporal visibility and returned-source membership before rendering. The optional continuous archive retains its existing controller and bounded gateway.

The visual direction continues the supplied scientific-wireframe references, viewport/sidebar proportions from the [Three.js editor](https://threejs.org/editor/) and coordinated views from [Vitessce](https://vitessce.io/). No outside assets or code were copied for this change.

## Verification

Behavioral tests cover a real fresh Key Corridor solve, contiguous route/layout transport, original ownership, observer parity, cancellation, duplicate-worker rejection, trace limits, invalid configurations and HTTP origins. The visual mapper tests temporal visibility, exact returned IDs and plan geometry. Browser checks cover shared cursor/source inspection, automatic paced playback, refresh recovery, stop/restart, optional archive access, Canvas fallback and mobile sizing. Source-bound results are recorded in `docs/evidence/task-solve-dashboard.json`; the previous UI-only milestone remains in its own evidence file.


## 10 November 2026 visual refinement

Navigation now sits at the top of a320px desktop rail, in a240px tall canvas rather than the old144px thumbnail. It draws at its actual display resolution from the task controller's observed/current/recalled data; it no longer scales up a small offscreen bitmap. Typography, controls and separators use neutral tones with restrained semantic colours. Human-readable planner objectives replace machine strings.

A persistent low-opacity antialiased floor grid supplies depth beneath both3D structures. It is context geometry only and adds no data points or axes claims. Less opaque plate grids, outlines and links let active observations carry the contrast. Plane/anchor labels avoid collisions. Auto-framing eases changes to camera span/target while preserving orientation, rather than snapping to the home pose on new bounds. Drag/orbit/focus still retain user camera control.

`PoseTween` interpolates only adjacent poses from the same evidence source during playback. The movement stops exactly at each observed target. Scrubbing, changing source, nonlocal moves and reduced motion snap to exact poses. The interpolation is presentation only; observations, fact identities, actions and decision timestamps remain unchanged. Navigation draws on animation frames only while dirty or transitioning. The helper is bundled with the existing visual runtime, so updating the UI did not restart either backend or expire the current solve.

The official [Drei Grid](https://github.com/pmndrs/drei/blob/master/src/core/Grid.tsx) and [Three.js dynamic-buffer example](https://github.com/mrdoob/three.js/blob/dev/examples/webgl_buffergeometry_drawrange.html) were read as implementation references. The grid/motion code is independently written for this existing vanilla Three.js interface; no React dependency was added.

Verification:452 Python tests,21 visual/motion tests, routing contracts, lint/format and strict typing pass. Browser checks cover actual intermediate poses, exact reduced-motion samples, mobile navigation/primary-action fit, focus layouts, source inspection, Canvas fallback and a fresh95-action solve. No FPS or numerical speedup claim is made. Source-bound evidence: `docs/evidence/refined-observatory-ui.json`.

The next proposed research milestone is persistent task memory across episodes, followed by a controlled wake/replay/forget/retest experiment against exact and graph controls. This requires implementation and evaluation; the UI refinement does not connect maze decisions to the independent continuous-learning engine.


## 13 November 2026 — cybernetics instrument

Rebuilt the shell around the user's fluid-simulation and LIDAR references. The primary field uses a blue/cyan/green/yellow/orange retrieval-frequency map inside a wireframe volume. A secondary hierarchy retains real source spans and node selection; bottom diagnostics expose density, the current read, history, occupancy and object classes. The maze stays at the top of the scrolling control rail. The user subsequently requested removal of SOMNA and the entire top strip: the masthead and connection badge are gone, the layout selector is under Run & query, and the workspace begins at the top edge. On narrow screens a small Controls button opens the rail.

Activity is derived only from published observations and reads up to the selected decision. Interpolated surface and interior cloud samples are explicitly display geometry, with a separate count. This does not connect the independent continuous-learning archive to the maze or implement new forgetting, replay or consolidation dynamics. Canvas remains a flat-map fallback. Existing CPU float64 solving and numerical policies are unchanged.

Verification and source hashes: `evidence/cybernetics-instrument-ui.json`. The local service remains on8792; there is no public push/release.


## 13 November 2026 — persistent memory in the Solve workflow

Open `http://127.0.0.1:8792/`. The initial view is a labelled saved development recording: Key Corridor seed 9001, decision 42 of the completed persistent-task-v2 experiment. It is not live execution until Run solver is pressed. The existing header-free cybernetics layout, maze rail, hierarchy and memory field remain one dashboard.

The default Fitted ZHA · persistent memory method loads eight trained reference vectors from `experiments/persistent-task-v2/fitted-references.json`. It runs the reviewed persistent reader with the shared observation-only symbolic actor. No reference fitting happens in the browser or during the solve. Training/validation context reuse and unavailable checkpoints fail before a worker is started. Fixed ZHA, random references, always-recover ZHA, exact recovery and no-cold-recovery remain selectable controls in the same Method menu. Older studies remain accessible through Saved study.

Memory layers now separate dormant canonical heads, active payloads and sources actually recovered on the selected read. Rings mark the facts actually returned to the planner. The lifecycle section reports active/capacity, dormant, recovered and retired/evicted counts; it exposes the checkpoint identity, gate reason and raw/summary/rerank work under Source & work. Age retirement, capacity eviction and superseded active versions are distinguished in source evidence. Observation admission can evict facts before a retrieval starts; its removals are derived from adjacent published active sets, excluding corrected versions, and combined with explicit read/retirement receipts. This presentation derivation never changes the reader, graph or actor.

When the recovery gate defers archive access, the hierarchy viewport shows only actual available payloads and is labelled Active workspace / Archive idle. It does not animate a fabricated tree read or keep a stale hierarchy from another decision. Exact/no-recovery methods likewise show their actual workspace. Numerical routing decisions retain their true source IDs, scores, selected nodes and original spans. Complete-chunk extents are reconstructed from the declared geometry; numerical scores and kept edges are never inferred from graphics. Retired originals remain stored. New task solves do not run sleep, learned consolidation or the independent continuous-memory process.

Run solver creates `var/task-solves/<solve-id>/memory.sqlite`, an immutable `references.json` checkpoint and a small completion `result.json`. These files are ignored by Git. They are local diagnostic archives, not a distributed service. Closing and reopening validates the archive at completion. A browser refresh can recover the same process-owned run, source identity and selected completed decision. A service restart expires the in-memory playback job; it does not resume simulator state, although its SQLite originals and completion record remain on disk. Starting again creates a new archive/reset namespace. Do not delete these archives while a worker owns one.

Original v2 experimental files did not store egocentric image arrays. The saved-view adapter reconstructs those arrays using official MiniGrid replay of the saved actions and checks reward/termination parity. It adapts traces in memory; frozen files remain byte-for-byte unchanged. Fresh solves now publish the actual egocentric observation alongside the same action/source receipt. A parity test confirms the observer does not alter actions, selected sources or persistent controller state.

The initial UI run and a fresh fitted Key Corridor seed 9001 solve complete in 78 actions. At decision 58, 96 facts are active, 92 dormant, 16 recovered and 31 returned. Those are diagnostic observations, not new benchmark/generalization or superiority claims. The default method's task features remain structured and hand-designed. The paper's approximate router still has no per-query global mass guarantee; graph and index costs remain extra.

Verification covers 482 Python tests, 33 visual/motion tests, the full 21-command local gate and independent scientific audits. Browser checks cover the real Run solver action, source inspection, exact-reader selection, next memory event, temporal rewind, same-job refresh, 390px controls, reduced motion and Canvas fallback. See `evidence/persistent-dashboard.json`. No public push or release.
