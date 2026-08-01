"""Image regression tests (pytest-mpl).

The rest of the suite asserts *structure* — that a call returns a Line2D, that
limits match, that a colorbar exists. None of it can see what the figure
actually looks like, which is the one thing this library exists to control.
These tests render a figure and compare it pixel-wise against a stored
baseline, so a Matplotlib upgrade that quietly changes the house style, marker
rendering, legend frame or colour handling fails loudly instead of shipping.

Running them::

    pytest --mpl                      # compare against tests/baseline/
    pytest                            # figures are built but NOT compared

Without ``--mpl`` the tests still execute (so they catch exceptions) but skip
the comparison — that is pytest-mpl's design, not an oversight.

Regenerating baselines, after an *intended* visual change::

    pytest --mpl-generate-path=tests/baseline

Then **look at the diff images** before committing. A regenerated baseline that
nobody eyeballed is worse than no baseline at all: it locks in whatever the
regression was.

Every figure here must be deterministic — no unseeded RNG, no timestamps, no
dependence on the machine's font configuration (the TeX Gyre fonts ship inside
the package, so that part is already pinned).
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from cfd_plot import (
    add_reference_lines,
    add_shared_colorbar,
    add_textbox,
    annotate_point,
    apply_oldschool_axes,
    compute_speed,
    dual_axis,
    make_figure_legend,
    make_legend,
    mask_field,
    new_figure,
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
    set_subtitle,
    set_suptitle,
    set_title,
    style_context,
    sync_axes_limits,
    use_style,
)
from cfd_plot.dispersion import (
    DispersionSpec,
    QuantityDispersion,
    plot_dispersion_pdf,
    plot_dispersion_type,
)

# Tolerance is an RMS difference, and it was calibrated rather than guessed.
# Injecting one deliberate style regression (plot_line's white marker fill
# turned red) produced RMS 8.6-23.6 across the affected tests, while rerunning
# unchanged on the same machine gives < 0.01. 2 sits well below the weakest
# real signal and leaves room for the antialiasing differences you get from a
# different FreeType build — the fonts themselves ship with the package, so
# that much larger source of drift is already pinned.
#
# If you raise this, re-run the injection experiment: at 20 the marker-colour
# regression slipped through 16 of 18 tests unnoticed.
TOL = 2

# pytest-mpl wraps each test in `style="classic"` by default. That is exactly
# wrong here: these tests exist to pin *our* house styles, and letting
# pytest-mpl impose Matplotlib's classic rcParams means the baselines record a
# style the package never produces. `style="default"` hands control back, and
# each test then establishes the profile it means to test.
#
# (Finding this was not academic: under `classic`, legend.edgecolor is the
# string "inherit", which crashed make_legend — see TestLegendEdgeColorInherit
# in test_figure_helpers.py.)
MPL = dict(tolerance=TOL, style="default")


@pytest.fixture(autouse=True)
def _house_style():
    """Every image test renders under the notebook profile unless it says otherwise."""
    use_style("notebook")
    yield
    plt.close("all")

# --------------------------------------------------------------------------
# Deterministic fixtures — no RNG anywhere in this module
# --------------------------------------------------------------------------

ALPHA = np.linspace(-4.0, 16.0, 21)
CN_SA = 0.11 * ALPHA + 0.004 * ALPHA**2
CN_KW = 0.108 * ALPHA + 0.0035 * ALPHA**2


def _field():
    x = np.linspace(-2.0, 2.0, 40)
    y = np.linspace(-1.5, 1.5, 30)
    X, Y = np.meshgrid(x, y)
    z = np.exp(-(X**2 + Y**2)) * np.cos(2.5 * X) + 0.25 * Y
    u = -Y * np.exp(-0.3 * (X**2 + Y**2))
    v = X * np.exp(-0.3 * (X**2 + Y**2))
    return x, y, X, Y, z, u, v


# --------------------------------------------------------------------------
# Style profiles — the core promise of the package
# --------------------------------------------------------------------------


@pytest.mark.parametrize("profile", ["notebook", "slides", "paper"])
@pytest.mark.mpl_image_compare(**MPL)
def test_style_profile(profile):
    """Each profile must keep its distinct look: figsize, fonts, grid."""
    with style_context(profile):
        fig, ax = plt.subplots(figsize=(5.2, 3.4))
        plot_line(ax, ALPHA, CN_SA, label="SA")
        plot_line(ax, ALPHA, CN_KW, marker="s", label=r"$k$-$\omega$ SST")
        ax.set_xlabel(r"$\alpha$ [deg]")
        ax.set_ylabel(r"$C_N$ [-]")
        set_title(ax, profile)
        make_legend(ax)
    return fig


# --------------------------------------------------------------------------
# 1D helpers
# --------------------------------------------------------------------------


@pytest.mark.mpl_image_compare(**MPL)
def test_plot_line_marker_treatment():
    """White-filled markers with a coloured edge — the house signature."""
    fig, ax = new_figure(figsize=(6, 4))
    plot_line(ax, ALPHA, CN_SA, label="SA")
    plot_line(ax, ALPHA, CN_KW, marker="s", label=r"$k$-$\omega$ SST")
    plot_line(ax, ALPHA, CN_SA * 0.9, marker="^", ls="none", label="Experiment")
    make_legend(ax)
    return fig


@pytest.mark.mpl_image_compare(**MPL)
def test_plot_with_band():
    band = 0.05 + 0.01 * np.abs(ALPHA)
    fig, ax = new_figure(figsize=(6, 4))
    plot_with_band(
        ax, ALPHA, CN_SA, y_low=CN_SA - band, y_high=CN_SA + band,
        label="SA", band_label=r"$\pm\,2\sigma$",
    )
    make_legend(ax)
    return fig


@pytest.mark.mpl_image_compare(**MPL)
def test_plot_bar():
    fig, ax = new_figure(figsize=(6, 4))
    plot_bar(ax, ["SA", "k-w SST", "k-e", "EXP"], [0.482, 0.474, 0.455, 0.489], color="C0")
    return fig


@pytest.mark.mpl_image_compare(**MPL)
def test_oldschool_axes():
    """Spine, tick and legend-frame polish applied on its own."""
    fig, ax = new_figure(figsize=(6, 4))
    plot_line(ax, ALPHA, CN_SA, label="SA")
    apply_oldschool_axes(ax)
    return fig


# --------------------------------------------------------------------------
# Annotations and axes helpers
# --------------------------------------------------------------------------


@pytest.mark.mpl_image_compare(**MPL)
def test_annotations():
    """Title/subtitle stacking, textbox anchoring, annotation arrow."""
    fig, ax = new_figure(figsize=(7, 4.5))
    plot_line(ax, ALPHA, CN_SA, label="SA")
    set_title(ax, "Normal force polar")
    set_subtitle(ax, "M = 0.7, Re = 6e6")
    add_reference_lines(ax, hlines=[0.0], vlines=[0.0])
    add_textbox(ax, "mesh: 20 M cells\nsolver: foamRun", loc="upper left")
    annotate_point(ax, "stall onset", (ALPHA[16], CN_SA[16]), offset=(-80, 25))
    make_legend(ax)
    return fig


@pytest.mark.mpl_image_compare(**MPL)
def test_dual_axis():
    """The right spine, ticks and label must all pick up the tint."""
    fig, ax = new_figure(figsize=(6, 4))
    plot_line(ax, ALPHA, CN_SA, label=r"$C_N$")
    ax_r = dual_axis(ax, ylabel=r"$C_D$ [-]", color="C3")
    plot_line(ax_r, ALPHA, 0.012 + 0.0009 * ALPHA**2, marker="s", color="C3")
    return fig


@pytest.mark.mpl_image_compare(**MPL)
def test_sync_axes_limits_across_artist_types():
    """Regression cover with eyes: line, scatter and bars share one y range."""
    fig, axes = new_figure(1, 3, figsize=(12, 3.5))
    plot_line(axes[0], ALPHA, 0.11 * ALPHA)
    axes[1].scatter(ALPHA, 0.55 * ALPHA, s=18, color="C1")
    axes[2].bar(["M 0.7", "M 0.8", "M 0.85"], [0.9, 1.4, 1.75], color="C2", edgecolor="0.15")
    sync_axes_limits(axes, which="y")
    return fig


@pytest.mark.mpl_image_compare(**MPL)
def test_figure_legend_dedupe():
    fig, axes = new_figure(1, 2, figsize=(9, 3.5))
    for ax in axes:
        plot_line(ax, ALPHA, CN_SA, label="SA")
        plot_line(ax, ALPHA, CN_KW, marker="s", label=r"$k$-$\omega$ SST")
    set_suptitle(fig, "shared legend")
    make_figure_legend(fig, axes, loc="center right", bbox_to_anchor=(1.15, 0.5))
    return fig


# --------------------------------------------------------------------------
# 2D scalar fields
# --------------------------------------------------------------------------


@pytest.mark.mpl_image_compare(**MPL)
def test_field2d_renderers():
    """All four renderers in one figure, so colour handling is pinned too."""
    x, y, _, _, z, _, _ = _field()
    fig, axes = new_figure(2, 2, figsize=(10, 7))
    flat = axes.ravel()
    plot_contour(flat[0], x, y, z, levels=14, colors="k", colorbar=False)
    plot_contourf(flat[1], x, y, z, levels=20, cmap="viridis", cbar_label=r"$C_p$")
    plot_pcolormesh(flat[2], x, y, z, cmap="RdBu_r", cbar_label=r"$C_p$")
    plot_imshow(flat[3], z, extent=(x[0], x[-1], y[0], y[-1]), cmap="magma", cbar_label=r"$C_p$")
    return fig


@pytest.mark.mpl_image_compare(**MPL)
def test_masking_and_bad_color():
    """Guards `bad_color`, which the Colormap.set_bad deprecation threatened."""
    x, y, X, Y, z, _, _ = _field()
    inside = (X**2 / 1.1**2 + Y**2 / 0.45**2) < 1.0
    z_masked = mask_field(z, inside)

    fig, axes = new_figure(1, 2, figsize=(10, 3.6))
    plot_pcolormesh(axes[0], x, y, z_masked, cmap="viridis", bad_color="0.85", cbar_label=r"$C_p$")
    plot_contourf(
        axes[1], x, y, z_masked, levels=20, cmap="viridis", bad_color="white",
        mask_outline=inside, mask_outline_color="k", mask_outline_width=1.8,
        cbar_label=r"$C_p$",
    )
    return fig


@pytest.mark.mpl_image_compare(**MPL)
def test_shared_colorbar():
    x, y, X, Y, _, _, _ = _field()
    fig, axes = new_figure(1, 3, figsize=(11, 3.2))
    mappable = None
    for ax, mach in zip(axes, (0.5, 0.7, 0.85), strict=True):
        z = np.exp(-(X**2 + Y**2)) * np.cos(2.5 * X) * mach
        mappable, _ = plot_pcolormesh(
            ax, x, y, z, cmap="RdBu_r", colorbar=False, vmin=-0.9, vmax=0.9
        )
        set_title(ax, f"M = {mach}")
    add_shared_colorbar(fig, mappable, axes=axes, location="right", label=r"$C_p$")
    return fig


# --------------------------------------------------------------------------
# Vector fields
# --------------------------------------------------------------------------


@pytest.mark.mpl_image_compare(**MPL)
def test_vector_fields():
    x, y, _, _, _, u, v = _field()
    fig, axes = new_figure(1, 3, figsize=(13, 3.6))
    plot_quiver(axes[0], x, y, u, v, stride=3, color="0.2")
    plot_quiver(axes[1], x, y, u, v, stride=3, magnitude_color=True, cmap="viridis", colorbar=True)
    plot_streamplot(
        axes[2], x, y, u, v, density=1.2, color=compute_speed(u, v), cmap="plasma", colorbar=True
    )
    return fig


@pytest.mark.mpl_image_compare(**MPL)
def test_contour_quiver_composite():
    x, y, _, _, z, u, v = _field()
    fig, ax = new_figure(figsize=(6, 4))
    plot_contour_quiver(
        ax, x, y, z, u, v, scalar_kind="contourf", levels=20, cmap="viridis",
        quiver_stride=4, quiver_color="k", cbar_label=r"$C_p$",
    )
    return fig


# --------------------------------------------------------------------------
# Dispersion
# --------------------------------------------------------------------------


@pytest.mark.mpl_image_compare(**MPL)
def test_dispersion_type_shapes():
    """The six distribution shapes — pure geometry, no sampling."""
    specs = [
        DispersionSpec(disp_type=t, moy=0.5 if t == 2 else 0.0, var=0.0 if t in (1, 2) else 1.0)
        for t in range(1, 7)
    ]
    with style_context("notebook"):
        fig, axes = plt.subplots(2, 3, figsize=(11, 5))
        for ax, spec in zip(axes.ravel(), specs, strict=True):
            plot_dispersion_type(spec, ax=ax)
    return fig


@pytest.mark.mpl_image_compare(**MPL)
def test_dispersion_pdf():
    """Sampled, so the generator is seeded explicitly for reproducibility."""
    qty = QuantityDispersion(
        name=r"$C_{m\alpha}$",
        nominal=-0.42,
        bias=DispersionSpec(disp_type=4, moy=0.0, var=0.02),
        scale=DispersionSpec(disp_type=6, moy=0.0, var=0.10),
    )
    fig, _ = plot_dispersion_pdf(qty, n=20000, rng=np.random.default_rng(0))
    return fig
