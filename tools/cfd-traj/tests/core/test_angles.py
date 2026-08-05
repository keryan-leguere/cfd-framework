"""Wind angles to aeroballistic angles."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_traj.core.angles import (
    ALPHA_MAX_DEG,
    AngleError,
    aerodynamic_roll,
    from_aeroballistic,
    is_roll_defined,
    to_aeroballistic,
    total_incidence,
    velocity_direction,
)


class TestRoundTrip:
    def test_wind_angles_survive_a_round_trip(self):
        rng = np.random.default_rng(20260804)
        alpha = rng.uniform(-60.0, 60.0, 10_000)
        beta = rng.uniform(-60.0, 60.0, 10_000)

        alpha_tot, phi, _ = to_aeroballistic(alpha, beta)
        back_alpha, back_beta = from_aeroballistic(alpha_tot, phi)

        assert np.allclose(back_alpha, alpha, atol=1e-10)
        assert np.allclose(back_beta, beta, atol=1e-10)

    def test_aeroballistic_angles_survive_the_reverse_round_trip(self):
        rng = np.random.default_rng(7)
        alpha_tot = rng.uniform(0.5, 60.0, 5_000)
        phi = rng.uniform(0.0, 360.0, 5_000)

        alpha, beta = from_aeroballistic(alpha_tot, phi)
        back_tot, back_phi, _ = to_aeroballistic(alpha, beta)

        assert np.allclose(back_tot, alpha_tot, atol=1e-10)
        assert np.allclose(np.mod(back_phi - phi + 180.0, 360.0) - 180.0, 0.0, atol=1e-10)


class TestIdentities:
    def test_cos_alpha_tot_is_the_product_of_the_wind_angle_cosines(self):
        rng = np.random.default_rng(3)
        alpha = rng.uniform(-70.0, 70.0, 2_000)
        beta = rng.uniform(-70.0, 70.0, 2_000)

        alpha_tot = total_incidence(alpha, beta)

        expected = np.cos(np.deg2rad(alpha)) * np.cos(np.deg2rad(beta))
        assert np.allclose(np.cos(np.deg2rad(alpha_tot)), expected, atol=1e-12)

    def test_sin_beta_is_sin_alpha_tot_times_sin_phi(self):
        rng = np.random.default_rng(4)
        alpha = rng.uniform(-70.0, 70.0, 2_000)
        beta = rng.uniform(-70.0, 70.0, 2_000)

        alpha_tot, phi, _ = to_aeroballistic(alpha, beta)

        expected = np.sin(np.deg2rad(alpha_tot)) * np.sin(np.deg2rad(phi))
        assert np.allclose(np.sin(np.deg2rad(beta)), expected, atol=1e-12)

    def test_velocity_direction_is_a_unit_vector(self):
        rng = np.random.default_rng(5)
        v = velocity_direction(rng.uniform(-70, 70, 500), rng.uniform(-70, 70, 500))

        assert v.shape == (500, 3)
        assert np.allclose(np.linalg.norm(v, axis=-1), 1.0)


class TestReferenceValues:
    @pytest.mark.parametrize(
        ("alpha", "beta", "alpha_tot", "phi"),
        [
            (5.0, 0.0, 5.0, 0.0),
            (-5.0, 0.0, 5.0, 180.0),
            (0.0, 5.0, 5.0, 90.0),
            (0.0, -5.0, 5.0, 270.0),
            # alpha_tot = arccos(cos 5deg . cos 5deg), phi = atan2(sin -5, sin -5 . cos -5)
            (-5.0, -5.0, 7.06657, 225.109),
            (5.0, 5.0, 7.06657, 45.109),
        ],
    )
    def test_tabulated_attitudes(self, alpha, beta, alpha_tot, phi):
        got_tot, got_phi, _ = to_aeroballistic(alpha, beta)

        assert float(got_tot) == pytest.approx(alpha_tot, abs=1e-3)
        assert float(got_phi) == pytest.approx(phi, abs=1e-3)

    def test_a_negative_incidence_is_a_positive_one_half_a_turn_round(self):
        # This is what the symmetry folding later cashes in: alpha < 0 is not a
        # separate case, it is phi = 180 deg.
        tot_neg, phi_neg, _ = to_aeroballistic(-7.5, 0.0)
        tot_pos, phi_pos, _ = to_aeroballistic(7.5, 0.0)

        assert float(tot_neg) == pytest.approx(float(tot_pos))
        assert float(phi_neg) == pytest.approx(180.0)
        assert float(phi_pos) == pytest.approx(0.0)


class TestDegenerateCases:
    def test_zero_zero_reports_an_undefined_roll(self):
        alpha_tot, phi, defined = to_aeroballistic(0.0, 0.0)

        assert float(alpha_tot) == 0.0
        assert float(phi) == 0.0
        assert not bool(defined)

    def test_roll_is_defined_everywhere_else(self):
        defined = is_roll_defined([0.0, 1e-3, 0.0, -2.0], [0.0, 0.0, 1e-3, 3.0])

        assert defined.tolist() == [False, True, True, True]

    def test_angles_near_zero_stay_finite(self):
        alpha_tot, phi, _ = to_aeroballistic(1e-8, 1e-8)

        assert np.isfinite(alpha_tot)
        assert np.isfinite(phi)
        assert float(alpha_tot) == pytest.approx(np.hypot(1e-8, 1e-8), rel=1e-6)

    def test_angles_near_ninety_degrees_stay_finite(self):
        alpha_tot = total_incidence(89.8, 0.0)

        assert np.isfinite(alpha_tot)
        assert float(alpha_tot) == pytest.approx(89.8, abs=1e-9)

    def test_angles_past_the_limit_are_a_data_error(self):
        with pytest.raises(AngleError, match="alpha"):
            total_incidence(ALPHA_MAX_DEG + 0.5, 0.0)

        with pytest.raises(AngleError, match="beta"):
            total_incidence(0.0, -ALPHA_MAX_DEG - 0.5)

    def test_nan_propagates_without_raising(self):
        alpha_tot, phi, _ = to_aeroballistic([1.0, np.nan], [np.nan, 2.0])

        assert np.isnan(alpha_tot).all()
        assert np.isnan(phi).all()


class TestShapes:
    @pytest.mark.parametrize("shape", [(), (7,), (3, 4)])
    def test_shapes_are_preserved(self, shape):
        rng = np.random.default_rng(11)
        alpha = rng.uniform(-10, 10, shape)
        beta = rng.uniform(-10, 10, shape)

        alpha_tot, phi, defined = to_aeroballistic(alpha, beta)

        assert alpha_tot.shape == shape
        assert phi.shape == shape
        assert defined.shape == shape

    def test_roll_is_wrapped_into_a_full_turn(self):
        rng = np.random.default_rng(12)
        phi = aerodynamic_roll(rng.uniform(-80, 80, 1000), rng.uniform(-80, 80, 1000))

        assert np.all(phi >= 0.0)
        assert np.all(phi < 360.0)
