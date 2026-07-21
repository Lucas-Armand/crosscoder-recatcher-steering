#!/usr/bin/env python3
"""
Robust CrossCoder feature relevance analysis.

Inputs
------
features.npz:
    X: float array [n_examples, n_features]
    y: binary array [n_examples], where 1 = failure and 0 = pass

Optional examples.csv:
    Row-aligned metadata. If it contains a "benchmark" column, benchmark-
    specific AUCs are reported.

Analyses
--------
1. Univariate ROC-AUC for every latent feature.
2. Benjamini-Hochberg FDR from Mann-Whitney/AUC normal approximation.
3. Max-AUC permutation test controlling family-wise selection across all
   tested features.
4. Stratified bootstrap stability for the strongest candidate pool.
5. Repeated stratified holdout validation, with feature selection repeated
   inside each training split.
6. Optional nested Elastic-Net logistic regression when scikit-learn is
   available.
7. Consolidated CSV/JSON/Markdown report of the best features.

The script intentionally preserves the original AUC direction:
    auc > 0.5  -> higher activation associated with failure
    auc < 0.5  -> higher activation associated with passing
and also reports:
    predictive_auc = max(auc, 1 - auc)
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--features-npz", type=Path, required=True)
    p.add_argument("--examples-csv", type=Path, default=None)
    p.add_argument("--output-dir", type=Path, required=True)

    p.add_argument("--top-k", type=int, default=50)
    p.add_argument("--candidate-pool", type=int, default=500)

    p.add_argument("--permutations", type=int, default=1000)
    p.add_argument("--bootstraps", type=int, default=300)
    p.add_argument("--bootstrap-fraction", type=float, default=0.8)

    p.add_argument("--cv-repeats", type=int, default=10)
    p.add_argument("--cv-folds", type=int, default=5)
    p.add_argument("--cv-top-k", type=int, default=20)

    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--skip-elastic-net", action="store_true")
    p.add_argument("--elastic-net-top-m", type=int, default=500)
    return p.parse_args()


def rank_columns(X: np.ndarray) -> np.ndarray:
    """Average ranks, column by column. Ranks start at 1."""
    n, p = X.shape
    ranks = np.empty((n, p), dtype=np.float32)

    for j in range(p):
        values = X[:, j]
        order = np.argsort(values, kind="mergesort")
        sorted_values = values[order]
        col_ranks = np.empty(n, dtype=np.float32)

        start = 0
        while start < n:
            end = start + 1
            while end < n and sorted_values[end] == sorted_values[start]:
                end += 1
            avg_rank = ((start + 1) + end) / 2.0
            col_ranks[order[start:end]] = avg_rank
            start = end

        ranks[:, j] = col_ranks

    return ranks


def auc_from_ranks(ranks: np.ndarray, y: np.ndarray) -> np.ndarray:
    y = np.asarray(y, dtype=np.int8)
    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return np.full(ranks.shape[1], np.nan, dtype=np.float64)

    rank_sum_pos = ranks[y == 1].sum(axis=0, dtype=np.float64)
    u = rank_sum_pos - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def binary_auc(scores: np.ndarray, y: np.ndarray) -> float:
    ranks = rank_columns(np.asarray(scores).reshape(-1, 1))
    return float(auc_from_ranks(ranks, y)[0])


def normal_cdf(x: np.ndarray | float) -> np.ndarray | float:
    arr = np.asarray(x, dtype=np.float64)
    out = 0.5 * (1.0 + np.vectorize(math.erf)(arr / math.sqrt(2.0)))
    return float(out) if out.ndim == 0 else out


def auc_p_values(auc: np.ndarray, n_pos: int, n_neg: int) -> np.ndarray:
    """
    Two-sided normal approximation under H0 AUC=0.5.
    Equivalent to the untied Mann-Whitney null variance.
    """
    if n_pos == 0 or n_neg == 0:
        return np.full_like(auc, np.nan, dtype=np.float64)
    se = math.sqrt((n_pos + n_neg + 1) / (12.0 * n_pos * n_neg))
    z = np.abs((auc - 0.5) / se)
    return 2.0 * (1.0 - normal_cdf(z))


def bh_q_values(pvals: np.ndarray) -> np.ndarray:
    pvals = np.asarray(pvals, dtype=np.float64)
    q = np.full_like(pvals, np.nan)
    valid = np.isfinite(pvals)
    pv = pvals[valid]
    if pv.size == 0:
        return q

    order = np.argsort(pv)
    ranked = pv[order]
    m = len(ranked)
    adjusted = ranked * m / np.arange(1, m + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0.0, 1.0)

    restored = np.empty_like(adjusted)
    restored[order] = adjusted
    q[valid] = restored
    return q


def stratified_subsample_indices(
    y: np.ndarray,
    fraction: float,
    rng: np.random.Generator,
) -> np.ndarray:
    selected = []
    for label in (0, 1):
        idx = np.flatnonzero(y == label)
        size = max(2, int(round(len(idx) * fraction)))
        size = min(size, len(idx))
        selected.append(rng.choice(idx, size=size, replace=False))
    out = np.concatenate(selected)
    rng.shuffle(out)
    return out


def stratified_bootstrap_indices(
    y: np.ndarray,
    rng: np.random.Generator,
) -> np.ndarray:
    selected = []
    for label in (0, 1):
        idx = np.flatnonzero(y == label)
        selected.append(rng.choice(idx, size=len(idx), replace=True))
    out = np.concatenate(selected)
    rng.shuffle(out)
    return out


def repeated_stratified_folds(
    y: np.ndarray,
    folds: int,
    repeats: int,
    rng: np.random.Generator,
):
    if folds < 2:
        raise ValueError("--cv-folds must be >= 2")

    for repeat in range(repeats):
        per_label_chunks = {}
        for label in (0, 1):
            idx = np.flatnonzero(y == label).copy()
            rng.shuffle(idx)
            per_label_chunks[label] = np.array_split(idx, folds)

        for fold in range(folds):
            test = np.concatenate([
                per_label_chunks[0][fold],
                per_label_chunks[1][fold],
            ])
            train = np.setdiff1d(np.arange(len(y)), test, assume_unique=False)
            yield repeat, fold, train, test


def read_examples(path: Path | None, n: int) -> list[dict[str, str]] | None:
    if path is None:
        return None
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != n:
        raise ValueError(
            f"examples.csv row count {len(rows)} != features rows {n}"
        )
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value, digits=4):
    if value is None or not np.isfinite(value):
        return ""
    return f"{float(value):.{digits}f}"


def maybe_run_elastic_net(
    X: np.ndarray,
    y: np.ndarray,
    selected_features: np.ndarray,
    args: argparse.Namespace,
) -> dict:
    if args.skip_elastic_net:
        return {"status": "skipped_by_flag"}

    try:
        from sklearn.linear_model import LogisticRegressionCV
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import RepeatedStratifiedKFold, cross_val_score
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
    except Exception as exc:
        return {
            "status": "skipped_missing_sklearn",
            "error": f"{type(exc).__name__}: {exc}",
        }

    top_m = min(args.elastic_net_top_m, len(selected_features))
    feats = selected_features[:top_m]
    Xs = X[:, feats]

    inner_cv = max(3, min(5, int(y.sum()), int((1 - y).sum())))
    outer = RepeatedStratifiedKFold(
        n_splits=args.cv_folds,
        n_repeats=args.cv_repeats,
        random_state=args.seed,
    )

    model = Pipeline([
        ("scale", StandardScaler()),
        (
            "model",
            LogisticRegressionCV(
                Cs=10,
                cv=inner_cv,
                penalty="elasticnet",
                solver="saga",
                scoring="roc_auc",
                l1_ratios=[0.1, 0.5, 0.9],
                max_iter=5000,
                n_jobs=-1,
                refit=True,
            ),
        ),
    ])

    scores = cross_val_score(
        model,
        Xs,
        y,
        cv=outer,
        scoring="roc_auc",
        n_jobs=1,
    )

    model.fit(Xs, y)
    coefs = model.named_steps["model"].coef_[0]
    nonzero = np.flatnonzero(np.abs(coefs) > 1e-12)
    coef_rows = sorted(
        [
            {
                "feature_id": int(feats[i]),
                "coefficient": float(coefs[i]),
                "abs_coefficient": float(abs(coefs[i])),
            }
            for i in nonzero
        ],
        key=lambda r: r["abs_coefficient"],
        reverse=True,
    )

    return {
        "status": "ok",
        "outer_auc_mean": float(np.mean(scores)),
        "outer_auc_std": float(np.std(scores, ddof=1)),
        "outer_auc_scores": [float(x) for x in scores],
        "n_input_features": int(top_m),
        "n_nonzero_features": int(len(nonzero)),
        "selected_coefficients": coef_rows[:100],
    }


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    start = time.perf_counter()
    data = np.load(args.features_npz)
    if "X" not in data or "y" not in data:
        raise KeyError("features.npz must contain arrays X and y")

    X = np.asarray(data["X"], dtype=np.float32)
    y = np.asarray(data["y"], dtype=np.int8).reshape(-1)

    if X.ndim != 2:
        raise ValueError(f"X must be 2D, got {X.shape}")
    if len(y) != X.shape[0]:
        raise ValueError(f"len(y)={len(y)} != X rows={X.shape[0]}")
    labels = np.unique(y)
    if not np.array_equal(labels, np.array([0, 1], dtype=np.int8)):
        raise ValueError(f"y must contain both 0 and 1, got {labels.tolist()}")

    n, p = X.shape
    n_fail = int(y.sum())
    n_pass = n - n_fail
    examples = read_examples(args.examples_csv, n)

    print(f"[1/7] Ranking {p} features across {n} examples...")
    ranks = rank_columns(X)
    auc = auc_from_ranks(ranks, y)
    predictive_auc = np.maximum(auc, 1.0 - auc)
    direction = np.where(auc >= 0.5, "failure_high", "pass_high")
    pvals = auc_p_values(auc, n_fail, n_pass)
    qvals = bh_q_values(pvals)
    order = np.argsort(-predictive_auc)

    means_pass = X[y == 0].mean(axis=0)
    means_fail = X[y == 1].mean(axis=0)
    nonzero_rate = (X != 0).mean(axis=0)

    print(f"[2/7] Running {args.permutations} max-AUC permutations...")
    null_max = np.empty(args.permutations, dtype=np.float32)
    for b in range(args.permutations):
        yp = rng.permutation(y)
        auc_perm = auc_from_ranks(ranks, yp)
        null_max[b] = np.nanmax(np.maximum(auc_perm, 1.0 - auc_perm))
        if (b + 1) % max(1, args.permutations // 10) == 0:
            print(f"  permutations {b + 1}/{args.permutations}")

    # Family-wise p for each observed feature against null distribution of max statistic.
    fwer_p = np.array([
        (1 + np.sum(null_max >= value)) / (args.permutations + 1)
        for value in predictive_auc
    ])

    pool_size = min(args.candidate_pool, p)
    candidate_ids = order[:pool_size]

    print(
        f"[3/7] Running {args.bootstraps} stratified bootstraps "
        f"on top-{pool_size} candidate pool..."
    )
    top_counts = Counter()
    boot_auc_values = defaultdict(list)
    boot_direction_counts = Counter()

    for b in range(args.bootstraps):
        idx = stratified_bootstrap_indices(y, rng)
        Xb = X[idx][:, candidate_ids]
        yb = y[idx]
        auc_b = auc_from_ranks(rank_columns(Xb), yb)
        pred_b = np.maximum(auc_b, 1.0 - auc_b)
        local_order = np.argsort(-pred_b)
        selected_local = local_order[: min(args.top_k, len(local_order))]

        for li in selected_local:
            fid = int(candidate_ids[li])
            top_counts[fid] += 1

        for li, fid in enumerate(candidate_ids):
            fid = int(fid)
            boot_auc_values[fid].append(float(auc_b[li]))
            if auc_b[li] >= 0.5:
                boot_direction_counts[(fid, "failure_high")] += 1
            else:
                boot_direction_counts[(fid, "pass_high")] += 1

        if (b + 1) % max(1, args.bootstraps // 10) == 0:
            print(f"  bootstraps {b + 1}/{args.bootstraps}")

    print(
        f"[4/7] Repeated stratified holdout validation: "
        f"{args.cv_repeats}x{args.cv_folds}..."
    )
    cv_selected = Counter()
    cv_test_auc = defaultdict(list)
    cv_direction_match = Counter()
    n_splits = 0

    for repeat, fold, train_idx, test_idx in repeated_stratified_folds(
        y, args.cv_folds, args.cv_repeats, rng
    ):
        n_splits += 1
        X_train = X[train_idx]
        y_train = y[train_idx]
        X_test = X[test_idx]
        y_test = y[test_idx]

        train_auc = auc_from_ranks(rank_columns(X_train), y_train)
        train_pred = np.maximum(train_auc, 1.0 - train_auc)
        selected = np.argsort(-train_pred)[: args.cv_top_k]

        for fid in selected:
            fid = int(fid)
            cv_selected[fid] += 1
            test_auc = binary_auc(X_test[:, fid], y_test)
            cv_test_auc[fid].append(test_auc)
            train_dir = train_auc[fid] >= 0.5
            test_dir = test_auc >= 0.5
            if train_dir == test_dir:
                cv_direction_match[fid] += 1

        if n_splits % max(1, (args.cv_repeats * args.cv_folds) // 10) == 0:
            print(f"  validation splits {n_splits}/{args.cv_repeats * args.cv_folds}")

    benchmark_auc = {}
    if examples and "benchmark" in examples[0]:
        print("[5/7] Computing benchmark-specific AUCs...")
        benchmarks = sorted({row["benchmark"] for row in examples})
        for benchmark in benchmarks:
            idx = np.array(
                [i for i, row in enumerate(examples) if row["benchmark"] == benchmark],
                dtype=int,
            )
            if len(np.unique(y[idx])) < 2:
                continue
            auc_bench = auc_from_ranks(rank_columns(X[idx]), y[idx])
            benchmark_auc[benchmark] = auc_bench
    else:
        print("[5/7] No benchmark column; benchmark-specific AUC skipped.")

    print("[6/7] Optional nested Elastic-Net...")
    elastic = maybe_run_elastic_net(X, y, order, args)

    ranking_rows = []
    for rank, fid in enumerate(order, start=1):
        fid = int(fid)
        row = {
            "rank": rank,
            "feature_id": fid,
            "auc": float(auc[fid]),
            "predictive_auc": float(predictive_auc[fid]),
            "direction": str(direction[fid]),
            "mean_pass": float(means_pass[fid]),
            "mean_fail": float(means_fail[fid]),
            "mean_difference_fail_minus_pass": float(means_fail[fid] - means_pass[fid]),
            "nonzero_rate": float(nonzero_rate[fid]),
            "p_value": float(pvals[fid]),
            "bh_q_value": float(qvals[fid]),
            "max_permutation_fwer_p": float(fwer_p[fid]),
            "bootstrap_top_k_frequency": top_counts[fid] / args.bootstraps,
            "bootstrap_auc_median": (
                float(np.median(boot_auc_values[fid]))
                if fid in boot_auc_values else math.nan
            ),
            "bootstrap_auc_q025": (
                float(np.quantile(boot_auc_values[fid], 0.025))
                if fid in boot_auc_values else math.nan
            ),
            "bootstrap_auc_q975": (
                float(np.quantile(boot_auc_values[fid], 0.975))
                if fid in boot_auc_values else math.nan
            ),
            "bootstrap_direction_consistency": (
                max(
                    boot_direction_counts[(fid, "failure_high")],
                    boot_direction_counts[(fid, "pass_high")],
                ) / args.bootstraps
                if fid in boot_auc_values else math.nan
            ),
            "cv_selection_frequency": cv_selected[fid] / n_splits,
            "cv_test_auc_median": (
                float(np.median(cv_test_auc[fid]))
                if fid in cv_test_auc else math.nan
            ),
            "cv_test_predictive_auc_median": (
                float(np.median(np.maximum(
                    cv_test_auc[fid],
                    1.0 - np.asarray(cv_test_auc[fid]),
                )))
                if fid in cv_test_auc else math.nan
            ),
            "cv_test_auc_q025": (
                float(np.quantile(cv_test_auc[fid], 0.025))
                if fid in cv_test_auc else math.nan
            ),
            "cv_test_auc_q975": (
                float(np.quantile(cv_test_auc[fid], 0.975))
                if fid in cv_test_auc else math.nan
            ),
            "cv_direction_consistency": (
                cv_direction_match[fid] / len(cv_test_auc[fid])
                if fid in cv_test_auc else math.nan
            ),
        }

        for benchmark, auc_values in benchmark_auc.items():
            row[f"auc_{benchmark}"] = float(auc_values[fid])
            row[f"predictive_auc_{benchmark}"] = float(
                max(auc_values[fid], 1.0 - auc_values[fid])
            )

        ranking_rows.append(row)

    # Consolidated score: favors out-of-sample consistency, then stability,
    # then corrected significance. It is only for ordering candidates.
    def evidence_score(row):
        cv_auc = row["cv_test_predictive_auc_median"]
        if not np.isfinite(cv_auc):
            cv_auc = 0.5
        return (
            3.0 * max(0.0, cv_auc - 0.5)
            + 1.5 * row["cv_selection_frequency"]
            + 1.0 * row["bootstrap_top_k_frequency"]
            + 0.5 * row["bootstrap_direction_consistency"]
            + 0.5 * (1.0 - row["max_permutation_fwer_p"])
        )

    for row in ranking_rows:
        row["evidence_score"] = evidence_score(row)

    best_rows = sorted(
        ranking_rows[: max(args.candidate_pool, args.top_k)],
        key=lambda r: r["evidence_score"],
        reverse=True,
    )[: args.top_k]

    print("[7/7] Writing reports...")
    write_csv(args.output_dir / "all_features_ranking.csv", ranking_rows)
    write_csv(args.output_dir / "best_features.csv", best_rows)

    permutation_summary = {
        "permutations": args.permutations,
        "observed_max_predictive_auc": float(np.max(predictive_auc)),
        "null_max_mean": float(np.mean(null_max)),
        "null_max_median": float(np.median(null_max)),
        "null_max_q95": float(np.quantile(null_max, 0.95)),
        "null_max_q99": float(np.quantile(null_max, 0.99)),
        "global_max_test_p": float(
            (1 + np.sum(null_max >= np.max(predictive_auc)))
            / (args.permutations + 1)
        ),
    }
    (args.output_dir / "permutation_summary.json").write_text(
        json.dumps(permutation_summary, indent=2),
        encoding="utf-8",
    )
    np.save(args.output_dir / "permutation_null_max_auc.npy", null_max)

    elastic_path = args.output_dir / "elastic_net_summary.json"
    elastic_path.write_text(json.dumps(elastic, indent=2), encoding="utf-8")

    elapsed = time.perf_counter() - start
    summary = {
        "features_npz": str(args.features_npz),
        "examples_csv": str(args.examples_csv) if args.examples_csv else None,
        "n_examples": n,
        "n_pass": n_pass,
        "n_fail": n_fail,
        "failure_rate": n_fail / n,
        "n_features": p,
        "top_k": args.top_k,
        "candidate_pool": pool_size,
        "permutations": args.permutations,
        "bootstraps": args.bootstraps,
        "cv_splits": n_splits,
        "elapsed_seconds": elapsed,
        "permutation": permutation_summary,
        "elastic_net": elastic,
        "best_features": best_rows,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )

    report = [
        "# CrossCoder feature relevance report",
        "",
        f"- Examples: **{n}**",
        f"- Passes: **{n_pass}**",
        f"- Failures: **{n_fail}**",
        f"- Failure rate: **{100*n_fail/n:.2f}%**",
        f"- Features tested: **{p}**",
        f"- Max-AUC permutations: **{args.permutations}**",
        f"- Bootstraps: **{args.bootstraps}**",
        f"- Repeated validation splits: **{n_splits}**",
        "",
        "## Multiple-comparison max test",
        "",
        f"- Observed maximum predictive AUC: **{permutation_summary['observed_max_predictive_auc']:.4f}**",
        f"- Null maximum AUC, 95th percentile: **{permutation_summary['null_max_q95']:.4f}**",
        f"- Null maximum AUC, 99th percentile: **{permutation_summary['null_max_q99']:.4f}**",
        f"- Global max-test p-value: **{permutation_summary['global_max_test_p']:.6f}**",
        "",
        "## Best features",
        "",
        "| Rank | Feature | AUC | Direction | FWER p | Bootstrap top-k | CV selected | CV predictive AUC | Evidence |",
        "|---:|---:|---:|:---|---:|---:|---:|---:|---:|",
    ]

    for i, row in enumerate(best_rows, start=1):
        report.append(
            "| "
            f"{i} | {row['feature_id']} | {row['auc']:.4f} | "
            f"{row['direction']} | {row['max_permutation_fwer_p']:.4f} | "
            f"{row['bootstrap_top_k_frequency']:.3f} | "
            f"{row['cv_selection_frequency']:.3f} | "
            f"{fmt(row['cv_test_predictive_auc_median'])} | "
            f"{row['evidence_score']:.4f} |"
        )

    report += [
        "",
        "## Interpretation",
        "",
        "- `max_permutation_fwer_p` controls selection across all tested features.",
        "- `bootstrap_top_k_frequency` measures ranking stability.",
        "- `cv_selection_frequency` shows how often a feature is rediscovered using training data only.",
        "- `cv_test_predictive_auc_median` measures out-of-sample discrimination.",
        "- Features are strongest when all four signals agree and the direction is stable.",
        "",
        f"Elapsed: **{elapsed/60:.1f} minutes**.",
    ]

    (args.output_dir / "REPORT.md").write_text(
        "\n".join(report) + "\n",
        encoding="utf-8",
    )

    print()
    print("=" * 100)
    print("BEST FEATURES")
    for i, row in enumerate(best_rows[: min(20, len(best_rows))], start=1):
        print(
            f"{i:2d}. feature={row['feature_id']:5d} "
            f"AUC={row['auc']:.4f} "
            f"dir={row['direction']:12s} "
            f"FWER_p={row['max_permutation_fwer_p']:.4f} "
            f"boot_top={row['bootstrap_top_k_frequency']:.3f} "
            f"cv_sel={row['cv_selection_frequency']:.3f} "
            f"cv_pAUC={fmt(row['cv_test_predictive_auc_median'])}"
        )
    print()
    print(f"Report: {args.output_dir / 'REPORT.md'}")
    print(f"Best CSV: {args.output_dir / 'best_features.csv'}")
    print(f"Summary: {args.output_dir / 'summary.json'}")


if __name__ == "__main__":
    main()
