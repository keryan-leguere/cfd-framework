"""The AtmosphereModel block: ISA, offset and custom behaviour."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_atm.core import isa
from cfd_atm.core.atmosphere import (
    AtmosphereModel,
    ModelKind,
    temperature_profile_from_table,
)


class TestIsaModel:
    def test_matches_isa_laws(self) -> None:
        model = AtmosphereModel.isa()
        st = model.state_from_geopotential(9000.0)
        assert st.t == pytest.approx(float(isa.isa_temperature(9000.0)))
        assert st.p == pytest.approx(float(isa.isa_pressure(9000.0)))
        assert st.rho == pytest.approx(float(isa.isa_density(9000.0)))

    def test_all_altitudes_equal_under_isa(self) -> None:
        # Under ISA the geopotential, pressure and density altitudes coincide.
        st = AtmosphereModel.isa().state_from_geopotential(9000.0)
        assert st.zp == pytest.approx(9000.0, abs=1e-3)
        assert st.zrho == pytest.approx(9000.0, abs=1e-2)

    def test_derived_quantities_present(self) -> None:
        st = AtmosphereModel.isa().state_from_pressure_altitude(10000.0)
        assert st.a > 0 and st.mu > 0 and st.nu > 0
        assert st.theta > 0 and st.delta > 0 and st.sigma > 0


class TestOffsetModel:
    def test_offset_shifts_temperature_at_pressure_altitude(self) -> None:
        zp = 8000.0
        isa_state = AtmosphereModel.isa().state_from_pressure_altitude(zp)
        hot = AtmosphereModel.isa_offset(15.0).state_from_pressure_altitude(zp)
        # Same pressure (pressure altitude fixes it), warmer, hence less dense.
        assert hot.p == pytest.approx(isa_state.p, rel=1e-3)
        assert hot.t > isa_state.t
        assert hot.rho < isa_state.rho

    def test_offset_temperature_referenced_to_pressure_altitude(self) -> None:
        # Aeronautical convention (confirmed against the ISA-deviation definition
        # ΔT = OAT − T_ISA(zp)): at a pressure altitude the offset is referenced to
        # zp, so T = T_ISA(zp) + ΔT exactly — NOT T_ISA(H*) + ΔT with H* the warm
        # hydrostatic height. The two differ by several K at high ΔT / high zp.
        zp = 9144.0  # ~ FL300
        dt = 35.0
        hot = AtmosphereModel.isa_offset(dt).state_from_pressure_altitude(zp)
        assert hot.t == pytest.approx(float(isa.isa_temperature(zp)) + dt)
        # The reported geopotential height is the warm pressure surface: H* > zp.
        assert hot.h > zp

    def test_offset_label(self) -> None:
        assert AtmosphereModel.isa_offset(35.0).label == "ISA+35"
        assert AtmosphereModel.isa_offset(-35.0).label == "ISA−35"

    def test_hotter_gives_higher_pressure_at_geometric_altitude(self) -> None:
        # The physics behind diagram A: at a fixed geometric altitude the warm
        # atmosphere has the higher pressure (hydrostatic integration).
        z = 10000.0
        p_isa = float(AtmosphereModel.isa().pressure_at_geometric(z))
        p_hot = float(AtmosphereModel.isa_offset(30.0).pressure_at_geometric(z))
        p_cold = float(AtmosphereModel.isa_offset(-30.0).pressure_at_geometric(z))
        assert p_cold < p_isa < p_hot


class TestCustomModel:
    def test_custom_temperature_from_table(self) -> None:
        profile = temperature_profile_from_table([0.0, 10000.0], [300.0, 200.0])
        model = AtmosphereModel.custom(profile, label="lin")
        assert model.kind is ModelKind.CUSTOM
        assert float(model.temperature(5000.0)) == pytest.approx(250.0)

    def test_custom_pressure_monotonic_decreasing(self) -> None:
        profile = temperature_profile_from_table([0.0, 20000.0], [295.0, 215.0])
        model = AtmosphereModel.custom(profile)
        h = np.linspace(0.0, 18000.0, 50)
        p = model.pressure_geopotential(h)
        assert np.all(np.diff(p) < 0)
        assert float(p[0]) == pytest.approx(101325.0, rel=1e-3)

    def test_custom_pressure_altitude_inverts_own_law(self) -> None:
        # A custom profile is a physical field vs geopotential altitude: entering
        # by the zp produced at a geopotential H must recover that same H and T
        # (invert p_model(H)=p -> H*, then T = T(H*)). Round-trip must be exact.
        profile = temperature_profile_from_table(
            [0.0, 3000.0, 11000.0, 20000.0], [295.0, 283.0, 210.0, 210.0]
        )
        model = AtmosphereModel.custom(profile)
        h_in = 9000.0
        direct = model.state_from_geopotential(h_in)
        back = model.state_from_pressure_altitude(direct.zp)
        assert back.h == pytest.approx(h_in, abs=1e-2)
        assert back.t == pytest.approx(direct.t, abs=1e-4)
        assert back.p == pytest.approx(direct.p, rel=1e-6)

    def test_table_validation(self) -> None:
        with pytest.raises(ValueError, match="croissant"):
            temperature_profile_from_table([0.0, 0.0], [300.0, 200.0])
        with pytest.raises(ValueError, match="même taille"):
            temperature_profile_from_table([0.0, 1000.0], [300.0])


class TestEntryPointConsistency:
    def test_geometric_and_geopotential_agree(self) -> None:
        model = AtmosphereModel.isa()
        from cfd_atm.core.altitudes import geopotential_from_geometric

        z = 12000.0
        h = float(geopotential_from_geometric(z))
        a = model.state_from_geometric(z)
        b = model.state_from_geopotential(h)
        assert a.p == pytest.approx(b.p)
        assert a.t == pytest.approx(b.t)
