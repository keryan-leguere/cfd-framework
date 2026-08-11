"""Report layer: the theme contract and the figure builders."""

from __future__ import annotations

import importlib
import math

import matplotlib
import pytest
from rich.console import Console

from cfd_nozzle.core.gas import GAS_LIBRARY
from cfd_nozzle.core.geometry import bell_contour
from cfd_nozzle.core.isentropic import isentropic_state
from cfd_nozzle.core.moc import moc_nozzle
from cfd_nozzle.core.nozzle import Nozzle
from cfd_nozzle.core.shocks import normal_shock_state, oblique_shock, theta_max_oblique
from cfd_nozzle.report import console as report
from cfd_nozzle.report import figures, theme

# --- theme ----------------------------------------------------------------


def test_bold_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(theme.ENV_GRAS, raising=False)
    reloaded = importlib.reload(theme)
    assert not reloaded.gras_actif()
    assert "bold" not in reloaded.TITRE
    assert "bold" not in reloaded.ACCENT


def test_bold_can_be_restored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(theme.ENV_GRAS, "1")
    reloaded = importlib.reload(theme)
    assert reloaded.gras_actif()
    assert reloaded.TITRE.startswith("bold ")
    monkeypatch.delenv(theme.ENV_GRAS)
    importlib.reload(theme)


def test_every_regime_has_a_style() -> None:
    from cfd_nozzle.core.nozzle import Regime

    for regime in Regime:
        assert regime.value in theme.STYLE_REGIME


# --- console reports ------------------------------------------------------


@pytest.fixture
def console() -> Console:
    return Console(width=100, force_terminal=False)


def test_reports_render_without_error(console: Console) -> None:
    report.print_isentropic_report(console, isentropic_state(2.0))
    report.print_normal_shock_report(console, normal_shock_state(2.0), 100.0)
    theta_max, _ = theta_max_oblique(3.0)
    report.print_oblique_shock_report(
        console, oblique_shock(3.0, math.radians(20.0)), math.degrees(theta_max)
    )
    report.print_prandtl_meyer_report(console, 2.0, 26.38, 30.0, 130.45, 1.4)
    report.print_gas_line(console, GAS_LIBRARY["air"])


def test_nozzle_report_contains_the_answer() -> None:
    console = Console(width=110, record=True, force_terminal=False)
    nozzle = Nozzle(0.03, 16.0, GAS_LIBRARY["lox_rp1"], eta_cstar=0.96)
    contour = bell_contour(math.sqrt(0.03 / math.pi), 16.0)
    report.print_nozzle_report(console, nozzle, nozzle.solve(100e5, 3500.0, 1.013e5), contour=contour)
    text = console.export_text()
    assert "sur-détendue" in text
    assert "poussée F" in text
    assert "NPR₃" in text
    assert "galbée Rao" in text


def test_contour_and_moc_reports() -> None:
    console = Console(width=110, record=True, force_terminal=False)
    report.print_contour_report(console, bell_contour(0.05, 16.0))
    report.print_moc_report(console, moc_nozzle(2.0, 12, 1.0, 1.4, axisymmetric=False))
    text = console.export_text()
    assert "λ (divergence)" in text
    assert "ε théorique" in text
    assert "Écart au ε théorique" in text


# --- figures --------------------------------------------------------------


def test_figures_use_a_headless_backend() -> None:
    assert matplotlib.get_backend().lower() == "agg"


def test_flow_field_figure(tmp_path) -> None:  # type: ignore[no-untyped-def]
    nozzle = Nozzle(0.03, 16.0, GAS_LIBRARY["lox_rp1"])
    contour = bell_contour(math.sqrt(0.03 / math.pi), 16.0)
    field = nozzle.flow_field(contour.x, contour.area, 100e5, 3500.0, 1.013e5)
    written = figures.save_figure(figures.plot_flow_field(contour, field), tmp_path / "champ")
    assert written and all(p.exists() and p.stat().st_size > 0 for p in written)


def test_flow_field_figure_marks_an_internal_shock(tmp_path) -> None:  # type: ignore[no-untyped-def]
    nozzle = Nozzle(0.03, 4.0, GAS_LIBRARY["air"])
    contour = bell_contour(math.sqrt(0.03 / math.pi), 4.0)
    field = nozzle.flow_field(contour.x, contour.area, 10e5, 300.0, 6e5)
    assert field.x_shock is not None
    written = figures.save_figure(figures.plot_flow_field(contour, field), tmp_path / "choc")
    assert written[0].exists()


def test_contour_figure(tmp_path) -> None:  # type: ignore[no-untyped-def]
    written = figures.save_figure(figures.plot_contour(bell_contour(0.05, 16.0)), tmp_path / "geom")
    assert written[0].exists()


@pytest.mark.parametrize("show_mesh", [True, False])
def test_moc_figure(tmp_path, show_mesh: bool) -> None:  # type: ignore[no-untyped-def]
    result = moc_nozzle(2.0, 10, 1.0, 1.4, axisymmetric=True)
    fig = figures.plot_moc(result, show_mesh=show_mesh)
    written = figures.save_figure(fig, tmp_path / f"moc_{show_mesh}")
    assert written[0].exists()


def test_performance_map_figure(tmp_path) -> None:  # type: ignore[no-untyped-def]
    nozzle = Nozzle(0.03, 16.0, GAS_LIBRARY["lox_rp1"])
    fig = figures.plot_performance_map(nozzle, 100e5, 3500.0, 1e3, 2e5, n=40)
    written = figures.save_figure(fig, tmp_path / "carte")
    assert written[0].exists()


def test_save_figure_creates_missing_directories(tmp_path) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "a" / "b" / "figure"
    written = figures.save_figure(figures.plot_contour(bell_contour(0.05, 8.0)), target)
    assert written[0].parent.is_dir()


def test_plotting_library_is_optional() -> None:
    """cfd-nozzle must render figures with or without the sibling cfd-plot."""
    from cfd_nozzle.report._plotting_lib import HAS_PLOTTING, get_plotting

    assert HAS_PLOTTING == (get_plotting() is not None)
