"""Statistical moment calculation including robust statistics and CI.

Provides :class:`MomentCalculator` for computing standard moments,
robust estimators, confidence intervals and goodness-of-fit tests.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
from scipy import stats as sp_stats


class MomentCalculator:
    """Compute statistical moments and diagnostics for a 1-D sample.

    Parameters
    ----------
    data : np.ndarray
        1-D array of observations.
    weights : np.ndarray, optional
        Per-sample weights for weighted averages.
    """

    def __init__(self, data: np.ndarray, weights: np.ndarray | None = None) -> None:
        self.data = np.asarray(data, dtype=float).ravel()
        self.weights = np.asarray(weights, dtype=float).ravel() if weights is not None else None
        if self.weights is not None and self.weights.shape != self.data.shape:
            raise ValueError("weights must have the same length as data")

    # ------------------------------------------------------------------
    # Moments
    # ------------------------------------------------------------------

    def compute_all_moments(self, max_order: int = 4) -> dict:
        """Compute moments up to *max_order*.

        Returns
        -------
        dict
            Keys: ``mean``, ``variance``, ``std``, ``skewness``,
            ``kurtosis``, ``excess_kurtosis``, ``higher_moments``,
            ``raw_moments``, ``central_moments``.
        """
        d = self.data
        w = self.weights

        mean = float(np.average(d, weights=w))
        var = float(np.average((d - mean) ** 2, weights=w))
        std = float(np.sqrt(var))

        raw_moments: dict[int, float] = {}
        central_moments: dict[int, float] = {}
        for k in range(1, max_order + 1):
            raw_moments[k] = float(np.average(d**k, weights=w))
            central_moments[k] = float(np.average((d - mean) ** k, weights=w))

        skewness = central_moments[3] / std**3 if std > 0 else 0.0
        kurtosis = central_moments[4] / std**4 if std > 0 and max_order >= 4 else 0.0
        excess_kurtosis = kurtosis - 3.0

        return {
            "mean": mean,
            "variance": var,
            "std": std,
            "skewness": round(skewness, 6),
            "kurtosis": round(kurtosis, 6),
            "excess_kurtosis": round(excess_kurtosis, 6),
            "higher_moments": {k: round(central_moments[k], 10) for k in range(2, max_order + 1)},
            "raw_moments": {k: round(v, 10) for k, v in raw_moments.items()},
            "central_moments": {k: round(v, 10) for k, v in central_moments.items()},
        }

    # ------------------------------------------------------------------
    # Robust statistics
    # ------------------------------------------------------------------

    def compute_robust_statistics(self) -> dict:
        """Outlier-robust summary statistics.

        Returns
        -------
        dict
            Keys: ``median``, ``mad``, ``iqr``, ``q25``, ``q75``, ``q95``,
            ``q99``, ``trimmed_mean_5``, ``winsorized_mean``.
        """
        d = self.data
        q25, q50, q75, q95, q99 = np.percentile(d, [25, 50, 75, 95, 99])
        mad = float(np.median(np.abs(d - q50)))
        iqr = float(q75 - q25)

        trimmed = sp_stats.trim_mean(d, proportiontocut=0.05)
        winsorized = float(sp_stats.mstats.winsorize(d, limits=[0.05, 0.05]).mean())

        return {
            "median": float(q50),
            "mad": mad,
            "iqr": iqr,
            "q25": float(q25),
            "q75": float(q75),
            "q95": float(q95),
            "q99": float(q99),
            "trimmed_mean_5": round(float(trimmed), 10),
            "winsorized_mean": round(winsorized, 10),
        }

    # ------------------------------------------------------------------
    # Confidence intervals (bootstrap)
    # ------------------------------------------------------------------

    def compute_confidence_intervals(
        self,
        confidence: float = 0.95,
        n_bootstrap: int = 1000,
        rng: np.random.Generator | None = None,
    ) -> dict:
        """Bootstrap confidence intervals for mean, std, and median.

        Returns
        -------
        dict
            Keys: ``mean_ci``, ``std_ci``, ``median_ci`` – each a
            ``(lower, upper)`` tuple.
        """
        gen = rng or np.random.default_rng()
        d = self.data
        n = d.size
        alpha = (1 - confidence) / 2

        means = np.empty(n_bootstrap)
        stds = np.empty(n_bootstrap)
        medians = np.empty(n_bootstrap)

        for i in range(n_bootstrap):
            sample = gen.choice(d, size=n, replace=True)
            means[i] = sample.mean()
            stds[i] = sample.std(ddof=1)
            medians[i] = np.median(sample)

        def _ci(arr: np.ndarray) -> tuple[float, float]:
            lo = float(np.percentile(arr, 100 * alpha))
            hi = float(np.percentile(arr, 100 * (1 - alpha)))
            return (lo, hi)

        return {
            "mean_ci": _ci(means),
            "std_ci": _ci(stds),
            "median_ci": _ci(medians),
        }

    # ------------------------------------------------------------------
    # Goodness of fit
    # ------------------------------------------------------------------

    def goodness_of_fit(self) -> dict:
        """Normality and distribution-fit diagnostics.

        Returns
        -------
        dict
            Keys: ``shapiro_wilk``, ``anderson_darling``,
            ``kolmogorov_smirnov``, ``jarque_bera``, ``is_normal``,
            ``recommended_distribution``.
        """
        d = self.data

        # Shapiro-Wilk (max 5000 samples)
        sw_sample = d[:5000] if d.size > 5000 else d
        sw_stat, sw_p = sp_stats.shapiro(sw_sample)

        # Anderson-Darling
        ad_result = sp_stats.anderson(d, dist="norm")
        ad_stat = float(ad_result.statistic)
        # Use the 5% significance level when available
        if hasattr(ad_result, "critical_values") and len(ad_result.critical_values) > 2:
            ad_critical = float(ad_result.critical_values[2])
            ad_reject = ad_stat > ad_critical
        else:
            # Newer scipy with method= returns p-value
            p = getattr(ad_result, "pvalue", None)
            ad_reject = (p is not None and p < 0.05) or ad_stat > 0.752

        # Kolmogorov-Smirnov vs normal
        ks_stat, ks_p = sp_stats.kstest(d, "norm", args=(d.mean(), d.std(ddof=1)))

        # Jarque-Bera
        jb_stat, jb_p = sp_stats.jarque_bera(d)

        is_normal = sw_p > 0.05 and ks_p > 0.05 and not ad_reject

        recommended = self._recommend_distribution(d, is_normal)

        return {
            "shapiro_wilk": {"statistic": round(float(sw_stat), 6), "p_value": round(float(sw_p), 6)},
            "anderson_darling": {"statistic": round(float(ad_result.statistic), 6), "reject_normal": ad_reject},
            "kolmogorov_smirnov": {"statistic": round(float(ks_stat), 6), "p_value": round(float(ks_p), 6)},
            "jarque_bera": {"statistic": round(float(jb_stat), 6), "p_value": round(float(jb_p), 6)},
            "is_normal": is_normal,
            "recommended_distribution": recommended,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _recommend_distribution(data: np.ndarray, is_normal: bool) -> str:
        if is_normal:
            return "normal"
        skew = float(sp_stats.skew(data))
        if (data > 0).all():
            if abs(skew) > 1.0:
                return "lognormal"
            return "gamma"
        if abs(skew) > 1.0:
            return "skew-normal"
        kurt = float(sp_stats.kurtosis(data))
        if kurt > 2.0:
            return "t"
        return "normal"
