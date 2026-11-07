# Working Memory 2.0 and a testable nonverbal dreaming direction

Research note: 7 November 2026. Status: source review and proposed experiments, not an implemented architecture, approved hardware purchase, biological replication or demonstrated novelty. The current ZHA numerical reference and lexical lifecycle diagnostic remain unchanged.

## Assessment

The user wants offline reasoning that can manipulate spatial, visual and symbolic representations, rather than merely ask a language model to rewrite notes. The technically actionable target is retrieval-conditioned latent imagination with durable, tested consolidation. An ordinary language model does not expose a documented human-like unconscious subsystem. In this design, dormant means stored but outside the currently active computational workspace.

## What the neuroscience contributes

Miller, Lundqvist and Bastos's 2018 Neuron Perspective proposes a hybrid account: brief informative activity, temporary synaptic changes between bursts, and executive gating. Its discussion of clearing working memory concerns short-term access, not erasing autobiographical memory. It is not an account of sleep or a proof that imagery causes insight. Figures 1-3 distinguish observations about burst dynamics from proposed control circuitry. The paper ends with unresolved questions about manipulation and long-term-memory loading.

Source: [Working Memory 2.0, author-hosted full paper](https://bpb-us-e1.wpmucdn.com/sites.mit.edu/dist/7/1739/files/2025/06/Miller-Lundqvist-Bastos-WM-20.pdf), DOI 10.1016/j.neuron.2018.09.023. Full main text and figures inspected. The original was retained only as a temporary local reading copy; no figure or full paper is redistributed in this repository.

Our computational hypotheses, rather than claims made by Miller:

- Separate durable episode storage, temporary associative state, and active execution. A record need not occupy the active workspace to remain recoverable.
- Compare on-demand reactivation and explicit refresh scheduling against continuous/full reads. Biological energetic arguments do not establish GPU efficiency: batching, gathers, metadata and maintenance must be measured.
- Separate a controller deciding when to read, suppress, refresh or clear from the representation carrying content. Test interference from distractors and changing goals.
- Test short-lived key/value associations or fast weights as a baseline. Do not equate these with durable model training or assert that an oscillatory schedule is necessary. Frequency constants from brains should not be hard-coded into a software scheduler without a causal benefit.

Existing computational precedent: [Ba et al., Using Fast Weights to Attend to the Recent Past, NeurIPS 2016](https://proceedings.neurips.cc/paper/2016/hash/9f44e956e3a2b7b5598c625fcc802c36-Abstract.html). Temporary associative weights are not a new contribution by themselves.

## What sleep and insight evidence supports

[Sanders et al. 2019](https://pmc.ncbi.nlm.nih.gov/articles/PMC6843748/) used sound cues associated with unsolved puzzles during sleep. The analysed sample of 57 solved 31.7% of cued versus 20.5% of uncued puzzles the next morning. This supports a targeted processing effect in that design; it does not identify a universal dream-visualisation mechanism or show that solutions were already fully computed before waking.

[Beijamini et al. 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC7965947/) found a sleep benefit in a different problem-solving task but no additional benefit from targeted cueing. Benefits depend on the task and procedure.

[Cai et al. 2009](https://pubmed.ncbi.nlm.nih.gov/19506253/) studied primed remote word associations and found an advantage after REM. This is relevant to recombination, but also shows why we should not assume sleep insight is exclusively visual or categorically superior to linguistic processing.

These studies motivate experiments, not a claim that implementing a replay loop reproduces human dreams. Subjective dreaming, neural replay, offline planning and parameter learning are distinct phenomena.

## Proposed computational system

1. **Perception and episodes.** Encode observations into spatial/object representations or learned visual latents. Store observed actions, outcomes, timestamps and evidence IDs. Maintain a canonical observed-data archive. Keep imagined transitions separate from observations.
2. **Working workspace.** Activate a small collection of relevant states and bindings. A controller regulates reads, refreshes and suppression. Suppression removes an item from present computation; deactivation, index retirement and permanent deletion are separate operations.
3. **ZHA-derived memory read.** Query numerical episode keys through the hierarchy. This is an episodic-memory adaptation, not automatically equivalent to the paper's transformer-KV experiments. Keep exact attention and conventional ANN comparators on the same representations. A nearest-neighbour recall result is not an attention-output guarantee.
4. **Offline seed selection.** Sample a mixture of unresolved situations, prediction errors, old rare experiences and uniform coverage. Do not let repeated retrieval alone define usefulness: confidently wrong retrieval can otherwise reinforce itself.
5. **Latent imagination.** A learned action-conditioned dynamics model proposes short sequences of states and outcomes. Branch on alternative actions, object roles and compatible recalled fragments. Start from valid observed states. Matching two pictures is insufficient evidence that they can be joined into a valid transition.
6. **Evaluation and consolidation.** Use calibrated model uncertainty and known constraints to reject poor imagined candidates. Imagined rewards remain predictions. Update one declared persistent component in the first experiment, such as a policy/value module; hold the encoder/dynamics representation fixed across the sleep comparison. If later training changes memory embeddings or routing references, rebuild/version affected summaries and charge that work. Do not quietly reuse incompatible vectors.
7. **Return to action.** Test the new checkpoint on fresh goals and layouts. Actual outcomes, not convincing dream animations, determine whether the update helped. A no-persistence ablation distinguishes useful online planning from durable consolidation.

An imagined sequence has evidence type `imagined`, model/checkpoint identity, contributing episode IDs and uncertainty diagnostics. It does not become an observed fact merely because it has high predicted reward. In a controlled task, a simulator can verify a plan, but simulator calls must be counted and that condition cannot be described as receiving no new environment information. The strict offline comparison makes no new environment calls during sleep.

## Existing engineering substrate

[DreamerV3](https://danijar.com/project/dreamerv3/) learns an environment model and improves behaviour through imagined scenarios. Its world-model approach is a strong starting point and baseline for nonverbal imagination. It does not establish equivalence to sleep or conscious dreaming. We should reuse an audited existing substrate rather than pretend that latent rollout generation is itself new.

Language can still specify a goal or explain an outcome. The internal task-solving trajectory can operate on states, object relations and actions. Render decoded predicted states for inspection; label them as model predictions. The decoder is a view of an internal trajectory, not proof of a subjective visual experience. A latent vector is not inherently a spatial or symbolic representation; the representation and training objective must support the claimed operations.

## First discriminating experiment

Use a partially observed visual manipulation/navigation task with delayed cues and reusable object affordances. For example, experiences establish how an object moves or supports another object; a later layout requires using that affordance in a different combination. Add distractors, changed rules, old rare clues and unseen layouts. Store no target answer or privileged future state in replay.

Collect wake experience once, freeze the checkpoint and branch it. Every experimental condition receives the same episodes and an explicitly charged offline compute budget. The first run should vary only the offline replay/imagination strategy with fixed perception and dynamics. Test workspace scheduling and retrieval replacement as separate follow-up axes, not a simultaneous architecture rewrite.

Required conditions:

- No offline update.
- Equal-compute additional ordinary planning or replay.
- Uniform replay using the same world model and update objective.
- Retrieval-conditioned latent imagination with the same total budget.
- A no-durable-update condition: keep the search result temporarily, then reset it before evaluation.

Then independently compare ZHA-derived retrieval with exact attention and Faiss/other strong numerical search on the same bank, and gated workspace with a simple cache/recurrent baseline. Keep a symbolic planner as a diagnostic ceiling where task rules permit it. A symbolic solver succeeding immediately prevents us from selling ordinary graph search as a newly discovered reasoning capability.

Measure task success on unseen layouts, transfer of a newly useful affordance, old-skill retention, rare-clue recovery, source-confabulation rate, transition-prediction error, active and total storage, index rebuild cost, query latency and total wake-plus-offline compute. Report uncertainty across independent world seeds, not permutations of an otherwise identical fixture. Keep task/test splits sealed and do not choose a checkpoint after reading final evaluation outcomes.

A visual-versus-language comparison needs matched observation information and a compute/quality frontier. More updates, privileged simulator access, different encoder quality or more data can explain a win without any benefit from the representation. The experiment may find no advantage; preserve that outcome.

## Proposed next decision

The synthesis worth testing is whether structured dormant experience plus budgeted nonverbal rehearsal improves compositional transfer and retention. It is a stronger question than whether replay can improve a toy cache hit rate, but not yet an established novel algorithm. Fast weights, generative replay, world-model imagination and hierarchical search all have substantial prior art.

First establish an audited world-model baseline and the offline fork experiment. Keep the existing numerical reference and lifecycle diagnostic as separate controls. Dedicated Linux/GPU execution is available as a planning assumption; hardware/model sizes require a resource estimate. Do not silently make laptop availability the scientific limit, but do not present unrun GPU behavior as validated. No current code implements the proposed visual imagination or consolidation loop.
