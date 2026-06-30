#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path
from typing import Any, Optional


DEFAULT_MODELS = [
    "codellama_base",
    "codellama_finetuned",
    "codellama_merged",
    "deepseek_base",
    "deepseek_finetuned",
    "deepseek_merged",
]

DEFAULT_BENCHMARKS = ["humanevalplus", "bigcodebench"]


def read_jsonl(path: Path):
    rows = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def get_nested(row: dict, keys):
    cur = row
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def get_task_id(row: dict, fallback: Optional[str] = None) -> str:
    candidates = [
        row.get("task_id"),
        row.get("id"),
        row.get("task"),
        row.get("problem_id"),
        get_nested(row, ["raw_record", "task_id"]),
        get_nested(row, ["raw_record", "id"]),
    ]
    for x in candidates:
        if x is not None:
            return str(x)
    return str(fallback)


def get_code(row: dict) -> str:
    candidates = [
        row.get("candidate_code_repaired"),
        row.get("repaired_code"),
        row.get("completion"),
        row.get("solution"),
        row.get("candidate_code"),
        row.get("generated_code"),
        row.get("raw_completion"),
        get_nested(row, ["raw_record", "completion"]),
        get_nested(row, ["raw_record", "solution"]),
        get_nested(row, ["raw_record", "raw_completion"]),
    ]
    for x in candidates:
        if isinstance(x, str) and x.strip():
            return x
    return ""


def truthy(x: Any) -> Optional[bool]:
    if isinstance(x, bool):
        return x
    if isinstance(x, int) and x in (0, 1):
        return bool(x)
    if isinstance(x, str):
        s = x.strip().lower()
        if s in {"true", "passed", "pass", "ok", "success", "correct"}:
            return True
        if s in {"false", "failed", "fail", "error", "timeout", "incorrect", "wrong"}:
            return False
    return None


def infer_correct_from_row(row: dict) -> Optional[bool]:
    positive_negative_keys = [
        "eval_candidate_code_repaired_correct",
        "correct",
        "passed",
        "pass",
        "success",
        "status",
        "result",
        "test_result",
        "base_status",
        "plus_status",
    ]

    for key in positive_negative_keys:
        if key in row:
            val = truthy(row.get(key))
            if val is not None:
                return val

            if isinstance(row.get(key), str):
                s = row[key].strip().lower()
                if "pass" in s or "success" in s or s == "ok":
                    return True
                if any(w in s for w in ["fail", "error", "timeout", "exception", "wrong"]):
                    return False

    # BigCodeBench sometimes stores details in nested fields.
    for key in ["details", "eval", "execution_result"]:
        sub = row.get(key)
        if isinstance(sub, dict):
            val = infer_correct_from_row(sub)
            if val is not None:
                return val

    return None


def load_code_map(root: Path, benchmark: str, model: str):
    stem = f"{benchmark}__{model}"
    paths = [
        root / "results_repaired" / f"{stem}_repaired.jsonl",
        root / "results" / f"{stem}_results.jsonl",
        root / "samples_for_external_eval" / f"{stem}_samples.jsonl",
    ]

    code_by_task = {}
    rows_by_task = {}

    for path in paths:
        for i, row in enumerate(read_jsonl(path)):
            task_id = get_task_id(row, fallback=f"{benchmark}/{i}")
            code = get_code(row)
            if code and task_id not in code_by_task:
                code_by_task[task_id] = code
                rows_by_task[task_id] = row

    return code_by_task, rows_by_task


def load_humaneval_records(root: Path, model: str):
    stem = f"humanevalplus__{model}"
    eval_path = root / "eval" / "humanevalplus" / f"{stem}_eval.jsonl"
    rows = read_jsonl(eval_path)

    records = []
    for i, row in enumerate(rows):
        task_id = get_task_id(row, fallback=f"HumanEval/{i}")
        correct = infer_correct_from_row(row)
        if correct is None:
            continue
        records.append({
            "task_id": task_id,
            "correct": correct,
            "eval_row": row,
            "source": str(eval_path),
        })

    return records


def flatten_json_for_bigcodebench(obj: Any, parent_task_id: Optional[str] = None):
    """
    Tries to support several possible BigCodeBench result schemas.
    Returns candidate dict-like records that may contain task_id + correctness.
    """
    out = []

    if isinstance(obj, dict):
        task_id = (
            obj.get("task_id")
            or obj.get("id")
            or obj.get("problem_id")
            or parent_task_id
        )

        # If dict keys themselves look like task ids, recurse with that key.
        for k, v in obj.items():
            k_as_task = str(k) if re.search(r"(BigCodeBench|HumanEval)/\d+", str(k)) else None
            if k_as_task:
                out.extend(flatten_json_for_bigcodebench(v, parent_task_id=k_as_task))

        if task_id is not None:
            candidate = dict(obj)
            candidate["task_id"] = str(task_id)
            out.append(candidate)

        for v in obj.values():
            if isinstance(v, (dict, list)):
                out.extend(flatten_json_for_bigcodebench(v, parent_task_id=task_id))

    elif isinstance(obj, list):
        for item in obj:
            out.extend(flatten_json_for_bigcodebench(item, parent_task_id=parent_task_id))

    return out


def load_bigcodebench_records(root: Path, model: str):
    candidates = [
        root / "eval" / "bigcodebench015" / f"bigcodebench__{model}_eval_results.json",
        root / "samples_for_external_eval" / f"bigcodebench__{model}_samples_eval_results.json",
    ]

    json_path = None
    for p in candidates:
        if p.exists():
            json_path = p
            break

    if json_path is None:
        print(f"WARNING: no BigCodeBench eval_results.json found for {model}")
        return []

    data = json.loads(json_path.read_text(encoding="utf-8"))
    flat = flatten_json_for_bigcodebench(data)

    seen = set()
    records = []

    for row in flat:
        if not isinstance(row, dict):
            continue

        task_id = get_task_id(row, fallback=None)
        if not task_id or task_id == "None":
            continue

        correct = infer_correct_from_row(row)
        if correct is None:
            continue

        # Keep one result per task_id. For this project, there is one generation per task.
        key = task_id
        if key in seen:
            continue
        seen.add(key)

        records.append({
            "task_id": task_id,
            "correct": correct,
            "eval_row": row,
            "source": str(json_path),
        })

    return records


def print_code_block(code: str, max_chars: int):
    code = code.rstrip()
    if len(code) > max_chars:
        print(code[:max_chars])
        print(f"\n... [TRUNCATED: showing first {max_chars} chars of {len(code)}] ...")
    else:
        print(code)


def inspect_one(root: Path, benchmark: str, model: str, limit: int, max_chars: int):
    print()
    print("=" * 100)
    print(f"{benchmark} / {model}")
    print("=" * 100)

    code_by_task, _ = load_code_map(root, benchmark, model)

    if benchmark == "humanevalplus":
        records = load_humaneval_records(root, model)
    elif benchmark == "bigcodebench":
        records = load_bigcodebench_records(root, model)
    else:
        raise ValueError(benchmark)

    if not records:
        print("No eval records found or could not infer correctness.")
        return

    correct = [r for r in records if r["correct"] is True]
    incorrect = [r for r in records if r["correct"] is False]

    print(f"records parsed: {len(records)}")
    print(f"correct: {len(correct)}")
    print(f"incorrect: {len(incorrect)}")

    for label, bucket in [("CORRECT", correct), ("INCORRECT", incorrect)]:
        print()
        print("-" * 100)
        print(f"{label}: showing up to {limit}")
        print("-" * 100)

        if not bucket:
            print(f"No {label.lower()} examples found.")
            continue

        for idx, rec in enumerate(bucket[:limit], start=1):
            task_id = rec["task_id"]
            code = code_by_task.get(task_id, "")

            print()
            print("#" * 100)
            print(f"{label} EXAMPLE {idx}")
            print(f"benchmark: {benchmark}")
            print(f"model: {model}")
            print(f"task_id: {task_id}")
            print(f"eval_source: {rec['source']}")
            print("#" * 100)

            if not code:
                print("WARNING: code not found for this task_id.")
                print("Eval row keys:", sorted(rec["eval_row"].keys()))
                continue

            print_code_block(code, max_chars=max_chars)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default="/tmp/crosscoder_postprocess_and_eval_v3/out",
        help="Local v3 output root.",
    )
    parser.add_argument(
        "--benchmark",
        default="all",
        choices=["all", "humanevalplus", "bigcodebench"],
    )
    parser.add_argument(
        "--models",
        default=" ".join(DEFAULT_MODELS),
        help="Space-separated model labels.",
    )
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--max-chars", type=int, default=5000)
    args = parser.parse_args()

    root = Path(args.root)

    if not root.exists():
        raise SystemExit(f"Root does not exist: {root}")

    benchmarks = DEFAULT_BENCHMARKS if args.benchmark == "all" else [args.benchmark]
    models = args.models.split()

    for benchmark in benchmarks:
        for model in models:
            inspect_one(
                root=root,
                benchmark=benchmark,
                model=model,
                limit=args.limit,
                max_chars=args.max_chars,
            )


if __name__ == "__main__":
    main()
