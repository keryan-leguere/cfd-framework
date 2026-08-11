"""Isentropic relations against the published tables, plus round-trips."""

from __future__ import annotations

import math

import pytest

from cfd_nozzle.core.isentropic import (
    Branch,
    area_ratio,
    isentropic_state,
    mach_angle,
    mach_from_area_ratio,
    mach_from_p0_over_p,
    mach_from_t0_over_t,
    mach_star,
    p0_over_p,
    rho0_over_rho,
    t0_over_t,
)
from tests.conftest import ISENTROPIC_TABLE


@pytest.mark.parametrize(("mach", "t_ratio", "p_ratio", "rho_ratio", "area"), ISENTROPIC_TABLE)
def test_matches_published_table(
    mach: float, t_ratio: float, p_ratio: float, rho_ratio: float, area: float
) -> None:
    assert 1.0 / t0_over_t(mach) == pytest.approx(t_ratio, rel=1e-5)
    assert 1.0 / p0_over_p(mach) == pytest.approx(p_ratio, rel=1e-4)
    assert 1.0 / rho0_over_rho(mach) == pytest.approx(rho_ratio, rel=1e-4)
    assert area_ratio(mach) == pytest.approx(area, rel=1e-5)


def test_area_ratio_is_minimum_at_sonic() -> None:
    assert area_ratio(1.0) == pytest.approx(1.0)
    for mach in (0.2, 0.5, 0.9, 1.1, 2.0, 5.0):
        assert area_ratio(mach) > 1.0


@pytest.mark.parametrize("mach", [0.1, 0.5, 0.99, 1.01, 2.0, 4.0, 8.0])
def test_area_ratio_round_trip(mach: float) -> None:
    branch: Branch = "sub" if mach < 1.0 else "sup"
    assert mach_from_area_ratio(area_ratio(mach), 1.4, branch) == pytest.approx(mach, rel=1e-9)


def test_area_ratio_has_two_roots() -> None:
    subsonic = mach_from_area_ratio(2.0, 1.4, "sub")
    supersonic = mach_from_area_ratio(2.0, 1.4, "sup")
    assert subsonic < 1.0 < supersonic
    assert area_ratio(subsonic) == pytest.approx(area_ratio(supersonic))


@pytest.mark.parametrize("mach", [0.3, 1.0, 2.5, 6.0])
def test_pressure_and_temperature_round_trips(mach: float) -> None:
    assert mach_from_p0_over_p(p0_over_p(mach)) == pytest.approx(mach, rel=1e-12)
    assert mach_from_t0_over_t(t0_over_t(mach)) == pytest.approx(mach, rel=1e-12)


def test_mach_star_stays_finite() -> None:
    limit = math.sqrt((1.4 + 1.0) / (1.4 - 1.0))
    assert mach_star(1.0) == pytest.approx(1.0)
    assert mach_star(1e6) == pytest.approx(limit, rel=1e-6)
    assert mach_star(1e6) < limit


def test_mach_angle() -> None:
    assert math.degrees(mach_angle(1.0)) == pytest.approx(90.0)
    assert math.degrees(mach_angle(2.0)) == pytest.approx(30.0)


def test_state_carries_supersonic_extras() -> None:
    subsonic = isentropic_state(0.5)
    assert subsonic.mu_deg is None and subsonic.nu_deg is None
    supersonic = isentropic_state(2.0)
    assert supersonic.mu_deg == pytest.approx(30.0)
    assert supersonic.nu_deg == pytest.approx(26.3798, abs=1e-3)


@pytest.mark.parametrize("gamma", [1.2, 1.3, 1.4, 1.667])
def test_relations_are_consistent_for_any_gamma(gamma: float) -> None:
    mach = 2.5
    # p0/p = (T0/T)^(γ/(γ-1)) and ρ0/ρ = (T0/T)^(1/(γ-1)) must stay compatible
    # with the perfect-gas law: p/ρ ∝ T.
    ratio = p0_over_p(mach, gamma) / rho0_over_rho(mach, gamma)
    assert ratio == pytest.approx(t0_over_t(mach, gamma), rel=1e-12)


def test_rejects_invalid_input() -> None:
    with pytest.raises(ValueError, match="M doit être"):
        area_ratio(0.0)
    with pytest.raises(ValueError, match="A/A"):
        mach_from_area_ratio(0.5)
    with pytest.raises(ValueError, match="sub"):
        mach_from_area_ratio(2.0, 1.4, "autre")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="M ≥ 1"):
        mach_angle(0.9)
    with pytest.raises(ValueError, match="p0/p"):
        mach_from_p0_over_p(0.5)
    with pytest.raises(ValueError, match="T0/T"):
        mach_from_t0_over_t(0.5)
