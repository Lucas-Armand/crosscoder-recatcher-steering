#!/usr/bin/env python3
"""
Transparent dual-model CrossCoder intervention runner.

Two intervention modes are supported. ``crosscoder_scaled`` preserves the
historical dual-model intervention:

    h_target' = h_target + alpha * z_j * decoder_target[:, j]

``traditional`` applies the decoder direction directly:

    h_target' = h_target + alpha * decoder_target[:, j]

Traditional steering does not require a reference-model forward. By default it
modifies only the last token, whose hidden state predicts the next token.

Important control behavior:
    alpha == 0 runs the target model without a hook, without CrossCoder
    computation, and without loading/running the reference model.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    PreTrainedTokenizerFast,
)

from crosscoder_common import read_jsonl, write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--model-a-id", required=True)
    parser.add_argument("--model-b-id", required=True)
    parser.add_argument("--target-side", choices=["a", "b"], required=True)
    parser.add_argument("--layer", type=int, required=True)
    parser.add_argument("--feature-id", type=int, required=True)
    parser.add_argument(
        "--per-example-direction-npz", type=Path, default=None,
        help=(
            "Optional archive with task_ids and directions [examples, hidden]. "
            "Overrides the CrossCoder decoder direction per input task."
        ),
    )
    parser.add_argument("--alpha", type=float, required=True)
    parser.add_argument(
        "--intervention-mode",
        choices=["crosscoder_scaled", "traditional"],
        default="crosscoder_scaled",
    )
    parser.add_argument(
        "--token-scope",
        choices=["all", "last_token"],
        default="all",
        help=(
            "Hidden-token positions modified in each forward. "
            "Use last_token for autoregressive traditional steering."
        ),
    )
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--max-examples", type=int, default=None)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument(
        "--generation-backend",
        choices=["manual", "hf_generate"],
        default="manual",
        help=(
            "Use hf_generate to match datasets captured with Transformers "
            "model.generate(use_cache=True). This backend currently supports "
            "traditional steering only."
        ),
    )
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--device-a", default="cuda:0")
    parser.add_argument("--device-b", default="cuda:1")
    parser.add_argument(
        "--dtype",
        choices=["float16", "bfloat16", "float32", "nf4"],
        default="float16",
    )
    parser.add_argument("--trust-remote-code", action="store_true")
    parser.add_argument(
        "--tokenizer-id",
        default=None,
        help=(
            "Shared tokenizer used for generation. Defaults to the target "
            "model tokenizer. The produced IDs must be valid for both models "
            "when alpha is non-zero."
        ),
    )
    parser.add_argument(
        "--debug-hook",
        action="store_true",
        help="Print hook tensor shapes/devices once per example.",
    )
    return parser.parse_args()


def get_layers(model: torch.nn.Module):
    candidates = [
        ("model", "layers"),
        ("transformer", "h"),
        ("gpt_neox", "layers"),
    ]

    for parent_name, child_name in candidates:
        parent = getattr(model, parent_name, None)
        layers = (
            getattr(parent, child_name, None)
            if parent is not None
            else None
        )
        if layers is not None:
            return layers

    raise AttributeError("Could not find transformer layers on model")


def post_layer_hidden(
    model: torch.nn.Module,
    input_ids: torch.Tensor,
    attention_mask: torch.Tensor,
    layer: int,
) -> torch.Tensor:
    with torch.inference_mode():
        out = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
            use_cache=False,
            return_dict=True,
        )

    hidden_states = out.hidden_states
    if hidden_states is None:
        raise RuntimeError("Reference model returned no hidden states")

    index = layer + 1
    if not 0 <= index < len(hidden_states):
        raise IndexError(
            f"Requested layer {layer}, but model returned "
            f"{len(hidden_states)} hidden-state tensors"
        )

    return hidden_states[index]


def sample_next_token(
    logits: torch.Tensor,
    temperature: float,
    top_p: float,
) -> torch.Tensor:
    if temperature <= 0:
        return torch.argmax(logits, dim=-1, keepdim=True)

    if not 0 < top_p <= 1:
        raise ValueError("--top-p must be in (0, 1]")

    probs = torch.softmax(logits / temperature, dim=-1)
    sorted_probs, sorted_indices = torch.sort(
        probs,
        descending=True,
        dim=-1,
    )
    cumulative = torch.cumsum(sorted_probs, dim=-1)
    mask = cumulative > top_p
    mask[..., 1:] = mask[..., :-1].clone()
    mask[..., 0] = False

    sorted_probs = sorted_probs.masked_fill(mask, 0)
    denominator = sorted_probs.sum(dim=-1, keepdim=True)

    if torch.any(denominator <= 0):
        raise RuntimeError("Top-p filtering produced zero probability mass")

    sorted_probs = sorted_probs / denominator
    sampled = torch.multinomial(sorted_probs, num_samples=1)
    return sorted_indices.gather(-1, sampled)


def resolve_prompt(row: dict[str, Any], row_index: int) -> str:
    prompt = (
        row.get("prompt")
        or row.get("instruction")
        or row.get("question")
    )

    if not isinstance(prompt, str) or not prompt.strip():
        raise KeyError(
            f"Input row {row_index} has no usable prompt. "
            f"Available keys: {sorted(row.keys())}"
        )

    return prompt


def validate_rows(
    input_jsonl: Path,
    max_examples: int | None,
) -> list[dict[str, Any]]:
    rows = read_jsonl(input_jsonl)

    if max_examples is not None:
        rows = rows[:max_examples]

    if not rows:
        raise ValueError(f"Input file is empty: {input_jsonl}")

    for index, row in enumerate(rows):
        resolve_prompt(row, index)

    return rows


def main() -> None:
    args = parse_args()

    if args.max_new_tokens <= 0:
        raise ValueError("--max-new-tokens must be positive")

    rows = validate_rows(args.input_jsonl, args.max_examples)

    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    dtype = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
        "nf4": torch.float16,
    }[args.dtype]

    target_model_id = (
        args.model_a_id
        if args.target_side == "a"
        else args.model_b_id
    )
    target_device = (
        args.device_a
        if args.target_side == "a"
        else args.device_b
    )
    reference_model_id = (
        args.model_b_id
        if args.target_side == "a"
        else args.model_a_id
    )
    reference_device = (
        args.device_b
        if args.target_side == "a"
        else args.device_a
    )
    needs_reference = (
        args.alpha != 0.0
        and args.intervention_mode == "crosscoder_scaled"
    )

    tokenizer_id = args.tokenizer_id or target_model_id
    if "deepseek" in tokenizer_id.lower():
        # Match run_recatcher_benchmarks.py exactly. AutoTokenizer has routed
        # this repository through an incompatible Llama tokenizer in some
        # environments, changing code whitespace and therefore token IDs.
        tokenizer = PreTrainedTokenizerFast.from_pretrained(
            tokenizer_id,
            trust_remote_code=args.trust_remote_code,
            bos_token="<｜begin▁of▁sentence｜>",
            eos_token="<｜end▁of▁sentence｜>",
            pad_token="<｜end▁of▁sentence｜>",
        )
    else:
        tokenizer = AutoTokenizer.from_pretrained(
            tokenizer_id,
            trust_remote_code=args.trust_remote_code,
            use_fast=True,
        )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    tokenizer.padding_side = "left"

    checkpoint = torch.load(
        args.checkpoint,
        map_location="cpu",
        weights_only=False,
    )
    if "model_state_dict" not in checkpoint:
        raise KeyError(
            f"{args.checkpoint}: missing model_state_dict"
        )

    state = checkpoint["model_state_dict"]
    required = {
        "encoder.weight",
        "encoder.bias",
        "decoder_a.weight",
        "decoder_b.weight",
    }
    missing = required - set(state)
    if missing:
        raise KeyError(
            f"{args.checkpoint}: missing checkpoint tensors "
            f"{sorted(missing)}"
        )

    encoder_weight_cpu = state["encoder.weight"].float()
    encoder_bias_cpu = state["encoder.bias"].float()
    decoder_key = (
        "decoder_a.weight"
        if args.target_side == "a"
        else "decoder_b.weight"
    )
    decoder_weight_cpu = state[decoder_key].float()

    latent_dim = encoder_weight_cpu.shape[0]
    if encoder_bias_cpu.shape != (latent_dim,):
        raise ValueError(
            "Encoder bias shape mismatch: "
            f"weight={tuple(encoder_weight_cpu.shape)}, "
            f"bias={tuple(encoder_bias_cpu.shape)}"
        )
    if decoder_weight_cpu.ndim != 2:
        raise ValueError(
            f"{decoder_key} must be 2D, got "
            f"{tuple(decoder_weight_cpu.shape)}"
        )
    if decoder_weight_cpu.shape[1] != latent_dim:
        raise ValueError(
            "Decoder latent width mismatch: "
            f"encoder={latent_dim}, "
            f"decoder={decoder_weight_cpu.shape[1]}"
        )
    if not 0 <= args.feature_id < latent_dim:
        raise ValueError(
            f"feature-id={args.feature_id} outside "
            f"[0, {latent_dim - 1}]"
        )

    print(
        json.dumps(
            {
                "target_model_id": target_model_id,
                "reference_model_id": (
                    reference_model_id
                    if needs_reference
                    else None
                ),
                "tokenizer_id": tokenizer_id,
                "target_side": args.target_side,
                "layer": args.layer,
                "feature_id": args.feature_id,
                "alpha": args.alpha,
                "intervention_mode": args.intervention_mode,
                "token_scope": args.token_scope,
                "encoder_weight_shape": list(
                    encoder_weight_cpu.shape
                ),
                "decoder_weight_shape": list(
                    decoder_weight_cpu.shape
                ),
                "n_input_examples": len(rows),
            },
            indent=2,
        ),
        flush=True,
    )

    quantization_config = (
        BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        if args.dtype == "nf4" else None
    )
    target_load_args = {
        "torch_dtype": dtype,
        "trust_remote_code": args.trust_remote_code,
    }
    if quantization_config is not None:
        target_load_args.update({
            "quantization_config": quantization_config,
            "device_map": {"": target_device},
            "low_cpu_mem_usage": True,
            "attn_implementation": "eager",
        })
    target_model = AutoModelForCausalLM.from_pretrained(
        target_model_id, **target_load_args,
    )
    if quantization_config is None:
        target_model = target_model.to(target_device)
    target_model = target_model.eval()

    target_layers = get_layers(target_model)
    if not 0 <= args.layer < len(target_layers):
        raise IndexError(
            f"layer={args.layer} outside target layer range "
            f"[0, {len(target_layers) - 1}]"
        )

    target_hidden_size = (
        target_model.get_input_embeddings().embedding_dim
    )
    if decoder_weight_cpu.shape[0] != target_hidden_size:
        raise ValueError(
            "Decoder output width does not match target hidden size: "
            f"decoder={decoder_weight_cpu.shape[0]}, "
            f"target={target_hidden_size}"
        )

    reference_model = None
    encoder_weight = None
    encoder_bias = None
    decoder_direction = None
    per_example_directions = None
    if args.per_example_direction_npz is not None:
        archive = np.load(args.per_example_direction_npz)
        task_ids = [str(value) for value in archive["task_ids"].tolist()]
        directions = np.asarray(archive["directions"], dtype=np.float32)
        if directions.ndim != 2 or directions.shape[1] != target_hidden_size:
            raise ValueError(
                "per-example directions must be [tasks, target_hidden_size], "
                f"got {directions.shape}"
            )
        if len(task_ids) != len(directions) or len(set(task_ids)) != len(task_ids):
            raise ValueError("per-example direction task IDs are missing or duplicated")
        norms = np.linalg.norm(directions, axis=1)
        if not np.isfinite(directions).all() or np.any(norms <= 0):
            raise ValueError("per-example directions must be finite and nonzero")
        directions = directions / norms[:, None]
        per_example_directions = dict(zip(task_ids, directions))

    if needs_reference:
        reference_load_args = dict(target_load_args)
        if quantization_config is not None:
            reference_load_args["device_map"] = {"": reference_device}
        reference_model = AutoModelForCausalLM.from_pretrained(
            reference_model_id, **reference_load_args,
        )
        if quantization_config is None:
            reference_model = reference_model.to(reference_device)
        reference_model = reference_model.eval()

        reference_hidden_size = (
            reference_model.get_input_embeddings().embedding_dim
        )
        expected_encoder_width = (
            target_hidden_size + reference_hidden_size
        )
        if encoder_weight_cpu.shape[1] != expected_encoder_width:
            raise ValueError(
                "CrossCoder encoder input width mismatch: "
                f"checkpoint={encoder_weight_cpu.shape[1]}, "
                f"expected={expected_encoder_width}"
            )

        encoder_weight = encoder_weight_cpu.to(
            target_device,
            dtype=torch.float32,
        )
        encoder_bias = encoder_bias_cpu.to(
            target_device,
            dtype=torch.float32,
        )
    if args.alpha != 0.0:
        decoder_direction = decoder_weight_cpu[:, args.feature_id].to(
            target_device, dtype=dtype
        )

    target_vocab = (
        target_model.get_input_embeddings().num_embeddings
    )
    reference_vocab = (
        reference_model.get_input_embeddings().num_embeddings
        if reference_model is not None
        else None
    )

    outputs: list[dict[str, Any]] = []
    overall_start = time.perf_counter()

    for example_idx, row in enumerate(rows):
        # Re-seed per solution so alpha arms remain paired even when an earlier
        # arm reaches EOS at a different decoding step.
        example_seed = int(row.get("seed", args.seed + example_idx))
        torch.manual_seed(example_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(example_seed)
        prompt = resolve_prompt(row, example_idx)
        if per_example_directions is not None and args.alpha != 0.0:
            task_id = str(row.get("task_id", ""))
            if task_id not in per_example_directions:
                raise KeyError(f"no per-example direction for {task_id}")
            decoder_direction = torch.from_numpy(
                per_example_directions[task_id]
            ).to(target_device, dtype=dtype)
        encoded = tokenizer(prompt, return_tensors="pt")
        input_ids_cpu = encoded["input_ids"]

        max_token_id = int(input_ids_cpu.max())
        if max_token_id >= target_vocab:
            raise ValueError(
                f"Input token ID {max_token_id} exceeds target "
                f"vocabulary size {target_vocab}"
            )
        if (
            reference_vocab is not None
            and max_token_id >= reference_vocab
        ):
            raise ValueError(
                f"Input token ID {max_token_id} exceeds reference "
                f"vocabulary size {reference_vocab}"
            )

        # Keep the authoritative token sequence on CPU. Some model/hook
        # combinations may reuse GPU input storage asynchronously; carrying the
        # sequence itself across decoding steps on a model device can therefore
        # corrupt later input IDs. Each forward receives a fresh device copy.
        generated_cpu = input_ids_cpu.clone()
        prompt_len = generated_cpu.shape[1]
        start = time.perf_counter()
        hook_debug_printed = False
        intervention_diagnostics: list[dict[str, float]] = []

        if args.generation_backend == "hf_generate":
            if args.intervention_mode != "traditional":
                raise ValueError(
                    "hf_generate currently supports traditional steering only"
                )

            handle = None
            if args.alpha != 0.0:
                assert decoder_direction is not None

                def hf_traditional_hook(_module, _inputs, output):
                    hidden = output[0] if isinstance(output, tuple) else output
                    token_count = (
                        1 if args.token_scope == "last_token" else hidden.shape[1]
                    )
                    modified = hidden.clone()
                    modified[:, -token_count:, :] += (
                        args.alpha * decoder_direction.view(1, 1, -1)
                    )
                    if isinstance(output, tuple):
                        return (modified, *output[1:])
                    return modified

                handle = target_layers[args.layer].register_forward_hook(
                    hf_traditional_hook
                )

            generate_kwargs = {
                "max_new_tokens": args.max_new_tokens,
                "do_sample": args.temperature > 0,
                "use_cache": True,
                "pad_token_id": tokenizer.pad_token_id,
                "eos_token_id": tokenizer.eos_token_id,
            }
            if args.temperature > 0:
                generate_kwargs.update({
                    "temperature": args.temperature,
                    "top_p": args.top_p,
                })
            try:
                with torch.inference_mode():
                    generated_device = target_model.generate(
                        input_ids=generated_cpu.to(target_device),
                        attention_mask=torch.ones_like(
                            generated_cpu, device=target_device
                        ),
                        **generate_kwargs,
                    )
                generated_cpu = generated_device.detach().to(
                    device="cpu", dtype=torch.long
                )
            finally:
                if handle is not None:
                    handle.remove()

        manual_steps = (
            0 if args.generation_backend == "hf_generate"
            else args.max_new_tokens
        )
        for _step in range(manual_steps):
            target_ids = generated_cpu.to(target_device)
            target_mask = torch.ones_like(
                target_ids,
                device=target_device,
            )

            if args.alpha == 0.0:
                # Exact unmodified control: no reference forward,
                # no hook, no CrossCoder computation.
                with torch.inference_mode():
                    out = target_model(
                        input_ids=target_ids,
                        attention_mask=target_mask,
                        use_cache=False,
                        return_dict=True,
                    )
            else:
                assert decoder_direction is not None

                ref_hidden = None
                if needs_reference:
                    assert reference_model is not None
                    assert encoder_weight is not None
                    assert encoder_bias is not None
                    ref_ids = generated_cpu.to(reference_device)
                    ref_mask = torch.ones_like(
                        ref_ids,
                        device=reference_device,
                    )

                    if int(ref_ids.max()) >= int(reference_vocab):
                        raise ValueError(
                            "A generated token is outside the reference "
                            f"vocabulary: max={int(ref_ids.max())}, "
                            f"vocab={reference_vocab}"
                        )

                    ref_hidden = post_layer_hidden(
                        reference_model,
                        ref_ids,
                        ref_mask,
                        args.layer,
                    ).to(target_device)

                def hook(_module, _inputs, output):
                    nonlocal hook_debug_printed

                    hidden = (
                        output[0]
                        if isinstance(output, tuple)
                        else output
                    )
                    if hidden.ndim != 3:
                        raise ValueError(
                            "Expected hidden shaped [batch, tokens, hidden]"
                        )

                    token_count = (
                        1
                        if args.token_scope == "last_token"
                        else hidden.shape[1]
                    )
                    target_slice = hidden[:, -token_count:, :]
                    paired = None
                    if needs_reference:
                        assert ref_hidden is not None
                        ref_slice = ref_hidden[:, -token_count:, :].to(
                            device=hidden.device,
                            dtype=hidden.dtype,
                        )
                        if args.target_side == "a":
                            paired = torch.cat(
                                [target_slice, ref_slice], dim=-1
                            )
                        else:
                            paired = torch.cat(
                                [ref_slice, target_slice], dim=-1
                            )

                    if args.debug_hook and not hook_debug_printed:
                        print(
                            json.dumps(
                                {
                                    "hidden_shape": list(
                                        hidden.shape
                                    ),
                                    "ref_hidden_shape": list(
                                        ref_hidden.shape
                                    ) if ref_hidden is not None else None,
                                    "paired_shape": (
                                        list(paired.shape)
                                        if paired is not None else None
                                    ),
                                    "encoder_weight_shape": (
                                        list(encoder_weight.shape)
                                        if encoder_weight is not None else None
                                    ),
                                    "encoder_bias_shape": (
                                        list(encoder_bias.shape)
                                        if encoder_bias is not None else None
                                    ),
                                    "decoder_direction_shape": list(
                                        decoder_direction.shape
                                    ),
                                    "hidden_device": str(
                                        hidden.device
                                    ),
                                    "ref_hidden_device": (
                                        str(ref_hidden.device)
                                        if ref_hidden is not None else None
                                    ),
                                    "encoder_device": (
                                        str(encoder_weight.device)
                                        if encoder_weight is not None else None
                                    ),
                                },
                                indent=2,
                            ),
                            flush=True,
                        )
                        hook_debug_printed = True

                    if args.intervention_mode == "traditional":
                        delta = (
                            args.alpha
                            * decoder_direction.view(1, 1, -1)
                        )
                    else:
                        assert paired is not None
                        assert encoder_weight is not None
                        assert encoder_bias is not None
                        z_all = torch.relu(
                            torch.nn.functional.linear(
                                paired.float(),
                                encoder_weight,
                                encoder_bias,
                            )
                        )
                        z = z_all[..., args.feature_id].to(hidden.dtype)
                        delta = (
                            args.alpha
                            * z.unsqueeze(-1)
                            * decoder_direction.view(1, 1, -1)
                        )

                    if args.intervention_mode == "traditional":
                        # Diagnostics use the exact modified positions. The
                        # normalized projection is comparable across features,
                        # while intervention_norm records the native decoder
                        # scale actually applied.
                        with torch.no_grad():
                            direction_norm = torch.linalg.vector_norm(
                                decoder_direction.float()
                            )
                            unit_direction = (
                                decoder_direction.float()
                                / direction_norm.clamp_min(1e-12)
                            )
                            residual_norm = torch.linalg.vector_norm(
                                target_slice.float(), dim=-1
                            ).mean()
                            delta_norm = torch.linalg.vector_norm(
                                delta.float(), dim=-1
                            ).mean()
                            projection_before = (
                                target_slice.float()
                                * unit_direction.view(1, 1, -1)
                            ).sum(dim=-1).mean()
                            projection_after = (
                                (target_slice.float() + delta.float())
                                * unit_direction.view(1, 1, -1)
                            ).sum(dim=-1).mean()
                            intervention_diagnostics.append(
                                {
                                    "residual_norm": float(
                                        residual_norm.item()
                                    ),
                                    "intervention_norm": float(
                                        delta_norm.item()
                                    ),
                                    "intervention_to_residual_ratio": float(
                                        (
                                            delta_norm
                                            / residual_norm.clamp_min(1e-12)
                                        ).item()
                                    ),
                                    "projection_before": float(
                                        projection_before.item()
                                    ),
                                    "projection_after": float(
                                        projection_after.item()
                                    ),
                                }
                            )

                    modified = hidden.clone()
                    modified[:, -token_count:, :] = (
                        target_slice + delta
                    )

                    if isinstance(output, tuple):
                        return (modified, *output[1:])
                    return modified

                handle = target_layers[
                    args.layer
                ].register_forward_hook(hook)

                try:
                    with torch.inference_mode():
                        out = target_model(
                            input_ids=target_ids,
                            attention_mask=target_mask,
                            use_cache=False,
                            return_dict=True,
                        )
                finally:
                    handle.remove()

            next_token = sample_next_token(
                out.logits[:, -1, :],
                args.temperature,
                args.top_p,
            )

            next_token_cpu = next_token.detach().to(
                device="cpu",
                dtype=torch.long,
            )
            next_token_id = int(next_token_cpu.item())
            if not 0 <= next_token_id < target_vocab:
                raise RuntimeError(
                    f"Target generated invalid token ID "
                    f"{next_token_id} for vocab {target_vocab}"
                )
            if (
                reference_vocab is not None
                and not 0 <= next_token_id < reference_vocab
            ):
                raise RuntimeError(
                    f"Target generated token ID {next_token_id} "
                    f"outside reference vocab {reference_vocab}"
                )

            generated_cpu = torch.cat(
                [generated_cpu, next_token_cpu],
                dim=1,
            )

            if (
                tokenizer.eos_token_id is not None
                and next_token_id == tokenizer.eos_token_id
            ):
                break

        elapsed = time.perf_counter() - start
        completion_ids = generated_cpu[0, prompt_len:]
        completion = tokenizer.decode(
            completion_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
        candidate_code = prompt + completion
        try:
            ast.parse(candidate_code)
            syntax_ok = True
            syntax_error = None
        except SyntaxError as exc:
            syntax_ok = False
            syntax_error = f"{type(exc).__name__}: {exc}"

        output_row = dict(row)
        diagnostics_summary = None
        if intervention_diagnostics:
            keys = intervention_diagnostics[0]
            diagnostics_summary = {
                f"{key}_{stat}": value
                for key in keys
                for stat, value in (
                    (
                        "mean",
                        sum(x[key] for x in intervention_diagnostics)
                        / len(intervention_diagnostics),
                    ),
                    (
                        "min",
                        min(x[key] for x in intervention_diagnostics),
                    ),
                    (
                        "max",
                        max(x[key] for x in intervention_diagnostics),
                    ),
                )
            }
            diagnostics_summary["n_intervention_steps"] = len(
                intervention_diagnostics
            )
        output_row.update(
            {
                "completion": completion,
                "prompt": prompt,
                "raw_completion": completion,
                "candidate_code": candidate_code,
                "syntax_ok": syntax_ok,
                "syntax_error": syntax_error,
                "correct": None,
                "error": None,
                "feature_id": args.feature_id,
                "alpha": args.alpha,
                "target_side": args.target_side,
                "target_model_id": target_model_id,
                "reference_model_id": (
                    reference_model_id
                    if needs_reference
                    else None
                ),
                "intervention_mode": args.intervention_mode,
                "token_scope": args.token_scope,
                "generation_backend": args.generation_backend,
                "direction_source": (
                    str(args.per_example_direction_npz)
                    if args.per_example_direction_npz is not None
                    else f"crosscoder_decoder_feature_{args.feature_id}"
                ),
                "max_new_tokens_config": args.max_new_tokens,
                "temperature_config": args.temperature,
                "top_p_config": args.top_p,
                "model_dtype_config": args.dtype,
                "decoder_direction_norm": float(
                    torch.linalg.vector_norm(decoder_direction).item()
                    if decoder_direction is not None else
                    torch.linalg.vector_norm(
                        decoder_weight_cpu[:, args.feature_id]
                    ).item()
                ),
                "intervention_vector_norm": float(
                    abs(args.alpha)
                    * (
                        torch.linalg.vector_norm(decoder_direction).item()
                        if decoder_direction is not None else
                        torch.linalg.vector_norm(
                            decoder_weight_cpu[:, args.feature_id]
                        ).item()
                    )
                ),
                "intervention_diagnostics": diagnostics_summary,
                "tokenizer_id": tokenizer_id,
                "generation_seconds": elapsed,
                "generation_seed": example_seed,
                "generated_tokens": int(
                    completion_ids.numel()
                ),
                "tokens_per_second": (
                    float(completion_ids.numel()) / elapsed
                    if elapsed > 0
                    else math.nan
                ),
            }
        )
        outputs.append(output_row)

        print(
            f"[{example_idx + 1}/{len(rows)}] "
            f"seconds={elapsed:.1f} "
            f"tokens={completion_ids.numel()} "
            f"tok/s={output_row['tokens_per_second']:.3f}",
            flush=True,
        )

        # Atomic checkpoint after each example.
        write_jsonl(args.output_jsonl, outputs)

    total_elapsed = time.perf_counter() - overall_start
    print(
        json.dumps(
            {
                "examples": len(outputs),
                "total_seconds": total_elapsed,
                "seconds_per_example": (
                    total_elapsed / len(outputs)
                    if outputs
                    else None
                ),
                "estimated_seconds_for_100_examples": (
                    100 * total_elapsed / len(outputs)
                    if outputs
                    else None
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
