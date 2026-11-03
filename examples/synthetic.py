"""Synthetic, untrained example. Dense metrics are offline verification work."""

import json

import torch

from open_hierarchical_memory import ExecutionMode, HierarchicalIndex, TreeConfig


def main() -> None:
    generator = torch.Generator().manual_seed(42)
    keys = torch.randn((1, 1, 257, 8), generator=generator, dtype=torch.float64)
    values = torch.randn((1, 1, 257, 4), generator=generator, dtype=torch.float64)
    references = torch.randn((1, 8, 8), generator=generator, dtype=torch.float64)
    queries = torch.randn((1, 2, 1, 8), generator=generator, dtype=torch.float64)
    index = HierarchicalIndex(keys, values, references, config=TreeConfig(chunk_size=4, depth=3))
    visible = torch.tensor([[257]], dtype=torch.int64)
    approximate = index.attend(
        queries,
        visible_counts=visible,
        mode=ExecutionMode.PAPER_APPROXIMATE,
        p=0.73,
        collect_trace=True,
    )
    dense = index.attend(queries, visible_counts=visible, mode=ExecutionMode.DENSE)
    observations = []
    for trace in approximate.routes:
        logits = keys[0, 0] @ queries[0, trace.query_head, 0] / 8**0.5
        observed_mass = torch.softmax(logits, dim=0)[list(trace.selected_ids)].sum().item()
        observations.append(
            {
                "query_head": trace.query_head,
                "state": trace.state.value,
                "keys_selected": len(trace.selected_ids),
                "keys_visible": trace.visible_count,
                "summary_nodes_scored": trace.scored_nodes,
                "observed_retained_mass_offline": observed_mass,
                "attention_l2_error_offline": float(
                    torch.linalg.vector_norm(
                        approximate.output[0, trace.query_head, 0]
                        - dense.output[0, trace.query_head, 0]
                    )
                ),
            }
        )
    print(
        json.dumps(
            {
                "fixture": "synthetic untrained random reference queries",
                "runtime_tolerance_guarantee": False,
                "snapshot_id": index.info.snapshot_id,
                "observations": observations,
            },
            indent=2,
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
