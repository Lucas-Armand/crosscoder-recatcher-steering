#!/usr/bin/env python3
import csv
import json
from pathlib import Path

taxonomy = Path("reports/codellama_base_merged_topk100_v1_regression_taxonomy/regression_failure_cases.csv")
source = Path("/tmp/crosscoder_postprocess_and_eval_v4/out/results_repaired/bigcodebench__codellama_merged_repaired.jsonl")
output = Path("runs/codellama_bm_wrong_logic_50_full_sweep_v1/input.jsonl")
wanted = {
    row["task_id"]
    for row in csv.DictReader(taxonomy.open())
    if row["benchmark"] == "bigcodebench"
    and row["primary_failure_category"] == "wrong_logic_or_other_runtime"
}
rows = []
for line in source.read_text().splitlines():
    row = json.loads(line)
    if row.get("task_id") in wanted:
        rows.append({
            "benchmark": "bigcodebench",
            "task_id": row["task_id"],
            "task_idx": row["task_idx"],
            "entry_point": row["entry_point"],
            "prompt": row["prompt"],
            "original_prompt": row["prompt"],
            "seed": 1000 + int(row["task_idx"]),
        })
if len(wanted) != 50 or len(rows) != 50:
    raise RuntimeError(f"expected 50 tasks, got wanted={len(wanted)} rows={len(rows)}")
rows.sort(key=lambda row: row["task_idx"])
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("".join(json.dumps(row) + "\n" for row in rows))
