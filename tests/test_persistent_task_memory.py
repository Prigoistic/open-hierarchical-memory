"""State/behavior tests for explicit forgetting, recovery and graph access."""

import json
import sqlite3
from dataclasses import replace

import pytest
import torch

from open_hierarchical_memory import QueryBudget
from research.minigrid_benchmark import Fact, ObservationPlanner, ReadContext, query_vectors
from research.persistent_task_memory import PersistentTaskReader
from research.task_references import RouterCheckpoint, TaskSample, fit_task_references
from research.task_store import TaskStore, WorkspaceConfig


@pytest.fixture(autouse=True)
def single_thread():
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(old)


def cell(x=0, y=0, obj=1, color=0, state=0, step=0):
    return Fact(0, x, y, obj, color, state, step, step)


def context(raw, mission="pick up the red key", position=(0, 0)):
    return ReadContext(position, 0, mission, None, tuple(raw), raw[0].observed_step)


def read(reader, raw):
    c = context(raw)
    reader.observe(raw)
    return reader.select_with_context(query_vectors(c.position, c.mission), c)


def prepare(reader):
    records = reader.observe([cell(i, 0, 5 if i == 3 else 1) for i in range(4)])
    reader.observe([cell(10 + i, 10, step=1) for i in range(8)])
    reader.fade(128)
    return records[-1].id


def test_originals_are_immutable_and_age_is_reversible_without_usage_credit(tmp_path):
    store = TaskStore(tmp_path / "m.sqlite", config=WorkspaceConfig(capacity=8, recovery_limit=4))
    reader = PersistentTaskReader(store, "world-a/reset0/frame0", backend="none")
    records = reader.observe([cell(), cell(1, 0, 5)])
    before = reader.archive()
    assert set(reader.fade(128)) == {f.id for f in records}
    assert not store.heads(reader.context, active=True, tag="active_payload_rows")
    assert reader.archive() == before
    assert store.db.execute("SELECT sum(hits) FROM heads").fetchone()[0] == 0
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        store.db.execute("DELETE FROM records")
    store.db.rollback()
    store.promote(reader.context, [records[1].id])
    assert [f.id for f in store.heads(reader.context, active=True, tag="active_payload_rows")] == [
        records[1].id
    ]
    store.close()


@pytest.mark.parametrize("backend", ["exact", "zha"])
def test_delayed_clue_recovery_returns_real_key_with_complete_current_support(tmp_path, backend):
    store = TaskStore(tmp_path / "m.sqlite", config=WorkspaceConfig(capacity=8, recovery_limit=4))
    reader = PersistentTaskReader(store, "world-a/reset0/frame0", backend=backend, threshold=1.0)
    clue = prepare(reader)
    selected, routes, receipt, coverage = read(reader, [cell(i, 0, step=2) for i in range(3)])
    assert clue in receipt["recovered_ids"]
    assert clue in {f.id for f in selected}
    assert set(receipt["returned_ids"]) <= set(receipt["available_ids"])
    assert len(receipt["available_ids"]) <= 8
    assert receipt["graph_source"] == "active_and_explicitly_recovered_only"
    assert coverage.contains((3, 0)) and not coverage.contains((4, 0))
    assert store.work["recovery_payload_rows"] <= 4
    assert receipt["work_delta"]["support_graph_build_nodes"] == len(receipt["available_ids"])
    if backend == "zha":
        assert routes and all(clue in r["index_fact_ids"] for r in routes)
        assert any(clue in r["selected_fact_ids"] for r in routes)
    else:
        assert not routes and reader._index is None
    assert store.db.execute("SELECT hits FROM heads WHERE id=?", (clue,)).fetchone()[0] == 1
    store.close()


def test_no_recovery_means_cold_clue_cannot_enter_graph_or_planner(tmp_path, monkeypatch):
    store = TaskStore(tmp_path / "m.sqlite", config=WorkspaceConfig(capacity=8, recovery_limit=4))
    reader = PersistentTaskReader(store, "world-a/reset0/frame0", backend="none")
    clue = prepare(reader)
    original = store.heads

    def restricted(ctx, *, active=False, tag="index_payload_rows"):
        assert active, "unexpected full archive materialisation in no-recovery read"
        return original(ctx, active=active, tag=tag)

    monkeypatch.setattr(store, "heads", restricted)
    selected, routes, receipt, _ = read(reader, [cell(i, 0, step=2) for i in range(3)])
    assert clue not in receipt["available_ids"]
    assert clue not in {f.id for f in selected}
    assert receipt["recovery_status"] == "disabled" and not routes
    assert store.work["index_payload_rows"] == 0 and store.work["recovery_payload_rows"] == 0
    store.close()


def test_warm_archive_queries_do_not_rematerialize_all_payloads(tmp_path):
    store = TaskStore(tmp_path / "m.sqlite", config=WorkspaceConfig(capacity=8, recovery_limit=4))
    reader = PersistentTaskReader(store, "same-world", threshold=1.0)
    prepare(reader)
    raw = [cell(i, 0, step=2) for i in range(3)]
    read(reader, raw)
    builds = reader.work["index_builds"]
    rows = store.work["index_payload_rows"]
    reader.select_with_context(query_vectors((0, 0), context(raw).mission), context(raw))
    assert reader.work["index_builds"] == builds
    assert store.work["index_payload_rows"] == rows
    store.close()


def test_reopen_preserves_active_usage_clock_and_exact_retrieval(tmp_path):
    path = tmp_path / "m.sqlite"
    config = WorkspaceConfig(capacity=8, recovery_limit=4)
    store = TaskStore(path, config=config)
    reader = PersistentTaskReader(store, "same-world", backend="exact")
    prepare(reader)
    raw = [cell(i, 0, step=2) for i in range(3)]
    a, _, _, _ = read(reader, raw)
    state = store.state(reader.context)
    metadata = [
        tuple(r) for r in store.db.execute("SELECT id,active,hits,last_use FROM heads ORDER BY id")
    ]
    originals = reader.archive()
    store.close()
    store = TaskStore(path, config=config)
    reader = PersistentTaskReader(store, "same-world", backend="exact")
    assert store.state(reader.context) == state
    assert [
        tuple(r) for r in store.db.execute("SELECT id,active,hits,last_use FROM heads ORDER BY id")
    ] == metadata
    assert reader.archive() == originals
    b, _, _, _ = reader.select_with_context(
        query_vectors((0, 0), context(raw).mission), context(raw)
    )
    assert [f.id for f in a] == [f.id for f in b]
    store.close()


def test_world_contexts_never_share_object_payloads_or_coverage(tmp_path):
    store = TaskStore(tmp_path / "m.sqlite", config=WorkspaceConfig(capacity=8, recovery_limit=4))
    a = PersistentTaskReader(store, "world-a/reset0", backend="exact")
    foreign = a.observe([cell(1, 0, 5)])[0].id
    b = PersistentTaskReader(store, "world-b/reset0", backend="exact")
    _, _, receipt, coverage = read(b, [cell()])
    assert foreign not in receipt["available_ids"] + receipt["recovered_ids"]
    assert not coverage.contains((1, 0))
    with pytest.raises(ValueError, match="foreign"):
        store.fetch(b.context, [foreign])
    store.close()


def test_correction_excludes_old_version_from_retrieval_and_invalidates_index(tmp_path):
    store = TaskStore(tmp_path / "m.sqlite", config=WorkspaceConfig(capacity=8, recovery_limit=4))
    reader = PersistentTaskReader(store, "world", threshold=1)
    first = reader.observe([cell(), cell(1, 0, 5)])[1]
    reader._build_archive_index(store.state("world")["version"])
    builds = reader.work["index_builds"]
    changed = [cell(step=1), cell(1, 0, 5, color=1, step=1)]
    current = reader.observe(changed)[0]
    assert reader._index is None and reader._index_version == -1
    reader._build_archive_index(store.state("world")["version"])
    reader.select_with_context(query_vectors((0, 0), context(changed).mission), context(changed))
    assert reader.work["index_builds"] == builds + 1
    assert (
        current.previous == first.id and current.id in reader._ids and first.id not in reader._ids
    )
    with pytest.raises(ValueError, match="superseded"):
        store.fetch("world", [first.id])
    assert len(reader.archive()) == 3
    store.close()


def test_invalid_or_future_reads_do_not_change_persistent_state(tmp_path):
    store = TaskStore(tmp_path / "m.sqlite")
    reader = PersistentTaskReader(store, "world")
    raw = [cell()]
    reader.observe(raw)
    state = store.state("world")
    work = reader.costs.copy()
    with pytest.raises(ValueError):
        reader.select_with_context(torch.zeros(2, 30), context(raw))
    with pytest.raises(ValueError, match="prefix"):
        reader.select_with_context(
            query_vectors((0, 0), context(raw).mission), context([cell(step=1)])
        )
    assert store.state("world") == state and reader.costs == work
    reader.observe([cell(step=2)])
    with pytest.raises(ValueError, match="rewind"):
        reader.observe([cell(step=1)])
    store.close()


def test_batch_record_limit_failure_rolls_back_every_observation_and_metadata(tmp_path):
    store = TaskStore(
        tmp_path / "m.sqlite", config=WorkspaceConfig(capacity=8, recovery_limit=4, max_records=2)
    )
    reader = PersistentTaskReader(store, "world")
    reader.observe([cell()])
    before = store.state("world")
    originals = reader.archive()
    with pytest.raises(ValueError, match="limit"):
        reader.observe([cell(1, 0, step=1), cell(2, 0, step=1)])
    assert reader.archive() == originals and store.count == 1 and store.state("world") == before
    assert reader.observe([cell(3, 0, step=1)])[0].id == 2
    store.close()


def test_single_writer_and_mismatched_checkpoint_cannot_open_archive(tmp_path):
    path = tmp_path / "m.sqlite"
    store = TaskStore(path)
    with pytest.raises(ValueError, match="writer"):
        TaskStore(path)
    store.close()
    fixed = RouterCheckpoint.fixed()
    values = [list(row) for row in fixed.values]
    values[0][0] += 1
    other = RouterCheckpoint(tuple(tuple(row) for row in values))
    with pytest.raises(ValueError, match="identity"):
        TaskStore(path, router=other)
    store = TaskStore(path)
    store.close()


def test_recovery_budget_failure_is_visible_and_never_turns_into_exact_fallback(tmp_path):
    store = TaskStore(tmp_path / "m.sqlite", config=WorkspaceConfig(capacity=8, recovery_limit=4))
    reader = PersistentTaskReader(
        store,
        "world",
        threshold=1,
        budget=QueryBudget(max_scored_nodes=1, max_attention_pairs=1, max_trace_nodes=1),
    )
    prepare(reader)
    _, routes, receipt, _ = read(reader, [cell(step=2)])
    assert receipt["recovery_status"] == "budget_exhausted"
    assert routes[0]["status"] == "budget_exhausted"
    assert receipt["recovered_ids"] == [] and store.work["recovery_payload_rows"] == 0
    assert reader.work["archive_rerank_pairs"] == 0
    store.close()


def sample(label, seed):
    rng = torch.Generator().manual_seed(seed)
    return TaskSample(
        label,
        3,
        torch.randn(2, 30, dtype=torch.float64, generator=rng),
        torch.cat(
            (
                torch.zeros(1, 30, dtype=torch.float64),
                torch.randn(31, 30, dtype=torch.float64, generator=rng),
            )
        ),
    )


def test_fitted_references_select_only_on_validation_and_own_their_values(tmp_path):
    train = [sample("train-a", 0), sample("train-b", 1)]
    val = [sample("validation", 2)]
    original = [s.queries.clone() for s in train]
    checkpoint, history = fit_task_references(train, val, steps=10)
    assert checkpoint.kind == "fitted"
    assert min(r["validation_kl"] for r in history) <= history[0]["validation_kl"]
    assert checkpoint.selected_step in [r["step"] for r in history]
    for source, before in zip(train, original, strict=True):
        assert source.queries.grad is None
        torch.testing.assert_close(source.queries, before, rtol=0, atol=0)
    t = checkpoint.tensor()
    t.zero_()
    assert bool(checkpoint.tensor().any())
    path = tmp_path / "refs.json"
    checkpoint.save(path)
    assert RouterCheckpoint.load(path) == checkpoint
    with pytest.raises(FileExistsError):
        checkpoint.save(path)
    with pytest.raises(ValueError, match="evaluation"):
        checkpoint.require_evaluation_context("train-a")
    checkpoint.require_evaluation_context("held-out")
    value = json.loads(path.read_text())
    value["references"][0][0] += 1
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="checksum"):
        RouterCheckpoint.load(path)


def test_fitting_rejects_split_overlap_and_future_source_facts():
    with pytest.raises(ValueError, match="overlap"):
        fit_task_references([sample("same", 0)], [sample("same", 1)], steps=1)
    with pytest.raises(ValueError, match="observed heads"):
        TaskSample.observed(
            "ctx", 0, [replace(cell(step=1), id=1)], torch.zeros(2, 30, dtype=torch.float64)
        )


def test_public_support_boundary_rejects_foreign_seed_and_future_fact(tmp_path):
    store = TaskStore(tmp_path / "m.sqlite")
    reader = PersistentTaskReader(store, "ctx")
    raw = [cell()]
    observed = reader.observe(raw)
    c = context(raw)
    with pytest.raises(ValueError, match="support"):
        reader.support.pack_available_support(observed, [replace(observed[0], id=999)], c)
    with pytest.raises(ValueError, match="support"):
        reader.support.pack_available_support([replace(observed[0], observed_step=1)], observed, c)
    store.close()


def test_existing_planner_accepts_persistent_reader_in_real_official_environment(tmp_path):
    from research.run_minigrid_benchmark import environment

    store = TaskStore(tmp_path / "m.sqlite")
    reader = PersistentTaskReader(
        store, "MiniGrid-MemoryS17Random-v0/seed0/reset0", backend="exact"
    )
    actor = ObservationPlanner("none", injected_reader=reader)
    env = environment("MiniGrid-MemoryS17Random-v0")
    obs, _ = env.reset(seed=0)
    try:
        for _ in range(4):
            action, decision, _ = actor.act(obs)
            receipt = decision["dependency"]
            assert set(decision["memory_ids"]) <= set(receipt["available_ids"])
            obs, _, done, truncated, _ = env.step(action)
            if done or truncated:
                break
    finally:
        env.close()
        store.close()


def test_configuration_is_readonly_and_duplicate_fit_samples_are_rejected(tmp_path):
    store = TaskStore(tmp_path / "m.sqlite")
    with pytest.raises(AttributeError):
        store.router = RouterCheckpoint.fixed()
    with pytest.raises(AttributeError):
        store.config = WorkspaceConfig(capacity=8, recovery_limit=4)
    store.close()
    one = sample("a", 42)
    with pytest.raises(ValueError, match="identical numerical"):
        fit_task_references([one], [replace(one, context="b")], steps=1)


def test_support_escape_is_caught_before_use_or_result_publication(tmp_path, monkeypatch):
    store = TaskStore(tmp_path / "m.sqlite")
    reader = PersistentTaskReader(store, "ctx", backend="none")
    raw = [cell()]
    reader.observe(raw)
    monkeypatch.setattr(
        reader.support,
        "pack_available_support",
        lambda *args, **kwargs: ([replace(cell(9, 9), id=999)], []),
    )
    with pytest.raises(ValueError, match="escaped"):
        reader.select_with_context(query_vectors((0, 0), context(raw).mission), context(raw))
    assert store.db.execute("SELECT sum(hits) FROM heads").fetchone()[0] == 0
    store.close()


def test_delayed_clue_runner_produces_real_recovery_and_correction_evidence(tmp_path):
    from research.run_persistent_tasks import delayed_clue

    for backend in ("none", "exact", "zha"):
        result = delayed_clue(tmp_path / f"{backend}.sqlite", RouterCheckpoint.fixed(), backend)
        assert result["restored_state_equal"] and result["original_prefix_unchanged"]
        assert result["superseded_not_returned"]
        if backend == "none":
            assert not result["clue_recovered"]
        else:
            assert result["clue_recovered"] and result["clue_returned_with_support"]


def test_independent_auditor_rejects_invented_sources_and_numerical_route_scores(tmp_path):
    import copy

    from research.run_persistent_tasks import persistent_episode
    from scripts.audit_persistent_tasks import audit_episode

    checkpoint = RouterCheckpoint.fixed()
    e = persistent_episode(
        tmp_path / "run.sqlite",
        "MiniGrid-DoorKey-16x16-v0",
        9001,
        checkpoint,
        "zha",
        6,
        recovery_policy="always",
    )
    assert e["result"]["error"] is None
    audit_episode(e, {**checkpoint.payload(), "sha256": checkpoint.sha256}, 0.8)
    broken = copy.deepcopy(e)
    broken["trajectory"][0]["decision"]["dependency"]["available_ids"].append(999)
    with pytest.raises(AssertionError):
        audit_episode(
            broken, {**checkpoint.payload(), "sha256": checkpoint.sha256}, 0.8, official=False
        )
    broken = copy.deepcopy(e)
    route = next(
        r
        for row in broken["trajectory"]
        for r in row["decision"]["route"]
        if r.get("steps") and len(r["index_fact_ids"]) >= 16
    )
    route["steps"][0]["scores"][0] += 0.1
    with pytest.raises(AssertionError, match="score"):
        audit_episode(
            broken, {**checkpoint.payload(), "sha256": checkpoint.sha256}, 0.8, official=False
        )


def test_recovery_gate_survives_restart_and_does_not_probe_while_making_progress(tmp_path):
    path = tmp_path / "gated.sqlite"
    config = WorkspaceConfig(capacity=8, recovery_limit=4)
    store = TaskStore(path, config=config)
    reader = PersistentTaskReader(store, "ctx", backend="exact")
    prepare(reader)
    raw = [cell(i, 0, step=2) for i in range(3)]
    _, _, first, _ = read(reader, raw)
    assert first["recovery_reason"] == "new_mission"
    state = store.recovery_control("ctx")
    store.close()
    store = TaskStore(path, config=config)
    reader = PersistentTaskReader(store, "ctx", backend="exact")
    assert store.recovery_control("ctx") == state
    q = query_vectors((0, 0), context(raw).mission)
    for _ in range(1, 8):
        _, routes, r, _ = reader.select_with_context(q, context(raw))
        assert r["recovery_reason"] == "active_progress" and not routes and not r["recovered_ids"]
    _, _, r, _ = reader.select_with_context(q, context(raw))
    assert r["recovery_reason"] == "exploration_stall"
    store.close()


def test_known_dormant_neighbors_do_not_become_false_exploration_frontiers(tmp_path):
    from research.minigrid_benchmark import KnownCoverage

    store = TaskStore(tmp_path / "m.sqlite")
    reader = PersistentTaskReader(store, "ctx", backend="none")
    raw = [cell()]
    available = reader.observe(raw)
    c = ReadContext((0, 0), 0, "go to the goal", None, tuple(raw), 0)
    known = KnownCoverage(bytes([255]) * 512, 1, "0" * 64)
    _, bundles = reader.support.pack_available_support(
        available, available, c, known_coverage=known
    )
    assert not bundles
    _, bundles = reader.support.pack_available_support(
        available, available, c, known_coverage=KnownCoverage(bytes(512), 1, "0" * 64)
    )
    assert any(b["kind"] == "true_observed_frontier" for b in bundles)
    store.close()


def test_corrupt_recovery_controller_is_rejected_on_reopen(tmp_path):
    path = tmp_path / "m.sqlite"
    store = TaskStore(path)
    reader = PersistentTaskReader(store, "ctx")
    read(reader, [cell()])
    with store.db:
        store.db.execute("UPDATE meta SET value='{}' WHERE key='recovery/ctx'")
    store.close()
    with pytest.raises(ValueError, match="controller checksum"):
        TaskStore(path)
