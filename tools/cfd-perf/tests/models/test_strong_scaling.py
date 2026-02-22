"""Tests for the strong-scaling performance model."""

import pytest

from cfd_perf.benchmark.models import PilotPoint, PilotSeries
from cfd_perf.models.parameters import BETA_DEFAULT, BETA_MAX, BETA_MIN
from cfd_perf.models.strong_scaling import (
    efficiency,
    efficiency_loss,
    fit_beta,
    speedup,
    time_per_iter,
    total_runtime_hours,
)


class TestTimePerIter:
    def test_at_baseline(self) -> None:
        """T(Nc0) should equal T0 regardless of beta."""
        assert time_per_iter(64, 64, 1.2, 0.25) == pytest.approx(1.2)

    def test_double_cores(self) -> None:
        """T(128) with Nc0=64, T0=1.0, beta=0.25."""
        # r = 64/128 = 0.5 => T = 1.0 * (0.5 + 0.25 * 0.5) = 0.625
        assert time_per_iter(128, 64, 1.0, 0.25) == pytest.approx(0.625)

    def test_zero_beta_gives_ideal(self) -> None:
        """Beta=0 means ideal scaling: T(Nc) = T0 * Nc0/Nc."""
        # Edge: beta=0 is below BETA_MIN for ModelParameters but the formula accepts it
        assert time_per_iter(256, 64, 1.0, 0.0) == pytest.approx(64 / 256)


class TestSpeedup:
    def test_at_baseline(self) -> None:
        assert speedup(64, 64, 1.0, 0.25) == pytest.approx(1.0)

    def test_double_cores(self) -> None:
        s = speedup(128, 64, 1.0, 0.25)
        expected = 1.0 / 0.625
        assert s == pytest.approx(expected)


class TestEfficiency:
    def test_at_baseline_is_one(self) -> None:
        assert efficiency(64, 64, 1.0, 0.25) == pytest.approx(1.0)

    def test_decreases_with_cores(self) -> None:
        e1 = efficiency(128, 64, 1.0, 0.25)
        e2 = efficiency(256, 64, 1.0, 0.25)
        assert e1 > e2

    def test_double_cores_value(self) -> None:
        # E(128) = S(128) / (128/64) = (1/0.625) / 2 = 0.8
        assert efficiency(128, 64, 1.0, 0.25) == pytest.approx(0.8)


class TestEfficiencyLoss:
    def test_at_baseline_is_zero(self) -> None:
        assert efficiency_loss(64, 64, 1.0, 0.25) == pytest.approx(0.0)

    def test_double_cores(self) -> None:
        assert efficiency_loss(128, 64, 1.0, 0.25) == pytest.approx(0.2)


class TestTotalRuntimeHours:
    def test_basic(self) -> None:
        # 0.625 s/iter * 5000 iter = 3125 s = 0.868055... h
        rt = total_runtime_hours(128, 64, 1.0, 0.25, 5000)
        assert rt == pytest.approx(3125 / 3600, rel=1e-9)


class TestFitBeta:
    def test_single_point_returns_default(self) -> None:
        pilot = PilotSeries(
            points=(PilotPoint(cores=64, time_per_iter_s=1.0, peak_ram_total_gb=32.0),),
            n_iterations=5000,
        )
        params = fit_beta(pilot)
        assert params.beta == BETA_DEFAULT
        assert params.beta_source == "fixed"

    def test_two_points_fits(self) -> None:
        pilot = PilotSeries(
            points=(
                PilotPoint(cores=64, time_per_iter_s=1.0, peak_ram_total_gb=32.0),
                PilotPoint(cores=128, time_per_iter_s=0.625, peak_ram_total_gb=32.0),
            ),
            n_iterations=5000,
        )
        params = fit_beta(pilot)
        assert params.beta_source == "fitted"
        assert params.beta == pytest.approx(0.25, abs=1e-4)

    def test_fitted_clamped_high(self) -> None:
        """If measured T is very slow (huge overhead), beta clamps to BETA_MAX."""
        pilot = PilotSeries(
            points=(
                PilotPoint(cores=64, time_per_iter_s=1.0, peak_ram_total_gb=32.0),
                PilotPoint(cores=128, time_per_iter_s=0.95, peak_ram_total_gb=32.0),
            ),
            n_iterations=5000,
        )
        params = fit_beta(pilot)
        assert params.beta == BETA_MAX

    def test_fitted_clamped_low(self) -> None:
        """If measured T is near-ideal, beta clamps to BETA_MIN."""
        pilot = PilotSeries(
            points=(
                PilotPoint(cores=64, time_per_iter_s=1.0, peak_ram_total_gb=32.0),
                PilotPoint(cores=128, time_per_iter_s=0.505, peak_ram_total_gb=32.0),
            ),
            n_iterations=5000,
        )
        params = fit_beta(pilot)
        assert params.beta == BETA_MIN
