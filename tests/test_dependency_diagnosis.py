from research.diagnose_dependency_failures import inspect_episode


def walls():
    return [
        dict(id=i + 1, x=x, y=y, object=2)
        for i, (x, y) in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1)))
    ]


def row(facts, goal=(0, 0)):
    return {
        "new_facts": facts,
        "decision": {
            "memory_facts": [],
            "current_facts": [dict(x=0, y=0, object=1)],
            "goal": goal,
            "objective": "scan-frontier",
        },
    }


def test_diagnosis_uses_only_observed_prefix():
    result = inspect_episode({"trajectory": [row([]), row(walls(), goal=None)]})
    assert result.get("frontier_only_omitted_known_obstacles", 0) == 0
    assert result["actions"] == 2


def test_diagnosis_detects_known_obstacle_omission():
    result = inspect_episode({"trajectory": [row(walls())]})
    assert result["frontier_only_omitted_known_cells"] == 1
    assert result["frontier_only_omitted_known_obstacles"] == 1


def test_diagnosis_respects_current_version():
    changed = [dict(id=i + 5, x=f["x"], y=f["y"], object=1) for i, f in enumerate(walls())]
    result = inspect_episode({"trajectory": [row(walls(), goal=None), row(changed)]})
    assert result["frontier_only_omitted_known_cells"] == 1
    assert result.get("frontier_only_omitted_known_obstacles", 0) == 0
