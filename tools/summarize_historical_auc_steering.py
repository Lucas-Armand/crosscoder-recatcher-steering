#!/usr/bin/env python3
"""Summarize paired historical-style AUC steering arms."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ARMS = (
    ("zero", 0.0),
    ("neg_0p10_p99", -0.10),
    ("neg_0p25_p99", -0.25),
    ("neg_0p50_p99", -0.50),
    ("neg_1p00_p99", -1.00),
)
VERDICT = "eval_candidate_code_repaired_correct"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    args.report_dir.mkdir(parents=True, exist_ok=True)
    selection = json.loads((args.run_dir / "smoke_selection.json").read_text())
    evaluated = {
        tag: {row["task_id"]: row for row in read_jsonl(
            args.run_dir / "evaluation" / tag / "results.jsonl"
        )}
        for tag, _ in ARMS
    }
    generated = {
        tag: {row["task_id"]: row for row in read_jsonl(
            args.run_dir / "generations" / f"alpha_{tag}.jsonl"
        )}
        for tag, _ in ARMS
    }
    control = evaluated["zero"]
    task_rows = []
    summary = []
    for tag, nominal_alpha in ARMS:
        current = evaluated[tag]
        gen = generated[tag]
        fail_to_pass = pass_to_fail = changed = 0
        historical_fail_passed = historical_control_passed = 0
        ratios = []
        for task_id, base in control.items():
            row = current[task_id]
            old = bool(base[VERDICT])
            new = bool(row[VERDICT])
            fail_to_pass += int(not old and new)
            pass_to_fail += int(old and not new)
            code_changed = (
                base.get("candidate_code_repaired")
                != row.get("candidate_code_repaired")
            )
            changed += int(code_changed)
            historical_label = gen[task_id]["historical_label"]
            historical_fail_passed += int(historical_label == "failure" and new)
            historical_control_passed += int(
                historical_label == "pass_control" and new
            )
            diagnostics = gen[task_id].get("intervention_diagnostics") or {}
            ratio = diagnostics.get("intervention_to_residual_ratio_mean")
            if ratio is not None:
                ratios.append(float(ratio))
            task_rows.append({
                "task_id": task_id,
                "historical_label": historical_label,
                "historical_feature_score": gen[task_id]["historical_feature_score"],
                "arm": tag,
                "nominal_alpha_times_p99": nominal_alpha,
                "effective_alpha": gen[task_id]["alpha"],
                "passed": new,
                "control_passed": old,
                "fail_to_pass": bool(not old and new),
                "pass_to_fail": bool(old and not new),
                "evaluated_code_changed": code_changed,
                "intervention_to_residual_ratio_mean": ratio,
                "error": row.get("eval_candidate_code_repaired_error"),
            })
        summary.append({
            "arm": tag,
            "nominal_alpha_times_p99": nominal_alpha,
            "effective_alpha": next(iter(gen.values()))["alpha"],
            "passed": sum(bool(row[VERDICT]) for row in current.values()),
            "n": len(current),
            "pass_rate": sum(bool(row[VERDICT]) for row in current.values()) / len(current),
            "fail_to_pass": fail_to_pass,
            "pass_to_fail": pass_to_fail,
            "net_paired_change": fail_to_pass - pass_to_fail,
            "evaluated_code_changed": changed,
            "historical_failures_passed": historical_fail_passed,
            "historical_controls_passed": historical_control_passed,
            "mean_intervention_to_residual_ratio": (
                sum(ratios) / len(ratios) if ratios else 0.0
            ),
        })

    for name, rows in (("summary.csv", summary), ("task_level_results.csv", task_rows)):
        with (args.report_dir / name).open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    x = [row["nominal_alpha_times_p99"] for row in summary]
    y = [row["pass_rate"] for row in summary]
    fig, ax = plt.subplots(figsize=(7.5, 4.5))
    ax.plot(x, y, marker="o", color="#2c7fb8")
    for row in summary:
        ax.annotate(
            f"{row['passed']}/{row['n']}",
            (row["nominal_alpha_times_p99"], row["pass_rate"]),
            xytext=(0, 8), textcoords="offset points", ha="center",
        )
    ax.set_xlabel("Nominal alpha multiplied by feature P99")
    ax.set_ylabel("Pass rate")
    ax.set_ylim(0, 0.35)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(args.report_dir / "pass_rate_by_alpha.png", dpi=180)
    plt.close(fig)

    lines = [
        "# Historical-style ROC-AUC steering: DeepSeek feature 4672",
        "",
        "## Design",
        "",
        "This smoke replicates the old feature-962 protocol with the new layer-16 "
        "DeepSeek base-versus-merged CrossCoder. Feature 4672 was the strongest "
        "failure-associated feature in the existing base-side HumanEval+ ROC-AUC "
        "screen (ROC-AUC 0.7944; maxT-adjusted p=0.0002).",
        "",
        f"The fixed sample contains {selection['n_failures']} historical failures and "
        f"{selection['n_controls']} historical pass controls with the largest feature "
        "scores. The natural scale is P99 of positive base-side encoder contribution "
        f"over exact evaluated tokens: `{selection['p99_scale']:.6f}`. Generation was "
        "greedy with 192 new tokens, and the layer-16 base decoder vector was subtracted "
        "from the last token at every decoding step.",
        "",
        "## Results",
        "",
        "| Nominal alpha | Effective alpha | Passed | Fail→pass | Pass→fail | Changed evaluated code | Mean ||delta||/||residual|| |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['nominal_alpha_times_p99']:.2f} | {row['effective_alpha']:.3f} | "
            f"{row['passed']}/{row['n']} | {row['fail_to_pass']} | "
            f"{row['pass_to_fail']} | {row['evaluated_code_changed']}/{row['n']} | "
            f"{row['mean_intervention_to_residual_ratio']:.4f} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "The historical result was not reproduced for feature 4672. No intervention "
        "corrected a control failure, while every nonzero arm regressed HumanEval/23. "
        "Most generations were invariant, showing that the hook was active but this "
        "decoder direction rarely crossed a greedy decoding boundary. The regression "
        "was caused by a longer continuation ending inside an unterminated docstring; "
        "postprocessing made no repair and reported no suspicious repair.",
        "",
        "This is a valid negative result for one statistically strong feature, not a "
        "general rejection of historical-style selection. The old protocol also used "
        "decoder-side specificity and qualitative coherence. Feature 4672 has strong "
        "failure prediction, but ROC-AUC alone does not establish that subtracting its "
        "decoder vector removes the failure mechanism.",
    ]
    (args.report_dir / "index.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
