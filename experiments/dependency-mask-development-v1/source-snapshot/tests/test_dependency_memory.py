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
    _, _, before, mask1 = reader.select_with_context(q, ctx(cells[:1]))
    assert any(b["missing"] for b in before["bundles"])
    opened = reader.observe([replace(cells[1], state=0, observed_step=1)])[0]
    selected, _, after, mask2 = reader.select_with_context(q, ctx([cell(0, 0, step=1)], step=1))
    assert opened.id in {f.id for f in selected} and heads[1].id not in {f.id for f in selected}
    assert any(b["kind"] == "goal_landmark" and b["status"] == "complete" for b in after["bundles"])
    assert mask1 is not None and mask2 is not None
    assert mask1.bits == mask2.bits and mask1.head_hash != mask2.head_hash
    assert mask1.version < mask2.version
