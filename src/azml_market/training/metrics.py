"""Probability metrics: Brier score, reliability curve, Spiegelhalter calibration test."""

import numpy as np
import pandas as pd
from scipy.stats import norm


def brier_score(y: np.ndarray, p: np.ndarray) -> float:
    """Mean squared error between outcomes (0/1) and predicted probabilities. Lower is better."""
    return float(np.mean((np.asarray(p) - np.asarray(y)) ** 2))


def reliability_curve(y: np.ndarray, p: np.ndarray, n_bins: int = 10) -> pd.DataFrame:
    """Observed rate vs mean predicted probability, in equal-width probability bins.

    Empty bins are dropped. A well calibrated model has observed_rate close to mean_predicted.
    """
    df = pd.DataFrame({"y": y, "p": p})
    df["bin"] = np.minimum((df["p"] * n_bins).astype(int), n_bins - 1)
    curve = df.groupby("bin").agg(
        mean_predicted=("p", "mean"), observed_rate=("y", "mean"), n=("y", "size")
    )
    curve["bin_lower"] = curve.index / n_bins
    curve["bin_upper"] = (curve.index + 1) / n_bins
    return curve.reset_index(drop=True)[["bin_lower", "bin_upper", "mean_predicted", "observed_rate", "n"]]


def spiegelhalter_test(y: np.ndarray, p: np.ndarray) -> tuple[float, float]:
    """Spiegelhalter z test of overall calibration. Returns (z, two-sided p-value).

    Under the null hypothesis that the predicted probabilities are the true ones,
    z follows a standard normal distribution. A small p-value means miscalibration.
    """
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    numerator = np.sum((y - p) * (1 - 2 * p))
    denominator = np.sqrt(np.sum((1 - 2 * p) ** 2 * p * (1 - p)))
    z = float(numerator / denominator)
    return z, float(2 * norm.sf(abs(z)))


def evaluate(y: np.ndarray, p: np.ndarray) -> dict[str, float]:
    """Metrics used for logging and for the promotion decision."""
    z, p_value = spiegelhalter_test(y, p)
    return {
        "brier": brier_score(y, p),
        "spiegelhalter_z": z,
        "spiegelhalter_p": p_value,
        "mean_predicted": float(np.mean(p)),
        "observed_rate": float(np.mean(y)),
    }
