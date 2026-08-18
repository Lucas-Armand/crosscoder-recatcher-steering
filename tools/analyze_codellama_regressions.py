#!/usr/bin/env python3
"""Taxonomize CodeLlama base-pass -> merged-fail transitions (extraction v4)."""
from __future__ import annotations

import argparse
import ast
import csv
import difflib
import json
import re
from collections import Counter
from pathlib import Path


def read_jsonl(path: Path) -> dict[str, dict]:
    with path.open() as handle:
        return {row["task_id"]: row for row in map(json.loads, handle)}


def as_bool(value) -> bool:
    return str(value).lower() == "true"


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def bcb_errors(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text())["eval"]
    result = {}
    for task_id, attempts in data.items():
        attempt = attempts[0]
        details = attempt.get("details") or {}
        result[task_id] = " | ".join(f"{key}: {value}" for key, value in details.items())
    return result


def hep_errors(path: Path) -> dict[str, str]:
    result = {}
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            result[row["task_id"]] = row.get("eval_candidate_code_repaired_error") or ""
    return result


def evaluator_category(error: str) -> str:
    rules = (
        (r"timeout|timed out", "timeout"),
        (r"SyntaxError|IndentationError|invalid syntax", "syntax_or_indentation"),
        (r"No module named ['\"]?(task|task_func|task_)", "generated_harness_import"),
        (r"NameError|is not defined", "missing_name_or_import"),
        (r"ModuleNotFoundError|ImportError", "dependency_or_import"),
        (r"AssertionError", "wrong_output_or_logic"),
        (r"TypeError", "wrong_type"),
        (r"ValueError", "unexpected_value"),
        (r"FileNotFound|No such file|does not exist", "file_or_path"),
        (r"AttributeError", "wrong_api_or_attribute"),
        (r"IndexError", "index_edge_case"),
        (r"KeyError", "key_edge_case"),
        (r"RecursionError", "recursion"),
        (r"NotImplementedError", "not_implemented"),
    )
    return next((label for pattern, label in rules if re.search(pattern, error, re.I)), "other_runtime")


def generated_part(row: dict) -> str:
    return row.get("extraction_generated_text") or row.get("raw_completion") or ""


def compile_ok(code: str) -> bool:
    try:
        compile(code, "<candidate>", "exec")
        return True
    except Exception:
        return False


def code_metrics(row: dict, token_count: int) -> dict:
    code = row.get("candidate_code_repaired") or ""
    generated = generated_part(row)
    low = generated.lower()
    lines = generated.splitlines()
    nonempty = [line for line in lines if line.strip()]
    comments = [line for line in nonempty if line.lstrip().startswith("#")]
    test_pattern = re.compile(
        r"(^|\n)\s*(?:#\s*)?(?:if\s+__name__\s*==|class\s+Test|def\s+test_|"
        r"import\s+(?:unittest|pytest)|from\s+(?:task|task_func|task_)\w*\s+import|"
        r"assert\s+\w+\s*\()",
        re.I,
    )
    import_lines = [line.strip() for line in nonempty if re.match(r"\s*(?:from\s+\S+\s+import|import\s+)", line)]
    post_solution_test = bool(test_pattern.search(generated))
    harness_import = bool(re.search(r"from\s+(?:task|task_func|task_)\w*\s+import", generated, re.I))
    empty_markers = bool(re.search(r"\bpass\b|NotImplementedError|TODO", generated, re.I))
    return {
        "chars": len(code),
        "generated_chars": len(generated),
        "lines": len(lines),
        "comment_ratio": len(comments) / max(1, len(nonempty)),
        "post_solution_test": post_solution_test,
        "harness_import": harness_import,
        "generated_import_count": len(import_lines),
        "empty_marker": empty_markers,
        "token_count": token_count,
        "at_generation_limit": token_count >= 500,
        "compile_ok_runtime": compile_ok(code),
        "compile_ok_recorded": as_bool(row.get("compile_ok_repaired", True)),
        "repair_changed": as_bool(row.get("changed", False)),
        "repair_suspicious": as_bool(row.get("suspicious_repair", False)),
        "extraction_ambiguous": as_bool(row.get("extraction_ambiguous", False)),
        "extraction_strategy": row.get("extraction_strategy", ""),
    }


def taxonomy(metrics: dict, error_cat: str) -> tuple[list[str], str]:
    tags = []
    if metrics["post_solution_test"] or metrics["harness_import"] or error_cat == "generated_harness_import":
        tags.append("post_solution_test_or_harness_contamination")
    if metrics["at_generation_limit"]:
        tags.append("generation_limit_or_overgeneration")
    if not metrics["compile_ok_runtime"] or error_cat == "syntax_or_indentation":
        tags.append("syntax_or_incomplete_code")
    if metrics["comment_ratio"] >= 0.38:
        tags.append("commentary_heavy")
    if metrics["empty_marker"]:
        tags.append("empty_or_placeholder_implementation")
    if error_cat in {"missing_name_or_import", "dependency_or_import"}:
        tags.append("missing_required_name_or_import")
    if error_cat == "timeout":
        tags.append("timeout_or_performance")
    if error_cat in {"wrong_type", "wrong_api_or_attribute"}:
        tags.append("api_or_type_mismatch")
    if error_cat in {"unexpected_value", "index_edge_case", "key_edge_case", "file_or_path", "recursion"}:
        tags.append("edge_case_or_exception")
    if error_cat in {"wrong_output_or_logic", "other_runtime"}:
        tags.append("wrong_logic_or_other_runtime")
    precedence = (
        "post_solution_test_or_harness_contamination",
        "syntax_or_incomplete_code",
        "empty_or_placeholder_implementation",
        "missing_required_name_or_import",
        "timeout_or_performance",
        "api_or_type_mismatch",
        "edge_case_or_exception",
        "generation_limit_or_overgeneration",
        "commentary_heavy",
        "wrong_logic_or_other_runtime",
    )
    primary = next((tag for tag in precedence if tag in tags), "unclassified")
    return tags, primary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--post-root", type=Path, required=True)
    parser.add_argument("--eval-root", type=Path, required=True)
    parser.add_argument("--activation-root", type=Path, required=True)
    parser.add_argument("--screening", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    labels = {}
    with (args.repo / "reports/paper_v1_v4_evaluation_labels.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["generation_idx"]) == 0 and row["model"] in {"codellama_base", "codellama_merged"}:
                labels[(row["model"], row["benchmark"], row["task_id"])] = int(row["label"])

    manifest = json.loads((args.activation_root / "capture_manifest.json").read_text())
    tokens = {
        (row["benchmark"], row["task_id"], row["source_text"]): int(row["tokens"])
        for row in manifest
    }
    repairs = {
        (benchmark, model): read_jsonl(args.post_root / f"{benchmark}__codellama_{model}_repaired.jsonl")
        for benchmark in ("bigcodebench", "humanevalplus")
        for model in ("base", "merged")
    }
    errors = {
        "bigcodebench": bcb_errors(args.eval_root / "bigcodebench015/bigcodebench__codellama_merged_eval_results.json"),
        "humanevalplus": hep_errors(args.eval_root / "humanevalplus/humanevalplus__codellama_merged_eval.jsonl"),
    }

    rows = []
    for benchmark in ("bigcodebench", "humanevalplus"):
        task_ids = sorted(task_id for model, bench, task_id in labels if model == "codellama_base" and bench == benchmark)
        for task_id in task_ids:
            if labels[("codellama_base", benchmark, task_id)] != 0 or labels[("codellama_merged", benchmark, task_id)] != 1:
                continue
            base = repairs[(benchmark, "base")][task_id]
            merged = repairs[(benchmark, "merged")][task_id]
            base_metrics = code_metrics(base, tokens[(benchmark, task_id, "codellama_base")])
            merged_metrics = code_metrics(merged, tokens[(benchmark, task_id, "codellama_merged")])
            error = errors[benchmark].get(task_id, "")
            error_cat = evaluator_category(error)
            tags, primary = taxonomy(merged_metrics, error_cat)
            base_code = base.get("candidate_code_repaired") or ""
            merged_code = merged.get("candidate_code_repaired") or ""
            matcher = difflib.SequenceMatcher(None, base_code, merged_code, autojunk=False)
            rows.append({
                "benchmark": benchmark,
                "task_id": task_id,
                "primary_failure_category": primary,
                "failure_tags": ";".join(tags),
                "evaluator_category": error_cat,
                "error_excerpt": error.replace("\n", " ")[:800],
                "code_similarity": matcher.ratio(),
                "common_prefix_chars": matcher.find_longest_match(0, len(base_code), 0, len(merged_code)).size,
                **{f"base_{key}": value for key, value in base_metrics.items()},
                **{f"merged_{key}": value for key, value in merged_metrics.items()},
                "base_code": base_code,
                "merged_code": merged_code,
                "base_generated": generated_part(base),
                "merged_generated": generated_part(merged),
            })

    write_csv(args.output / "regression_failure_cases.csv", rows)
    primary_counts = Counter((row["benchmark"], row["primary_failure_category"]) for row in rows)
    summary_rows = []
    for (benchmark, category), count in sorted(primary_counts.items()):
        denominator = sum(row["benchmark"] == benchmark for row in rows)
        summary_rows.append({"benchmark": benchmark, "taxonomy_level": "primary", "category": category, "count": count, "denominator": denominator, "fraction": count / denominator})
    tag_counts = Counter((row["benchmark"], tag) for row in rows for tag in row["failure_tags"].split(";") if tag)
    for (benchmark, category), count in sorted(tag_counts.items()):
        denominator = sum(row["benchmark"] == benchmark for row in rows)
        summary_rows.append({"benchmark": benchmark, "taxonomy_level": "multilabel", "category": category, "count": count, "denominator": denominator, "fraction": count / denominator})
    write_csv(args.output / "failure_category_summary.csv", summary_rows)

    # Deterministic audit sample: up to 4 cases/category, spread through sorted IDs.
    audit = []
    for key in sorted(primary_counts):
        candidates = [row for row in rows if (row["benchmark"], row["primary_failure_category"]) == key]
        candidates.sort(key=lambda row: row["task_id"])
        indices = sorted(set(round(i * (len(candidates) - 1) / max(1, min(4, len(candidates)) - 1)) for i in range(min(4, len(candidates)))))
        for row in (candidates[index] for index in indices):
            audit.append({
                "benchmark": row["benchmark"], "task_id": row["task_id"],
                "rule_primary": row["primary_failure_category"], "rule_tags": row["failure_tags"],
                "evaluator_category": row["evaluator_category"], "error_excerpt": row["error_excerpt"],
                "merged_tokens": row["merged_token_count"], "merged_generated": row["merged_generated"],
                "base_generated": row["base_generated"], "manual_primary": "", "manual_notes": "",
            })
    write_csv(args.output / "manual_audit_sample.csv", audit)

    top = []
    with (args.screening / "regression_top10_by_specification.csv").open(newline="") as handle:
        top = list(csv.DictReader(handle))
    (args.output / "run_summary.json").write_text(json.dumps({
        "taxonomy_version": "codellama_regressions_v1",
        "population": "generation_idx=0, extraction-v4 labels; base pass (0) -> merged fail (1)",
        "cases": len(rows),
        "by_benchmark": dict(Counter(row["benchmark"] for row in rows)),
        "rule_based": True,
        "manual_audit_rows": len(audit),
        "top_features_reference": sorted({int(row["feature_id"]) for row in top}),
        "limitations": [
            "Behavior tags are heuristics and require manual validation.",
            "Evaluator exceptions do not uniquely identify root cause.",
            "Generation-limit tags can represent overgeneration or truncation.",
        ],
    }, indent=2) + "\n")
    print(json.dumps({"cases": len(rows), "audit_rows": len(audit), "primary_counts": {str(k): v for k, v in primary_counts.items()}}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
