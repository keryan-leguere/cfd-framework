"""Non-dimensionalisation against the cfd-atm atmosphere."""

from __future__ import annotations

import numpy as np
import pytest
from cfd_atm.core.constants import GAMMA

from cfd_traj.core.adim import (
    Reference,
    flow_state,
    isa_density,
    isa_speed_of_sound,
    nondimensionalise,
)

REF = Reference(length_m=2.5)


class TestAtmosphereAgreement:
    def test_sea_level_matches_the_standard_atmosphere(self):
        state = flow_state(0.0, 0.0, reference=REF)

        assert state.p_inf == pytest.approx(101_325.0, abs=1e-3)
        assert state.t_inf == pytest.approx(288.15, abs=1e-6)
        assert state.rho_inf == pytest.approx(1.225, abs=1e-4)
        assert state.a_inf == pytest.approx(340.294, abs=1e-2)

    def test_the_tropopause_matches_the_published_value(self):
        state = flow_state(0.5, 11_019.0, reference=REF)

        assert state.p_inf == pytest.approx(22_632.0, abs=5.0)
        assert state.t_inf == pytest.approx(216.65, abs=0.05)

    def test_a_positive_isa_offset_warms_and_thins_the_air(self):
        cold = flow_state(0.8, 8_000.0, reference=REF, delta_t_k=0.0)
        warm = flow_state(0.8, 8_000.0, reference=REF, delta_t_k=20.0)

        assert warm.t_inf == pytest.approx(cold.t_inf + 20.0, abs=1e-6)
        assert warm.rho_inf < cold.rho_inf


class TestIdentities:
    def test_dynamic_pressure_agrees_with_half_rho_v_squared(self):
        out = nondimensionalise([0.2, 0.9, 2.5], [0.0, 6_000.0, 18_000.0], reference=REF)

        assert np.allclose(out["q_inf"], 0.5 * out["rho_inf"] * out["V_inf"] ** 2, rtol=1e-12)

    def test_dynamic_pressure_agrees_with_the_compressible_form(self):
        mach = np.array([0.2, 0.9, 2.5])
        out = nondimensionalise(mach, [0.0, 6_000.0, 18_000.0], reference=REF)

        assert np.allclose(out["q_inf"], 0.5 * GAMMA * out["p_inf"] * mach**2, rtol=1e-12)

    def test_the_reference_reynolds_is_the_unit_reynolds_times_the_length(self):
        out = nondimensionalise([1.2], [9_000.0], reference=REF)

        assert out["Re_ref"] == pytest.approx(out["Re_m"] * REF.length_m, rel=1e-15)

    def test_the_velocity_is_the_mach_number_times_the_speed_of_sound(self):
        out = nondimensionalise([1.7], [3_000.0], reference=REF)

        assert out["V_inf"] == pytest.approx(1.7 * out["a_inf"], rel=1e-15)


class TestMonotonicity:
    def test_unit_reynolds_falls_with_altitude(self):
        out = nondimensionalise(1.0, np.linspace(0.0, 30_000.0, 40), reference=REF)

        assert np.all(np.diff(out["Re_m"]) < 0.0)

    def test_unit_reynolds_grows_with_mach(self):
        out = nondimensionalise(np.linspace(0.2, 3.0, 30), 10_000.0, reference=REF)

        assert np.all(np.diff(out["Re_m"]) > 0.0)


class TestVectorisation:
    def test_the_vectorised_call_matches_the_scalar_one(self):
        mach = np.array([0.3, 1.1, 2.4])
        alt = np.array([500.0, 9_000.0, 21_000.0])

        out = nondimensionalise(mach, alt, reference=REF)

        for i, (m, z) in enumerate(zip(mach, alt, strict=True)):
            one = flow_state(float(m), float(z), reference=REF)
            assert out["q_inf"][i] == pytest.approx(one.q_inf, rel=1e-12)
            assert out["Re_ref"][i] == pytest.approx(one.re_ref, rel=1e-12)

    def test_scalars_broadcast_against_arrays(self):
        out = nondimensionalise(0.8, np.zeros(5), reference=REF)

        assert out["q_inf"].shape == (5,)


class TestEdgeCases:
    def test_a_still_vehicle_has_no_dynamic_pressure_and_no_reynolds(self):
        state = flow_state(0.0, 1_000.0, reference=REF)

        assert state.v_inf == 0.0
        assert state.q_inf == 0.0
        assert state.re_per_metre == 0.0

    def test_a_slightly_negative_altitude_is_accepted(self):
        state = flow_state(0.3, -200.0, reference=REF)

        assert state.p_inf > 101_325.0

    def test_an_altitude_above_the_model_ceiling_is_refused(self):
        with pytest.raises(ValueError, match="ceiling"):
            nondimensionalise(1.0, 120_000.0, reference=REF)

    def test_nan_altitudes_do_not_trip_the_range_check(self):
        out = nondimensionalise([1.0, 1.0], [5_000.0, np.nan], reference=REF)

        assert np.isfinite(out["q_inf"][0])
        assert np.isnan(out["q_inf"][1])

    @pytest.mark.parametrize("length", [0.0, -1.0, float("nan")])
    def test_a_non_positive_reference_length_is_refused(self, length):
        with pytest.raises(ValueError, match="reference length"):
            Reference(length_m=length)

    def test_a_non_positive_reference_area_is_refused(self):
        with pytest.raises(ValueError, match="reference area"):
            Reference(length_m=1.0, area_m2=0.0)


class TestFlightModelHelpers:
    def test_density_falls_with_altitude(self):
        rho = isa_density(np.linspace(0.0, 30_000.0, 20))

        assert np.all(np.diff(rho) < 0.0)
        assert float(rho[0]) == pytest.approx(1.225, abs=1e-4)

    def test_the_speed_of_sound_is_constant_through_the_lower_stratosphere(self):
        a = isa_speed_of_sound([12_000.0, 15_000.0, 19_000.0])

        assert np.allclose(a, a[0], rtol=1e-6)
