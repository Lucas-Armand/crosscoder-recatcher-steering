#!/usr/bin/env python3
"""
Build binary correctness labels from BigCodeBench/HumanEval evaluation JSON files
and optionally compute ROC-AUC by joining them with a score CSV.

Expected evaluation JSON shape:
{
  "date": "...",
  "eval": {
    "BigCodeBench/6": [
      {"task_id": "BigCodeBench/6", "status": "pass", ...}
    ]
  }
}

Expected score CSV columns:
  model, benchmark, task_id, generation_idx, score

Examples:
  python tools/build_auc_labels.py \
      --eval-dir reports/eval_results \
      --labels-out reports/auc_labels.csv

  python tools/build_auc_labels.py \
      --eval-dir reports/eval_results \
      --scores reports/activation_scores.csv \
      --labels-out reports/auc_labels.csv \
      --merged-out reports/auc_samples.csv \
      --summary-out reports/auc_summary.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


PASS_STATUSES = {"pass", "passed", "success", "correct"}


def normalize_model_name(path: Path) -> str:
    """
    Extract model name from filenames such as:
      bigcodebench__deepseek_finetuned_eval_results.json
      humanevalplus__codellama_base_eval_results.json
    """
    name = path.stem
    name = re.sub(r"_eval_results$", "", name)
    if "__" in name:
        return name.split("__", 1)[1]
    return name


def infer_benchmark(path: Path, task_id: str | None = None) -> str:
    lower = path.name.lower()

    if "bigcodebench" in lower:
        return "bigcodebench"
    if "humanevalplus" in lower or "humaneval_plus" in lower:
        return "humanevalplus"
    if "humaneval" in lower:
        return "humanevalplus"

    if task_id:
        task_lower = task_id.lower()
        if task_lower.startswith("bigcodebench/"):
            return "bigcodebench"
        if "humaneval" in task_lower:
            return "humanevalplus"

    return "unknown"


def iter_eval_rows(eval_path: Path) -> Iterable[dict[str, Any]]:
    with eval_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    eval_data = payload.get("eval")
    if not isinstance(eval_data, dict):
        raise ValueError(f"{eval_path}: top-level key 'eval' must be a dictionary")

    model = normalize_model_name(eval_path)

    for outer_task_id, results in eval_data.items():
        if isinstance(results, dict):
            results = [results]

        if not isinstance(results, list):
            raise ValueError(
                f"{eval_path}: eval[{outer_task_id!r}] must be a list or dictionary"
            )

        for generation_idx, result in enumerate(results):
            if not isinstance(result, dict):
                raise ValueError(
                    f"{eval_path}: result for {outer_task_id!r}, generation "
                    f"{generation_idx} is not a dictionary"
                )

            task_id = str(result.get("task_id", outer_task_id))
            status = str(result.get("status", "")).strip().lower()
            label = int(status in PASS_STATUSES)

            details = result.get("details", {})
            if isinstance(details, dict):
                error = details.get("ALL", "")
            else:
                error = str(details)

            yield {
                "model": model,
                "benchmark": infer_benchmark(eval_path, task_id),
                "task_id": task_id,
                "generation_idx": generation_idx,
                "label": label,
                "status": status,
                "error": error or "",
                "eval_file": str(eval_path),
            }


def find_eval_files(eval_dir: Path) -> list[Path]:
    patterns = (
        "*_eval_results.json",
        "*eval_results*.json",
    )

    found: set[Path] = set()
    for pattern in patterns:
        found.update(eval_dir.rglob(pattern))

    files = sorted(p for p in found if p.is_file())
    if not files:
        raise FileNotFoundError(
            f"No evaluation JSON files were found under {eval_dir}"
        )
    return files


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_scores(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"model", "benchmark", "task_id", "generation_idx", "score"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                f"{path}: missing required score columns: {sorted(missing)}"
            )

        rows = []
        for line_number, row in enumerate(reader, start=2):
            try:
                generation_idx = int(row["generation_idx"])
                score = float(row["score"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{path}:{line_number}: invalid generation_idx or score"
                ) from exc

            if not math.isfinite(score):
                raise ValueError(
                    f"{path}:{line_number}: score must be finite, got {score}"
                )

            rows.append(
                {
                    "model": row["model"].strip(),
                    "benchmark": row["benchmark"].strip().lower(),
                    "task_id": row["task_id"].strip(),
                    "generation_idx": generation_idx,
                    "score": score,
                }
            )
        return rows


def canonical_key(row: dict[str, Any]) -> tuple[str, str, str, int]:
    return (
        str(row["model"]).strip(),
        str(row["benchmark"]).strip().lower(),
        str(row["task_id"]).strip(),
        int(row["generation_idx"]),
    )


def rankdata(values: list[float]) -> list[float]:
    """Average ranks for ties, using one-based ranks."""
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)

    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1

        average_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[order[k]] = average_rank
        i = j

    return ranks


def roc_auc(labels: list[int], scores: list[float]) -> float:
    """
    ROC-AUC computed through the Mann-Whitney U statistic.
    Equivalent to sklearn.metrics.roc_auc_score for binary labels.
    """
    positives = sum(labels)
    negatives = len(labels) - positives

    if positives == 0 or negatives == 0:
        return float("nan")

    ranks = rankdata(scores)
    positive_rank_sum = sum(
        rank for rank, label in zip(ranks, labels) if label == 1
    )

    return (
        positive_rank_sum - positives * (positives + 1) / 2.0
    ) / (positives * negatives)


def merge_labels_and_scores(
    labels: list[dict[str, Any]],
    scores: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[tuple[str, str, str, int]], list[tuple[str, str, str, int]]]:
    label_map: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    duplicate_labels = []

    for row in labels:
        key = canonical_key(row)
        if key in label_map:
            duplicate_labels.append(key)
        label_map[key] = row

    if duplicate_labels:
        raise ValueError(
            f"Duplicate evaluation keys found. First examples: {duplicate_labels[:5]}"
        )

    score_map: dict[tuple[str, str, str, int], dict[str, Any]] = {}
    duplicate_scores = []

    for row in scores:
        key = canonical_key(row)
        if key in score_map:
            duplicate_scores.append(key)
        score_map[key] = row

    if duplicate_scores:
        raise ValueError(
            f"Duplicate score keys found. First examples: {duplicate_scores[:5]}"
        )

    common = sorted(set(label_map) & set(score_map))
    labels_without_scores = sorted(set(label_map) - set(score_map))
    scores_without_labels = sorted(set(score_map) - set(label_map))

    merged = []
    for key in common:
        label_row = label_map[key]
        score_row = score_map[key]
        merged.append(
            {
                **label_row,
                "score": score_row["score"],
            }
        )

    return merged, labels_without_scores, scores_without_labels


def build_summary(merged: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for row in merged:
        grouped[(row["model"], row["benchmark"])].append(row)

    summary = []
    for (model, benchmark), rows in sorted(grouped.items()):
        labels = [int(row["label"]) for row in rows]
        scores = [float(row["score"]) for row in rows]
        positives = sum(labels)
        negatives = len(labels) - positives
        auc = roc_auc(labels, scores)

        summary.append(
            {
                "model": model,
                "benchmark": benchmark,
                "n_samples": len(rows),
                "n_positive": positives,
                "n_negative": negatives,
                "positive_rate": positives / len(rows) if rows else float("nan"),
                "roc_auc": auc,
                "auc_defined": not math.isnan(auc),
            }
        )

    # Optional pooled summaries by benchmark
    by_benchmark: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in merged:
        by_benchmark[row["benchmark"]].append(row)

    for benchmark, rows in sorted(by_benchmark.items()):
        labels = [int(row["label"]) for row in rows]
        scores = [float(row["score"]) for row in rows]
        positives = sum(labels)
        negatives = len(labels) - positives
        auc = roc_auc(labels, scores)

        summary.append(
            {
                "model": "__ALL_MODELS__",
                "benchmark": benchmark,
                "n_samples": len(rows),
                "n_positive": positives,
                "n_negative": negatives,
                "positive_rate": positives / len(rows) if rows else float("nan"),
                "roc_auc": auc,
                "auc_defined": not math.isnan(auc),
            }
        )

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create evaluation labels and optionally calculate ROC-AUC."
    )
    parser.add_argument(
        "--eval-dir",
        type=Path,
        required=True,
        help="Directory containing *_eval_results.json files.",
    )
    parser.add_argument(
        "--labels-out",
        type=Path,
        default=Path("reports/auc_labels.csv"),
        help="Output CSV containing one correctness label per generation.",
    )
    parser.add_argument(
        "--scores",
        type=Path,
        help=(
            "Optional score CSV with columns: model, benchmark, task_id, "
            "generation_idx, score."
        ),
    )
    parser.add_argument(
        "--merged-out",
        type=Path,
        default=Path("reports/auc_samples.csv"),
        help="Output CSV containing labels joined with scores.",
    )
    parser.add_argument(
        "--summary-out",
        type=Path,
        default=Path("reports/auc_summary.csv"),
        help="Output CSV containing ROC-AUC summaries.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any evaluation row lacks a score or any score lacks a label.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    eval_files = find_eval_files(args.eval_dir)
    labels: list[dict[str, Any]] = []

    for eval_file in eval_files:
        file_rows = list(iter_eval_rows(eval_file))
        labels.extend(file_rows)
        passed = sum(row["label"] for row in file_rows)
        print(
            f"[labels] {eval_file.name}: "
            f"{len(file_rows)} rows, {passed} pass, {len(file_rows) - passed} fail"
        )

    write_csv(
        args.labels_out,
        labels,
        [
            "model",
            "benchmark",
            "task_id",
            "generation_idx",
            "label",
            "status",
            "error",
            "eval_file",
        ],
    )
    print(f"[written] {args.labels_out} ({len(labels)} rows)")

    if args.scores is None:
        return 0

    scores = read_scores(args.scores)
    merged, labels_without_scores, scores_without_labels = merge_labels_and_scores(
        labels, scores
    )

    if labels_without_scores:
        print(
            f"[warning] {len(labels_without_scores)} labels have no matching score.",
            file=sys.stderr,
        )
        for key in labels_without_scores[:5]:
            print(f"  label only: {key}", file=sys.stderr)

    if scores_without_labels:
        print(
            f"[warning] {len(scores_without_labels)} scores have no matching label.",
            file=sys.stderr,
        )
        for key in scores_without_labels[:5]:
            print(f"  score only: {key}", file=sys.stderr)

    if args.strict and (labels_without_scores or scores_without_labels):
        raise RuntimeError(
            "Strict alignment failed because labels and scores do not match exactly."
        )

    write_csv(
        args.merged_out,
        merged,
        [
            "model",
            "benchmark",
            "task_id",
            "generation_idx",
            "label",
            "score",
            "status",
            "error",
            "eval_file",
        ],
    )
    print(f"[written] {args.merged_out} ({len(merged)} aligned rows)")

    summary = build_summary(merged)
    write_csv(
        args.summary_out,
        summary,
        [
            "model",
            "benchmark",
            "n_samples",
            "n_positive",
            "n_negative",
            "positive_rate",
            "roc_auc",
            "auc_defined",
        ],
    )
    print(f"[written] {args.summary_out}")

    for row in summary:
        auc_text = (
            f"{row['roc_auc']:.6f}"
            if row["auc_defined"]
            else "N/A (only one class)"
        )
        print(
            f"[auc] model={row['model']} benchmark={row['benchmark']} "
            f"n={row['n_samples']} positives={row['n_positive']} "
            f"negatives={row['n_negative']} auc={auc_text}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

