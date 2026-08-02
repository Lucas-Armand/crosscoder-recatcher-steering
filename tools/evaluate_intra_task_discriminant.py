#!/usr/bin/env python3
"""Leave-one-task-out improvement-versus-regression direction evaluation."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import balanced_accuracy_score, roc_auc_score


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directions-npz", type=Path, required=True)
    p.add_argument("--selection-json", type=Path, required=True)
    p.add_argument("--permutations", type=int, default=2000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--output-dir", type=Path, required=True)
    return p.parse_args()


def unit_rows(x):
    norms = np.linalg.norm(x, axis=1, keepdims=True)
    return np.divide(x, norms, out=np.zeros_like(x), where=norms > 0)


def loo_scores(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    margins = np.empty(len(y), dtype=np.float64)
    directions = np.empty_like(x)
    for test in range(len(y)):
        train = np.arange(len(y)) != test
        center = x[train].mean(axis=0)
        normalized = unit_rows(x[train] - center)
        positive = normalized[y[train] == 1].mean(axis=0)
        negative = normalized[y[train] == 0].mean(axis=0)
        direction = positive - negative
        direction /= max(np.linalg.norm(direction), 1e-12)
        positive_score = normalized[y[train] == 1] @ direction
        negative_score = normalized[y[train] == 0] @ direction
        threshold = 0.5 * (positive_score.mean() + negative_score.mean())
        test_vector = unit_rows((x[test:test + 1] - center))[0]
        margins[test] = test_vector @ direction - threshold
        directions[test] = direction
    return margins, directions


def metrics(y, scores):
    return {
        "roc_auc": float(roc_auc_score(y, scores)),
        "balanced_accuracy": float(balanced_accuracy_score(y, scores >= 0)),
        "improvement_recall": float(np.mean(scores[y == 1] >= 0)),
        "regression_recall": float(np.mean(scores[y == 0] < 0)),
    }


def main():
    a = parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=True)
    selection = json.loads(a.selection_json.read_text())
    regressions = selection["base_pass_finetuned_fail"]
    improvements = selection["base_fail_finetuned_pass"]
    tasks = regressions + improvements
    y = np.asarray([0] * len(regressions) + [1] * len(improvements), dtype=np.int8)
    archive = np.load(a.directions_npz)
    analyses = {
        "same_text": "raw_same_text_mean_delta__",
        "different_own_text": "raw_different_own_text_mean_delta__",
    }
    rows = []
    summaries = []
    rng = np.random.default_rng(a.seed)
    permutations = [rng.permutation(y) for _ in range(a.permutations)]
    figure, axes = plt.subplots(2, 1, figsize=(12, 9), sharex=False)
    for axis, (analysis, prefix) in zip(axes, analyses.items()):
        x = np.stack([archive[prefix + task.replace("/", "_")] for task in tasks])
        scores, fold_directions = loo_scores(x, y)
        observed = metrics(y, scores)
        null_auc = np.empty(a.permutations)
        null_balanced = np.empty(a.permutations)
        for index, permuted in enumerate(permutations):
            null_scores, _ = loo_scores(x, permuted)
            null = metrics(permuted, null_scores)
            null_auc[index] = null["roc_auc"]
            null_balanced[index] = null["balanced_accuracy"]
        summary = {
            "analysis": analysis,
            "n_tasks": len(tasks),
            "n_improvements": int(y.sum()),
            "n_regressions": int((y == 0).sum()),
            **observed,
            "roc_auc_permutation_p": float((1 + np.count_nonzero(null_auc >= observed["roc_auc"])) / (a.permutations + 1)),
            "balanced_accuracy_permutation_p": float((1 + np.count_nonzero(null_balanced >= observed["balanced_accuracy"])) / (a.permutations + 1)),
            "null_auc_mean": float(null_auc.mean()),
            "null_auc_sd": float(null_auc.std(ddof=1)),
            "null_balanced_accuracy_mean": float(null_balanced.mean()),
            "null_balanced_accuracy_sd": float(null_balanced.std(ddof=1)),
            "permutations": a.permutations,
            "seed": a.seed,
        }
        summaries.append(summary)
        order = np.argsort(scores)
        colors = np.where(y[order] == 1, "#ff7f0e", "#1f77b4")
        axis.bar(np.arange(len(tasks)), scores[order], color=colors, alpha=.85)
        axis.axhline(0, color="black", linewidth=.9)
        axis.set_ylabel("LOTO discriminant margin")
        axis.set_title(
            f"{analysis}: AUC={observed['roc_auc']:.3f}, "
            f"balanced accuracy={observed['balanced_accuracy']:.3f}"
        )
        axis.set_xticks(np.arange(len(tasks)))
        axis.set_xticklabels([tasks[i].split("/")[-1] for i in order], rotation=90, fontsize=7)
        for index, task in enumerate(tasks):
            rows.append({
                "analysis": analysis, "task_id": task,
                "outcome": "improvement" if y[index] else "regression",
                "leave_one_task_out_margin": scores[index],
                "predicted_outcome": "improvement" if scores[index] >= 0 else "regression",
                "correct": bool((scores[index] >= 0) == bool(y[index])),
            })
        np.savez_compressed(
            a.output_dir / f"{analysis}_leave_one_out_directions.npz",
            task_ids=np.asarray(tasks), directions=fold_directions,
            margins=scores, labels=y,
        )
    figure.tight_layout()
    figure.savefig(a.output_dir / "leave_one_task_out_discriminant.png", dpi=180)
    plt.close(figure)
    with (a.output_dir / "task_scores.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    with (a.output_dir / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summaries[0]))
        writer.writeheader(); writer.writerows(summaries)
    (a.output_dir / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
