#!/usr/bin/env python3
"""Evaluate an explicit BigCodeBench subset with the official 0.1.5 harness."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from bigcodebench.data import get_bigcodebench, load_solutions
from bigcodebench.eval import PASS
from bigcodebench.evaluate import check_correctness


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--parallel", type=int, default=16)
    parser.add_argument("--min-time-limit", type=float, default=0.1)
    args = parser.parse_args()

    problems = get_bigcodebench()
    samples = list(load_solutions(str(args.samples)))
    if not samples:
        raise ValueError("No samples")

    seen = Counter(sample["task_id"] for sample in samples)
    duplicates = sorted(task_id for task_id, count in seen.items() if count != 1)
    if duplicates:
        raise ValueError(f"Expected one sample per selected task: {duplicates}")

    results: dict[str, list[dict]] = defaultdict(list)
    with ProcessPoolExecutor(max_workers=args.parallel) as executor:
        futures = []
        completion_ids: Counter[str] = Counter()
        for sample in samples:
            task_id = sample["task_id"]
            if task_id not in problems:
                raise KeyError(f"Unknown BigCodeBench task: {task_id}")
            solution = sample.get(
                "solution",
                problems[task_id]["complete_prompt"] + sample["completion"],
            )
            completion_id = completion_ids[task_id]
            completion_ids[task_id] += 1
            futures.append(
                executor.submit(
                    check_correctness,
                    completion_id,
                    problems[task_id],
                    solution,
                    sample["_identifier"],
                    args.min_time_limit,
                    20,
                )
            )

        for future in as_completed(futures):
            result = future.result()
            status, details = result["base"]
            results[result["task_id"]].append(
                {
                    "task_id": result["task_id"],
                    "solution": result["solution"],
                    "status": status,
                    "correct": status == PASS,
                    "details": details,
                }
            )

    payload = {
        "benchmark": "bigcodebench",
        "version": "0.1.5",
        "subset_evaluation": True,
        "n_tasks": len(samples),
        "passed": sum(
            row["correct"] for task_rows in results.values() for row in task_rows
        ),
        "eval": dict(sorted(results.items())),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "eval"}, indent=2))


if __name__ == "__main__":
    main()
