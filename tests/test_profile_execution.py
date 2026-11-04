import pytest
import torch

from open_hierarchical_memory import ExecutionMode
from research.profile_execution import StageTimer, instrumented_attention
from tests.test_core import fixture


@pytest.mark.parametrize(
    "count,chunk,depth,p", [(1, 2, 2, 0.73), (18, 2, 4, 0.73), (67, 3, 3, 0.43), (129, 4, 3, 1.0)]
)
def test_instrumentation_preserves_exact_outputs_routes_and_trace(count, chunk, depth, p):
    index, _, _, _, queries, visible = fixture(count=count, chunk=chunk, depth=depth)
    timer = StageTimer()
    method = instrumented_attention(timer)
    expected = index.attend(
        queries,
        visible_counts=visible,
        mode=ExecutionMode.PAPER_APPROXIMATE,
        p=p,
        collect_trace=True,
    )
    actual = method(
        index,
        queries,
        visible_counts=visible,
        mode=ExecutionMode.PAPER_APPROXIMATE,
        p=p,
        collect_trace=True,
    )
    assert actual.routes == expected.routes
    torch.testing.assert_close(actual.output, expected.output, atol=0, rtol=0)
    assert timer.rows["attend_total"]["calls"] == 1
    assert timer.rows["attend_total"]["inclusive_ms"] >= timer.rows["attend_total"]["exclusive_ms"]
    assert timer.stack == []


def test_nested_stage_timer_exclusive_accounting_and_exception_cleanup():
    timer = StageTimer()
    with pytest.raises(ValueError):
        with timer.stage("outer"):
            with timer.stage("inner"):
                raise ValueError("expected")
    assert timer.stack == []
    assert timer.rows["outer"]["exclusive_ms"] + timer.rows["inner"][
        "inclusive_ms"
    ] == pytest.approx(timer.rows["outer"]["inclusive_ms"])
