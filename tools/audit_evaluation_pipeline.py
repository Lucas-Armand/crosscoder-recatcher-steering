#!/usr/bin/env python3
"""Audit raw -> repaired -> evaluator lineage and build human-readable samples."""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


MODELS = (
    "deepseek_base",
    "deepseek_finetuned",
    "deepseek_merged",
    "codellama_base",
    "codellama_finetuned",
    "codellama_merged",
)
BENCHMARKS = ("humanevalplus", "bigcodebench")


class Source:
    def __init__(self, root: str) -> None:
        self.root = root.rstrip("/")

    def read(self, relative: str) -> str:
        location = f"{self.root}/{relative}"
        if self.root.startswith("gs://"):
            result = subprocess.run(
                ["gcloud", "storage", "cat", location],
                text=True,
                capture_output=True,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or f"could not read {location}")
            return result.stdout
        return Path(location).read_text(encoding="utf-8")


def jsonl(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def key(row: dict[str, Any]) -> tuple[int, int]:
    return int(row["task_idx"]), int(row.get("gen_idx", 0))


def evaluation_map(
    source: Source, benchmark: str, model: str
) -> dict[str, dict[str, Any]]:
    stem = f"{benchmark}__{model}"
    if benchmark == "humanevalplus":
        rows = jsonl(source.read(f"eval/humanevalplus/{stem}_eval.jsonl"))
        return {
            row["task_id"]: {
                "status": (
                    "pass" if row.get("eval_candidate_code_repaired_correct") else "fail"
                ),
                "error": row.get("eval_candidate_code_repaired_error"),
                "time": row.get("eval_candidate_code_repaired_time"),
            }
            for row in rows
        }

    payload = json.loads(
        source.read(f"eval/bigcodebench015/{stem}_eval_results.json")
    )
    result: dict[str, dict[str, Any]] = {}
    for task_id, attempts in payload.get("eval", {}).items():
        attempt = attempts[0] if attempts else {}
        result[task_id] = {
            "status": str(attempt.get("status", "missing")).lower(),
            "error": attempt.get("details"),
            "time": None,
        }
    return result


def clip(value: Any, limit: int = 1200) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[:limit] + "\n... [truncated]"


def choose_samples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for wanted in ("pass", "fail"):
        match = next((row for row in rows if row["verdict"] == wanted), None)
        if match is not None:
            selected.append(match)
    return selected


def render_samples(samples: list[dict[str, Any]]) -> str:
    lines = [
        "# Evaluation pipeline samples",
        "",
        "Each section traces the generated completion, the exact candidate consumed by",
        "post-processing, the repaired candidate consumed by the evaluator, and the final",
        "verdict. Selection is deterministic: the lowest-index pass and failure available",
        "for each model/benchmark pair.",
        "",
    ]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in samples:
        grouped.setdefault((row["benchmark"], row["model"]), []).append(row)

    for benchmark in BENCHMARKS:
        for model in MODELS:
            rows = grouped.get((benchmark, model), [])
            lines.extend([f"## {benchmark} / {model}", ""])
            if not rows:
                lines.extend(["No auditable sample was available.", ""])
                continue
            observed = {row["verdict"] for row in rows}
            if "pass" not in observed:
                lines.extend(["No passing example exists in this evaluated result set.", ""])
            for row in rows:
                lines.extend(
                    [
                        f"### {row['verdict'].upper()}: {row['task_id']}",
                        "",
                        f"- Raw generator verdict: `{row['raw_generator_verdict']}`",
                        f"- Original compiled: `{row['compile_ok_original']}`",
                        f"- Post-processing changed code: `{row['changed']}`",
                        f"- Rules: `{row['rules_applied']}`",
                        f"- Repaired compiled: `{row['compile_ok_repaired']}`",
                        f"- Evaluator verdict: `{row['verdict']}`",
                        f"- Evaluator detail: `{clip(row['evaluator_error'], 300)}`",
                        "",
                        "Network completion:",
                        "",
                        "```python",
                        clip(row["raw_completion"]),
                        "```",
                        "",
                        "Candidate before post-processing:",
                        "",
                        "```python",
                        clip(row["candidate_code_original"]),
                        "```",
                        "",
                        "Candidate evaluated after post-processing:",
                        "",
                        "```python",
                        clip(row["candidate_code_repaired"]),
                        "```",
                        "",
                    ]
                )
    return "\n".join(lines)


def render_summary(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| Benchmark | Model | Evaluated | Pass | Pass % | Fail | Fail % | Timeout/other | Timeout/other % | Changed by post-processing |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {benchmark} | {model} | {evaluated} | {passed} | {pass_rate:.2f}% | "
            "{failed} | {fail_rate:.2f}% | {indeterminate} | {indeterminate_rate:.2f}% | "
            "{changed} |".format(**row)
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source = Source(args.dataset)
    summaries: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    failures: list[str] = []

    for benchmark in BENCHMARKS:
        for model in MODELS:
            stem = f"{benchmark}__{model}"
            raw_rows = jsonl(source.read(f"raw_results/{stem}_results.jsonl"))
            repaired_rows = jsonl(source.read(f"results/{stem}_results.jsonl"))
            evaluated = evaluation_map(source, benchmark, model)
            raw_by_key = {key(row): row for row in raw_rows}
            repair_by_key = {key(row): row for row in repaired_rows}

            if set(raw_by_key) != set(repair_by_key):
                failures.append(f"{stem}: raw/repaired task keys differ")

            audited: list[dict[str, Any]] = []
            status_counts: Counter[str] = Counter()
            changed = 0
            for row_key in sorted(raw_by_key):
                raw = raw_by_key[row_key]
                repaired = repair_by_key.get(row_key)
                if repaired is None:
                    continue
                task_id = raw["task_id"]
                outcome = evaluated.get(task_id, {"status": "missing", "error": "missing"})
                status = str(outcome["status"]).lower()
                verdict = "pass" if status == "pass" else "fail"
                status_counts[status] += 1
                changed += int(bool(repaired.get("changed")))

                if repaired.get("candidate_code_original") != raw.get("candidate_code"):
                    failures.append(f"{stem}/{task_id}: raw candidate mismatch")

                audited.append(
                    {
                        "benchmark": benchmark,
                        "model": model,
                        "task_id": task_id,
                        "task_idx": raw["task_idx"],
                        "verdict": verdict,
                        "evaluator_status": status,
                        "evaluator_error": outcome.get("error"),
                        "raw_generator_verdict": raw.get("correct"),
                        "prompt": raw.get("prompt"),
                        "raw_completion": raw.get("raw_completion"),
                        "candidate_code_original": repaired.get("candidate_code_original"),
                        "candidate_code_repaired": repaired.get("candidate_code_repaired"),
                        "compile_ok_original": repaired.get("compile_ok_original"),
                        "compile_ok_repaired": repaired.get("compile_ok_repaired"),
                        "changed": repaired.get("changed"),
                        "rules_applied": repaired.get("rules_applied", []),
                    }
                )

            total = len(audited)
            passed = status_counts["pass"]
            failed = status_counts["fail"]
            indeterminate = total - passed - failed
            if total != len(raw_rows) or "missing" in status_counts:
                failures.append(
                    f"{stem}: evaluated={total}, raw={len(raw_rows)}, statuses={dict(status_counts)}"
                )
            summaries.append(
                {
                    "benchmark": benchmark,
                    "model": model,
                    "evaluated": total,
                    "passed": passed,
                    "pass_rate": 100 * passed / total if total else 0,
                    "failed": failed,
                    "fail_rate": 100 * failed / total if total else 0,
                    "indeterminate": indeterminate,
                    "indeterminate_rate": 100 * indeterminate / total if total else 0,
                    "changed": changed,
                    "status_counts": dict(status_counts),
                }
            )
            samples.extend(choose_samples(audited))

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "paper_v1_evaluation_audit.json").write_text(
        json.dumps(
            {"status": "FAIL" if failures else "PASS", "failures": failures, "summary": summaries},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "paper_v1_evaluation_samples.json").write_text(
        json.dumps(samples, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (args.output_dir / "paper_v1_evaluation_samples.md").write_text(
        render_samples(samples), encoding="utf-8"
    )
    (args.output_dir / "paper_v1_evaluation_summary.md").write_text(
        render_summary(summaries) + "\n", encoding="utf-8"
    )

    print(render_summary(summaries))
    if failures:
        print(json.dumps({"failures": failures}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
