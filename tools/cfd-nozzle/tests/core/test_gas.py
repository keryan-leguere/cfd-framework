"""Gas model: derived properties, library, construction guards."""

from __future__ import annotations

import math

import pytest

from cfd_nozzle.core.gas import GAS_LIBRARY, R_UNIVERSAL, GasModel, gas_from_name


def test_air_reference_properties(air: GasModel) -> None:
    assert air.gamma == pytest.approx(1.4)
    assert air.cp == pytest.approx(1004.675, rel=1e-5)
    assert air.cv == pytest.approx(717.625, rel=1e-5)
    assert air.cp - air.cv == pytest.approx(air.r, rel=1e-12)
    assert air.cp / air.cv == pytest.approx(air.gamma, rel=1e-12)


def test_speed_of_sound_at_sea_level(air: GasModel) -> None:
    assert air.sound_speed(288.15) == pytest.approx(340.294, rel=1e-5)
    assert air.velocity(2.0, 288.15) == pytest.approx(2.0 * 340.294, rel=1e-5)


def test_density_follows_the_perfect_gas_law(air: GasModel) -> None:
    assert air.density(101325.0, 288.15) == pytest.approx(1.225, rel=1e-3)


@pytest.mark.parametrize("gamma", [1.2, 1.3, 1.4, 1.667])
def test_vandenkerckhove_function(gamma: float) -> None:
    gas = GasModel(gamma, 300.0, "test")
    expected = math.sqrt(gamma) * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))
    assert gas.vandenkerckhove == pytest.approx(expected, rel=1e-12)
    assert 0.6 < gas.vandenkerckhove < 0.8


def test_limit_velocity_bounds_any_expansion(air: GasModel) -> None:
    t0 = 3000.0
    limit = air.limit_velocity(t0)
    assert limit == pytest.approx(math.sqrt(2.0 * air.cp * t0))
    # A very large but finite Mach number stays under it.
    static = t0 / (1.0 + 0.5 * (air.gamma - 1.0) * 50.0**2)
    assert air.velocity(50.0, static) < limit


def test_from_molar_mass() -> None:
    gas = GasModel.from_molar_mass(1.4, 28.9647, "air")
    assert gas.r == pytest.approx(R_UNIVERSAL / 28.9647)
    assert gas.r == pytest.approx(287.05, rel=2e-3)


def test_library_entries_are_physical() -> None:
    assert len(GAS_LIBRARY) >= 8
    for name, gas in GAS_LIBRARY.items():
        assert gas.gamma > 1.0, name
        assert gas.r > 0.0, name
        assert gas.cp > gas.cv > 0.0, name


def test_gas_lookup_lists_alternatives_when_unknown() -> None:
    assert gas_from_name("air") is GAS_LIBRARY["air"]
    with pytest.raises(KeyError, match="lox_rp1"):
        gas_from_name("kerozene")


def test_rejects_unphysical_construction() -> None:
    with pytest.raises(ValueError, match="γ"):
        GasModel(1.0, 287.0)
    with pytest.raises(ValueError, match="R"):
        GasModel(1.4, 0.0)
    with pytest.raises(ValueError, match="masse molaire"):
        GasModel.from_molar_mass(1.4, 0.0)
    with pytest.raises(ValueError, match="T"):
        GasModel(1.4, 287.0).density(1e5, 0.0)
    with pytest.raises(ValueError, match="T"):
        GasModel(1.4, 287.0).sound_speed(-1.0)


def test_model_is_immutable(air: GasModel) -> None:
    with pytest.raises(AttributeError):
        air.gamma = 1.3  # type: ignore[misc]
