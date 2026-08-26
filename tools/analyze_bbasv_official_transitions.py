#!/usr/bin/env python3
"""Summarize paired official BigCodeBench transitions for completed BBASV arms."""

import argparse
import csv
import json
import re
from pathlib import Path


ARM_RE = re.compile(
    r"bigcodebench__(?P<kind>target|random|sham)_f(?P<feature>\d+)_"
    r"(?P<side>direct|reverse)_(?P<sign>pos|neg)(?P<magnitude>[0-9.]+)_eval\.json$"
)


def load(path: Path):
    with path.open() as f:
        return json.load(f)


def passed_tasks(doc):
    passed = set()
    for task_id, rows in doc["eval"].items():
        row = rows[0] if isinstance(rows, list) else rows
        value = row.get("passed")
        if value is None:
            value = row.get("status") == "pass"
        if value:
            passed.add(task_id)
    return passed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--evaluations", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    baselines = {}
    for side in ("direct", "reverse"):
        path = args.evaluations / f"bigcodebench__baseline_{side}_eval.json"
        if path.exists():
            baselines[side] = passed_tasks(load(path))

    summaries, details = [], []
    for path in sorted(args.evaluations.glob("*_eval.json")):
        match = ARM_RE.match(path.name)
        if not match or match["side"] not in baselines:
            continue
        meta = match.groupdict()
        current = passed_tasks(load(path))
        baseline = baselines[meta["side"]]
        fail_to_pass = sorted(current - baseline)
        pass_to_fail = sorted(baseline - current)
        alpha = float(meta["magnitude"]) * (1 if meta["sign"] == "pos" else -1)
        summaries.append({
            "project": args.project,
            "kind": meta["kind"],
            "feature": int(meta["feature"]),
            "side": meta["side"],
            "alpha": alpha,
            "baseline_passes": len(baseline),
            "current_passes": len(current),
            "fail_to_pass": len(fail_to_pass),
            "pass_to_fail": len(pass_to_fail),
            "net_pass": len(current) - len(baseline),
        })
        for transition, tasks in (("fail_to_pass", fail_to_pass), ("pass_to_fail", pass_to_fail)):
            for task_id in tasks:
                details.append({**summaries[-1], "transition": transition, "task_id": task_id})

    fields = ["project", "kind", "feature", "side", "alpha", "baseline_passes",
              "current_passes", "fail_to_pass", "pass_to_fail", "net_pass"]
    with (args.output_dir / "official_transition_summary.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(summaries)
    with (args.output_dir / "official_transition_tasks.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields + ["transition", "task_id"])
        writer.writeheader(); writer.writerows(details)
    print(json.dumps({"project": args.project, "baselines": {k: len(v) for k,v in baselines.items()},
                      "arms": len(summaries), "transitions": len(details)}, indent=2))


if __name__ == "__main__":
    main()
