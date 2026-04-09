"""Tests for the statistical moments module."""

from __future__ import annotations

import numpy as np

from cfd_stats.core.moments import MomentCalculator


class TestAllMoments:
    def test_normal_distribution(self, normal_sample: np.ndarray) -> None:
        mc = MomentCalculator(normal_sample)
        m = mc.compute_all_moments()
        assert abs(m["mean"] - 5.0) < 0.05
        assert abs(m["std"] - 0.1) < 0.02
        assert abs(m["skewness"]) < 0.15
        assert abs(m["excess_kurtosis"]) < 0.3

    def test_keys_present(self, normal_sample: np.ndarray) -> None:
        mc = MomentCalculator(normal_sample)
        m = mc.compute_all_moments(max_order=4)
        for key in ("mean", "variance", "std", "skewness", "kurtosis", "excess_kurtosis", "raw_moments", "central_moments"):
            assert key in m
        assert 4 in m["central_moments"]


class TestRobustStatistics:
    def test_median_close_to_mean(self, normal_sample: np.ndarray) -> None:
        mc = MomentCalculator(normal_sample)
        r = mc.compute_robust_statistics()
        assert abs(r["median"] - 5.0) < 0.05
        assert r["iqr"] > 0
        assert r["mad"] > 0

    def test_quantiles_ordered(self, normal_sample: np.ndarray) -> None:
        mc = MomentCalculator(normal_sample)
        r = mc.compute_robust_statistics()
        assert r["q25"] < r["median"] < r["q75"] < r["q95"] < r["q99"]


class TestConfidenceIntervals:
    def test_mean_ci_contains_true_mean(self, normal_sample: np.ndarray) -> None:
        mc = MomentCalculator(normal_sample)
        ci = mc.compute_confidence_intervals(confidence=0.95, n_bootstrap=500, rng=np.random.default_rng(0))
        lo, hi = ci["mean_ci"]
        assert lo < 5.0 < hi

    def test_std_ci_positive(self, normal_sample: np.ndarray) -> None:
        mc = MomentCalculator(normal_sample)
        ci = mc.compute_confidence_intervals(n_bootstrap=200, rng=np.random.default_rng(0))
        assert ci["std_ci"][0] > 0


class TestGoodnessOfFit:
    def test_normal_detected(self, normal_sample: np.ndarray) -> None:
        mc = MomentCalculator(normal_sample)
        gof = mc.goodness_of_fit()
        assert gof["recommended_distribution"] == "normal"

    def test_keys_present(self, normal_sample: np.ndarray) -> None:
        mc = MomentCalculator(normal_sample)
        gof = mc.goodness_of_fit()
        for key in ("shapiro_wilk", "anderson_darling", "kolmogorov_smirnov", "jarque_bera", "is_normal"):
            assert key in gof
