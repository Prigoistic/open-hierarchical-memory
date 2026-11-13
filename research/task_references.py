"""Task-specific fitted ZHA references; observed prefixes and explicit split identities."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import torch

from open_hierarchical_memory import TreeConfig
from open_hierarchical_memory.training import pooled_chunk_kl
from research.minigrid_benchmark import FEATURE_VERSION, Fact, fact_features, fixed_references

GEOMETRY = TreeConfig(chunk_size=4, depth=3)
FORMAT = "task-reference-v1"


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def identity(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 256:
        raise ValueError("context identity must be nonempty UTF-8, at most256 bytes")


@dataclass(frozen=True)
class TaskSample:
    context: str
    step: int
    queries: torch.Tensor
    keys: torch.Tensor

    @classmethod
    def observed(
        cls, context: str, step: int, facts: list[Fact], queries: torch.Tensor
    ) -> TaskSample:
        identity(context)
        if type(step) is not int or step < 0 or not facts or len(facts) > 8192:
            raise ValueError("invalid observed task sample")
        if len({f.position for f in facts}) != len(facts) or any(
            f.observed_step > step or f.id <= 0 for f in facts
        ):
            raise ValueError("sample must contain current observed heads only")
        keys = torch.stack(
            [torch.zeros(30, dtype=torch.float64), *[fact_features(f) for f in facts]]
        )
        sample = cls(context, step, queries.detach().clone(), keys)
        validate_sample(sample)
        return sample


def validate_sample(sample: TaskSample) -> None:
    identity(sample.context)
    if type(sample.step) is not int or sample.step < 0:
        raise ValueError("invalid sample step")
    for t in (sample.queries, sample.keys):
        if (
            not isinstance(t, torch.Tensor)
            or t.dtype != torch.float64
            or t.device.type != "cpu"
            or t.ndim != 2
            or t.shape[1] != 30
            or not bool(torch.isfinite(t).all())
        ):
            raise ValueError("task samples require finite CPU float64 matrices with30 features")
    if (
        not 1 <= len(sample.queries) <= 8
        or not 2 <= len(sample.keys) <= 8193
        or bool(sample.keys[0].any())
    ):
        raise ValueError("unsupported task sample size/sink")


@dataclass(frozen=True)
class RouterCheckpoint:
    values: tuple[tuple[float, ...], ...]
    kind: Literal["fixed", "random", "fitted"] = "fixed"
    training_contexts: tuple[str, ...] = ()
    validation_contexts: tuple[str, ...] = ()
    selected_step: int = 0
    corpus_hash: str = ""

    def __post_init__(self) -> None:
        if (
            not isinstance(self.values, tuple)
            or len(self.values) != 8
            or any(
                not isinstance(row, tuple)
                or len(row) != 30
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in row)
                for row in self.values
            )
        ):
            raise ValueError("checkpoint must own eight finite30-dimensional reference tuples")
        if (
            self.kind not in ("fixed", "random", "fitted")
            or type(self.selected_step) is not int
            or self.selected_step < 0
        ):
            raise ValueError("invalid reference checkpoint metadata")
        for contexts in (self.training_contexts, self.validation_contexts):
            if not isinstance(contexts, tuple) or len(set(contexts)) != len(contexts):
                raise ValueError("checkpoint context identities must be unique owned tuples")
            for context in contexts:
                identity(context)
        if set(self.training_contexts) & set(self.validation_contexts):
            raise ValueError("training and validation contexts overlap")
        if self.kind == "fitted" and (
            not self.training_contexts
            or not self.validation_contexts
            or len(self.corpus_hash) != 64
        ):
            raise ValueError("fitted checkpoint needs training/validation provenance")

    @classmethod
    def fixed(cls) -> RouterCheckpoint:
        return cls(tuple(tuple(float(x) for x in row) for row in fixed_references()[0].tolist()))

    def tensor(self) -> torch.Tensor:
        return torch.tensor(self.values, dtype=torch.float64)[None]

    def payload(self) -> dict[str, Any]:
        return {
            "format": FORMAT,
            "features": FEATURE_VERSION,
            "chunk_size": 4,
            "depth": 3,
            "kind": self.kind,
            "references": self.values,
            "training_contexts": self.training_contexts,
            "validation_contexts": self.validation_contexts,
            "selected_step": self.selected_step,
            "corpus_hash": self.corpus_hash,
        }

    @property
    def sha256(self) -> str:
        return digest(self.payload())

    def require_evaluation_context(self, context: str) -> None:
        identity(context)
        if context in (*self.training_contexts, *self.validation_contexts):
            raise ValueError("evaluation context was used to fit/select references")

    def save(self, path: Path) -> None:
        # A checkpoint is immutable evidence; never overwrite a prior result.
        with path.open("x") as stream:
            json.dump({**self.payload(), "sha256": self.sha256}, stream, indent=2, allow_nan=False)
            stream.write("\n")

    @classmethod
    def decode(cls, value: dict[str, Any]) -> RouterCheckpoint:
        expected = set(cls.fixed().payload()) | {"sha256"}
        if (
            set(value) != expected
            or value.get("format") != FORMAT
            or value.get("features") != FEATURE_VERSION
            or value.get("chunk_size") != 4
            or value.get("depth") != 3
        ):
            raise ValueError("unsupported reference coordinates/geometry/schema")
        try:
            result = cls(
                tuple(tuple(row) for row in value["references"]),
                value["kind"],
                tuple(value["training_contexts"]),
                tuple(value["validation_contexts"]),
                value["selected_step"],
                value["corpus_hash"],
            )
        except (TypeError, KeyError) as error:
            raise ValueError("malformed checkpoint") from error
        if value["sha256"] != result.sha256:
            raise ValueError("reference checkpoint checksum mismatch")
        return result

    @classmethod
    def load(cls, path: Path) -> RouterCheckpoint:
        if path.stat().st_size > 256 * 1024:
            raise ValueError("reference checkpoint exceeds256KiB")
        value = json.loads(path.read_text())
        if not isinstance(value, dict):
            raise ValueError("checkpoint must be an object")
        return cls.decode(value)


def sample_loss(sample: TaskSample, references: torch.Tensor) -> torch.Tensor:
    return pooled_chunk_kl(
        sample.queries[None],
        sample.keys[None],
        references,
        visible_counts=torch.full((len(sample.queries),), len(sample.keys), dtype=torch.int64),
        chunk_size=4,
        depth=3,
    )


def fit_task_references(
    training: list[TaskSample],
    validation: list[TaskSample],
    *,
    steps: int = 40,
    seed: int = 7,
    learning_rate: float = 0.01,
) -> tuple[RouterCheckpoint, list[dict[str, float | int]]]:
    if (
        not training
        or not validation
        or type(steps) is not int
        or not 1 <= steps <= 2000
        or type(seed) is not int
        or not 0 <= seed < 2**31
        or type(learning_rate) not in (int, float)
        or not math.isfinite(learning_rate)
        or learning_rate <= 0
    ):
        raise ValueError("invalid task fitting configuration")
    for sample in [*training, *validation]:
        validate_sample(sample)
    train_ids, val_ids = {s.context for s in training}, {s.context for s in validation}
    if train_ids & val_ids:
        raise ValueError("training and validation contexts overlap")

    def fingerprint(s: TaskSample) -> str:
        return digest([s.queries.tolist(), s.keys.tolist()])

    if {fingerprint(s) for s in training} & {fingerprint(s) for s in validation}:
        raise ValueError("training and validation contain identical numerical samples")
    # Own inputs: callers cannot mutate the fitting corpus during an optimisation step.
    training = [
        TaskSample(s.context, s.step, s.queries.detach().clone(), s.keys.detach().clone())
        for s in training
    ]
    validation = [
        TaskSample(s.context, s.step, s.queries.detach().clone(), s.keys.detach().clone())
        for s in validation
    ]
    corpus_hash = digest(
        [
            [s.context, s.step, digest(s.queries.tolist()), digest(s.keys.tolist())]
            for s in [*training, *validation]
        ]
    )
    refs = torch.nn.Parameter(RouterCheckpoint.fixed().tensor())
    optimizer = torch.optim.Adam([refs], lr=learning_rate)
    generator = torch.Generator().manual_seed(seed)

    loss_calls = teacher_pairs = reference_key_pairs = 0

    def objective(s: TaskSample) -> torch.Tensor:
        nonlocal loss_calls, teacher_pairs, reference_key_pairs
        loss_calls += 1
        teacher_pairs += len(s.queries) * len(s.keys)
        reference_key_pairs += (
            len(s.queries)
            * 8
            * sum(((len(s.keys) - 1) // (4**level)) * (4**level) for level in (1, 2, 3))
        )
        return sample_loss(s, refs)

    def evaluate(samples: list[TaskSample]) -> float:
        with torch.no_grad():
            return sum(float(objective(s)) for s in samples) / len(samples)

    best_val, best, best_step = evaluate(validation), refs.detach().clone(), 0
    history: list[dict[str, float | int]] = [
        {"step": 0, "training_kl": evaluate(training), "validation_kl": best_val}
    ]
    order: list[int] = []
    for step in range(1, steps + 1):
        if not order:
            order = torch.randperm(len(training), generator=generator).tolist()
        optimizer.zero_grad(set_to_none=True)
        loss = objective(training[order.pop()])
        loss.backward()  # type: ignore[no-untyped-call]  # PyTorch Tensor stub boundary
        if refs.grad is None or not bool(torch.isfinite(refs.grad).all()):
            raise ArithmeticError("non-finite/missing reference gradient")
        torch.nn.utils.clip_grad_norm_([refs], 1.0, error_if_nonfinite=True)
        optimizer.step()
        if not bool(torch.isfinite(refs).all()):
            raise ArithmeticError("non-finite fitted reference")
        if step % 5 == 0 or step == steps:
            score = evaluate(validation)
            history.append(
                {"step": step, "training_kl": evaluate(training), "validation_kl": score}
            )
            if score < best_val - 1e-12:
                best_val, best, best_step = score, refs.detach().clone(), step
    checkpoint = RouterCheckpoint(
        tuple(tuple(float(x) for x in row) for row in best[0].tolist()),
        "fitted",
        tuple(sorted(train_ids)),
        tuple(sorted(val_ids)),
        best_step,
        corpus_hash,
    )
    history[-1].update(
        loss_calls=loss_calls,
        dense_teacher_pairs=teacher_pairs,
        reference_key_pairs=reference_key_pairs,
        optimizer_steps=steps,
    )
    return checkpoint, history
