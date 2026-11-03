import math

import pytest
import torch

from open_hierarchical_memory import InputError
from open_hierarchical_memory.training import pooled_chunk_kl

from . import oracle


def inputs():
    generator = torch.Generator().manual_seed(812)
    query = torch.randn((2, 3, 3), generator=generator, dtype=torch.float64, requires_grad=True)
    keys = torch.randn((2, 19, 3), generator=generator, dtype=torch.float64, requires_grad=True)
    references = torch.randn(
        (2, 4, 3), generator=generator, dtype=torch.float64, requires_grad=True
    )
    counts = torch.tensor([7, 12, 19], dtype=torch.int64)
    return query, keys, references, counts


def test_training_loss_matches_literal_independent_partition():
    queries, keys, references, counts = inputs()
    observed = pooled_chunk_kl(
        queries, keys, references, visible_counts=counts, chunk_size=3, depth=2
    )
    total = 0.0
    for head in range(2):
        for query_index, count in enumerate(counts.tolist()):
            query = queries[head, query_index].detach().tolist()
            raw = keys[head, :count].detach().tolist()
            logits = [oracle.dot(query, key) / math.sqrt(3) for key in raw]
            for level in (1, 2):
                span = 3**level
                groups = [(0, 1)]
                groups.extend((start, min(start + span, count)) for start in range(1, count, span))
                truth, approximation = [], []
                for start, stop in groups:
                    exact = oracle.lse(logits[start:stop])
                    truth.append(exact)
                    if start == 0 or stop - start < span:
                        approximation.append(exact)
                    else:
                        tangents = []
                        for ref in references[head].detach().tolist():
                            mean, bias = oracle.summary(raw[start:stop], ref)
                            tangents.append(oracle.dot(query, mean) / math.sqrt(3) + bias)
                        approximation.append(max(tangents))
                z_true, z_predicted = oracle.lse(truth), oracle.lse(approximation)
                total += sum(
                    math.exp(a - z_true) * (a - z_true - b + z_predicted)
                    for a, b in zip(truth, approximation, strict=True)
                )
    assert observed.item() == pytest.approx(total / 6, abs=1e-11)


def test_only_references_receive_gradients_and_gradient_matches_finite_difference():
    queries, keys, references, counts = inputs()
    loss = pooled_chunk_kl(queries, keys, references, visible_counts=counts, chunk_size=3, depth=2)
    loss.backward()
    assert queries.grad is None and keys.grad is None
    assert references.grad is not None
    assert bool(torch.isfinite(references.grad).all())
    assert references.grad.abs().sum().item() > 0
    flat_index = references.grad.abs().reshape(-1).argmax().item()
    plus, minus = references.detach().clone(), references.detach().clone()
    epsilon = 1e-6
    plus.reshape(-1)[flat_index] += epsilon
    minus.reshape(-1)[flat_index] -= epsilon
    a = pooled_chunk_kl(queries, keys, plus, visible_counts=counts, chunk_size=3, depth=2)
    b = pooled_chunk_kl(queries, keys, minus, visible_counts=counts, chunk_size=3, depth=2)
    assert references.grad.reshape(-1)[flat_index].item() == pytest.approx(
        ((a - b) / (2 * epsilon)).item(), rel=2e-5, abs=1e-8
    )


def test_matching_reference_query_gives_zero_kl_at_all_levels():
    generator = torch.Generator().manual_seed(9)
    keys = torch.randn((2, 19, 3), generator=generator, dtype=torch.float64)
    queries = torch.randn((2, 1, 3), generator=generator, dtype=torch.float64)
    loss = pooled_chunk_kl(
        queries, keys, queries.clone(), visible_counts=torch.tensor([19]), chunk_size=3, depth=3
    )
    assert abs(loss.item()) < 1e-12


def test_objective_cannot_see_future_keys():
    queries, keys, references, _ = inputs()
    counts = torch.tensor([7, 7, 7])
    a = pooled_chunk_kl(queries, keys, references, visible_counts=counts, chunk_size=3, depth=2)
    changed = keys.detach().clone()
    changed[:, 7:] *= 1000
    b = pooled_chunk_kl(queries, changed, references, visible_counts=counts, chunk_size=3, depth=2)
    torch.testing.assert_close(a, b, rtol=0, atol=0)


def test_optimizer_reduces_training_loss_without_updating_inputs():
    queries, keys, references, counts = inputs()
    query_before, keys_before = queries.detach().clone(), keys.detach().clone()
    optimizer = torch.optim.Adam([references], lr=0.03)
    start = pooled_chunk_kl(
        queries, keys, references, visible_counts=counts, chunk_size=3, depth=2
    ).item()
    for _ in range(30):
        optimizer.zero_grad(set_to_none=True)
        loss = pooled_chunk_kl(
            queries, keys, references, visible_counts=counts, chunk_size=3, depth=2
        )
        loss.backward()
        optimizer.step()
    final = pooled_chunk_kl(
        queries, keys, references, visible_counts=counts, chunk_size=3, depth=2
    ).item()
    assert final < start * 0.8
    torch.testing.assert_close(queries, query_before, rtol=0, atol=0)
    torch.testing.assert_close(keys, keys_before, rtol=0, atol=0)


def test_invalid_training_visibility_is_rejected():
    queries, keys, references, counts = inputs()
    for bad in (counts.float(), torch.tensor([0, 12, 19]), torch.tensor([7, 12, 99]), counts[:1]):
        with pytest.raises(InputError):
            pooled_chunk_kl(queries, keys, references, visible_counts=bad, chunk_size=3, depth=2)
