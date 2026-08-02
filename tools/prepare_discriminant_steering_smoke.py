#!/usr/bin/env python3
"""Prepare top LOTO improvement cases and matched residual-direction controls."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scores-csv", type=Path, required=True)
    p.add_argument("--directions-npz", type=Path, required=True)
    p.add_argument("--source-results", type=Path, required=True)
    p.add_argument("--examples", type=int, default=10)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output-dir", type=Path, required=True)
    a = p.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=True)
    with a.scores_csv.open(newline="") as handle:
        scores = [row for row in csv.DictReader(handle)
                  if row["analysis"] == "different_own_text"
                  and row["outcome"] == "improvement"]
    scores.sort(key=lambda row: float(row["leave_one_task_out_margin"]), reverse=True)
    selected = scores[:a.examples]
    source = {json.loads(line)["task_id"]: json.loads(line)
              for line in a.source_results.read_text().splitlines() if line.strip()}
    archive = np.load(a.directions_npz)
    direction_map = {
        str(task): direction.astype(np.float32)
        for task, direction in zip(archive["task_ids"].tolist(), archive["directions"])
    }
    task_ids = [row["task_id"] for row in selected]
    directions = np.stack([direction_map[task] for task in task_ids])
    directions /= np.linalg.norm(directions, axis=1, keepdims=True)
    rng = np.random.default_rng(a.seed)
    random = rng.standard_normal(directions.shape).astype(np.float32)
    random -= (random * directions).sum(axis=1, keepdims=True) * directions
    random /= np.linalg.norm(random, axis=1, keepdims=True)
    (a.output_dir / "input.jsonl").write_text(
        "".join(json.dumps(source[task]) + "\n" for task in task_ids)
    )
    np.savez_compressed(a.output_dir / "expected_directions.npz",
                        task_ids=np.asarray(task_ids), directions=directions)
    np.savez_compressed(a.output_dir / "random_orthogonal_directions.npz",
                        task_ids=np.asarray(task_ids), directions=random)
    (a.output_dir / "design.json").write_text(json.dumps({
        "selection": "top positive different-own-text LOTO margins among base-fail/finetuned-pass tasks",
        "task_ids": task_ids,
        "loto_margins": {row["task_id"]: float(row["leave_one_task_out_margin"]) for row in selected},
        "direction_norm": 1.0,
        "random_control": "seeded unit vector orthogonal to each expected direction",
        "random_seed": a.seed,
        "planned_alphas": [0, 2, 4, 6, -4],
    }, indent=2) + "\n")
    print(json.dumps({"task_ids": task_ids}, indent=2))


if __name__ == "__main__":
    main()
