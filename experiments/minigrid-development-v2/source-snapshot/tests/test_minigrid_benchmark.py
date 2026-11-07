"""Partial-observation, bounded-workspace and official closed-loop regressions."""

from __future__ import annotations

import ast
import inspect
import math
from dataclasses import FrozenInstanceError, replace

import numpy as np
import pytest
import torch

from research.minigrid_benchmark import (
    ADAPTIVE_P,
    COLORS,
    READERS,
    DIMENSION,
    OBJECTS,
    Fact,
    FactReader,
    ObservationPlanner,
    fact_features,
    normalize_observation,
    observed_cells,
    query_vectors,
)


@pytest.fixture(autouse=True)
def one_thread():
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(old)


def observation(cells=None, direction=0, mission="go to the goal"):
    image = np.zeros((7, 7, 3), dtype=np.uint8)
    image[3, 6] = [1, 0, 0]
    for point, value in (cells or {}).items():
        image[point] = value
    return {"image": image, "direction": direction, "mission": mission}


@pytest.mark.parametrize(
    "direction,front,right",
    [
        (0, (11, -4), (10, -3)),
        (1, (10, -3), (9, -4)),
        (2, (9, -4), (10, -5)),
        (3, (10, -5), (11, -4)),
    ],
)
def test_official_egocentric_coordinates_and_carried_object(direction, front, right):
    obs = observation({(3, 5): [5, 2, 0], (4, 6): [6, 1, 0], (3, 6): [5, 4, 0]}, direction)
    cells, inventory = observed_cells(obs, (10, -4), 3)
    bypos = {f.position: f for f in cells}
    assert bypos[front].object == 5
    assert bypos[right].object == 6
    assert bypos[(10, -4)].object == 1
    assert inventory == (5, 4)


@pytest.mark.parametrize(
    "field,value",
    [
        ("direction", True),
        ("direction", 4),
        ("image", np.zeros((7, 7, 3), dtype=np.float64)),
        ("mission", None),
        ("oracle", {"target": [3, 4]}),
    ],
)
def test_observation_boundary_rejects_hidden_fields_and_bad_types(field, value):
    obs = observation()
    obs[field] = value
    with pytest.raises(ValueError):
        normalize_observation(obs)


def test_observation_ownership_and_immutable_versions():
    obs = observation({(3, 5): [4, 2, 1]})
    owned = normalize_observation(obs)
    obs["image"][3, 5] = [8, 1, 0]
    assert owned["image"][3, 5].tolist() == [4, 2, 1]
    reader = FactReader("full", 8)
    closed = Fact(0, 1, 0, 4, 2, 1, 0, 0)
    original = reader.observe([closed])[0]
    with pytest.raises(FrozenInstanceError):
        original.state = 0
    opened = reader.observe([replace(closed, state=0, observed_step=2)])[0]
    assert opened.previous == original.id and opened.first_seen == 0
    selected, _ = reader.select(torch.zeros((1, DIMENSION), dtype=torch.float64))
    assert selected == [opened]
    assert reader.archive()[0]["state"] == 1


def scalar_features(fact):
    values = [
        2 * fn(f * math.pi * x / 128)
        for x in (fact.x, fact.y)
        for f in (1, 2, 4)
        for fn in (math.cos, math.sin)
    ]
    values += [4.0 * (fact.object == kind) for kind in range(11)]
    values += [2.0 * (fact.color == color) for color in range(6)]
    values += [6.0 * fact.cue]
    return values


def facts(count=100):
    return [
        Fact(0, i % 20 - 10, i // 20, 5 if i == 0 else 1 + i % 4, i % 6, 0, 0, 0, cue=i == 0)
        for i in range(count)
    ]


def test_identical_feature_exact_reader_matches_independent_ranking():
    reader = FactReader("exact", 16)
    observed = reader.observe(facts())
    q = torch.zeros((2, DIMENSION), dtype=torch.float64)
    q[0, -1] = 8
    q[1, 12 + 5] = 4
    q[1, 23 + 3] = 2
    selected, _ = reader.select(q)
    scored = [
        (
            max(
                sum(a * b for a, b in zip(query, scalar_features(f), strict=True))
                for query in q.tolist()
            ),
            f.id,
        )
        for f in observed
    ]
    expected = [
        identifier for _, identifier in sorted(scored, key=lambda row: (-row[0], row[1]))[:16]
    ]
    assert [f.id for f in selected] == expected
    assert reader.costs["exact_score_pairs"] == 200
    assert fact_features(observed[0]).tolist() == pytest.approx(
        scalar_features(observed[0]), abs=1e-14
    )


def test_zha_uses_sparse_current_originals_and_numerical_subset_attention():
    reader = FactReader("zha", 16)
    observed = reader.observe(facts())
    q = torch.zeros((1, DIMENSION), dtype=torch.float64)
    q[0, -1] = 8
    selected, routes = reader.select(q)
    assert len(selected) <= 16 and any(f.cue for f in selected)
    route = routes[0]
    assert 0 in route["selected_logical_ids"]
    assert 0 < len(route["selected_fact_ids"]) < len(observed)
    scores = [0.0] + [
        sum(a * b for a, b in zip(q[0].tolist(), scalar_features(observed[i - 1]), strict=True))
        / math.sqrt(DIMENSION)
        for i in route["selected_fact_ids"]
    ]
    values = [[0.0, 0.0, 0.0]] + [
        [f.object, f.color, f.state] for f in (observed[i - 1] for i in route["selected_fact_ids"])
    ]
    weights = [math.exp(s - max(scores)) for s in scores]
    expected = [
        sum(w * v[j] for w, v in zip(weights, values, strict=True)) / sum(weights) for j in range(3)
    ]
    assert route["attention_output"] == pytest.approx(expected, abs=1e-12)
    changed = reader.observe([replace(observed[0], id=0, object=1, cue=False, observed_step=2)])[0]
    selected, _ = reader.select(q)
    assert observed[0].id not in {f.id for f in selected}
    assert changed.id in {f["id"] for f in reader.archive()}


@pytest.mark.parametrize("name", READERS)
def test_reader_capacity_and_no_cross_episode_state(name):
    reader = FactReader(name, 8)
    reader.observe(facts())
    selected, _ = reader.select(query_vectors((0, 0), "go to the goal"))
    if name == "none":
        assert selected == []
    elif name == "full":
        assert len(selected) == 100
    else:
        assert 0 < len(selected) <= 8
    other = FactReader(name, 8)
    assert other.select(query_vectors((0, 0), "go to the goal"))[0] == []
    if name == "recency":
        assert all(f.id >= 93 for f in selected)
    if name == "fifo":
        assert [f.id for f in selected] == list(range(1, 9))


def test_controller_has_no_environment_or_persistent_planner_map():
    import research.minigrid_benchmark as module

    forbidden = {
        "grid",
        "agent_pos",
        "success_pos",
        "failure_pos",
        "unwrapped",
        "goal_pos",
        "obj",
        "carrying",
    }
    tree = ast.parse(inspect.getsource(module))
    assert not {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)} & forbidden
    actor = ObservationPlanner("none", 8)
    actor.reader.observe(facts())
    actor.reader.archive = lambda: (_ for _ in ()).throw(
        AssertionError("policy cannot export archive")
    )
    _, decision, _ = actor.act(observation({(3, 5): [1, 0, 0]}))
    assert decision["memory_ids"] == []
    assert set(vars(actor)) == {
        "reader",
        "position",
        "direction",
        "previous_action",
        "previous_front",
        "recent",
        "step",
    }
    assert actor.recent.maxlen == 16


def test_no_memory_cannot_inherit_archive_only_cue_metadata():
    corner = observation(
        {(2, 5): [5, 1, 0], (2, 6): [1, 0, 0], (3, 5): [1, 0, 0]},
        mission="go to the matching object at the end of the hallway",
    )
    full, _ = observed_cells(corner, (0, 0), 0)
    assert any(f.cue for f in full)
    partial = observation({(2, 5): [5, 1, 0], (3, 5): [1, 0, 0]}, mission=corner["mission"])
    actor = ObservationPlanner("none", 8)
    actor.reader.observe(full)
    _, decision, _ = actor.act(partial)
    assert not any(f["cue"] for f in decision["current_facts"])
    assert decision["memory_ids"] == []
    assert not decision["objective"].startswith("matching-target")


def test_egomotion_uses_visible_passability_and_rejects_compass_drift():
    actor = ObservationPlanner("none", 8)
    actor.direction = 0
    actor.previous_action = 2
    actor.previous_front = Fact(0, 1, 0, 2, 5, 0, 0, 0)
    actor._advance(0)
    assert actor.position == (0, 0)
    actor.previous_front = replace(actor.previous_front, object=1)
    actor._advance(0)
    assert actor.position == (1, 0)
    actor.previous_action = 0
    with pytest.raises(ValueError, match="compass"):
        actor._advance(0)


@pytest.mark.parametrize(
    "identifier",
    [
        "MiniGrid-MemoryS17Random-v0",
        "MiniGrid-MultiRoom-N6-v0",
        "MiniGrid-DoorKey-16x16-v0",
        "MiniGrid-KeyCorridorS6R3-v0",
    ],
)
def test_official_closed_loop_full_observed_control(identifier):
    pytest.importorskip("minigrid")
    from minigrid.core.constants import COLOR_TO_IDX, OBJECT_TO_IDX

    from research.run_minigrid_benchmark import environment, require_versions, run_episode

    assert require_versions()["minigrid"] == "3.1.0"
    assert COLORS == COLOR_TO_IDX and OBJECTS == OBJECT_TO_IDX

    class ObservationOnlyEnvironment:
        def __init__(self, inner):
            self._inner = inner

        def reset(self, **kwargs):
            return self._inner.reset(**kwargs)

        def step(self, action):
            return self._inner.step(action)

        def close(self):
            self._inner.close()

        def __getattr__(self, name):
            raise AssertionError(f"forbidden environment attribute{name}")

    result = run_episode(
        identifier,
        "full",
        0,
        split="unit",
        step_cap=512,
        factory=lambda name: ObservationOnlyEnvironment(environment(name)),
    )
    assert result["result"]["error"] is None
    assert result["result"]["success"] and result["result"]["return"] > 0
    assert result["trajectory"][-1]["terminated"]
    for step, row in enumerate(result["trajectory"]):
        assert row["step"] == step
        assert all(f["observed_step"] <= step for f in row["decision"]["memory_facts"])
        assert set(row["observation"]) == {"image", "direction", "mission"}


def test_adaptive_reader_repairs_underfilled_workspace_without_unrouted_facts():
    fixed, adaptive = FactReader("zha", 96), FactReader("zha_adaptive", 96)
    originals = facts(60)
    fixed.observe(originals)
    current = adaptive.observe(originals)
    query = torch.zeros((1, DIMENSION), dtype=torch.float64)
    fixed_selected, _ = fixed.select(query)
    selected, routes = adaptive.select(query)
    assert 0 < len(fixed_selected) < len(current)
    assert {f.id for f in selected} == {f.id for f in current}
    attempts = sorted({route["attempt"] for route in routes})
    assert attempts == list(range(len(attempts))) and 1 < len(attempts) <= len(ADAPTIVE_P)
    assert [route["p"] for route in routes] == list(ADAPTIVE_P[: len(attempts)])
    assert adaptive.costs["routing_passes"] == len(attempts)
    assert adaptive.costs["full_candidate_fallbacks"] == int(routes[-1]["p"] == 1.0)
    assert adaptive.costs["raw_attention_pairs"] == sum(
        len(route["selected_logical_ids"]) for route in routes
    )
    assert adaptive.costs["scored_nodes"] == sum(
        len(step["candidates"]) for route in routes for step in route["steps"]
    )
    assert adaptive.costs["summary_dot_products"] == adaptive.costs["scored_nodes"] * 8
    assert adaptive.costs["rerank_pairs"] == len(current)
    assert adaptive.costs["exact_score_pairs"] == 0
    stale = current[0]
    replacement = adaptive.observe([replace(stale, id=0, state=1, observed_step=2)])[0]
    selected, routes = adaptive.select(query)
    assert stale.id not in {f.id for f in selected}
    assert replacement.id in {f.id for f in selected}
    assert all(stale.id not in route["selected_fact_ids"] for route in routes)


def test_adaptive_topk_reranks_only_actual_candidate_union_and_obeys_capacity():
    reader = FactReader("zha_adaptive", 16)
    observed = reader.observe(facts())
    queries = query_vectors((0, 0), "go to the goal")
    selected, routes = reader.select(queries)
    candidates = {i for route in routes for i in route["selected_fact_ids"]}
    assert len(selected) == 16
    assert {f.id for f in selected} <= candidates
    scalar_rank = sorted(
        (
            (
                max(
                    sum(a * b for a, b in zip(q, scalar_features(f), strict=True))
                    for q in queries.tolist()
                ),
                f.id,
            )
            for f in observed
            if f.id in candidates
        ),
        key=lambda pair: (-pair[0], pair[1]),
    )
    assert [f.id for f in selected] == [i for _, i in scalar_rank[:16]]
    assert reader.costs["rerank_pairs"] == len(candidates) * len(queries)
    assert reader.costs["exact_score_pairs"] == 0
    assert reader.costs["routing_passes"] == 1
    assert reader.costs["full_candidate_fallbacks"] == 0


def test_adaptive_full_candidate_fallback_is_explicitly_charged():
    reader = FactReader("zha_adaptive", 96)
    current = reader.observe(facts(96))
    query = torch.zeros((1, DIMENSION), dtype=torch.float64)
    selected, routes = reader.select(query)
    assert len(selected) == len(current)
    assert routes[-1]["p"] == 1.0
    assert reader.costs["full_candidate_fallbacks"] == 1
    assert reader.costs["routing_passes"] == len(ADAPTIVE_P)
    assert set(routes[-1]["selected_fact_ids"]) == {f.id for f in current}
