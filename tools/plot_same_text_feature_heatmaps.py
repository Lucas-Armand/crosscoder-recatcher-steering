#!/usr/bin/env python3
"""Plot token-by-feature CrossCoder contribution maps for two models and texts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from matplotlib.colors import TwoSlopeNorm
from transformers import AutoModelForCausalLM, PreTrainedTokenizerFast


def rows(path: Path) -> dict[str, dict]:
    return {x["task_id"]: x for x in map(json.loads, path.open())}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--base-results", type=Path, required=True)
    p.add_argument("--variant-results", type=Path, required=True)
    p.add_argument("--base-model", required=True)
    p.add_argument("--variant-model", required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--feature-id", type=int, required=True)
    p.add_argument("--top-k", type=int, default=500)
    p.add_argument("--layer", type=int, default=16)
    p.add_argument("--device-base", default="cuda:0")
    p.add_argument("--device-variant", default="cuda:1")
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()

    source = {"base text": rows(a.base_results)[a.task_id],
              "finetuned text": rows(a.variant_results)[a.task_id]}
    tok_kw = dict(bos_token="<｜begin▁of▁sentence｜>",
                  eos_token="<｜end▁of▁sentence｜>",
                  pad_token="<｜end▁of▁sentence｜>", use_fast=True,
                  local_files_only=True, trust_remote_code=True)
    tokenizer = PreTrainedTokenizerFast.from_pretrained(a.base_model, **tok_kw)
    tokenizer_variant = PreTrainedTokenizerFast.from_pretrained(a.variant_model, **tok_kw)
    common = dict(torch_dtype=torch.float16, trust_remote_code=True,
                  local_files_only=True, attn_implementation="eager")
    base = AutoModelForCausalLM.from_pretrained(a.base_model, **common).to(a.device_base).eval()
    variant = AutoModelForCausalLM.from_pretrained(a.variant_model, **common).to(a.device_variant).eval()
    state = torch.load(a.checkpoint, map_location="cpu", weights_only=False)["model_state_dict"]
    enc = state["encoder.weight"].float(); hidden = state["decoder_a.weight"].shape[0]
    enc_base = enc[:, :hidden].to(a.device_base)
    enc_variant = enc[:, hidden:].to(a.device_variant)
    bias = state["encoder.bias"].float().cpu().numpy()

    maps: dict[tuple[str, str], np.ndarray] = {}
    latent_maps: dict[str, np.ndarray] = {}
    token_text: dict[str, list[str]] = {}
    for text_label, row in source.items():
        code = row["candidate_code_repaired"]
        prompt = row["prompt"].rstrip() + "\n"
        start = len(prompt) if code.startswith(prompt) else 0
        encoded = tokenizer(code, return_tensors="pt", return_offsets_mapping=True,
                            add_special_tokens=False)
        check = tokenizer_variant(code, return_tensors="pt", add_special_tokens=False)
        if not torch.equal(encoded["input_ids"], check["input_ids"]):
            raise ValueError(f"token IDs differ for {text_label}")
        offsets = encoded["offset_mapping"][0].numpy()
        mask_np = (offsets[:, 1] > start) & (offsets[:, 0] < len(code))
        mask = torch.from_numpy(mask_np)
        ids = encoded["input_ids"]; attention = encoded["attention_mask"]
        with torch.inference_mode():
            ob = base(input_ids=ids.to(a.device_base), attention_mask=attention.to(a.device_base),
                      output_hidden_states=True, use_cache=False, return_dict=True)
            hb = ob.hidden_states[a.layer + 1][0, mask].float(); del ob
            ov = variant(input_ids=ids.to(a.device_variant), attention_mask=attention.to(a.device_variant),
                         output_hidden_states=True, use_cache=False, return_dict=True)
            hv = ov.hidden_states[a.layer + 1][0, mask].float(); del ov
            hb = hb / torch.sqrt(torch.mean(hb ** 2, dim=-1, keepdim=True) + 1e-6)
            hv = hv / torch.sqrt(torch.mean(hv ** 2, dim=-1, keepdim=True) + 1e-6)
            cb_raw = torch.nn.functional.linear(hb, enc_base).cpu().numpy()
            cv_raw = torch.nn.functional.linear(hv, enc_variant).cpu().numpy()
        maps[(text_label, "base model")] = np.maximum(cb_raw, 0).T
        maps[(text_label, "finetuned model")] = np.maximum(cv_raw, 0).T
        latent_maps[text_label] = np.maximum(cb_raw + cv_raw + bias, 0).T
        selected_offsets = offsets[mask_np]
        token_text[text_label] = [code[s:e].replace("\n", "↵") for s, e in selected_offsets]

    reference = maps[("base text", "base model")]
    scores = np.quantile(reference, 0.80, axis=1)
    ranked = np.argsort(scores)[::-1][:a.top_k].tolist()
    candidate_natural_rank = int(np.flatnonzero(np.argsort(scores)[::-1] == a.feature_id)[0]) + 1
    candidate_forced = a.feature_id not in ranked
    if candidate_forced:
        ranked.append(a.feature_id)
    candidate_row = ranked.index(a.feature_id)
    values = np.concatenate([maps[key][ranked].ravel() for key in maps])
    vmax = float(np.quantile(values, 0.995)); vmax = max(vmax, 1e-6)
    diffs = {label: maps[(label, "finetuned model")][ranked] - maps[(label, "base model")][ranked]
             for label in source}
    diff_abs = np.concatenate([np.abs(x).ravel() for x in diffs.values()])
    dmax = max(float(np.quantile(diff_abs, 0.995)), 1e-6)

    fig, axes = plt.subplots(2, 3, figsize=(25, 14), constrained_layout=True)
    for row_idx, text_label in enumerate(source):
        for col_idx, model_label in enumerate(("base model", "finetuned model")):
            ax = axes[row_idx, col_idx]
            image = np.arcsinh(maps[(text_label, model_label)][ranked] / vmax)
            im = ax.imshow(image, aspect="auto", interpolation="nearest", cmap="magma",
                           vmin=0, vmax=np.arcsinh(1))
            ax.set_title(f"{model_label} on {text_label}")
        ax = axes[row_idx, 2]
        imd = ax.imshow(diffs[text_label], aspect="auto", interpolation="nearest",
                        cmap="coolwarm", norm=TwoSlopeNorm(vmin=-dmax, vcenter=0, vmax=dmax))
        ax.set_title(f"finetuned − base contribution on {text_label}")
        for col_idx in range(3):
            ax = axes[row_idx, col_idx]
            ax.axhline(candidate_row - 0.5, color="#00ff66", linewidth=1.8)
            ax.axhline(candidate_row + 0.5, color="#00ff66", linewidth=1.8)
            ax.set_yticks([candidate_row], [f"feature {a.feature_id}"], color="#008a38")
            n = len(token_text[text_label]); ticks = np.linspace(0, n - 1, min(9, n), dtype=int)
            ax.set_xticks(ticks, [f"{i}: {token_text[text_label][i][:14]}" for i in ticks],
                          rotation=45, ha="right", fontsize=8)
            ax.set_xlabel("evaluated token position")
        axes[row_idx, 0].set_ylabel("features ordered by base-text/base-model P80")
    fig.colorbar(im, ax=axes[:, :2], shrink=0.65, label="asinh-scaled positive contribution")
    fig.colorbar(imd, ax=axes[:, 2], shrink=0.65, label="raw contribution difference")
    fig.suptitle(
        f"{a.task_id}: top {a.top_k} CrossCoder features + candidate {a.feature_id}\n"
        f"candidate natural rank={candidate_natural_rank}; forced into view={candidate_forced}",
        fontsize=16,
    )
    a.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.output, dpi=180); plt.close(fig)
    metadata = {
        "task_id": a.task_id, "feature_id": a.feature_id, "top_k": a.top_k,
        "candidate_natural_rank": candidate_natural_rank,
        "candidate_forced_into_view": candidate_forced,
        "candidate_display_row_zero_based": candidate_row,
        "feature_order": ranked,
        "evaluated_token_counts": {k: len(v) for k, v in token_text.items()},
        "ranking": "P80 positive base-side encoder contribution on base-generated evaluated code",
    }
    thresholds = (0.0, 1e-8, 1e-6, 1e-4, 1e-2, 1e-1)
    sparsity = {}
    for label, latent in latent_maps.items():
        per_threshold = {}
        for threshold in thresholds:
            counts = (latent > threshold).sum(axis=0)
            per_threshold[str(threshold)] = {
                "mean_active_features_per_token": float(counts.mean()),
                "median_active_features_per_token": float(np.median(counts)),
                "p05": float(np.quantile(counts, 0.05)),
                "p95": float(np.quantile(counts, 0.95)),
                "mean_active_fraction": float(counts.mean() / latent.shape[0]),
            }
        sparsity[label] = per_threshold
    combined = np.concatenate(list(latent_maps.values()), axis=1)
    sparsity["combined"] = {}
    for threshold in thresholds:
        counts = (combined > threshold).sum(axis=0)
        sparsity["combined"][str(threshold)] = {
            "mean_active_features_per_token": float(counts.mean()),
            "median_active_features_per_token": float(np.median(counts)),
            "p05": float(np.quantile(counts, 0.05)),
            "p95": float(np.quantile(counts, 0.95)),
            "mean_active_fraction": float(counts.mean() / combined.shape[0]),
        }
    metadata["joint_latent_sparsity"] = sparsity
    a.output.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({k: v for k, v in metadata.items() if k != "feature_order"}, indent=2))


if __name__ == "__main__":
    main()
