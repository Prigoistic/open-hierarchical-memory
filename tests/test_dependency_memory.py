"""Behavior, information-boundary and raw-fact dependency regressions."""

from dataclasses import replace

import pytest
import torch

from research.dependency_memory import WORK_KEYS, DependencyReader, ObservedGraph
from research.minigrid_benchmark import (
    Fact,
    KnownCoverage,
    ObservationPlanner,
    ReadContext,
    query_vectors,
)


@pytest.fixture(autouse=True)
def one_thread():
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(old)


def cell(x, y, kind=1, color=0, state=0, step=0):
    return Fact(0, x, y, kind, color, state, step, step)


def ctx(current, inventory=None, position=(0, 0), mission="go to the goal", step=0):
    return ReadContext(position, 0, mission, inventory, tuple(current), step)


def graph_of(cells, inventory=None):
    reader = DependencyReader("graph")
    heads = reader.observe(cells)
    return ObservedGraph(heads, ctx([cells[0]], inventory), dict.fromkeys(WORK_KEYS, 0)), heads


def test_coverage_is_known_only_and_never_adds_traversal():
    bits = bytearray(512)
    offset = 32 * 64 + 33
    bits[offset // 8] |= 1 << (offset % 8)
    mask = KnownCoverage(bytes(bits), 1, "0" * 64)
    assert mask.contains((1, 0)) and not mask.contains((0, 0))
    assert not mask.contains((32, 0))
    actor = ObservationPlanner("none")
    actor.direction = 0
    view = {(0, 0): cell(0, 0)}
    action, _, _, _, path = actor._plan(view, None, "go to the goal", known_coverage=mask)
    assert path == [(0, 0)] and action in (0, 1)
    assert (1, 0) not in path


def test_known_omission_suppressed_but_unknown_frontier_remains():
    actor = ObservationPlanner("none")
    actor.direction = 0
    view = {(0, 0): cell(0, 0)}
    mask = KnownCoverage(bytes([255]) * 512, 1, "0" * 64)
    assert actor._plan(view, None, "go to the goal")[1] == "scan-frontier"
    assert (
        actor._plan(view, None, "go to the goal", known_coverage=mask)[1]
        == "scan-no-reachable-frontier"
    )


def test_feasible_detour_does_not_invent_missing_key_prerequisite():
    graph, heads = graph_of(
        [cell(0, 0), cell(1, 0, 4, 0, 2), cell(2, 0, 8), cell(0, 1), cell(1, 1), cell(2, 1)]
    )
    bundle = graph.bundle(heads[2], "goal_landmark")
    assert bundle.missing == ()
    assert heads[1].id not in bundle.path_ids
    assert set(bundle.path_ids) == {heads[i].id for i in (0, 2, 3, 4, 5)}
    assert bundle.prerequisite_ids == ()


def test_key_behind_own_lock_is_not_accessible_support():
    graph, heads = graph_of(
        [cell(0, 0), cell(1, 0, 4, 0, 2), cell(2, 0), cell(3, 0, 5, 0), cell(2, 1, 8)]
    )
    bundle = graph.bundle(heads[-1], "goal_landmark")
    assert bundle.missing == (f"unreachable_matching_key:{heads[1].id}:0",)
    assert bundle.prerequisite_ids == ()


def test_accessible_key_support_and_adjacent_interaction():
    graph, heads = graph_of([cell(0, 0), cell(1, 0, 4, 0, 2), cell(2, 0, 8), cell(0, 1, 5, 0)])
    bundle = graph.bundle(heads[2], "goal_landmark")
    assert bundle.missing == () and bundle.prerequisite_ids == (heads[3].id,)
    assert heads[3].id not in bundle.path_ids and heads[3].id in bundle.required_ids
    graph2, heads2 = graph_of([cell(0, 0), cell(1, 0, 4, 0, 2), cell(2, 0, 8)], (5, 0))
    held = graph2.bundle(heads2[2], "goal_landmark")
    assert held.missing == () and held.prerequisite_ids == ()


def test_whole_bundle_or_explicit_budget_rejection():
    reader = DependencyReader("graph", 8)
    cells = [cell(x, 0, 8 if x == 12 else 1) for x in range(13)]
    cells += [cell(x, y, 2) for x in range(13) for y in (-1, 1)]
    cells += [cell(-1, 0, 2), cell(13, 0, 2)]
    reader.observe(cells)
    reader.observe(cells[:1])
    selected, _, receipt, mask = reader.select_with_context(
        query_vectors((0, 0), "go to the goal"), ctx(cells[:1])
    )
    assert selected == [] and mask is not None
    assert receipt["status"] == "structural_rejection"
    bundle = receipt["bundles"][0]
    assert bundle["status"] == "overbudget" and bundle["required_historical_count"] == 40
    assert bundle["omitted_ids"] == list(range(2, 42))
    assert receipt["work_delta"]["bundles_overbudget"] >= 1


def test_flat_mask_preserves_selection_and_charges_transport():
    reader = DependencyReader("flat_exact_mask", 8)
    reader.observe([cell(x, 0) for x in range(12)])
    q = query_vectors((0, 0), "go to the goal")
    reader.observe([cell(0, 0)])
    expected, _ = reader.source.select(q)
    selected, routes, receipt, mask = reader.select_with_context(q, ctx([cell(0, 0)]))
    assert selected == expected and routes == []
    assert len(selected) == 8 and mask is not None and len(mask.bits) == 512
    assert sum(byte.bit_count() for byte in mask.bits) == 12
    assert receipt["work_delta"]["head_scan_items"] == 12
    assert receipt["work_delta"]["graph_build_nodes"] == 0
    assert receipt["work_delta"]["coverage_binary_bytes"] == 512
    assert receipt["work_delta"]["coverage_json_bytes"] > 1024
    assert receipt["bundles"] == []


def test_stale_door_correction_updates_support_and_identity():
    reader = DependencyReader("graph")
    cells = [cell(0, 0), cell(1, 0, 4, 0, 2), cell(2, 0, 8)]
    heads = reader.observe(cells)
    q = query_vectors((0, 0), "go to the goal")
    reader.observe(cells[:1])
    _, _, before, mask1 = reader.select_with_context(q, ctx(cells[:1]))
    assert any(b["missing"] for b in before["bundles"])
    opened = reader.observe([replace(cells[1], state=0, observed_step=1)])[0]
    reader.observe([cell(0, 0, step=1)])
    selected, _, after, mask2 = reader.select_with_context(q, ctx([cell(0, 0, step=1)], step=1))
    assert opened.id in {f.id for f in selected} and heads[1].id not in {f.id for f in selected}
    assert any(b["kind"] == "goal_landmark" and b["status"] == "complete" for b in after["bundles"])
    assert mask1 is not None and mask2 is not None
    assert mask1.bits == mask2.bits and mask1.head_hash != mask2.head_hash
    assert mask1.version < mask2.version


def test_historical_exact_mask_matches_independent_exclusion_ranking():
    reader = DependencyReader("flat_exact_history_mask", 8)
    raw = [
        cell(i % 10, i // 10, 5 if i % 3 == 0 else 8 if i % 5 == 0 else 1, i % 6)
        for i in range(100)
    ]
    for start in range(0, 100, 49):
        reader.observe(raw[start : start + 49])
    visible = raw[:30]
    reader.observe(visible)
    q = torch.zeros((2, 30), dtype=torch.float64)
    q[0, 17], q[1, 20], q[1, 26] = 8, 6, 2
    selected, _, receipt, _ = reader.select_with_context(q, ctx(visible))
    # Only object/color channels are nonzero, so this scalar ranking is exact
    # integer arithmetic independent of the production feature/rerank routines.
    expected = sorted(
        enumerate(raw, 1),
        key=lambda pair: (
            -max(
                32 if pair[1].object == 5 else 0,
                (24 if pair[1].object == 8 else 0) + (4 if pair[1].color == 3 else 0),
            ),
            pair[0],
        ),
    )
    visible_positions = {f.position for f in visible}
    expected = [identifier for identifier, f in expected if f.position not in visible_positions][:8]
    assert [f.id for f in selected] == expected
    assert all(f.position not in visible_positions for f in selected)
    assert receipt["work_delta"]["flat_history_filter_items"] == 57
    assert reader.source.costs["exact_score_pairs"] == 200
    assert reader.source.capacity == 57


@pytest.mark.parametrize("bad", ["future_step", "foreign_cell", "old_visible_set"])
def test_read_context_cannot_supply_unobserved_or_future_support(bad):
    reader = DependencyReader("flat_exact_mask")
    reader.observe([cell(0, 0), cell(1, 0)])
    reader.observe([cell(0, 0)])
    context = ctx([cell(0, 0)])
    if bad == "future_step":
        context = ctx([cell(0, 0, step=1)], step=1)
    elif bad == "foreign_cell":
        context = ctx([cell(0, 0), cell(10, 10, 8)])
    else:
        context = ctx([cell(0, 0), cell(1, 0)])
    with pytest.raises(ValueError, match="context"):
        reader.select_with_context(query_vectors((0, 0), "go to the goal"), context)


def test_current_support_exemption_does_not_discard_remembered_cue_role():
    reader = DependencyReader("graph")
    original = replace(cell(0, 0, 5), cue=True)
    reader.observe([cell(-1, 0), original])
    current = [cell(-1, 0), cell(0, 0, 5)]
    reader.observe(current)
    context = ctx(current, position=(-1, 0))
    heads = list(reader._heads.values())
    graph = ObservedGraph(heads, context, dict.fromkeys(WORK_KEYS, 0))
    cue = next(f for f in heads if f.object == 5)
    bundle = graph.bundle(cue, "cue")
    assert cue.id in bundle.historical_ids and cue.id not in bundle.current_support_ids


def test_receipts_and_returned_facts_do_not_alias_mutable_engine_state():
    reader = DependencyReader("flat_exact_mask", 8)
    raw = [cell(x, 0) for x in range(10)]
    reader.observe(raw)
    current = [cell(0, 0)]
    reader.observe(current)
    q = query_vectors((0, 0), "go to the goal")
    selected, _, first, mask = reader.select_with_context(q, ctx(current))
    first["source_head_ids"].clear()
    first["context"]["current_facts"][0]["object"] = 8
    first["work_delta"]["coverage_binary_bytes"] = -1
    selected2, _, second, mask2 = reader.select_with_context(q, ctx(current))
    assert selected2 == selected
    assert len(second["source_head_ids"]) == 10
    assert second["context"]["current_facts"][0]["object"] == 1
    assert second["work_delta"]["coverage_binary_bytes"] == 512
    assert mask == mask2


def test_seed_perturbation_changes_raw_evidence_and_common_planner_action():
    import numpy as np

    raw = [cell(x, 0, 8 if x == -4 else 1) for x in range(-4, 5)]
    raw += [cell(x, y, 2) for x in range(-4, 5) for y in (-1, 1)]
    raw += [cell(-5, 0, 2)]
    actions, receipts = [], []
    for seed_position in ((-4, 0), (4, 0)):
        reader = DependencyReader("bundle_exact")
        original = reader.observe(raw)
        seed = next(f for f in original if f.position == seed_position)
        # Explicit test ablation, not a claimed actual-ZHA read.
        reader.source.select = lambda queries, s=seed: ([s], [])
        actor = ObservationPlanner("none", injected_reader=reader)
        image = np.zeros((7, 7, 3), dtype=np.uint8)
        image[3, 6] = [1, 0, 0]
        action, decision, _ = actor.act(
            {"image": image, "direction": 0, "mission": "go to the goal"}
        )
        actions.append(action)
        receipts.append(decision)
    assert actions == [1, 2]
    assert receipts[0]["memory_ids"] != receipts[1]["memory_ids"]
    assert receipts[0]["objective"] == "goal"
    assert receipts[1]["objective"] == "explore"
    assert receipts[0]["coverage"]["bits_hex"] == receipts[1]["coverage"]["bits_hex"]


def test_reader_receipt_is_not_a_second_action_or_goal_channel():
    import numpy as np

    class MaliciousReceiptReader:
        costs = {}

        def observe(self, visible):
            return []

        def select_with_context(self, queries, context):
            return [], [], {"action": 2, "goal": [10, 0], "path": [[0, 0], [10, 0]]}, None

        def archive(self):
            return []

    image = np.zeros((7, 7, 3), dtype=np.uint8)
    image[3, 6] = [1, 0, 0]
    obs = {"image": image, "direction": 0, "mission": "go to the goal"}
    action, decision, _ = ObservationPlanner("none", injected_reader=MaliciousReceiptReader()).act(
        obs
    )
    expected, original, _ = ObservationPlanner("none").act(obs)
    assert action == expected and action != 2
    assert decision["plan"] == original["plan"] == [(0, 0)]
    assert decision["goal"] == original["goal"]


def test_coverage_edges_and_typed_context_are_owned_and_bounded():
    from dataclasses import FrozenInstanceError

    mask = KnownCoverage(bytes(512), 1, "0" * 64)
    with pytest.raises(FrozenInstanceError):
        mask.version = 2
    with pytest.raises(ValueError):
        KnownCoverage(bytes(513), 1, "0" * 64)
    with pytest.raises(ValueError):
        ReadContext([0, 0], 0, "x", None, (), 0)
    with pytest.raises(ValueError):
        ReadContext((0, 0), 0, "x", (5, True), (), 0)
    reader = DependencyReader("graph")
    with pytest.raises(ValueError):
        reader.observe([cell(32, 0)])
    with pytest.raises(ValueError):
        reader.observe([cell(0, 0), cell(0, 0, 8)])
    with pytest.raises(ValueError):
        reader.observe([replace(cell(0, 0), id=1)])


def test_wall_to_floor_update_cannot_reuse_stale_graph_or_path_ids():
    reader = DependencyReader("graph")
    raw = [cell(0, 0), cell(1, 0, 2), cell(2, 0, 8)]
    old = reader.observe(raw)
    reader.observe(raw[:1])
    q = query_vectors((0, 0), "go to the goal")
    _, _, before, _ = reader.select_with_context(q, ctx(raw[:1]))
    rejected = next(b for b in before["bundles"] if b["kind"] == "goal_landmark")
    assert rejected["status"] == "missing_prerequisite"
    assert rejected["missing"] == ("no_observed_route",)
    replacement = reader.observe([cell(1, 0, step=1)])[0]
    reader.observe([cell(0, 0, step=1)])
    selected, _, after, _ = reader.select_with_context(q, ctx([cell(0, 0, step=1)], step=1))
    assert replacement.id in {f.id for f in selected}
    assert old[1].id not in {f.id for f in selected}
    complete = next(b for b in after["bundles"] if b["kind"] == "goal_landmark")
    assert complete["status"] == "complete"
    assert old[1].id not in complete["required_ids"]


def test_bundle_rejects_foreign_superseded_or_changed_seed_payload():
    graph, heads = graph_of([cell(0, 0), cell(1, 0), cell(2, 0, 8)])
    for bad in (
        replace(heads[-1], id=999),
        replace(heads[-1], object=5),
        replace(heads[-1], observed_step=100),
    ):
        with pytest.raises(ValueError, match="canonical"):
            graph.bundle(bad, "goal_landmark")
    with pytest.raises(ValueError, match="canonical"):
        graph.bundle(heads[-1], "goal_landmark", (replace(heads[0], id=999),))


def test_bundle_paths_are_observed_adjacent_and_matching_cue_is_raw_support():
    graph, heads = graph_of([cell(0, 0), cell(1, 0), cell(2, 0, 5), cell(-1, 0), cell(-2, 0, 5)])
    cue = replace(heads[-1], cue=True)
    graph.by_id[cue.id] = cue
    graph.cells[cue.position] = cue
    bundle = graph.bundle(heads[2], "matching_landmark", (cue,))
    assert bundle.semantic_support_ids == (cue.id,)
    assert cue.id in bundle.required_ids and cue.id not in bundle.prerequisite_ids
    for path in bundle.paths:
        assert path[0] == heads[0].id
        for a, b in zip(path, path[1:], strict=False):
            x, y = graph.by_id[a], graph.by_id[b]
            assert abs(x.x - y.x) + abs(x.y - y.y) == 1
            assert x.object in (1, 3, 4, 8) and y.object in (1, 3, 4, 8)
    assert bundle.paths[0][-1] == heads[1].id
    assert set(bundle.current_support_ids).isdisjoint(bundle.historical_ids)
    assert set(bundle.current_support_ids) | set(bundle.historical_ids) == set(bundle.required_ids)
