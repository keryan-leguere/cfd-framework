"""Derived thermodynamic quantities."""

from __future__ import annotations

import pytest

from cfd_atm.core import constants as C
from cfd_atm.core import thermo


class TestSpeedOfSound:
    def test_sea_level(self) -> None:
        assert float(thermo.speed_of_sound(C.T0)) == pytest.approx(C.A0, abs=1e-6)

    def test_monotonic_in_temperature(self) -> None:
        assert float(thermo.speed_of_sound(300.0)) > float(thermo.speed_of_sound(250.0))


class TestViscosity:
    def test_sutherland_at_sea_level(self) -> None:
        # ISA sea-level dynamic viscosity ≈ 1.789e-5 Pa·s.
        assert float(thermo.viscosity_sutherland(C.T0)) == pytest.approx(1.789e-5, rel=2e-2)

    def test_kinematic_is_dynamic_over_density(self) -> None:
        nu = float(thermo.kinematic_viscosity(C.T0, C.RHO0))
        expected = float(thermo.viscosity_sutherland(C.T0)) / C.RHO0
        assert nu == pytest.approx(expected)


class TestRatios:
    def test_unity_at_sea_level(self) -> None:
        assert float(thermo.theta(C.T0)) == pytest.approx(1.0)
        assert float(thermo.delta(C.P0)) == pytest.approx(1.0)
        assert float(thermo.sigma(C.RHO0)) == pytest.approx(1.0)

    def test_sigma_equals_delta_over_theta(self) -> None:
        t, p = 250.0, 40000.0
        rho = p / (C.R_AIR * t)
        assert float(thermo.sigma(rho)) == pytest.approx(
            float(thermo.delta(p)) / float(thermo.theta(t)), rel=1e-9
        )
