#!/usr/bin/env python3
"""Normalize baseline or steering generations into the canonical evaluator contract."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any


def normalize_row(
    row: dict[str, Any], benchmark: str, model_label: str, fallback_index: int
) -> dict[str, Any]:
    output = dict(row)
    prompt = str(row.get("prompt", ""))
    completion = row.get("completion", row.get("raw_completion"))
    if completion is None:
        raise ValueError(f"row {fallback_index} has neither completion nor raw_completion")
    completion = str(completion)
    candidate_code = prompt + completion
    try:
        ast.parse(candidate_code)
        syntax_ok = True
        syntax_error = None
    except SyntaxError as exc:
        syntax_ok = False
        syntax_error = f"{type(exc).__name__}: {exc}"

    task_idx = int(row.get("task_idx", fallback_index))
    task_id = row.get("task_id")
    if not task_id:
        prefix = "HumanEval" if benchmark == "humanevalplus" else "BigCodeBench"
        task_id = f"{prefix}/{task_idx}"

    output.update(
        {
            "benchmark": benchmark,
            "model_label": model_label,
            "task_idx": task_idx,
            "task_id": task_id,
            "gen_idx": int(row.get("gen_idx", 0)),
            "raw_completion": completion,
            "completion": completion,
            "candidate_code": candidate_code,
            "syntax_ok": syntax_ok,
            "syntax_error": syntax_error,
            "correct": None,
            "error": None,
        }
    )
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-jsonl", type=Path, required=True)
    parser.add_argument("--output-jsonl", type=Path, required=True)
    parser.add_argument("--benchmark", choices=["humanevalplus", "bigcodebench"], required=True)
    parser.add_argument("--model-label", required=True)
    args = parser.parse_args()

    rows: list[dict[str, Any]] = []
    for index, line in enumerate(args.input_jsonl.read_text(encoding="utf-8").splitlines()):
        if line.strip():
            rows.append(normalize_row(json.loads(line), args.benchmark, args.model_label, index))

    keys = [(row["task_idx"], row["gen_idx"]) for row in rows]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate (task_idx, gen_idx) keys in normalized output")

    args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.output_jsonl.open("w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"rows": len(rows), "output": str(args.output_jsonl)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
