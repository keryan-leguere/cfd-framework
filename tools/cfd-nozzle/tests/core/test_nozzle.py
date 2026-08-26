"""Nozzle regimes, performance decomposition and the quasi-1D field."""

from __future__ import annotations

import math

import numpy as np
import pytest

from cfd_nozzle._compat import pairwise
from cfd_nozzle.core.gas import G0, GAS_LIBRARY, GasModel
from cfd_nozzle.core.geometry import bell_contour
from cfd_nozzle.core.isentropic import area_ratio, p0_over_p
from cfd_nozzle.core.nozzle import Nozzle, Regime

P0 = 100e5
T0 = 3500.0


@pytest.fixture
def engine(lox_rp1: GasModel) -> Nozzle:
    return Nozzle(0.25 * math.pi * 0.20**2, 16.0, lox_rp1)


@pytest.fixture
def small_nozzle(air: GasModel) -> Nozzle:
    """A modest ε, so the unchoked window (NPR < NPR₁) is wide enough to probe.

    At ε = 16 the first critical ratio sits at 1.0008: the venturi regime is a
    sliver, and testing in it says nothing.
    """
    return Nozzle(0.01, 2.0, air)


def _unchoked_pa(nozzle: Nozzle, p0: float) -> float:
    """A back pressure that leaves the throat subsonic (1 < NPR < NPR₁)."""
    return p0 / (1.0 + 0.5 * (nozzle.critical_ratios().npr_choked - 1.0))


# --- construction ---------------------------------------------------------


def test_geometry_properties(engine: Nozzle) -> None:
    assert engine.exit_area == pytest.approx(engine.throat_area * 16.0)
    assert engine.throat_diameter == pytest.approx(0.20)
    assert engine.exit_diameter == pytest.approx(0.20 * math.sqrt(16.0))


def test_from_diameters() -> None:
    nozzle = Nozzle.from_diameters(0.05, 0.10)
    assert nozzle.eps == pytest.approx(4.0)
    assert nozzle.throat_diameter == pytest.approx(0.05)


def test_rejects_invalid_construction(air: GasModel) -> None:
    with pytest.raises(ValueError, match="aire au col"):
        Nozzle(0.0, 4.0, air)
    with pytest.raises(ValueError, match="ε"):
        Nozzle(0.01, 0.5, air)
    with pytest.raises(ValueError, match="η_c"):
        Nozzle(0.01, 4.0, air, eta_cstar=1.5)
    with pytest.raises(ValueError, match="λ"):
        Nozzle(0.01, 4.0, air, lambda_div=0.0)


# --- critical ratios and regimes -----------------------------------------


def test_critical_ratios_are_ordered(engine: Nozzle) -> None:
    critical = engine.critical_ratios()
    assert 1.0 < critical.npr_choked < critical.npr_shock_at_exit < critical.npr_design
    assert critical.mach_exit_sub < 1.0 < critical.mach_exit_sup
    assert area_ratio(critical.mach_exit_sup, engine.gas.gamma) == pytest.approx(engine.eps)


def test_each_regime_is_reached(engine: Nozzle) -> None:
    critical = engine.critical_ratios()
    cases = [
        (_unchoked_pa(engine, P0), Regime.VENTURI),
        (P0 / (0.5 * (critical.npr_choked + critical.npr_shock_at_exit)), Regime.SHOCK_IN_DIVERGENT),
        (P0 / (0.5 * (critical.npr_shock_at_exit + critical.npr_design)), Regime.OVEREXPANDED),
        (P0 / critical.npr_design, Regime.ADAPTED),
        (P0 / (2.0 * critical.npr_design), Regime.UNDEREXPANDED),
    ]
    for pa, expected in cases:
        assert engine.solve(P0, T0, pa).regime is expected


def test_venturi_regime_on_a_modest_area_ratio(small_nozzle: Nozzle) -> None:
    p0 = 3e5
    state = small_nozzle.solve(p0, 300.0, _unchoked_pa(small_nozzle, p0))
    assert state.regime is Regime.VENTURI
    assert not state.choked
    assert state.mach_exit < 1.0
    assert state.p_exit == pytest.approx(state.pa, rel=1e-9)
    assert any("divergent" in w for w in state.warnings)


def test_choking_flag_follows_the_regime(engine: Nozzle) -> None:
    critical = engine.critical_ratios()
    assert not engine.solve(P0, T0, _unchoked_pa(engine, P0)).choked
    assert engine.solve(P0, T0, P0 / critical.npr_design).choked


def test_adapted_point_has_matched_pressure(engine: Nozzle) -> None:
    critical = engine.critical_ratios()
    state = engine.solve(P0, T0, P0 / critical.npr_design)
    assert state.regime is Regime.ADAPTED
    assert state.p_exit == pytest.approx(state.pa, rel=1e-6)
    assert state.mach_exit == pytest.approx(critical.mach_exit_sup)


def test_back_pressure_is_matched_when_the_flow_is_not_supersonic(engine: Nozzle) -> None:
    critical = engine.critical_ratios()
    for pa in (
        _unchoked_pa(engine, P0),
        P0 / (0.5 * (critical.npr_choked + critical.npr_shock_at_exit)),
    ):
        state = engine.solve(P0, T0, pa)
        assert state.p_exit == pytest.approx(pa, rel=1e-6)


def test_supersonic_exit_ignores_back_pressure(engine: Nozzle) -> None:
    critical = engine.critical_ratios()
    over = engine.solve(P0, T0, P0 / (0.9 * critical.npr_design))
    under = engine.solve(P0, T0, P0 / (5.0 * critical.npr_design))
    assert over.p_exit == pytest.approx(under.p_exit)
    assert over.mach_exit == pytest.approx(under.mach_exit)
    assert over.p_exit < over.pa  # over-expanded
    assert under.p_exit > under.pa  # under-expanded


def test_shock_location_moves_downstream_with_npr(engine: Nozzle) -> None:
    critical = engine.critical_ratios()
    lower, upper = critical.npr_choked * 1.5, critical.npr_shock_at_exit * 0.99
    weak = engine.solve(P0, T0, P0 / lower)
    strong = engine.solve(P0, T0, P0 / upper)
    assert weak.mach_shock is not None and strong.mach_shock is not None
    assert strong.area_ratio_shock is not None and weak.area_ratio_shock is not None
    assert strong.area_ratio_shock > weak.area_ratio_shock
    assert strong.mach_shock > weak.mach_shock
    # At the second critical ratio the shock sits in the exit plane.
    assert strong.area_ratio_shock == pytest.approx(engine.eps, rel=2e-2)


def test_separation_warning_appears_when_over_expanded(engine: Nozzle) -> None:
    state = engine.solve(P0, T0, P0 / (0.3 * engine.critical_ratios().npr_design))
    assert state.regime is Regime.OVEREXPANDED
    assert any("Summerfield" in w for w in state.warnings)


def test_vacuum_is_under_expanded(engine: Nozzle) -> None:
    state = engine.solve(P0, T0, 0.0)
    assert state.regime is Regime.UNDEREXPANDED
    assert math.isinf(state.npr)


# --- performance decomposition -------------------------------------------


@pytest.mark.parametrize("eta", [1.0, 0.96, 0.85])
@pytest.mark.parametrize("lam", [1.0, 0.985])
def test_sutton_decomposition_is_self_consistent(
    lox_rp1: GasModel, eta: float, lam: float
) -> None:
    nozzle = Nozzle(0.03, 16.0, lox_rp1, eta_cstar=eta, lambda_div=lam)
    state = nozzle.solve(P0, T0, 1.013e5)
    # c* ≡ p0·At/ṁ, by definition.
    assert state.mdot * state.c_star == pytest.approx(P0 * nozzle.throat_area, rel=1e-12)
    # F = Cf·p0·At and Isp = Cf·c*/g0 must agree with F/(ṁ·g0).
    assert state.thrust == pytest.approx(state.cf * P0 * nozzle.throat_area, rel=1e-12)
    assert state.isp == pytest.approx(state.cf * state.c_star / G0, rel=1e-10)
    assert state.v_effective == pytest.approx(state.thrust / state.mdot, rel=1e-12)


def test_lower_combustion_efficiency_raises_flow_and_lowers_isp(lox_rp1: GasModel) -> None:
    ideal = Nozzle(0.03, 16.0, lox_rp1).solve(P0, T0, 1.013e5)
    degraded = Nozzle(0.03, 16.0, lox_rp1, eta_cstar=0.9).solve(P0, T0, 1.013e5)
    assert degraded.mdot > ideal.mdot
    assert degraded.isp < ideal.isp
    assert degraded.thrust == pytest.approx(ideal.thrust)  # Cf is untouched
    assert degraded.c_star == pytest.approx(0.9 * ideal.c_star)


def test_divergence_loss_only_degrades_the_momentum_term(lox_rp1: GasModel) -> None:
    ideal = Nozzle(0.03, 16.0, lox_rp1).solve(P0, T0, 1.013e5)
    lossy = Nozzle(0.03, 16.0, lox_rp1, lambda_div=0.95).solve(P0, T0, 1.013e5)
    assert lossy.thrust < ideal.thrust
    assert lossy.mdot == pytest.approx(ideal.mdot)


def test_ideal_adapted_thrust_equals_momentum_flux(lox_rp1: GasModel) -> None:
    """With η = λ = 1 and pe = pa, F must reduce to ṁ·Ve."""
    nozzle = Nozzle(0.03, 16.0, lox_rp1)
    state = nozzle.solve(P0, T0, P0 / nozzle.critical_ratios().npr_design)
    assert state.thrust == pytest.approx(state.mdot * state.v_exit, rel=1e-9)


def test_choked_mass_flow_matches_the_textbook_formula(lox_rp1: GasModel) -> None:
    nozzle = Nozzle(0.03, 16.0, lox_rp1)
    expected = (
        lox_rp1.vandenkerckhove * P0 * nozzle.throat_area / math.sqrt(lox_rp1.r * T0)
    )
    assert nozzle.mdot_choked(P0, T0) == pytest.approx(expected, rel=1e-12)


def test_mass_flow_is_independent_of_back_pressure_once_choked(engine: Nozzle) -> None:
    critical = engine.critical_ratios()
    flows = [
        engine.solve(P0, T0, P0 / npr).mdot
        for npr in (critical.npr_shock_at_exit * 1.1, critical.npr_design, 1e6)
    ]
    assert flows[0] == pytest.approx(flows[1]) == pytest.approx(flows[2])


def test_thrust_grows_monotonically_as_ambient_pressure_drops(engine: Nozzle) -> None:
    thrusts = [engine.solve(P0, T0, pa).thrust for pa in (2e5, 1e5, 5e4, 1e3, 1.0)]
    assert all(a < b for a, b in pairwise(thrusts))


def test_optimal_area_ratio_reproduces_adaptation(engine: Nozzle) -> None:
    pa = 1.013e5
    eps_opt = engine.optimal_area_ratio(P0, pa)
    adapted = Nozzle(engine.throat_area, eps_opt, engine.gas)
    assert adapted.solve(P0, T0, pa).regime is Regime.ADAPTED
    assert engine.optimal_area_ratio(P0, 0.0) == math.inf
    assert engine.optimal_area_ratio(1e5, 2e5) == 1.0


def test_exit_velocity_stays_below_the_vacuum_limit(engine: Nozzle) -> None:
    state = engine.solve(P0, T0, 1.0)
    assert state.v_exit < engine.gas.limit_velocity(T0)


def test_solve_rejects_impossible_conditions(engine: Nozzle) -> None:
    with pytest.raises(ValueError, match="p0"):
        engine.solve(0.0, T0, 1e5)
    with pytest.raises(ValueError, match="T0"):
        engine.solve(P0, 0.0, 1e5)
    with pytest.raises(ValueError, match="pa"):
        engine.solve(P0, T0, -1.0)
    # No pressure difference means no flow; a reversed one is out of model.
    with pytest.raises(ValueError, match="hors du modèle"):
        engine.solve(P0, T0, P0)
    with pytest.raises(ValueError, match="hors du modèle"):
        engine.solve(P0, T0, 2.0 * P0)


# --- axial field ----------------------------------------------------------


def _contour_arrays(engine: Nozzle) -> tuple[np.ndarray, np.ndarray]:
    contour = bell_contour(math.sqrt(engine.throat_area / math.pi), engine.eps)
    return contour.x, contour.area


def test_field_is_sonic_at_the_throat_when_choked(engine: Nozzle) -> None:
    x, area = _contour_arrays(engine)
    field = engine.flow_field(x, area, P0, T0, 1.013e5)
    throat = int(np.argmin(area))
    assert field.mach[throat] == pytest.approx(1.0, abs=1e-6)
    assert field.mach[0] < 1.0
    assert field.mach[-1] > 1.0


def test_field_ends_on_the_solved_exit_state(engine: Nozzle) -> None:
    x, area = _contour_arrays(engine)
    field = engine.flow_field(x, area, P0, T0, 1.013e5)
    assert field.mach[-1] == pytest.approx(field.state.mach_exit, rel=1e-4)
    assert field.p[-1] == pytest.approx(field.state.p_exit, rel=1e-3)
    assert field.x_shock is None


def test_field_captures_an_internal_shock(engine: Nozzle) -> None:
    critical = engine.critical_ratios()
    pa = P0 / (0.5 * (critical.npr_choked + critical.npr_shock_at_exit))
    x, area = _contour_arrays(engine)
    field = engine.flow_field(x, area, P0, T0, pa)
    assert field.x_shock is not None and field.x_shock > 0.0
    before = field.mach[field.x < field.x_shock]
    after = field.mach[field.x > field.x_shock]
    assert before.max() > 1.0  # supersonic upstream
    assert after.max() < 1.0  # subsonic downstream
    assert field.p[-1] == pytest.approx(pa, rel=1e-2)


def test_field_stays_subsonic_when_not_choked(engine: Nozzle) -> None:
    pa = _unchoked_pa(engine, P0)
    x, area = _contour_arrays(engine)
    field = engine.flow_field(x, area, P0, T0, pa)
    assert field.mach.max() < 1.0
    assert not field.state.choked


def test_field_satisfies_mass_conservation(engine: Nozzle) -> None:
    x, area = _contour_arrays(engine)
    field = engine.flow_field(x, area, P0, T0, 1.013e5)
    mass_flux = field.rho * field.v * field.area
    assert mass_flux.std() / mass_flux.mean() < 1e-6


def test_field_rejects_mismatched_arrays(engine: Nozzle) -> None:
    with pytest.raises(ValueError, match="même forme"):
        engine.flow_field(np.array([0.0, 1.0]), np.array([1.0]), P0, T0, 1e5)
    with pytest.raises(ValueError, match="deux points"):
        engine.flow_field(np.array([0.0]), np.array([1.0]), P0, T0, 1e5)


def test_thrust_coefficient_helper_matches_solve(engine: Nozzle) -> None:
    pa = 1.013e5
    state = engine.solve(P0, T0, pa)
    p_exit = P0 / p0_over_p(engine.mach_exit("sup"), engine.gas.gamma)
    assert engine.thrust_coefficient(P0, pa, p_exit=p_exit) == pytest.approx(state.cf)
    assert engine.thrust_coefficient(P0, pa) == pytest.approx(state.cf)


def test_air_wind_tunnel_case(air: GasModel) -> None:
    """A Mach-2 tunnel nozzle: ε = 1.6875 must give exactly Me = 2."""
    nozzle = Nozzle.from_diameters(0.05, 0.05 * math.sqrt(1.6875), gas=air)
    assert nozzle.mach_exit("sup") == pytest.approx(2.0, rel=1e-6)
    critical = nozzle.critical_ratios()
    assert critical.npr_design == pytest.approx(p0_over_p(2.0, 1.4), rel=1e-6)
    assert GAS_LIBRARY["air"].gamma == 1.4
