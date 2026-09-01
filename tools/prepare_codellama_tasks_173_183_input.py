#!/usr/bin/env python3
import json
from pathlib import Path

source = Path(
    "/tmp/crosscoder_postprocess_and_eval_v4/out/results_repaired/"
    "bigcodebench__codellama_merged_repaired.jsonl"
)
output = Path(
    "runs/codellama_bm_tasks_173_183_exclusive_feature_probe_v1/input.jsonl"
)
wanted = {"BigCodeBench/173", "BigCodeBench/183"}
rows = []
for line in source.read_text().splitlines():
    row = json.loads(line)
    if row.get("task_id") not in wanted:
        continue
    rows.append(
        {
            "benchmark": "bigcodebench",
            "task_id": row["task_id"],
            "task_idx": row["task_idx"],
            "entry_point": row["entry_point"],
            "prompt": row["prompt"],
            "original_prompt": row["prompt"],
            "seed": 1000 + int(row["task_idx"]),
        }
    )
if {row["task_id"] for row in rows} != wanted:
    raise RuntimeError("Did not find both requested tasks")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("".join(json.dumps(row) + "\n" for row in rows))
