import pytest
import torch
from hypothesis import given, settings
from hypothesis import strategies as st

from open_hierarchical_memory import (
    ExecutionMode,
    InputError,
    NodeId,
    NumericalError,
    QueryBudget,
    ResourceLimitError,
    TreeConfig,
)
from research.batched_execution import BatchedHierarchicalIndex
from tests import oracle
from tests.test_core import fixture


def make(seed=7, count=67, chunk=3, depth=3, **kw):
    reference, keys, values, refs, queries, visible = fixture(seed, count, chunk, depth)
    batch = BatchedHierarchicalIndex(keys, values, refs, config=reference.info.config, **kw)
    return reference, batch, keys, values, refs, queries, visible


@settings(max_examples=60, derandomize=True, deadline=None)
@given(
    seed=st.integers(0, 10000),
    count=st.integers(1, 90),
    chunk=st.integers(2, 5),
    depth=st.integers(1, 4),
    p=st.sampled_from([0.43, 0.73, 0.95, 1.0]),
)
def test_batched_sparse_routes_and_outputs_match_independent_oracle(seed, count, chunk, depth, p):
    reference, batch, keys, values, refs, queries, visible = make(seed, count, chunk, depth)
    expected = reference.attend(
        queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=p
    )
    actual = batch.attend(
        queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=p
    )
    assert actual.engine == "batched"
    assert actual.routes == expected.routes
    assert actual.scored_summary_slots == sum(r.scored_nodes for r in expected.routes)
    assert actual.selected_key_slots == sum(len(r.selected_ids) for r in expected.routes)
    assert actual.ordering_slots >= actual.scored_summary_slots
    assert actual.attention_softmax_slots >= actual.selected_key_slots
    torch.testing.assert_close(actual.output, expected.output, atol=1e-10, rtol=1e-9)
    for route in actual.routes:
        b, h, t = route.batch, route.query_head, route.query_index
        ids, _ = oracle.route(
            queries[b, h, t].tolist(),
            keys[b, h // 2].tolist(),
            refs[h // 2].tolist(),
            chunk,
            depth,
            route.visible_count,
            p,
        )
        assert route.selected_ids == ids
        wanted = oracle.attention(
            queries[b, h, t].tolist(), keys[b, h // 2].tolist(), values[b, h // 2].tolist(), ids
        )
        torch.testing.assert_close(
            actual.output[b, h, t], torch.tensor(wanted, dtype=torch.float64), atol=1e-10, rtol=1e-9
        )


@pytest.mark.parametrize("count", [1, 2, 4, 5, 8, 9, 16, 17, 18, 63, 64, 65])
def test_batched_boundaries_and_uniform_score_ties(count):
    keys = torch.zeros((2, 2, count, 3), dtype=torch.float64)
    values = torch.arange(2 * 2 * count * 2, dtype=torch.float64).reshape(2, 2, count, 2)
    refs = torch.zeros((2, 3, 3), dtype=torch.float64)
    queries = torch.zeros((2, 4, 3, 3), dtype=torch.float64)
    visible = torch.tensor([[1, max(1, count // 2), count]] * 2)
    index = BatchedHierarchicalIndex(keys, values, refs, config=TreeConfig(chunk_size=2, depth=4))
    actual = index.attend(
        queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=0.73
    )
    expected = index._reference.attend(
        queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=0.73
    )
    assert actual.routes == expected.routes
    torch.testing.assert_close(actual.output, expected.output, atol=1e-10, rtol=1e-9)


def test_batched_ownership_prefix_and_independent_output_storage():
    _, batch, keys, values, refs, queries, _ = make(count=129, chunk=4, depth=3)
    visible = torch.full((2, 3), 18, dtype=torch.int64)
    before = batch.attend(
        queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=0.43
    )
    changed_keys, changed_values = keys.clone(), values.clone()
    changed_keys[:, :, 18:] *= 1000
    changed_values[:, :, 18:] += 10000
    changed = BatchedHierarchicalIndex(changed_keys, changed_values, refs, config=batch.info.config)
    after = changed.attend(
        queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=0.43
    )
    assert before.routes == after.routes
    torch.testing.assert_close(before.output, after.output, atol=0, rtol=0)
    keys.fill_(900)
    values.fill_(123)
    refs.fill_(600)
    inspection = batch.node_summary(0, NodeId(1, 0))
    inspection.means.zero_()
    again = batch.attend(
        queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=0.43
    )
    torch.testing.assert_close(again.output, before.output, atol=0, rtol=0)
    before.output.zero_()
    last = batch.attend(
        queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=0.43
    )
    torch.testing.assert_close(last.output, again.output, atol=0, rtol=0)


def test_batched_batch_permutation_and_single_sample_invariance():
    _, batch, keys, values, refs, queries, visible = make(count=47)
    whole = batch.attend(
        queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=0.73
    )
    permuted = BatchedHierarchicalIndex(
        keys.flip(0), values.flip(0), refs, config=batch.info.config
    ).attend(
        queries.flip(0),
        visible_counts=visible.flip(0),
        mode=ExecutionMode.PAPER_APPROXIMATE,
        p=0.73,
    )
    torch.testing.assert_close(whole.output, permuted.output.flip(0), atol=1e-10, rtol=1e-9)
    for b in range(2):
        result = BatchedHierarchicalIndex(
            keys[b : b + 1], values[b : b + 1], refs, config=batch.info.config
        ).attend(
            queries[b : b + 1],
            visible_counts=visible[b : b + 1],
            mode=ExecutionMode.PAPER_APPROXIMATE,
            p=0.73,
        )
        torch.testing.assert_close(result.output, whole.output[b : b + 1], atol=1e-10, rtol=1e-9)


def test_batched_p1_still_scores_nodes_and_retains_underflowed_keys():
    keys = torch.tensor([0.0, 0.0, 0.0, -1000.0, -1000.0], dtype=torch.float64).reshape(1, 1, 5, 1)
    index = BatchedHierarchicalIndex(
        keys,
        keys.clone(),
        torch.ones((1, 1, 1), dtype=torch.float64),
        config=TreeConfig(chunk_size=2, depth=2),
    )
    result = index.attend(
        torch.ones((1, 1, 1, 1), dtype=torch.float64),
        visible_counts=torch.tensor([[5]]),
        mode=ExecutionMode.PAPER_APPROXIMATE,
        p=1,
    )
    assert result.routes[0].selected_ids == (0, 1, 2, 3, 4)
    assert result.scored_summary_slots == 3


def test_reference_dispatch_is_explicit_for_dense_trace_and_custom_budgets():
    reference, batch, _, _, _, queries, visible = make()
    for kw in [
        dict(mode=ExecutionMode.DENSE),
        dict(mode=ExecutionMode.PAPER_APPROXIMATE, collect_trace=True),
        dict(
            mode=ExecutionMode.PAPER_APPROXIMATE,
            budget=QueryBudget(max_scored_nodes=1),
            allow_dense_fallback=True,
        ),
    ]:
        actual = batch.attend(queries, visible_counts=visible, **kw)
        expected = reference.attend(queries, visible_counts=visible, **kw)
        assert actual.engine == "reference"
        assert actual.routes == expected.routes
        torch.testing.assert_close(actual.output, expected.output, atol=0, rtol=0)
    with pytest.raises(ResourceLimitError):
        batch.attend(
            queries,
            visible_counts=visible,
            mode=ExecutionMode.PAPER_APPROXIMATE,
            budget=QueryBudget(max_attention_pairs=1),
        )


@pytest.mark.parametrize(
    "limit", ["max_scored_nodes", "max_attention_pairs", "max_output_tensor_bytes"]
)
def test_batched_fast_path_enforces_whole_call_default_limits(monkeypatch, limit):
    _, batch, _, _, _, queries, visible = make()
    monkeypatch.setattr("research.batched_execution.QueryBudget", lambda: QueryBudget(**{limit: 1}))
    with pytest.raises(ResourceLimitError):
        batch.attend(queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE)


def test_batched_reports_duplicate_storage_and_enforces_stage_budget():
    reference, batch, keys, values, refs, queries, visible = make()
    assert batch.info.owned_tensor_bytes > reference.info.owned_tensor_bytes
    config = TreeConfig(
        chunk_size=3, depth=3, max_snapshot_tensor_bytes=reference.info.owned_tensor_bytes
    )
    with pytest.raises(ResourceLimitError, match="additional packed"):
        BatchedHierarchicalIndex(keys, values, refs, config=config)
    tiny = BatchedHierarchicalIndex(
        keys, values, refs, config=reference.info.config, max_stage_tensor_bytes=1
    )
    with pytest.raises(ResourceLimitError, match="stage tensor"):
        tiny.attend(queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE)


@pytest.mark.parametrize("bad", [True, 0, -0.1, 1.1, float("nan"), float("inf")])
def test_batched_rejects_invalid_threshold(bad):
    _, batch, _, _, _, queries, visible = make(count=3)
    with pytest.raises(InputError):
        batch.attend(queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=bad)


def test_batched_rejects_invalid_inputs_and_nonfinite_queries():
    _, batch, _, _, _, queries, visible = make(count=3)
    for counts in [visible.float(), visible * 0, visible + 100, visible[:, :1]]:
        with pytest.raises(InputError):
            batch.attend(queries, visible_counts=counts, mode=ExecutionMode.PAPER_APPROXIMATE)
    with pytest.raises(InputError):
        batch.attend(queries.float(), visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE)
    queries[0, 0, 0, 0] = float("nan")
    with pytest.raises(NumericalError):
        batch.attend(queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE)
