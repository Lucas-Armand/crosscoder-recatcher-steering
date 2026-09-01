#!/usr/bin/env python3
"""Paired first-token E/V screen: merged repetitive text vs base successful text."""
import csv, json, math
from pathlib import Path

import numpy as np
import torch
from transformers import AutoTokenizer

CKPT = Path("runs/crosscoder_codellama_base_merged_layer16_same_text_topk100_v1/final.pt")
ROOT = Path("runs/same_text_activations/codellama_base_merged_layer16_rms")
ATTR = Path("reports/codellama_base_merged_topk100_v1_repetition_attribution/task_feature_attributions.npz")
OUT = Path("reports/codellama_base_merged_topk100_v1_repetition_paired_first_token_ev")
FEATURES = 16384
PERMS = 200
SEED = 42


def encode_first(pa, pb, weight, bias, top_k):
    a, b = np.load(pa), np.load(pb)
    if not np.array_equal(a["input_ids"], b["input_ids"]): raise ValueError(f"unaligned: {pa}")
    x = np.concatenate([a["layer_16"][:1], b["layer_16"][:1]], axis=1)
    with torch.inference_mode():
        dense = torch.relu(torch.nn.functional.linear(torch.from_numpy(x).float().cuda(), weight, bias))
        values, indices = torch.topk(dense, top_k, dim=1)
    z = np.zeros(FEATURES, np.float32)
    z[indices[0].cpu().numpy()] = values[0].cpu().numpy()
    return z, int(a["input_ids"][0])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ck = torch.load(CKPT, map_location="cpu", weights_only=False); sd = ck["model_state_dict"]
    top_k = int(ck["config"]["top_k"]); weight = sd["encoder.weight"].float().cuda(); bias = sd["encoder.bias"].float().cuda()
    da, db = sd["decoder_a.weight"].float(), sd["decoder_b.weight"].float()
    na, nb = torch.linalg.vector_norm(da, dim=0), torch.linalg.vector_norm(db, dim=0)
    specificity = (nb / (na + nb + 1e-12)).numpy()
    task_ids = list(map(str, np.load(ATTR)["task_ids"].tolist()))
    manifest = json.loads((ROOT / "capture_manifest.json").read_text())
    index = {(m["task_id"], m["source_text"]): m for m in manifest if m["benchmark"] == "bigcodebench"}
    tokenizer = AutoTokenizer.from_pretrained("meta-llama/CodeLlama-7b-hf", local_files_only=True)
    base, merged, evidence = [], [], []
    for task_id in task_ids:
        scores = {}; tokens = {}
        for source in ("codellama_base", "codellama_merged"):
            m = index[(task_id, source)]
            pa = ROOT / "bigcodebench" / "codellama_base" / m["filename"]
            pb = ROOT / "bigcodebench" / "codellama_merged" / m["filename"]
            scores[source], tokens[source] = encode_first(pa, pb, weight, bias, top_k)
        base.append(scores["codellama_base"]); merged.append(scores["codellama_merged"])
        evidence.append({"task_id": task_id, "base_first_token_id": tokens["codellama_base"], "base_first_token": tokenizer.decode([tokens["codellama_base"]]), "merged_first_token_id": tokens["codellama_merged"], "merged_first_token": tokenizer.decode([tokens["codellama_merged"]])})
    base, merged = np.stack(base), np.stack(merged); delta = merged - base
    effect = delta.mean(0)
    rng = np.random.default_rng(SEED); null = np.empty((PERMS, FEATURES), np.float32)
    for i in range(PERMS):
        signs = rng.choice(np.asarray([-1.0, 1.0], np.float32), size=(len(task_ids), 1))
        null[i] = (delta * signs).mean(0)
    null_sd = null.std(0, ddof=1); ev = np.divide(effect, null_sd, out=np.zeros_like(effect), where=null_sd > 0)
    p = (1 + (np.abs(null) >= np.abs(effect)[None]).sum(0)) / (PERMS + 1)
    support_min = max(3, math.ceil(0.1 * len(task_ids)))
    rows = []
    for f in range(FEATURES):
        rows.append({"feature_id": f, "mean_paired_delta_merged_minus_base": float(effect[f]), "permutation_null_sd": float(null_sd[f]), "ev": float(ev[f]), "permutation_p_nominal": float(p[f]), "merged_support": int((merged[:, f] > 0).sum()), "base_support": int((base[:, f] > 0).sum()), "positive_delta_tasks": int((delta[:, f] > 0).sum()), "negative_delta_tasks": int((delta[:, f] < 0).sum()), "merged_mean_activation": float(merged[:, f].mean()), "base_mean_activation": float(base[:, f].mean()), "decoder_merged_specificity": float(specificity[f])})
    positive = [r for r in rows if r["mean_paired_delta_merged_minus_base"] > 0 and r["merged_support"] >= support_min]
    positive.sort(key=lambda r: (r["ev"], r["positive_delta_tasks"], r["decoder_merged_specificity"]), reverse=True)
    negative = [r for r in rows if r["mean_paired_delta_merged_minus_base"] < 0 and r["base_support"] >= support_min]
    negative.sort(key=lambda r: (r["ev"], -r["negative_delta_tasks"]));
    for rank, r in enumerate(positive, 1): r["rank"] = rank; r["suggested_steering_sign"] = "negative"
    for rank, r in enumerate(negative, 1): r["rank"] = rank; r["suggested_steering_sign"] = "positive"
    fields = ["rank", "suggested_steering_sign"] + list(rows[0])
    for name, data in (("positive_delta_negative_steering_ranking.csv", positive), ("negative_delta_positive_steering_ranking.csv", negative)):
        with (OUT / name).open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(data)
    with (OUT / "task_first_tokens.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(evidence[0])); w.writeheader(); w.writerows(evidence)
    np.savez_compressed(OUT / "paired_first_token_scores.npz", task_ids=np.asarray(task_ids), base=base, merged=merged, delta=delta)
    summary = {"method": "paired_first_evaluated_token_topk100_ev", "tasks": len(task_ids), "pair": "merged repetitive source text minus base successful source text", "effect": "mean paired delta", "null": "200 within-task random sign flips", "ev": "effect divided by permutation-null SD; not a z-score or p-value", "minimum_support": support_min, "top50_negative_steering_candidates": positive[:50], "top20_positive_steering_candidates": negative[:20], "limitations": ["first evaluated generated token, not the last prompt token", "post-selected 41-case repetition cohort", "nominal uncorrected permutation p-values", "activation association screen, not intervention evidence"]}
    (OUT / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__": main()
