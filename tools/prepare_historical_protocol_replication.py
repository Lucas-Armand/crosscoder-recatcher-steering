#!/usr/bin/env python3
"""Prepare the exact 20-task historical steering cohort and token-level scales."""
import argparse, json
from pathlib import Path
import numpy as np

HISTORICAL_TASKS = [
    "HumanEval/5", "HumanEval/10", "HumanEval/33", "HumanEval/36",
    "HumanEval/37", "HumanEval/41", "HumanEval/49", "HumanEval/56",
    "HumanEval/62", "HumanEval/64", "HumanEval/65", "HumanEval/73",
    "HumanEval/74", "HumanEval/77", "HumanEval/78", "HumanEval/80",
    "HumanEval/82", "HumanEval/85", "HumanEval/86", "HumanEval/87",
]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--token-values",type=Path,required=True)
    p.add_argument("--source-results",type=Path,required=True)
    p.add_argument("--output-jsonl",type=Path,required=True)
    p.add_argument("--metadata-json",type=Path,required=True)
    a=p.parse_args()
    z=np.load(a.token_values)
    scales={}
    for column,feature in enumerate(z["feature_ids"]):
        values=z["values"][:,column]
        positive=values[values>0]
        scales[str(int(feature))]={
            "positive_token_count":int(len(positive)),
            "p95":float(np.percentile(positive,95)),
            "p99":float(np.percentile(positive,99)),
            "max":float(positive.max()),
        }
    rows=[json.loads(line) for line in a.source_results.read_text().splitlines() if line.strip()]
    by_id={row["task_id"]:row for row in rows}
    missing=[task for task in HISTORICAL_TASKS if task not in by_id]
    if missing: raise KeyError(f"missing historical tasks: {missing}")
    selected=[by_id[task] for task in HISTORICAL_TASKS]
    a.output_jsonl.parent.mkdir(parents=True,exist_ok=True)
    a.output_jsonl.write_text("".join(json.dumps(row)+"\n" for row in selected))
    a.metadata_json.write_text(json.dumps({
        "cohort":"exact first 20 merged_only_correct tasks printed by historical notebook",
        "task_ids":HISTORICAL_TASKS,"token_level_positive_scales":scales,
    },indent=2)+"\n")
    print(json.dumps(scales,indent=2))
if __name__=="__main__":main()
