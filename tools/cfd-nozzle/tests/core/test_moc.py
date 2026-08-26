"""Method of characteristics: compatibility relations, convergence, contour.

The decisive check is that the designed wall reproduces the area ratio that
A/A*(M_exit) prescribes — the design fixes the exit Mach number, so the two
must agree. It catches any error in the source term, the unit processes or the
wall tracing at once.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from cfd_nozzle._compat import pairwise
from cfd_nozzle.core.isentropic import area_ratio, mach_angle
from cfd_nozzle.core.moc import check_axisymmetric_compatibility, moc_nozzle
from cfd_nozzle.core.shocks import prandtl_meyer

# --- the compatibility relations themselves -------------------------------


@pytest.mark.parametrize("mach", [1.5, 2.0, 3.5])
@pytest.mark.parametrize("phi_deg", [5.0, 12.0, 25.0])
@pytest.mark.parametrize("gamma", [1.2, 1.4])
def test_axisymmetric_source_term_is_exact_on_the_source_flow(
    mach: float, phi_deg: float, gamma: float
) -> None:
    """The spherical source flow is an exact solution: residuals must vanish."""
    residuals = check_axisymmetric_compatibility(mach, phi_deg, gamma)
    for name, value in residuals.items():
        assert abs(value) < 1e-12, f"{name} = {value:g}"


# --- planar design --------------------------------------------------------


@pytest.mark.parametrize("mach_exit", [1.6, 2.0, 2.4, 3.0])
def test_planar_theta_max_is_half_nu_exit(mach_exit: float) -> None:
    """In planar flow the Riemann invariants hold, giving θ_max = ν_e/2 exactly."""
    result = moc_nozzle(mach_exit, 20, 1.0, 1.4, axisymmetric=False)
    expected = 0.5 * math.degrees(prandtl_meyer(mach_exit, 1.4))
    assert result.theta_max_deg == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("mach_exit", [1.6, 2.0, 2.4, 3.0])
def test_planar_contour_matches_the_theoretical_area_ratio(mach_exit: float) -> None:
    result = moc_nozzle(mach_exit, 40, 1.0, 1.4, axisymmetric=False)
    assert result.area_ratio == pytest.approx(result.area_ratio_theory, rel=1e-3)
    assert result.area_ratio_theory == pytest.approx(area_ratio(mach_exit, 1.4))
    assert not result.axisymmetric
    assert result.label == "plane"


# --- axisymmetric design --------------------------------------------------


@pytest.mark.parametrize("mach_exit", [1.6, 2.0, 2.4, 3.0, 4.0])
def test_axisymmetric_contour_matches_the_theoretical_area_ratio(mach_exit: float) -> None:
    result = moc_nozzle(mach_exit, 40, 1.0, 1.4, axisymmetric=True)
    assert result.area_ratio == pytest.approx(result.area_ratio_theory, rel=1e-3)
    assert result.axisymmetric
    assert result.label == "axisymétrique"


@pytest.mark.parametrize("gamma", [1.2, 1.4, 1.667])
def test_design_works_across_gamma(gamma: float) -> None:
    result = moc_nozzle(3.0, 30, 1.0, gamma, axisymmetric=True)
    assert result.area_ratio == pytest.approx(result.area_ratio_theory, rel=2e-3)


def test_axisymmetric_needs_less_corner_turning_than_planar() -> None:
    """The δ = 1 source term accelerates the axis, so θ_max must be smaller."""
    planar = moc_nozzle(2.4, 30, 1.0, 1.4, axisymmetric=False)
    axi = moc_nozzle(2.4, 30, 1.0, 1.4, axisymmetric=True)
    assert axi.theta_max_deg < planar.theta_max_deg
    # ...and the resulting nozzle is shorter for the same exit Mach number.
    assert axi.length < planar.length


@pytest.mark.parametrize("axisymmetric", [False, True])
def test_refining_the_mesh_converges(axisymmetric: bool) -> None:
    errors = [
        moc_nozzle(2.4, n, 1.0, 1.4, axisymmetric=axisymmetric).area_ratio_error
        for n in (15, 30, 60)
    ]
    assert errors[0] > errors[1] > errors[2]
    assert errors[-1] < 1e-3


# --- contour shape --------------------------------------------------------


@pytest.mark.parametrize("axisymmetric", [False, True])
def test_wall_is_monotonic_and_ends_axially(axisymmetric: bool) -> None:
    result = moc_nozzle(2.4, 30, 1.0, 1.4, axisymmetric=axisymmetric)
    assert np.all(np.diff(result.wall_x) > -1e-12)
    assert np.all(np.diff(result.wall_y) > -1e-12)
    assert result.wall_x[0] == pytest.approx(0.0)
    assert result.wall_y[0] == pytest.approx(1.0)  # starts at the throat corner
    # The last wall point lies on the exit characteristic, flow already axial.
    assert result.wall_points[-1].theta == pytest.approx(0.0, abs=1e-9)
    assert result.wall_points[-1].mach == pytest.approx(2.4, rel=1e-6)


def test_throat_radius_scales_the_whole_contour() -> None:
    unit = moc_nozzle(2.4, 20, 1.0, 1.4, axisymmetric=True)
    scaled = moc_nozzle(2.4, 20, 0.05, 1.4, axisymmetric=True)
    assert scaled.length == pytest.approx(0.05 * unit.length, rel=1e-9)
    assert scaled.y_exit == pytest.approx(0.05 * unit.y_exit, rel=1e-9)
    assert scaled.area_ratio == pytest.approx(unit.area_ratio, rel=1e-9)


def test_mesh_is_exported_for_plotting() -> None:
    result = moc_nozzle(2.0, 12, 1.0, 1.4, axisymmetric=False)
    assert result.kernel[(1, 1)].kind == "axis"
    assert len(result.kernel) == 12 * 13 // 2  # one point per (i, j ≤ i)
    assert len(result.transition) == result.n_char + 1
    assert all(p.mach >= 1.0 for p in result.points)
    # Every kernel axis point is at y = 0 with zero flow angle, by symmetry.
    for i in range(1, result.n_char + 1):
        assert result.kernel[(i, 1)].y == 0.0
        assert result.kernel[(i, 1)].theta == 0.0


def test_mach_grows_monotonically_along_the_axis() -> None:
    result = moc_nozzle(2.4, 25, 1.0, 1.4, axisymmetric=True)
    axis_mach = [result.kernel[(i, 1)].mach for i in range(1, result.n_char + 1)]
    assert all(a < b for a, b in pairwise(axis_mach))
    assert axis_mach[-1] == pytest.approx(2.4, rel=1e-6)


def test_wall_points_stay_supersonic_and_below_the_exit_mach() -> None:
    result = moc_nozzle(2.4, 25, 1.0, 1.4, axisymmetric=True)
    machs = [p.mach for p in result.wall_points]
    assert min(machs) > 1.0
    assert max(machs) == pytest.approx(2.4, rel=1e-3)


def test_exit_characteristic_slope_is_the_mach_angle() -> None:
    result = moc_nozzle(2.4, 20, 1.0, 1.4, axisymmetric=False)
    exit_line = result.transition[0]
    dx = exit_line[-1].x - exit_line[0].x
    dy = exit_line[-1].y - exit_line[0].y
    assert math.atan2(dy, dx) == pytest.approx(mach_angle(2.4), rel=1e-9)


# --- input validation and domain limits -----------------------------------


def test_rejects_invalid_input() -> None:
    with pytest.raises(ValueError, match="M_sortie"):
        moc_nozzle(1.0, 20)
    with pytest.raises(ValueError, match="n_char"):
        moc_nozzle(2.0, 2)
    with pytest.raises(ValueError, match="y_col"):
        moc_nozzle(2.0, 20, 0.0)


def test_out_of_envelope_design_reports_a_clear_limit() -> None:
    """Beyond M ≈ 4 axisymmetric the Goursat mesh degenerates — say so."""
    with pytest.raises(RuntimeError, match="hors du domaine validé"):
        moc_nozzle(5.0, 30, 1.0, 1.4, axisymmetric=True)
