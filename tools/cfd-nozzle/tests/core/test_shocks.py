"""Normal shocks, oblique shocks and Prandtl-Meyer against published tables."""

from __future__ import annotations

import math

import pytest

from cfd_nozzle.core.gas import GAS_LIBRARY, GasModel
from cfd_nozzle.core.isentropic import mach_angle
from cfd_nozzle.core.shocks import (
    beta_from_theta,
    mach_from_prandtl_meyer,
    mach_from_shock_p0_ratio,
    normal_shock_state,
    nu_max,
    oblique_shock,
    pitot_p0_ratio,
    prandtl_meyer,
    shock_entropy_rise,
    shock_m2,
    shock_p0_ratio,
    shock_p_ratio,
    shock_rho_ratio,
    shock_t_ratio,
    theta_from_beta,
    theta_max_oblique,
)
from tests.conftest import (
    NORMAL_SHOCK_TABLE,
    OBLIQUE_SHOCK_TABLE,
    PRANDTL_MEYER_TABLE,
    THETA_MAX_TABLE,
)

# --- normal shock ---------------------------------------------------------


@pytest.mark.parametrize(("m1", "m2", "p", "rho", "t", "p0"), NORMAL_SHOCK_TABLE)
def test_normal_shock_matches_table(
    m1: float, m2: float, p: float, rho: float, t: float, p0: float
) -> None:
    state = normal_shock_state(m1)
    assert state.m2 == pytest.approx(m2, rel=1e-5)
    assert state.p_ratio == pytest.approx(p, rel=1e-6)
    assert state.rho_ratio == pytest.approx(rho, rel=1e-6)
    assert state.t_ratio == pytest.approx(t, rel=1e-6)
    assert state.p0_ratio == pytest.approx(p0, rel=1e-4)


def test_sonic_shock_is_the_identity() -> None:
    assert shock_m2(1.0) == pytest.approx(1.0)
    assert shock_p_ratio(1.0) == pytest.approx(1.0)
    assert shock_rho_ratio(1.0) == pytest.approx(1.0)
    assert shock_p0_ratio(1.0) == pytest.approx(1.0)


@pytest.mark.parametrize("m1", [1.2, 2.0, 3.5, 6.0])
def test_shock_always_decelerates_and_loses_total_pressure(m1: float) -> None:
    assert shock_m2(m1) < 1.0
    assert 0.0 < shock_p0_ratio(m1) < 1.0
    assert shock_p_ratio(m1) > 1.0
    assert shock_t_ratio(m1) > 1.0
    assert shock_entropy_rise(m1, GAS_LIBRARY["air"]) > 0.0


def test_density_jump_is_bounded() -> None:
    limit = (1.4 + 1.0) / (1.4 - 1.0)
    assert shock_rho_ratio(1e4) < limit
    assert shock_rho_ratio(1e4) == pytest.approx(limit, rel=1e-6)


@pytest.mark.parametrize("m1", [1.1, 2.0, 4.0])
def test_p0_ratio_round_trip(m1: float) -> None:
    assert mach_from_shock_p0_ratio(shock_p0_ratio(m1)) == pytest.approx(m1, rel=1e-9)


def test_normal_shock_rejects_subsonic() -> None:
    with pytest.raises(ValueError, match="M1 ≥ 1"):
        shock_m2(0.8)
    with pytest.raises(ValueError, match="p02/p01"):
        mach_from_shock_p0_ratio(1.5)


def test_pitot_ratio_switches_regime() -> None:
    # Below M = 1 the pitot reads the isentropic total pressure; above it, the
    # bow shock costs total pressure, so p02/p1 grows more slowly.
    assert pitot_p0_ratio(0.5) == pytest.approx(1.186212, rel=1e-5)
    assert pitot_p0_ratio(2.0) == pytest.approx(5.640440, rel=1e-5)
    # Continuous through M = 1, where the shock vanishes.
    assert pitot_p0_ratio(1.0 - 1e-9) == pytest.approx(pitot_p0_ratio(1.0), rel=1e-6)


# --- Prandtl-Meyer --------------------------------------------------------


@pytest.mark.parametrize(("mach", "nu_deg"), PRANDTL_MEYER_TABLE)
def test_prandtl_meyer_matches_table(mach: float, nu_deg: float) -> None:
    assert math.degrees(prandtl_meyer(mach)) == pytest.approx(nu_deg, abs=1e-3)


def test_nu_max() -> None:
    assert math.degrees(nu_max(1.4)) == pytest.approx(130.4541, abs=1e-3)
    assert prandtl_meyer(1e7) < nu_max(1.4)


@pytest.mark.parametrize("mach", [1.0, 1.5, 3.0, 7.0])
def test_prandtl_meyer_round_trip(mach: float) -> None:
    assert mach_from_prandtl_meyer(prandtl_meyer(mach)) == pytest.approx(mach, rel=1e-8)


def test_prandtl_meyer_rejects_impossible_turning() -> None:
    with pytest.raises(ValueError, match="M ≥ 1"):
        prandtl_meyer(0.9)
    with pytest.raises(ValueError, match="détente impossible"):
        mach_from_prandtl_meyer(nu_max(1.4) + 0.1)
    with pytest.raises(ValueError, match="ν doit être"):
        mach_from_prandtl_meyer(-0.1)


# --- oblique shock --------------------------------------------------------


@pytest.mark.parametrize(("m1", "theta_deg", "beta_deg"), OBLIQUE_SHOCK_TABLE)
def test_oblique_shock_matches_table(m1: float, theta_deg: float, beta_deg: float) -> None:
    state = oblique_shock(m1, math.radians(theta_deg))
    assert state.beta_deg == pytest.approx(beta_deg, abs=1e-3)


@pytest.mark.parametrize(("m1", "theta_max_deg"), THETA_MAX_TABLE)
def test_theta_max_matches_table(m1: float, theta_max_deg: float) -> None:
    theta_max, beta_at_max = theta_max_oblique(m1)
    assert math.degrees(theta_max) == pytest.approx(theta_max_deg, abs=1e-3)
    assert mach_angle(m1) < beta_at_max < 0.5 * math.pi


@pytest.mark.parametrize(("m1", "theta_deg", "_beta"), OBLIQUE_SHOCK_TABLE)
def test_beta_round_trip(m1: float, theta_deg: float, _beta: float) -> None:
    theta = math.radians(theta_deg)
    beta = beta_from_theta(m1, theta)
    assert theta_from_beta(m1, beta) == pytest.approx(theta, rel=1e-9)


def test_zero_deflection_gives_a_mach_wave() -> None:
    beta = beta_from_theta(3.0, 0.0)
    assert beta == pytest.approx(mach_angle(3.0), abs=1e-6)


def test_strong_solution_is_subsonic_and_steeper() -> None:
    weak = oblique_shock(3.0, math.radians(20.0), weak=True)
    strong = oblique_shock(3.0, math.radians(20.0), weak=False)
    assert strong.beta_deg > weak.beta_deg
    assert weak.m2 > 1.0
    assert strong.m2 < 1.0
    assert strong.p_ratio > weak.p_ratio
    assert weak.solution_label == "faible"
    assert strong.solution_label == "forte"


def test_oblique_reduces_to_normal_at_ninety_degrees() -> None:
    # A shock normal to the flow deflects nothing.
    assert theta_from_beta(2.0, 0.5 * math.pi) == pytest.approx(0.0, abs=1e-12)


def test_detached_shock_is_reported() -> None:
    theta_max, _ = theta_max_oblique(2.0)
    with pytest.raises(ValueError, match="détaché"):
        oblique_shock(2.0, theta_max + math.radians(1.0))
    with pytest.raises(ValueError, match="θ doit être"):
        beta_from_theta(2.0, -0.1)


def test_oblique_jumps_use_the_normal_component() -> None:
    state = oblique_shock(3.0, math.radians(20.0))
    assert state.mn1 == pytest.approx(3.0 * math.sin(math.radians(state.beta_deg)))
    assert state.p_ratio == pytest.approx(shock_p_ratio(state.mn1))
    assert state.mn2 == pytest.approx(shock_m2(state.mn1))


@pytest.mark.parametrize("gamma", [1.2, 1.4, 1.667])
def test_entropy_rise_matches_total_pressure_loss(gamma: float) -> None:
    gas = GasModel(gamma, 300.0, "test")
    rise = shock_entropy_rise(2.5, gas)
    assert rise == pytest.approx(-gas.r * math.log(shock_p0_ratio(2.5, gamma)))
