"""Explicit supported inputs, immutable metadata and successful result states."""

from dataclasses import dataclass
from enum import StrEnum

from torch import Tensor


class InputError(ValueError):
    """The caller supplied an unsupported or inconsistent input."""


class NumericalError(ArithmeticError):
    """A finite, supported calculation could not be completed numerically."""


class ResourceLimitError(RuntimeError):
    """The declared work or tensor-allocation budget would be exceeded."""


class ExecutionMode(StrEnum):
    DENSE = "dense"
    PAPER_APPROXIMATE = "paper_approximate"


class ResultState(StrEnum):
    DENSE_REFERENCE = "dense_reference"
    PAPER_APPROXIMATE = "paper_approximate"
    DENSE_FALLBACK = "dense_fallback"


def positive_int(name: str, value: int) -> None:
    if type(value) is not int or value <= 0:
        raise InputError(f"{name} must be a positive integer (not a boolean)")


@dataclass(frozen=True)
class TreeConfig:
    chunk_size: int = 4
    depth: int = 3
    max_nodes: int = 100_000
    max_snapshot_tensor_bytes: int = 128 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in ("chunk_size", "depth", "max_nodes", "max_snapshot_tensor_bytes"):
            positive_int(name, getattr(self, name))
        if self.chunk_size < 2:
            raise InputError("chunk_size must be at least 2")
        if self.depth > 32:
            raise InputError("depth above 32 is unsupported")


@dataclass(frozen=True)
class QueryBudget:
    """Whole-call limits, shared across batch entries, query heads and queries.

    Tensor bytes limit final output storage; Python-object/RSS limits are not
    promised. Routing and optional trace work are counted before scoring.
    """

    max_scored_nodes: int = 100_000
    max_attention_pairs: int = 1_000_000
    max_trace_nodes: int = 100_000
    max_output_tensor_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in (
            "max_scored_nodes",
            "max_attention_pairs",
            "max_trace_nodes",
            "max_output_tensor_bytes",
        ):
            positive_int(name, getattr(self, name))


@dataclass(frozen=True, order=True)
class NodeId:
    level: int
    index: int


@dataclass(frozen=True)
class NodeSpan:
    node_id: NodeId
    start: int
    stop: int


@dataclass(frozen=True)
class RouteStep:
    level: int
    candidates: tuple[NodeId, ...]
    scores: tuple[float, ...]
    selected: tuple[NodeId, ...]


@dataclass(frozen=True)
class QueryTrace:
    batch: int
    query_head: int
    query_index: int
    visible_count: int
    state: ResultState
    selected_ids: tuple[int, ...]
    scored_nodes: int
    steps: tuple[RouteStep, ...]
    fallback_reason: str | None = None


@dataclass(frozen=True)
class SnapshotInfo:
    snapshot_id: str
    batch_size: int
    kv_heads: int
    key_count: int
    key_dim: int
    value_dim: int
    reference_count: int
    config: TreeConfig
    spans: tuple[NodeSpan, ...]
    owned_tensor_bytes: int


@dataclass(frozen=True)
class AttentionResult:
    """Output is independently owned; mutating it cannot change the index.

    Each query has its own execution state because a call may mix approximate
    and dense-fallback results. No unimplemented tolerance flag is exposed.
    """

    output: Tensor
    requested_mode: ExecutionMode
    snapshot_id: str
    p: float
    routes: tuple[QueryTrace, ...]
