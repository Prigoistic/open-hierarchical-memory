"""Compare the actual package output to an 80-digit scalar Decimal oracle."""

import random
from decimal import Decimal, localcontext

import pytest
import torch

from open_hierarchical_memory import ExecutionMode, HierarchicalIndex, TreeConfig


@pytest.mark.parametrize("seed", range(16))
def test_actual_attention_against_high_precision_oracle(seed):
    rng = random.Random(seed)
    keys = [[rng.uniform(-4, 4) for _ in range(3)] for _ in range(29)]
    values = [[rng.uniform(-3, 3) for _ in range(2)] for _ in keys]
    query = [rng.uniform(-2, 2) for _ in range(3)]
    references = [[rng.uniform(-2, 2) for _ in range(3)] for _ in range(3)]
    index = HierarchicalIndex(
        torch.tensor([[keys]], dtype=torch.float64),
        torch.tensor([[values]], dtype=torch.float64),
        torch.tensor([references], dtype=torch.float64),
        config=TreeConfig(chunk_size=3, depth=3),
    )
    for mode in ExecutionMode:
        result = index.attend(
            torch.tensor([[[query]]], dtype=torch.float64),
            visible_counts=torch.tensor([[23]]),
            mode=mode,
            p=0.73,
        )
        ids = result.routes[0].selected_ids
        with localcontext() as ctx:
            ctx.prec = 80
            logits = [
                sum(
                    (
                        Decimal.from_float(q) * Decimal.from_float(k)
                        for q, k in zip(query, keys[i], strict=True)
                    ),
                    Decimal(0),
                )
                / Decimal(3).sqrt()
                for i in ids
            ]
            maximum = max(logits)
            masses = [(logit - maximum).exp() for logit in logits]
            total = sum(masses, Decimal(0))
            expected = [
                float(
                    sum(
                        (
                            mass * Decimal.from_float(values[i][j])
                            for mass, i in zip(masses, ids, strict=True)
                        ),
                        Decimal(0),
                    )
                    / total
                )
                for j in range(2)
            ]
        torch.testing.assert_close(
            result.output[0, 0, 0],
            torch.tensor(expected, dtype=torch.float64),
            rtol=1e-9,
            atol=1e-10,
        )
