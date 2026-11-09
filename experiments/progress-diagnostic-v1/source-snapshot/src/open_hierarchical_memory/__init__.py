"""Independent, explicitly approximate hierarchical attention reference."""

from .attention import HierarchicalIndex
from .contracts import (
    AttentionResult,
    ExecutionMode,
    InputError,
    NodeId,
    NumericalError,
    QueryBudget,
    ResourceLimitError,
    ResultState,
    TreeConfig,
)

__all__ = [
    "AttentionResult",
    "ExecutionMode",
    "HierarchicalIndex",
    "InputError",
    "NodeId",
    "NumericalError",
    "QueryBudget",
    "ResourceLimitError",
    "ResultState",
    "TreeConfig",
]
