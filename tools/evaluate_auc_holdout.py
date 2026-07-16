#!/usr/bin/env python3

import argparse
import csv
from pathlib import Path

import numpy as np


def binary_roc_auc(y_true, scores):
    y_true = np.asarray(y_true, dtype=np.int8)
    scores = np.asarray(scores, dtype=np.float64)

    positive = y_true == 1
    negative = y_true == 0

    n_positive = int(positive.sum())
    n_negative = int(negative.sum())

    if n_positive == 0 or n_negative == 0:
        return float("nan")

    order = np.argsort(scores, kind="mergesort")
    sorted_scores = scores[order]
    ranks = np.empty(len(scores), dtype=np.float64)

    start = 0
    while start < len(scores):
        end = start + 1

        while (
            end < len(scores)
            and sorted_scores[end] == sorted_scores[start]
        ):
            end += 1

        average_rank = ((start + 1) + end) / 2.0
        ranks[order[start:end]] = average_rank
        start = end

    rank_sum_positive = float(ranks[positive].sum())

    return (
        rank_sum_positive
        - n_positive * (n_positive + 1) / 2.0
    ) / (n_positive * n_negative)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--features-npz", type=Path, required=True)
    parser.add_argument("--train-frac", type=float, default=0.7)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    data = np.load(args.features_npz)
    X = data["X"]
    y = data["y"]

    rng = np.random.default_rng(args.seed)

    pass_idx = np.where(y == 0)[0]
    fail_idx = np.where(y == 1)[0]

    rng.shuffle(pass_idx)
    rng.shuffle(fail_idx)

    n_pass_train = int(len(pass_idx) * args.train_frac)
    n_fail_train = int(len(fail_idx) * args.train_frac)

    train_idx = np.concatenate([
        pass_idx[:n_pass_train],
        fail_idx[:n_fail_train],
    ])

    test_idx = np.concatenate([
        pass_idx[n_pass_train:],
        fail_idx[n_fail_train:],
    ])

    rng.shuffle(train_idx)
    rng.shuffle(test_idx)

    X_train = X[train_idx]
    y_train = y[train_idx]

    X_test = X[test_idx]
    y_test = y[test_idx]

    ranking = []

    for feature_id in range(X.shape[1]):
        auc = binary_roc_auc(
            y_train,
            X_train[:, feature_id],
        )

        predictive_auc = max(auc, 1.0 - auc)

        ranking.append(
            (
                feature_id,
                auc,
                predictive_auc,
            )
        )

    ranking.sort(
        key=lambda row: row[2],
        reverse=True,
    )

    rows = []

    for rank, (
        feature_id,
        train_auc,
        train_predictive_auc,
    ) in enumerate(ranking[:args.top_k], start=1):

        test_auc = binary_roc_auc(
            y_test,
            X_test[:, feature_id],
        )

        rows.append({
            "feature_id": feature_id,
            "train_rank": rank,
            "train_auc": train_auc,
            "train_predictive_auc": train_predictive_auc,
            "train_direction": (
                "positive"
                if train_auc >= 0.5
                else "negative"
            ),
            "test_auc": test_auc,
            "test_predictive_auc": max(
                test_auc,
                1.0 - test_auc,
            ),
            "test_direction": (
                "positive"
                if test_auc >= 0.5
                else "negative"
            ),
            "n_train": len(train_idx),
            "failures_train": int(y_train.sum()),
            "n_test": len(test_idx),
            "failures_test": int(y_test.sum()),
        })

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
            fieldnames=list(rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(rows)

    for row in rows:
        print(
            f'feature={row["feature_id"]:5d} '
            f'train={row["train_predictive_auc"]:.4f} '
            f'test={row["test_predictive_auc"]:.4f} '
            f'direction='
            f'{row["train_direction"]}/'
            f'{row["test_direction"]}'
        )


if __name__ == "__main__":
    main()
