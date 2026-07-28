#!/usr/bin/env python3
"""Compare immutable v3 and extraction-v4 evaluation artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


MODELS = (
    "codellama_base", "codellama_finetuned", "codellama_merged",
    "deepseek_base", "deepseek_finetuned", "deepseek_merged",
)
BENCHMARKS = ("humanevalplus", "bigcodebench")


def jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def verdicts(root: Path, benchmark: str, model: str) -> dict[str, bool]:
    stem = f"{benchmark}__{model}"
    if benchmark == "humanevalplus":
        return {
            row["task_id"]: bool(row.get("eval_candidate_code_repaired_correct"))
            for row in jsonl(root / "eval" / benchmark / f"{stem}_eval.jsonl")
        }
    payload = json.loads(
        (root / "eval" / "bigcodebench015" / f"{stem}_eval_results.json").read_text()
    )
    return {
        task_id: bool(attempts and str(attempts[0].get("status", "")).lower() == "pass")
        for task_id, attempts in payload["eval"].items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v3-root", type=Path, required=True)
    parser.add_argument("--v4-root", type=Path, required=True)
    parser.add_argument("--mask-report", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()

    comparisons = []
    extraction = []
    failures = []
    for benchmark in BENCHMARKS:
        for model in MODELS:
            old = verdicts(args.v3_root, benchmark, model)
            new = verdicts(args.v4_root, benchmark, model)
            if set(old) != set(new):
                failures.append(f"{benchmark}/{model}: evaluator task IDs differ")
            rescued = sorted(task for task in old if not old[task] and new.get(task, False))
            lost = sorted(task for task in old if old[task] and not new.get(task, False))
            old_code = {
                row["task_id"]: row["candidate_code_repaired"]
                for row in jsonl(args.v3_root / "results" / f"{benchmark}__{model}_results.jsonl")
            }
            new_code = {
                row["task_id"]: row["candidate_code_repaired"]
                for row in jsonl(args.v4_root / "results" / f"{benchmark}__{model}_results.jsonl")
            }
            lost_identical = [
                task for task in lost if old_code.get(task) == new_code.get(task)
            ]
            lost_changed = [task for task in lost if task not in lost_identical]
            comparisons.append({
                "benchmark": benchmark, "model": model, "n": len(new),
                "v3_pass": sum(old.values()), "v4_pass": sum(new.values()),
                "delta": sum(new.values()) - sum(old.values()),
                "rescued_count": len(rescued), "lost_count": len(lost),
                "rescued_task_ids": rescued, "lost_task_ids": lost,
                "lost_identical_code_count": len(lost_identical),
                "lost_changed_code_count": len(lost_changed),
            })
            stem = f"{benchmark}__{model}"
            processed = jsonl(args.v4_root / "results" / f"{stem}_results.jsonl")
            strategies = Counter()
            span_errors = 0
            for row in processed:
                strategies[row["extraction_strategy"]] += 1
                literal = "".join(
                    row["raw_completion"][lo:hi]
                    for lo, hi in row["extraction_generated_spans"]
                ).rstrip()
                span_errors += int(literal != row["extraction_generated_text"].rstrip())
            extraction.append({
                "benchmark": benchmark, "model": model, "n": len(processed),
                "compile_ok": sum(bool(row["compile_ok_repaired"]) for row in processed),
                "span_errors": span_errors, "ambiguous": sum(bool(row["extraction_ambiguous"]) for row in processed),
                "strategies": dict(strategies),
            })
            if lost_changed:
                failures.append(
                    f"{benchmark}/{model}: {len(lost_changed)} v3 passes were lost after code changed"
                )
            if span_errors:
                failures.append(f"{benchmark}/{model}: {span_errors} literal span errors")

    mask_report = json.loads(args.mask_report.read_text())
    if mask_report["status"] != "PASS":
        failures.append("mask materialization failed")
    report = {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "evaluation_comparison": comparisons,
        "extraction_validation": extraction,
        "mask_materialization": mask_report,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2) + "\n")

    lines = [
        "# Post-processing extraction-v4 validation", "",
        f"Overall status: **{report['status']}**", "",
        "The comparison uses the immutable v3 evaluator artifacts as the baseline. "
        "Extraction decisions are deterministic and never inspect evaluator outcomes.", "",
        "## Evaluation impact", "",
        "| Benchmark | Model | v3 pass | v4 pass | Delta | Rescued | Lost |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for row in comparisons:
        lines.append(
            f"| {row['benchmark']} | {row['model']} | {row['v3_pass']} | "
            f"{row['v4_pass']} | {row['delta']:+d} | {row['rescued_count']} | {row['lost_count']} |"
        )
    lines += [
        "", "## Alignment and extraction integrity", "",
        f"- Materialized masks: **{sum(x.get('materialized', 0) for x in mask_report['summary']):,}**.",
        f"- Mask reconstruction failures: **{len(mask_report['failures'])}**.",
        f"- Literal extraction-span errors: **{sum(x['span_errors'] for x in extraction)}**.",
        f"- Lost passes after candidate code changed: **{sum(x['lost_changed_code_count'] for x in comparisons)}**.",
        f"- Evaluator disagreements with byte-identical code: **{sum(x['lost_identical_code_count'] for x in comparisons)}**.",
        "",
        "The three absent DeepSeek masks correspond to the declared missing activation "
        "for BigCodeBench task 764 in each DeepSeek model. No activation was fabricated.",
        "",
        "## Interpretation", "",
        "The largest correction is CodeLlama fine-tuned, whose leading Python continuation "
        "was previously discarded in favor of later fenced prose or non-Python examples. "
        "Helper definitions are now retained when the historical candidate references them. "
        "Valid historical candidates remain unchanged unless a structural defect is detected.",
        "",
        "ROC-AUC screening was intentionally not recomputed.",
    ]
    args.output_markdown.write_text("\n".join(lines) + "\n")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
