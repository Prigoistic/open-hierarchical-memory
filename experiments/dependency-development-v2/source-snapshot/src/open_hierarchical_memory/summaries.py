"""No-RoPE affine key summaries; standalone tensor math with no hidden state."""

import math
from dataclasses import dataclass

import torch
from torch import Tensor

from .contracts import InputError, NumericalError


def require_tensor(name: str, tensor: Tensor, ndim: int) -> None:
    if not isinstance(tensor, Tensor) or tensor.ndim != ndim:
        raise InputError(f"{name} must be a {ndim}-dimensional torch.Tensor")
    if tensor.device.type != "cpu" or tensor.dtype != torch.float64:
        raise InputError(f"{name}: only CPU float64 is supported")
    if tensor.layout != torch.strided or any(size <= 0 for size in tensor.shape):
        raise InputError(f"{name} must be a nonempty strided tensor")
    require_finite(name, tensor)


def require_finite(name: str, tensor: Tensor) -> None:
    if not bool(torch.isfinite(tensor).all()):
        raise NumericalError(f"{name} contains non-finite values")


@dataclass(frozen=True)
class AffineSummary:
    means: Tensor  # [Hkv, R, D]
    biases: Tensor  # [Hkv, R]


def summarize(keys: Tensor, references: Tensor) -> AffineSummary:
    """Summarize keys [Hkv,N,D] at references [Hkv,R,D].

    Output tensors are new allocations. The standalone function preserves
    autograd; immutable inference snapshots separately own detached copies.
    """
    require_tensor("keys", keys, 3)
    require_tensor("references", references, 3)
    if keys.shape[0] != references.shape[0] or keys.shape[2] != references.shape[2]:
        raise InputError("key/reference heads and dimensions must match")
    scores = torch.einsum("hrd,hnd->hrn", references, keys) / math.sqrt(keys.shape[-1])
    require_finite("reference logits", scores)
    log_weights = torch.log_softmax(scores, dim=-1)
    require_finite("reference log weights", log_weights)
    weights = log_weights.exp()
    means = torch.einsum("hrn,hnd->hrd", weights, keys)
    biases = -(weights * log_weights).sum(dim=-1)
    require_finite("summary means", means)
    require_finite("summary biases", biases)
    return AffineSummary(means, biases)


def merge(children: tuple[AffineSummary, ...], references: Tensor) -> AffineSummary:
    """Merge matching reference identities; include inherited child biases."""
    require_tensor("references", references, 3)
    if not children:
        raise InputError("cannot merge an empty child list")
    expected = references.shape
    for child in children:
        require_tensor("child means", child.means, 3)
        require_tensor("child biases", child.biases, 2)
        if child.means.shape != expected or child.biases.shape != expected[:2]:
            raise InputError("all child summaries must match the reference shape")
    means = torch.stack([child.means for child in children])
    biases = torch.stack([child.biases for child in children])
    scores = (means * references.unsqueeze(0)).sum(dim=-1) / math.sqrt(expected[-1]) + biases
    require_finite("merge logits", scores)
    log_weights = torch.log_softmax(scores, dim=0)
    require_finite("merge log weights", log_weights)
    weights = log_weights.exp()
    parent_means = (weights.unsqueeze(-1) * means).sum(dim=0)
    parent_biases = -(weights * log_weights).sum(dim=0) + (weights * biases).sum(dim=0)
    require_finite("merged means", parent_means)
    require_finite("merged biases", parent_biases)
    return AffineSummary(parent_means, parent_biases)
