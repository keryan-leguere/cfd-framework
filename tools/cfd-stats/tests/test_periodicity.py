"""Tests for the periodicity detection module."""

from __future__ import annotations

import numpy as np

from cfd_stats.core.periodicity import PeriodicityDetector


class TestFFTDetection:
    def test_pure_sine(self) -> None:
        n = 4000
        t = np.arange(n, dtype=float)
        period = 100.0
        signal = np.sin(2 * np.pi * t / period)

        det = PeriodicityDetector(signal, t)
        result = det.detect_period_fft()

        assert result["is_periodic"]
        assert abs(result["period"] - period) < period * 0.05
        assert result["confidence"] > 0.3

    def test_no_periodicity(self, rng: np.random.Generator) -> None:
        n = 2000
        t = np.arange(n, dtype=float)
        signal = rng.normal(0, 1, n)

        det = PeriodicityDetector(signal, t)
        result = det.detect_period_fft()
        assert result["confidence"] < 0.3


class TestAutocorrDetection:
    def test_noisy_periodic(self, rng: np.random.Generator) -> None:
        n = 5000
        t = np.arange(n, dtype=float)
        period = 200.0
        signal = np.sin(2 * np.pi * t / period) + rng.normal(0, 0.3, n)

        det = PeriodicityDetector(signal, t)
        result = det.detect_period_autocorr()

        assert result["confidence"] > 0.2
        assert abs(result["period"] - period) < period * 0.15


class TestValidation:
    def test_sufficient_periods(self) -> None:
        n = 10000
        t = np.arange(n, dtype=float)
        period = 100.0
        signal = np.sin(2 * np.pi * t / period)

        det = PeriodicityDetector(signal, t)
        val = det.validate_periodicity(n_periods_required=10)
        assert val["is_sufficient"]
        assert val["n_periods_available"] > 10
        assert val["quality_flag"] in ("excellent", "good")

    def test_insufficient_periods(self) -> None:
        n = 500
        t = np.arange(n, dtype=float)
        period = 200.0
        signal = np.sin(2 * np.pi * t / period)

        det = PeriodicityDetector(signal, t)
        val = det.validate_periodicity(n_periods_required=10)
        assert not val["is_sufficient"]


class TestPhaseLocked:
    def test_cycle_extraction(self) -> None:
        n = 4000
        t = np.arange(n, dtype=float)
        period = 200.0
        signal = np.sin(2 * np.pi * t / period)

        det = PeriodicityDetector(signal, t)
        cycles = det.extract_phase_locked_cycles(period=period)
        assert cycles.ndim == 2
        assert cycles.shape[0] == n // int(period)
        assert cycles.shape[1] == int(period)
