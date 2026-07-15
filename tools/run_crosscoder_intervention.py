#!/usr/bin/env python3
"""
Slow but transparent dual-model intervention runner.

It runs the reference model on the same current prefix, captures its post-layer
hidden state, then runs the target model with a forward hook on the corresponding
layer. The hook computes the paired CrossCoder latent and applies:

    h_target' = h_target + alpha * z_j * decoder_target[:, j]

Therefore alpha=0 is the unmodified control, alpha=-1 removes the decoded
contribution estimated for that feature, and alpha=1 adds one more copy.

This implementation intentionally recomputes both full prefixes every token.
That makes it suitable for smoke tests and timing estimates. Optimize with KV
caches only after validating correctness.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from crosscoder_common import read_jsonl, write_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--model-a-id", required=True)
    parser.add_argument("--model-b-id", required=True)
    parser.add_argument("--target-side", choices=["a", "b"], required=True)
    parser.add_argument("--layer", type=int, required=True)
    parser.add_argument("--feature-id", type=int, required=True)
    parser.add_argument("--alpha", type=float, required=True)
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--max-examples", type=int, default=None)
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--seed", type=int, default=1000)
    parser.add_argument("--device-a", default="cuda:0")
    parser.add_argument("--device-b", default="cuda:1")
    parser.add_argument("--dtype", choices=["float16", "bfloat16", "float32"], default="float16")
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def get_layers(model: torch.nn.Module):
    candidates = [
        ("model", "layers"),
        ("transformer", "h"),
        ("gpt_neox", "layers"),
    ]
    for parent_name, child_name in candidates:
        parent = getattr(model, parent_name, None)
        layers = getattr(parent, child_name, None) if parent is not None else None
        if layers is not None:
            return layers
    raise AttributeError("Could not find transformer layers on model")


def post_layer_hidden(model, input_ids, attention_mask, layer: int) -> torch.Tensor:
    with torch.inference_mode():
        out = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
            use_cache=False,
            return_dict=True,
        )
    # hidden_states[0] is embeddings; layer k output is index k+1.
    return out.hidden_states[layer + 1]


def sample_next_token(logits, temperature: float, top_p: float) -> torch.Tensor:
    if temperature <= 0:
        return torch.argmax(logits, dim=-1, keepdim=True)
    probs = torch.softmax(logits / temperature, dim=-1)
    sorted_probs, sorted_indices = torch.sort(probs, descending=True, dim=-1)
    cumulative = torch.cumsum(sorted_probs, dim=-1)
    mask = cumulative > top_p
    mask[..., 1:] = mask[..., :-1].clone()
    mask[..., 0] = False
    sorted_probs = sorted_probs.masked_fill(mask, 0)
    sorted_probs = sorted_probs / sorted_probs.sum(dim=-1, keepdim=True)
    sampled = torch.multinomial(sorted_probs, num_samples=1)
    return sorted_indices.gather(-1, sampled)


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)

    dtype = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }[args.dtype]

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    state = checkpoint["model_state_dict"]
    encoder_weight = state["encoder.weight"].float()
    encoder_bias = state["encoder.bias"].float()
    decoder_key = "decoder_a.weight" if args.target_side == "a" else "decoder_b.weight"
    decoder_direction = state[decoder_key][:, args.feature_id].float()

    tokenizer_id = args.model_a_id if args.target_side == "a" else args.model_b_id
    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_id, trust_remote_code=args.trust_remote_code
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    model_a = AutoModelForCausalLM.from_pretrained(
        args.model_a_id,
        torch_dtype=dtype,
        trust_remote_code=args.trust_remote_code,
    ).to(args.device_a).eval()
    model_b = AutoModelForCausalLM.from_pretrained(
        args.model_b_id,
        torch_dtype=dtype,
        trust_remote_code=args.trust_remote_code,
    ).to(args.device_b).eval()

    target_model = model_a if args.target_side == "a" else model_b
    reference_model = model_b if args.target_side == "a" else model_a
    target_device = args.device_a if args.target_side == "a" else args.device_b
    reference_device = args.device_b if args.target_side == "a" else args.device_a
    target_layers = get_layers(target_model)

    encoder_weight = encoder_weight.to(target_device)
    encoder_bias = encoder_bias.to(target_device)
    decoder_direction = decoder_direction.to(target_device, dtype=dtype)

    rows = read_jsonl(args.input_jsonl)
    if args.max_examples is not None:
        rows = rows[: args.max_examples]

    outputs: list[dict[str, Any]] = []
    overall_start = time.perf_counter()

    for example_idx, row in enumerate(rows):
        prompt = row.get("prompt")
        if prompt is None:
            raise KeyError("Each input row must contain a 'prompt' field")

        encoded = tokenizer(prompt, return_tensors="pt")
        generated = encoded["input_ids"].to(target_device)
        prompt_len = generated.shape[1]

        start = time.perf_counter()
        for _ in range(args.max_new_tokens):
            target_mask = torch.ones_like(generated, device=target_device)
            ref_ids = generated.to(reference_device)
            ref_mask = torch.ones_like(ref_ids, device=reference_device)

            ref_hidden = post_layer_hidden(
                reference_model, ref_ids, ref_mask, args.layer
            ).to(target_device)

            def hook(_module, _inputs, output):
                hidden = output[0] if isinstance(output, tuple) else output
                token_count = min(hidden.shape[1], ref_hidden.shape[1])
                target_slice = hidden[:, -token_count:, :]
                ref_slice = ref_hidden[:, -token_count:, :].to(hidden.dtype)

                if args.target_side == "a":
                    paired = torch.cat([target_slice, ref_slice], dim=-1)
                else:
                    paired = torch.cat([ref_slice, target_slice], dim=-1)

                z = torch.relu(
                    torch.nn.functional.linear(
                        paired.float(), encoder_weight, encoder_bias
                    )
                )[..., args.feature_id].to(hidden.dtype)

                delta = (
                    args.alpha
                    * z.unsqueeze(-1)
                    * decoder_direction.view(1, 1, -1)
                )
                modified = hidden.clone()
                modified[:, -token_count:, :] = target_slice + delta
                if isinstance(output, tuple):
                    return (modified, *output[1:])
                return modified

            handle = target_layers[args.layer].register_forward_hook(hook)
            try:
                with torch.inference_mode():
                    out = target_model(
                        input_ids=generated,
                        attention_mask=target_mask,
                        use_cache=False,
                        return_dict=True,
                    )
            finally:
                handle.remove()

            next_token = sample_next_token(
                out.logits[:, -1, :], args.temperature, args.top_p
            )
            generated = torch.cat([generated, next_token], dim=1)
            if tokenizer.eos_token_id is not None and int(next_token.item()) == tokenizer.eos_token_id:
                break

        elapsed = time.perf_counter() - start
        completion_ids = generated[0, prompt_len:]
        completion = tokenizer.decode(completion_ids, skip_special_tokens=True)
        output_row = dict(row)
        output_row.update(
            {
                "completion": completion,
                "feature_id": args.feature_id,
                "alpha": args.alpha,
                "target_side": args.target_side,
                "target_model_id": tokenizer_id,
                "generation_seconds": elapsed,
                "generated_tokens": int(completion_ids.numel()),
                "tokens_per_second": (
                    float(completion_ids.numel()) / elapsed if elapsed > 0 else math.nan
                ),
            }
        )
        outputs.append(output_row)
        print(
            f"[{example_idx + 1}/{len(rows)}] "
            f"seconds={elapsed:.1f} tokens={completion_ids.numel()} "
            f"tok/s={output_row['tokens_per_second']:.3f}",
            flush=True,
        )
        write_jsonl(args.output_jsonl, outputs)

    total_elapsed = time.perf_counter() - overall_start
    print(
        json.dumps(
            {
                "examples": len(outputs),
                "total_seconds": total_elapsed,
                "seconds_per_example": total_elapsed / len(outputs) if outputs else None,
                "estimated_seconds_for_100_examples": (
                    100 * total_elapsed / len(outputs) if outputs else None
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
