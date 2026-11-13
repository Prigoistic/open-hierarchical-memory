"""Auditable offline reference-query replay over observed task prefixes.

This updates routing parameters, never canonical payloads or the task controller.
"""

from __future__ import annotations

import copy
import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import torch

from research.minigrid_benchmark import Fact
from research.task_references import (
    RouterCheckpoint,
    TaskSample,
    digest,
    sample_loss,
    validate_sample,
)

Schedule = Literal["uniform", "priority", "recent"]


@dataclass(frozen=True)
class ReplayItem:
    sample: TaskSample
    role: str
    source_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        validate_sample(self.sample)
        if (
            self.role not in ("anchor", "wake", "validation_old", "validation_new", "comparison")
            or len(self.source_ids) != len(self.sample.keys) - 1
            or len(set(self.source_ids)) != len(self.source_ids)
            or any(type(i) is not int or i <= 0 for i in self.source_ids)
        ):
            raise ValueError("invalid replay source mapping/role")

    @property
    def uid(self) -> str:
        return digest(self.payload())

    def payload(self) -> dict[str, Any]:
        s = self.sample
        return {
            "context": s.context,
            "step": s.step,
            "queries": s.queries.tolist(),
            "keys": s.keys.tolist(),
            "role": self.role,
            "source_ids": self.source_ids,
        }

    def owned(self) -> ReplayItem:
        s = self.sample
        return ReplayItem(
            TaskSample(s.context, s.step, s.queries.detach().clone(), s.keys.detach().clone()),
            self.role,
            self.source_ids,
        )


def episode_items(episode: dict[str, Any], role: str, count: int = 6) -> list[ReplayItem]:
    if type(count) is not int or not 2 <= count <= 32 or not episode["trajectory"]:
        raise ValueError("replay collection needs a nonempty observed trajectory")
    context = f"{episode['environment_id']}/seed={episode['seed']}"
    rows = episode["trajectory"]
    wanted = {int((len(rows) - 1) * i / (count - 1)) for i in range(count)}
    heads: dict[tuple[int, int], Fact] = {}
    seen: set[int] = set()
    items = []
    for step, row in enumerate(rows):
        if row["step"] != step:
            raise ValueError("noncontiguous observed replay prefix")
        for raw in row["new_facts"]:
            f = Fact(**raw)
            previous = heads.get(f.position)
            if (
                f.id <= 0
                or f.id in seen
                or f.observed_step > step
                or f.previous != (previous.id if previous else None)
            ):
                raise ValueError("foreign/future/invalid replay source version")
            heads[f.position] = f
            seen.add(f.id)
        if step in wanted:
            ordered = sorted(heads.values(), key=lambda f: f.id)
            sample = TaskSample.observed(
                context,
                step,
                ordered,
                torch.tensor(row["decision"]["queries"], dtype=torch.float64),
            )
            items.append(ReplayItem(sample, role, tuple(f.id for f in ordered)))
    return items


def deduplicate(groups: dict[str, list[ReplayItem]]) -> dict[str, int]:
    """Declared insertion-order filtering, independent of outcomes/labels."""
    seen: set[str] = set()
    dropped = {}
    for role, items in groups.items():
        kept = []
        for item in items:
            if item.role != role:
                raise ValueError("corpus role mismatch")
            fingerprint = digest([item.sample.queries.tolist(), item.sample.keys.tolist()])
            if fingerprint not in seen:
                seen.add(fingerprint)
                kept.append(item)
        dropped[role] = len(items) - len(kept)
        items[:] = kept
    return dropped


def replay_references(
    training: list[ReplayItem],
    validation_old: list[ReplayItem],
    validation_new: list[ReplayItem],
    parent: RouterCheckpoint,
    schedule: Schedule,
    *,
    seed: int,
    steps: int = 64,
    learning_rate: float = 1.0,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[RouterCheckpoint, dict[str, Any]]:
    if (
        schedule not in ("uniform", "priority", "recent")
        or type(seed) is not int
        or not 0 <= seed < 2**31
        or type(steps) is not int
        or not 1 <= steps <= 512
        or type(learning_rate) not in (int, float)
        or not math.isfinite(learning_rate)
        or not 0 < learning_rate <= 10
        or not training
        or not validation_old
        or not validation_new
    ):
        raise ValueError("invalid replay budget/corpus")
    if (
        any(i.role not in ("anchor", "wake") for i in training)
        or any(i.role != "validation_old" for i in validation_old)
        or any(i.role != "validation_new" for i in validation_new)
    ):
        raise ValueError("training/validation replay roles overlap")
    train_contexts = {i.sample.context for i in training} | set(parent.training_contexts)
    val_contexts = {i.sample.context for i in validation_old + validation_new} | set(
        parent.validation_contexts
    )
    if train_contexts & val_contexts:
        raise ValueError("replay training/validation contexts overlap")
    fingerprints = [
        {digest([i.sample.queries.tolist(), i.sample.keys.tolist()]) for i in items}
        for items in (training, validation_old, validation_new)
    ]
    if any(fingerprints[a] & fingerprints[b] for a, b in ((0, 1), (0, 2), (1, 2))):
        raise ValueError("replay training/validation numerical overlap")
    training = [i.owned() for i in training]
    validation_old = [i.owned() for i in validation_old]
    validation_new = [i.owned() for i in validation_new]
    pool = [i for i in training if schedule != "recent" or i.role == "wake"]
    if not pool:
        raise ValueError("recent replay needs wake observations")
    refs = parent.tensor().requires_grad_(True)
    rng = random.Random(seed)
    work = dict.fromkeys(
        (
            "loss_calls",
            "dense_teacher_pairs",
            "reference_key_pairs",
            "gradient_calls",
            "priority_calls",
            "validation_calls",
        ),
        0,
    )

    def objective(item: ReplayItem, purpose: str) -> torch.Tensor:
        s = item.sample
        work["loss_calls"] += 1
        work[purpose + "_calls"] += 1
        work["dense_teacher_pairs"] += len(s.queries) * len(s.keys)
        work["reference_key_pairs"] += (
            len(s.queries)
            * 8
            * sum(((len(s.keys) - 1) // 4**level) * 4**level for level in (1, 2, 3))
        )
        return sample_loss(s, refs)

    def validate(step: int) -> dict[str, Any]:
        with torch.no_grad():
            old = sum(float(objective(i, "validation")) for i in validation_old) / len(
                validation_old
            )
            new = sum(float(objective(i, "validation")) for i in validation_new) / len(
                validation_new
            )
        return {
            "step": step,
            "old_validation_kl": old,
            "new_validation_kl": new,
            "selection_kl": (old + new) / 2,
            "reference_hash": digest(refs.detach().tolist()),
        }

    history = [validate(0)]
    best_score, best_step, best = history[0]["selection_kl"], 0, refs.detach().clone()
    updates, refreshes = [], []
    probabilities = [1 / len(pool)] * len(pool)
    for step in range(1, steps + 1):
        if schedule == "priority" and (step - 1) % 8 == 0:
            with torch.no_grad():
                losses = [float(objective(i, "priority")) for i in pool]
            weights = [(max(0.0, x) + 1e-6) ** 0.6 for x in losses]
            total = math.fsum(weights)
            probabilities = [0.1 / len(pool) + 0.9 * w / total for w in weights]
            refreshes.append(
                {"before_step": step, "losses": losses, "probabilities": probabilities.copy()}
            )
        index = rng.choices(range(len(pool)), weights=probabilities, k=1)[0]
        item = pool[index]
        before_hash = digest(refs.detach().tolist())
        loss = objective(item, "gradient")
        (gradient,) = torch.autograd.grad(loss, refs)
        if not bool(torch.isfinite(gradient).all()):
            raise ArithmeticError("nonfinite replay gradient")
        norm = float(torch.linalg.vector_norm(gradient))
        factor = min(1.0, 1.0 / (norm + 1e-12))
        with torch.no_grad():
            refs.add_(gradient, alpha=-float(learning_rate) * factor)
        if not bool(torch.isfinite(refs).all()):
            raise ArithmeticError("nonfinite replay parameters")
        record = {
            "step": step,
            "sample_id": item.uid,
            "pool_index": index,
            "role": item.role,
            "probability": probabilities[index],
            "loss": float(loss.detach()),
            "gradient": gradient.tolist(),
            "parameters": refs.detach().tolist(),
            "gradient_norm": norm,
            "clip_factor": factor,
            "before_hash": before_hash,
            "after_hash": digest(refs.detach().tolist()),
        }
        updates.append(record)
        if on_update is not None:
            on_update(copy.deepcopy(record))
        if step % 8 == 0 or step == steps:
            history.append(validate(step))
            if history[-1]["selection_kl"] < best_score - 1e-12:
                best_score, best_step, best = (
                    history[-1]["selection_kl"],
                    step,
                    refs.detach().clone(),
                )
    corpus_hash = digest(
        {
            "parent": parent.sha256,
            "schedule": schedule,
            "seed": seed,
            "steps": steps,
            "learning_rate": learning_rate,
            "items": [i.uid for i in training + validation_old + validation_new],
        }
    )
    checkpoint = RouterCheckpoint(
        tuple(tuple(float(v) for v in row) for row in best[0].tolist()),
        "fitted",
        tuple(sorted(train_contexts)),
        tuple(sorted(val_contexts)),
        best_step,
        corpus_hash,
    )
    result = {
        "parent_hash": parent.sha256,
        "child_hash": checkpoint.sha256,
        "schedule": schedule,
        "seed": seed,
        "steps": steps,
        "learning_rate": learning_rate,
        "selected_step": best_step,
        "selected_parameters_changed": checkpoint.values != parent.values,
        "pool_ids": [i.uid for i in pool],
        "validation_old_ids": [i.uid for i in validation_old],
        "validation_new_ids": [i.uid for i in validation_new],
        "history": history,
        "updates": updates,
        "priority_refreshes": refreshes,
        "work": work,
        "owned_corpus_tensor_bytes": sum(
            t.numel() * t.element_size()
            for i in training + validation_old + validation_new
            for t in (i.sample.queries, i.sample.keys)
        ),
    }
    return checkpoint, result
