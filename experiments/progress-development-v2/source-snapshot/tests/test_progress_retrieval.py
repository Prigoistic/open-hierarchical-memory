"""Progress evidence, bounded retries, corrections and actual route metadata."""

from dataclasses import replace

import pytest
import torch

from research.minigrid_benchmark import Fact, ReadContext, query_vectors
from research.progress_retrieval import HISTORY_LIMIT, ProgressReader


@pytest.fixture(autouse=True)
def one_thread():
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(old)


def cell(x=0, y=0, kind=1, state=0, step=0):
    return Fact(0, x, y, kind, 0, state, step, step)


def read(reader, step, raw=None, position=(0, 0)):
    current = raw if raw is not None else [cell(step=step)]
    reader.observe(current)
    context = ReadContext(position, 0, "go to the goal", None, tuple(current), step)
    q = query_vectors(position, context.mission)
    return reader.select_with_context(q, context)


def test_stages_are_bounded_observable_and_graph_is_explicit():
    reader = ProgressReader("progress_zha")
    snapshots = {}
    for step in range(25):
        selected, routes, receipt, _ = read(reader, step)
        snapshots[step] = receipt["repair"]
        assert len(selected) <= 96 and len(receipt["repair"]["history"]) <= HISTORY_LIMIT
        assert receipt["repair"]["work_delta"]["history_pose_checks"] == min(step + 1, 24)
        if step == 24:
            assert routes == [] and receipt["seed_reader"] == "full"
    assert [snapshots[i]["stage"] for i in (0, 7, 8, 15, 16, 23, 24)] == [0, 0, 1, 1, 2, 2, 3]
    assert len(snapshots[8]["cues"]) == 6
    assert snapshots[16]["candidate_budget"] == 192
    assert snapshots[24]["fallback_active"]
    assert snapshots[24]["executed_source"] == "full_observed_graph"
    assert snapshots[24]["trigger"] == "repeated_stall_after_widening"
    assert reader.costs["repair_graph_fallback_reads"] == 1
    assert reader.costs["repair_payload_novelty_checks"] == 1


def test_cue_only_control_never_calls_graph_even_when_stalled():
    reader = ProgressReader("cues_exact")
    for step in range(60):
        _, _, receipt, _ = read(reader, step)
    assert receipt["repair"]["stage"] == 2
    assert not receipt["repair"]["fallback_allowed"]
    assert not receipt["repair"]["fallback_active"]
    assert reader.costs["repair_graph_fallback_reads"] == 0
    assert receipt["seed_reader"] == "exact"


def test_repeated_old_door_state_is_not_new_information_but_heads_are_current():
    reader = ProgressReader("progress_zha")
    for step, state in enumerate((2, 2, 0, 2, 0)):
        raw = [cell(step=step), cell(1, 0, 4, state, step)]
        _, routes, receipt, _ = read(reader, step, raw)
        if step in (0, 2):
            assert receipt["repair"]["no_information_reads"] == 0
        if step == 4:
            assert receipt["repair"]["no_information_reads"] == 2
            head = max(f["id"] for f in reader.archive() if f["object"] == 4)
            assert head in receipt["repair"]["source_original_ids"]
            assert all(head in route["index_fact_ids"] for route in routes)


def test_new_information_exits_graph_and_invalidates_index_correctly():
    reader = ProgressReader("progress_zha")
    for step in range(25):
        read(reader, step)
    assert reader._fallback_active
    _, routes, receipt, _ = read(reader, 25, [cell(step=25), cell(1, 0, 8, step=25)])
    assert receipt["repair"]["stage"] == 0 and not receipt["repair"]["fallback_active"]
    assert receipt["repair"]["novel_observed_ids"]
    assert routes and all(route["used"] for route in routes)
    assert receipt["seed_reader"] == "zha_adaptive"
    assert all(route["logical_key_count"] == 3 for route in routes)


def test_route_layout_is_true_current_index_order_and_owned():
    reader = ProgressReader("progress_zha")
    all_raw = [cell(i % 10, i // 10) for i in range(100)]
    for start in range(0, 100, 49):
        reader.observe(all_raw[start : start + 49])
    _, routes, receipt, _ = read(reader, 0)
    assert routes and reader.source._index is not None
    info = reader.source._index.info
    expected = [
        {
            "level": span.node_id.level,
            "index": span.node_id.index,
            "start": span.start,
            "stop": span.stop,
        }
        for span in info.spans
    ]
    assert routes[0]["node_spans"] == expected
    assert routes[0]["index_fact_ids"] == reader.source._index_ids
    for route in routes:
        assert [
            route["index_fact_ids"][i - 1] for i in route["selected_logical_ids"] if i
        ] == route["selected_fact_ids"]
        assert route["snapshot_id"] == info.snapshot_id
    routes[0]["index_fact_ids"].clear()
    routes[0]["node_spans"].clear()
    _, routes2, _, _ = read(reader, 1)
    assert routes2[0]["index_fact_ids"] and routes2[0]["node_spans"] == expected
    assert receipt["repair"]["work_delta"]["trace_node_spans"] > 0


def test_invalid_queries_or_future_context_do_not_advance_progress():
    reader = ProgressReader("progress_zha")
    raw = [cell()]
    reader.observe(raw)
    context = ReadContext((0, 0), 0, "go to the goal", None, tuple(raw), 0)
    before = (reader._no_information, list(reader._history), reader._repair_work.copy())
    with pytest.raises(ValueError):
        reader.select_with_context(torch.ones(2, 30), context)
    with pytest.raises(ValueError):
        reader.select_with_context(
            query_vectors((0, 0), "go to the goal"), replace(context, step=1)
        )
    assert (reader._no_information, list(reader._history), reader._repair_work.copy()) == before


def test_hard_limit_bounds_no_information_even_without_repeated_pose():
    reader = ProgressReader("progress_exact")
    grid = [cell(i % 8, i // 8) for i in range(64)]
    for start in range(0, 64, 49):
        reader.observe(grid[start : start + 49])
    positions = [(x, y) for y in range(8) for x in (range(8) if y % 2 == 0 else range(7, -1, -1))]
    for step, position in enumerate(positions[:49]):
        _, _, receipt, _ = read(reader, step, [cell(*position, step=step)], position)
    repair = receipt["repair"]
    assert not repair["repeated_pose"] and repair["no_information_reads"] == 48
    assert repair["trigger"] == "hard_no_information_limit"
    assert repair["stage"] == 3 and repair["fallback_active"]
    assert all(not cue["used"] for cue in repair["cues"])


def test_work_deltas_include_observe_novelty_and_match_lifetime_counters():
    reader = ProgressReader("progress_zha")
    totals = {}
    for step in range(30):
        raw = [cell(step=step)]
        if step >= 27:
            raw.append(cell(1, 0, 8, step=step))
        _, _, receipt, _ = read(reader, step, raw)
        for key, value in receipt["repair"]["work_delta"].items():
            totals[key] = totals.get(key, 0) + value
    assert totals == reader._repair_work
    assert all(reader.costs[f"repair_{key}"] == value for key, value in totals.items())
    assert totals["payload_novelty_checks"] == 2
    assert totals["graph_fallback_reads"] > 0


def test_actual_exposed_stuck_episode_recovers_without_hidden_environment_access():
    pytest.importorskip("minigrid")
    from research.run_minigrid_benchmark import environment
    from research.run_progress_benchmark import run_episode

    class ObservationOnly:
        def __init__(self, inner):
            self._inner = inner

        def reset(self, **kwargs):
            return self._inner.reset(**kwargs)

        def step(self, action):
            return self._inner.step(action)

        def close(self):
            return self._inner.close()

        def __getattr__(self, name):
            raise AssertionError(f"hidden simulator access:{name}")

    episode = run_episode(
        "MiniGrid-KeyCorridorS6R3-v0",
        "progress_zha",
        2001,
        split="unit",
        step_cap=256,
        factory=lambda name: ObservationOnly(environment(name)),
    )
    assert episode["result"]["error"] is None and episode["result"]["success"]
    assert episode["result"]["steps"] < 200
    assert any(row["decision"]["repair"]["stage"] >= 1 for row in episode["trajectory"])
    assert all(len(row["decision"]["memory_ids"]) <= 96 for row in episode["trajectory"])
    assert all(
        row["decision"]["queries"] == [cue["vector"] for cue in row["decision"]["repair"]["cues"]]
        for row in episode["trajectory"]
    )
    assert episode["costs"]["repair_graph_fallback_reads"] == 0
    import hashlib
    import json

    bank = episode["routing_snapshots"]
    assert bank and episode["costs"]["wire_routing_snapshot_count"] == len(bank)
    for snapshot_id, layout in bank.items():
        assert (
            hashlib.sha256(
                json.dumps(layout, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            == snapshot_id
        )
    for row in episode["trajectory"]:
        decision = row["decision"]
        assert "repair" not in decision["dependency"]
        for i, route in enumerate(decision["route"]):
            assert route["snapshot_id"] in bank
            assert "node_spans" not in route and "index_fact_ids" not in route
            assert decision["repair"]["attempts"][i]["route_index"] == i
            assert "steps" not in decision["repair"]["attempts"][i]
    assert len(bank) < sum(len(row["decision"]["route"]) for row in episode["trajectory"])
