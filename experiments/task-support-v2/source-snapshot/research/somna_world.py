"""Controlled continuous dynamics and fixed cue encoding, outside the engine.

The simulator is used only for collecting observed episodes and sealed evaluation.
Offline learning and imagined rollouts must not call it.
"""

from __future__ import annotations

import math
import random
from typing import Any

import torch

ACTIONS = ((0.0, -1.0), (1.0, 0.0), (0.0, 1.0), (-1.0, 0.0))
FEATURE_VERSION = "continuous-half-harmonic-cue-v2"


def pair(value: Any, name: str, limit: float = 1.0) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must have two finite numbers")
    if any(type(v) not in (float, int) or not math.isfinite(v) or abs(v) > limit for v in value):
        raise ValueError(f"{name} must have two finite numbers in [-{limit},{limit}]")
    return [float(v) for v in value]


def context_value(value: Any, *, optional: bool = False) -> int | None:
    if value is None and optional:
        return None
    if type(value) is not int or value not in (0, 1):
        raise ValueError("context must be 0 or 1" + (" or null" if optional else ""))
    return value


def cue(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) - {
        "position",
        "action",
        "context",
        "mask",
        "audit",
    }:
        raise ValueError(
            "unsupported cue fields; episode identifiers/answer labels are not accepted"
        )
    position = pair(value.get("position", [0.0, 0.0]), "position")
    mask = value.get("mask", [True, True])
    if not isinstance(mask, list) or len(mask) != 2 or any(type(v) is not bool for v in mask):
        raise ValueError("mask must contain two booleans")
    action = value.get("action")
    if action is not None:
        action = pair(action, "action")
    context = context_value(value.get("context"), optional=True)
    audit = value.get("audit", True)
    if type(audit) is not bool:
        raise ValueError("audit must be boolean")
    if not any(mask) and action is None and context is None:
        raise ValueError("at least one observed cue is required")
    return {
        "position": position,
        "mask": mask,
        "action": action,
        "context": context,
        "audit": audit,
    }


def features(value: dict[str, Any]) -> torch.Tensor:
    """Missing axes contribute zero. Keys and queries use identical fixed coordinates."""
    data = cue(value)
    out: list[float] = []
    for coordinate, visible in zip(data["position"], data["mask"], strict=True):
        out.extend(
            [
                3.0 * fn(frequency * math.pi * coordinate) if visible else 0.0
                for frequency in (0.5, 1.0)
                for fn in (math.cos, math.sin)
            ]
        )
    out.extend([0.0, 0.0] if data["action"] is None else [4.0 * v for v in data["action"]])
    out.extend(
        [0.0, 0.0]
        if data["context"] is None
        else [6.0 * float(data["context"] == i) for i in (0, 1)]
    )
    return torch.tensor(out, dtype=torch.float64)


def simulate(position: list[float], action: list[float], context: int) -> list[float]:
    """Two context-dependent vector fields; a synthetic task, not physics data."""
    x, y = pair(position, "position")
    ax, ay = pair(action, "action")
    context_value(context)
    if context == 0:
        dx, dy = 0.14 * ax + 0.035 * math.sin(2 * y), 0.14 * ay + 0.035 * math.cos(2 * x)
    else:
        dx, dy = -0.14 * ay + 0.045 * math.cos(2 * y), 0.14 * ax - 0.045 * math.sin(2 * x)
    return [max(-1.0, min(1.0, x + dx)), max(-1.0, min(1.0, y + dy))]


def observations(
    seed: int, count: int, *, context: int | None = None, offset: int = 0
) -> list[dict[str, Any]]:
    if (
        type(seed) is not int
        or type(count) is not int
        or not 1 <= count <= 512
        or type(offset) is not int
        or offset < 0
    ):
        raise ValueError("invalid collection budget")
    context_value(context, optional=True)
    rng = random.Random(seed + offset * 103)
    out = []
    for i in range(count):
        # Rare context arrives early, then is displaced by a long common phase.
        ctx = context if context is not None else int(offset + i < 16)
        position = [rng.uniform(-0.88, 0.88), rng.uniform(-0.88, 0.88)]
        action = list(rng.choice(ACTIONS))
        out.append(
            {
                "position": position,
                "action": action,
                "context": ctx,
                "successor": simulate(position, action, ctx),
                "evidence": "observed",
                "source": "controlled-simulator-v1",
            }
        )
    return out


def model_inputs(rows: list[dict[str, Any]]) -> torch.Tensor:
    return torch.tensor(
        [
            [*r["position"], *r["action"], float(r["context"] == 0), float(r["context"] == 1)]
            for r in rows
        ],
        dtype=torch.float64,
    )


def model_targets(rows: list[dict[str, Any]]) -> torch.Tensor:
    return torch.tensor(
        [[b - a for a, b in zip(r["position"], r["successor"], strict=True)] for r in rows],
        dtype=torch.float64,
    )
