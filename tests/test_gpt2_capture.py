import pytest
import torch

pytest.importorskip("transformers")
from transformers import GPT2Config, GPT2Model

from open_hierarchical_memory import InputError
from open_hierarchical_memory.training import pooled_chunk_kl
from research.gpt2_capture import capture_gpt2, parameter_hash


def model_fixture():
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(71)
        config = GPT2Config(
            vocab_size=43,
            n_positions=64,
            n_embd=12,
            n_layer=2,
            n_head=3,
            attn_pdrop=0.0,
            resid_pdrop=0.0,
            embd_pdrop=0.0,
        )
        config._attn_implementation = "eager"
        model = GPT2Model(config).eval().requires_grad_(False)
    return model


def test_capture_matches_native_eager_outputs_and_is_trainable_as_constant():
    model = model_fixture()
    before = parameter_hash(model)
    tokens = torch.arange(17).reshape(1, 17)
    captured = capture_gpt2(model, tokens, layer=1)
    assert captured.queries.shape == (3, 17, 4)
    assert captured.native_weight_max_abs_error < 3e-6
    assert captured.native_output_max_abs_error < 3e-5
    assert not any(t.is_inference() for t in (captured.queries, captured.keys, captured.values))
    references = captured.queries[:, :3].clone().requires_grad_(True)
    loss = pooled_chunk_kl(
        captured.queries[:, [10, 16]],
        captured.keys,
        references,
        visible_counts=torch.tensor([11, 17]),
        chunk_size=2,
        depth=2,
    )
    loss.backward()
    assert references.grad is not None and torch.isfinite(references.grad).all()
    assert parameter_hash(model) == before
    assert all(p.grad is None for p in model.parameters())


def test_captured_prefix_is_unchanged_by_future_tokens():
    model = model_fixture()
    tokens = torch.arange(17).reshape(1, 17)
    original = capture_gpt2(model, tokens, layer=1)
    tokens[:, 10:] += 11
    changed = capture_gpt2(model, tokens, layer=1)
    for name in ("queries", "keys", "values"):
        torch.testing.assert_close(
            getattr(original, name)[:, :10], getattr(changed, name)[:, :10], rtol=0, atol=0
        )


def test_adapter_rejects_unsupported_state_and_removes_hooks_on_failure(monkeypatch):
    model = model_fixture()
    tokens = torch.arange(17).reshape(1, 17)
    model.train()
    with pytest.raises(InputError):
        capture_gpt2(model, tokens, layer=1)
    model.eval()
    model.h[1].attn.scale_attn_by_inverse_layer_idx = True
    with pytest.raises(InputError):
        capture_gpt2(model, tokens, layer=1)
    model.h[1].attn.scale_attn_by_inverse_layer_idx = False

    def fail(*args, **kwargs):
        raise RuntimeError("injected model failure")

    monkeypatch.setattr(model, "forward", fail)
    with pytest.raises(RuntimeError, match="injected"):
        capture_gpt2(model, tokens, layer=1)
    assert not model.h[1].attn.c_attn._forward_hooks
    assert not model.h[1].attn.c_proj._forward_pre_hooks
