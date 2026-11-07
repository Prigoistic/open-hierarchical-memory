# Somna: live episodic memory and learned offline rehearsal

8 November 2026. Implemented CPU float64 research prototype. The working name does not rename the repository/package or imply affiliation with Zyphra. This extends the earlier [symbolic diagnostic](SOMNA.md); its unique-state lookup task is not used as evidence for the current memory system.

## What actually runs

The live inspector sends real requests to a local Python engine. Observations enter an immutable, versioned SQLite archive. Continuous partial cues search a numerical hierarchy over dormant observations. Selected dormant sources reactivate into a bounded workspace, whose hierarchy supplies observed transitions for retrieval and neural training. Offline jobs update actual neural parameters and publish completed-step snapshots while they run. A learned dynamics ensemble can then generate short predicted spatial trajectories. Those predictions never become observed facts.

The controlled task has continuous position `(x,y)`, a two-dimensional action and one of two visible contexts. The second context rotates the action response. Initial collection contains256 observations, only16 in the rare context, followed by a long common-context phase. A query can omit a position axis, action or context and add view noise. Many observations share each partial cue; no state ID, episode ID, expected successor or answer label is accepted as a query. The engine also accepts external observed tuples through `/api/remember`, so data are not limited to its built-in simulator.

This is structured continuous-state learning, not a learned image encoder, language-model memory product or biological dream mechanism. The visual display decodes the actual two-dimensional states directly.

## Representation and actual hierarchy

Keys and queries share12 fixed coordinates. Each position coordinate contributes `3cos(pi*x/2), 3sin(pi*x/2), 3cos(pi*x), 3sin(pi*x)`. Actions are scaled by4 and the two context indicators by6. Missing cue components contribute zeros. Values are observed successor displacements. The half-frequency components distinguish the supported clamped boundaries at-1 and+1; earlier periodic coordinates could not, an error found by independent review. `FEATURE_VERSION` is now `continuous-half-harmonic-cue-v2`.

Cold search uses the existing no-positional-encoding ZHA numerical core, chunk4, depth3, eight reference channels and p=.25, with caps of128 raw attention pairs and512 scored summary nodes. Its selected raw observations, not a hidden full-bank nearest-neighbor search, determine up to four dormant reactivations. A rotating physical archive page of16 rows provides an independently charged coverage safeguard, including superseded/already-hot rows in that read budget. At most four page candidates reactivate. There is no claim that either approximate selection or coverage guarantees recovery.

The default active workspace contains at most48 current observations. Its chunk4/depth2/p=.8 hierarchy returns a numerical selected-attention displacement mixture and ranked observed sources. Training uses at most16 of those actual selected sources. Archive IDs appear only after search for provenance and explicit manual restore/correction operations; they are not a query-time answer shortcut.

The original records remain stored. Both indexes own immutable numerical snapshots, bind current reference coordinates and exclude superseded versions. Ingest/correction rebuilds affected indexes; fitted reference changes invalidate both. Index key rows, summary nodes, reference-channel scoring, construction time and owned tensor bytes are recorded. Cold indexes and the small inspection cache still retain the growing archive in memory: the active limit is not a promise of bounded total storage or RSS.

Eight reference vectors can be fitted with the existing pooled-KL objective. Eight augmented observed cues train the references; four separate augmented cues select the checkpoint. External comparison states do not enter that API. Random-reference controls are retained. This small internal validation set does not establish general retrieval quality or fitting superiority.

## Forgetting, correction and persistence

Active salience is `(1 + log(1 + actual_hits)) * 2^(-age/32)`, with age measured since the most recent actual use or explicit refresh. Logical ticks, not wall-clock seconds, define age. Replay/coverage refreshes do not fabricate actual-use counts. Advancing time retires active entries below.5; manual restore or a subsequent numerical query can reactivate them. Neither operation deletes canonical observations. Neural parameters can retain information after an episode leaves the workspace; this is reversible execution/index forgetting, not certified parameter erasure.

Corrections append a new observed version and atomically replace its explicit current head. Old versions remain inspectable but cannot be returned or trained from either index. A correction also invalidates the learned model and immediately clears the stored imagined path. The next offline job starts fresh neural parameters and learns only from current heads. This avoids pretending that a previously trained network automatically unlearns the old outcome. It does not guarantee perfect relearning.

SQLite transactions persist originals/heads, hot membership, usage/refresh metadata, archive cursor, logical clock, cumulative work, numerical references and model parameters in inert JSON with integrity hashes. POSIX file locks enforce one controller per archive and a separate configured-session namespace lock remains held across reset/pointer transitions. Application.close() releases ownership after its worker stops. Independent review reproduced and verified the boundary, stale-forecast, default-restart and reset-race fixes; see [recorded evidence](evidence/somna-independent-review.json). Cached numerical indexes rebuild after restart. Interrupted jobs retain their last committed completed updates and reopen as interrupted, never silently complete.

Reset creates a separate archive while preserving the previous file. An atomically replaced, checksummed active-session pointer makes the same launch command resume the new active archive. API `session.active_archive` identifies that file. Pointer-write failure restores the previous controller. These local filesystem tests are not a universal crash-durability or malicious-file security proof.

Known old periodic-coordinate sessions migrate explicitly: canonical physical observations and compatible physical-input dynamics weights remain; old routing references/indexes and stored forecasts are invalidated. Unsupported formats or bad checksums fail rather than silently erase data.

## What offline learning and imagination mean here

Three independent `6→24→24→2` tanh MLPs predict displacement from position, action and context indicators:2,454 learned dynamics parameters total. Each ensemble step trains on observed transitions actually selected through memory, using mean squared error, SGD rate.06 and gradient-norm cap5. No simulator is available to the update rule, and a test replaces the simulator with a failing function during offline learning.

Uniform replay samples observed cues. Priority uses prediction error over the current hot set and charges that scan. Pure coverage favors the rare context and stale refreshes, charging its metadata scan. The separate mixture policy uses rare coverage every fourth read and uniform sampling otherwise. Uniform and rare-only policies expose a real interference tradeoff; the mixture is a fixed hypothesis, not a universally optimal schedule.

Rollouts use learned action-conditioned predictions, not simulator frames. A short greedy model-based planner chooses actions toward a displayed goal. Each predicted point is labeled `imagined`, has contributing observed source IDs, a model checkpoint hash and an ensemble-spread diagnostic. Model maturity, same-context observed support, disagreement and domain checks can stop the rollout. Ensemble spread is an uncalibrated heuristic: agreement does not prove that a prediction is correct. Rejected or invalidated forecasts replace stored display state rather than leaving an old plausible path visible.

This is nonverbal learned state prediction and rehearsal. It does not demonstrate subjective dreaming, an unconscious language-model subsystem, symbolic insight or general compositional reasoning.

## Evidence and its limits

The [corrected-coordinate v4 comparison](../experiments/somna-continuous-v4/SUMMARY.md) branches identical observed banks and neural checkpoints into no-update, uniform, priority, pure coverage and mixed replay, with hot-workspace dense-reader controls and discarded-update controls. Dormant traversal is held fixed in those learning controls; full-bank dense/exact-neighbor diagnostics and ordinary replay are separate stronger controls. Each context evaluates192 new continuous positions per training seed. V4 uses fixed1501/1502/1503 states after earlier cohorts became development evidence. Training and evaluation share the same two synthetic dynamics laws; this is not transfer to new physics.

Each learned condition receives160 read/update opportunities. Actual examples, recovery, scheduler, routing, reference and index work differ and are reported; equal gradient limits do not mean equal total compute. Discarding learned parameters returns model quality to the initial checkpoint despite paying replay costs. Reopening ordinary checkpoints preserves model predictions and controller state.

The initial neural dynamics parameters are untrained. The MSE gains therefore demonstrate offline acquisition from archived observations, not retention of an already pretrained skill. A separate [ordinary observed-replay control](../experiments/somna-direct-control-v1/report.json) samples sixteen canonical transitions per step without any hierarchy; it learns common-context motion better but can retain less rare-context accuracy than the fixed mixture. That is a tradeoff, not proof that ZHA is necessary. The control uses the already evaluated v4 cohort and is an additional diagnostic.

Full-bank dense attention and conventional exact top16 search use the identical features as strong retrieval controls. Dense audits are explicitly additional computation, not a free production confidence score. Exact search often approximates the full-bank teacher better, and fitted references have not consistently improved the pipeline. No ZHA speed advantage, reliable rare-memory guarantee or new algorithm is established. Keep all unfavorable rows.

V1 preserves the earlier page-only recovery adapter; v2 adds the dormant hierarchy; v3 adds the mixed-policy comparison. V1–v3 also preserve the old boundary-alias limitation. Source snapshots bind those historical results. They must not be presented as validation of corrected coordinates or the current live session.

The independent auditor imports no engine, simulator, encoder or router. It reconstructs scalar selected softmax, full-bank/nearest-neighbor teachers, dormant-leaf materialization, immutable source chains, functional MLP forward passes and every SGD update. It verifies final parameters, held-out predictions and reported errors. Semantic fault controls corrupt attention, gradients, sources, future-label fields, losses, evaluation, cold routing and work to ensure failures are detected.

## Run and operate

From `/Users/priyamghosh/Documents/GitHub/open-hierarchical-memory`:

```sh
uv sync --locked --extra research
uv run --locked --extra research python -m research.serve_somna --archive /tmp/somna-live.sqlite --port 8791
```

Open `http://127.0.0.1:8791/`. The server binds loopback, accepts bounded JSON requests and rejects cross-origin writes. GET state returns immutable published snapshots without waiting for the training lock. Sleep jobs are asynchronous; other writes return409 while a job is active. Progress consists of completed real updates, not a timer or replayed recording.

| Endpoint | Actual operation |
| --- | --- |
| GET `/api/state` | Current published memory/model/job state and metered work |
| POST `/api/query` | Partial `position`, boolean `mask`, optional `action`/`context`, optional separately charged `audit` |
| POST `/api/remember` | Validated observed `position, action, context, successor, evidence` tuple |
| POST `/api/collect` | Bounded new controlled observations, charged simulator calls |
| POST `/api/forget` | Advance logical ticks and retire decayed workspace entries |
| POST `/api/restore` | Explicitly reactivate an inspected current record |
| POST `/api/correct` | Append an observed correction and invalidate obsolete forecasts |
| POST `/api/sleep` | Actual uniform/priority/coverage/mixture neural updates and learned rollout |
| POST `/api/reset` | Preserve old archive, switch and durably resume a fresh session |

The supported prototype limit is2,048 originals, eight reference channels, a bounded workspace and16 rollout steps maximum. Additional records fail explicitly; originals are not silently dropped. The Linux CPU workflow uses the same lock and commands. GPU/reduced-precision backends, multi-controller serving and a learned visual encoder remain separate gates.

```sh
uv run --locked --extra research python scripts/verify.py --profile core
uv run --locked --extra research python -m research.run_somna_continuous --output experiments/somna-new --archives .cache/somna-new
uv run --locked --extra research python scripts/audit_somna_continuous.py --results experiments/somna-new
uv run --locked --extra research python -m research.run_somna_direct_control --source experiments/somna-new --output experiments/somna-direct-new
```

Fresh destinations are required. Results include raw compressed reads/training traces, initial/final parameters, imagined trajectories, held-out predictions, protocol and frozen source hashes. No model download, paid service or public deployment is part of the numerical experiment.

## Source grounding and next research gate

[ZHA](https://arxiv.org/html/2610.42112v2) supplies the hierarchical numerical construction; this is an independent episodic-memory adaptation of the no-positional-encoding subset. [Dyna](https://doi.org/10.1145/122344.122377), [prioritized sweeping](https://publications.ri.cmu.edu/prioritized-sweeping-reinforcement-learning-with-less-data-and-less-real-time) and [DreamerV3](https://danijar.com/project/dreamerv3/) establish substantial prior art for offline planning, prioritized updates and learned imagination. [Working Memory2.0](https://bpb-us-e1.wpmucdn.com/sites.mit.edu/dist/7/1739/files/2025/06/Miller-Lundqvist-Bastos-WM-20.pdf) motivates separating active content, traces and control; it does not validate this software as neuroscience replication.

The contribution presently supported is an integrated, inspectable and tested research substrate with explicit evidence and lifecycle boundaries. Novel algorithmic value remains a hypothesis. Next, establish a quality/cost frontier against stronger exact/ANN and replay baselines, calibrated model error, genuinely new tasks/dynamics and learned visual representations before scaling or public performance claims.
