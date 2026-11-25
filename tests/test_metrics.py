"""Unit tests for the probability metrics."""

import numpy as np
import pytest

from azml_market.training.metrics import brier_score, reliability_curve, spiegelhalter_test


def test_brier_score_known_values():
    assert brier_score(np.array([1, 0]), np.array([1.0, 0.0])) == 0.0
    assert brier_score(np.array([1, 0]), np.array([0.5, 0.5])) == pytest.approx(0.25)


def test_reliability_curve_bins_and_counts():
    y = np.array([0, 1, 1, 1])
    p = np.array([0.05, 0.15, 0.95, 0.99])
    curve = reliability_curve(y, p, n_bins=10)
    assert curve["n"].sum() == 4
    assert curve["bin_lower"].tolist() == [0.0, 0.1, 0.9]
    assert curve.loc[2, "observed_rate"] == 1.0


def test_spiegelhalter_does_not_reject_true_probabilities():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.1, 0.9, size=5000)
    y = (rng.random(5000) < p).astype(int)
    _, p_value = spiegelhalter_test(y, p)
    assert p_value > 0.05


def test_spiegelhalter_rejects_shifted_probabilities():
    rng = np.random.default_rng(0)
    p = rng.uniform(0.1, 0.9, size=5000)
    y = (rng.random(5000) < p).astype(int)
    _, p_value = spiegelhalter_test(y, np.clip(p + 0.15, 0.01, 0.99))
    assert p_value < 0.001
