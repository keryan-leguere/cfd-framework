"""Scaling curve plots.

Uses the ``plotting`` library (from ``scripts/post/plot/plotting``) when
importable, falling back to vanilla Matplotlib otherwise.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

from cfd_perf.benchmark.models import PilotSeries
from cfd_perf.mesh.models import MeshStats
from cfd_perf.models.parameters import ModelParameters
from cfd_perf.optimizer.curve import build_scaling_curve
from cfd_perf.optimizer.models import OptimizationResult

try:
    from plotting import (
        add_reference_lines,
        add_textbox,
        annotate_point,
        apply_oldschool_axes,
        make_legend,
        new_figure,
        plot_line,
        save_figure,
        set_suptitle,
        set_title,
        use_style,
    )

    _HAS_PLOTTING = True
except ImportError:
    _HAS_PLOTTING = False

_GREEN = "#009900"
_RED = "#CC0000"
_BLUE = "#0066CC"
_ZONE_ALPHA = 0.18
_PILOT_MARKER_SIZE = 42

_MODE_LABELS = {
    "efficiency": "efficacité",
    "deadline": "deadline",
    "min_runtime": "durée min.",
}


def _format_runtime_mdh(hours: float) -> str:
    """Format runtime as e.g. '2 mois, 15 j, 6.5 h'."""
    total_h = hours
    months = int(total_h // (30 * 24))
    rest = total_h - months * 30 * 24
    days = int(rest // 24)
    h = rest - days * 24
    parts = []
    if months > 0:
        parts.append(f"{months} mois")
    parts.append(f"{days} j")
    parts.append(f"{h:.1f} h")
    return ", ".join(parts)


def _build_full_arrays(
    result: OptimizationResult,
    pilot: PilotSeries,
    mesh: MeshStats,
    params: ModelParameters,
) -> (
    tuple[
        np.ndarray, np.ndarray, np.ndarray, np.ndarray,
        list[int], list[int],
        tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    ]
    | None
):
    """Build the full scaling curve arrays and pilot overlay data."""
    nc0 = pilot.baseline_cores
    t0 = pilot.baseline_time_per_iter_s
    n_iter = pilot.n_iterations

    all_cores = sorted(
        {c.cores for c in result.accepted} | {r.cores for r in result.rejected}
    )
    if not all_cores:
        return None

    step = all_cores[1] - all_cores[0] if len(all_cores) >= 2 else 1
    nc_range = range(min(all_cores), max(all_cores) + 1, step)
    full = build_scaling_curve(nc_range, params, nc0, t0, n_iter, mesh)

    cores_all = np.array([c.cores for c in full])
    runtime_all = np.array([c.runtime_hours for c in full])
    eff_all = np.array([c.efficiency for c in full]) * 100
    rpc_all = np.array([c.ram_per_core_gb for c in full])

    accepted_cores = [c.cores for c in result.accepted]
    rejected_cores = [r.cores for r in result.rejected]

    pilot_nc = np.array([p.cores for p in pilot.points])
    pilot_runtime_h = np.array([p.time_per_iter_s * n_iter / 3600 for p in pilot.points])
    pilot_eff = np.array([
        (t0 * nc0 / (p.time_per_iter_s * p.cores)) * 100 for p in pilot.points
    ])
    pilot_rpc = np.array([p.peak_ram_total_gb / p.cores for p in pilot.points])

    return (
        cores_all, runtime_all, eff_all, rpc_all,
        accepted_cores, rejected_cores,
        (pilot_nc, pilot_runtime_h, pilot_eff, pilot_rpc),
    )


def _hline_label(ax: plt.Axes, y_val: float, label: str, x_max: float) -> None:
    ax.axhline(y=y_val, color="C2", linewidth=0.9, linestyle=":", zorder=2)
    ax.text(
        x_max * 0.97, y_val, f"  {label}",
        ha="right", va="bottom", fontsize=10, color="black", fontweight="bold", zorder=3,
    )


def _compute_zones(
    result: OptimizationResult,
    accepted_cores: list[int],
    rejected_cores: list[int],
    x_max: float,
) -> tuple[tuple[float, float], tuple[float, float], float]:
    """Return (green_span, red_span, boundary) for the zone overlay."""
    if result.mode == "efficiency":
        boundary = max(accepted_cores) if accepted_cores else (min(rejected_cores) if rejected_cores else 0)
        return (0, boundary), (boundary, x_max), float(boundary)
    elif result.mode == "deadline":
        boundary = min(accepted_cores) if accepted_cores else (max(rejected_cores) if rejected_cores else x_max)
        return (boundary, x_max), (0, boundary), float(boundary)
    else:
        green_span = (0.0, x_max)
        red_span = (0.0, 0.0)
        boundary = 0.0
        if rejected_cores:
            boundary = max(accepted_cores) if accepted_cores else (min(rejected_cores) if rejected_cores else 0)
            green_span = (0, boundary)
            red_span = (boundary, x_max)
        return green_span, red_span, boundary


def _textbox_content(meta: dict) -> str:
    """Build the metadata text for the runtime panel textbox."""
    model_kind = meta.get("model_kind", "beta")
    lines = [
        f"Mailles : {meta.get('num_cells', 0) / 1e6:.0f}M",
        f"Itér. : {meta.get('n_iterations', 0):,}",
        f"Modèle : {model_kind}",
    ]
    if model_kind == "beta":
        lines.append(f"β : {meta.get('beta', '?')}")
    return "\n".join(lines)


def _plot_with_plotting_lib(
    result: OptimizationResult,
    pilot: PilotSeries,
    mesh: MeshStats,
    params: ModelParameters,
    out: Path | None,
    *,
    title_suffix: str = "",
    show: bool = False,
    return_figure: bool = False,
) -> Path | None | tuple[plt.Figure, np.ndarray]:
    """Render using the ``plotting`` package (professional style)."""
    use_style("paper")

    arrays = _build_full_arrays(result, pilot, mesh, params)
    if arrays is None:
        if show:
            plt.show()
        return out

    cores_all, runtime_all, eff_all, rpc_all, accepted_cores, rejected_cores, pilot_data = arrays
    pilot_nc, pilot_runtime_h, pilot_eff, pilot_rpc = pilot_data

    fig, axes = new_figure(1, 3, figsize=(16, 4.8), constrained_layout=False)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.82, bottom=0.14, wspace=0.12)
    mode_label = _MODE_LABELS.get(result.mode, result.mode)
    set_suptitle(fig, f"Analyse de scalabilité forte  (mode {mode_label}){title_suffix}", fontsize=12)

    nc_opt = result.optimal.cores if result.optimal else None
    opt = result.optimal
    mrc = result.min_runtime_candidate
    meta = result.metadata
    x_max = float(cores_all.max()) * 1.05

    target_eff_pct = (1.0 - meta["max_efficiency_loss"]) * 100 if "max_efficiency_loss" in meta else None
    target_deadline_h = meta.get("deadline_hours")

    green_span, red_span, boundary = _compute_zones(result, accepted_cores, rejected_cores, x_max)

    def draw_zones(ax: plt.Axes) -> None:
        ax.axvspan(*green_span, alpha=_ZONE_ALPHA, color=_GREEN, zorder=0, label="Accepté")
        if red_span[1] > red_span[0]:
            ax.axvspan(*red_span, alpha=_ZONE_ALPHA, color=_RED, zorder=0, label="Rejeté")
        if boundary > 0:
            ax.axvline(x=boundary, color="0.15", linewidth=1.8, linestyle="-", zorder=1)

    # Interpolated target intersection
    if result.mode == "efficiency" and target_eff_pct is not None:
        nc_at_target = np.interp(target_eff_pct, eff_all[::-1], cores_all[::-1].astype(float))
        h_eff = target_eff_pct
        h_runtime = float(np.interp(nc_at_target, cores_all, runtime_all))
        h_ram = float(np.interp(nc_at_target, cores_all, rpc_all))
        lbl_eff = f"cible : {target_eff_pct:.0f} %"
        lbl_rt = f"cible : {_format_runtime_mdh(h_runtime)}"
        lbl_ram = f"{h_ram:.1f} Go"
    elif result.mode == "deadline" and target_deadline_h is not None:
        nc_at_target = np.interp(target_deadline_h, runtime_all[::-1], cores_all[::-1].astype(float))
        h_runtime = target_deadline_h
        h_eff = float(np.interp(nc_at_target, cores_all, eff_all))
        h_ram = float(np.interp(nc_at_target, cores_all, rpc_all))
        lbl_rt = f"cible : {_format_runtime_mdh(target_deadline_h)}"
        lbl_eff = f"{h_eff:.1f} %"
        lbl_ram = f"{h_ram:.1f} Go"
    else:
        h_runtime = h_eff = h_ram = None
        lbl_rt = lbl_eff = lbl_ram = ""

    # --- Runtime ---
    ax = axes[0]
    set_title(ax, "Durée totale")
    ax.set_xlim(0, x_max)
    draw_zones(ax)
    plot_line(ax, cores_all, runtime_all, marker="o", label="Prédit", markersize=4)
    ax.scatter(
        pilot_nc, pilot_runtime_h, marker="D", s=_PILOT_MARKER_SIZE, color="C4",
        edgecolors="black", linewidths=0.8, zorder=5, label="Pilote",
    )
    if opt:
        add_reference_lines(ax, vlines=[nc_opt], color="C2", linewidth=1.0, linestyle="--")
        annotate_point(
            ax, f"opt : {nc_opt} cœurs\n{_format_runtime_mdh(opt.runtime_hours)}",
            xy=(nc_opt, opt.runtime_hours), offset=(40, 25),
        )
    if mrc is not None and (opt is None or mrc.cores != opt.cores):
        add_reference_lines(ax, vlines=[mrc.cores], color=_BLUE, linewidth=1.0, linestyle="--")
        annotate_point(
            ax, f"min : {mrc.cores} cœurs\n{_format_runtime_mdh(mrc.runtime_hours)}",
            xy=(mrc.cores, mrc.runtime_hours), offset=(-60, -30),
        )
    if h_runtime is not None:
        _hline_label(ax, h_runtime, lbl_rt, x_max)
    ax.set_xlabel("Cœurs")
    ax.set_ylabel("Durée totale (h)")
    add_textbox(ax, _textbox_content(meta), loc="center right", fontsize=7)
    apply_oldschool_axes(ax, legend=False)
    make_legend(ax, loc="upper right", fontsize=7, title="Légende")

    # --- Efficiency ---
    ax = axes[1]
    set_title(ax, "Efficacité parallèle")
    ax.set_xlim(0, x_max)
    draw_zones(ax)
    plot_line(ax, cores_all, eff_all, marker="s", label="Efficacité", markersize=4)
    ax.scatter(
        pilot_nc, pilot_eff, marker="D", s=_PILOT_MARKER_SIZE, color="C4",
        edgecolors="black", linewidths=0.8, zorder=5, label="Pilote",
    )
    if opt:
        add_reference_lines(ax, vlines=[nc_opt], color="C2", linewidth=1.0, linestyle="--")
        annotate_point(
            ax, f"opt : {nc_opt} cœurs\n{opt.efficiency * 100:.1f} %",
            xy=(nc_opt, opt.efficiency * 100), offset=(40, 25),
        )
    if mrc is not None and (opt is None or mrc.cores != opt.cores):
        add_reference_lines(ax, vlines=[mrc.cores], color=_BLUE, linewidth=1.0, linestyle="--")
        annotate_point(
            ax, f"min : {mrc.cores} cœurs\n{mrc.efficiency * 100:.1f} %",
            xy=(mrc.cores, mrc.efficiency * 100), offset=(-60, -30),
        )
    if h_eff is not None:
        _hline_label(ax, h_eff, lbl_eff, x_max)
    ax.set_xlabel("Cœurs")
    ax.set_ylabel("Efficacité parallèle (%)")
    ax.set_ylim(0, 105)
    ax.yaxis.set_major_locator(mticker.MultipleLocator(10))
    ax.yaxis.set_minor_locator(mticker.MultipleLocator(5))
    apply_oldschool_axes(ax, legend=False)
    make_legend(ax, loc="upper right", fontsize=7, title="Légende")

    # --- Memory / core ---
    ax = axes[2]
    set_title(ax, "RAM par cœur")
    ax.set_xlim(0, x_max)
    draw_zones(ax)
    plot_line(ax, cores_all, rpc_all, marker="^", label="RAM / Cœur", markersize=4)
    ax.scatter(
        pilot_nc, pilot_rpc, marker="D", s=_PILOT_MARKER_SIZE, color="C4",
        edgecolors="black", linewidths=0.8, zorder=5, label="Pilote",
    )
    if opt:
        add_reference_lines(ax, vlines=[nc_opt], color="C2", linewidth=1.0, linestyle="--")
        annotate_point(
            ax, f"opt : {nc_opt} cœurs\n{opt.ram_per_core_gb:.1f} Go",
            xy=(nc_opt, opt.ram_per_core_gb), offset=(40, 25),
        )
    if mrc is not None and (opt is None or mrc.cores != opt.cores):
        add_reference_lines(ax, vlines=[mrc.cores], color=_BLUE, linewidth=1.0, linestyle="--")
        annotate_point(
            ax, f"min : {mrc.cores} cœurs\n{mrc.ram_per_core_gb:.1f} Go",
            xy=(mrc.cores, mrc.ram_per_core_gb), offset=(-60, -30),
        )
    if h_ram is not None:
        _hline_label(ax, h_ram, lbl_ram, x_max)
    ax.set_xlabel("Cœurs")
    ax.set_ylabel("RAM par cœur (Go)")
    apply_oldschool_axes(ax, legend=False)
    make_legend(ax, loc="upper right", fontsize=7, title="Légende")

    if return_figure:
        if show:
            plt.show()
        return (fig, axes)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        save_figure(fig, str(out.with_suffix("")), formats=("png",), dpi=180, report=False)
    if show:
        plt.show()
    else:
        plt.close(fig)
    return out


def _plot_vanilla(
    result: OptimizationResult,
    pilot: PilotSeries,
    mesh: MeshStats,
    params: ModelParameters,
    out: Path | None,
    *,
    title_suffix: str = "",
    show: bool = False,
    return_figure: bool = False,
) -> Path | None | tuple[plt.Figure, np.ndarray]:
    """Fallback renderer using vanilla Matplotlib."""
    arrays = _build_full_arrays(result, pilot, mesh, params)
    if arrays is None:
        if show:
            plt.show()
        return out

    cores_all, runtime_all, eff_all, rpc_all, accepted_cores, rejected_cores, pilot_data = arrays
    pilot_nc, pilot_runtime_h, pilot_eff, pilot_rpc = pilot_data

    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), constrained_layout=False)
    fig.subplots_adjust(left=0.06, right=0.98, top=0.82, bottom=0.14, wspace=0.12)
    mode_label = _MODE_LABELS.get(result.mode, result.mode)
    fig.suptitle(
        f"Analyse strong-scaling  (mode {mode_label}){title_suffix}",
        fontsize=12, fontweight="bold",
    )

    nc_opt = result.optimal.cores if result.optimal else None
    opt = result.optimal
    mrc = result.min_runtime_candidate
    meta = result.metadata
    x_max = float(cores_all.max()) * 1.05

    target_eff_pct = (1.0 - meta["max_efficiency_loss"]) * 100 if "max_efficiency_loss" in meta else None
    target_deadline_h = meta.get("deadline_hours")

    green_span, red_span, boundary = _compute_zones(result, accepted_cores, rejected_cores, x_max)

    def draw_zones(ax: plt.Axes) -> None:
        ax.axvspan(*green_span, alpha=_ZONE_ALPHA, color=_GREEN, zorder=0, label="Accepté")
        if red_span[1] > red_span[0]:
            ax.axvspan(*red_span, alpha=_ZONE_ALPHA, color=_RED, zorder=0, label="Rejeté")
        if boundary > 0:
            ax.axvline(x=boundary, color="0.15", linewidth=1.8, linestyle="-", zorder=1)

    if result.mode == "efficiency" and target_eff_pct is not None:
        nc_at_target = np.interp(target_eff_pct, eff_all[::-1], cores_all[::-1].astype(float))
        h_eff = target_eff_pct
        h_runtime = float(np.interp(nc_at_target, cores_all, runtime_all))
        h_ram = float(np.interp(nc_at_target, cores_all, rpc_all))
        lbl_eff = f"cible : {target_eff_pct:.0f} %"
        lbl_rt = f"cible : {_format_runtime_mdh(h_runtime)}"
        lbl_ram = f"{h_ram:.1f} Go"
    elif result.mode == "deadline" and target_deadline_h is not None:
        nc_at_target = np.interp(target_deadline_h, runtime_all[::-1], cores_all[::-1].astype(float))
        h_runtime = target_deadline_h
        h_eff = float(np.interp(nc_at_target, cores_all, eff_all))
        h_ram = float(np.interp(nc_at_target, cores_all, rpc_all))
        lbl_rt = f"cible : {_format_runtime_mdh(target_deadline_h)}"
        lbl_eff = f"{h_eff:.1f} %"
        lbl_ram = f"{h_ram:.1f} Go"
    else:
        h_runtime = h_eff = h_ram = None
        lbl_rt = lbl_eff = lbl_ram = ""

    # --- Runtime ---
    ax_rt = axes[0]
    ax_rt.set_title("Durée totale")
    ax_rt.set_xlim(0, x_max)
    draw_zones(ax_rt)
    ax_rt.plot(cores_all, runtime_all, "o-", color="C0", markersize=4, label="Prédit")
    ax_rt.scatter(
        pilot_nc, pilot_runtime_h, marker="D", s=_PILOT_MARKER_SIZE, color="C4",
        edgecolors="black", linewidths=0.8, zorder=5, label="Pilote",
    )
    if opt:
        ax_rt.axvline(nc_opt, color="C2", linestyle="--", linewidth=0.9)
        ax_rt.annotate(
            f"opt : {nc_opt} cœurs\n{_format_runtime_mdh(opt.runtime_hours)}",
            xy=(nc_opt, opt.runtime_hours), xytext=(40, 25),
            textcoords="offset points", fontsize=7,
            arrowprops={"arrowstyle": "->", "color": "0.4"},
        )
    if mrc is not None and (opt is None or mrc.cores != opt.cores):
        ax_rt.axvline(mrc.cores, color=_BLUE, linestyle="--", linewidth=0.9)
        ax_rt.annotate(
            f"min : {mrc.cores} cœurs\n{_format_runtime_mdh(mrc.runtime_hours)}",
            xy=(mrc.cores, mrc.runtime_hours), xytext=(-60, -30),
            textcoords="offset points", fontsize=7,
            arrowprops={"arrowstyle": "->", "color": _BLUE},
        )
    if h_runtime is not None:
        _hline_label(ax_rt, h_runtime, lbl_rt, x_max)
    ax_rt.set_xlabel("Cœurs")
    ax_rt.set_ylabel("Durée totale (h)")
    ax_rt.text(
        0.96, 0.5, _textbox_content(meta),
        transform=ax_rt.transAxes, ha="right", va="center",
        fontsize=7, bbox={"boxstyle": "round,pad=0.4", "fc": "wheat", "alpha": 0.5},
    )
    ax_rt.legend(fontsize=7, loc="upper right", title="Légende")

    # --- Efficiency ---
    ax_eff = axes[1]
    ax_eff.set_title("Efficacité parallèle")
    ax_eff.set_xlim(0, x_max)
    draw_zones(ax_eff)
    ax_eff.plot(cores_all, eff_all, "s-", color="C1", markersize=4, label="Efficacité")
    ax_eff.scatter(
        pilot_nc, pilot_eff, marker="D", s=_PILOT_MARKER_SIZE, color="C4",
        edgecolors="black", linewidths=0.8, zorder=5, label="Pilote",
    )
    if opt:
        ax_eff.axvline(nc_opt, color="C2", linestyle="--", linewidth=0.9)
        ax_eff.annotate(
            f"opt : {nc_opt} cœurs\n{opt.efficiency * 100:.1f} %",
            xy=(nc_opt, opt.efficiency * 100), xytext=(40, 25),
            textcoords="offset points", fontsize=7,
            arrowprops={"arrowstyle": "->", "color": "0.4"},
        )
    if mrc is not None and (opt is None or mrc.cores != opt.cores):
        ax_eff.axvline(mrc.cores, color=_BLUE, linestyle="--", linewidth=0.9)
        ax_eff.annotate(
            f"min : {mrc.cores} cœurs\n{mrc.efficiency * 100:.1f} %",
            xy=(mrc.cores, mrc.efficiency * 100), xytext=(-60, -30),
            textcoords="offset points", fontsize=7,
            arrowprops={"arrowstyle": "->", "color": _BLUE},
        )
    if h_eff is not None:
        _hline_label(ax_eff, h_eff, lbl_eff, x_max)
    ax_eff.set_xlabel("Cœurs")
    ax_eff.set_ylabel("Efficacité parallèle (%)")
    ax_eff.set_ylim(0, 105)
    ax_eff.yaxis.set_major_locator(mticker.MultipleLocator(10))
    ax_eff.yaxis.set_minor_locator(mticker.MultipleLocator(5))
    ax_eff.legend(fontsize=7, loc="upper right", title="Légende")

    # --- Memory / core ---
    ax_mem = axes[2]
    ax_mem.set_title("RAM par cœur")
    ax_mem.set_xlim(0, x_max)
    draw_zones(ax_mem)
    ax_mem.plot(cores_all, rpc_all, "^-", color="C3", markersize=4, label="RAM / Cœur")
    ax_mem.scatter(
        pilot_nc, pilot_rpc, marker="D", s=_PILOT_MARKER_SIZE, color="C4",
        edgecolors="black", linewidths=0.8, zorder=5, label="Pilote",
    )
    if opt:
        ax_mem.axvline(nc_opt, color="C2", linestyle="--", linewidth=0.9)
        ax_mem.annotate(
            f"opt : {nc_opt} cœurs\n{opt.ram_per_core_gb:.1f} Go",
            xy=(nc_opt, opt.ram_per_core_gb), xytext=(40, 25),
            textcoords="offset points", fontsize=7,
            arrowprops={"arrowstyle": "->", "color": "0.4"},
        )
    if mrc is not None and (opt is None or mrc.cores != opt.cores):
        ax_mem.axvline(mrc.cores, color=_BLUE, linestyle="--", linewidth=0.9)
        ax_mem.annotate(
            f"min : {mrc.cores} cœurs\n{mrc.ram_per_core_gb:.1f} Go",
            xy=(mrc.cores, mrc.ram_per_core_gb), xytext=(-60, -30),
            textcoords="offset points", fontsize=7,
            arrowprops={"arrowstyle": "->", "color": _BLUE},
        )
    if h_ram is not None:
        _hline_label(ax_mem, h_ram, lbl_ram, x_max)
    ax_mem.set_xlabel("Cœurs")
    ax_mem.set_ylabel("RAM par cœur (Go)")
    ax_mem.legend(fontsize=7, loc="upper right", title="Légende")

    if return_figure:
        if show:
            plt.show()
        return (fig, axes)
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, dpi=150)
    if show:
        plt.show()
    else:
        plt.close(fig)
    return out


def plot_scaling(
    result: OptimizationResult,
    out: Path | None = None,
    *,
    pilot: PilotSeries | None = None,
    mesh: MeshStats | None = None,
    params: ModelParameters | None = None,
    title_suffix: str = "",
    show: bool = False,
    return_figure: bool = False,
) -> Path | None | tuple[plt.Figure, np.ndarray]:
    """Generate a 3-panel scaling figure: runtime, efficiency, memory/core.

    When *pilot*, *mesh*, and *params* are provided the figure includes the
    full scaling curve (accepted + rejected), coloured accepted/rejected
    zones, interpolated target lines, and pilot-data overlay.

    Set *show* to ``True`` for inline display in notebooks (calls
    ``plt.show()`` instead of closing the figure).

    Set *return_figure* to ``True`` to return ``(fig, axes)`` instead of
    saving to *out*; the caller can then save with custom formats (e.g. SVG).

    Falls back to a minimal accepted-only plot when these are ``None``.
    """
    if not result.accepted and not result.rejected:
        return None

    output = out

    if pilot is not None and mesh is not None and params is not None:
        if _HAS_PLOTTING:
            return _plot_with_plotting_lib(
                result, pilot, mesh, params, output,
                title_suffix=title_suffix, show=show, return_figure=return_figure,
            )
        return _plot_vanilla(
            result, pilot, mesh, params, output,
            title_suffix=title_suffix, show=show, return_figure=return_figure,
        )

    # Legacy path: no pilot/mesh/params -> simple accepted-only plot
    from cfd_perf.models.parameters import ModelParameters as _MP

    _dummy_pilot = PilotSeries(
        points=tuple(
            __import__("cfd_perf.benchmark.models", fromlist=["PilotPoint"]).PilotPoint(
                cores=result.accepted[0].cores,
                time_per_iter_s=result.accepted[0].time_per_iter_s,
                peak_ram_total_gb=result.accepted[0].ram_total_gb,
            )
            for _ in [0]
        ),
        n_iterations=int(result.metadata.get("n_iterations", 5000)),
    )
    _dummy_mesh = MeshStats(
        num_cells=int(result.metadata.get("num_cells", 1_000_000)),
        num_faces=int(result.metadata.get("num_cells", 1_000_000)) * 3,
        estimated_mem_per_cell_bytes=None,
    )
    _dummy_params = _MP(
        beta=float(result.metadata.get("beta", 0.25)),
        beta_source=str(result.metadata.get("beta_source", "fixed")),
    )
    if _HAS_PLOTTING:
        return _plot_with_plotting_lib(
            result, _dummy_pilot, _dummy_mesh, _dummy_params, output,
            show=show, return_figure=return_figure,
        )
    return _plot_vanilla(
        result, _dummy_pilot, _dummy_mesh, _dummy_params, output,
        show=show, return_figure=return_figure,
    )
