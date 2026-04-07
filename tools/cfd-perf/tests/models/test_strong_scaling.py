"""Tests for the strong-scaling performance model."""

import pytest

from cfd_perf.benchmark.models import PilotPoint, PilotSeries
from cfd_perf.models.parameters import BETA_DEFAULT, BETA_MAX, BETA_MIN, ModelParameters
from cfd_perf.models.strong_scaling import (
    efficiency,
    efficiency_loss,
    fit_beta,
    fit_scaling_model,
    predict_time_per_iter,
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


# -----------------------------------------------------------------------
# Empirical model and fit_scaling_model
# -----------------------------------------------------------------------

def _make_u_shape_pilot() -> PilotSeries:
    """7-point pilot with a clear communication-dominated uptick."""
    return PilotSeries(
        points=(
            PilotPoint(cores=48,   time_per_iter_s=3.85, peak_ram_total_gb=142.0),
            PilotPoint(cores=96,   time_per_iter_s=2.18, peak_ram_total_gb=142.0),
            PilotPoint(cores=192,  time_per_iter_s=1.41, peak_ram_total_gb=143.0),
            PilotPoint(cores=384,  time_per_iter_s=1.12, peak_ram_total_gb=144.0),
            PilotPoint(cores=576,  time_per_iter_s=1.05, peak_ram_total_gb=145.0),
            PilotPoint(cores=768,  time_per_iter_s=1.10, peak_ram_total_gb=146.0),
            PilotPoint(cores=1024, time_per_iter_s=1.28, peak_ram_total_gb=148.0),
        ),
        n_iterations=12_000,
    )


class TestFitScalingModel:
    def test_auto_selects_beta_for_two_points(self) -> None:
        pilot = PilotSeries(
            points=(
                PilotPoint(cores=64, time_per_iter_s=1.0, peak_ram_total_gb=32.0),
                PilotPoint(cores=128, time_per_iter_s=0.625, peak_ram_total_gb=32.0),
            ),
            n_iterations=5000,
        )
        params = fit_scaling_model(pilot, model_hint="auto")
        assert params.model_kind == "beta"
        assert params.empirical_coeffs is None

    def test_auto_selects_empirical_for_three_plus(self) -> None:
        pilot = _make_u_shape_pilot()
        params = fit_scaling_model(pilot, model_hint="auto")
        assert params.model_kind == "empirical"
        assert params.empirical_coeffs is not None
        assert len(params.empirical_coeffs) == 3

    def test_beta_hint_forces_beta(self) -> None:
        pilot = _make_u_shape_pilot()
        params = fit_scaling_model(pilot, model_hint="beta")
        assert params.model_kind == "beta"

    def test_empirical_hint_with_too_few_points_raises(self) -> None:
        pilot = PilotSeries(
            points=(
                PilotPoint(cores=64, time_per_iter_s=1.0, peak_ram_total_gb=32.0),
                PilotPoint(cores=128, time_per_iter_s=0.625, peak_ram_total_gb=32.0),
            ),
            n_iterations=5000,
        )
        with pytest.raises(ValueError, match="empirical model requires"):
            fit_scaling_model(pilot, model_hint="empirical")

    def test_single_point_returns_fixed_beta(self) -> None:
        pilot = PilotSeries(
            points=(PilotPoint(cores=64, time_per_iter_s=1.0, peak_ram_total_gb=32.0),),
            n_iterations=5000,
        )
        params = fit_scaling_model(pilot, model_hint="auto")
        assert params.model_kind == "beta"
        assert params.beta == BETA_DEFAULT
        assert params.beta_source == "fixed"

    def test_empirical_nc_range(self) -> None:
        pilot = _make_u_shape_pilot()
        params = fit_scaling_model(pilot, model_hint="empirical")
        assert params.empirical_nc_range == (48, 1024)


class TestPredictTimePerIter:
    def test_beta_model_matches_legacy(self) -> None:
        params = ModelParameters(beta=0.25, beta_source="fixed")
        t_new = predict_time_per_iter(128, 64, 1.0, params)
        t_old = time_per_iter(128, 64, 1.0, 0.25)
        assert t_new == pytest.approx(t_old)

    def test_empirical_captures_uptick(self) -> None:
        """With U-shaped data, T should decrease then increase."""
        pilot = _make_u_shape_pilot()
        params = fit_scaling_model(pilot, model_hint="empirical")
        nc0 = pilot.baseline_cores
        t0 = pilot.baseline_time_per_iter_s

        t_low = predict_time_per_iter(192, nc0, t0, params)
        t_mid = predict_time_per_iter(576, nc0, t0, params)
        t_high = predict_time_per_iter(1024, nc0, t0, params)

        assert t_low > t_mid
        assert t_high > t_mid

    def test_empirical_minimum_exists(self) -> None:
        """The empirical curve should have a minimum in the pilot range."""
        import numpy as np

        pilot = _make_u_shape_pilot()
        params = fit_scaling_model(pilot, model_hint="empirical")
        nc0 = pilot.baseline_cores
        t0 = pilot.baseline_time_per_iter_s

        times = [predict_time_per_iter(nc, nc0, t0, params) for nc in range(48, 1025)]
        min_idx = int(np.argmin(times))
        nc_min = 48 + min_idx
        assert 200 < nc_min < 800

    def test_positive_floor(self) -> None:
        """Predicted time should never be negative."""
        pilot = _make_u_shape_pilot()
        params = fit_scaling_model(pilot, model_hint="empirical")
        nc0 = pilot.baseline_cores
        t0 = pilot.baseline_time_per_iter_s

        for nc in [1, 2, 10, 10000]:
            assert predict_time_per_iter(nc, nc0, t0, params) > 0
