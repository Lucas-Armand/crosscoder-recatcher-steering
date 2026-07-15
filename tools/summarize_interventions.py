#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from crosscoder_common import read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize evaluated intervention JSONL files containing correct."
    )
    parser.add_argument("--evaluated-jsonl", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    groups = defaultdict(lambda: {"n": 0, "failures": 0})
    for path in args.evaluated_jsonl:
        for row in read_jsonl(path):
            key = (
                row.get("benchmark"),
                row.get("model_label", row.get("target_model_id")),
                int(row["feature_id"]),
                float(row["alpha"]),
            )
            groups[key]["n"] += 1
            groups[key]["failures"] += int(not bool(row["correct"]))

    control_rates = {}
    for key, counts in groups.items():
        benchmark, model, feature_id, alpha = key
        if alpha == 0.0:
            control_rates[(benchmark, model, feature_id)] = counts["failures"] / counts["n"]

    rows = []
    for key, counts in sorted(groups.items()):
        benchmark, model, feature_id, alpha = key
        rate = counts["failures"] / counts["n"]
        control = control_rates.get((benchmark, model, feature_id))
        rows.append(
            {
                "benchmark": benchmark,
                "model": model,
                "feature_id": feature_id,
                "alpha": alpha,
                "n": counts["n"],
                "failures": counts["failures"],
                "failure_rate": rate,
                "failure_rate_percent": 100.0 * rate,
                "delta_vs_alpha0_pp": (
                    100.0 * (rate - control) if control is not None else ""
                ),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    for row in rows:
        print(row)


if __name__ == "__main__":
    main()
