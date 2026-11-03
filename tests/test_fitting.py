import pytest
import torch

from open_hierarchical_memory import InputError, TreeConfig
from research.fitting import TraceExample, fit_references


def samples(name):
    generator = torch.Generator().manual_seed(15)
    return [
        TraceExample(
            name,
            0,
            *[torch.randn((1, 17, 2), generator=generator, dtype=torch.float64) for _ in range(3)],
        )
    ]


def settings():
    return dict(
        seed=7,
        count=2,
        steps=10,
        learning_rate=0.01,
        gradient_limit=1.0,
        validation_every=5,
        positions=(7, 16),
        geometry=TreeConfig(chunk_size=2, depth=2),
    )


def test_fitter_rejects_reused_validation_document():
    with pytest.raises(InputError, match="overlap"):
        fit_references(samples("same-document"), samples("same-document"), **settings())


def test_fit_is_reproducible_and_never_selects_worse_validation_than_initial():
    training, validation = samples("train"), samples("validation")
    before = training[0].keys.clone()
    first = fit_references(training, validation, **settings())
    second = fit_references(training, validation, **settings())
    torch.testing.assert_close(first.references, second.references, rtol=0, atol=0)
    assert first.history == second.history
    assert first.selected_step in [row["step"] for row in first.history]
    chosen = next(row for row in first.history if row["step"] == first.selected_step)
    assert chosen["validation_kl"] <= first.history[0]["validation_kl"] + 1e-12
    torch.testing.assert_close(training[0].keys, before, rtol=0, atol=0)
    assert not first.references.requires_grad


def test_initial_checkpoint_remains_eligible_when_already_exact():
    # All supervised queries are identical; initial references are exact tangents.
    training, validation = samples("train"), samples("validation")
    training[0].queries.fill_(0.25)
    validation[0].queries.fill_(0.25)
    result = fit_references(training, validation, **settings())
    assert result.selected_step == 0
    torch.testing.assert_close(result.references, result.initial_references, rtol=0, atol=0)
