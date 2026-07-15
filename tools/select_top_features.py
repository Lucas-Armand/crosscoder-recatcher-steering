#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--auc-csv", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--min-nonzero-rate", type=float, default=0.01)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with args.auc_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    selected = [
        row for row in rows
        if float(row["nonzero_rate"]) >= args.min_nonzero_rate
    ][: args.top_k]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in selected:
            handle.write(f'{row["feature_id"]}\n')

    print("Selected:", ", ".join(row["feature_id"] for row in selected))


if __name__ == "__main__":
    main()
