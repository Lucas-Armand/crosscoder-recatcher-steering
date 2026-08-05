#!/usr/bin/env python3
"""Prepare high-differential pass-to-fail cases for percentile steering."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


FEATURES = ((4815, "p80"), (13439, "p80"), (4567, "p60"))
CASE = "codellama_base_merged_layer16__bigcodebench__layer16__paired_transitions"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate-tasks", type=Path, required=True)
    p.add_argument("--raw-results", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--candidates-per-feature", type=int, default=10)
    p.add_argument("--selected-per-feature", type=int, default=5)
    p.add_argument("--baseline-eval", type=Path)
    a = p.parse_args(); a.output_dir.mkdir(parents=True, exist_ok=True)
    candidates = pd.read_csv(a.candidate_tasks)
    raw_rows = [json.loads(line) for line in a.raw_results.read_text().splitlines() if line]
    raw = {row["task_id"]: row for row in raw_rows}
    design = {"case_id": CASE, "features": [], "candidate_union": []}
    union: dict[str, dict] = {}
    for feature, aggregation in FEATURES:
        selected = candidates[
            candidates["case_id"].eq(CASE)
            & candidates["feature_id"].eq(feature)
            & candidates["aggregation"].eq(aggregation)
            & candidates["transition"].eq("base_pass_variant_fail")
        ].sort_values("differential").head(a.candidates_per_feature)
        if len(selected) != a.candidates_per_feature:
            raise ValueError(f"feature {feature}/{aggregation}: only {len(selected)} candidates")
        rows = []
        for rank, (_, item) in enumerate(selected.iterrows(), 1):
            task_id = str(item.task_id)
            if "/" not in task_id:
                task_id = f"BigCodeBench/{int(float(task_id))}"
            row = dict(raw[task_id])
            row.update({
                "steering_feature_id": feature,
                "selection_aggregation": aggregation,
                "selection_rank": rank,
                "historical_transition": "base_pass_variant_fail",
                "base_contribution": float(item.base_contribution),
                "variant_contribution": float(item.variant_contribution),
                "differential": float(item.differential),
            })
            rows.append(row); union.setdefault(task_id, dict(raw[task_id]))
        path = a.output_dir / f"feature_{feature}_{aggregation}_candidate10.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        design["features"].append({
            "feature_id": feature, "aggregation": aggregation,
            "candidate_tasks": [row["task_id"] for row in rows],
        })
    union_rows = sorted(union.values(), key=lambda row: int(row["task_idx"]))
    (a.output_dir / "alpha0_candidate_union.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in union_rows)
    )
    design["candidate_union"] = [row["task_id"] for row in union_rows]
    (a.output_dir / "design.json").write_text(json.dumps(design, indent=2) + "\n")
    if a.baseline_eval:
        evaluation = json.loads(a.baseline_eval.read_text())
        verdict = {
            task_id: bool(rows[0]["correct"])
            for task_id, rows in evaluation["eval"].items()
        }
        for feature, aggregation in FEATURES:
            source = a.output_dir / f"feature_{feature}_{aggregation}_candidate10.jsonl"
            rows = [json.loads(line) for line in source.read_text().splitlines() if line]
            reproduced = [row for row in rows if not verdict.get(row["task_id"], True)]
            selected = reproduced[:a.selected_per_feature]
            if len(selected) != a.selected_per_feature:
                raise ValueError(
                    f"feature {feature}/{aggregation}: only {len(selected)} reproduced failures"
                )
            path = a.output_dir / f"feature_{feature}_{aggregation}_selected5.jsonl"
            path.write_text("".join(json.dumps(row) + "\n" for row in selected))
            for item in design["features"]:
                if item["feature_id"] == feature:
                    item["selected_reproduced_failures"] = [
                        row["task_id"] for row in selected
                    ]
        (a.output_dir / "design.json").write_text(
            json.dumps(design, indent=2) + "\n"
        )
    print(json.dumps({"features": len(FEATURES), "unique_tasks": len(union_rows)}, indent=2))


if __name__ == "__main__":
    main()
