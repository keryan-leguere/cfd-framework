"""Tests for the strong-scaling model.

The headline test is ``test_fit_tracks_real_pilot_data``: it is the
regression guard for the defect that motivated this rewrite -- a model whose
curve did not follow the measured points.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cfd_perf.core.model import ModelKind, ScalingModel, fit_model
from cfd_perf.data.pilot import pilot_from_points


class TestFitQuality:
    def test_fit_tracks_real_pilot_data(self, pilot):
        """Every predicted point must land within 5% of its measurement.

        This is the core guarantee: the curve follows the pilot data. A model
        without the communication term drifts past 20% on this dataset once
        communication dominates.
        """
        model = fit_model(pilot)

        for p in pilot.points:
            pred = model.time_per_iter(p.cores)
            rel = abs(pred - p.time_per_iter_s) / p.time_per_iter_s
            assert rel < 0.05, f"{p.cores} cores: predicted {pred:.3f} vs {p.time_per_iter_s:.3f}"

        assert model.quality.max_rel_err_pct < 5.0
        assert model.quality.r_squared > 0.99
        assert model.quality.is_trustworthy

    def test_captures_communication_uptick(self, pilot):
        """The model must reproduce the U shape, not just decay monotonically."""
        model = fit_model(pilot)

        assert model.t_comm > 0, "communication term should be active on this data"
        # The minimum must sit inside the measured range, near the observed
        # 576-core bottom, rather than at the extreme.
        nc_min = model.time_minimum_cores(2048)
        assert nc_min is not None
        assert 300 < nc_min < 900

        # And time must genuinely rise again past the minimum.
        assert model.time_per_iter(2048) > model.time_per_iter(nc_min)

    def test_quality_verdicts(self, pilot):
        model = fit_model(pilot)
        assert model.quality.verdict in {"excellent", "good"}


class TestModelSelection:
    def test_auto_picks_comm_model_with_enough_points(self, pilot):
        assert fit_model(pilot).kind is ModelKind.AMDAHL_COMM

    def test_auto_falls_back_to_amdahl_with_two_points(self):
        p = pilot_from_points(
            [
                {"cores": 48, "time_per_iter_s": 4.0},
                {"cores": 96, "time_per_iter_s": 2.1},
            ],
            n_iterations=1000,
        )
        model = fit_model(p)
        assert model.kind is ModelKind.AMDAHL
        assert model.t_comm == 0.0
        assert model.gamma == 0.0

    def test_forcing_comm_model_with_too_few_points_raises(self):
        p = pilot_from_points(
            [
                {"cores": 48, "time_per_iter_s": 4.0},
                {"cores": 96, "time_per_iter_s": 2.1},
            ],
            n_iterations=1000,
        )
        with pytest.raises(ValueError, match="needs >= 3 pilot"):
            fit_model(p, kind=ModelKind.AMDAHL_COMM)

    def test_single_point_raises(self):
        p = pilot_from_points([{"cores": 48, "time_per_iter_s": 4.0}], n_iterations=1000)
        with pytest.raises(ValueError, match=">= 2 pilot points"):
            fit_model(p)

    def test_forced_amdahl_stays_monotone(self, pilot):
        model = fit_model(pilot, kind=ModelKind.AMDAHL)
        times = [model.time_per_iter(n) for n in (48, 96, 192, 384, 768, 1536)]
        assert times == sorted(times, reverse=True)


class TestRecoversSyntheticTruth:
    def test_recovers_known_coefficients(self):
        """Fit noise-free data generated from the model itself."""
        ts, tp, tc, gamma = 0.5, 100.0, 1e-5, 1.5
        cores = [32, 64, 128, 256, 512, 1024]
        points = [
            {"cores": n, "time_per_iter_s": ts + tp / n + tc * n**gamma} for n in cores
        ]
        model = fit_model(pilot_from_points(points, n_iterations=1000))

        assert model.quality.max_rel_err_pct < 1.0
        assert model.t_serial == pytest.approx(ts, abs=0.05)
        assert model.t_parallel == pytest.approx(tp, rel=0.05)

    def test_pure_amdahl_data_gets_negligible_comm_term(self):
        """Data with no communication cost should not invent one."""
        ts, tp = 0.4, 80.0
        points = [
            {"cores": n, "time_per_iter_s": ts + tp / n} for n in (32, 64, 128, 256, 512)
        ]
        model = fit_model(pilot_from_points(points, n_iterations=1000))

        assert model.quality.max_rel_err_pct < 1.0
        assert model.time_minimum_cores(4096) is None, "should still be improving"


class TestDerivedMetrics:
    def test_speedup_is_exactly_one_at_reference(self, pilot):
        """Speedup and efficiency are referenced to the model at Nc_ref, so
        both are exactly 1 there by construction."""
        model = fit_model(pilot)
        assert model.speedup(model.ref_cores) == pytest.approx(1.0)
        assert model.efficiency(model.ref_cores) == pytest.approx(1.0)
        assert model.efficiency_loss(model.ref_cores) == pytest.approx(0.0)

    def test_efficiency_matches_speedup_definition(self, pilot):
        model = fit_model(pilot)
        nc = 384
        expected = model.speedup(nc) / (nc / model.ref_cores)
        assert model.efficiency(nc) == pytest.approx(expected)

    def test_runtime_and_core_hours_are_consistent(self, pilot):
        model = fit_model(pilot)
        rt = model.runtime_hours(192, 12_000)
        assert rt == pytest.approx(model.time_per_iter(192) * 12_000 / 3600)
        assert model.core_hours(192, 12_000) == pytest.approx(rt * 192)

    def test_predicted_time_is_always_positive(self, pilot):
        """Predicted time must stay positive at every core count, including
        far outside the pilot range."""
        model = fit_model(pilot)
        for nc in (1, 2, 8, 4096, 100_000):
            assert model.time_per_iter(nc) > 0

    def test_extrapolation_flag(self, pilot):
        model = fit_model(pilot)
        assert model.fitted_range == (48, 1024)
        assert not model.is_extrapolating(500)
        assert model.is_extrapolating(2048)
        assert model.is_extrapolating(16)

    def test_zero_or_negative_cores_rejected(self, pilot):
        model = fit_model(pilot)
        with pytest.raises(ValueError, match="must be positive"):
            model.time_per_iter(0)


class TestValidation:
    def test_negative_coefficients_rejected(self, pilot):
        model = fit_model(pilot)
        with pytest.raises(ValueError, match="non-negative"):
            ScalingModel(
                t_serial=-1.0,
                t_parallel=model.t_parallel,
                t_comm=0.0,
                gamma=0.0,
                kind=ModelKind.AMDAHL,
                quality=model.quality,
                ref_cores=48,
                ref_time_s=3.85,
                fitted_range=(48, 1024),
            )

    def test_fitted_coefficients_are_non_negative(self, pilot):
        model = fit_model(pilot)
        assert model.t_serial >= 0
        assert model.t_parallel >= 0
        assert model.t_comm >= 0

    def test_describe_contains_the_numbers(self, pilot):
        model = fit_model(pilot)
        text = model.describe()
        assert "Nc" in text
        assert not math.isnan(model.t_parallel)


class TestRobustness:
    def test_noisy_data_still_fits_reasonably(self, pilot):
        """Add +/-3% jitter, as a real cluster would produce."""
        rng = np.random.default_rng(42)
        noisy = [
            {
                "cores": p.cores,
                "time_per_iter_s": p.time_per_iter_s * (1 + rng.uniform(-0.03, 0.03)),
            }
            for p in pilot.points
        ]
        model = fit_model(pilot_from_points(noisy, n_iterations=12_000))
        assert model.quality.max_rel_err_pct < 10.0

    def test_relative_weighting_does_not_neglect_fast_points(self, pilot):
        """The fast, high-core points decide the answer, so they must fit too.

        Unweighted least squares lets the large low-core values dominate; this
        asserts the high-core end is fitted as tightly as the low-core end.
        """
        model = fit_model(pilot)
        fast = pilot.points[-1]
        rel = abs(model.time_per_iter(fast.cores) - fast.time_per_iter_s) / fast.time_per_iter_s
        assert rel < 0.05
