#!/usr/bin/env python3
"""Strict, manifest-discovered ROC-AUC screening for CrossCoder latents."""
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


def permutation_statistics(
    ranks: np.ndarray, labels: np.ndarray, observed: np.ndarray, permutations: int,
    seed: int, work_dir: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    p = ranks.shape[1]
    null_sum = np.zeros(p); null_sumsq = np.zeros(p)
    max_effect = np.empty(permutations)
    ranked_path = work_dir / "ranked_null.float32"
    ranked = np.memmap(ranked_path, mode="w+", dtype=np.float32, shape=(permutations, p))
    for b in range(permutations):
        perm_auc = auc_from_ranks(ranks, rng.permutation(labels))
        null_sum += perm_auc; null_sumsq += perm_auc * perm_auc
        max_effect[b] = np.max(np.abs(perm_auc - 0.5))
        ranked[b] = np.sort(perm_auc).astype(np.float32)
    ranked.flush()
    null_mean = null_sum / permutations
    null_sd = np.sqrt(np.maximum(0, null_sumsq / permutations - null_mean**2))
    effect = np.abs(observed - 0.5)
    p_max = (1 + (max_effect[:, None] >= effect[None, :]).sum(axis=0)) / (permutations + 1)
    env_mean = np.asarray(ranked.mean(axis=0)); lower = np.asarray(np.quantile(ranked, .025, axis=0))
    upper = np.asarray(np.quantile(ranked, .975, axis=0))
    del ranked
    ranked_path.unlink(missing_ok=True)
    return null_mean, null_sd, p_max, env_mean, lower, upper


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


def plot_case(path: Path, observed: np.ndarray, lower: np.ndarray, upper: np.ndarray,
              mean: np.ndarray, feature_ids: np.ndarray) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    order = np.argsort(observed); y = observed[order]; ids = feature_ids[order]
    x = np.arange(len(y)); below = y < lower; above = y > upper
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.fill_between(x, lower, upper, color="#9ecae1", alpha=.55, label="95% ranked permutation envelope")
    ax.plot(x, mean, color="#3182bd", linewidth=1, label="permutation mean")
    ax.scatter(x, y, s=7, color="#555", alpha=.7, label="observed")
    ax.scatter(x[below], y[below], s=18, color="#238b45", label="below envelope (success-associated)")
    ax.scatter(x[above], y[above], s=18, color="#cb181d", label="above envelope (failure-associated)")
    ax.axhline(.5, color="black", linestyle="--", linewidth=1)
    extremes = np.r_[np.arange(min(3, len(y))), np.arange(max(0, len(y)-3), len(y))]
    for idx in np.unique(extremes):
        ax.annotate(str(int(ids[idx])), (x[idx], y[idx]), fontsize=7, xytext=(2, 3), textcoords="offset points")
    ax.set(xlabel="Feature rank", ylabel="ROC-AUC", ylim=(-.02, 1.02))
    ax.legend(fontsize=8, loc="best"); fig.tight_layout(); fig.savefig(path, dpi=180); plt.close(fig)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, default=Path("manifests/paper_v1.json"))
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
    p.add_argument("--output-root", type=Path, default=Path("reports/roc_auc_feature_screening"))
    p.add_argument("--permutations", type=int, default=5000)
    p.add_argument("--smoke-test", action="store_true", help="Use 200 permutations and at most 24 examples per case")
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
    B = 200 if args.smoke_test else args.permutations
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
                    if args.smoke_test: label_keys = label_keys[:24]
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
                    ranks = rank_columns(X); observed = auc_from_ranks(ranks, y)
                    stats = describe(X, y); valid = stats["unique_values"] > 1
                    observed[~valid] = np.nan
                    with tempfile.TemporaryDirectory(prefix="roc_auc_null_") as temp:
                        nm, ns, pm, em, lo, hi = permutation_statistics(ranks[:, valid], y, observed[valid], B, args.seed, Path(temp))
                    valid_ids = np.flatnonzero(valid); sorted_valid = np.argsort(observed[valid])
                    rank_position = np.empty(len(valid_ids), dtype=int); rank_position[sorted_valid] = np.arange(len(valid_ids))
                    table = []
                    for j in range(X.shape[1]):
                        pos = np.flatnonzero(valid_ids == j)
                        is_valid = bool(valid[j]); k = int(pos[0]) if len(pos) else -1
                        auc = float(observed[j]) if is_valid else None
                        direction = "neutral_or_degenerate" if not is_valid or abs(auc-.5) < 1e-12 else ("high_activation_associated_with_failure" if auc > .5 else "high_activation_associated_with_success")
                        row = {"feature_id": j, "observed_roc_auc": auc, "signed_auc_effect": auc-.5 if is_valid else None,
                               "absolute_auc_effect": abs(auc-.5) if is_valid else None, "null_mean": float(nm[k]) if is_valid else None,
                               "null_sd": float(ns[k]) if is_valid else None, "p_maxT": float(pm[k]) if is_valid else None,
                               "activation_count": int(stats["activation_count"][j]), "activation_proportion": float(stats["activation_proportion"][j]),
                               "unique_aggregated_values": int(stats["unique_values"][j]), "mean": float(stats["mean"][j]), "median": float(stats["median"][j]),
                               "maximum": float(stats["maximum"][j]), "q05": float(stats["q05"][j]), "q25": float(stats["q25"][j]), "q75": float(stats["q75"][j]), "q95": float(stats["q95"][j]),
                               "pass_mean": float(stats["pass_mean"][j]), "pass_median": float(stats["pass_median"][j]), "pass_maximum": float(stats["pass_maximum"][j]),
                               "fail_mean": float(stats["fail_mean"][j]), "fail_median": float(stats["fail_median"][j]), "fail_maximum": float(stats["fail_maximum"][j]),
                               "outside_lower_ranked_envelope": bool(is_valid and auc < lo[rank_position[k]]),
                               "outside_upper_ranked_envelope": bool(is_valid and auc > hi[rank_position[k]]), "direction": direction}
                        table.append(row)
                    case_dir.mkdir(parents=True, exist_ok=True); write_csv(case_dir / "feature_statistics.csv", table)
                    plot_case(case_dir / "ranked_roc_auc_permutation_envelope.png", observed[valid], lo, hi, em, valid_ids)
                    ranked_table = sorted((r for r in table if r["observed_roc_auc"] is not None), key=lambda r: r["observed_roc_auc"])
                    for r in sorted(ranked_table, key=lambda r: r["absolute_auc_effect"], reverse=True)[:10]: candidates.append({"case_id": case_id, **r})
                    summaries.append({"case_id": case_id, "crosscoder_run": cc["id"], "model_pair": f"{cc['model_a']} vs {cc['model_b']}", "model_side": side,
                                      "model": target, "benchmark": benchmark, "layer": layer, "token_scope": "evaluated_tokens", "n_solutions": len(y),
                                      "n_failures": int(y.sum()), "failure_prevalence": float(y.mean()), "permutations": B, "seed": args.seed,
                                      "minimum_latent_activation": minimum, "fraction_below_minus_1e_8": negatives / latent_values,
                                      "legacy_masks_reconstructed": legacy_masks, "nonprefix_legacy_masks": nonprefix_masks,
                                      "skipped_solutions": len(solution_skips),
                                      "skipped_solution_reasons": json.dumps(solution_skips, ensure_ascii=False),
                                      "degenerate_features": int((~valid).sum()), "lowest_features": "; ".join(f"{r['feature_id']} ({r['observed_roc_auc']:.4f})" for r in ranked_table[:5]),
                                      "highest_features": "; ".join(f"{r['feature_id']} ({r['observed_roc_auc']:.4f})" for r in ranked_table[-5:])})
                except Exception as exc:
                    skipped.append({"case_id": case_id, "crosscoder_run": cc["id"], "model": target, "benchmark": benchmark, "reason": f"{type(exc).__name__}: {exc}"})
    write_csv(
        output / "all_cases_summary.csv", summaries,
        ["case_id", "crosscoder_run", "model_pair", "model_side", "model", "benchmark", "layer", "token_scope", "n_solutions", "n_failures", "failure_prevalence", "permutations", "seed", "minimum_latent_activation", "fraction_below_minus_1e_8", "legacy_masks_reconstructed", "nonprefix_legacy_masks", "skipped_solutions", "skipped_solution_reasons", "degenerate_features", "lowest_features", "highest_features"],
    )
    write_csv(
        output / "top_feature_candidates.csv", candidates,
        ["case_id", "feature_id", "observed_roc_auc", "signed_auc_effect", "absolute_auc_effect", "null_mean", "null_sd", "p_maxT", "activation_count", "activation_proportion", "outside_lower_ranked_envelope", "outside_upper_ranked_envelope", "direction"],
    )
    lines = ["# ROC-AUC feature screening", "", f"Permutation count: **{B}**; seed: **{args.seed}**.", "", "## Analyzed cases", ""]
    for s in summaries:
        rel = s["case_id"]
        lines += [f"### `{rel}`", "", f"n={s['n_solutions']}; failure prevalence={s['failure_prevalence']:.3f}; degenerate features={s['degenerate_features']}; skipped solutions={s['skipped_solutions']}; reconstructed legacy masks={s['legacy_masks_reconstructed']}; non-prefix masks={s['nonprefix_legacy_masks']}.", "",
                  f"Lowest five: {s['lowest_features']}", "", f"Highest five: {s['highest_features']}", "",
                  f"[Figure]({rel}/ranked_roc_auc_permutation_envelope.png) · [Feature table]({rel}/feature_statistics.csv)", ""]
    lines += ["## Skipped cases", ""] + [f"- `{s['case_id']}` — {s['reason']}" for s in skipped]
    lines += ["", "## Warnings", "", "Legacy activations without capture-time `evaluated_token_mask` and `token_char_spans` are deliberately skipped; exact alignment is not inferred by retokenizing cleaned code.", "", "The ranked 95% envelope is exploratory; use `p_maxT` as the multiple-testing-aware evidence."]
    (output / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "skipped_cases.json").write_text(json.dumps(skipped, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"analyzed": len(summaries), "skipped": len(skipped), "output": str(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
