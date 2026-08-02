#!/usr/bin/env python3
"""Compare layer-16 directions within tasks for same and model-specific text."""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import torch
from transformers import AutoModelForCausalLM, BitsAndBytesConfig, PreTrainedTokenizerFast


GROUPS = (
    "base_pass_finetuned_fail",
    "base_fail_finetuned_pass",
    "both_pass",
    "both_fail",
)


def argspec() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results-root", type=Path, required=True)
    p.add_argument("--labels-csv", type=Path, required=True)
    p.add_argument("--model-base-id", required=True)
    p.add_argument("--model-finetuned-id", required=True)
    p.add_argument("--layer", type=int, default=16)
    p.add_argument("--per-group", type=int, default=10)
    p.add_argument("--device-base", default="cuda:0")
    p.add_argument("--device-finetuned", default="cuda:1")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--trust-remote-code", action="store_true")
    return p.parse_args()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def rms(x: torch.Tensor) -> torch.Tensor:
    return x.float() / torch.sqrt(torch.mean(x.float() ** 2, dim=-1, keepdim=True) + 1e-6)


def unit(x: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(x)
    return x / n if n > 0 else np.zeros_like(x)


def cosine(a: np.ndarray, b: np.ndarray, absolute: bool = False) -> float:
    value = float(np.dot(unit(a), unit(b)))
    return abs(value) if absolute else value


def dominant(matrix: np.ndarray) -> tuple[np.ndarray, float]:
    """Uncentered SVD: direction captures the dominant model displacement."""
    if not len(matrix):
        raise ValueError("empty token matrix")
    _, singular, vh = np.linalg.svd(matrix, full_matrices=False)
    energy = singular ** 2
    explained = float(energy[0] / energy.sum()) if energy.sum() else 0.0
    direction = unit(vh[0].astype(np.float32))
    mean = matrix.mean(axis=0)
    if np.dot(direction, mean) < 0:
        direction = -direction
    return direction, explained


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    a = argspec()
    a.output_dir.mkdir(parents=True, exist_ok=True)
    labels = {}
    with a.labels_csv.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["benchmark"] == "humanevalplus" and int(row["generation_idx"]) == 0:
                labels[(row["model"], row["task_id"])] = int(row["label"])

    raw = {}
    solutions = {}
    for model in ("deepseek_base", "deepseek_finetuned"):
        result_rows = jsonl(a.results_root / "results" / f"humanevalplus__{model}_results.jsonl")
        sample_rows = jsonl(a.results_root / "samples_for_external_eval" / f"humanevalplus__{model}_samples.jsonl")
        raw[model] = {row["task_id"]: row for row in result_rows}
        solutions[model] = {row["task_id"]: row["solution"] for row in sample_rows}

    task_ids = sorted(set(raw["deepseek_base"]) & set(raw["deepseek_finetuned"]),
                      key=lambda x: int(x.split("/")[-1]))
    grouped = defaultdict(list)
    for task_id in task_ids:
        base_failed = labels[("deepseek_base", task_id)] == 1
        ft_failed = labels[("deepseek_finetuned", task_id)] == 1
        group = (
            "base_pass_finetuned_fail" if not base_failed and ft_failed else
            "base_fail_finetuned_pass" if base_failed and not ft_failed else
            "both_fail" if base_failed else "both_pass"
        )
        grouped[group].append(task_id)
    selected = [task for group in GROUPS for task in grouped[group][:a.per_group]]

    tokenizer = PreTrainedTokenizerFast.from_pretrained(
        a.model_base_id, trust_remote_code=a.trust_remote_code,
        bos_token="<｜begin▁of▁sentence｜>", eos_token="<｜end▁of▁sentence｜>",
        pad_token="<｜end▁of▁sentence｜>", local_files_only=True,
    )
    tokenizer_ft = PreTrainedTokenizerFast.from_pretrained(
        a.model_finetuned_id, trust_remote_code=a.trust_remote_code,
        bos_token="<｜begin▁of▁sentence｜>", eos_token="<｜end▁of▁sentence｜>",
        pad_token="<｜end▁of▁sentence｜>", local_files_only=True,
    )
    quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16,
                              bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4")
    common = dict(quantization_config=quant, torch_dtype=torch.float16,
                  trust_remote_code=a.trust_remote_code, local_files_only=True,
                  low_cpu_mem_usage=True, attn_implementation="eager")
    model_base = AutoModelForCausalLM.from_pretrained(
        a.model_base_id, device_map={"": a.device_base}, **common).eval()
    model_ft = AutoModelForCausalLM.from_pretrained(
        a.model_finetuned_id, device_map={"": a.device_finetuned}, **common).eval()

    def forward(code: str, prompt: str) -> tuple[np.ndarray, list[list[int]], list[int]]:
        # The two repositories share identical content-token IDs but differ in
        # automatic BOS insertion. Excluding model-specific special tokens
        # gives both models the exact same controlled sequence.
        encoded = tokenizer(
            code, return_tensors="pt", return_offsets_mapping=True,
            add_special_tokens=False,
        )
        encoded_ft = tokenizer_ft(
            code, return_tensors="pt", add_special_tokens=False,
        )
        if not torch.equal(encoded["input_ids"], encoded_ft["input_ids"]):
            raise ValueError("base and finetuned tokenizers produced different IDs")
        offsets = encoded.pop("offset_mapping")[0].numpy()
        evaluated_start = len(prompt.rstrip() + "\n") if code.startswith(prompt.rstrip() + "\n") else 0
        mask = (offsets[:, 1] > evaluated_start) & (offsets[:, 0] < len(code))
        ids = encoded["input_ids"]
        attention = encoded["attention_mask"]
        with torch.inference_mode():
            out_b = model_base(input_ids=ids.to(a.device_base),
                               attention_mask=attention.to(a.device_base),
                               output_hidden_states=True, use_cache=False, return_dict=True)
            hb = out_b.hidden_states[a.layer + 1][0, mask].float()
            del out_b
            out_f = model_ft(input_ids=ids.to(a.device_finetuned),
                             attention_mask=attention.to(a.device_finetuned),
                             output_hidden_states=True, use_cache=False, return_dict=True)
            hf = out_f.hidden_states[a.layer + 1][0, mask].float().to(a.device_base)
            del out_f
            # Direction analysis is scale-normalized below. The historical
            # norm<500 latent-screening filter is not a validity criterion and
            # can remove every finetuned token; retain every finite pair.
            valid = torch.isfinite(hb).all(1) & torch.isfinite(hf).all(1)
            if not bool(valid.any()):
                raise ValueError("no finite paired evaluated tokens")
            hb = rms(hb[valid]).cpu().numpy()
            hf = rms(hf[valid]).cpu().numpy()
        return np.stack([hb, hf]), offsets[mask][valid.cpu().numpy()].tolist(), ids[0, mask][valid.cpu()].tolist()

    records = []
    direction_store = {}
    hidden_means = {}
    for idx, task_id in enumerate(selected):
        base_failed = labels[("deepseek_base", task_id)] == 1
        ft_failed = labels[("deepseek_finetuned", task_id)] == 1
        group = ("base_pass_finetuned_fail" if not base_failed and ft_failed else
                 "base_fail_finetuned_pass" if base_failed and not ft_failed else
                 "both_fail" if base_failed else "both_pass")
        for source in ("deepseek_base", "deepseek_finetuned"):
            code = solutions[source][task_id]
            prompt = raw[source][task_id]["prompt"]
            pair, offsets, token_ids = forward(code, prompt)
            hb, hf = pair
            delta = hf - hb
            direction, explained = dominant(delta)
            mean_delta = delta.mean(axis=0)
            norms = np.linalg.norm(delta, axis=1)
            peak = int(np.argmax(norms))
            lo, hi = offsets[peak]
            direction_store[f"{task_id.replace('/', '_')}__{source}"] = direction
            hidden_means[(task_id, source, "base")] = hb.mean(axis=0)
            hidden_means[(task_id, source, "finetuned")] = hf.mean(axis=0)
            records.append({
                "task_id": task_id, "group": group, "source_text": source,
                "base_failed": base_failed, "finetuned_failed": ft_failed,
                "evaluated_tokens": len(delta),
                "same_text_mean_delta_norm": float(np.linalg.norm(mean_delta)),
                "same_text_rms_token_delta": float(np.sqrt(np.mean(norms ** 2))),
                "same_text_pc1_explained_energy": explained,
                "mean_delta_cosine_pc1": cosine(mean_delta, direction),
                "peak_delta_token_index": peak,
                "peak_delta_token_norm": float(norms[peak]),
                "peak_delta_text": code[lo:hi].replace("\n", "\\n"),
                "peak_delta_token_id": token_ids[peak],
            })
        print(f"[{idx + 1}/{len(selected)}] {group} {task_id}", flush=True)

    by_key = {(r["task_id"], r["source_text"]): r for r in records}
    own_rows = []
    for task_id in selected:
        group = by_key[(task_id, "deepseek_base")]["group"]
        own_delta = (hidden_means[(task_id, "deepseek_finetuned", "finetuned")] -
                     hidden_means[(task_id, "deepseek_base", "base")])
        cross_model_base_text = direction_store[f"{task_id.replace('/', '_')}__deepseek_base"]
        cross_model_ft_text = direction_store[f"{task_id.replace('/', '_')}__deepseek_finetuned"]
        own_rows.append({
            "task_id": task_id, "group": group,
            "own_text_mean_delta_norm": float(np.linalg.norm(own_delta)),
            "same_text_direction_cosine_across_source_texts": cosine(
                cross_model_base_text, cross_model_ft_text),
            "own_text_delta_cosine_same_text_base_code": cosine(own_delta, cross_model_base_text),
            "own_text_delta_cosine_same_text_finetuned_code": cosine(own_delta, cross_model_ft_text),
            "base_code_length_tokens": by_key[(task_id, "deepseek_base")]["evaluated_tokens"],
            "finetuned_code_length_tokens": by_key[(task_id, "deepseek_finetuned")]["evaluated_tokens"],
        })

    # Remove the checkpoint-wide displacement before asking whether residual
    # directions cluster by evaluator transition. Otherwise the nearly global
    # base-to-finetuned shift dominates every task-specific PC.
    same_vectors = {}
    own_vectors = {}
    for task_id in selected:
        deltas = []
        for source in ("deepseek_base", "deepseek_finetuned"):
            deltas.append(
                hidden_means[(task_id, source, "finetuned")] -
                hidden_means[(task_id, source, "base")]
            )
        same_vectors[task_id] = np.mean(deltas, axis=0)
        own_vectors[task_id] = (
            hidden_means[(task_id, "deepseek_finetuned", "finetuned")] -
            hidden_means[(task_id, "deepseek_base", "base")]
        )
    global_same = np.mean(list(same_vectors.values()), axis=0)
    global_own = np.mean(list(own_vectors.values()), axis=0)
    same_centered = {task: unit(value - global_same) for task, value in same_vectors.items()}
    own_centered = {task: unit(value - global_own) for task, value in own_vectors.items()}
    for row in own_rows:
        task = row["task_id"]
        row["globally_centered_same_text_delta_norm"] = float(
            np.linalg.norm(same_vectors[task] - global_same)
        )
        row["globally_centered_own_text_delta_norm"] = float(
            np.linalg.norm(own_vectors[task] - global_own)
        )
        row["centered_same_vs_own_cosine"] = cosine(
            same_centered[task], own_centered[task]
        )

    def separation(vector_map: dict[str, np.ndarray], seed: int = 42) -> dict:
        vectors = np.stack([vector_map[t] for t in selected])
        group_labels = np.asarray([by_key[(t, "deepseek_base")]["group"] for t in selected])
        similarity = vectors @ vectors.T
        upper = np.triu(np.ones_like(similarity, dtype=bool), 1)

        def statistic(labels: np.ndarray) -> tuple[float, float, float]:
            same = labels[:, None] == labels[None, :]
            within = float(similarity[upper & same].mean())
            between = float(similarity[upper & ~same].mean())
            return within - between, within, between

        observed, within, between = statistic(group_labels)
        rng = np.random.default_rng(seed)
        null = np.asarray([statistic(rng.permutation(group_labels))[0] for _ in range(2000)])
        return {
            "observed_within_minus_between_cosine": observed,
            "mean_within_group_cosine": within,
            "mean_between_group_cosine": between,
            "permutation_null_mean": float(null.mean()),
            "permutation_null_sd": float(null.std(ddof=1)),
            "permutation_p_greater": float((1 + np.count_nonzero(null >= observed)) / (len(null) + 1)),
            "permutations": len(null),
            "seed": seed,
        }

    separation_rows = []
    for name, vectors in (("globally_centered_same_text", same_centered),
                          ("globally_centered_different_own_text", own_centered)):
        separation_rows.append({"analysis": name, **separation(vectors)})

    centroid_rows = []
    for analysis, vectors in (("same_text", same_centered), ("different_own_text", own_centered)):
        centroids = {
            group: unit(np.mean([vectors[t] for t in selected
                                 if by_key[(t, "deepseek_base")]["group"] == group], axis=0))
            for group in GROUPS
        }
        for left_index, left in enumerate(GROUPS):
            for right in GROUPS[left_index:]:
                centroid_rows.append({
                    "analysis": analysis, "group_a": left, "group_b": right,
                    "centroid_cosine": cosine(centroids[left], centroids[right]),
                })

    summaries = []
    for group in GROUPS:
        tasks = [x for x in selected if by_key[(x, "deepseek_base")]["group"] == group]
        for source in ("deepseek_base", "deepseek_finetuned"):
            directions = np.stack([direction_store[f"{x.replace('/', '_')}__{source}"] for x in tasks])
            consensus, explained = dominant(directions)
            coherences = directions @ consensus
            summaries.append({
                "group": group, "analysis": f"same_text_{source}", "n_tasks": len(tasks),
                "consensus_pc1_explained_energy": explained,
                "mean_signed_cosine_to_consensus": float(coherences.mean()),
                "median_signed_cosine_to_consensus": float(np.median(coherences)),
                "mean_delta_norm": float(np.mean([by_key[(x, source)]["same_text_mean_delta_norm"] for x in tasks])),
            })
            direction_store[f"consensus__{group}__{source}"] = consensus
        own = np.stack([unit(hidden_means[(x, "deepseek_finetuned", "finetuned")] -
                            hidden_means[(x, "deepseek_base", "base")]) for x in tasks])
        consensus, explained = dominant(own)
        summaries.append({
            "group": group, "analysis": "different_own_text", "n_tasks": len(tasks),
            "consensus_pc1_explained_energy": explained,
            "mean_signed_cosine_to_consensus": float((own @ consensus).mean()),
            "median_signed_cosine_to_consensus": float(np.median(own @ consensus)),
            "mean_delta_norm": float(np.mean([x["own_text_mean_delta_norm"] for x in own_rows if x["group"] == group])),
        })
        direction_store[f"consensus__{group}__different_own_text"] = consensus

    write_csv(a.output_dir / "same_text_task_metrics.csv", records)
    write_csv(a.output_dir / "different_text_task_metrics.csv", own_rows)
    write_csv(a.output_dir / "group_direction_summary.csv", summaries)
    write_csv(a.output_dir / "direction_group_separation.csv", separation_rows)
    write_csv(a.output_dir / "group_centroid_cosines.csv", centroid_rows)
    np.savez_compressed(a.output_dir / "task_and_consensus_directions.npz", **direction_store)
    selection = {g: grouped[g][:a.per_group] for g in GROUPS}
    (a.output_dir / "selection.json").write_text(json.dumps(selection, indent=2) + "\n")

    colors = {GROUPS[i]: plt.cm.tab10(i) for i in range(len(GROUPS))}
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for group in GROUPS:
        subset = [r for r in records if r["group"] == group]
        axes[0].scatter([r["same_text_mean_delta_norm"] for r in subset],
                        [r["same_text_pc1_explained_energy"] for r in subset],
                        label=group, color=colors[group], alpha=.75)
        subset_own = [r for r in own_rows if r["group"] == group]
        axes[1].scatter([r["own_text_mean_delta_norm"] for r in subset_own],
                        [r["same_text_direction_cosine_across_source_texts"] for r in subset_own],
                        label=group, color=colors[group], alpha=.8)
    axes[0].set(xlabel="mean same-text delta norm", ylabel="PC1 explained energy",
                title="Model displacement on controlled text")
    axes[1].axhline(0, color="black", lw=.8)
    axes[1].set(xlabel="own-text mean-state delta norm", ylabel="same-text direction cosine",
                title="Own-text change vs direction stability")
    axes[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(a.output_dir / "intra_task_direction_overview.png", dpi=180)
    plt.close(fig)

    print(json.dumps({"selected_tasks": len(selected),
                      "group_counts": {g: len(selection[g]) for g in GROUPS},
                      "output_dir": str(a.output_dir)}, indent=2))


if __name__ == "__main__":
    main()
