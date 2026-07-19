"""ISA laws against published reference values, plus inversion round-trips."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_atm.core import constants as C
from cfd_atm.core import isa


class TestReferenceValues:
    def test_sea_level_derived_constants(self) -> None:
        assert C.RHO0 == pytest.approx(1.2250, abs=1e-4)
        assert C.A0 == pytest.approx(340.294, abs=1e-2)

    def test_isa_table(self, isa_reference: list[tuple[float, float, float, float]]) -> None:
        for h, t_ref, p_ref, rho_ref in isa_reference:
            assert float(isa.isa_temperature(h)) == pytest.approx(t_ref, rel=1e-4)
            assert float(isa.isa_pressure(h)) == pytest.approx(p_ref, rel=1e-3)
            assert float(isa.isa_density(h)) == pytest.approx(rho_ref, rel=1e-3)

    def test_tropopause_is_isothermal(self) -> None:
        assert float(isa.isa_temperature(11000)) == pytest.approx(216.65)
        assert float(isa.isa_temperature(15000)) == pytest.approx(216.65)
        assert float(isa.isa_temperature(20000)) == pytest.approx(216.65)


class TestVectorised:
    def test_array_input_preserves_shape(self) -> None:
        h = np.array([0.0, 5000.0, 11000.0, 25000.0])
        assert isa.isa_pressure(h).shape == h.shape
        assert np.all(np.diff(isa.isa_pressure(h)) < 0)  # pressure decreases


class TestInversions:
    @pytest.mark.parametrize("h", [0.0, 3000.0, 11000.0, 18000.0, 30000.0, 45000.0])
    def test_pressure_altitude_round_trip(self, h: float) -> None:
        p = float(isa.isa_pressure(h))
        assert float(isa.geopotential_from_pressure(p)) == pytest.approx(h, abs=1e-3)

    @pytest.mark.parametrize("h", [0.0, 3000.0, 11000.0, 18000.0, 30000.0, 45000.0])
    def test_density_altitude_round_trip(self, h: float) -> None:
        rho = float(isa.isa_density(h))
        assert float(isa.geopotential_from_density(rho)) == pytest.approx(h, abs=1e-2)
