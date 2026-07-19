"""Airspeed conversions: round-trips, sea-level identities, sub/supersonic."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_atm.core import airspeed
from cfd_atm.core import constants as C
from cfd_atm.core.atmosphere import AtmosphereModel


@pytest.fixture
def state_35kft():
    return AtmosphereModel.isa().state_from_pressure_altitude(10668.0)  # 35000 ft


class TestSeaLevelIdentities:
    def test_cas_eas_tas_equal_at_sea_level(self) -> None:
        # At standard sea level Vc = EAS = TAS for the same Mach.
        s = airspeed.airspeeds(C.P0, C.T0, mach=0.5)
        assert s.cas == pytest.approx(s.tas, rel=1e-6)
        assert s.eas == pytest.approx(s.tas, rel=1e-6)

    def test_sea_level_mach_equals_speed_over_a0(self) -> None:
        tas = 150.0
        s = airspeed.airspeeds(C.P0, C.T0, tas=tas)
        assert s.mach == pytest.approx(tas / C.A0, rel=1e-9)


class TestRoundTrips:
    @pytest.mark.parametrize("cas_kt", [100.0, 250.0, 350.0])
    def test_cas_mach_round_trip(self, state_35kft, cas_kt: float) -> None:
        cas = cas_kt * 0.514444
        mach = float(airspeed.mach_from_cas(cas, state_35kft.p))
        assert float(airspeed.cas_from_mach(mach, state_35kft.p)) == pytest.approx(cas, rel=1e-6)

    def test_tas_and_eas_round_trip(self, state_35kft) -> None:
        m = 0.8
        tas = float(airspeed.tas_from_mach(m, state_35kft.t))
        assert float(airspeed.mach_from_tas(tas, state_35kft.t)) == pytest.approx(m, rel=1e-9)
        eas = float(airspeed.eas_from_mach(m, state_35kft.p))
        assert float(airspeed.mach_from_eas(eas, state_35kft.p)) == pytest.approx(m, rel=1e-9)


class TestOrdering:
    def test_tas_exceeds_cas_at_altitude(self, state_35kft) -> None:
        s = airspeed.airspeeds(state_35kft.p, state_35kft.t, cas=250.0 * 0.514444)
        assert s.tas > s.cas > 0
        assert s.tas > s.eas


class TestSupersonic:
    @pytest.mark.parametrize("mach", [1.2, 2.0, 3.0])
    def test_supersonic_round_trip(self, state_35kft, mach: float) -> None:
        cas = float(airspeed.cas_from_mach(mach, state_35kft.p))
        assert float(airspeed.mach_from_cas(cas, state_35kft.p)) == pytest.approx(mach, rel=1e-5)

    def test_regime_continuity_at_mach_one(self) -> None:
        # The subsonic and Rayleigh branches must give the same qc/p at M = 1.
        sub = (1.0 + 0.2) ** 3.5 - 1.0
        sup = airspeed._qc_ratio_supersonic(1.0)
        assert sup == pytest.approx(sub, rel=1e-9)

    def test_temperature_independence_of_mach_cas(self) -> None:
        # Vc <-> Mach depends only on pressure, not temperature.
        p = 23842.0
        cas = 200.0 * 0.514444
        m_cold = float(airspeed.mach_from_cas(cas, p))
        # same p, different T must give the same Mach (T never enters the relation)
        assert float(airspeed.mach_from_cas(cas, p)) == pytest.approx(m_cold)


class TestVectorised:
    def test_array_pressure(self) -> None:
        p = np.array([101325.0, 50000.0, 23842.0])
        mach = airspeed.mach_from_cas(120.0, p)
        assert mach.shape == p.shape
        assert np.all(np.diff(mach) > 0)  # lower pressure -> higher Mach for fixed Vc


class TestValidation:
    def test_requires_exactly_one_speed(self) -> None:
        with pytest.raises(ValueError, match="exactement une"):
            airspeed.airspeeds(C.P0, C.T0)
        with pytest.raises(ValueError, match="exactement une"):
            airspeed.airspeeds(C.P0, C.T0, mach=0.5, cas=100.0)
