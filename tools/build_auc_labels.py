#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


TASK_RE = re.compile(r"(?:BigCodeBench[/_])?(\d+)$")


def normalize_task_id(value: Any) -> str:
    text = str(value).strip()
    match = TASK_RE.search(text)

    if match:
        return str(int(match.group(1)))

    return text


def extract_passed(value: Any) -> bool | None:
    """
    Try to infer whether one evaluated generation passed.
    """
    if isinstance(value, bool):
        return value

    if isinstance(value, str):
        text = value.strip().lower()

        if text in {
            "pass",
            "passed",
            "success",
            "successful",
            "ok",
            "correct",
        }:
            return True

        if text in {
            "fail",
            "failed",
            "failure",
            "error",
            "incorrect",
            "timeout",
            "timed out",
        }:
            return False

        return None

    if isinstance(value, (int, float)):
        if value == 1:
            return True
        if value == 0:
            return False

    if isinstance(value, dict):
        preferred_keys = [
            "passed",
            "pass",
            "success",
            "correct",
            "status",
            "result",
            "base_status",
            "plus_status",
        ]

        for key in preferred_keys:
            if key in value:
                result = extract_passed(value[key])
                if result is not None:
                    return result

        # BigCodeBench often stores execution details in a list/dict.
        for child in value.values():
            result = extract_passed(child)
            if result is not None:
                return result

    if isinstance(value, list):
        if not value:
            return None

        inferred = [
            extract_passed(item)
            for item in value
        ]
        inferred = [
            item for item in inferred
            if item is not None
        ]

        if not inferred:
            return None

        # One generation per task in this experiment.
        # If several statuses exist, pass only if at least one passed.
        return any(inferred)

    return None


def find_task_results(
    obj: Any,
    path: str = "root",
) -> list[tuple[str, Any]]:
    """
    Find dictionary entries whose keys look like BigCodeBench task IDs.
    """
    found: list[tuple[str, Any]] = []

    if isinstance(obj, dict):
        for key, value in obj.items():
            normalized = normalize_task_id(key)

            if normalized.isdigit():
                found.append((normalized, value))

            found.extend(
                find_task_results(
                    value,
                    f"{path}.{key}",
                )
            )

    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            if isinstance(value, dict):
                task_id = (
                    value.get("task_id")
                    or value.get("identifier")
                    or value.get("id")
                )

                if task_id is not None:
                    found.append(
                        (
                            normalize_task_id(task_id),
                            value,
                        )
                    )

            found.extend(
                find_task_results(
                    value,
                    f"{path}[{index}]",
                )
            )

    return found


def load_labels(
    path: Path,
    model: str,
) -> list[dict[str, Any]]:
    obj = json.loads(
        path.read_text(encoding="utf-8")
    )

    candidates = find_task_results(obj)

    labels: dict[str, int] = {}

    for task_id, value in candidates:
        if not task_id.isdigit():
            continue

        passed = extract_passed(value)

        if passed is None:
            continue

        label = int(not passed)

        if task_id in labels and labels[task_id] != label:
            raise ValueError(
                f"{path}: conflicting labels for task {task_id}"
            )

        labels[task_id] = label

    if not labels:
        raise RuntimeError(
            f"{path}: no task-level labels could be extracted"
        )

    rows = []

    for task_id in sorted(
        labels,
        key=lambda value: int(value),
    ):
        rows.append(
            {
                "model": model,
                "benchmark": "bigcodebench",
                "task_id": task_id,
                "generation_idx": 0,
                "label": labels[task_id],
            }
        )

    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--eval-root",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )
    args = parser.parse_args()

    models = [
        "deepseek_base",
        "deepseek_finetuned",
        "deepseek_merged",
    ]

    all_rows = []

    for model in models:
        path = (
            args.eval_root
            / f"bigcodebench__{model}_eval_results.json"
        )

        if not path.exists():
            raise FileNotFoundError(path)

        rows = load_labels(path, model)
        all_rows.extend(rows)

        passes = sum(
            row["label"] == 0
            for row in rows
        )
        failures = sum(
            row["label"] == 1
            for row in rows
        )

        print(
            f"{model:24s} "
            f"n={len(rows):4d} "
            f"pass={passes:4d} "
            f"fail={failures:4d} "
            f"pass_rate={passes / len(rows):.4f}"
        )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with args.output.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "model",
                "benchmark",
                "task_id",
                "generation_idx",
                "label",
            ],
        )
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
