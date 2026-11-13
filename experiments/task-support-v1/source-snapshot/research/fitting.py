"""Reference-only fitting. The fitting API never accepts test samples."""

import math
from dataclasses import dataclass

import torch
from torch import Tensor

from open_hierarchical_memory import InputError, NumericalError, TreeConfig
from open_hierarchical_memory.summaries import require_tensor
from open_hierarchical_memory.training import pooled_chunk_kl


@dataclass(frozen=True)
class TraceExample:
    document_id: str
    window_offset: int
    queries: Tensor
    keys: Tensor
    values: Tensor


@dataclass(frozen=True)
class FitResult:
    references: Tensor
    initial_references: Tensor
    random_references: Tensor
    selected_step: int
    history: tuple[dict, ...]


def validate_examples(examples: list[TraceExample]) -> None:
    if not examples:
        raise InputError("nonempty examples required")
    shape = examples[0].queries.shape
    for sample in examples:
        for name in ("queries", "keys", "values"):
            require_tensor(name, getattr(sample, name), 3)
        if (
            sample.queries.shape != shape
            or sample.keys.shape != shape
            or sample.values.shape[:2] != shape[:2]
        ):
            raise InputError("pilot examples must share aligned head/sequence dimensions")
        if not sample.document_id:
            raise InputError("document identity required")


def sample_loss(
    sample: TraceExample, references: Tensor, positions: tuple[int, ...], geometry: TreeConfig
) -> Tensor:
    return pooled_chunk_kl(
        sample.queries[:, list(positions)],
        sample.keys,
        references,
        visible_counts=torch.tensor([p + 1 for p in positions], dtype=torch.int64),
        chunk_size=geometry.chunk_size,
        depth=geometry.depth,
    )


@torch.no_grad()
def mean_loss(
    samples: list[TraceExample],
    references: Tensor,
    positions: tuple[int, ...],
    geometry: TreeConfig,
) -> float:
    return sum(float(sample_loss(s, references, positions, geometry)) for s in samples) / len(
        samples
    )


def fit_references(
    training: list[TraceExample],
    validation: list[TraceExample],
    *,
    seed: int,
    count: int,
    steps: int,
    learning_rate: float,
    gradient_limit: float,
    validation_every: int,
    positions: tuple[int, ...],
    geometry: TreeConfig,
) -> FitResult:
    validate_examples(training)
    validate_examples(validation)
    if validation[0].queries.shape != training[0].queries.shape:
        raise InputError("training and validation shapes must match")
    if {s.document_id for s in training} & {s.document_id for s in validation}:
        raise InputError("training and validation documents overlap")
    if (
        type(seed) is not int
        or type(steps) is not int
        or steps < 1
        or type(count) is not int
        or count < 1
        or type(validation_every) is not int
        or validation_every < 1
    ):
        raise InputError("invalid fitting integer configuration")
    if (
        not math.isfinite(learning_rate)
        or learning_rate <= 0
        or not math.isfinite(gradient_limit)
        or gradient_limit <= 0
    ):
        raise InputError("invalid optimizer parameters")
    if not positions or any(
        type(p) is not int or not 0 <= p < training[0].queries.shape[1] for p in positions
    ):
        raise InputError("invalid supervised query positions")
    pool = torch.cat([sample.queries[:, list(positions)] for sample in training], dim=1).detach()
    if count > pool.shape[1]:
        raise InputError("not enough training queries for reference initialization")
    generator = torch.Generator().manual_seed(seed)
    initial = torch.stack(
        [head[torch.randperm(pool.shape[1], generator=generator)[:count]] for head in pool]
    ).clone()
    random = pool.mean(1, keepdim=True) + torch.randn(
        initial.shape, generator=generator, dtype=torch.float64
    ) * pool.std(1, keepdim=True)
    references = torch.nn.Parameter(initial.clone())
    optimizer = torch.optim.Adam([references], lr=learning_rate)
    best_validation = mean_loss(validation, initial, positions, geometry)
    best = initial.clone()
    best_step = 0
    history = [
        {
            "step": 0,
            "train_kl": mean_loss(training, initial, positions, geometry),
            "validation_kl": best_validation,
        }
    ]
    order = []
    for step in range(1, steps + 1):
        if not order:
            order = torch.randperm(len(training), generator=generator).tolist()
        sample = training[order.pop()]
        optimizer.zero_grad(set_to_none=True)
        loss = sample_loss(sample, references, positions, geometry)
        loss.backward()
        if references.grad is None or not torch.isfinite(references.grad).all():
            raise NumericalError("non-finite or missing reference gradient")
        torch.nn.utils.clip_grad_norm_([references], gradient_limit, error_if_nonfinite=True)
        optimizer.step()
        if not torch.isfinite(references).all():
            raise NumericalError("non-finite optimizer state")
        if step % validation_every == 0 or step == steps:
            validation_kl = mean_loss(validation, references, positions, geometry)
            history.append(
                {
                    "step": step,
                    "train_kl": mean_loss(training, references, positions, geometry),
                    "validation_kl": validation_kl,
                }
            )
            if validation_kl < best_validation - 1e-12:
                best_validation = validation_kl
                best = references.detach().clone()
                best_step = step
            print(f"seed={seed} step={step} validation_KL={validation_kl:.6g}", flush=True)
    return FitResult(best, initial, random, best_step, tuple(history))
