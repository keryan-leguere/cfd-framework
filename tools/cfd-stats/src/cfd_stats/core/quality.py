"""Data-quality metrics for CFD time-series."""

from __future__ import annotations

import numpy as np
from scipy import stats as sp_stats


def compute_quality_metrics(data: np.ndarray) -> dict:
    """Assess the quality of a 1-D numeric sample.

    Parameters
    ----------
    data : np.ndarray
        1-D array of observations (NaN allowed).

    Returns
    -------
    dict
        Keys: ``data_completeness``, ``outliers_detected``,
        ``outlier_percentage``, ``stationarity_score``.
    """
    total = data.size
    valid = np.isfinite(data)
    n_valid = int(valid.sum())
    completeness = 100.0 * n_valid / total if total > 0 else 0.0

    clean = data[valid]
    n_outliers = 0
    outlier_pct = 0.0
    if clean.size > 10:
        q1, q3 = np.percentile(clean, [25, 75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        n_outliers = int(((clean < lo) | (clean > hi)).sum())
        outlier_pct = 100.0 * n_outliers / clean.size

    stationarity = _augmented_stationarity_score(clean) if clean.size >= 20 else 0.0

    return {
        "data_completeness": round(completeness, 2),
        "outliers_detected": n_outliers,
        "outlier_percentage": round(outlier_pct, 4),
        "stationarity_score": round(stationarity, 4),
    }


def _augmented_stationarity_score(data: np.ndarray) -> float:
    """Simple stationarity proxy based on variance ratio.

    Splits the series into two halves and compares means and variances.
    Returns a 0-1 score (1 = perfectly stationary).
    """
    n = data.size
    h1, h2 = data[: n // 2], data[n // 2 :]
    mean_diff = abs(h1.mean() - h2.mean())
    pooled_std = float(np.sqrt((h1.var() + h2.var()) / 2))
    if pooled_std == 0:
        return 1.0
    t_like = mean_diff / pooled_std
    # Map t-statistic to a 0-1 score (exponential decay)
    return float(np.exp(-t_like))
