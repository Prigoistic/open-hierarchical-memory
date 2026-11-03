import dataclasses
import math

import pytest
import torch
from hypothesis import given, settings
from hypothesis import strategies as st

from open_hierarchical_memory import (
    ExecutionMode,
    HierarchicalIndex,
    InputError,
    NodeId,
    NumericalError,
    QueryBudget,
    ResourceLimitError,
    ResultState,
    TreeConfig,
)
from open_hierarchical_memory.summaries import merge, summarize

from . import oracle


def fixture(seed: int = 7, count: int = 67, chunk: int = 3, depth: int = 3):
    generator = torch.Generator().manual_seed(seed)

    def rand(*shape):
        return torch.randn(shape, generator=generator, dtype=torch.float64)

    keys, values, refs = rand(2, 2, count, 3), rand(2, 2, count, 2), rand(2, 3, 3)
    queries = rand(2, 4, 3, 3)
    visible = torch.tensor([[1, max(1, count // 2), count]] * 2, dtype=torch.int64)
    index = HierarchicalIndex(keys, values, refs, config=TreeConfig(chunk_size=chunk, depth=depth))
    return index, keys, values, refs, queries, visible


def assert_matches_literal(seed: int, count: int, chunk: int, depth: int, p: float) -> None:
    index, keys, values, refs, queries, visible = fixture(seed, count, chunk, depth)
    result = index.attend(
        queries,
        visible_counts=visible,
        mode=ExecutionMode.PAPER_APPROXIMATE,
        p=p,
        collect_trace=True,
    )
    for trace in result.routes:
        b, h, t = trace.batch, trace.query_head, trace.query_index
        kv = h // 2
        query = queries[b, h, t].tolist()
        raw_keys = keys[b, kv].tolist()
        selected, steps = oracle.route(
            query, raw_keys, refs[kv].tolist(), chunk, depth, trace.visible_count, p
        )
        assert trace.selected_ids == selected
        actual_steps = [
            (
                step.level,
                tuple(n.index for n in step.candidates),
                tuple(n.index for n in step.selected),
            )
            for step in trace.steps
        ]
        assert actual_steps == steps
        expected = oracle.attention(query, raw_keys, values[b, kv].tolist(), selected)
        torch.testing.assert_close(
            result.output[b, h, t],
            torch.tensor(expected, dtype=torch.float64),
            rtol=1e-9,
            atol=1e-10,
        )
        assert trace.state is ResultState.PAPER_APPROXIMATE
        assert all(i < trace.visible_count for i in trace.selected_ids)


@settings(max_examples=60, derandomize=True, deadline=None)
@given(
    seed=st.integers(0, 10000),
    count=st.integers(1, 90),
    chunk=st.integers(2, 5),
    depth=st.integers(1, 4),
    p=st.sampled_from([0.43, 0.73, 0.95, 1.0]),
)
def test_generated_sparse_route_matches_independent_oracle(seed, count, chunk, depth, p):
    assert_matches_literal(seed, count, chunk, depth, p)


@pytest.mark.parametrize("count", [1, 2, 4, 5, 8, 9, 16, 17, 18, 63, 64, 65])
def test_boundary_and_parentless_chunks(count):
    assert_matches_literal(51, count, 2, 4, 0.73)


def test_literal_sparse_routing_discriminates_heads():
    assert_matches_literal(731, 67, 3, 3, 0.43)


def test_every_node_summary_matches_direct_original_keys():
    index, keys, _, refs, _, _ = fixture(count=83, chunk=3, depth=4)
    for span in index.info.spans:
        for batch in range(2):
            actual = index.node_summary(batch, span.node_id)
            for head in range(2):
                for ref_index in range(3):
                    mean, bias = oracle.summary(
                        keys[batch, head, span.start : span.stop].tolist(),
                        refs[head, ref_index].tolist(),
                    )
                    torch.testing.assert_close(
                        actual.means[head, ref_index],
                        torch.tensor(mean, dtype=torch.float64),
                        rtol=1e-9,
                        atol=1e-10,
                    )
                    assert actual.biases[head, ref_index].item() == pytest.approx(bias, abs=1e-10)


def test_merge_preserves_bias_for_identical_zero_keys():
    keys = torch.zeros((1, 8, 1), dtype=torch.float64)
    refs = torch.zeros((1, 2, 1), dtype=torch.float64)
    result = merge((summarize(keys[:, :4], refs), summarize(keys[:, 4:], refs)), refs)
    torch.testing.assert_close(result.biases, torch.full((1, 2), math.log(8), dtype=torch.float64))


def test_prefix_queries_cannot_see_future_values_or_summaries():
    index, keys, values, refs, queries, _ = fixture(count=129, chunk=4, depth=3)
    visible = torch.full((2, 3), 18, dtype=torch.int64)
    before = index.attend(
        queries,
        visible_counts=visible,
        mode=ExecutionMode.PAPER_APPROXIMATE,
        p=0.43,
        collect_trace=True,
    )
    keys[:, :, 18:] *= 1000
    values[:, :, 18:] += 10000
    changed = HierarchicalIndex(keys, values, refs, config=index.info.config)
    after = changed.attend(
        queries,
        visible_counts=visible,
        mode=ExecutionMode.PAPER_APPROXIMATE,
        p=0.43,
        collect_trace=True,
    )
    torch.testing.assert_close(before.output, after.output, rtol=0, atol=0)
    assert before.routes == after.routes
    assert before.snapshot_id != after.snapshot_id


def test_decode_prefix_mask_is_not_upper_left_rectangular_causality():
    keys = torch.zeros((1, 1, 3, 1), dtype=torch.float64)
    values = torch.tensor([1.0, 2.0, 30.0], dtype=torch.float64).reshape(1, 1, 3, 1)
    index = HierarchicalIndex(keys, values, torch.zeros((1, 1, 1), dtype=torch.float64))
    result = index.attend(
        torch.zeros((1, 1, 1, 1), dtype=torch.float64),
        visible_counts=torch.tensor([[3]]),
        mode=ExecutionMode.DENSE,
    )
    assert result.output.item() == pytest.approx(11.0)


def test_batch_permutation_and_single_sample_invariance():
    index, keys, values, refs, queries, visible = fixture(count=47)
    whole = index.attend(
        queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=0.73
    )
    permuted = HierarchicalIndex(
        keys.flip(0), values.flip(0), refs, config=index.info.config
    ).attend(
        queries.flip(0),
        visible_counts=visible.flip(0),
        mode=ExecutionMode.PAPER_APPROXIMATE,
        p=0.73,
    )
    torch.testing.assert_close(whole.output, permuted.output.flip(0))
    for b in range(2):
        single = HierarchicalIndex(
            keys[b : b + 1], values[b : b + 1], refs, config=index.info.config
        ).attend(
            queries[b : b + 1],
            visible_counts=visible[b : b + 1],
            mode=ExecutionMode.PAPER_APPROXIMATE,
            p=0.73,
        )
        torch.testing.assert_close(whole.output[b : b + 1], single.output)


def test_p1_retains_all_ids_and_still_exercises_tree():
    keys = torch.tensor([0.0, 0.0, 0.0, -1000.0, -1000.0], dtype=torch.float64).reshape(1, 1, 5, 1)
    values = keys.clone()
    refs = torch.ones((1, 1, 1), dtype=torch.float64)
    index = HierarchicalIndex(keys, values, refs, config=TreeConfig(chunk_size=2, depth=2))
    query = torch.ones((1, 1, 1, 1), dtype=torch.float64)
    result = index.attend(
        query,
        visible_counts=torch.tensor([[5]]),
        mode=ExecutionMode.PAPER_APPROXIMATE,
        p=1,
        collect_trace=True,
    )
    assert result.routes[0].selected_ids == (0, 1, 2, 3, 4)
    assert [step.level for step in result.routes[0].steps] == [2, 1]
    assert result.routes[0].scored_nodes == 3
    dense = index.attend(query, visible_counts=torch.tensor([[5]]), mode=ExecutionMode.DENSE)
    torch.testing.assert_close(result.output, dense.output)


def test_owned_snapshot_survives_caller_and_inspection_mutation():
    index, keys, values, refs, queries, visible = fixture(count=67)
    before = index.attend(queries, visible_counts=visible, mode=ExecutionMode.DENSE)
    old_id = index.info.snapshot_id
    keys.fill_(17)
    values.fill_(500)
    refs.fill_(-21)
    inspection = index.node_summary(0, NodeId(1, 0))
    inspection.means.fill_(900)
    inspection.biases.zero_()
    after = index.attend(queries, visible_counts=visible, mode=ExecutionMode.DENSE)
    torch.testing.assert_close(before.output, after.output, rtol=0, atol=0)
    assert old_id == index.info.snapshot_id
    before.output.fill_(123)
    again = index.attend(queries, visible_counts=visible, mode=ExecutionMode.DENSE)
    torch.testing.assert_close(after.output, again.output, rtol=0, atol=0)


def test_resource_failure_is_not_a_successful_partial_result():
    index, _, _, _, queries, visible = fixture(count=67)
    with pytest.raises(ResourceLimitError, match="attention pair"):
        index.attend(
            queries,
            visible_counts=visible,
            mode=ExecutionMode.PAPER_APPROXIMATE,
            budget=QueryBudget(max_attention_pairs=1),
        )
    with pytest.raises(ResourceLimitError, match="route node"):
        index.attend(
            queries,
            visible_counts=visible,
            mode=ExecutionMode.PAPER_APPROXIMATE,
            budget=QueryBudget(max_scored_nodes=1),
        )


def test_dense_fallback_is_explicit_and_matches_same_snapshot():
    index, _, _, _, queries, visible = fixture(count=67)
    result = index.attend(
        queries,
        visible_counts=visible,
        mode=ExecutionMode.PAPER_APPROXIMATE,
        budget=QueryBudget(max_scored_nodes=1),
        allow_dense_fallback=True,
    )
    dense = index.attend(queries, visible_counts=visible, mode=ExecutionMode.DENSE)
    assert any(r.state is ResultState.DENSE_FALLBACK for r in result.routes)
    assert all(r.fallback_reason for r in result.routes if r.state is ResultState.DENSE_FALLBACK)
    for trace in result.routes:
        if trace.state is ResultState.DENSE_FALLBACK:
            torch.testing.assert_close(
                result.output[trace.batch, trace.query_head, trace.query_index],
                dense.output[trace.batch, trace.query_head, trace.query_index],
            )
    with pytest.raises(ResourceLimitError):
        index.attend(
            queries,
            visible_counts=visible,
            mode=ExecutionMode.PAPER_APPROXIMATE,
            budget=QueryBudget(max_scored_nodes=1, max_attention_pairs=1),
            allow_dense_fallback=True,
        )


def test_trace_and_output_budgets_are_enforced():
    index, _, _, _, queries, visible = fixture()
    with pytest.raises(ResourceLimitError, match="trace"):
        index.attend(
            queries,
            visible_counts=visible,
            mode=ExecutionMode.PAPER_APPROXIMATE,
            collect_trace=True,
            budget=QueryBudget(max_trace_nodes=1),
        )
    without_trace = index.attend(
        queries,
        visible_counts=visible,
        mode=ExecutionMode.PAPER_APPROXIMATE,
        budget=QueryBudget(max_trace_nodes=1),
    )
    assert all(not r.steps for r in without_trace.routes)
    with pytest.raises(ResourceLimitError, match="output"):
        index.attend(
            queries,
            visible_counts=visible,
            mode=ExecutionMode.DENSE,
            budget=QueryBudget(max_output_tensor_bytes=1),
        )


@pytest.mark.parametrize("bad", [True, 0, -1, 1.5])
def test_invalid_integer_configs_are_rejected(bad):
    with pytest.raises(InputError):
        TreeConfig(depth=bad)
    with pytest.raises(InputError):
        QueryBudget(max_attention_pairs=bad)


@pytest.mark.parametrize("bad", [True, 0, -0.1, 1.1, float("nan"), float("inf")])
def test_invalid_top_p_is_rejected(bad):
    index, _, _, _, queries, visible = fixture(count=3)
    with pytest.raises(InputError):
        index.attend(queries, visible_counts=visible, mode=ExecutionMode.PAPER_APPROXIMATE, p=bad)


def test_invalid_shapes_modes_visibility_and_backends():
    index, keys, values, refs, queries, visible = fixture(count=3)
    with pytest.raises(InputError, match="ExecutionMode"):
        index.attend(queries, visible_counts=visible, mode="checked_mass")
    for counts in (visible.float(), torch.zeros_like(visible), visible + 100, visible[:, :1]):
        with pytest.raises(InputError):
            index.attend(queries, visible_counts=counts, mode=ExecutionMode.DENSE)
    with pytest.raises(InputError):
        HierarchicalIndex(keys.float(), values.float(), refs.float())
    with pytest.raises(InputError):
        index.attend(queries[:, :3], visible_counts=visible, mode=ExecutionMode.DENSE)
    with pytest.raises(ResourceLimitError):
        HierarchicalIndex(keys, values, refs, config=TreeConfig(max_snapshot_tensor_bytes=1))
    with pytest.raises(ResourceLimitError):
        HierarchicalIndex(
            torch.zeros((1, 1, 40, 1), dtype=torch.float64),
            torch.zeros((1, 1, 40, 1), dtype=torch.float64),
            torch.zeros((1, 1, 1), dtype=torch.float64),
            config=TreeConfig(max_nodes=1),
        )
    with pytest.raises(InputError):
        TreeConfig(chunk_size=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        index.info.config.depth = 2


def test_nonfinite_and_overflow_fail_instead_of_normalizing():
    index, keys, values, refs, queries, visible = fixture(count=3)
    queries[0, 0, 0, 0] = float("nan")
    with pytest.raises(NumericalError):
        index.attend(queries, visible_counts=visible, mode=ExecutionMode.DENSE)
    keys[0, 0, 0, 0] = float("inf")
    with pytest.raises(NumericalError):
        HierarchicalIndex(keys, values, refs)
    huge = torch.full((1, 1, 3, 1), 1e308, dtype=torch.float64)
    with pytest.raises(NumericalError):
        HierarchicalIndex(
            huge,
            huge,
            torch.full((1, 1, 1), 1e308, dtype=torch.float64),
            config=TreeConfig(chunk_size=2),
        )
