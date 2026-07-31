#!/usr/bin/env python3
"""Same-text joint-latent PR-AUC analysis for a trained tied CrossCoder."""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

from run_pr_auc_feature_screening import (
    normalize_pr_effect,
    pr_auc_both,
    prepare_pr_order,
)


STATISTICS = ("mean", "max", "p95", "p99", "active_fraction")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    parser.add_argument("--labels-csv", type=Path, required=True)
    parser.add_argument("--model-a-id", required=True)
    parser.add_argument("--model-b-id", required=True)
    parser.add_argument("--model-a-label", default="deepseek_base")
    parser.add_argument("--model-b-label", default="deepseek_merged")
    parser.add_argument("--benchmark", default="humanevalplus")
    parser.add_argument("--layer", type=int, default=16)
    parser.add_argument("--device-a", default="cuda:0")
    parser.add_argument("--device-b", default="cuda:1")
    parser.add_argument(
        "--dtype", choices=["float16", "bfloat16", "float32", "nf4"], default="float16"
    )
    parser.add_argument("--permutations", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--top-features", type=int, default=50)
    parser.add_argument("--contexts-per-feature", type=int, default=5)
    parser.add_argument("--token-feature-ids", type=int, nargs="*", default=[])
    parser.add_argument(
        "--capture-only", action="store_true",
        help="Capture aggregates/token values without running PR-AUC permutations.",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def rms_normalize(x: torch.Tensor, eps: float = 1e-6) -> torch.Tensor:
    rms = torch.sqrt(torch.mean(x.float() ** 2, dim=-1, keepdim=True) + eps)
    return x.float() / rms


def normalized_entropy(values: np.ndarray) -> np.ndarray:
    total = values.sum(axis=0, keepdims=True)
    probabilities = np.divide(
        values, total, out=np.zeros_like(values, dtype=np.float64), where=total > 0
    )
    log_probabilities = np.zeros_like(probabilities)
    positive = probabilities > 0
    log_probabilities[positive] = np.log(probabilities[positive])
    entropy = -(probabilities * log_probabilities).sum(axis=0)
    denominator = math.log(values.shape[0]) if values.shape[0] > 1 else 1.0
    return entropy / denominator


def aggregate_latent(z: torch.Tensor) -> dict[str, np.ndarray]:
    if z.ndim != 2 or not len(z):
        raise ValueError("joint latent must be [tokens, features] and nonempty")
    p95 = torch.quantile(z, 0.95, dim=0)
    p99 = torch.quantile(z, 0.99, dim=0)
    token_count = z.shape[0]
    first_quarter_end = max(1, math.ceil(token_count * 0.25))
    second_quarter_end = max(first_quarter_end + 1, math.ceil(token_count * 0.50))
    second_quarter_end = min(token_count, second_quarter_end)
    first_q = z[:first_quarter_end]
    second_q = z[first_quarter_end:second_quarter_end]
    if not len(second_q):
        second_q = z[-1:]
    maximum, argmax = z.max(dim=0)
    above_p95 = (z >= p95.unsqueeze(0)) & (z > 0)
    token_positions = torch.arange(token_count, device=z.device).unsqueeze(1)
    sentinel = torch.full_like(token_positions.expand_as(above_p95), token_count)
    first_p95 = torch.where(above_p95, token_positions, sentinel).min(dim=0).values
    first_p95 = first_p95.float() / max(1, token_count - 1)
    first_p95[p95 <= 0] = torch.nan
    return {
        "mean": z.mean(dim=0).cpu().numpy(),
        "max": maximum.cpu().numpy(),
        "p95": p95.cpu().numpy(),
        "p99": p99.cpu().numpy(),
        "active_fraction": (z > 0).float().mean(dim=0).cpu().numpy(),
        "sum": z.sum(dim=0).cpu().numpy(),
        "first_p95_position": first_p95.cpu().numpy(),
        "first_quarter_mean": first_q.mean(dim=0).cpu().numpy(),
        "second_quarter_mean": second_q.mean(dim=0).cpu().numpy(),
        "argmax": argmax.cpu().numpy().astype(np.int16),
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"no rows for {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def screen_source(
    source_label: str,
    indices: np.ndarray,
    labels: np.ndarray,
    aggregates: dict[str, np.ndarray],
    decoder_specificity: np.ndarray,
    base_decoder_norm: np.ndarray,
    merged_decoder_norm: np.ndarray,
    base_contribution_mean: np.ndarray,
    merged_contribution_mean: np.ndarray,
    activation_source_base_share: np.ndarray,
    permutations: int,
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    y = labels[indices].astype(np.int8)
    if len(np.unique(y)) != 2:
        raise ValueError(f"{source_label}: labels contain only one class")
    prevalence = float(y.mean())
    feature_count = aggregates["mean"].shape[1]
    observed: dict[str, np.ndarray] = {}
    orders: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for statistic in STATISTICS:
        matrix = aggregates[statistic][indices]
        order, ties = prepare_pr_order(matrix)
        values, _ = pr_auc_both(order, ties, y)
        observed[statistic] = values
        orders[statistic] = (order, ties)

    rng = np.random.default_rng(seed)
    null = {
        statistic: np.empty((permutations, feature_count), dtype=np.float32)
        for statistic in STATISTICS
    }
    max_effect = np.empty(permutations, dtype=np.float32)
    for permutation in range(permutations):
        permuted = rng.permutation(y)
        largest = 0.0
        for statistic in STATISTICS:
            values, _ = pr_auc_both(*orders[statistic], permuted)
            null[statistic][permutation] = values
            largest = max(
                largest,
                float(normalize_pr_effect(values, prevalence).max()),
            )
        max_effect[permutation] = largest

    sums = aggregates["sum"][indices]
    entropy = normalized_entropy(sums)
    fail = y == 1
    passed = y == 0
    table: list[dict[str, Any]] = []
    for statistic in STATISTICS:
        scores = aggregates[statistic][indices]
        obs = observed[statistic]
        effect = normalize_pr_effect(obs, prevalence)
        null_effect = normalize_pr_effect(null[statistic], prevalence)
        null_mean = null[statistic].mean(axis=0)
        null_sd = null[statistic].std(axis=0)
        effect_null_mean = null_effect.mean(axis=0)
        effect_null_sd = null_effect.std(axis=0)
        effect_to_variability = np.divide(
            effect - effect_null_mean,
            effect_null_sd,
            out=np.zeros_like(effect),
            where=effect_null_sd > 0,
        )
        p_max_t = (
            1 + (max_effect[:, None] >= effect[None, :]).sum(axis=0)
        ) / (permutations + 1)
        for feature in range(feature_count):
            table.append({
                "source_model": source_label,
                "feature_id": feature,
                "aggregation": statistic,
                "pr_auc": float(obs[feature]),
                "failure_prevalence": prevalence,
                "normalized_pr_effect": float(effect[feature]),
                "effect_to_variability": float(effect_to_variability[feature]),
                "null_mean": float(null_mean[feature]),
                "null_sd": float(null_sd[feature]),
                "p_maxT_across_features_and_aggregations": float(p_max_t[feature]),
                "pass_mean_score": float(scores[passed, feature].mean()),
                "fail_mean_score": float(scores[fail, feature].mean()),
                "activation_support": int((aggregates["active_fraction"][indices, feature] > 0).sum()),
                "mean_active_fraction": float(aggregates["active_fraction"][indices, feature].mean()),
                "task_activation_entropy": float(entropy[feature]),
                "decoder_base_norm": float(base_decoder_norm[feature]),
                "decoder_merged_norm": float(merged_decoder_norm[feature]),
                "decoder_base_specificity": float(decoder_specificity[feature]),
                "base_contribution_mean": float(base_contribution_mean[feature]),
                "merged_contribution_mean": float(merged_contribution_mean[feature]),
                "activation_source_base_share": float(
                    activation_source_base_share[feature]
                ),
                "first_p95_position_mean": (
                    float(finite_positions.mean())
                    if (finite_positions := aggregates["first_p95_position"][
                        indices, feature
                    ][np.isfinite(aggregates["first_p95_position"][indices, feature])]).size
                    else math.nan
                ),
                "first_quarter_activation_mean": float(
                    aggregates["first_quarter_mean"][indices, feature].mean()
                ),
                "second_quarter_activation_mean": float(
                    aggregates["second_quarter_mean"][indices, feature].mean()
                ),
            })
    ranked = sorted(
        table,
        key=lambda row: (
            row["p_maxT_across_features_and_aggregations"],
            -row["effect_to_variability"],
            -row["normalized_pr_effect"],
            -row["activation_support"],
        ),
    )
    best_per_feature: dict[int, dict[str, Any]] = {}
    for row in ranked:
        best_per_feature.setdefault(int(row["feature_id"]), row)
    candidates = list(best_per_feature.values())
    candidates.sort(
        key=lambda row: (
            row["p_maxT_across_features_and_aggregations"],
            -row["effect_to_variability"],
            -row["normalized_pr_effect"],
        )
    )
    return table, candidates


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    dtype = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
        "nf4": torch.float16,
    }[args.dtype]
    result_files = {
        args.model_a_label: args.results_root / "results" /
        f"{args.benchmark}__{args.model_a_label}_results.jsonl",
        args.model_b_label: args.results_root / "results" /
        f"{args.benchmark}__{args.model_b_label}_results.jsonl",
    }
    source_rows: list[dict[str, Any]] = []
    label_map: dict[tuple[str, str], int] = {}
    with args.labels_csv.open(newline="", encoding="utf-8") as handle:
        for label_row in csv.DictReader(handle):
            if (
                label_row["benchmark"] == args.benchmark
                and int(label_row["generation_idx"]) == 0
            ):
                label_map[(label_row["model"], label_row["task_id"])] = int(
                    label_row["label"]
                )
    for source_label, path in result_files.items():
        for row in read_jsonl(path):
            item = dict(row)
            item["source_model"] = source_label
            label_key = (source_label, item["task_id"])
            if label_key not in label_map:
                raise KeyError(f"missing evaluation label for {label_key}")
            item["failed"] = bool(label_map[label_key])
            source_rows.append(item)

    tokenizer_a = AutoTokenizer.from_pretrained(
        args.model_a_id, trust_remote_code=args.trust_remote_code,
        use_fast=True, local_files_only=True,
    )
    tokenizer_b = AutoTokenizer.from_pretrained(
        args.model_b_id, trust_remote_code=args.trust_remote_code,
        use_fast=True, local_files_only=True,
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
    common_model_args = {
        "torch_dtype": dtype,
        "trust_remote_code": args.trust_remote_code,
        "local_files_only": True,
        "attn_implementation": "eager",
    }
    if quantization_config is not None:
        common_model_args["quantization_config"] = quantization_config
        model_a = AutoModelForCausalLM.from_pretrained(
            args.model_a_id, device_map={"": args.device_a}, **common_model_args,
        ).eval()
        model_b = AutoModelForCausalLM.from_pretrained(
            args.model_b_id, device_map={"": args.device_b}, **common_model_args,
        ).eval()
    else:
        model_a = AutoModelForCausalLM.from_pretrained(
            args.model_a_id, **common_model_args,
        ).to(args.device_a).eval()
        model_b = AutoModelForCausalLM.from_pretrained(
            args.model_b_id, **common_model_args,
        ).to(args.device_b).eval()

    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    state = checkpoint["model_state_dict"]
    encoder = state["encoder.weight"].float()
    hidden_size = state["decoder_a.weight"].shape[0]
    if encoder.shape[1] != 2 * hidden_size:
        raise ValueError(
            f"encoder width {encoder.shape[1]} != 2 * hidden size {hidden_size}"
        )
    encoder_base = encoder[:, :hidden_size].to(args.device_a)
    encoder_merged = encoder[:, hidden_size:].to(args.device_a)
    bias = state["encoder.bias"].float().to(args.device_a)
    decoder_base = state["decoder_a.weight"].float()
    decoder_merged = state["decoder_b.weight"].float()
    feature_count = encoder_base.shape[0]
    base_norm = torch.linalg.vector_norm(decoder_base, dim=0).cpu().numpy()
    merged_norm = torch.linalg.vector_norm(decoder_merged, dim=0).cpu().numpy()
    base_specificity = base_norm / (base_norm + merged_norm + 1e-12)

    aggregate_lists: dict[str, list[np.ndarray]] = {
        key: [] for key in (
            *STATISTICS, "sum", "first_p95_position", "first_quarter_mean",
            "second_quarter_mean", "argmax",
        )
    }
    metadata: list[dict[str, Any]] = []
    base_contribution_sum = np.zeros(feature_count, dtype=np.float64)
    merged_contribution_sum = np.zeros(feature_count, dtype=np.float64)
    total_tokens = 0
    nonprefix_cases = []
    skipped_solutions = []
    removed_nonfinite_or_extreme_tokens = 0
    token_feature_chunks: list[np.ndarray] = []
    token_feature_offsets = [0]

    for index, row in enumerate(source_rows):
        code = row["candidate_code_repaired"]
        prompt_prefix = row["prompt"].rstrip() + "\n"
        if code.startswith(prompt_prefix):
            evaluated_start = len(prompt_prefix)
            boundary_kind = "prompt_literal_prefix"
        else:
            if row.get("extraction_strategy") != "leading_literal_prefix":
                raise ValueError(
                    f"{row['source_model']}/{row['task_id']}: candidate is not a "
                    "prompt prefix and was not a full-function replacement"
                )
            evaluated_start = 0
            boundary_kind = "full_function_replacement"
            nonprefix_cases.append(f"{row['source_model']}:{row['task_id']}")

        encoded_a = tokenizer_a(
            code, return_tensors="pt", return_offsets_mapping=True,
            add_special_tokens=True,
        )
        encoded_b = tokenizer_b(
            code, return_tensors="pt", return_offsets_mapping=True,
            add_special_tokens=True,
        )
        ids_a = encoded_a["input_ids"]
        ids_b = encoded_b["input_ids"]
        if not torch.equal(ids_a, ids_b):
            raise ValueError(f"token IDs differ for {row['source_model']}/{row['task_id']}")
        offsets = encoded_a["offset_mapping"][0].numpy()
        mask = (offsets[:, 1] > evaluated_start) & (offsets[:, 0] < len(code))
        if not mask.any():
            raise ValueError(f"no evaluated tokens for {row['source_model']}/{row['task_id']}")
        attention = torch.ones_like(ids_a)
        with torch.inference_mode():
            out_a = model_a(
                input_ids=ids_a.to(args.device_a),
                attention_mask=attention.to(args.device_a),
                output_hidden_states=True, use_cache=False, return_dict=True,
            )
            hidden_a = out_a.hidden_states[args.layer + 1][0, mask].float()
            del out_a
            out_b = model_b(
                input_ids=ids_b.to(args.device_b),
                attention_mask=attention.to(args.device_b),
                output_hidden_states=True, use_cache=False, return_dict=True,
            )
            hidden_b = out_b.hidden_states[args.layer + 1][0, mask].to(args.device_a).float()
            del out_b
            valid_tokens = (
                torch.isfinite(hidden_a).all(dim=1)
                & torch.isfinite(hidden_b).all(dim=1)
                & (torch.linalg.vector_norm(hidden_a, dim=1) < 500)
                & (torch.linalg.vector_norm(hidden_b, dim=1) < 500)
            )
            removed = int((~valid_tokens).sum().item())
            removed_nonfinite_or_extreme_tokens += removed
            if not bool(valid_tokens.any()):
                skipped_solutions.append({
                    "source_model": row["source_model"],
                    "task_id": row["task_id"],
                    "reason": "no finite paired evaluated tokens after historical norm<500 filter",
                })
                continue
            hidden_a = hidden_a[valid_tokens]
            hidden_b = hidden_b[valid_tokens]
            hidden_a = rms_normalize(hidden_a)
            hidden_b = rms_normalize(hidden_b)
            finite_a = bool(torch.isfinite(hidden_a).all())
            finite_b = bool(torch.isfinite(hidden_b).all())
            if not finite_a or not finite_b:
                raise ValueError(
                    f"non-finite normalized hidden state for "
                    f"{row['source_model']}/{row['task_id']}: "
                    f"model_a_finite={finite_a}, model_b_finite={finite_b}"
                )
            contribution_a = torch.nn.functional.linear(hidden_a, encoder_base)
            contribution_b = torch.nn.functional.linear(hidden_b, encoder_merged)
            z = torch.relu(contribution_a + contribution_b + bias)
            if not torch.isfinite(z).all():
                raise ValueError(
                    f"non-finite joint latent for {row['source_model']}/{row['task_id']}"
                )
            aggregated = aggregate_latent(z)
            if args.token_feature_ids:
                token_feature_chunks.append(
                    z[:, args.token_feature_ids].cpu().numpy().astype(np.float32)
                )
                token_feature_offsets.append(
                    token_feature_offsets[-1] + int(z.shape[0])
                )
            base_contribution_sum += contribution_a.sum(dim=0).cpu().numpy()
            merged_contribution_sum += contribution_b.sum(dim=0).cpu().numpy()
            total_tokens += len(z)
        for key, value in aggregated.items():
            aggregate_lists[key].append(value)
        selected_offsets = offsets[mask][valid_tokens.cpu().numpy()]
        metadata.append({
            "row_index": index,
            "source_model": row["source_model"],
            "task_id": row["task_id"],
            "task_idx": row["task_idx"],
            "failed": bool(row["failed"]),
            "boundary_kind": boundary_kind,
            "evaluated_start_character": evaluated_start,
            "evaluated_token_count": int(mask.sum()),
            "retained_paired_token_count": int(valid_tokens.sum().item()),
            "removed_nonfinite_or_extreme_token_count": removed,
            "candidate_code_repaired": code,
            "selected_token_offsets": selected_offsets.tolist(),
        })
        if (index + 1) % 20 == 0 or index + 1 == len(source_rows):
            print(f"[{index + 1}/{len(source_rows)}] {row['source_model']} {row['task_id']}", flush=True)

    aggregates = {key: np.stack(values) for key, values in aggregate_lists.items()}
    labels = np.asarray([int(row["failed"]) for row in metadata], dtype=np.int8)
    base_contribution_mean = base_contribution_sum / total_tokens
    merged_contribution_mean = merged_contribution_sum / total_tokens
    base_solution_indices = np.asarray([
        i for i, row in enumerate(metadata)
        if row["source_model"] == args.model_a_label
    ])
    merged_solution_indices = np.asarray([
        i for i, row in enumerate(metadata)
        if row["source_model"] == args.model_b_label
    ])
    base_activation_sum = aggregates["sum"][base_solution_indices].sum(axis=0)
    merged_activation_sum = aggregates["sum"][merged_solution_indices].sum(axis=0)
    activation_source_base_share = np.divide(
        base_activation_sum,
        base_activation_sum + merged_activation_sum,
        out=np.full(feature_count, 0.5, dtype=np.float64),
        where=(base_activation_sum + merged_activation_sum) > 0,
    )
    np.savez_compressed(
        args.output_dir / "solution_feature_aggregates.npz",
        **aggregates,
        labels=labels,
    )
    (args.output_dir / "solution_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False) + "\n"
    )
    if args.token_feature_ids:
        np.savez_compressed(
            args.output_dir / "selected_token_feature_values.npz",
            feature_ids=np.asarray(args.token_feature_ids, dtype=np.int32),
            values=np.concatenate(token_feature_chunks, axis=0),
            solution_offsets=np.asarray(token_feature_offsets, dtype=np.int64),
        )

    if args.capture_only:
        summary = {
            "models": [args.model_a_id, args.model_b_id],
            "benchmark": args.benchmark,
            "layer": args.layer,
            "crosscoder_checkpoint": str(args.checkpoint),
            "n_solutions": len(metadata),
            "n_base_solutions": int(len(base_solution_indices)),
            "n_merged_solutions": int(len(merged_solution_indices)),
            "token_feature_ids": args.token_feature_ids,
            "nonprefix_full_function_cases": nonprefix_cases,
            "skipped_solutions": skipped_solutions,
            "removed_nonfinite_or_extreme_tokens": removed_nonfinite_or_extreme_tokens,
            "capture_only": True,
            "elapsed_seconds": time.perf_counter() - started,
        }
        (args.output_dir / "run_summary.json").write_text(
            json.dumps(summary, indent=2) + "\n"
        )
        print(json.dumps(summary, indent=2))
        return 0

    all_tables = []
    all_candidates = []
    for source_offset, source_label in enumerate((args.model_a_label, args.model_b_label)):
        indices = np.asarray([
            i for i, row in enumerate(metadata) if row["source_model"] == source_label
        ])
        table, candidates = screen_source(
            source_label, indices, labels, aggregates, base_specificity,
            base_norm, merged_norm, base_contribution_mean,
            merged_contribution_mean, activation_source_base_share, args.permutations,
            args.seed + source_offset,
        )
        all_tables.extend(table)
        all_candidates.extend(candidates[:args.top_features])
    write_csv(args.output_dir / "feature_aggregation_statistics.csv", all_tables)
    write_csv(args.output_dir / "top_feature_candidates.csv", all_candidates)

    context_rows = []
    for candidate in all_candidates:
        source_label = candidate["source_model"]
        feature = int(candidate["feature_id"])
        source_indices = [
            i for i, row in enumerate(metadata) if row["source_model"] == source_label
        ]
        ranked_solutions = sorted(
            source_indices,
            key=lambda i: aggregates["max"][i, feature], reverse=True,
        )[:args.contexts_per_feature]
        for rank, solution_index in enumerate(ranked_solutions, 1):
            item = metadata[solution_index]
            local_token = int(aggregates["argmax"][solution_index, feature])
            start, end = item["selected_token_offsets"][local_token]
            code = item["candidate_code_repaired"]
            context_rows.append({
                "source_model": source_label,
                "feature_id": feature,
                "selected_aggregation": candidate["aggregation"],
                "candidate_rank_context": rank,
                "task_id": item["task_id"],
                "failed": item["failed"],
                "max_activation": float(aggregates["max"][solution_index, feature]),
                "normalized_token_position": local_token / max(
                    1, item["retained_paired_token_count"] - 1
                ),
                "token_text": code[start:end],
                "context": code[max(0, start - 120):min(len(code), end + 120)].replace("\n", "\\n"),
            })
    write_csv(args.output_dir / "top_feature_contexts.csv", context_rows)

    summary = {
        "models": [args.model_a_id, args.model_b_id],
        "benchmark": args.benchmark,
        "layer": args.layer,
        "crosscoder_checkpoint": str(args.checkpoint),
        "n_solutions": len(metadata),
        "n_base_solutions": sum(row["source_model"] == args.model_a_label for row in metadata),
        "n_merged_solutions": sum(row["source_model"] == args.model_b_label for row in metadata),
        "identical_token_ids_required": True,
        "nonprefix_full_function_cases": nonprefix_cases,
        "skipped_solutions": skipped_solutions,
        "removed_nonfinite_or_extreme_tokens": removed_nonfinite_or_extreme_tokens,
        "token_scope": "evaluated generated code; prompt excluded unless full-function replacement",
        "latent": "relu(rms(x_base) @ D_base.T + rms(x_merged) @ D_target.T + b_enc)",
        "statistics": list(STATISTICS),
        "permutations": args.permutations,
        "seed": args.seed,
        "failure_positive_class": True,
        "elapsed_seconds": time.perf_counter() - started,
    }
    (args.output_dir / "run_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
