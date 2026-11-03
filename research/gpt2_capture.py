"""Narrow GPT-2 dynamic-library boundary, checked against native eager attention.

This file deliberately stays outside the dependency-free numerical core.
"""

import hashlib
import math
from dataclasses import dataclass

import torch
from torch import Tensor

from open_hierarchical_memory import InputError, NumericalError


@dataclass(frozen=True)
class CapturedAttention:
    queries: Tensor
    keys: Tensor
    values: Tensor
    native_weight_max_abs_error: float
    native_output_max_abs_error: float


def parameter_hash(model) -> str:
    digest = hashlib.sha256()
    for name, parameter in model.named_parameters():
        if parameter.device.type != "cpu":
            raise InputError("pilot parameter hashing supports CPU only")
        digest.update(name.encode())
        digest.update(str((tuple(parameter.shape), parameter.dtype)).encode())
        digest.update(memoryview(parameter.detach().contiguous().numpy()).cast("B"))
    return digest.hexdigest()


def capture_gpt2(model, token_ids: Tensor, *, layer: int) -> CapturedAttention:
    if model.training or any(parameter.requires_grad for parameter in model.parameters()):
        raise InputError("capture requires an eval-mode, frozen backbone")
    if getattr(model.config, "model_type", None) != "gpt2":
        raise InputError("only the audited GPT-2 architecture is supported")
    if type(layer) is not int or not 0 <= layer < len(model.h):
        raise InputError("invalid GPT-2 layer")
    if (
        token_ids.ndim != 2
        or token_ids.shape[0] != 1
        or token_ids.dtype != torch.int64
        or token_ids.device.type != "cpu"
    ):
        raise InputError("pilot capture requires CPU int64 token IDs [1,T]")
    attention = model.h[layer].attn
    if (
        not attention.scale_attn_weights
        or attention.scale_attn_by_inverse_layer_idx
        or attention.reorder_and_upcast_attn
        or attention.is_cross_attention
    ):
        raise InputError("unsupported attention scaling or cross-attention configuration")
    if model.config._attn_implementation != "eager":
        raise InputError("native eager attention is required for adapter validation")
    captured = {}

    def qkv_hook(_module, _inputs, output):
        captured["qkv"] = output.detach()

    def output_hook(_module, inputs):
        captured["merged_output"] = inputs[0].detach()

    first = attention.c_attn.register_forward_hook(qkv_hook)
    second = attention.c_proj.register_forward_pre_hook(output_hook)
    try:
        with torch.inference_mode():
            result = model(
                input_ids=token_ids, use_cache=False, output_attentions=True, return_dict=True
            )
    finally:
        first.remove()
        second.remove()
    if set(captured) != {"qkv", "merged_output"} or result.attentions[layer] is None:
        raise RuntimeError("native attention capture was incomplete")
    hidden = model.config.n_embd
    heads = model.config.n_head
    if hidden % heads:
        raise InputError("invalid head dimensions")
    length = token_ids.shape[1]
    # Clone outside inference_mode so these constants can participate in a
    # later reference-query backward pass without inference-tensor restrictions.
    pieces = captured["qkv"].split(hidden, dim=-1)
    if len(pieces) != 3:
        raise InputError("unexpected GPT-2 packed QKV layout")
    query, key, value = [
        piece.reshape(1, length, heads, hidden // heads)
        .transpose(1, 2)[0]
        .to(dtype=torch.float64)
        .clone()
        for piece in pieces
    ]
    logits = query @ key.transpose(-2, -1) / math.sqrt(hidden // heads)
    mask = torch.ones((length, length), dtype=torch.bool).tril()
    probabilities = logits.masked_fill(~mask, float("-inf")).softmax(-1)
    observed_weights = result.attentions[layer][0].to(dtype=torch.float64).clone()
    native_outputs = (
        captured["merged_output"]
        .reshape(1, length, heads, hidden // heads)
        .transpose(1, 2)[0]
        .to(dtype=torch.float64)
        .clone()
    )
    reconstructed = probabilities @ value
    weight_error = float((probabilities - observed_weights).abs().max())
    output_error = float((reconstructed - native_outputs).abs().max())
    if not torch.isfinite(reconstructed).all() or weight_error > 3e-6 or output_error > 3e-5:
        raise NumericalError(
            f"native GPT-2 attention mismatch: weights={weight_error}, output={output_error}"
        )
    return CapturedAttention(query, key, value, weight_error, output_error)
