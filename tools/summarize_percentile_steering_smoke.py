#!/usr/bin/env python3
"""Summarize the low-percentile pass-to-fail steering smoke."""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--report-dir", type=Path, required=True)
    a = p.parse_args(); a.report_dir.mkdir(parents=True, exist_ok=True)
    baseline_rows = {
        row["task_id"]: row
        for row in map(json.loads, (a.run_dir / "baseline/alpha_0.jsonl").open())
    }
    baseline_eval = json.loads(
        (a.run_dir / "baseline/evaluation/subset_eval_results.json").read_text()
    )["eval"]
    rows = []
    pattern = re.compile(r"feature_(\d+)_(p\d+)_alpha_(neg)?([\dp]+)$")
    for generation_path in sorted((a.run_dir / "generations").glob("*.jsonl")):
        match = pattern.match(generation_path.stem)
        if not match: continue
        feature, aggregation, negative, alpha_text = match.groups()
        alpha = float(alpha_text.replace("p", ".")) * (-1 if negative else 1)
        evaluation = json.loads(
            (a.run_dir / "evaluations" / generation_path.stem / "subset_eval_results.json").read_text()
        )["eval"]
        for generated in map(json.loads, generation_path.open()):
            task_id = generated["task_id"]
            detail = evaluation[task_id][0]
            rows.append({
                "feature_id": int(feature), "aggregation": aggregation,
                "alpha": alpha, "task_id": task_id,
                "baseline_correct": bool(baseline_eval[task_id][0]["correct"]),
                "steered_correct": bool(detail["correct"]),
                "raw_completion_changed": generated["completion"] != baseline_rows[task_id]["completion"],
                "baseline_tokens": baseline_rows[task_id]["generated_tokens"],
                "steered_tokens": generated["generated_tokens"],
                "intervention_vector_norm": generated["intervention_vector_norm"],
                "status": detail["status"],
                "failed_test_count": len(detail.get("details", {})),
            })
    fields = list(rows[0])
    with (a.report_dir / "task_level_results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(rows)
    grouped = {}
    for row in rows:
        key = (row["feature_id"], row["aggregation"], row["alpha"])
        grouped.setdefault(key, []).append(row)
    summary = []
    for (feature, aggregation, alpha), group in sorted(grouped.items()):
        summary.append({
            "feature_id": feature, "aggregation": aggregation, "alpha": alpha,
            "n": len(group), "passed": sum(x["steered_correct"] for x in group),
            "changed": sum(x["raw_completion_changed"] for x in group),
            "intervention_vector_norm": group[0]["intervention_vector_norm"],
        })
    with (a.report_dir / "arm_summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary[0]), lineterminator="\n"); writer.writeheader(); writer.writerows(summary)

    lines = [
        "# Low-percentile CrossCoder pass-to-fail steering smoke", "",
        "## Objective", "",
        "Test whether restoring merged-side decoder directions for corrected ",
        "P80-or-lower regression-associated features rescues historically paired ",
        "CodeLlama base-pass/merged-fail BigCodeBench tasks.", "",
        "## Design", "",
        "- CrossCoder: CodeLlama base versus merged, layer 16, 16,384 features.",
        "- Features: 4815/P80, 13439/P80, and 4567/P60.",
        "- Five tasks per feature, selected by the largest negative paired ",
        "model-side contribution differential among historical regressions.",
        "- All 21 unique alpha-zero candidates reproduced failure (0/21 pass); ",
        "the top five per feature were retained.",
        "- Traditional merged-side last-token steering at alpha +1, +2, +4, ",
        "with alpha -2 as a directionality control.",
        "- Paper-v1 generation settings and per-task seeds; extraction v4 and ",
        "BigCodeBench 0.1.5 subset evaluation.", "",
        "The selection percentile is an observational aggregation, not the alpha ",
        "unit. Actual intervention norms are reported below.", "",
        "## Results", "",
        "| Feature | P | Alpha | Vector norm | Changed | Passed |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['feature_id']} | {row['aggregation'].upper()} | {row['alpha']:g} | "
            f"{row['intervention_vector_norm']:.4f} | {row['changed']}/{row['n']} | "
            f"{row['passed']}/{row['n']} |"
        )
    lines += [
        "", "No arm rescued a task: 0/60 steered generations passed. The null ",
        "result is not caused by an inert hook: at alpha +4, 4815 and 13439 each ",
        "changed 3/5 completions and 4567 changed 2/5.", "",
        "## Qualitative effects", "",
        "- **4815/P80:** task 566 moves from no useful implementation toward an ",
        "attempted argument-inspection implementation, but the generated iteration ",
        "is invalid. Task 504 only renames intermediate variables. Task 288 changes ",
        "a repetitive trajectory without implementing the required directory logic.",
        "- **13439/P80:** task 722 becomes more complete but returns matched ERROR ",
        "strings rather than their count. Task 563 replaces a helper with a malformed ",
        "doctest, and task 592 shifts repetition from executable statements into ",
        "comments without completing CSV generation.",
        "- **4567/P60:** positive steering sends task 722 to the same still-wrong ",
        "implementation reached by 13439. It reduces or changes repetition in tasks ",
        "288 and 976 but does not restore the requested computation.", "",
        "The three merged decoder vectors are nearly orthogonal (pairwise cosine ",
        "range -0.0054 to 0.0399). Task 722 responding similarly to two different ",
        "features is therefore better treated as a perturbation-sensitive generation ",
        "attractor than as shared semantic evidence.", "",
        "## Interpretation", "",
        "The percentile screen successfully identifies stable observational ",
        "differences, but direct addition of an individual merged-side decoder vector ",
        "does not reconstruct the useful base behavior in this smoke. This rejects ",
        "the tested traditional intervention, doses, and selected tasks; it does not ",
        "prove the features are non-causal under activation-matched clamping or a ",
        "joint multi-feature intervention.", "",
        "A stronger alpha is not the immediate next step because alpha +4 already ",
        "changes 40--60% of target completions without any recovery. The next useful ",
        "diagnostic is same-text joint-latent measurement for these features, followed ",
        "by clamping the latent/contribution toward the base value rather than adding ",
        "a constant decoder direction at every generation step.", "",
        "Machine-readable outputs: [arm summary](arm_summary.csv) and ",
        "[task-level results](task_level_results.csv).",
    ]
    (a.report_dir / "index.md").write_text(
        "\n".join(line.rstrip() for line in lines) + "\n"
    )


if __name__ == "__main__":
    main()
