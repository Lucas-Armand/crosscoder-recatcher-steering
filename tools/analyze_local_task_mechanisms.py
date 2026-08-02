#!/usr/bin/env python3
"""Decompose model differences into local per-task residual directions."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np
import torch
from transformers import AutoModelForCausalLM, BitsAndBytesConfig, PreTrainedTokenizerFast


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results-root", type=Path, required=True)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--model-base-id", required=True)
    p.add_argument("--model-finetuned-id", required=True)
    p.add_argument("--task-ids", nargs="+", required=True)
    p.add_argument("--layer", type=int, default=16)
    p.add_argument("--device-base", default="cuda:0")
    p.add_argument("--device-finetuned", default="cuda:1")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--trust-remote-code", action="store_true")
    return p.parse_args()


def jsonl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines() if x.strip()]


def unit(x):
    norm = np.linalg.norm(x)
    return x / norm if norm else np.zeros_like(x)


def oriented_pcs(matrix, count=5):
    _, singular, vh = np.linalg.svd(matrix, full_matrices=False)
    energy = singular ** 2
    mean = matrix.mean(axis=0)
    pcs = vh[:count].astype(np.float32)
    for index in range(len(pcs)):
        if np.dot(pcs[index], mean) < 0:
            pcs[index] *= -1
    return pcs, (energy[:count] / energy.sum()).astype(np.float32)


def cosine(a, b):
    return float(np.dot(unit(a), unit(b)))


def main():
    a = parse_args(); a.output_dir.mkdir(parents=True, exist_ok=True)
    direction_dir = a.output_dir / "steering_directions"; direction_dir.mkdir(exist_ok=True)
    raw = {}; solutions = {}
    for label in ("deepseek_base", "deepseek_finetuned"):
        raw[label] = {x["task_id"]: x for x in jsonl(
            a.results_root / "results" / f"humanevalplus__{label}_results.jsonl")}
        solutions[label] = {x["task_id"]: x["solution"] for x in jsonl(
            a.results_root / "samples_for_external_eval" / f"humanevalplus__{label}_samples.jsonl")}

    tok_kw = dict(bos_token="<｜begin▁of▁sentence｜>", eos_token="<｜end▁of▁sentence｜>",
                  pad_token="<｜end▁of▁sentence｜>", local_files_only=True,
                  trust_remote_code=a.trust_remote_code)
    tokenizer = PreTrainedTokenizerFast.from_pretrained(a.model_base_id, **tok_kw)
    tokenizer_ft = PreTrainedTokenizerFast.from_pretrained(a.model_finetuned_id, **tok_kw)
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
                              bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4")
    common = dict(quantization_config=quant, torch_dtype=torch.float16,
                  trust_remote_code=a.trust_remote_code, local_files_only=True,
                  low_cpu_mem_usage=True, attn_implementation="eager")
    base = AutoModelForCausalLM.from_pretrained(
        a.model_base_id, device_map={"": a.device_base}, **common).eval()
    ft = AutoModelForCausalLM.from_pretrained(
        a.model_finetuned_id, device_map={"": a.device_finetuned}, **common).eval()

    checkpoint = torch.load(a.checkpoint, map_location="cpu", weights_only=False)
    state = checkpoint["model_state_dict"]
    decoder_base = state["decoder_a.weight"].float().numpy()
    decoder_ft = state["decoder_b.weight"].float().numpy()

    def forward_pair(code, prompt):
        encoded = tokenizer(code, return_tensors="pt", return_offsets_mapping=True,
                            add_special_tokens=False)
        check = tokenizer_ft(code, return_tensors="pt", add_special_tokens=False)
        if not torch.equal(encoded["input_ids"], check["input_ids"]):
            raise ValueError("content token IDs differ")
        offsets = encoded.pop("offset_mapping")[0].numpy()
        start = len(prompt.rstrip() + "\n") if code.startswith(prompt.rstrip() + "\n") else 0
        mask = (offsets[:, 1] > start) & (offsets[:, 0] < len(code))
        ids = encoded["input_ids"]; attention = encoded["attention_mask"]
        with torch.inference_mode():
            ob = base(input_ids=ids.to(a.device_base), attention_mask=attention.to(a.device_base),
                      output_hidden_states=True, use_cache=False, return_dict=True)
            hb = ob.hidden_states[a.layer + 1][0, mask].float(); del ob
            of = ft(input_ids=ids.to(a.device_finetuned), attention_mask=attention.to(a.device_finetuned),
                    output_hidden_states=True, use_cache=False, return_dict=True)
            hf = of.hidden_states[a.layer + 1][0, mask].float().to(a.device_base); del of
            valid = torch.isfinite(hb).all(1) & torch.isfinite(hf).all(1)
            hb = hb[valid]; hf = hf[valid]
            hb = hb / torch.sqrt(torch.mean(hb ** 2, dim=-1, keepdim=True) + 1e-6)
            hf = hf / torch.sqrt(torch.mean(hf ** 2, dim=-1, keepdim=True) + 1e-6)
        return hb.cpu().numpy(), hf.cpu().numpy(), offsets[mask][valid.cpu().numpy()]

    metric_rows = []; projection_rows = []; manifest = {}
    for task_id in a.task_ids:
        representations = {}
        components = {}
        for source in ("deepseek_base", "deepseek_finetuned"):
            code = solutions[source][task_id]; prompt = raw[source][task_id]["prompt"]
            hb, hf, offsets = forward_pair(code, prompt)
            delta = hf - hb; mean = unit(delta.mean(axis=0)); pcs, explained = oriented_pcs(delta)
            representations[source] = (hb, hf)
            components[f"mean_{source}"] = mean
            for pc_index, pc in enumerate(pcs, 1):
                components[f"pc{pc_index}_{source}"] = unit(pc)
                metric_rows.append({"task_id": task_id, "source_text": source,
                                    "component": f"pc{pc_index}",
                                    "explained_energy": float(explained[pc_index - 1]),
                                    "token_count": len(delta)})
        mean_a = components["mean_deepseek_base"]
        mean_b = components["mean_deepseek_finetuned"]
        if np.dot(mean_a, mean_b) < 0: mean_b = -mean_b
        components["shared_mean"] = unit(mean_a + mean_b)
        pc_a = components["pc1_deepseek_base"]
        pc_b = components["pc1_deepseek_finetuned"]
        if np.dot(pc_a, pc_b) < 0: pc_b = -pc_b
        components["shared_pc1"] = unit(pc_a + pc_b)
        components["different_own_text"] = unit(
            representations["deepseek_finetuned"][1].mean(axis=0) -
            representations["deepseek_base"][0].mean(axis=0))
        manifest[task_id] = {
            "mean_direction_cosine_across_texts": cosine(mean_a, mean_b),
            "pc1_cosine_across_texts": cosine(pc_a, pc_b),
            "component_names": sorted(components),
        }
        safe = task_id.replace("/", "_")
        for name, direction in components.items():
            np.savez_compressed(direction_dir / f"{safe}__{name}.npz",
                                task_ids=np.asarray([task_id]),
                                directions=direction[None].astype(np.float32))
            for side, decoder in (("base", decoder_base), ("finetuned", decoder_ft)):
                norms = np.linalg.norm(decoder, axis=0)
                similarities = direction @ decoder / np.maximum(norms, 1e-12)
                top = np.argsort(np.abs(similarities))[-5:][::-1]
                for rank, feature in enumerate(top, 1):
                    projection_rows.append({
                        "task_id": task_id, "component": name, "decoder_side": side,
                        "rank": rank, "feature_id": int(feature),
                        "signed_cosine": float(similarities[feature]),
                        "absolute_cosine": float(abs(similarities[feature])),
                    })
        print(task_id, json.dumps(manifest[task_id]), flush=True)

    for path, rows in ((a.output_dir / "component_metrics.csv", metric_rows),
                       (a.output_dir / "crosscoder_decoder_projections.csv", projection_rows)):
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    (a.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__": main()
