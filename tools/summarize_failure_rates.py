#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

from crosscoder_common import read_jsonl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-jsonl", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    groups = defaultdict(lambda: {"n": 0, "failures": 0})
    for path in args.results_jsonl:
        for row in read_jsonl(path):
            key = (str(row["benchmark"]), str(row["model_label"]))
            groups[key]["n"] += 1
            groups[key]["failures"] += int(not bool(row["correct"]))

    output_rows = []
    for (benchmark, model), counts in sorted(groups.items()):
        n = counts["n"]
        failures = counts["failures"]
        output_rows.append(
            {
                "benchmark": benchmark,
                "model_label": model,
                "n": n,
                "failures": failures,
                "passes": n - failures,
                "failure_rate": failures / n if n else float("nan"),
                "failure_rate_percent": 100.0 * failures / n if n else float("nan"),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0].keys()))
        writer.writeheader()
        writer.writerows(output_rows)

    for row in output_rows:
        print(
            f'{row["benchmark"]:16s} {row["model_label"]:24s} '
            f'n={row["n"]:4d} failures={row["failures"]:4d} '
            f'failure_rate={row["failure_rate_percent"]:.2f}%'
        )


if __name__ == "__main__":
    main()
