#!/usr/bin/env python3
import csv, json
from pathlib import Path

import numpy as np
import pandas as pd
from transformers import AutoTokenizer

root = Path("reports/codellama_base_merged_topk100_v1_repetition_attribution")
out = Path("runs/codellama_bm_repetition_10token_probe_v1")
out.mkdir(parents=True, exist_ok=True)
features = [9608, 1058, 8313, 5411, 7915]
rows = {
    r["task_id"]: r
    for r in map(json.loads, (root / "repetition_candidate_cohort.jsonl").read_text().splitlines())
}
boundaries = pd.read_csv(root / "boundary_manifest.csv").set_index("task_id")
z = np.load(root / "task_feature_attributions.npz")
task_ids = [str(x) for x in z["task_ids"]]
positions = z["max_attribution_positions"]
tok = AutoTokenizer.from_pretrained("meta-llama/CodeLlama-7b-hf", local_files_only=True, use_fast=True)

summary = []
for feature in features:
    inputs, manifest = [], []
    for i, task_id in enumerate(task_ids):
        local = int(positions[i, feature])
        if local < 0:
            continue
        source = rows[task_id]
        code = source["candidate_code_repaired"]
        prompt = source["prompt"].rstrip() + "\n"
        start = len(prompt) if code.startswith(prompt) else max(0, code.find(source["raw_completion"]))
        enc = tok(code, add_special_tokens=False, return_offsets_mapping=True)
        offsets = np.asarray(enc["offset_mapping"], dtype=np.int64)
        evaluated = np.flatnonzero((offsets[:, 1] > start) & (offsets[:, 0] < len(code)))
        boundary_char = int(boundaries.loc[task_id, "boundary_char"])
        prefix_ids = [j for j, (_, end) in enumerate(offsets) if int(end) <= boundary_char]
        if not prefix_ids:
            raise ValueError(f"empty prefix: {task_id}")
        bad_global = len(prefix_ids)
        if bad_global >= len(enc["input_ids"]):
            raise ValueError(f"bad token outside sequence: {task_id}")
        expected_bad = int(boundaries.loc[task_id, "bad_token_id"])
        if int(enc["input_ids"][bad_global]) != expected_bad:
            raise ValueError(f"bad-token mismatch: {task_id}")
        global_position = int(evaluated[local])
        if global_position >= bad_global:
            raise ValueError(f"intervention not pre-boundary: {task_id}")
        prefix = code[:boundary_char]
        if tok(prefix, add_special_tokens=False).input_ids != enc["input_ids"][:bad_global]:
            raise ValueError(f"prefix tokenization mismatch: {task_id}")
        inputs.append({
            "benchmark": "bigcodebench", "task_id": task_id,
            "task_idx": int(task_id.split("/")[-1]), "entry_point": source["entry_point"],
            "prompt": prefix, "original_prompt": source["prompt"],
            "seed": 1000 + int(task_id.split("/")[-1]) * 100,
            "canonical_bad_token_id": expected_bad,
            "canonical_bad_token": str(boundaries.loc[task_id, "bad_token_text"]),
            "repeat_motif": str(boundaries.loc[task_id, "boundary_text"]),
            "target_local_evaluated_position": local,
        })
        manifest.append({"task_id": task_id, "token_position": global_position})
    idir = out / f"feature_{feature}"
    idir.mkdir(exist_ok=True)
    (idir / "input.jsonl").write_text("".join(json.dumps(r) + "\n" for r in inputs))
    with (idir / "positions.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["task_id", "token_position"])
        w.writeheader(); w.writerows(manifest)
    summary.append({"feature_id": feature, "support": len(inputs)})
(out / "cohort_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
print(json.dumps(summary, indent=2))
