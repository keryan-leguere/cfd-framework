"""Tests for the convergence analysis module."""

from __future__ import annotations

import numpy as np
import pandas as pd

from cfd_stats.core.convergence import ConvergenceAnalyzer


class TestDetectRegime:
    def test_converged_signal(self, converged_df: pd.DataFrame) -> None:
        ca = ConvergenceAnalyzer(converged_df)
        result = ca.detect_regime("Cl")
        assert result["regime"] in ("converged", "periodic")
        assert result["quality_score"] > 0

    def test_periodic_signal(self, periodic_df: pd.DataFrame) -> None:
        ca = ConvergenceAnalyzer(periodic_df)
        result = ca.detect_regime("Cl")
        assert result["regime"] in ("periodic", "converged")

    def test_diverging_signal(self, diverging_df: pd.DataFrame) -> None:
        ca = ConvergenceAnalyzer(diverging_df)
        result = ca.detect_regime("Cl")
        assert result["regime"] in ("diverging", "transient")


class TestConvergenceMetrics:
    def test_converged_cauchy(self, converged_df: pd.DataFrame) -> None:
        ca = ConvergenceAnalyzer(converged_df)
        m = ca.compute_convergence_metrics("Cl")
        # Cauchy = 1 - p_value; converged signal → p >> 0.05 → cauchy < 0.95
        assert m["cauchy_criterion"] < 0.95
        assert m["is_converged"] or m["final_variance"] < 1e-4

    def test_has_expected_keys(self, converged_df: pd.DataFrame) -> None:
        ca = ConvergenceAnalyzer(converged_df)
        m = ca.compute_convergence_metrics("Cl")
        for key in ("convergence_rate", "plateau_iterations", "final_variance", "cauchy_criterion", "is_converged"):
            assert key in m


class TestSlidingStatistics:
    def test_output_shape(self, converged_df: pd.DataFrame) -> None:
        ca = ConvergenceAnalyzer(converged_df)
        sl = ca.sliding_statistics("Cl", window_size=50)
        assert len(sl) == len(converged_df)
        assert "mean" in sl.columns
        assert "variance_ratio" in sl.columns

    def test_mean_close_to_global(self, converged_df: pd.DataFrame) -> None:
        ca = ConvergenceAnalyzer(converged_df)
        sl = ca.sliding_statistics("Cl", window_size=200)
        tail_mean = sl["mean"].iloc[-1]
        global_mean = converged_df["Cl"].mean()
        assert abs(tail_mean - global_mean) < 0.5
