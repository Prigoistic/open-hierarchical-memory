"""Source, capacity, correction and optimization checks for compact recovery."""

import pytest
import torch

from open_hierarchical_memory import QueryBudget
from research.minigrid_benchmark import Fact, ReadContext, query_vectors
from research.task_memory.support import SupportTaskReader
from research.task_store import TaskStore, WorkspaceConfig


@pytest.fixture(autouse=True)
def single_thread():
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(old)


def cell(x=0, y=0, obj=1, step=0):
    return Fact(0, x, y, obj, 0, 0, step, step)


def setup_reader(tmp_path, **kwargs):
    store = TaskStore(tmp_path / "m.sqlite", config=WorkspaceConfig(capacity=8, recovery_limit=4))
    return store, SupportTaskReader(store, "world", **kwargs)


def read(reader, raw, mission="pick up the red key"):
    reader.observe(raw)
    c = ReadContext((0, 0), 0, mission, None, tuple(raw), raw[0].observed_step)
    return reader.select_with_context(query_vectors(c.position, c.mission), c)


def prepare(reader):
    originals = reader.observe([cell(i, 0, 5 if i == 3 else 1) for i in range(4)])
    reader.observe([cell(-1, 0, 2), cell(0, 1, 2), cell(0, -1, 2)])
    reader.observe([cell(10 + i, 10, step=1) for i in range(8)])
    reader.fade(128)
    return originals


def test_connector_recovers_complete_observed_path_under_same_caps(tmp_path):
    store, r = setup_reader(tmp_path, backend="none")
    originals = prepare(r)
    before = r.archive()
    selected, routes, receipt, _ = read(r, [cell(step=2)])
    assert {f.id for f in originals[1:]} <= {f.id for f in selected}
    assert receipt["connector"]["attempted"] and receipt["connector"]["status"] == "complete"
    assert len(receipt["available_ids"]) <= 8 and len(receipt["recovered_ids"]) <= 4
    assert set(receipt["returned_ids"]) <= set(receipt["available_ids"])
    assert receipt["connector"]["source_ids"] and not routes
    assert r.archive() == before
    store.close()


def test_compact_only_does_not_scan_cold_graph(tmp_path, monkeypatch):
    store, r = setup_reader(tmp_path, backend="none", support_mode="compact")
    prepare(r)
    real = store.heads

    def scoped(ctx, *, active=False, tag="index_payload_rows"):
        assert active
        return real(ctx, active=active, tag=tag)

    monkeypatch.setattr(store, "heads", scoped)
    _, _, receipt, _ = read(r, [cell(step=2)])
    assert not receipt["connector"]["attempted"] and not receipt["recovered_ids"]
    assert r.work["connector_head_scans"] == 0
    store.close()


def test_cache_owns_immutable_heads_and_invalidates_after_correction(tmp_path):
    store, r = setup_reader(tmp_path, backend="none")
    old = prepare(r)[-1]
    version = store.state("world")["version"]
    a = r._heads(version)
    a.clear()
    assert r._heads(version) and r.work["connector_cache_hits"] == 1
    scans = r.work["connector_head_scans"]
    r.observe([cell(3, 0, 2, step=2)])
    b = r._heads(store.state("world")["version"])
    assert old.id not in {f.id for f in b} and r.work["connector_head_scans"] > scans
    with pytest.raises(ValueError, match="superseded"):
        store.fetch("world", [old.id])
    store.close()


def test_budget_failure_never_triggers_hidden_connector_fallback(tmp_path):
    store, r = setup_reader(
        tmp_path,
        backend="zha",
        budget=QueryBudget(max_scored_nodes=1, max_attention_pairs=1, max_trace_nodes=1),
    )
    prepare(r)
    _, routes, receipt, _ = read(r, [cell(step=2)])
    assert (
        receipt["recovery_status"] == "budget_exhausted" and not receipt["connector"]["attempted"]
    )
    assert not receipt["recovered_ids"] and routes[0]["status"] == "budget_exhausted"
    store.close()


def test_foreign_or_future_context_is_rejected_before_mutation(tmp_path):
    store, r = setup_reader(tmp_path, backend="none")
    raw = [cell()]
    r.observe(raw)
    before = store.state("world")
    c = ReadContext((0, 0), 0, "pick up the red key", None, tuple([cell(step=1)]), 1)
    with pytest.raises(ValueError, match="prefix"):
        r.select_with_context(query_vectors((0, 0), c.mission), c)
    assert before == store.state("world")
    store.close()


def test_support_that_cannot_fit_is_explicitly_rejected(tmp_path):
    store, r = setup_reader(tmp_path, backend="none")
    r.observe([cell(i, 0, 5 if i == 7 else 1) for i in range(8)])
    r.observe([cell(-1, 0, 2), cell(0, 1, 2), cell(0, -1, 2)])
    r.observe([cell(10 + i, 10, step=1) for i in range(8)])
    r.fade(128)
    _, _, receipt, _ = read(r, [cell(step=2)])
    assert 8 not in receipt["returned_ids"] and any(
        b["status"] == "overbudget" for b in receipt["bundles"]
    )
    assert len(receipt["recovered_ids"]) <= 4
    store.close()


def test_corrected_obstacle_cannot_be_used_as_old_path_support(tmp_path):
    store, r = setup_reader(tmp_path, backend="none")
    originals = prepare(r)
    r.observe([cell(1, 0, 2, step=2)])
    r.fade(128)
    selected, _, receipt, _ = read(r, [cell(step=3)])
    assert originals[1].id not in receipt["available_ids"] + receipt["connector"]["source_ids"]
    assert not any(f.object == 5 for f in selected)
    store.close()


def test_cache_toggle_has_identical_actions_sources_and_controller_state(tmp_path):
    from research.run_persistent_tasks import persistent_episode
    from research.task_references import RouterCheckpoint

    episodes = []
    for cached in (False, True):
        e = persistent_episode(
            tmp_path / f"{cached}.sqlite",
            "MiniGrid-DoorKey-16x16-v0",
            19002,
            RouterCheckpoint.fixed(),
            "none",
            80,
            workspace=WorkspaceConfig(capacity=64),
            reader_factory=lambda s, c, cached=cached: SupportTaskReader(
                s, c, backend="none", cache_heads=cached
            ),
        )
        assert e["result"]["error"] is None
        episodes.append(e)

    def behavior(e):
        return [
            (r["action"], r["decision"]["memory_ids"], r["decision"]["dependency"]["available_ids"])
            for r in e["trajectory"]
        ]

    assert behavior(episodes[0]) == behavior(episodes[1])
    assert episodes[0]["controller_state"] == episodes[1]["controller_state"]
    assert episodes[0]["result"] == episodes[1]["result"]


def test_independent_audit_rejects_fabricated_connectors_and_path_edges(tmp_path):
    import copy

    from research.task_memory.run_study import layout_identity, run
    from research.task_references import RouterCheckpoint
    from scripts.audit_task_support import audit_episode

    cp = RouterCheckpoint.fixed()
    e = run(
        "connected_graph",
        tmp_path / "audit.sqlite",
        "MiniGrid-DoorKey-16x16-v0",
        19002,
        cp,
        cap=100,
    )
    e["evaluator_layout_identity"] = layout_identity(e["environment_id"], e["seed"])
    payload = {**cp.payload(), "sha256": cp.sha256}
    assert audit_episode(e, payload)["connector_reads"] > 0
    bad = copy.deepcopy(e)
    row = next(
        t for t in bad["trajectory"] if t["decision"]["dependency"]["connector"]["attempted"]
    )
    row["decision"]["dependency"]["connector"]["source_ids"].append(999999)
    with pytest.raises(AssertionError, match="prefix"):
        audit_episode(bad, payload, official=False)
    bad = copy.deepcopy(e)
    bundle = next(
        b
        for t in bad["trajectory"]
        for b in t["decision"]["dependency"]["bundles"]
        if b["status"] == "complete" and b["support_edges"]
    )
    bundle["support_edges"][0][1] = bundle["support_edges"][0][0]
    with pytest.raises(AssertionError, match="support edges"):
        audit_episode(bad, payload, official=False)


def test_diagnosis_replays_recorded_actions_and_detects_missing_active_support(tmp_path):
    import copy

    from research.run_persistent_tasks import persistent_episode
    from research.task_memory.diagnosis import inspect_episode
    from research.task_references import RouterCheckpoint

    e = persistent_episode(
        tmp_path / "diagnosis.sqlite",
        "MiniGrid-DoorKey-16x16-v0",
        19002,
        RouterCheckpoint.fixed(),
        "zha",
        40,
        workspace=WorkspaceConfig(capacity=64),
    )
    result = inspect_episode(e)
    assert result["counts"]["active_support_gap"] > 0
    bad = copy.deepcopy(e)
    bad["trajectory"][0]["action"] = 6
    with pytest.raises(ValueError, match="planner replay"):
        inspect_episode(bad)
