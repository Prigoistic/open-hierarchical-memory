import pytest
import torch

from open_hierarchical_memory import TreeConfig
from research.fitting import TraceExample
from research.metrics import aggregate, evaluate_routes
from research.prepare_gpt2 import download_book

BODY = b"*** START OF THE PROJECT GUTENBERG EBOOK EXAMPLE ***\nActual text.\n*** END OF THE PROJECT GUTENBERG EBOOK EXAMPLE ***"


class Response:
    def __init__(self, data, status=200):
        self.data, self.status = data, status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.data[:limit]


def test_download_retries_invalid_transfers_but_only_returns_valid_content(monkeypatch):
    responses = iter([Response(b"partial"), Response(b"<html>blocked</html>"), Response(BODY)])
    monkeypatch.setattr(
        "research.prepare_gpt2.urllib.request.urlopen", lambda *args, **kwargs: next(responses)
    )
    assert download_book("https://example.invalid/text") == BODY


def test_invalid_or_partial_http_transfers_fail_after_bounded_attempts(monkeypatch):
    calls = []

    def partial(*args, **kwargs):
        calls.append(1)
        return Response(BODY, status=206)

    monkeypatch.setattr("research.prepare_gpt2.urllib.request.urlopen", partial)
    with pytest.raises(ValueError, match="HTTP 200"):
        download_book("https://example.invalid/text")
    assert len(calls) == 3


def test_uniform_attention_measurements_match_closed_form():
    q = torch.zeros((1, 17, 2), dtype=torch.float64)
    sample = TraceExample("uniform-fixture", 0, q, q.clone(), q.clone())
    refs = torch.zeros((1, 2, 2), dtype=torch.float64)
    records = evaluate_routes([sample], refs, (0, 8, 16), TreeConfig(chunk_size=2, depth=2), 0.5)
    for record in records:
        assert record["retained_mass"] == pytest.approx(record["selected_key_fraction"], abs=1e-12)
        assert record["attention_l2_error"] == 0
        if record["visible_keys"] > 1:
            assert record["retained_non_sink_mass"] == pytest.approx(
                (record["selected_keys"] - 1) / (record["visible_keys"] - 1), abs=1e-12
            )
        else:
            assert record["retained_non_sink_mass"] is None
    exact = evaluate_routes([sample], refs, (0, 8, 16), TreeConfig(chunk_size=2, depth=2), 1.0)
    assert aggregate(exact)["retained_mass"]["mean"] == pytest.approx(1.0)
    assert aggregate(exact)["selected_key_fraction"]["mean"] == 1.0
