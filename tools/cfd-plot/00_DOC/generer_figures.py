#!/usr/bin/env python3
"""Regenerate the illustrations used by the cfd-plot README.

    python3 00_DOC/generer_figures.py

Writes PNGs into ``00_DOC/FIGURES/``. Every figure here corresponds to one
section of the README, so a feature and its picture stay in sync: if you add a
helper to the public API, add a panel here too.

The figures are versioned in the repository — this script only exists to
rebuild them when the library changes.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

from cfd_plot._compat import zip_strict

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from cfd_plot import (
    PALETTES,
    FoldSpec,
    add_reference_lines,
    add_shared_colorbar,
    add_textbox,
    animate_sweep,
    annotate_point,
    apply_oldschool_axes,
    batch_compare_flight_points,
    batch_plot,
    compute_speed,
    contact_sheet,
    dataframe_to_grid,
    discover_flight_point_values,
    dual_axis,
    extract_slice2d,
    fill_between_curves,
    interpolate_field2d,
    make_figure_legend,
    make_legend,
    mask_field,
    new_figure,
    palette_colors,
    panel_labels,
    pdf_report,
    plot_bar,
    plot_contour,
    plot_contour_quiver,
    plot_contourf,
    plot_imshow,
    plot_line,
    plot_pcolormesh,
    plot_quiver,
    plot_streamplot,
    plot_with_band,
    save_figure,
    set_axis_sci,
    set_subtitle,
    set_suptitle,
    set_title,
    style_context,
    subsample_vectors,
    sync_axes_limits,
    use_style,
)

ICI = Path(__file__).resolve().parent
FIGURES = ICI / "FIGURES"
DPI = 110

SEED = 12345


def _write(fig, name: str) -> None:
    save_figure(fig, FIGURES / name, formats=("png",), dpi=DPI)
    plt.close(fig)
    print(f"  {name}.png")


# ---------------------------------------------------------------------------
# Shared synthetic data — a small "airfoil-like" set of CFD-flavoured samples
# ---------------------------------------------------------------------------

def _polar():
    """Alpha sweep with two turbulence models and an experimental reference."""
    alpha = np.linspace(-4, 16, 21)
    cn_sa = 0.11 * alpha + 0.004 * alpha**2
    cn_kw = 0.108 * alpha + 0.0035 * alpha**2
    # A generator local to the call, not a module-level one: with a shared
    # stream the noise depends on how many figures ran before this one, so
    # inserting a new figure silently churns every later PNG in the repo.
    cn_exp = cn_sa + np.random.default_rng(SEED).normal(0, 0.02, alpha.size)
    return alpha, cn_sa, cn_kw, cn_exp


def _field2d(nx: int = 60, ny: int = 45):
    """A smooth scalar field + its velocity field on a structured grid."""
    x = np.linspace(-2.0, 2.0, nx)
    y = np.linspace(-1.5, 1.5, ny)
    X, Y = np.meshgrid(x, y)
    z = np.exp(-(X**2 + Y**2)) * np.cos(2.5 * X) + 0.25 * Y
    u = -Y * np.exp(-0.3 * (X**2 + Y**2))
    v = X * np.exp(-0.3 * (X**2 + Y**2))
    return x, y, X, Y, z, u, v


# ---------------------------------------------------------------------------
# 01 — style profiles
# ---------------------------------------------------------------------------

def fig_styles() -> None:
    alpha, cn_sa, cn_kw, _ = _polar()
    for profile in ("notebook", "slides", "paper"):
        with style_context(profile):
            fig, ax = plt.subplots(figsize=(5.2, 3.4))
            plot_line(ax, alpha, cn_sa, label="SA")
            plot_line(ax, alpha, cn_kw, marker="s", label=r"$k$-$\omega$ SST")
            ax.set_xlabel(r"$\alpha$ [deg]")
            ax.set_ylabel(r"$C_N$ [-]")
            set_title(ax, f'style_context("{profile}")')
            make_legend(ax)
            _write(fig, f"01_style_{profile}")


# ---------------------------------------------------------------------------
# 02 — 1D helpers: plot_line / plot_with_band / plot_bar
# ---------------------------------------------------------------------------

def fig_line_helpers() -> None:
    use_style("notebook")
    alpha, cn_sa, cn_kw, cn_exp = _polar()

    fig, axes = new_figure(1, 3, figsize=(15, 4.2))

    plot_line(axes[0], alpha, cn_sa, label="SA")
    plot_line(axes[0], alpha, cn_kw, marker="s", label=r"$k$-$\omega$ SST")
    plot_line(axes[0], alpha, cn_exp, marker="^", ls="none", label="Experiment")
    axes[0].set_xlabel(r"$\alpha$ [deg]")
    axes[0].set_ylabel(r"$C_N$ [-]")
    set_title(axes[0], "plot_line")
    make_legend(axes[0])

    band = 0.05 + 0.01 * np.abs(alpha)
    plot_with_band(
        axes[1], alpha, cn_sa,
        y_low=cn_sa - band, y_high=cn_sa + band,
        label="SA", band_label=r"$\pm\,2\sigma$",
    )
    axes[1].set_xlabel(r"$\alpha$ [deg]")
    axes[1].set_ylabel(r"$C_N$ [-]")
    set_title(axes[1], "plot_with_band")
    make_legend(axes[1])

    plot_bar(
        axes[2],
        ["SA", "k-ω SST", "k-ε", "EXP"],
        [0.482, 0.474, 0.455, 0.489],
        color="C0",
    )
    axes[2].set_ylabel(r"$C_N$ at $\alpha=4°$ [-]")
    set_title(axes[2], "plot_bar")

    _write(fig, "02_1d_helpers")


# ---------------------------------------------------------------------------
# 02b — filling between two curves
# ---------------------------------------------------------------------------

def fig_fill_between() -> None:
    """The three modes, on the same pair of curves so they compare directly."""
    use_style("notebook")
    alpha, cn_sa, cn_kw, _ = _polar()
    delta = cn_sa - cn_kw

    fig, axes = new_figure(1, 3, figsize=(15, 4.2))

    fill_between_curves(axes[0], alpha, cn_sa, cn_kw, label="gap")
    axes[0].set_ylabel(r"$C_N$ [-]")
    set_title(axes[0], "two curves")
    make_legend(axes[0])

    fill_between_curves(axes[1], alpha, delta, label=r"$\Delta C_N$")
    add_reference_lines(axes[1], hlines=[0.0])
    axes[1].set_ylabel(r"$\Delta C_N$ [-]")
    set_title(axes[1], "down to the zero baseline")
    make_legend(axes[1])

    fill_between_curves(
        axes[2], alpha, delta, signed=True,
        signed_labels=("SA above", "SA below"),
    )
    add_reference_lines(axes[2], hlines=[0.0])
    axes[2].set_ylabel(r"$\Delta C_N$ [-]")
    set_title(axes[2], "signed=True")
    make_legend(axes[2], loc="upper left")

    for ax in axes:
        ax.set_xlabel(r"$\alpha$ [deg]")

    _write(fig, "02b_fill_between")


# ---------------------------------------------------------------------------
# 03 — annotations
# ---------------------------------------------------------------------------

def fig_annotations() -> None:
    use_style("notebook")
    alpha, cn_sa, _, _ = _polar()

    fig, ax = new_figure(figsize=(8.5, 5.0))
    plot_line(ax, alpha, cn_sa, label="SA")
    ax.set_xlabel(r"$\alpha$ [deg]")
    ax.set_ylabel(r"$C_N$ [-]")

    set_title(ax, "set_title — normal force polar")
    set_subtitle(ax, "set_subtitle — M = 0.7, Re = 6e6")
    add_reference_lines(ax, hlines=[0.0], vlines=[0.0])
    add_textbox(ax, "add_textbox\nmesh: 20 M cells\nsolver: foamRun", loc="upper left")

    i = 16
    annotate_point(ax, "annotate_point\nstall onset", (alpha[i], cn_sa[i]), offset=(-90, 30))
    make_legend(ax)

    _write(fig, "03_annotations")


# ---------------------------------------------------------------------------
# 04 — axes helpers: dual_axis / set_axis_sci / sync_axes_limits
# ---------------------------------------------------------------------------

def fig_axes_helpers() -> None:
    use_style("notebook")
    alpha, cn_sa, _, _ = _polar()
    cd = 0.012 + 0.0009 * alpha**2

    fig, axes = new_figure(1, 3, figsize=(15, 4.2))

    plot_line(axes[0], alpha, cn_sa, label=r"$C_N$")
    axes[0].set_xlabel(r"$\alpha$ [deg]")
    axes[0].set_ylabel(r"$C_N$ [-]")
    ax_r = dual_axis(axes[0], ylabel=r"$C_D$ [-]", color="C3")
    plot_line(ax_r, alpha, cd, marker="s", color="C3", label=r"$C_D$")
    set_title(axes[0], "dual_axis")

    residual = 1e-4 * np.exp(-0.35 * np.arange(40)) + 1e-9
    plot_line(axes[1], np.arange(40), residual, marker="")
    axes[1].set_xlabel("Iteration")
    axes[1].set_ylabel(r"$\|R\|$")
    set_axis_sci(axes[1], axis="y")
    set_title(axes[1], "set_axis_sci")

    plot_line(axes[2], alpha, cn_sa, label=r"$C_N$")
    axes[2].set_xlabel(r"$\alpha$ [deg]")
    axes[2].set_ylabel(r"$C_N$ [-]")
    apply_oldschool_axes(axes[2])
    set_title(axes[2], "apply_oldschool_axes")

    _write(fig, "04_axes_helpers")


# ---------------------------------------------------------------------------
# 04b — sync_axes_limits, before / after, across artist types
# ---------------------------------------------------------------------------

def fig_sync_axes_limits() -> None:
    use_style("notebook")
    alpha = np.linspace(-4, 16, 21)

    def _fill(row):
        """Same three panels twice: a curve, a scatter and a bar chart."""
        plot_line(row[0], alpha, 0.11 * alpha, label="SA")
        row[0].set_ylabel(r"$C_N$ [-]")
        row[1].scatter(alpha, 0.55 * alpha, s=18, color="C1", label="probe")
        row[2].bar(["M 0.7", "M 0.8", "M 0.85"], [0.9, 1.4, 1.75], color="C2", edgecolor="0.15")
        row[0].set_xlabel(r"$\alpha$ [deg]")
        row[1].set_xlabel(r"$\alpha$ [deg]")
        row[2].set_xlabel("Flight point")

    fig, axes = new_figure(2, 3, figsize=(15, 7.4))
    _fill(axes[0])
    _fill(axes[1])

    for ax, name in zip_strict(axes[0], ("plot_line", "scatter", "bar")):
        set_title(ax, f"{name} — before")
    sync_axes_limits(axes[1], which="y")
    for ax, name in zip_strict(axes[1], ("plot_line", "scatter", "bar")):
        set_title(ax, f"{name} — after sync_axes_limits")

    set_suptitle(
        fig,
        "sync_axes_limits — curves, scatters and bars are all scanned, "
        "so the three panels become directly comparable",
    )
    _write(fig, "04b_sync_axes_limits")


# ---------------------------------------------------------------------------
# 05 — legends: per-axes vs figure-level
# ---------------------------------------------------------------------------

def fig_legends() -> None:
    use_style("notebook")
    alpha, cn_sa, cn_kw, cn_exp = _polar()

    fig, axes = new_figure(1, 2, figsize=(12, 4.2))
    for ax, title in zip_strict(axes, ("Z = 5000 m", "Z = 10000 m")):
        plot_line(ax, alpha, cn_sa, label="SA")
        plot_line(ax, alpha, cn_kw, marker="s", label=r"$k$-$\omega$ SST")
        plot_line(ax, alpha, cn_exp, marker="^", ls="none", label="Experiment")
        ax.set_xlabel(r"$\alpha$ [deg]")
        ax.set_ylabel(r"$C_N$ [-]")
        set_title(ax, title)
    set_suptitle(fig, "make_figure_legend — one deduplicated legend for the whole figure")
    make_figure_legend(fig, axes, loc="center right", bbox_to_anchor=(1.13, 0.5))

    _write(fig, "05_legends")


# ---------------------------------------------------------------------------
# 06 — 2D scalar fields
# ---------------------------------------------------------------------------

def fig_field2d() -> None:
    use_style("notebook")
    x, y, _, _, z, _, _ = _field2d()

    fig, axes = new_figure(2, 2, figsize=(12, 8))
    flat = axes.ravel()

    plot_contour(flat[0], x, y, z, levels=14, colors="k", colorbar=False)
    set_title(flat[0], "plot_contour")

    plot_contourf(flat[1], x, y, z, levels=20, cmap="viridis", cbar_label=r"$C_p$ [-]")
    set_title(flat[1], "plot_contourf")

    plot_pcolormesh(flat[2], x, y, z, cmap="RdBu_r", cbar_label=r"$C_p$ [-]")
    set_title(flat[2], "plot_pcolormesh")

    plot_imshow(flat[3], z, extent=(x[0], x[-1], y[0], y[-1]), cmap="magma", cbar_label=r"$C_p$ [-]")
    set_title(flat[3], "plot_imshow")

    for ax in flat:
        ax.set_xlabel("x/c [-]")
        ax.set_ylabel("y/c [-]")
    set_suptitle(fig, "2D scalar field — the four renderers")

    _write(fig, "06_field2d")


# ---------------------------------------------------------------------------
# 07 — interpolation
# ---------------------------------------------------------------------------

def fig_interpolation() -> None:
    use_style("notebook")
    x = np.linspace(-2.0, 2.0, 16)
    y = np.linspace(-1.5, 1.5, 12)
    X, Y = np.meshgrid(x, y)
    z = np.exp(-(X**2 + Y**2)) * np.cos(2.5 * X)

    xi, yi, zi = interpolate_field2d(x, y, z, factor=5, method="cubic")

    fig, axes = new_figure(1, 2, figsize=(12, 4.4))
    plot_pcolormesh(axes[0], x, y, z, cmap="viridis", cbar_label=r"$C_p$ [-]")
    set_title(axes[0], f"raw grid — {z.shape[1]}×{z.shape[0]}")
    plot_pcolormesh(axes[1], xi, yi, zi, cmap="viridis", cbar_label=r"$C_p$ [-]")
    set_title(axes[1], f"interpolate_field2d(factor=5) — {zi.shape[1]}×{zi.shape[0]}")
    for ax in axes:
        ax.set_xlabel("x/c [-]")
        ax.set_ylabel("y/c [-]")

    _write(fig, "07_interpolation")


# ---------------------------------------------------------------------------
# 08 — masking
# ---------------------------------------------------------------------------

def fig_masking() -> None:
    use_style("notebook")
    x, y, X, Y, z, _, _ = _field2d()

    inside = (X**2 / 1.1**2 + Y**2 / 0.45**2) < 1.0
    z_masked = mask_field(z, inside)

    fig, axes = new_figure(1, 2, figsize=(12, 4.4))

    plot_pcolormesh(axes[0], x, y, z_masked, cmap="viridis", bad_color="0.85", cbar_label=r"$C_p$ [-]")
    set_title(axes[0], 'mask_field + bad_color="0.85"')

    plot_contourf(
        axes[1], x, y, z_masked, levels=20, cmap="viridis",
        bad_color="white", mask_outline=inside, mask_outline_color="k",
        mask_outline_width=1.8, cbar_label=r"$C_p$ [-]",
    )
    set_title(axes[1], "mask_outline= — body silhouette drawn")

    for ax in axes:
        ax.set_xlabel("x/c [-]")
        ax.set_ylabel("y/c [-]")

    _write(fig, "08_masking")


# ---------------------------------------------------------------------------
# 09 — vector fields
# ---------------------------------------------------------------------------

def fig_vector2d() -> None:
    use_style("notebook")
    x, y, _, _, _, u, v = _field2d()

    fig, axes = new_figure(1, 3, figsize=(16, 4.4))

    plot_quiver(axes[0], x, y, u, v, stride=4, color="0.2")
    set_title(axes[0], "plot_quiver(stride=4)")

    plot_quiver(axes[1], x, y, u, v, stride=4, magnitude_color=True, cmap="viridis",
                colorbar=True, cbar_label=r"$|U|$ [m/s]")
    set_title(axes[1], "plot_quiver(magnitude_color=True)")

    speed = compute_speed(u, v)
    plot_streamplot(axes[2], x, y, u, v, density=1.4, color=speed, cmap="plasma",
                    colorbar=True, cbar_label=r"$|U|$ [m/s]")
    set_title(axes[2], "plot_streamplot(color=compute_speed(u, v))")

    for ax in axes:
        ax.set_xlabel("x/c [-]")
        ax.set_ylabel("y/c [-]")

    _write(fig, "09_vector2d")


# ---------------------------------------------------------------------------
# 10 — composite + subsample_vectors
# ---------------------------------------------------------------------------

def fig_composite() -> None:
    use_style("notebook")
    x, y, _, _, z, u, v = _field2d()

    fig, axes = new_figure(1, 2, figsize=(12.5, 4.6))

    plot_contour_quiver(
        axes[0], x, y, z, u, v,
        scalar_kind="contourf", levels=20, cmap="viridis",
        quiver_stride=5, quiver_color="k", cbar_label=r"$C_p$ [-]",
    )
    set_title(axes[0], "plot_contour_quiver")

    xs, ys, us, vs = subsample_vectors(x, y, u, v, target=18)
    plot_contourf(axes[1], x, y, z, levels=20, cmap="Blues", cbar_label=r"$C_p$ [-]")
    plot_quiver(axes[1], xs, ys, us, vs, color="k")
    set_title(axes[1], "subsample_vectors(target=18) + plot_quiver")

    for ax in axes:
        ax.set_xlabel("x/c [-]")
        ax.set_ylabel("y/c [-]")

    _write(fig, "10_composite")


# ---------------------------------------------------------------------------
# 11 — shared colorbar
# ---------------------------------------------------------------------------

def fig_shared_colorbar() -> None:
    use_style("notebook")
    x, y, X, Y, _, _, _ = _field2d()

    fig, axes = new_figure(1, 3, figsize=(14, 3.8))
    mappable = None
    for ax, mach in zip_strict(axes, (0.5, 0.7, 0.85)):
        z = np.exp(-(X**2 + Y**2)) * np.cos(2.5 * X) * mach
        # the 2D helpers return (artist, colorbar) — we only want the artist
        mappable, _ = plot_pcolormesh(
            ax, x, y, z, cmap="RdBu_r", colorbar=False, vmin=-0.9, vmax=0.9
        )
        set_title(ax, f"M = {mach}")
        ax.set_xlabel("x/c [-]")
    axes[0].set_ylabel("y/c [-]")
    set_suptitle(fig, "add_shared_colorbar — one scale for all panels")
    add_shared_colorbar(fig, mappable, axes=axes, location="right", label=r"$C_p$ [-]")

    _write(fig, "11_shared_colorbar")


# ---------------------------------------------------------------------------
# 12 — data preparation
# ---------------------------------------------------------------------------

def fig_prep() -> None:
    use_style("notebook")

    # A long-format CSV-like table, the shape post-processing usually produces
    xs = np.linspace(-2.0, 2.0, 40)
    ys = np.linspace(-1.5, 1.5, 30)
    X, Y = np.meshgrid(xs, ys)
    df = pd.DataFrame({
        "x": X.ravel(),
        "y": Y.ravel(),
        "cp": (np.exp(-(X**2 + Y**2)) * np.cos(2.5 * X)).ravel(),
    })

    gx, gy, gz = dataframe_to_grid(df, x="x", y="y", values="cp")

    fig, axes = new_figure(1, 2, figsize=(12, 4.4))
    plot_pcolormesh(axes[0], gx, gy, gz, cmap="viridis", cbar_label=r"$C_p$ [-]")
    set_title(axes[0], "dataframe_to_grid — long CSV → 2D grid")
    axes[0].set_xlabel("x/c [-]")
    axes[0].set_ylabel("y/c [-]")

    # extract_slice2d cuts a 2D plane out of a 3D volume (nx, ny, nz)
    xv = np.linspace(-2.0, 2.0, 40)
    yv = np.linspace(-1.5, 1.5, 30)
    zv = np.linspace(0.0, 1.0, 12)
    XV, YV, ZV = np.meshgrid(xv, yv, zv, indexing="ij")
    volume = np.exp(-(XV**2 + YV**2)) * np.cos(2.5 * XV) * (1.0 + ZV)

    c1, c2, plane = extract_slice2d(volume, axis="z", coord=0.75, x=xv, y=yv, z=zv)
    plot_pcolormesh(axes[1], c1, c2, plane, cmap="plasma", cbar_label=r"$C_p$ [-]")
    set_title(axes[1], "extract_slice2d(axis='z', coord=0.75) — 3D volume → plane")
    axes[1].set_xlabel("x/c [-]")
    axes[1].set_ylabel("y/c [-]")

    _write(fig, "12_prep")


# ---------------------------------------------------------------------------
# 13 — declassified export
# ---------------------------------------------------------------------------

def fig_declassify() -> None:
    use_style("paper")
    alpha, cn_sa, cn_kw, _ = _polar()

    fig, ax = plt.subplots(figsize=(5.5, 3.6))
    plot_line(ax, alpha, cn_sa, label="SA")
    plot_line(ax, alpha, cn_kw, marker="s", label=r"$k$-$\omega$ SST")
    ax.set_xlabel(r"$\alpha$ [deg]")
    ax.set_ylabel(r"$C_N$ [-]")
    set_title(ax, "save_figure(..., declassify='y')")
    make_legend(ax)
    apply_oldschool_axes(ax)

    # Writes 13_declassify.png *and* 13_declassify_declassified.png
    save_figure(fig, FIGURES / "13_declassify", formats=("png",), dpi=DPI, declassify="y")
    plt.close(fig)
    print("  13_declassify.png (+ _declassified)")


# ---------------------------------------------------------------------------
# 19/20 — batch plotting, driven from the E2E CSV fixtures
# ---------------------------------------------------------------------------


def _batch_config():
    """Build the four dictionaries batch_plot consumes, from the test CSVs."""
    data_dir = ICI.parent / "tests" / "E2E_MULTIPLE_PLOTTING"
    sources = {
        "KW": {"name": "KW", "label": r"$k$-$\omega$", "color": "C0", "marker": "o"},
        "SA": {"name": "SA", "label": "SA", "color": "C1", "marker": "s"},
        "EXP": {"name": "REF", "label": "Ref.", "color": "C2", "marker": "^", "linestyle": "--"},
    }
    files = {"KW": "kw.csv", "SA": "sa.csv", "EXP": "exp.csv"}
    configuration_dict = {}
    for key, meta in sources.items():
        entry = dict(meta)
        entry["dir"] = str(data_dir)
        entry["df"] = pd.read_csv(data_dir / files[key])
        configuration_dict[key] = entry

    y_axis_dict = {
        "CN": {"col_name": "CN", "literal_name": "Normal force coefficient",
               "symbol": r"$C_N$", "unit": "-", "y_save_name": "CN"},
    }
    sweep_dict = {
        "alpha": {"col_name": "alpha", "literal_name": "Angle of attack",
                  "symbol": r"$\alpha$", "unit": "°", "x_save_name": "alpha",
                  "polar_prefix": "ALPHA_POLAR", "label": r"$\alpha$", "save_name": "ALPHA"},
    }
    keys = ["Mach", "Altitude_m", "alpha", "beta"]
    labels = {"Mach": "M", "Altitude_m": "Z", "alpha": r"$\alpha$", "beta": r"$\beta$"}
    saves = {"Mach": "M", "Altitude_m": "Z", "alpha": "ALPHA", "beta": "BETA"}
    units = {"Mach": "-", "Altitude_m": "m", "alpha": "°", "beta": "°"}
    discovered = discover_flight_point_values(configuration_dict, keys)
    flight_point_dict = {
        k: {"values": discovered[k], "label": labels[k], "save_name": saves[k], "unit": units[k]}
        for k in keys
    }
    return configuration_dict, y_axis_dict, sweep_dict, flight_point_dict


def fig_animation() -> None:
    """The two shapes of curve animation, as GIFs the README embeds directly.

    Deliberately on the ``readme`` preset: these are checked into the
    repository, so weight matters more than resolution.
    """
    alpha, cn_sa, _, _ = _polar()

    with style_context("notebook"):
        animate_sweep(
            alpha, cn_sa, FIGURES / "21_animation_reveal.gif",
            reveal=True, preset="readme", figsize=(6.4, 4.0),
            xlabel=r"$\alpha$ (°)", ylabel=r"$C_N$ (-)",
            title="animate_sweep(reveal=True)",
        )
    print("  21_animation_reveal.gif")

    # One polar per Mach number, previous ones left faded — the accumulating
    # family plot you would otherwise build by hand, frame by frame.
    mach = np.linspace(0.30, 0.85, 12)
    polars = np.array([(0.11 + 0.09 * (m - 0.3)) * alpha + 0.004 * alpha**2 for m in mach])

    with style_context("notebook"):
        animate_sweep(
            alpha, polars, FIGURES / "21b_animation_sweep.gif",
            labels=[f"M = {m:.2f}" for m in mach],
            keep_previous=True, boomerang=True,
            preset="readme", figsize=(6.4, 4.0),
            xlabel=r"$\alpha$ (°)", ylabel=r"$C_N$ (-)",
            title="animate_sweep",
        )
    print("  21b_animation_sweep.gif")


# ---------------------------------------------------------------------------
# 19/20 — batch plotting (continued)
# ---------------------------------------------------------------------------

def fig_batch() -> None:
    import shutil

    cfg, y_axis, sweep, fp = _batch_config()
    tmp = FIGURES / "_tmp_batch"

    written = batch_plot(
        configuration_dict=cfg, y_axis_dict=y_axis, sweep_dict=sweep,
        flight_point_dict=fp, output_base=tmp,
        style_profile="paper", formats=("png",), report=False,
    )
    shutil.copy(sorted(written)[0], FIGURES / "19_batch_plot.png")
    print("  19_batch_plot.png")

    # Each entry is one panel, and must pin *every* active flight-point key
    # (alpha is dropped automatically because it is the sweep variable).
    compare = {
        "M 0.70": {"Mach": 0.70, "Altitude_m": 5000, "beta": 0.0},
        "M 0.80": {"Mach": 0.80, "Altitude_m": 5000, "beta": 0.0},
        "M 0.85": {"Mach": 0.85, "Altitude_m": 5000, "beta": 0.0},
    }
    written = batch_compare_flight_points(
        configuration_dict=cfg, y_axis_dict=y_axis, sweep_dict=sweep,
        flight_point_dict=fp, compare_flight_points=compare,
        output_base=tmp, style_profile="paper", formats=("png",),
        max_cols=3, report=False,
    )
    shutil.copy(sorted(written)[0], FIGURES / "20_batch_compare.png")
    print("  20_batch_compare.png")

    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 26-30 — folded batch sheets
# ---------------------------------------------------------------------------

def _pick(directory, prefix: str):
    """First sheet whose name starts with *prefix*.

    CA sorts before CN and its three curves lie on top of each other in this
    fixture — a truthful figure, and a useless illustration.
    """
    return sorted(p for p in directory.rglob("*.png") if p.name.startswith(prefix))[0]


def _fold_config(sweep_keys, machs, altitudes):
    """The README's worked example, narrowed to one polar.

    ``batch_plot`` renders every ordinary figure before it can fold them, and
    the README's two-sweep study is ~150 renders per illustration. Each picture
    only needs one polar, so each run declares only the sweep it is about.

    That is not a simplification the pictures pay for: a key left out of
    ``sweep_dict`` becomes a flight point, and a flight point produces the same
    directory level, the same title fragment and the same fold families as a
    pinned sweep. The sheets below are byte-identical to the ones the full
    two-sweep run would write.
    """
    cfg, y_axis, sweep, fp = _batch_config()
    y_axis = {
        **y_axis,
        "CA": {"col_name": "CA", "literal_name": "Axial force coefficient",
               "symbol": r"$C_A$", "unit": "-", "y_save_name": "CA"},
    }
    sweep = {
        **sweep,
        "beta": {"col_name": "beta", "literal_name": "Sideslip angle",
                 "symbol": r"$\beta$", "unit": "°", "x_save_name": "beta",
                 "polar_prefix": "BETA_POLAR", "label": r"$\beta$", "save_name": "BETA"},
    }
    sweep = {key: sweep[key] for key in sweep_keys}
    for key, entry in cfg.items():
        df = entry["df"]
        cfg[key] = {**entry, "df": df[df["Mach"].isin(machs) & df["Altitude_m"].isin(altitudes)]}
    return cfg, y_axis, sweep, fp


def fig_batch_fold() -> None:
    """Every fold option, on the study the README walks through.

    Two runs, because the two interesting fold axes live in different polars:
    ALPHA_POLAR folds over the altitude (and over the Y list), BETA_POLAR folds
    over alpha — nine values, which is what makes the ``max_panels`` split
    visible.
    """
    import shutil

    tmp = FIGURES / "_tmp_fold"

    # --- ALPHA_POLAR: fold the Y list, and fold the altitudes three ways -----
    cfg, y_axis, sweep, fp = _fold_config(["alpha"], [0.7, 0.85], [5000, 8000, 10000])
    batch_plot(
        configuration_dict=cfg, y_axis_dict=y_axis, sweep_dict=sweep,
        flight_point_dict=fp, output_base=tmp,
        style_profile="paper", formats=("png",), report=False,
        clean=True,
        fold=[
            FoldSpec(kind="y"),
            FoldSpec(kind="context", over=("Altitude_m",)),
            FoldSpec(kind="context", layout="overlay", over=("Altitude_m",)),
            # A second overlay of the same family: without its own folder it
            # would overwrite the one above, which is what `folder` is for.
            FoldSpec(kind="context", layout="overlay", over=("Altitude_m",),
                     overlay_color="source", folder="FOLD_OVERLAY_SOURCE"),
        ],
    )
    polar = tmp / "ALPHA_POLAR"
    for source, name in [
        (_pick(polar / "M_0.7" / "Z_8000", "FOLD_Y"), "28_batch_fold_y.png"),
        (_pick(polar / "FOLD", "CN_"), "26_batch_fold.png"),
        (_pick(polar / "FOLD_OVERLAY", "CN_"), "27_batch_fold_overlay.png"),
        (_pick(polar / "FOLD_OVERLAY_SOURCE", "CN_"), "30_batch_fold_overlay_source.png"),
    ]:
        shutil.copy(source, FIGURES / name)
        print(f"  {name}")

    # --- BETA_POLAR: fold over alpha, nine values, split into two sheets -----
    # Same Mach/altitude set as above, so the sheet's subtitle matches the
    # study the README walks through. Only CN, because ``batch_plot`` renders
    # every ordinary figure before folding it and CA would double 54 renders
    # for a picture that shows a CN sheet either way.
    cfg, y_axis, sweep, fp = _fold_config(["beta"], [0.7, 0.85], [5000, 8000, 10000])
    y_axis = {"CN": y_axis["CN"]}
    batch_plot(
        configuration_dict=cfg, y_axis_dict=y_axis, sweep_dict=sweep,
        flight_point_dict=fp, output_base=tmp,
        style_profile="paper", formats=("png",), report=False,
        clean=True,
        fold=[FoldSpec(kind="context", over=("alpha",))],
    )
    # Pinned to the exact sheet the README's tree expands, so the picture and
    # the tree name the same file.
    shutil.copy(
        _pick(tmp / "BETA_POLAR" / "FOLD" / "M_0.7" / "Z_5000", "CN_"),
        FIGURES / "29_batch_fold_split.png",
    )
    print("  29_batch_fold_split.png")

    shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 22 — panel labels
# ---------------------------------------------------------------------------

def fig_panel_labels() -> None:
    use_style("paper")
    alpha, cn, _, _ = _polar()

    fig, axes = new_figure(2, 2, figsize=(10, 7))
    flat = axes.ravel()
    for index, ax in enumerate(flat):
        plot_line(ax, alpha, cn * (1.0 + 0.15 * index), label=f"config {index + 1}")
        ax.set_xlabel(r"$\alpha$ [deg]")
        ax.set_ylabel(r"$C_N$ [-]")
        make_legend(ax)

    panel_labels(axes)
    set_suptitle(fig, "panel_labels — (a) (b) (c) for the caption to point at")
    _write(fig, "22_panel_labels")


# ---------------------------------------------------------------------------
# 23 — palettes
# ---------------------------------------------------------------------------

def fig_palettes() -> None:
    use_style("paper")
    alpha, cn, _, _ = _polar()

    names = ["okabe_ito", "tol_bright", "tol_muted", "grayscale"]
    fig, axes = new_figure(2, 2, figsize=(10, 7))
    for ax, name in zip(axes.ravel(), names):
        colors = palette_colors(name, 5)
        for index, color in enumerate(colors):
            plot_line(ax, alpha, cn * (1.0 + 0.12 * index), color=color, label=f"s{index + 1}")
        ax.set_xlabel(r"$\alpha$ [deg]")
        ax.set_ylabel(r"$C_N$ [-]")
        set_title(ax, f"{name} ({len(PALETTES[name])} colours)")

    set_suptitle(fig, "Named colour cycles — colourblind-safe, and one for print")
    _write(fig, "23_palettes")


# ---------------------------------------------------------------------------
# 24 — contact sheet and PDF report
# ---------------------------------------------------------------------------

def fig_pdf_report() -> None:
    """Render a small study, then show the two ways of collecting it."""
    import shutil
    import tempfile

    use_style("paper")
    alpha, cn, _, _ = _polar()
    tmp = Path(tempfile.mkdtemp(prefix="cfd_plot_report_"))

    # A handful of figures standing in for a parametric study.
    pngs: list[Path] = []
    figures = []
    for index, mach in enumerate([0.60, 0.70, 0.80, 0.85, 0.90, 0.95]):
        fig, ax = new_figure()
        plot_line(ax, alpha, cn * (1.0 + 0.25 * index), label=r"$k\!-\!\omega$")
        plot_line(ax, alpha, cn * (1.0 + 0.25 * index) * 1.04, label="SA")
        ax.set_xlabel(r"$\alpha$ [deg]")
        ax.set_ylabel(r"$C_N$ [-]")
        make_legend(ax)
        set_title(ax, f"M = {mach:.2f}")
        fig.set_label(f"CN_vs_alpha, M={mach:.2f}")
        pngs.extend(save_figure(fig, tmp / f"CN_M{mach:.2f}", formats=("png",)))
        figures.append(fig)

    # (a) contact sheet — triage, everything at once.
    sheets = contact_sheet(pngs, tmp / "sheet.png", rows=2, cols=3, title="Study — contact sheet")
    shutil.copy(sheets[0], FIGURES / "24_contact_sheet.png")
    print("  24_contact_sheet.png")

    # (b) the report — cover, contents, one page per figure.
    report = pdf_report(
        figures,
        tmp / "ETUDE.pdf",
        title="Mach sweep",
        subtitle="k-omega vs Spalart-Allmaras",
        summary=[("Figures", str(len(figures))), ("Mach", "0.60 - 0.95")],
    )
    for fig in figures:
        plt.close(fig)

    # Show the first pages of the report side by side, if a rasteriser is around.
    _report_preview(report, FIGURES / "25_pdf_report.png")

    shutil.rmtree(tmp, ignore_errors=True)


def _report_preview(pdf_path: Path, out_path: Path) -> None:
    """Paste the first three pages of *pdf_path* side by side, via pdftoppm.

    Skipped when Poppler is not installed: the README picture is a convenience,
    not something worth adding a dependency for.
    """
    import shutil
    import subprocess
    import tempfile

    if shutil.which("pdftoppm") is None:
        print("  (25_pdf_report.png skipped — pdftoppm not found)")
        return

    with tempfile.TemporaryDirectory() as raw:
        subprocess.run(
            ["pdftoppm", "-png", "-r", "80", "-f", "1", "-l", "3", str(pdf_path), f"{raw}/pg"],
            check=True,
        )
        pages = sorted(Path(raw).glob("pg-*.png"))
        if not pages:
            return
        images = [plt.imread(str(page)) for page in pages]

        fig, axes = new_figure(1, len(images), figsize=(4.0 * len(images), 5.2))
        for ax, image, name in zip(axes.ravel(), images, ["cover", "contents", "figure"]):
            ax.imshow(image)
            ax.set_axis_off()
            set_title(ax, name)
        set_suptitle(fig, "pdf_report — one document out of a whole study")
        _write(fig, out_path.stem)


# ---------------------------------------------------------------------------

def main() -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    print(f"Writing figures to {FIGURES}")
    fig_styles()
    fig_line_helpers()
    fig_fill_between()
    fig_annotations()
    fig_axes_helpers()
    fig_sync_axes_limits()
    fig_legends()
    fig_field2d()
    fig_interpolation()
    fig_masking()
    fig_vector2d()
    fig_composite()
    fig_shared_colorbar()
    fig_prep()
    fig_declassify()
    fig_batch()
    fig_batch_fold()
    fig_animation()
    fig_panel_labels()
    fig_palettes()
    fig_pdf_report()
    print("Done.")


if __name__ == "__main__":
    main()
