"""Matplotlib figures, built on the in-house ``cfd_plot`` package when it is
available and falling back to plain Matplotlib otherwise.

Four figures, all labelled in French:

- the quasi-1D field along the nozzle (contour, M, p, T), with the internal
  shock marked when there is one;
- the characteristics mesh and the wall of a MOC design;
- the performance map versus ambient pressure, with the design point;
- a bare contour.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cfd_nozzle.core.geometry import NozzleContour
from cfd_nozzle.core.moc import MOCResult
from cfd_nozzle.core.nozzle import FlowField, Nozzle
from cfd_nozzle.report._plotting_lib import get_plotting

__all__ = [
    "plot_contour",
    "plot_flow_field",
    "plot_moc",
    "plot_performance_map",
    "save_figure",
]

_plotting = get_plotting()

_WALL = "#1b1b1b"
_MACH = "#1f77b4"
_PRESSURE = "#2ca02c"
_TEMPERATURE = "#d62728"
_SHOCK = "#9467bd"
_DESIGN = "#e377c2"


def _use_style(profile: str = "notebook") -> None:
    if _plotting is not None:
        _plotting.use_style(profile)


def save_figure(fig: Any, base: Path) -> list[Path]:
    """Save ``fig`` next to ``base`` (no suffix), returning the files written."""
    base.parent.mkdir(parents=True, exist_ok=True)
    if _plotting is not None:
        return [Path(p) for p in _plotting.save_figure(fig, str(base), formats=("png", "svg"))]
    written = []
    for suffix in (".png", ".svg"):
        path = base.with_suffix(suffix)
        fig.savefig(path, dpi=150, bbox_inches="tight")
        written.append(path)
    return written


def _grid(ax: Any) -> None:
    ax.grid(alpha=0.3)


def _draw_walls(ax: Any, x_mm: Any, r_mm: Any) -> None:
    ax.plot(x_mm, r_mm, "-", color=_WALL, lw=2)
    ax.plot(x_mm, -r_mm, "-", color=_WALL, lw=2)
    ax.fill_between(x_mm, -r_mm, r_mm, color="0.90")
    ax.axhline(0.0, color="0.6", ls=":", lw=0.8)


def plot_flow_field(
    contour: NozzleContour,
    field: FlowField,
    *,
    title: str = "Tuyère — champ quasi-1D",
) -> Any:
    """Four stacked panels: contour, Mach, pressure, temperature."""
    _use_style("notebook")
    x_mm = field.x * 1e3
    fig, axes = plt.subplots(4, 1, figsize=(9, 11), sharex=True)

    radius_mm = contour.r * 1e3
    _draw_walls(axes[0], x_mm, radius_mm)
    axes[0].set_ylabel("r [mm]")
    axes[0].set_title(title)
    # Not to scale: this panel shares its x-axis with the three physics panels
    # below, so forcing an equal aspect would let Matplotlib shrink the y-range
    # and clip the walls right out of the frame. The radius is bounded
    # explicitly instead.
    limit = 1.08 * float(radius_mm.max())
    axes[0].set_ylim(-limit, limit)

    axes[1].plot(x_mm, field.mach, "-", color=_MACH, lw=1.8)
    axes[1].axhline(1.0, color=_TEMPERATURE, ls="--", lw=0.9, label="M = 1 (col sonique)")
    axes[1].set_ylabel("Mach [-]")
    axes[1].legend(loc="best", fontsize=8)

    axes[2].plot(x_mm, field.p * 1e-5, "-", color=_PRESSURE, lw=1.8)
    axes[2].axhline(field.state.pa * 1e-5, color="0.4", ls="--", lw=0.9, label="pression ambiante")
    axes[2].set_ylabel("p [bar]")
    axes[2].legend(loc="best", fontsize=8)

    axes[3].plot(x_mm, field.t, "-", color=_TEMPERATURE, lw=1.8)
    axes[3].set_ylabel("T [K]")
    axes[3].set_xlabel("x [mm]   (col à x = 0)")

    if field.x_shock is not None:
        for ax in axes:
            ax.axvline(field.x_shock * 1e3, color=_SHOCK, ls="-.", lw=1.2)
        axes[1].annotate(
            "choc droit",
            (field.x_shock * 1e3, 1.5),
            color=_SHOCK,
            fontsize=9,
            rotation=90,
            va="bottom",
        )

    for ax in axes:
        _grid(ax)
    fig.tight_layout()
    return fig


def plot_contour(contour: NozzleContour, *, title: str | None = None) -> Any:
    """Plot a bare nozzle contour."""
    _use_style("notebook")
    fig, ax = plt.subplots(figsize=(9, 4))
    _draw_walls(ax, contour.x * 1e3, contour.r * 1e3)
    ax.set_xlabel("x [mm]   (col à x = 0)")
    ax.set_ylabel("r [mm]")
    ax.set_title(title or f"Contour — {contour.label}, ε = {contour.area_ratio:.2f}")
    ax.set_aspect("equal", adjustable="datalim")
    _grid(ax)
    fig.tight_layout()
    return fig


def _inside(result: MOCResult, x: Any, y: Any) -> Any:
    """Mask of the points lying inside the nozzle, i.e. under the wall.

    The Goursat mesh of the straightening region is deliberately marched past
    the wall — the wall is only found afterwards, as a streamline through that
    field. Those extra nodes carry no flow and must not be drawn.
    """
    wall = np.interp(x, result.wall_x, result.wall_y, right=result.y_exit)
    return np.asarray(y) <= wall + 1e-9


def plot_moc(result: MOCResult, *, show_mesh: bool = True) -> Any:
    """Plot the characteristics mesh and the designed wall."""
    _use_style("notebook")
    fig, ax = plt.subplots(figsize=(10, 5))

    if show_mesh:
        n = result.n_char
        kernel = result.kernel
        # C⁻ family of the kernel: from the throat corner down to the axis.
        for i in range(1, n + 1):
            xs = [0.0] + [kernel[(i, j)].x for j in range(i, 0, -1)]
            ys = [result.y_throat] + [kernel[(i, j)].y for j in range(i, 0, -1)]
            ax.plot(xs, ys, color="tab:blue", lw=0.5, alpha=0.55, zorder=1)
        # C⁺ family: reflected off the axis, up to the last kernel line.
        for k in range(1, n + 1):
            xs = [kernel[(k, 1)].x] + [kernel[(i, i - k + 1)].x for i in range(k + 1, n + 1)]
            ys = [kernel[(k, 1)].y] + [kernel[(i, i - k + 1)].y for i in range(k + 1, n + 1)]
            ax.plot(xs, ys, color="tab:red", lw=0.5, alpha=0.55, zorder=1)
        # Straightening region: the C⁺ lines running up to the wall, clipped
        # there — the mesh is marched beyond it by construction.
        for line in result.transition:
            line_x = np.array([p.x for p in line])
            line_y = np.array([p.y for p in line])
            visible = _inside(result, line_x, line_y)
            ax.plot(
                line_x[visible], line_y[visible], color="tab:green", lw=0.4, alpha=0.45, zorder=1
            )

        px = np.array([p.x for p in result.points])
        py = np.array([p.y for p in result.points])
        pm = np.array([p.mach for p in result.points])
        keep = _inside(result, px, py)
        scatter = ax.scatter(
            px[keep], py[keep], s=6, c=pm[keep], cmap="viridis", zorder=3
        )
        bar = fig.colorbar(scatter, ax=ax)
        bar.set_label("Mach local")

    ax.plot(result.wall_x, result.wall_y, "-", color=_WALL, lw=2.2, label="paroi (MOC)")
    ax.axhline(0.0, color="0.5", ls=":", lw=1.0)
    ax.set_xlabel("x   (en unités de y_col)")
    ax.set_ylabel("y   (en unités de y_col)")
    ax.set_title(
        f"Tuyère {result.label} à longueur minimale — MOC | "
        f"Me = {result.mach_exit:.2f}, n = {result.n_char}, "
        f"θ_max = {result.theta_max_deg:.2f}°"
    )
    ax.legend(loc="best", fontsize=9)
    ax.set_aspect("equal", adjustable="datalim")
    _grid(ax)
    fig.tight_layout()
    return fig


def plot_performance_map(
    nozzle: Nozzle,
    p0: float,
    t0: float,
    pa_min: float,
    pa_max: float,
    *,
    n: int = 200,
) -> Any:
    """Thrust, Cf and exit Mach against ambient pressure."""
    _use_style("notebook")
    pressures = np.linspace(pa_min, pa_max, n)
    states = [nozzle.solve(p0, t0, float(pa)) for pa in pressures]
    thrust = np.array([s.thrust for s in states])
    cf = np.array([s.cf for s in states])
    mach = np.array([s.mach_exit for s in states])
    pa_design = p0 / nozzle.critical_ratios().npr_design

    fig, axes = plt.subplots(3, 1, figsize=(8.5, 9), sharex=True)
    axes[0].plot(pressures * 1e-5, thrust * 1e-3, "-", color=_MACH, lw=1.8)
    axes[0].set_ylabel("Poussée [kN]")
    axes[0].set_title(
        f"Carte de performance | p₀ = {p0 * 1e-5:.1f} bar, T₀ = {t0:.0f} K, ε = {nozzle.eps:.1f}"
    )
    axes[1].plot(pressures * 1e-5, cf, "-", color=_PRESSURE, lw=1.8)
    axes[1].set_ylabel("Cf [-]")
    axes[2].plot(pressures * 1e-5, mach, "-", color=_TEMPERATURE, lw=1.8)
    axes[2].set_ylabel("Mach en sortie [-]")
    axes[2].set_xlabel("Pression ambiante [bar]")

    for ax in axes:
        ax.axvline(pa_design * 1e-5, color=_DESIGN, ls="--", lw=1.0)
        _grid(ax)
    # Axes-fraction placement: a data-coordinate y is not safe here, the thrust
    # range never starting at zero — the label used to land off-frame.
    axes[0].annotate(
        "adaptation (pe = pa)",
        (pa_design * 1e-5, 0.55),
        xycoords=("data", "axes fraction"),
        color=_DESIGN,
        rotation=90,
        fontsize=9,
        va="center",
        ha="right",
    )
    fig.tight_layout()
    return fig
