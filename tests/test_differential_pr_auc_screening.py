from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from run_differential_pr_auc_screening import (
    CATEGORIES,
    maximum_positive_contribution,
    positive_contribution_percentiles,
    permutation_statistics,
    roc_auc_from_order,
)
from run_pr_auc_feature_screening import pr_auc_both, prepare_pr_order


def test_model_side_contribution_is_positive_max_without_bias():
    hidden = np.array([[1.0, 2.0], [-3.0, 1.0]], dtype=np.float32)
    weight = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.float32)
    actual = maximum_positive_contribution(
        hidden, np.array([True, True]), weight, "cpu"
    )
    np.testing.assert_allclose(actual, [1.0, 0.0])


def test_model_side_positive_contribution_percentiles():
    hidden = np.array([[1.0, 2.0], [-3.0, 1.0]], dtype=np.float32)
    weight = np.array([[1.0, 0.0], [0.0, -1.0]], dtype=np.float32)
    actual = positive_contribution_percentiles(
        hidden, np.array([True, True]), weight, "cpu", [50, 100]
    )
    np.testing.assert_allclose(actual, [[0.5, 0.0], [1.0, 0.0]])


def test_tie_aware_roc_auc_from_precomputed_order():
    scores = np.array(
        [[0.0, 1.0], [0.0, 2.0], [1.0, 3.0], [1.0, 4.0]],
        dtype=np.float32,
    )
    labels = np.array([0, 0, 1, 1], dtype=np.int8)
    order, ties = prepare_pr_order(scores)
    np.testing.assert_allclose(roc_auc_from_order(order, ties, labels), [1.0, 1.0])


def test_four_category_permutation_correction_is_reproducible(tmp_path):
    delta = np.array(
        [[0.0, 3.0], [1.0, 2.0], [2.0, 1.0], [3.0, 0.0]],
        dtype=np.float32,
    )
    regression = np.array([0, 0, 1, 1], dtype=np.int8)
    order, ties = prepare_pr_order(delta)
    reverse_order, reverse_ties = prepare_pr_order(-delta)
    high_regression, high_improvement = pr_auc_both(order, ties, regression)
    low_regression, low_improvement = pr_auc_both(
        reverse_order, reverse_ties, regression
    )
    observed = {
        "variant_increase_associated_with_regression": high_regression,
        "variant_decrease_associated_with_regression": low_regression,
        "variant_increase_associated_with_improvement": high_improvement,
        "variant_decrease_associated_with_improvement": low_improvement,
    }
    first = permutation_statistics(
        (order, ties, reverse_order, reverse_ties),
        (order, ties, reverse_order, reverse_ties),
        regression, regression,
        observed, 20, 7, tmp_path / "first",
    )
    second = permutation_statistics(
        (order, ties, reverse_order, reverse_ties),
        (order, ties, reverse_order, reverse_ties),
        regression, regression,
        observed, 20, 7, tmp_path / "second",
    )
    assert set(CATEGORIES) == set(observed)
    np.testing.assert_allclose(first["p_maxT"], second["p_maxT"])
    assert np.all((first["p_maxT"] > 0) & (first["p_maxT"] <= 1))
