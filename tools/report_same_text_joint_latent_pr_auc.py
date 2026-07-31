#!/usr/bin/env python3
"""Create the compact report for the same-text joint-latent PR-AUC run."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    run = args.run_dir
    summary = json.loads((run / "run_summary.json").read_text())
    metadata = json.loads((run / "solution_metadata.json").read_text())
    arrays = np.load(run / "solution_feature_aggregates.npz")
    rows = read_csv(run / "feature_aggregation_statistics.csv")
    contexts = read_csv(run / "top_feature_contexts.csv")

    base_label = summary["models"][0].split("/")[-1]
    source_labels = sorted({row["source_model"] for row in metadata})
    base_source = next(label for label in source_labels if label.endswith("_base"))
    merged_source = next(label for label in source_labels if label.endswith("_merged"))
    base_indices = np.array([i for i, row in enumerate(metadata) if row["source_model"] == base_source])
    merged_indices = np.array([i for i, row in enumerate(metadata) if row["source_model"] == merged_source])
    base_sum = arrays["sum"][base_indices].sum(axis=0)
    merged_sum = arrays["sum"][merged_indices].sum(axis=0)
    source_share = np.divide(
        base_sum, base_sum + merged_sum, out=np.full_like(base_sum, 0.5),
        where=(base_sum + merged_sum) > 0,
    )

    for row in rows:
        row["activation_source_base_share"] = float(source_share[int(row["feature_id"])])

    eligible = [
        row for row in rows
        if row["source_model"] == base_source
        and int(row["activation_support"]) >= len(base_indices) // 2
    ]
    best: dict[int, dict[str, str]] = {}
    for row in eligible:
        feature = int(row["feature_id"])
        if feature not in best or float(row["effect_to_variability"]) > float(best[feature]["effect_to_variability"]):
            best[feature] = row
    ranked = sorted(best.values(), key=lambda row: float(row["pr_auc"]))
    top_ev = sorted(best.values(), key=lambda row: float(row["effect_to_variability"]), reverse=True)[:5]
    top_ids = {int(row["feature_id"]) for row in top_ev}

    x = np.arange(len(ranked))
    y = np.array([float(row["pr_auc"]) for row in ranked])
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.scatter(x, y, s=8, alpha=0.5, color="#35618d", label="best aggregation per feature")
    prevalence = float(ranked[0]["failure_prevalence"])
    ax.axhline(prevalence, color="#666666", linestyle="--", label=f"failure prevalence = {prevalence:.3f}")
    label_offsets = {6258: 5, 6873: 5, 15907: 15, 12659: -14, 9611: 0}
    for rank, row in enumerate(ranked):
        feature = int(row["feature_id"])
        if feature in top_ids:
            ax.scatter(rank, float(row["pr_auc"]), s=55, color="#c43b3b", zorder=3)
            ax.annotate(
                str(feature), (rank, float(row["pr_auc"])),
                xytext=(-7, label_offsets.get(feature, 5)), textcoords="offset points",
                ha="right", fontsize=8,
            )
    ax.set(xlabel="Feature rank by PR-AUC", ylabel="PR-AUC (failure is positive)", title="Same-text joint-latent failure screening — DeepSeek base solutions")
    ax.legend(loc="upper left")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(run / "ranked_joint_latent_pr_auc.png", dpi=180)
    plt.close(fig)

    compact = []
    for rank, row in enumerate(sorted(top_ev, key=lambda r: float(r["effect_to_variability"]), reverse=True), 1):
        compact.append({
            "rank_by_effect_to_variability": rank,
            "feature_id": row["feature_id"],
            "aggregation": row["aggregation"],
            "pr_auc": row["pr_auc"],
            "failure_prevalence": row["failure_prevalence"],
            "normalized_pr_effect": row["normalized_pr_effect"],
            "effect_to_variability": row["effect_to_variability"],
            "p_maxT": row["p_maxT_across_features_and_aggregations"],
            "activation_support": row["activation_support"],
            "mean_active_fraction": row["mean_active_fraction"],
            "decoder_base_specificity": row["decoder_base_specificity"],
            "activation_source_base_share": row["activation_source_base_share"],
            "task_activation_entropy": row["task_activation_entropy"],
            "first_p95_position_mean": row["first_p95_position_mean"],
            "first_quarter_activation_mean": row["first_quarter_activation_mean"],
            "second_quarter_activation_mean": row["second_quarter_activation_mean"],
        })
    write_csv(run / "steering_candidate_summary.csv", compact)

    context_by_feature = {}
    for row in contexts:
        if row["source_model"] == base_source and int(row["feature_id"]) in top_ids:
            context_by_feature.setdefault(int(row["feature_id"]), []).append(row)

    table_lines = []
    for row in compact:
        table_lines.append(
            f"| {row['rank_by_effect_to_variability']} | {row['feature_id']} | {row['aggregation']} | "
            f"{float(row['pr_auc']):.3f} | {float(row['effect_to_variability']):.2f} | "
            f"{float(row['p_maxT']):.3f} | {int(row['activation_support'])}/{len(base_indices)} | "
            f"{float(row['activation_source_base_share']):.3f} | {float(row['decoder_base_specificity']):.3f} |"
        )
    report = f"""# Same-text joint-latent PR-AUC screening

This experiment forwards each already evaluated HumanEval+ solution through the
DeepSeek base and merged models using identical token IDs. It captures layer 16,
applies per-token RMS normalization, calculates the full joint CrossCoder latent,
and treats evaluation failure as the positive class.

![Ranked PR-AUC](ranked_joint_latent_pr_auc.png)

## Coverage and validity

- Retained solutions: **{summary['n_solutions']}/328** ({summary['n_base_solutions']} base, {summary['n_merged_solutions']} merged).
- Fully skipped: **{len(summary['skipped_solutions'])}/328 (10.1%)** because no paired evaluated token survived the historical finite-state and norm `<500` rule.
- Removed individual tokens: **{summary['removed_nonfinite_or_extreme_tokens']}**.
- Token IDs were required to be identical across both model forwards.
- The prompt was excluded. Three valid full-function replacements start at character zero.
- Failure prevalence after filtering: base **{np.mean(arrays['labels'][base_indices]):.3f}**; merged **{np.mean(arrays['labels'][merged_indices]):.3f}**.
- Permutations: **{summary['permutations']}**, seed **{summary['seed']}**. `p_maxT` corrects the search over all 16,384 features and all five aggregations.

The exclusions are not missing at random until proven otherwise. Consequently,
this is a screening result, not a final population-level estimate. The analysis
must also be rerun with 5,000 permutations before paper-level inference.

## Top base-solution features by effect/variability

Eligibility for this table requires activation in at least half of retained base
solutions. The graph marks these same five features.

| Rank | Feature | Aggregation | PR-AUC | E/V | p_maxT | Support | Base activation share | Decoder base specificity |
|---:|---:|---|---:|---:|---:|---:|---:|---:|
{chr(10).join(table_lines)}

Only feature **6258/P99** survives the 200-permutation maxT screen at 0.05. Its
decoder specificity is only mildly base-weighted, however, and its strongest
contexts include scaffolding comments, placeholder code, and incomplete
solutions. It is therefore a strong failure marker but not yet a clean causal
steering target.

Feature **6873/max** is the clearest semantic candidate: its high-activation
contexts repeatedly contain `TODO`, `YOUR CODE HERE`, `pass`, or placeholder
returns. Its adjusted p-value is 0.129, so semantic coherence is stronger than
the present multiple-testing evidence. Features 9611 and 11780 show a similar
placeholder/comment family. This correlation is a warning that the screen may
be finding several redundant detectors of unfinished code.

None of the leading features is strongly base-specific by decoder norm
(approximately 0.50–0.55). Their observed activation is more base-heavy
(approximately 0.56–0.60), but part of that difference can be caused by code
length, label prevalence, and the different solution sets. Decoder specificity
and observed source share should therefore be treated as diagnostics, not as
proof of a base-only mechanism.

## Meaning of the additional diagnostics

- **Decoder specificity** asks whether the feature decoder vector has greater
  norm on the base or merged side. It describes representation geometry.
- **Base/merged contribution** measures the two additive encoder terms before
  ReLU. It helps determine which side drives the joint latent.
- **Task entropy** is high when activation mass is spread across many tasks and
  low when a feature is dominated by a few examples.
- **First P95 position** locates the earliest within-solution high-activation
  token on a normalized 0–1 code axis.
- **First/second quarter activation** tests whether the signal appears early
  enough to be useful for intervention before the final error is expressed.

These fields are descriptive filters. They should not be folded into one score
post hoc. A steering candidate should pass separate gates: adequate support,
failure association, base-side evidence, interpretable contexts, and a planned
directional intervention with negative and sham controls.

## Decision for steering

Do not steer 6258 solely because it is statistically strongest. First inspect
more contexts and distinguish whether it detects unfinished-code scaffolding or
causes it. Feature 6873 is the best semantic replication candidate, while 6258
is the best statistical candidate. A small controlled experiment comparing both
would be more informative than selecting either by a single score.
"""
    (run / "index.md").write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
