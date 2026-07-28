#!/usr/bin/env python3
"""Bidirectional PR-AUC screening for CrossCoder latents."""
from __future__ import annotations

import argparse
import csv
import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from crosscoder_common import (
    compute_latent_summary,
    derive_legacy_evaluated_token_mask,
    index_activation_files,
    load_checkpoint_encoder,
    load_evaluated_token_mask,
    load_layer,
    normalize_benchmark,
    normalize_task_id,
)
from audit_evaluation_pipeline import Source, jsonl


def rank_columns(values: np.ndarray) -> np.ndarray:
    n, p = values.shape
    ranks = np.empty((n, p), dtype=np.float32)
    for j in range(p):
        order = np.argsort(values[:, j], kind="mergesort")
        sorted_values = values[order, j]
        start = 0
        while start < n:
            end = start + 1
            while end < n and sorted_values[end] == sorted_values[start]:
                end += 1
            ranks[order[start:end], j] = ((start + 1) + end) / 2.0
            start = end
    return ranks


def auc_from_ranks(ranks: np.ndarray, labels: np.ndarray) -> np.ndarray:
    n_failure = int(labels.sum())
    n_pass = len(labels) - n_failure
    if not n_failure or not n_pass:
        raise ValueError("ROC-AUC requires both passing and failing solutions")
    rank_sum = ranks[labels == 1].sum(axis=0, dtype=np.float64)
    return (rank_sum - n_failure * (n_failure + 1) / 2.0) / (n_failure * n_pass)


def read_labels(path: Path) -> dict[tuple[str, str, str, int], int]:
    labels: dict[tuple[str, str, str, int], int] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"model", "benchmark", "task_id", "generation_idx", "label"}
        if not required <= set(reader.fieldnames or []):
            raise ValueError(f"{path}: labels must contain {sorted(required)}")
        for line, row in enumerate(reader, 2):
            key = (
                row["model"].strip(), normalize_benchmark(row["benchmark"]),
                normalize_task_id(row["task_id"]), int(row["generation_idx"]),
            )
            value = int(row["label"])
            if value not in (0, 1):
                raise ValueError(f"{path}:{line}: label must be 0 or 1")
            if key in labels:
                raise ValueError(f"{path}:{line}: duplicate solution label {key}")
            labels[key] = value
    return labels


def describe(values: np.ndarray, labels: np.ndarray) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {
        "activation_count": (values > 0).sum(axis=0),
        "activation_proportion": (values > 0).mean(axis=0),
        "unique_values": np.asarray([len(np.unique(values[:, j])) for j in range(values.shape[1])]),
        "mean": values.mean(axis=0), "median": np.median(values, axis=0),
        "maximum": values.max(axis=0),
    }
    for q in (0.05, 0.25, 0.75, 0.95):
        out[f"q{int(q*100):02d}"] = np.quantile(values, q, axis=0)
    for label, name in ((0, "pass"), (1, "fail")):
        group = values[labels == label]
        out[f"{name}_mean"] = group.mean(axis=0)
        out[f"{name}_median"] = np.median(group, axis=0)
        out[f"{name}_maximum"] = group.max(axis=0)
    return out


def prepare_pr_order(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Precompute descending orders and tie-group ends for exact average precision."""
    order = np.argsort(-values, axis=0, kind="stable").T.astype(np.int32)
    sorted_values = np.take_along_axis(values.T, order, axis=1)
    group_end = np.ones_like(order, dtype=np.bool_)
    group_end[:, :-1] = sorted_values[:, :-1] != sorted_values[:, 1:]
    return order, group_end


def _pr_kernel():
    try:
        from numba import njit, prange
    except ImportError as exc:
        raise RuntimeError("PR-AUC permutation analysis requires numba") from exc

    @njit(parallel=True, cache=True)
    def kernel(order, group_end, labels):
        features, n = order.shape
        n_failure = 0
        for i in range(n):
            n_failure += labels[i]
        n_success = n - n_failure
        failure = np.empty(features, dtype=np.float64)
        success = np.empty(features, dtype=np.float64)
        for feature in prange(features):
            cum_failure = 0
            previous_failure = 0
            previous_total = 0
            ap_failure = 0.0
            ap_success = 0.0
            for rank in range(n):
                cum_failure += labels[order[feature, rank]]
                if group_end[feature, rank]:
                    group_failure = cum_failure - previous_failure
                    cum_success = (rank + 1) - cum_failure
                    previous_success = previous_total - previous_failure
                    group_success = cum_success - previous_success
                    if group_failure:
                        ap_failure += (cum_failure / (rank + 1)) * (group_failure / n_failure)
                    if group_success:
                        ap_success += (cum_success / (rank + 1)) * (group_success / n_success)
                    previous_failure = cum_failure
                    previous_total = rank + 1
            failure[feature] = ap_failure
            success[feature] = ap_success
        return failure, success

    return kernel


def pr_auc_both(
    order: np.ndarray, group_end: np.ndarray, labels: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    if not hasattr(pr_auc_both, "_kernel"):
        pr_auc_both._kernel = _pr_kernel()  # type: ignore[attr-defined]
    return pr_auc_both._kernel(order, group_end, labels)  # type: ignore[attr-defined]


def normalize_pr_effect(pr_auc: np.ndarray, prevalence: float) -> np.ndarray:
    return (pr_auc - prevalence) / (1.0 - prevalence)


def pr_permutation_statistics(
    order: np.ndarray, group_end: np.ndarray, labels: np.ndarray,
    observed_failure: np.ndarray, observed_success: np.ndarray,
    permutations: int, seed: int, work_dir: Path,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    p = order.shape[0]
    failure_path = work_dir / "failure_null.float32"
    success_path = work_dir / "success_null.float32"
    failure_null = np.memmap(failure_path, mode="w+", dtype=np.float32, shape=(permutations, p))
    success_null = np.memmap(success_path, mode="w+", dtype=np.float32, shape=(permutations, p))
    failure_baseline = float(labels.mean())
    success_baseline = 1.0 - failure_baseline
    max_effect = np.empty(permutations, dtype=np.float64)
    for permutation in range(permutations):
        permuted = rng.permutation(labels)
        failure, success = pr_auc_both(order, group_end, permuted)
        failure_null[permutation] = failure
        success_null[permutation] = success
        failure_effect = normalize_pr_effect(failure, failure_baseline)
        success_effect = normalize_pr_effect(success, success_baseline)
        max_effect[permutation] = max(
            0.0, float(failure_effect.max()), float(success_effect.max())
        )
    failure_null.flush(); success_null.flush()
    observed_failure_effect = normalize_pr_effect(observed_failure, failure_baseline)
    observed_success_effect = normalize_pr_effect(observed_success, success_baseline)
    selected_effect = np.maximum(observed_failure_effect, observed_success_effect)
    p_max = (
        1 + (max_effect[:, None] >= selected_effect[None, :]).sum(axis=0)
    ) / (permutations + 1)

    result = {"p_maxT": p_max}
    for name, null, baseline in (
        ("failure", failure_null, failure_baseline),
        ("success", success_null, success_baseline),
    ):
        effect_null = normalize_pr_effect(np.asarray(null), baseline)
        result[f"{name}_null_mean"] = np.asarray(null.mean(axis=0))
        result[f"{name}_null_sd"] = np.asarray(null.std(axis=0))
        result[f"{name}_effect_null_mean"] = effect_null.mean(axis=0)
        result[f"{name}_effect_null_sd"] = effect_null.std(axis=0)
        ranked = np.sort(np.asarray(null), axis=1)
        result[f"{name}_ranked_mean"] = ranked.mean(axis=0)
        result[f"{name}_ranked_lower"] = np.quantile(ranked, .025, axis=0)
        result[f"{name}_ranked_upper"] = np.quantile(ranked, .975, axis=0)
    del failure_null, success_null
    failure_path.unlink(missing_ok=True); success_path.unlink(missing_ok=True)
    return result


def write_csv(
    path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text(",".join(fieldnames or []) + "\n", encoding="utf-8"); return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader(); writer.writerows(rows)


def plot_case(path: Path, failure: np.ndarray, success: np.ndarray,
              null: dict[str, np.ndarray], feature_ids: np.ndarray,
              top_five: list[dict[str, Any]], failure_baseline: float,
              success_baseline: float) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(14, 10), sharex=True)
    selected = {int(row["feature_id"]): row for row in top_five}
    for ax, name, observed, baseline, color in (
        (axes[0], "failure", failure, failure_baseline, "#cb181d"),
        (axes[1], "success", success, success_baseline, "#238b45"),
    ):
        order = np.argsort(observed); y = observed[order]; ids = feature_ids[order]
        x = np.arange(len(y))
        lower = null[f"{name}_ranked_lower"]; upper = null[f"{name}_ranked_upper"]
        ax.fill_between(x, lower, upper, color="#9ecae1", alpha=.5, label="95% ranked permutation envelope")
        ax.plot(x, null[f"{name}_ranked_mean"], color="#3182bd", linewidth=1, label="permutation mean")
        ax.scatter(x, y, s=7, color="#555", alpha=.65, label="observed PR-AUC")
        positions = {int(feature): rank for rank, feature in enumerate(ids)}
        marked = [
            row for row in top_five
            if row["selected_direction"] == f"high_activation_associated_with_{name}"
        ]
        for row in marked:
            rank = positions[int(row["feature_id"])]
            ax.scatter(rank, y[rank], s=55, color=color, edgecolor="black", zorder=4)
            ax.annotate(
                f"{row['feature_id']} (E/V={row['selected_effect_to_variability']:.1f})",
                (rank, y[rank]), fontsize=8, xytext=(4, 5), textcoords="offset points",
            )
        ax.axhline(baseline, color="black", linestyle="--", linewidth=1, label=f"class prevalence={baseline:.3f}")
        ax.set(ylabel=f"{name.title()} PR-AUC", ylim=(-.02, 1.02))
        ax.legend(fontsize=8, loc="best")
    axes[-1].set_xlabel("Feature rank")
    fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, default=Path("manifests/paper_v1_extraction_v4.json"))
    p.add_argument(
        "--activation-root", type=Path, action="append", required=True,
        help="Canonical activation root; repeat for materialized roots split by model family.",
    )
    p.add_argument("--checkpoint-root", type=Path, required=True)
    p.add_argument("--labels-csv", type=Path, required=True)
    p.add_argument(
        "--dataset",
        help="Raw/repaired dataset root used for exact legacy mask reconstruction.",
    )
    p.add_argument("--output-root", type=Path, default=Path("reports/pr_auc_feature_screening"))
    p.add_argument("--permutations", type=int, default=200)
    p.add_argument("--smoke-test", action="store_true", help="Use 20 permutations and at most 48 examples per case")
    p.add_argument("--minimum-activation-count", type=int, default=5)
    p.add_argument("--minimum-activation-proportion", type=float, default=.01)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--device", default="cpu")
    return p.parse_args()


def load_historical_tokenizer(model_name: str):
    """Mirror the tokenizer construction used by run_recatcher_benchmarks.py."""
    from transformers import AutoTokenizer, PreTrainedTokenizerFast
    if "deepseek" in model_name.lower() or "ds-trinity" in model_name.lower():
        return PreTrainedTokenizerFast.from_pretrained(
            model_name,
            trust_remote_code=True,
            bos_token="<｜begin▁of▁sentence｜>",
            eos_token="<｜end▁of▁sentence｜>",
            pad_token="<｜end▁of▁sentence｜>",
            local_files_only=True,
        )
    return AutoTokenizer.from_pretrained(
        model_name, trust_remote_code=True, use_fast=True, local_files_only=True
    )


def discover_activation_index(roots: list[Path], benchmark: str, model: str):
    errors = []
    for root in roots:
        try:
            return index_activation_files(root / benchmark, model)
        except FileNotFoundError as exc:
            errors.append(str(exc))
    raise FileNotFoundError(
        f"No activation files for {benchmark}/{model} in declared roots: {errors}"
    )


def main() -> int:
    args = parse_args(); manifest = json.loads(args.manifest.read_text())
    B = 20 if args.smoke_test else args.permutations
    labels = read_labels(args.labels_csv); output = args.output_root; output.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []; candidates: list[dict[str, Any]] = []; skipped: list[dict[str, Any]] = []
    source = Source(args.dataset) if args.dataset else None
    result_cache: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    tokenizer_cache: dict[str, Any] = {}
    layer = int(str(manifest["crosscoder_contract"]["layer"]).split("_")[-1])
    for cc in manifest["crosscoders"]:
        checkpoint = args.checkpoint_root / cc["id"] / "final.pt"
        if not checkpoint.exists(): checkpoint = args.checkpoint_root / f"{cc['id']}.pt"
        for benchmark in manifest["benchmarks"]:
            for side, target in (("a", cc["model_a"]), ("b", cc["model_b"])):
                case_id = f"{cc['id']}__{side}_{target}__{benchmark}__layer{layer}__evaluated_tokens"
                case_dir = output / case_id
                try:
                    if not checkpoint.exists(): raise FileNotFoundError(f"checkpoint not found: {checkpoint}")
                    index_a = discover_activation_index(args.activation_root, benchmark, cc["model_a"])
                    index_b = discover_activation_index(args.activation_root, benchmark, cc["model_b"])
                    wanted = {k: v for k, v in labels.items() if k[0] == target and k[1] == benchmark}
                    if not wanted: raise ValueError("no labels for model/benchmark")
                    weight, bias, _ = load_checkpoint_encoder(checkpoint)
                    rows = []; ys = []; negatives = 0; latent_values = 0; minimum = math.inf
                    legacy_masks = 0; nonprefix_masks = 0; solution_skips = []
                    if source is not None:
                        cache_key = (benchmark, target)
                        if cache_key not in result_cache:
                            stem = f"{benchmark}__{target}"
                            raw_rows = jsonl(source.read(f"raw_results/{stem}_results.jsonl"))
                            repaired_rows = jsonl(source.read(f"results/{stem}_results.jsonl"))
                            raw_by_task = {normalize_task_id(r["task_id"]): r for r in raw_rows}
                            repaired_by_task = {normalize_task_id(r["task_id"]): r for r in repaired_rows}
                            if len(raw_by_task) != len(raw_rows) or len(repaired_by_task) != len(repaired_rows):
                                raise ValueError("duplicate raw or repaired task IDs")
                            if set(raw_by_task) != set(repaired_by_task):
                                raise ValueError("raw/repaired task IDs differ")
                            result_cache[cache_key] = (raw_by_task, repaired_by_task)
                        if target not in tokenizer_cache:
                            tokenizer_cache[target] = load_historical_tokenizer(manifest["models"][target])
                    label_keys = sorted(wanted, key=lambda k: (int(k[2]), k[3]))
                    if args.smoke_test: label_keys = label_keys[:48]
                    for label_key in label_keys:
                        try:
                            _, _, task_id, gen = label_key
                            matches = [k for k in index_a if str(k.task_idx) == task_id and k.gen_idx == gen]
                            if len(matches) != 1: raise ValueError(f"activation task mismatch: matches={len(matches)}")
                            key = matches[0]
                            if key not in index_b: raise ValueError(f"paired activation missing for {key}")
                            a = load_layer(index_a[key], layer); b = load_layer(index_b[key], layer)
                            target_array = a if side == "a" else b
                            target_path = index_a[key] if side == "a" else index_b[key]
                            used_legacy = False
                            was_nonprefix = False
                            try:
                                mask = load_evaluated_token_mask(target_path, len(target_array))
                            except KeyError:
                                if source is None:
                                    raise
                                raw_by_task, repaired_by_task = result_cache[(benchmark, target)]
                                if task_id not in raw_by_task:
                                    raise KeyError(f"missing raw/repaired row for task {task_id}")
                                mask, provenance = derive_legacy_evaluated_token_mask(
                                    target_path, len(target_array), raw_by_task[task_id],
                                    repaired_by_task[task_id], tokenizer_cache[target],
                                )
                                used_legacy = True
                                was_nonprefix = not provenance["literal_prefix"]
                            n = min(len(a), len(b)); summary = compute_latent_summary(
                                a, b, weight, bias, "max", args.device, token_mask=mask[-n:]
                            )
                            legacy_masks += int(used_legacy)
                            nonprefix_masks += int(was_nonprefix)
                            minimum = min(minimum, float(summary.min())); negatives += int((summary < -1e-8).sum()); latent_values += summary.size
                            rows.append(summary); ys.append(wanted[label_key])
                        except Exception as exc:
                            solution_skips.append({
                                "label_key": repr(label_key),
                                "reason": f"{type(exc).__name__}: {exc}",
                            })
                    if not rows:
                        raise ValueError(f"no aligned solutions; first errors={solution_skips[:3]}")
                    X = np.stack(rows); y = np.asarray(ys, dtype=np.int8)
                    if len(np.unique(y)) != 2: raise ValueError("labels contain only one class")
                    stats = describe(X, y); valid = stats["unique_values"] > 1
                    valid_ids = np.flatnonzero(valid)
                    order, group_end = prepare_pr_order(X[:, valid])
                    observed_failure, observed_success = pr_auc_both(order, group_end, y)
                    failure_baseline = float(y.mean())
                    success_baseline = 1.0 - failure_baseline
                    failure_effect = normalize_pr_effect(observed_failure, failure_baseline)
                    success_effect = normalize_pr_effect(observed_success, success_baseline)
                    with tempfile.TemporaryDirectory(prefix="pr_auc_null_") as temp:
                        null = pr_permutation_statistics(
                            order, group_end, y, observed_failure, observed_success,
                            B, args.seed, Path(temp),
                        )
                    failure_ev = np.divide(
                        failure_effect - null["failure_effect_null_mean"],
                        null["failure_effect_null_sd"],
                        out=np.zeros_like(failure_effect),
                        where=null["failure_effect_null_sd"] > 0,
                    )
                    success_ev = np.divide(
                        success_effect - null["success_effect_null_mean"],
                        null["success_effect_null_sd"],
                        out=np.zeros_like(success_effect),
                        where=null["success_effect_null_sd"] > 0,
                    )
                    table = []
                    for j in range(X.shape[1]):
                        pos = np.flatnonzero(valid_ids == j)
                        is_valid = bool(valid[j]); k = int(pos[0]) if len(pos) else -1
                        if is_valid and max(failure_ev[k], success_ev[k]) > 0:
                            choose_failure = failure_ev[k] >= success_ev[k]
                            direction = (
                                "high_activation_associated_with_failure"
                                if choose_failure else "high_activation_associated_with_success"
                            )
                        else:
                            choose_failure = True
                            direction = "neutral_or_degenerate"
                        selected_auc = (
                            float(observed_failure[k] if choose_failure else observed_success[k])
                            if is_valid else None
                        )
                        selected_effect = (
                            float(failure_effect[k] if choose_failure else success_effect[k])
                            if is_valid else None
                        )
                        selected_ev = (
                            float(failure_ev[k] if choose_failure else success_ev[k])
                            if is_valid else None
                        )
                        support_ok = bool(
                            stats["activation_count"][j] >= args.minimum_activation_count
                            and stats["activation_proportion"][j] >= args.minimum_activation_proportion
                        )
                        row = {"feature_id": j,
                               "failure_pr_auc": float(observed_failure[k]) if is_valid else None,
                               "failure_baseline": failure_baseline,
                               "failure_normalized_effect": float(failure_effect[k]) if is_valid else None,
                               "failure_null_mean": float(null["failure_null_mean"][k]) if is_valid else None,
                               "failure_null_sd": float(null["failure_null_sd"][k]) if is_valid else None,
                               "failure_effect_null_mean": float(null["failure_effect_null_mean"][k]) if is_valid else None,
                               "failure_effect_null_sd": float(null["failure_effect_null_sd"][k]) if is_valid else None,
                               "failure_effect_to_variability": float(failure_ev[k]) if is_valid else None,
                               "success_pr_auc": float(observed_success[k]) if is_valid else None,
                               "success_baseline": success_baseline,
                               "success_normalized_effect": float(success_effect[k]) if is_valid else None,
                               "success_null_mean": float(null["success_null_mean"][k]) if is_valid else None,
                               "success_null_sd": float(null["success_null_sd"][k]) if is_valid else None,
                               "success_effect_null_mean": float(null["success_effect_null_mean"][k]) if is_valid else None,
                               "success_effect_null_sd": float(null["success_effect_null_sd"][k]) if is_valid else None,
                               "success_effect_to_variability": float(success_ev[k]) if is_valid else None,
                               "selected_direction": direction, "selected_pr_auc": selected_auc,
                               "selected_normalized_effect": selected_effect,
                               "selected_effect_to_variability": selected_ev,
                               "p_maxT": float(null["p_maxT"][k]) if is_valid else None,
                               "support_ok": support_ok,
                               "activation_count": int(stats["activation_count"][j]), "activation_proportion": float(stats["activation_proportion"][j]),
                               "unique_aggregated_values": int(stats["unique_values"][j]), "mean": float(stats["mean"][j]), "median": float(stats["median"][j]),
                               "maximum": float(stats["maximum"][j]), "q05": float(stats["q05"][j]), "q25": float(stats["q25"][j]), "q75": float(stats["q75"][j]), "q95": float(stats["q95"][j]),
                               "pass_mean": float(stats["pass_mean"][j]), "pass_median": float(stats["pass_median"][j]), "pass_maximum": float(stats["pass_maximum"][j]),
                               "fail_mean": float(stats["fail_mean"][j]), "fail_median": float(stats["fail_median"][j]), "fail_maximum": float(stats["fail_maximum"][j])}
                        table.append(row)
                    case_dir.mkdir(parents=True, exist_ok=True); write_csv(case_dir / "feature_statistics.csv", table)
                    eligible = [
                        row for row in table
                        if row["support_ok"] and row["selected_direction"] != "neutral_or_degenerate"
                        and row["selected_normalized_effect"] > 0
                    ]
                    top_five = sorted(
                        eligible,
                        key=lambda row: (
                            row["selected_effect_to_variability"],
                            row["selected_normalized_effect"],
                        ),
                        reverse=True,
                    )[:5]
                    plot_case(
                        case_dir / "ranked_pr_auc_permutation_envelope.png",
                        observed_failure, observed_success, null, valid_ids, top_five,
                        failure_baseline, success_baseline,
                    )
                    for rank, row in enumerate(top_five, 1):
                        candidates.append({"case_id": case_id, "rank": rank, **row})
                    summaries.append({"case_id": case_id, "crosscoder_run": cc["id"], "model_pair": f"{cc['model_a']} vs {cc['model_b']}", "model_side": side,
                                      "model": target, "benchmark": benchmark, "layer": layer, "token_scope": "evaluated_tokens", "n_solutions": len(y),
                                      "n_failures": int(y.sum()), "failure_prevalence": float(y.mean()), "permutations": B, "seed": args.seed,
                                      "minimum_latent_activation": minimum, "fraction_below_minus_1e_8": negatives / latent_values,
                                      "legacy_masks_reconstructed": legacy_masks, "nonprefix_legacy_masks": nonprefix_masks,
                                      "skipped_solutions": len(solution_skips),
                                      "skipped_solution_reasons": json.dumps(solution_skips, ensure_ascii=False),
                                      "degenerate_features": int((~valid).sum()),
                                      "top_five": "; ".join(
                                          f"{r['feature_id']} ({r['selected_direction'].removeprefix('high_activation_associated_with_')}, "
                                          f"PR={r['selected_pr_auc']:.4f}, lift={r['selected_normalized_effect']:.4f}, "
                                          f"E/V={r['selected_effect_to_variability']:.2f}, p_maxT={r['p_maxT']:.4f})"
                                          for r in top_five
                                      )})
                except Exception as exc:
                    skipped.append({"case_id": case_id, "crosscoder_run": cc["id"], "model": target, "benchmark": benchmark, "reason": f"{type(exc).__name__}: {exc}"})
    write_csv(
        output / "all_cases_summary.csv", summaries,
        ["case_id", "crosscoder_run", "model_pair", "model_side", "model", "benchmark", "layer", "token_scope", "n_solutions", "n_failures", "failure_prevalence", "permutations", "seed", "minimum_latent_activation", "fraction_below_minus_1e_8", "legacy_masks_reconstructed", "nonprefix_legacy_masks", "skipped_solutions", "skipped_solution_reasons", "degenerate_features", "top_five"],
    )
    write_csv(
        output / "top_feature_candidates.csv", candidates,
        ["case_id", "rank", "feature_id", "failure_pr_auc", "failure_baseline", "failure_normalized_effect", "failure_null_mean", "failure_null_sd", "failure_effect_null_mean", "failure_effect_null_sd", "failure_effect_to_variability", "success_pr_auc", "success_baseline", "success_normalized_effect", "success_null_mean", "success_null_sd", "success_effect_null_mean", "success_effect_null_sd", "success_effect_to_variability", "selected_direction", "selected_pr_auc", "selected_normalized_effect", "selected_effect_to_variability", "p_maxT", "support_ok", "activation_count", "activation_proportion"],
    )
    lines = ["# Bidirectional PR-AUC feature screening", "",
             f"Permutation count: **{B}**; seed: **{args.seed}**.", "",
             "Failure and success are analyzed as separate positive classes. Raw PR-AUC is interpreted relative to each class prevalence. "
             "The normalized effect is `(PR-AUC - prevalence) / (1 - prevalence)`. "
             "`E/V` is `(observed normalized effect - permutation mean) / permutation SD`; it is a permutation signal-to-noise score, not a Gaussian z-test.", "",
             f"Top-five support filter: activation count ≥ {args.minimum_activation_count} and activation proportion ≥ {args.minimum_activation_proportion:.3f}.", "",
             "## Analyzed cases", ""]
    for s in summaries:
        rel = s["case_id"]
        lines += [f"### `{rel}`", "", f"n={s['n_solutions']}; failure prevalence={s['failure_prevalence']:.3f}; degenerate features={s['degenerate_features']}; skipped solutions={s['skipped_solutions']}; reconstructed legacy masks={s['legacy_masks_reconstructed']}; non-prefix masks={s['nonprefix_legacy_masks']}.", "",
                  f"Top five by E/V: {s['top_five'] or 'none eligible'}", "",
                  f"[Figure]({rel}/ranked_pr_auc_permutation_envelope.png) · [Feature table]({rel}/feature_statistics.csv)", ""]
    lines += ["## Skipped cases", ""] + [f"- `{s['case_id']}` — {s['reason']}" for s in skipped]
    lines += ["", "## Warnings", "", "Exact v4 extraction spans and stored-token-ID equality are required for reconstructed masks.", "", "Raw failure and success PR-AUC values are not directly comparable because their prevalence baselines differ; compare normalized effect or E/V.", "", "The ranked 95% envelopes are exploratory. `p_maxT` uses the maximum positive normalized effect across both directions and all valid features in each permutation.", "", f"With {B} permutations, the minimum attainable p_maxT is 1/{B + 1} ≈ {1 / (B + 1):.5f}."]
    (output / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "skipped_cases.json").write_text(json.dumps(skipped, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"analyzed": len(summaries), "skipped": len(skipped), "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
