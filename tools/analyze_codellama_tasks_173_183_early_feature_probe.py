#!/usr/bin/env python3
import csv
import glob
import json
import os
import re
from pathlib import Path

root = Path("runs/codellama_bm_tasks_173_183_early_feature_sweep_v1")


def load(path):
    with open(path) as handle:
        return {row["task_id"]: row for row in map(json.loads, handle)}


baseline = load(root / "probe" / "baseline.jsonl")
rows = []
selected = []
pattern = re.compile(r"(base|merged)_only_f(\d+)_(pos|neg)(\d+)$")
for filename in sorted(glob.glob(str(root / "probe" / "*.jsonl"))):
    if filename.endswith("baseline.jsonl"):
        continue
    name = Path(filename).stem
    match = pattern.match(name)
    if not match:
        continue
    side, feature, sign, magnitude = match.groups()
    arm = load(filename)
    changed_tasks = []
    for task_id, base_row in baseline.items():
        if arm[task_id]["raw_completion"] != base_row["raw_completion"]:
            changed_tasks.append(task_id)
    row = {
        "arm": name,
        "side": side,
        "feature_id": int(feature),
        "alpha": int(magnitude) * (1 if sign == "pos" else -1),
        "changed_task_count": len(changed_tasks),
        "changed_tasks": ";".join(changed_tasks),
    }
    rows.append(row)
    if changed_tasks:
        selected.append(row)

fields = ["arm", "side", "feature_id", "alpha", "changed_task_count", "changed_tasks"]
with (root / "probe_summary.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
with (root / "selected_for_full.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    writer.writerows(selected)
print(json.dumps({"arms": len(rows), "selected_for_full": len(selected)}, indent=2))
