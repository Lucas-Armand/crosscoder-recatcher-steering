#!/usr/bin/env python3
"""Paired base-versus-variant CrossCoder contribution screening."""
from __future__ import annotations

import argparse
import csv
import json
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

from audit_evaluation_pipeline import Source, jsonl
from crosscoder_common import (
    derive_legacy_evaluated_token_mask,
    load_checkpoint_encoder,
    load_evaluated_token_mask,
    load_layer,
    normalize_task_id,
)
from run_pr_auc_feature_screening import (
    discover_activation_index,
    load_historical_tokenizer,
    normalize_pr_effect,
    pr_auc_both,
    prepare_pr_order,
    read_labels,
    write_csv,
)


CATEGORIES = (
    "variant_increase_associated_with_regression",
    "variant_decrease_associated_with_regression",
    "variant_increase_associated_with_improvement",
    "variant_decrease_associated_with_improvement",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("manifests/paper_v1_extraction_v4.json"),
    )
    parser.add_argument("--activation-root", type=Path, action="append", required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--labels-csv", type=Path, required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("reports/differential_pr_auc_feature_screening"),
    )
    parser.add_argument("--permutations", type=int, default=200)
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--minimum-difference-count", type=int, default=5)
    parser.add_argument("--minimum-difference-proportion", type=float, default=0.01)
    parser.add_argument("--difference-epsilon", type=float, default=1e-8)
    return parser.parse_args()


def load_result_maps(
    source: Source,
    benchmark: str,
    model: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    stem = f"{benchmark}__{model}"
    raw_rows = jsonl(source.read(f"raw_results/{stem}_results.jsonl"))
    repaired_rows = jsonl(source.read(f"results/{stem}_results.jsonl"))
    raw = {normalize_task_id(row["task_id"]): row for row in raw_rows}
    repaired = {normalize_task_id(row["task_id"]): row for row in repaired_rows}
    if len(raw) != len(raw_rows) or len(repaired) != len(repaired_rows):
        raise ValueError(f"{benchmark}/{model}: duplicate raw or repaired task IDs")
    if set(raw) != set(repaired):
        raise ValueError(f"{benchmark}/{model}: raw/repaired task IDs differ")
    return raw, repaired


def exact_mask(
    path: Path,
    array: np.ndarray,
    token_count: int,
    task_id: str,
    raw: dict[str, dict[str, Any]],
    repaired: dict[str, dict[str, Any]],
    tokenizer: Any,
) -> tuple[np.ndarray, bool, bool]:
    legacy = False
    nonprefix = False
    try:
        mask = load_evaluated_token_mask(path, len(array))
    except KeyError:
        if task_id not in raw:
            raise KeyError(f"missing raw/repaired row for task {task_id}")
        mask, provenance = derive_legacy_evaluated_token_mask(
            path,
            len(array),
            raw[task_id],
            repaired[task_id],
            tokenizer,
        )
        legacy = True
        nonprefix = not provenance["literal_prefix"]
    mask = np.asarray(mask[-token_count:], dtype=np.bool_)
    if not mask.any():
        raise ValueError("evaluated-token mask has no rows after last-N pairing")
    return mask, legacy, nonprefix


def maximum_positive_contribution(
    hidden: np.ndarray,
    mask: np.ndarray,
    weight: Any,
    device: str,
) -> np.ndarray:
    """Maximum positive additive encoder contribution over selected rows."""
    import torch

    selected = np.asarray(hidden[-len(mask):][mask], dtype=np.float32)
    if selected.ndim != 2 or not len(selected):
        raise ValueError("no selected hidden-state rows")
    torch_device = torch.device(device)
    with torch.inference_mode():
        x = torch.from_numpy(selected).to(torch_device, dtype=torch.float32)
        w = (
            torch.from_numpy(weight).to(torch_device, dtype=torch.float32)
            if isinstance(weight, np.ndarray)
            else weight
        )
        contribution = torch.nn.functional.linear(x, w)
        result = contribution.max(dim=0).values.clamp_min_(0).cpu().numpy()
    if not np.isfinite(result).all():
        raise ValueError("non-finite model-side contribution")
    return result.astype(np.float32, copy=False)


def permutation_statistics(
    regression_orders: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    improvement_orders: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    regression: np.ndarray,
    improvement: np.ndarray,
    observed: dict[str, np.ndarray],
    permutations: int,
    seed: int,
    work_dir: Path,
) -> dict[str, np.ndarray]:
    work_dir.mkdir(parents=True, exist_ok=True)
    p = regression_orders[0].shape[0]
    prevalence = {
        "regression": float(regression.mean()),
        "improvement": float(improvement.mean()),
    }
    paths: dict[str, Path] = {}
    nulls: dict[str, np.memmap] = {}
    for category in CATEGORIES:
        paths[category] = work_dir / f"{category}.float32"
        nulls[category] = np.memmap(
            paths[category], mode="w+", dtype=np.float32, shape=(permutations, p)
        )
    rng = np.random.default_rng(seed)
    max_effect = np.empty(permutations, dtype=np.float64)
    for permutation in range(permutations):
        permuted_regression = rng.permutation(regression)
        permuted_improvement = rng.permutation(improvement)
        regression_high, _ = pr_auc_both(
            regression_orders[0], regression_orders[1], permuted_regression
        )
        regression_low, _ = pr_auc_both(
            regression_orders[2], regression_orders[3], permuted_regression
        )
        improvement_high, _ = pr_auc_both(
            improvement_orders[0], improvement_orders[1], permuted_improvement
        )
        improvement_low, _ = pr_auc_both(
            improvement_orders[2], improvement_orders[3], permuted_improvement
        )
        values = {
            "variant_increase_associated_with_regression": regression_high,
            "variant_decrease_associated_with_regression": regression_low,
            "variant_increase_associated_with_improvement": improvement_high,
            "variant_decrease_associated_with_improvement": improvement_low,
        }
        effects = []
        for category, array in values.items():
            nulls[category][permutation] = array
            target = (
                "regression" if category.endswith("regression") else "improvement"
            )
            effects.append(normalize_pr_effect(array, prevalence[target]))
        max_effect[permutation] = max(0.0, *(float(x.max()) for x in effects))

    result: dict[str, np.ndarray] = {}
    observed_effects: dict[str, np.ndarray] = {}
    for category in CATEGORIES:
        nulls[category].flush()
        target = "regression" if category.endswith("regression") else "improvement"
        baseline = prevalence[target]
        null = np.asarray(nulls[category])
        effect_null = normalize_pr_effect(null, baseline)
        result[f"{category}_null_mean"] = null.mean(axis=0)
        result[f"{category}_null_sd"] = null.std(axis=0)
        result[f"{category}_effect_null_mean"] = effect_null.mean(axis=0)
        result[f"{category}_effect_null_sd"] = effect_null.std(axis=0)
        ranked = np.sort(null, axis=1)
        result[f"{category}_ranked_mean"] = ranked.mean(axis=0)
        result[f"{category}_ranked_lower"] = np.quantile(ranked, 0.025, axis=0)
        result[f"{category}_ranked_upper"] = np.quantile(ranked, 0.975, axis=0)
        observed_effects[category] = normalize_pr_effect(
            observed[category], baseline
        )
        result[f"{category}_p_maxT"] = (
            1
            + (
                max_effect[:, None]
                >= observed_effects[category][None, :]
            ).sum(axis=0)
        ) / (permutations + 1)
    selected_effect = np.maximum.reduce(list(observed_effects.values()))
    result["p_maxT"] = (
        1 + (max_effect[:, None] >= selected_effect[None, :]).sum(axis=0)
    ) / (permutations + 1)
    for category in CATEGORIES:
        del nulls[category]
        paths[category].unlink(missing_ok=True)
    return result


def plot_case(
    path: Path,
    observed: dict[str, np.ndarray],
    null: dict[str, np.ndarray],
    feature_ids: np.ndarray,
    top: list[dict[str, Any]],
    regression_prevalence: float,
    improvement_prevalence: float,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    titles = {
        "variant_increase_associated_with_regression": "Variant increase → regression",
        "variant_decrease_associated_with_regression": "Variant decrease → regression",
        "variant_increase_associated_with_improvement": "Variant increase → improvement",
        "variant_decrease_associated_with_improvement": "Variant decrease → improvement",
    }
    fig, axes = plt.subplots(2, 2, figsize=(15, 10), sharex=True)
    for ax, category in zip(axes.flat, CATEGORIES):
        values = observed[category]
        order = np.argsort(values)
        ranked_values = values[order]
        ids = feature_ids[order]
        x = np.arange(len(values))
        ax.fill_between(
            x,
            null[f"{category}_ranked_lower"],
            null[f"{category}_ranked_upper"],
            color="#bdd7e7",
            alpha=0.55,
            label="95% permutation envelope",
        )
        ax.plot(x, null[f"{category}_ranked_mean"], color="#3182bd", linewidth=1)
        ax.scatter(x, ranked_values, s=6, color="#555", alpha=0.6)
        positions = {int(feature): rank for rank, feature in enumerate(ids)}
        marked_index = 0
        for row in top:
            if row["selected_category"] != category:
                continue
            rank = positions[int(row["feature_id"])]
            ax.scatter(
                rank, ranked_values[rank], s=55, color="#e6550d",
                edgecolor="black", zorder=4,
            )
            ax.annotate(
                f"{row['feature_id']} (E/V={row['selected_effect_to_variability']:.1f})",
                (rank, ranked_values[rank]),
                xytext=(
                    4,
                    (
                        -12 - 11 * marked_index
                        if ranked_values[rank] > 0.75
                        else 5 + 11 * marked_index
                    ),
                ),
                textcoords="offset points", fontsize=8,
            )
            marked_index += 1
        baseline = (
            regression_prevalence
            if category.endswith("regression")
            else improvement_prevalence
        )
        ax.axhline(baseline, color="black", linestyle="--", linewidth=1)
        ax.set_title(titles[category])
        ax.set_ylabel("PR-AUC")
        ax.set_ylim(-0.02, 1.02)
    for ax in axes[-1]:
        ax.set_xlabel("Feature rank")
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text())
    labels = read_labels(args.labels_csv)
    source = Source(args.dataset)
    output = args.output_root
    output.mkdir(parents=True, exist_ok=True)
    layer = int(str(manifest["crosscoder_contract"]["layer"]).split("_")[-1])
    permutations = 20 if args.smoke_test else args.permutations
    summaries: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    candidate_tasks: list[dict[str, Any]] = []
    skipped_cases: list[dict[str, Any]] = []
    result_cache: dict[tuple[str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
    tokenizer_cache: dict[str, Any] = {}

    for cc in manifest["crosscoders"]:
        base_model = cc["model_a"]
        variant_model = cc["model_b"]
        checkpoint = args.checkpoint_root / cc["id"] / "final.pt"
        if not checkpoint.exists():
            checkpoint = args.checkpoint_root / f"{cc['id']}.pt"
        for benchmark in manifest["benchmarks"]:
            case_id = f"{cc['id']}__{benchmark}__layer{layer}__paired_transitions"
            case_dir = output / case_id
            try:
                if not checkpoint.exists():
                    raise FileNotFoundError(f"checkpoint not found: {checkpoint}")
                index_a = discover_activation_index(
                    args.activation_root, benchmark, base_model
                )
                index_b = discover_activation_index(
                    args.activation_root, benchmark, variant_model
                )
                weight, _, _ = load_checkpoint_encoder(checkpoint)
                hidden_a = load_layer(next(iter(index_a.values())), layer).shape[1]
                hidden_b = load_layer(next(iter(index_b.values())), layer).shape[1]
                if weight.shape[1] != hidden_a + hidden_b:
                    raise ValueError(
                        f"encoder width {weight.shape[1]} != {hidden_a}+{hidden_b}"
                    )
                weight_a = weight[:, :hidden_a]
                weight_b = weight[:, hidden_a:]
                import torch
                torch_device = torch.device(args.device)
                weight_a_device = torch.from_numpy(weight_a).to(
                    torch_device, dtype=torch.float32
                )
                weight_b_device = torch.from_numpy(weight_b).to(
                    torch_device, dtype=torch.float32
                )
                for model in (base_model, variant_model):
                    key = (benchmark, model)
                    if key not in result_cache:
                        result_cache[key] = load_result_maps(source, benchmark, model)
                    if model not in tokenizer_cache:
                        tokenizer_cache[model] = load_historical_tokenizer(
                            manifest["models"][model]
                        )
                raw_a, repaired_a = result_cache[(benchmark, base_model)]
                raw_b, repaired_b = result_cache[(benchmark, variant_model)]

                label_a = {
                    (task, gen): value
                    for (model, bench, task, gen), value in labels.items()
                    if model == base_model and bench == benchmark
                }
                label_b = {
                    (task, gen): value
                    for (model, bench, task, gen), value in labels.items()
                    if model == variant_model and bench == benchmark
                }
                paired_labels = sorted(
                    set(label_a) & set(label_b),
                    key=lambda key: (int(key[0]), key[1]),
                )
                if set(label_a) != set(label_b):
                    raise ValueError("base/variant label task IDs differ")
                if args.smoke_test:
                    # Sample every paired transition stratum so both causal
                    # contrasts are represented whenever the data permit.
                    strata = {
                        transition: [
                            key for key in paired_labels
                            if (label_a[key], label_b[key]) == transition
                        ][:12]
                        for transition in ((0, 1), (0, 0), (1, 0), (1, 1))
                    }
                    paired_labels = [
                        key
                        for transition in ((0, 1), (0, 0), (1, 0), (1, 1))
                        for key in strata[transition]
                    ]

                contributions_a = []
                contributions_b = []
                transitions = []
                task_ids = []
                skips = []
                legacy_masks = 0
                nonprefix_masks = 0
                for label_key in paired_labels:
                    task_id, generation = label_key
                    try:
                        matches = [
                            key for key in index_a
                            if str(key.task_idx) == task_id
                            and key.gen_idx == generation
                        ]
                        if len(matches) != 1:
                            raise ValueError(
                                f"activation task mismatch: matches={len(matches)}"
                            )
                        activation_key = matches[0]
                        if activation_key not in index_b:
                            raise ValueError(
                                f"paired activation missing for {activation_key}"
                            )
                        array_a = load_layer(index_a[activation_key], layer)
                        array_b = load_layer(index_b[activation_key], layer)
                        token_count = min(len(array_a), len(array_b))
                        if token_count <= 0:
                            raise ValueError("empty paired activation")
                        mask_a, legacy_a, nonprefix_a = exact_mask(
                            index_a[activation_key], array_a, token_count, task_id,
                            raw_a, repaired_a, tokenizer_cache[base_model],
                        )
                        mask_b, legacy_b, nonprefix_b = exact_mask(
                            index_b[activation_key], array_b, token_count, task_id,
                            raw_b, repaired_b, tokenizer_cache[variant_model],
                        )
                        score_a = maximum_positive_contribution(
                            array_a, mask_a, weight_a_device, args.device
                        )
                        score_b = maximum_positive_contribution(
                            array_b, mask_b, weight_b_device, args.device
                        )
                        contributions_a.append(score_a)
                        contributions_b.append(score_b)
                        transitions.append((label_a[label_key], label_b[label_key]))
                        task_ids.append(task_id)
                        legacy_masks += int(legacy_a) + int(legacy_b)
                        nonprefix_masks += int(nonprefix_a) + int(nonprefix_b)
                    except Exception as exc:
                        skips.append(
                            {
                                "task_id": task_id,
                                "generation_idx": generation,
                                "reason": f"{type(exc).__name__}: {exc}",
                            }
                        )
                if not contributions_a:
                    raise ValueError(f"no aligned paired tasks; errors={skips[:3]}")
                score_a = np.stack(contributions_a)
                score_b = np.stack(contributions_b)
                transition_array = np.asarray(transitions, dtype=np.int8)
                differential = (score_b - score_a).astype(np.float32)
                regression_population = transition_array[:, 0] == 0
                improvement_population = transition_array[:, 0] == 1
                regression = transition_array[
                    regression_population, 1
                ].astype(np.int8)
                improvement = (
                    1 - transition_array[improvement_population, 1]
                ).astype(np.int8)
                if len(regression) < 4 or len(np.unique(regression)) != 2:
                    raise ValueError(
                        "base-pass population does not contain both preserved "
                        f"success and regression: n={len(regression)}"
                    )
                if len(improvement) < 4 or len(np.unique(improvement)) != 2:
                    raise ValueError(
                        "base-fail population does not contain both persistent "
                        f"failure and improvement: n={len(improvement)}"
                    )
                unique_values = np.asarray(
                    [
                        len(np.unique(differential[:, feature]))
                        for feature in range(differential.shape[1])
                    ]
                )
                valid = unique_values > 1
                valid_ids = np.flatnonzero(valid)
                regression_delta = differential[regression_population]
                improvement_delta = differential[improvement_population]
                regression_order, regression_ties = prepare_pr_order(
                    regression_delta[:, valid]
                )
                regression_reverse_order, regression_reverse_ties = (
                    prepare_pr_order(-regression_delta[:, valid])
                )
                improvement_order, improvement_ties = prepare_pr_order(
                    improvement_delta[:, valid]
                )
                improvement_reverse_order, improvement_reverse_ties = (
                    prepare_pr_order(-improvement_delta[:, valid])
                )
                high_regression, _ = pr_auc_both(
                    regression_order, regression_ties, regression
                )
                low_regression, _ = pr_auc_both(
                    regression_reverse_order, regression_reverse_ties, regression
                )
                high_improvement, _ = pr_auc_both(
                    improvement_order, improvement_ties, improvement
                )
                low_improvement, _ = pr_auc_both(
                    improvement_reverse_order, improvement_reverse_ties,
                    improvement,
                )
                observed = {
                    "variant_increase_associated_with_regression": high_regression,
                    "variant_decrease_associated_with_regression": low_regression,
                    "variant_increase_associated_with_improvement": high_improvement,
                    "variant_decrease_associated_with_improvement": low_improvement,
                }
                regression_prevalence = float(regression.mean())
                improvement_prevalence = float(improvement.mean())
                prevalence = {
                    "regression": regression_prevalence,
                    "improvement": improvement_prevalence,
                }
                with tempfile.TemporaryDirectory(
                    prefix="differential_pr_null_"
                ) as temporary:
                    null = permutation_statistics(
                        (
                            regression_order, regression_ties,
                            regression_reverse_order, regression_reverse_ties,
                        ),
                        (
                            improvement_order, improvement_ties,
                            improvement_reverse_order, improvement_reverse_ties,
                        ),
                        regression, improvement, observed, permutations, args.seed,
                        Path(temporary),
                    )
                effects: dict[str, np.ndarray] = {}
                effect_variability: dict[str, np.ndarray] = {}
                for category in CATEGORIES:
                    target = (
                        "regression"
                        if category.endswith("regression")
                        else "improvement"
                    )
                    effects[category] = normalize_pr_effect(
                        observed[category], prevalence[target]
                    )
                    effect_variability[category] = np.divide(
                        effects[category]
                        - null[f"{category}_effect_null_mean"],
                        null[f"{category}_effect_null_sd"],
                        out=np.zeros_like(effects[category]),
                        where=null[f"{category}_effect_null_sd"] > 0,
                    )

                regression_positive_delta = regression_delta[regression == 1]
                regression_control_delta = regression_delta[regression == 0]
                improvement_positive_delta = improvement_delta[improvement == 1]
                improvement_control_delta = improvement_delta[improvement == 0]
                difference_count = (
                    np.abs(differential) > args.difference_epsilon
                ).sum(axis=0)
                table = []
                for feature in range(differential.shape[1]):
                    positions = np.flatnonzero(valid_ids == feature)
                    is_valid = bool(valid[feature])
                    position = int(positions[0]) if len(positions) else -1
                    sign_compatible = {
                        "variant_increase_associated_with_regression":
                            float(np.median(
                                regression_positive_delta[:, feature]
                            )) > 0,
                        "variant_decrease_associated_with_regression":
                            float(np.median(
                                regression_positive_delta[:, feature]
                            )) < 0,
                        "variant_increase_associated_with_improvement":
                            float(np.median(
                                improvement_positive_delta[:, feature]
                            )) > 0,
                        "variant_decrease_associated_with_improvement":
                            float(np.median(
                                improvement_positive_delta[:, feature]
                            )) < 0,
                    }
                    compatible = [
                        category for category in CATEGORIES
                        if is_valid
                        and sign_compatible[category]
                        and effects[category][position] > 0
                    ]
                    selected = (
                        max(
                            compatible,
                            key=lambda category: (
                                effect_variability[category][position],
                                effects[category][position],
                            ),
                        )
                        if compatible else "neutral_or_degenerate"
                    )
                    support_ok = bool(
                        difference_count[feature] >= args.minimum_difference_count
                        and difference_count[feature] / len(differential)
                        >= args.minimum_difference_proportion
                    )
                    row: dict[str, Any] = {
                        "feature_id": feature,
                        "selected_category": selected,
                        "selected_pr_auc": (
                            float(observed[selected][position])
                            if selected != "neutral_or_degenerate" else None
                        ),
                        "selected_normalized_effect": (
                            float(effects[selected][position])
                            if selected != "neutral_or_degenerate" else None
                        ),
                        "selected_effect_to_variability": (
                            float(effect_variability[selected][position])
                            if selected != "neutral_or_degenerate" else None
                        ),
                        "p_maxT": (
                            float(null[f"{selected}_p_maxT"][position])
                            if selected != "neutral_or_degenerate" else None
                        ),
                        "support_ok": support_ok,
                        "difference_count": int(difference_count[feature]),
                        "difference_proportion": float(
                            difference_count[feature] / len(differential)
                        ),
                        "unique_differential_values": int(unique_values[feature]),
                        "base_contribution_mean": float(
                            score_a[:, feature].mean()
                        ),
                        "variant_contribution_mean": float(
                            score_b[:, feature].mean()
                        ),
                        "differential_mean": float(differential[:, feature].mean()),
                        "differential_median": float(
                            np.median(differential[:, feature])
                        ),
                        "regression_differential_mean": float(
                            regression_positive_delta[:, feature].mean()
                        ),
                        "regression_differential_median": float(
                            np.median(regression_positive_delta[:, feature])
                        ),
                        "preserved_success_differential_mean": float(
                            regression_control_delta[:, feature].mean()
                        ),
                        "preserved_success_differential_median": float(
                            np.median(regression_control_delta[:, feature])
                        ),
                        "improvement_differential_mean": float(
                            improvement_positive_delta[:, feature].mean()
                        ),
                        "improvement_differential_median": float(
                            np.median(improvement_positive_delta[:, feature])
                        ),
                        "persistent_failure_differential_mean": float(
                            improvement_control_delta[:, feature].mean()
                        ),
                        "persistent_failure_differential_median": float(
                            np.median(improvement_control_delta[:, feature])
                        ),
                    }
                    for category in CATEGORIES:
                        target = (
                            "regression"
                            if category.endswith("regression")
                            else "improvement"
                        )
                        row[f"{category}_pr_auc"] = (
                            float(observed[category][position])
                            if is_valid else None
                        )
                        row[f"{category}_baseline"] = prevalence[target]
                        row[f"{category}_normalized_effect"] = (
                            float(effects[category][position])
                            if is_valid else None
                        )
                        row[f"{category}_effect_to_variability"] = (
                            float(effect_variability[category][position])
                            if is_valid else None
                        )
                    table.append(row)
                case_dir.mkdir(parents=True, exist_ok=True)
                write_csv(case_dir / "feature_statistics.csv", table)
                eligible = [
                    row for row in table
                    if row["support_ok"]
                    and row["selected_category"] != "neutral_or_degenerate"
                    and row["selected_effect_to_variability"] > 0
                ]
                top = sorted(
                    eligible,
                    key=lambda row: (
                        row["p_maxT"],
                        -row["selected_effect_to_variability"],
                        -row["selected_normalized_effect"],
                    ),
                )[:5]
                category_rank: dict[str, int] = {category: 0 for category in CATEGORIES}
                category_top: list[dict[str, Any]] = []
                for category in CATEGORIES:
                    rows = [
                        row for row in eligible
                        if row["selected_category"] == category
                    ]
                    for row in sorted(
                        rows,
                        key=lambda item: (
                            item["p_maxT"],
                            -item["selected_effect_to_variability"],
                            -item["selected_normalized_effect"],
                        ),
                    )[:5]:
                        category_rank[category] += 1
                        category_top.append(
                            {
                                "case_id": case_id,
                                "category_rank": category_rank[category],
                                **row,
                            }
                        )
                candidates.extend(category_top)
                task_id_array = np.asarray(task_ids, dtype=object)
                for candidate in category_top:
                    feature = int(candidate["feature_id"])
                    is_regression_category = candidate[
                        "selected_category"
                    ].endswith("regression")
                    population = (
                        regression_population
                        if is_regression_category
                        else improvement_population
                    )
                    population_task_ids = task_id_array[population]
                    population_transitions = transition_array[population]
                    population_score_a = score_a[population, feature]
                    population_score_b = score_b[population, feature]
                    population_delta = differential[population, feature]
                    for task_position, task_id in enumerate(
                        population_task_ids
                    ):
                        base_label, variant_label = population_transitions[
                            task_position
                        ]
                        transition_name = {
                            (0, 1): "base_pass_variant_fail",
                            (0, 0): "both_pass",
                            (1, 0): "base_fail_variant_pass",
                            (1, 1): "both_fail",
                        }[(int(base_label), int(variant_label))]
                        candidate_tasks.append(
                            {
                                "case_id": case_id,
                                "crosscoder_run": cc["id"],
                                "benchmark": benchmark,
                                "feature_id": feature,
                                "selected_category":
                                    candidate["selected_category"],
                                "category_rank": candidate["category_rank"],
                                "task_id": task_id,
                                "transition": transition_name,
                                "base_contribution": float(
                                    population_score_a[task_position]
                                ),
                                "variant_contribution": float(
                                    population_score_b[task_position]
                                ),
                                "differential": float(
                                    population_delta[task_position]
                                ),
                            }
                        )
                plot_case(
                    case_dir / "ranked_differential_pr_auc_envelope.png",
                    observed, null, valid_ids, top, regression_prevalence,
                    improvement_prevalence,
                )
                counts = {
                    "base_pass_variant_fail": int(
                        ((transition_array[:, 0] == 0)
                         & (transition_array[:, 1] == 1)).sum()
                    ),
                    "base_fail_variant_pass": int(
                        ((transition_array[:, 0] == 1)
                         & (transition_array[:, 1] == 0)).sum()
                    ),
                    "both_pass": int((transition_array.sum(axis=1) == 0).sum()),
                    "both_fail": int((transition_array.sum(axis=1) == 2).sum()),
                }
                summaries.append(
                    {
                        "case_id": case_id,
                        "crosscoder_run": cc["id"],
                        "base_model": base_model,
                        "variant_model": variant_model,
                        "benchmark": benchmark,
                        "layer": layer,
                        "n_paired_tasks": len(transition_array),
                        "n_discordant_tasks": int(
                            (transition_array[:, 0] != transition_array[:, 1]).sum()
                        ),
                        **counts,
                        "regression_prevalence_among_base_pass":
                            regression_prevalence,
                        "improvement_prevalence_among_base_fail":
                            improvement_prevalence,
                        "permutations": permutations,
                        "seed": args.seed,
                        "legacy_masks_reconstructed": legacy_masks,
                        "nonprefix_legacy_masks": nonprefix_masks,
                        "skipped_tasks": len(skips),
                        "skipped_task_reasons": json.dumps(
                            skips, ensure_ascii=False
                        ),
                        "degenerate_features": int((~valid).sum()),
                        "top_candidates": "; ".join(
                            f"{row['feature_id']} ({row['selected_category']}, "
                            f"E/V={row['selected_effect_to_variability']:.2f}, "
                            f"p={row['p_maxT']:.4f})"
                            for row in top[:5]
                        ),
                    }
                )
            except Exception as exc:
                skipped_cases.append(
                    {
                        "case_id": case_id,
                        "crosscoder_run": cc["id"],
                        "benchmark": benchmark,
                        "reason": f"{type(exc).__name__}: {exc}",
                    }
                )

    write_csv(output / "all_cases_summary.csv", summaries)
    write_csv(output / "top_feature_candidates.csv", candidates)
    write_csv(output / "candidate_task_examples.csv", candidate_tasks)
    (output / "skipped_cases.json").write_text(
        json.dumps(skipped_cases, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# Paired differential PR-AUC feature screening",
        "",
        f"Permutations: **{permutations}**; seed: **{args.seed}**.",
        "",
        "The score is the task-level difference between the variant-side and "
        "base-side maximum positive additive encoder contributions. Regressions "
        "are tested only among tasks passed by the base model (variant failure "
        "versus preserved success). Improvements are tested only among tasks "
        "failed by the base model (variant success versus persistent failure).",
        "",
        "The four jointly corrected searches are: variant increase associated "
        "with regression, variant decrease associated with regression, variant "
        "increase associated with improvement, and variant decrease associated "
        "with improvement. `p_maxT` searches all valid features and all four "
        "categories in every label permutation.",
        "",
        "These are model-side contributions to a shared joint latent, not "
        "independently encoded model-specific latent activations.",
        "",
        "[Implementation notes](IMPLEMENTATION_NOTES.md) · "
        "[Candidate recommendations](CANDIDATE_RECOMMENDATIONS.md) · "
        "[Candidate task examples](candidate_task_examples.csv)",
        "",
        "## Cases",
        "",
    ]
    for summary in summaries:
        case_id = summary["case_id"]
        lines.extend(
            [
                f"### `{case_id}`",
                "",
                f"paired={summary['n_paired_tasks']}; "
                f"discordant={summary['n_discordant_tasks']}; "
                f"base-pass/variant-fail={summary['base_pass_variant_fail']}; "
                f"base-fail/variant-pass={summary['base_fail_variant_pass']}; "
                f"skipped={summary['skipped_tasks']}.",
                "",
                f"Top candidates: {summary['top_candidates'] or 'none eligible'}",
                "",
                f"[Figure]({case_id}/ranked_differential_pr_auc_envelope.png) · "
                f"[Feature table]({case_id}/feature_statistics.csv)",
                "",
            ]
        )
    lines.extend(["## Skipped cases", ""])
    lines.extend(
        f"- `{row['case_id']}` — {row['reason']}" for row in skipped_cases
    )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "Stored paper-v1 activations come from different model-generated "
            "texts and are paired by the historical last-N rule. Model-side "
            "contributions are therefore exploratory until the candidate is "
            "validated by forwarding the same text through both models.",
            "",
            "Feature selection uses evaluator outcomes from these benchmarks. "
            "Causal confirmation should use frozen candidates and held-out tasks "
            "or cross-benchmark replication.",
        ]
    )
    (output / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "analyzed": len(summaries),
                "skipped": len(skipped_cases),
                "output": str(output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
