"""Altitude conversions and their consistency."""

from __future__ import annotations

import pytest

from cfd_atm.core import altitudes, isa


class TestGeopotentialGeometric:
    @pytest.mark.parametrize("z", [0.0, 1000.0, 11000.0, 30000.0])
    def test_round_trip(self, z: float) -> None:
        h = float(altitudes.geopotential_from_geometric(z))
        assert float(altitudes.geometric_from_geopotential(h)) == pytest.approx(z, abs=1e-6)

    def test_geopotential_below_geometric(self) -> None:
        # H is slightly smaller than z (gravity weakens with altitude).
        z = 11000.0
        assert float(altitudes.geopotential_from_geometric(z)) < z

    def test_zero_at_sea_level(self) -> None:
        assert float(altitudes.geopotential_from_geometric(0.0)) == pytest.approx(0.0)


class TestPressureDensityAltitude:
    def test_pressure_altitude_matches_isa(self) -> None:
        p = float(isa.isa_pressure(9000.0))
        assert float(altitudes.pressure_altitude(p)) == pytest.approx(9000.0, abs=1e-3)

    def test_density_altitude_matches_isa(self) -> None:
        rho = float(isa.isa_density(9000.0))
        assert float(altitudes.density_altitude(rho)) == pytest.approx(9000.0, abs=1e-2)
