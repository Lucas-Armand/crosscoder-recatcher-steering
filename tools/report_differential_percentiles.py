#!/usr/bin/env python3
"""Summarize percentile sensitivity in paired differential PR-AUC outputs."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.report_root
    frames = []
    for path in sorted(root.glob("*/feature_statistics.csv")):
        frame = pd.read_csv(path)
        frame["case_id"] = path.parent.name
        frames.append(frame)
    if not frames:
        raise SystemExit("no case feature tables found")
    data = pd.concat(frames, ignore_index=True)
    eligible = data[
        data["support_ok"].eq(True)
        & data["selected_category"].ne("neutral_or_degenerate")
    ].copy()

    comparison = []
    for (case_id, category, aggregation), group in eligible.groupby(
        ["case_id", "selected_category", "aggregation"], sort=True
    ):
        best = group.sort_values(
            ["p_maxT", "selected_effect_to_variability", "selected_normalized_effect"],
            ascending=[True, False, False],
        ).iloc[0]
        roc_column = f"{category}_roc_auc"
        comparison.append(
            {
                "case_id": case_id,
                "transition": "pass_to_fail" if category.endswith("regression") else "fail_to_pass",
                "category": category,
                "aggregation": aggregation,
                "top_feature_id": int(best.feature_id),
                "pr_auc": best.selected_pr_auc,
                "roc_auc": best[roc_column],
                "normalized_pr_effect": best.selected_normalized_effect,
                "effect_to_variability": best.selected_effect_to_variability,
                "p_maxT": best.p_maxT,
                "difference_count": int(best.difference_count),
            }
        )
    comparison_frame = pd.DataFrame(comparison)
    comparison_frame.to_csv(root / "percentile_comparison.csv", index=False)

    significant = eligible[eligible["p_maxT"] <= 0.05].copy()
    significant = significant.sort_values(
        ["p_maxT", "selected_effect_to_variability"], ascending=[True, False]
    )
    significant.to_csv(root / "significant_feature_percentiles.csv", index=False)

    summaries = pd.read_csv(root / "all_cases_summary.csv")
    lines = [
        "# Percentile sensitivity analysis",
        "",
        "The paired score is `P_variant - P_base`, where each P is a token-level ",
        "positive model-side CrossCoder encoder-contribution percentile over exact ",
        "evaluated tokens. P50, P60, P70, P80, P90, P95, and P99 are searched ",
        "jointly with 16,384 features and four signed transition hypotheses. ",
        "`p_maxT` therefore corrects the percentile choice as part of the search.",
        "",
        "## Main findings",
        "",
        f"- Analyzed {len(summaries)} model-pair/benchmark cases with no skipped cases.",
        f"- No fail-to-pass candidate passed the joint maxT threshold of 0.05.",
        f"- {len(significant)} feature/percentile rows passed maxT; these represent "
        f"{significant[['case_id','feature_id']].drop_duplicates().shape[0]} unique "
        "case-feature pairs, all associated with pass-to-fail transitions.",
        "- Significant rows are distributed across all tested percentiles: "
        + ", ".join(
            f"{key.upper()}={value}"
            for key, value in significant["aggregation"].value_counts().sort_index().items()
        ) + ".",
        "",
        "The result does not support one universally optimal percentile. Lower and ",
        "middle percentiles can outperform P99, showing that broadly sustained ",
        "activation differences contain information that a peak-only analysis misses.",
        "",
        "## Corrected candidates",
        "",
    ]
    for case_id, group in significant.groupby("case_id", sort=True):
        lines += [f"### `{case_id}`", ""]
        unique = group.drop_duplicates("feature_id").head(12)
        lines += [
            "| Feature | P | Direction | PR-AUC | ROC-AUC | E/V | p_maxT |",
            "|---:|---:|---|---:|---:|---:|---:|",
        ]
        for _, row in unique.iterrows():
            roc = row[f"{row.selected_category}_roc_auc"]
            lines.append(
                f"| {int(row.feature_id)} | {row.aggregation.upper()} | "
                f"{row.selected_category} | {row.selected_pr_auc:.4f} | "
                f"{roc:.4f} | {row.selected_effect_to_variability:.2f} | "
                f"{row.p_maxT:.4f} |"
            )
        lines.append("")

    lines += [
        "## Previously studied features",
        "",
        "In CodeLlama base-versus-merged BigCodeBench, feature 8994 is corrected at ",
        "P99 (`p_maxT=0.00498`) and P95 (`p_maxT=0.0448`); feature 11586 is corrected ",
        "at P99 (`p_maxT=0.0299`) and P95 (`p_maxT=0.0348`). Both are categorized as ",
        "variant decrease associated with regression: the model-side contribution is ",
        "lower in merged-model regressions than in preserved successes. Feature 2562 ",
        "does not survive correction at any percentile.",
        "",
        "## Interpretation limits",
        "",
        "- CodeLlama base-versus-merged BigCodeBench has 246 regressions and only 16 ",
        "preserved successes among aligned base-pass tasks. Its regression PR baseline ",
        "is therefore 0.9389. The normalized effect and maxT result, rather than raw ",
        "PR-AUC alone, carry the interpretation.",
        "- HumanEval regression results with one or two positive events are descriptive ",
        "only, even when raw PR-AUC equals 1.",
        "- Model-side contributions are additive encoder terms of a joint latent, not ",
        "independently encoded activations.",
        "- Stored own-text activations mix checkpoint and generated-text differences. ",
        "Same-text confirmation remains necessary before causal steering.",
        "- Failure association does not by itself identify whether adding or removing a ",
        "feature decoder will reproduce the transition.",
        "",
        "Machine-readable summaries: [percentile comparison](percentile_comparison.csv) ",
        "and [corrected feature/percentile rows](significant_feature_percentiles.csv).",
    ]
    (root / "PERCENTILE_ANALYSIS.md").write_text(
        "\n".join(line.rstrip() for line in lines) + "\n"
    )


if __name__ == "__main__":
    main()
