"""Owned read-only KV snapshots and recursively compressed key trees."""

import hashlib
import json
from dataclasses import asdict, dataclass

import torch
from torch import Tensor

from .contracts import InputError, NodeId, NodeSpan, ResourceLimitError, SnapshotInfo, TreeConfig
from .summaries import AffineSummary, merge, require_tensor, summarize


@dataclass(frozen=True)
class _Node:
    span: NodeSpan
    summary: AffineSummary


Levels = tuple[tuple[_Node, ...], ...]


class KVSnapshot:
    """Inference-only owned snapshot. Public methods never expose tensor aliases.

    References [Hkv,R,D] are shared across batch entries, as model parameters
    would be. Raw keys/values have [B,Hkv,N,D/Dv]. There is no positional
    transformation, persistence, append operation or mutable cache interface.
    Private underscored state is not a supported external mutation interface.
    """

    @torch.no_grad()
    def __init__(
        self, keys: Tensor, values: Tensor, references: Tensor, *, config: TreeConfig | None = None
    ) -> None:
        if config is not None and not isinstance(config, TreeConfig):
            raise InputError("config must be a TreeConfig")
        config = config if config is not None else TreeConfig()
        require_tensor("keys", keys, 4)
        require_tensor("values", values, 4)
        require_tensor("references", references, 3)
        if keys.shape[:3] != values.shape[:3]:
            raise InputError("keys and values must have matching batch/head/sequence dimensions")
        batch, heads, count, dim = keys.shape
        if references.shape[0] != heads or references.shape[-1] != dim:
            raise InputError("reference heads and dimensions must match keys")
        refs = references.shape[1]
        per_level: list[int] = []
        full = count - 1  # key zero is an independent, mandatory sink
        for _ in range(config.depth):
            full //= config.chunk_size
            per_level.append(full)
        total_nodes = sum(per_level) * batch
        if total_nodes > config.max_nodes:
            raise ResourceLimitError("snapshot node budget exceeded")
        raw_bytes = sum(t.numel() * t.element_size() for t in (keys, values, references))
        owned_bytes = raw_bytes + total_nodes * heads * refs * (dim + 1) * 8
        if owned_bytes > config.max_snapshot_tensor_bytes:
            raise ResourceLimitError("snapshot owned-tensor budget exceeded")
        self._keys = keys.detach().clone(memory_format=torch.contiguous_format)
        self._values = values.detach().clone(memory_format=torch.contiguous_format)
        self._references = references.detach().clone(memory_format=torch.contiguous_format)
        self._config = config
        digest = hashlib.sha256()
        digest.update(
            json.dumps({"formula": "nope-v1", "config": asdict(config)}, sort_keys=True).encode()
        )
        for tensor in (self._keys, self._values, self._references):
            digest.update(json.dumps(list(tensor.shape)).encode())
            digest.update(tensor.numpy().tobytes())
        self._trees = tuple(self._build(batch_index, per_level) for batch_index in range(batch))
        spans = tuple(node.span for level in self._trees[0] for node in level)
        self._info = SnapshotInfo(
            digest.hexdigest(),
            batch,
            heads,
            count,
            dim,
            values.shape[-1],
            refs,
            config,
            spans,
            owned_bytes,
        )

    def _build(self, batch: int, counts: list[int]) -> Levels:
        chunk = self._config.chunk_size
        levels: list[tuple[_Node, ...]] = []
        for level, count in enumerate(counts, start=1):
            nodes: list[_Node] = []
            for index in range(count):
                if level == 1:
                    start, stop = 1 + index * chunk, 1 + (index + 1) * chunk
                    compressed = summarize(self._keys[batch, :, start:stop], self._references)
                else:
                    children = levels[-1][index * chunk : (index + 1) * chunk]
                    start, stop = children[0].span.start, children[-1].span.stop
                    compressed = merge(tuple(child.summary for child in children), self._references)
                nodes.append(_Node(NodeSpan(NodeId(level, index), start, stop), compressed))
            levels.append(tuple(nodes))
        return tuple(levels)

    @property
    def info(self) -> SnapshotInfo:
        return self._info

    def node_summary(self, batch: int, node_id: NodeId) -> AffineSummary:
        """Return independent copies for inspection, never live index storage."""
        if type(batch) is not int or not 0 <= batch < self.info.batch_size:
            raise InputError("invalid batch index")
        if not isinstance(node_id, NodeId):
            raise InputError("node_id must be a NodeId")
        if type(node_id.level) is not int or not 1 <= node_id.level <= self._config.depth:
            raise InputError("invalid node level")
        level = self._trees[batch][node_id.level - 1]
        if type(node_id.index) is not int or not 0 <= node_id.index < len(level):
            raise InputError("invalid node index")
        summary = level[node_id.index].summary
        return AffineSummary(summary.means.clone(), summary.biases.clone())
