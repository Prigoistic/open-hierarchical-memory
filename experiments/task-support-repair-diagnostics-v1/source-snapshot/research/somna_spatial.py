"""Observed symbolic episodes, numerical ZHA reads and durable offline updates.

This is a Dyna-style diagnostic, not learned latent dreaming or a speed claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import torch

from open_hierarchical_memory import ExecutionMode, HierarchicalIndex, TreeConfig

Backend = Literal["dense", "zha"]
Policy = Literal["none", "uniform", "priority"]
GAMMA = 0.95
DECISION_TOLERANCE = 1e-10
REPRESENTATION = "symbolic-state-action-onehot-v1"


@dataclass(frozen=True)
class Transition:
    identifier: int
    state: int
    action: int
    successor: int
    reward: float
    evidence: str = "observed"


@dataclass(frozen=True)
class World:
    seed: int
    width: int
    cells: tuple[tuple[int, int], ...]
    goal: int
    transitions: tuple[Transition, ...]
    evaluation_starts: tuple[int, ...]


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def make_world(seed: int, width: int = 11) -> World:
    """Seeded perfect maze; evaluator labels stay outside the replay API."""
    if type(seed) is not int or type(width) is not int or width < 5 or width % 2 == 0:
        raise ValueError("seed must be integer and width odd, at least five")
    rng = random.Random(seed)
    opened = {(1, 1)}
    stack = [(1, 1)]
    while stack:
        x, y = stack[-1]
        neighbors = [(x + dx, y + dy) for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2))]
        choices = [
            (a, b)
            for a, b in neighbors
            if 0 < a < width - 1 and 0 < b < width - 1 and (a, b) not in opened
        ]
        if not choices:
            stack.pop()
            continue
        nxt = rng.choice(choices)
        opened.add(((x + nxt[0]) // 2, (y + nxt[1]) // 2))
        opened.add(nxt)
        stack.append(nxt)
    cells = tuple(sorted(opened, key=lambda xy: (xy[1], xy[0])))
    positions = {xy: i for i, xy in enumerate(cells)}
    goal = len(cells) - 1
    raw = []
    for state, (x, y) in enumerate(cells):
        if state == goal:
            continue
        for action, (dx, dy) in enumerate(((0, -1), (1, 0), (0, 1), (-1, 0))):
            successor = positions.get((x + dx, y + dy), state)
            raw.append((state, action, successor, float(successor == goal)))
    rng.shuffle(raw)
    transitions = tuple(Transition(i + 1, *row) for i, row in enumerate(raw))
    starts = list(range(goal))
    random.Random(seed + 9000).shuffle(starts)
    return World(seed, width, cells, goal, transitions, tuple(starts[:16]))


def validate_archive(episodes: tuple[Transition, ...], states: int, goal: int) -> None:
    if type(states) is not int or states < 2 or not 0 <= goal < states or not episodes:
        raise ValueError("invalid archive dimensions")
    ids = set()
    pairs = set()
    for row in episodes:
        if row.evidence != "observed":
            raise ValueError("replay accepts observed evidence only")
        if any(type(v) is not int for v in (row.identifier, row.state, row.action, row.successor)):
            raise ValueError("transition indexes must be integers")
        if row.identifier in ids or row.identifier < 1 or (row.state, row.action) in pairs:
            raise ValueError("duplicate episode or state/action")
        if (
            not 0 <= row.state < states
            or row.state == goal
            or not 0 <= row.action < 4
            or not 0 <= row.successor < states
        ):
            raise ValueError("transition outside supported state/action space")
        if not math.isfinite(row.reward) or row.reward != float(row.successor == goal):
            raise ValueError("diagnostic requires unit terminal reward")
        ids.add(row.identifier)
        pairs.add((row.state, row.action))
    if ids != set(range(1, len(episodes) + 1)):
        raise ValueError("episode IDs must be contiguous in canonical archive order")


def key_for(state: int, action: int, states: int) -> torch.Tensor:
    if (
        type(state) is not int
        or type(action) is not int
        or not 0 <= state < states
        or not 0 <= action < 4
    ):
        raise ValueError("invalid state/action query")
    vector = torch.zeros(states + 4, dtype=torch.float64)
    vector[state] = 16.0
    vector[states + action] = 16.0
    return vector


class EpisodeIndex:
    """Owned numerical bank shared by exact and approximate readers.

    State-basis references are idealized, untrained and costly. No semantic
    embedding, fitting benefit or practical compression advantage is implied.
    """

    def __init__(self, episodes: tuple[Transition, ...], states: int, goal: int) -> None:
        validate_archive(episodes, states, goal)
        self.episodes = tuple(episodes)
        self.states = states
        self.goal = goal
        self.archive_hash = digest([asdict(row) for row in episodes])
        keys = torch.zeros((1, 1, len(episodes) + 1, states + 4), dtype=torch.float64)
        values = torch.zeros((1, 1, len(episodes) + 1, states + 1), dtype=torch.float64)
        for row in episodes:
            keys[0, 0, row.identifier] = key_for(row.state, row.action, states)
            values[0, 0, row.identifier, row.successor] = 1.0
            values[0, 0, row.identifier, -1] = row.reward
        references = torch.zeros((1, states, states + 4), dtype=torch.float64)
        references[0, :, :states] = torch.eye(states, dtype=torch.float64) * 16.0
        started = time.perf_counter()
        self.index = HierarchicalIndex(
            keys, values, references, config=TreeConfig(chunk_size=8, depth=2)
        )
        self.build_seconds = time.perf_counter() - started
        self.keys = keys.clone()
        self.values = values.clone()

    def read(self, state: int, action: int, backend: Backend) -> dict[str, Any]:
        if backend not in ("dense", "zha"):
            raise ValueError("unsupported reader")
        query = key_for(state, action, self.states).reshape(1, 1, 1, -1)
        started = time.perf_counter()
        result = self.index.attend(
            query,
            visible_counts=torch.tensor([[len(self.episodes) + 1]], dtype=torch.int64),
            mode=ExecutionMode.DENSE if backend == "dense" else ExecutionMode.PAPER_APPROXIMATE,
            p=0.8,
            collect_trace=True,
        )
        elapsed = time.perf_counter() - started
        route = result.routes[0]
        return {
            "probabilities": result.output[0, 0, 0, :-1].tolist(),
            "reward": float(result.output[0, 0, 0, -1]),
            "selected_ids": list(route.selected_ids),
            "scored_nodes": route.scored_nodes,
            "attention_pairs": len(route.selected_ids),
            "summary_dot_products": route.scored_nodes * self.states,
            "seconds": elapsed,
            "steps": [
                {
                    "level": step.level,
                    "candidates": [n.index for n in step.candidates],
                    "selected": [n.index for n in step.selected],
                    "scores": list(step.scores),
                }
                for step in route.steps
            ],
        }


def target(q: torch.Tensor, probabilities: list[float], reward: float, goal: int) -> float:
    continuation = q.max(dim=1).values.clone()
    continuation[goal] = 0.0
    return reward + GAMMA * float(torch.tensor(probabilities, dtype=torch.float64) @ continuation)


def wake_checkpoint(episodes: tuple[Transition, ...], states: int, goal: int) -> torch.Tensor:
    validate_archive(episodes, states, goal)
    q = torch.zeros((states, 4), dtype=torch.float64)
    for row in episodes:
        continuation = 0.0 if row.successor == goal else float(q[row.successor].max())
        q[row.state, row.action] = row.reward + GAMMA * continuation
    return q


def offline_fork(
    bank: EpisodeIndex,
    checkpoint: torch.Tensor,
    policy: Policy,
    backend: Backend,
    *,
    updates: int = 256,
    seed: int = 0,
) -> dict[str, Any]:
    """No world, simulator, held-out starts or future labels enter this API.

    Priority is exhaustive observed-graph Bellman residual scheduling, not
    efficient prioritized sweeping. Every scheduler comparison is charged.
    """
    if policy not in ("none", "uniform", "priority") or backend not in ("dense", "zha"):
        raise ValueError("unsupported fork")
    if type(updates) is not int or updates < 0 or updates > 4096:
        raise ValueError("updates must be a bounded nonnegative integer")
    if (
        checkpoint.dtype != torch.float64
        or checkpoint.shape != (bank.states, 4)
        or not bool(torch.isfinite(checkpoint).all())
    ):
        raise ValueError("invalid checkpoint")
    q = checkpoint.detach().clone()
    initial_hash = digest(q.tolist())
    rng = random.Random(seed)
    frames = [{"iteration": 0, "q": q.tolist(), "read": None}]
    records = []
    started = time.perf_counter()
    for iteration in range(0 if policy == "none" else updates):
        if policy == "uniform":
            row = bank.episodes[rng.randrange(len(bank.episodes))]
            scheduler_comparisons = 0
        else:
            state_values = q.max(dim=1).values.tolist()
            state_values[bank.goal] = 0.0
            residuals = [
                abs(r.reward + GAMMA * state_values[r.successor] - float(q[r.state, r.action]))
                for r in bank.episodes
            ]
            peak = max(residuals)
            row = next(
                r
                for r, error in zip(bank.episodes, residuals, strict=True)
                if error >= peak - DECISION_TOLERANCE
            )
            scheduler_comparisons = len(bank.episodes)
        read = bank.read(row.state, row.action, backend)
        before = float(q[row.state, row.action])
        after = target(q, read["probabilities"], read["reward"], bank.goal)
        q[row.state, row.action] = after
        records.append(
            {
                "iteration": iteration + 1,
                "state": row.state,
                "action": row.action,
                "evidence_id": row.identifier,
                "before": before,
                "after": after,
                "delta": after - before,
                "scheduler_comparisons": scheduler_comparisons,
                **read,
            }
        )
        if (iteration + 1) % 8 == 0 or iteration + 1 == updates:
            frames.append({"iteration": iteration + 1, "q": q.tolist(), "read": records[-1]})
    return {
        "policy": policy,
        "backend": backend,
        "archive_hash": bank.archive_hash,
        "representation": REPRESENTATION,
        "snapshot_id": bank.index.info.snapshot_id,
        "initial_checkpoint_hash": initial_hash,
        "checkpoint_hash": digest(q.tolist()),
        "q": q.tolist(),
        "updates": len(records),
        "records": records,
        "frames": frames,
        "offline_seconds": time.perf_counter() - started,
        "work": {
            name: sum(row[name] for row in records)
            for name in (
                "scheduler_comparisons",
                "scored_nodes",
                "summary_dot_products",
                "attention_pairs",
            )
        },
        "environment_calls_during_offline": 0,
    }


def evaluate(world: World, q: list[list[float]]) -> dict[str, Any]:
    """Evaluation only: known map, previously untested start positions."""
    tensor = torch.tensor(q, dtype=torch.float64)
    if tensor.shape != (len(world.cells), 4) or not bool(torch.isfinite(tensor).all()):
        raise ValueError("invalid evaluation policy")
    lookup = {(row.state, row.action): row.successor for row in world.transitions}
    trials = []
    for start in world.evaluation_starts:
        state = start
        path = [state]
        seen = set()
        while state != world.goal and state not in seen and len(path) <= 4 * len(world.cells):
            seen.add(state)
            values = tensor[state]
            action = int(torch.nonzero(values >= values.max() - DECISION_TOLERANCE)[0, 0])
            state = lookup[state, action]
            path.append(state)
        trials.append({"start": start, "success": state == world.goal, "path": path})
    return {"successes": sum(t["success"] for t in trials), "trials": len(trials), "paths": trials}


def save_checkpoint(path: Path, result: dict[str, Any]) -> None:
    """Inert JSON. Temporary reads/frames are deliberately not persisted."""
    q = result["q"]
    tensor = torch.tensor(q, dtype=torch.float64)
    if tensor.ndim != 2 or tensor.shape[1] != 4 or not bool(torch.isfinite(tensor).all()):
        raise ValueError("invalid checkpoint values")
    payload = {
        name: result[name] for name in ("archive_hash", "representation", "checkpoint_hash", "q")
    }
    if digest(q) != payload["checkpoint_hash"]:
        raise ValueError("checkpoint hash does not match values")
    with path.open("x") as stream:
        json.dump(payload, stream, allow_nan=False)
        stream.write("\n")


def load_checkpoint(path: Path, archive_hash: str) -> list[list[float]]:
    if path.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("checkpoint exceeds size limit")
    payload = json.loads(path.read_text())
    if set(payload) != {"archive_hash", "representation", "checkpoint_hash", "q"}:
        raise ValueError("unsupported checkpoint schema")
    if payload["archive_hash"] != archive_hash or payload["representation"] != REPRESENTATION:
        raise ValueError("checkpoint archive/representation mismatch")
    q = payload["q"]
    tensor = torch.tensor(q, dtype=torch.float64)
    if (
        tensor.ndim != 2
        or tensor.shape[1] != 4
        or not bool(torch.isfinite(tensor).all())
        or digest(q) != payload["checkpoint_hash"]
    ):
        raise ValueError("invalid checkpoint values or hash")
    return q  # type: ignore[no-any-return]
