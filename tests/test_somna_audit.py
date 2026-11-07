"""Negative controls prove that the separate auditor rejects corrupted evidence."""

from copy import deepcopy
from dataclasses import asdict

import pytest
import torch

from research.somna_spatial import EpisodeIndex, evaluate, make_world, offline_fork, wake_checkpoint
from scripts.audit_somna_spatial import audit_world


@pytest.fixture
def entry():
    original = torch.get_num_threads()
    torch.set_num_threads(1)
    world = make_world(19, 5)
    bank = EpisodeIndex(world.transitions, len(world.cells), world.goal)
    q = wake_checkpoint(world.transitions, bank.states, bank.goal)
    result = offline_fork(bank, q, "uniform", "zha", updates=8, seed=world.seed + 40)
    result["evaluation"] = evaluate(world, result["q"])
    value = {
        "world": asdict(world),
        "archive_hash": bank.archive_hash,
        "initial_q": q.tolist(),
        "forks": [result],
    }
    yield value
    torch.set_num_threads(original)


def test_independent_auditor_accepts_clean_trace(entry):
    assert audit_world(entry)["updates_checked"] == 8


@pytest.mark.parametrize("fault", ["target", "selection", "archive", "frame", "work"])
def test_independent_auditor_detects_semantic_fault(entry, fault):
    corrupted = deepcopy(entry)
    fork = corrupted["forks"][0]
    if fault == "target":
        fork["records"][0]["after"] += 0.1
    elif fault == "selection":
        fork["records"][0]["selected_ids"].remove(0)
    elif fault == "archive":
        corrupted["world"]["transitions"][0]["successor"] += 1
    elif fault == "frame":
        fork["frames"][-1]["q"][0][0] += 1
    elif fault == "work":
        fork["work"]["attention_pairs"] = 0
    with pytest.raises(AssertionError):
        audit_world(corrupted)
