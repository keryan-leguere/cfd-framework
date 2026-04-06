"""
dispersion.plots — Matplotlib visualization for dispersion analyses.

Styling is delegated to the companion ``plotting`` package, which must be on
the Python path (e.g. run from ``scripts/post/plot`` with ``PYTHONPATH=.``).
When a function creates its own figure it applies the ``"notebook"`` style
profile via :func:`plotting.style_context`; when an external ``ax`` is
supplied the caller controls the style.

All functions are composable:

    fig, ax   = plot_dispersion_type(spec)           # new figure
    fig, ax   = plot_dispersion_pdf(qty)             # new figure
    fig, ax   = plot_dispersion_cdf(qty)             # new figure
    fig, axes = plot_dispersion_dashboard(qty)       # always new figure
    fig, axes = plot_dispersion_matrix(qty_list)     # always new figure

    # embed in an external figure
    outer_fig, ax_ext = plt.subplots()
    plot_dispersion_type(spec, ax=ax_ext)
"""

from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle
from scipy.stats import gaussian_kde, norm, truncnorm

from .core import DispersionSpec, QuantityDispersion, sigma

# ---------------------------------------------------------------------------
# Plotting package — styling helpers
# ---------------------------------------------------------------------------
from plotting import (
    add_textbox,
    annotate_point,
    apply_oldschool_axes,
    set_suptitle,
    set_title,
    style_context,
)

if TYPE_CHECKING:
    from matplotlib.axes import Axes

_PROFILE = "notebook"

# Theoretical Gaussian coverage for ±k sigma (used in legend labels)
_SIGMA_THEORY: dict[int, float] = {1: 68.27, 2: 95.45, 3: 99.73}

# Per-type default colours — tab10 palette indexed by type int 1–6
_TAB10 = plt.cm.tab10.colors
_TYPE_COLORS: dict[int, tuple] = {i + 1: _TAB10[i] for i in range(6)}

# Offsets (pts from annotation xy) for the 6 sigma marks on the CDF
_CDF_SIGMA_OFFSETS: dict[tuple, tuple] = {
    (1, +1): (48,  12),   # +1σ at ~84% → right-up
    (2, +1): (48,   5),   # +2σ at ~98% → right
    (3, +1): (-65,  -6),  # +3σ at ~100% → left (avoid top-right edge)
    (1, -1): (-48, -12),  # -1σ at ~16% → left-down
    (2, -1): (-48,  -5),  # -2σ at ~2%  → left
    (3, -1): (65,    6),  # -3σ at ~0%  → right (avoid bottom-left edge)
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _type_color(disp_type: int, override) -> tuple | str:
    return override if override is not None else _TYPE_COLORS.get(disp_type, _TAB10[0])


def _ctx(own_fig: bool):
    """Return a style context manager when we own the figure, else a no-op."""
    return style_context(_PROFILE) if own_fig else nullcontext()


def _empirical_coverage(samples: np.ndarray, mean: float, std: float) -> dict[int, float]:
    """Empirical proportion (%) of samples within ±1σ, ±2σ, ±3σ of the mean."""
    if std < 1e-10:
        return {1: 100.0, 2: 100.0, 3: 100.0}
    return {
        k: float(np.mean(np.abs(samples - mean) <= k * std) * 100)
        for k in (1, 2, 3)
    }


def _stats_textbox(
    mean: float,
    std: float,
    coverage: dict[int, float] | None = None,
) -> str:
    """Build the stats textbox string with E[X], σ, and optional coverage rows."""
    lines = [f"E[X] = {mean:.4g}", f"  \u03c3  = {std:.4g}"]
    if coverage is not None and std > 1e-10:
        lines.append("-" * 16)
        for k, pct in coverage.items():
            lines.append(f"P(\u00b1{k}\u03c3) = {pct:.1f}%")
    return "\n".join(lines)


def _draw_sigma_bands(ax, mean: float, std: float, color) -> None:
    """Draw ±1σ, ±2σ, ±3σ nested shaded bands and their edge lines.

    Bands are added with ``label`` so they appear in the legend (in the order
    ±1σ, ±2σ, ±3σ).  Edge lines have no legend entry.
    """
    if std < 1e-10:
        return
    for k, pct, alpha in [
        (1, _SIGMA_THEORY[1], 0.14),
        (2, _SIGMA_THEORY[2], 0.09),
        (3, _SIGMA_THEORY[3], 0.05),
    ]:
        ax.axvspan(
            mean - k * std, mean + k * std,
            alpha=alpha, color=color, zorder=1,
            label=f"\u00b1{k}\u03c3   ({pct:.1f}%)",
        )
    # Edge lines — gray, different dash style per band level
    for k, ls, alp in [(1, "-", 0.55), (2, "--", 0.45), (3, ":", 0.35)]:
        for sign in (-1, +1):
            ax.axvline(
                mean + sign * k * std,
                color="0.65", ls=ls, lw=0.85, alpha=alp, zorder=3,
            )


def _add_sigma_axis_labels(ax, mean: float, std: float, fontsize: float = 9.0) -> None:
    """Place ±σ, ±2σ, ±3σ labels just below the x-axis (clip disabled).

    The offset is chosen to clear the numeric x-tick labels: the notebook
    style uses ``xtick.labelsize=10`` with a tick length of 5 pt and a
    label pad of ~4 pt, so the bottom of the numeric labels sits roughly
    19–22 pt below the axis line.  We use -28 pt to stay well clear.
    """
    if std < 1e-10:
        return
    for k in (1, 2, 3):
        for sign in (-1, +1):
            xpos = mean + sign * k * std
            klab = "" if k == 1 else str(k)
            sign_char = "+" if sign > 0 else "\u2212"
            ax.annotate(
                f"{sign_char}{klab}\u03c3",
                xy=(xpos, 0),
                xycoords=("data", "axes fraction"),
                xytext=(0, -28),
                textcoords="offset points",
                fontsize=fontsize,
                ha="center",
                color="0.40",
                annotation_clip=False,
            )


def _spec_textbox_content(spec: DispersionSpec) -> str | None:
    """Compact parameter summary for a distribution type panel."""
    dt = spec.disp_type
    moy, var = float(spec.moy), float(spec.var)
    s = sigma(var)
    if dt == 1:
        return None
    if dt == 2:
        return f"value = {moy:.4g}"
    if dt == 3:
        return f"moy = {moy:.4g}\nvar = {var:.4g}"
    if dt == 4:
        return f"moy = {moy:.4g}\n\u03c3   = {s:.4g}"
    if dt == 5:
        lo, hi = moy - 1.5 * var, moy + 1.5 * var
        return f"moy = {moy:.4g}\n\u03c3   = {s:.4g}\n\u00b13\u03c3: [{lo:.4g}, {hi:.4g}]"
    lo, hi = moy - var, moy + var
    return f"moy = {moy:.4g}\n\u03c3   = {s:.4g}\n\u00b12\u03c3: [{lo:.4g}, {hi:.4g}]"


# ---------------------------------------------------------------------------
# plot_dispersion_type
# ---------------------------------------------------------------------------

def plot_dispersion_type(
    spec: DispersionSpec,
    ax: Axes | None = None,
    color: str | tuple | None = None,
) -> tuple:
    """Illustrative mini-plot of the distribution shape for one DispersionSpec.

    Parameters
    ----------
    spec:
        The dispersion spec to illustrate.
    ax:
        Existing axes to draw on.  If *None*, a new figure is created.
    color:
        Fill / line colour.  When *None*, a type-keyed tab10 default is used.

    Returns
    -------
    fig, ax
    """
    own_fig = ax is None
    with _ctx(own_fig):
        if own_fig:
            fig, ax = plt.subplots(figsize=(3.8, 3.0))
        else:
            fig = ax.get_figure()

        c = _type_color(spec.disp_type, color)
        moy = float(spec.moy)
        var = float(spec.var)
        dt = spec.disp_type

        if dt == 1:
            ax.annotate(
                "",
                xy=(0.0, 0.85), xytext=(0.0, 0.0),
                xycoords="data", textcoords="data",
                arrowprops=dict(arrowstyle="-|>", color=c, lw=2.5),
            )
            ax.set_xlim(-1, 1)
            ax.set_ylim(0, 1)

        elif dt == 2:
            ax.annotate(
                "",
                xy=(moy, 0.85), xytext=(moy, 0.0),
                xycoords="data", textcoords="data",
                arrowprops=dict(arrowstyle="-|>", color=c, lw=2.5),
            )
            half = max(abs(moy) * 0.5, 1.0)
            ax.set_xlim(moy - half, moy + half)
            ax.set_ylim(0, 1)

        elif dt == 3:
            if var == 0.0:
                ax.annotate(
                    "",
                    xy=(moy, 0.85), xytext=(moy, 0.0),
                    xycoords="data", textcoords="data",
                    arrowprops=dict(arrowstyle="-|>", color=c, lw=2.5),
                )
                ax.set_xlim(moy - 1, moy + 1)
                ax.set_ylim(0, 1)
            else:
                height = 1.0 / (2.0 * var)
                rect = Rectangle(
                    (moy - var, 0.0), 2.0 * var, height,
                    facecolor=c, edgecolor=c, alpha=0.50, linewidth=1.4,
                )
                ax.add_patch(rect)
                ax.axvline(moy - var, color=c, lw=1.6)
                ax.axvline(moy + var, color=c, lw=1.6)
                ax.set_xlim(moy - var * 1.7, moy + var * 1.7)
                ax.set_ylim(0, height * 1.35)

        elif dt == 4:
            s = sigma(var)
            if s == 0.0:
                ax.annotate(
                    "",
                    xy=(moy, 0.85), xytext=(moy, 0.0),
                    xycoords="data", textcoords="data",
                    arrowprops=dict(arrowstyle="-|>", color=c, lw=2.5),
                )
                ax.set_xlim(moy - 1, moy + 1)
                ax.set_ylim(0, 1)
            else:
                x = np.linspace(moy - 4.2 * s, moy + 4.2 * s, 400)
                y = norm.pdf(x, loc=moy, scale=s)
                ax.fill_between(x, y, alpha=0.22, color=c)
                ax.plot(x, y, color=c, lw=2)
                ax.axvline(moy, color=c, ls="--", lw=1.1, alpha=0.55)
                ax.set_xlim(x[0], x[-1])
                ax.set_ylim(0, y.max() * 1.30)

        else:  # types 5 and 6
            a_std, b_std = (-3.0, 3.0) if dt == 5 else (-2.0, 2.0)
            s = sigma(var)
            if s == 0.0:
                ax.annotate(
                    "",
                    xy=(moy, 0.85), xytext=(moy, 0.0),
                    xycoords="data", textcoords="data",
                    arrowprops=dict(arrowstyle="-|>", color=c, lw=2.5),
                )
                ax.set_xlim(moy - 1, moy + 1)
                ax.set_ylim(0, 1)
            else:
                lo, hi = moy + a_std * s, moy + b_std * s
                margin = (hi - lo) * 0.18
                x = np.linspace(lo - margin, hi + margin, 500)
                y = truncnorm.pdf(x, a_std, b_std, loc=moy, scale=s)
                ax.fill_between(x, y, alpha=0.22, color=c)
                ax.plot(x, y, color=c, lw=2)
                ax.axvline(moy, color=c, ls="--", lw=1.1, alpha=0.55)
                for wall in (lo, hi):
                    ax.axvline(wall, color=c, lw=1.6, ls="--", alpha=0.85)
                ax.set_xlim(x[0], x[-1])
                ax.set_ylim(0, y.max() * 1.30)

        # Parameter textbox
        tb_text = _spec_textbox_content(spec)
        if tb_text:
            add_textbox(ax, tb_text, loc="lower right", fontsize=9)

        set_title(ax, spec.label, fontsize=11)
        ax.set_xlabel("x", fontsize=10)
        ax.set_ylabel("pdf", fontsize=10)
        ax.tick_params(labelsize=8)
        apply_oldschool_axes(ax, legend=False)

    return fig, ax


# ---------------------------------------------------------------------------
# plot_dispersion_pdf
# ---------------------------------------------------------------------------

def plot_dispersion_pdf(
    qty: QuantityDispersion,
    n: int = 10000,
    bins: int = 80,
    ax: Axes | None = None,
    color: str | tuple | None = None,
    rng: np.random.Generator | None = None,
) -> tuple:
    """Histogram + KDE with ±σ / ±2σ / ±3σ bands and coverage statistics.

    E[X] (espérance) and σ are shown in a textbox (upper-left).  Empirical
    coverage probabilities for ±kσ intervals are added below.  The ±kσ
    positions are labelled directly on the x-axis.  A spec summary textbox
    appears (lower-right) when the function creates its own figure.

    Parameters
    ----------
    qty:
        Quantity to sample and plot.
    n:
        Number of Monte Carlo samples.
    bins:
        Number of histogram bins.
    ax:
        Existing axes.  If *None*, a new figure is created.
    color:
        Base colour for the distribution.  Defaults to ``"C0"``.
    rng:
        Optional random generator for reproducibility.

    Returns
    -------
    fig, ax
    """
    own_fig = ax is None
    with _ctx(own_fig):
        if own_fig:
            fig, ax = plt.subplots(figsize=(9, 5.5), layout="none")
        else:
            fig = ax.get_figure()

        c = color if color is not None else "C0"
        samples = qty.sample(n, rng=rng)
        mean = float(np.mean(samples))
        std = float(np.std(samples))
        coverage = _empirical_coverage(samples, mean, std)
        x_range = samples.max() - samples.min()

        # ── Histogram ─────────────────────────────────────────────────
        ax.hist(samples, bins=bins, density=True, color=c, alpha=0.22, zorder=2)

        # ── KDE overlay ───────────────────────────────────────────────
        if x_range > 0:
            try:
                kde = gaussian_kde(samples)
                x_lo = samples.min() - 0.08 * x_range
                x_hi = samples.max() + 0.08 * x_range
                x_kde = np.linspace(x_lo, x_hi, 600)
                ax.plot(x_kde, kde(x_kde), color=c, lw=2, label="KDE", zorder=4)
            except Exception:
                pass

        # ── Nominal and E[X] vertical lines ───────────────────────────
        ax.axvline(
            qty.nominal,
            color="0.20", ls="--", lw=1.5, label="Nominal", zorder=5,
        )
        ax.axvline(
            mean,
            color=c, ls=(0, (4, 2)), lw=2.2, label="E[X]", zorder=6,
        )

        # ── σ bands (added after lines → legend order: KDE, Nominal, E[X], ±1σ…) ─
        _draw_sigma_bands(ax, mean, std, c)

        # ── Textbox: E[X], σ, empirical coverage ──────────────────────
        tb_fs = 10 if own_fig else 9
        full_coverage = coverage if own_fig else None
        add_textbox(ax, _stats_textbox(mean, std, full_coverage), loc="upper left", fontsize=tb_fs)

        # ── Spec textbox (standalone only, lower right) ────────────────
        if own_fig:
            b, sc = qty.bias, qty.scale
            spec_text = (
                f"Bias:  {b.label}\n"
                f"  moy={b.moy:.4g},  \u03c3={b.sigma:.4g}\n"
                f"Scale: {sc.label}\n"
                f"  moy={sc.moy:.4g},  \u03c3={sc.sigma:.4g}"
            )
            add_textbox(ax, spec_text, loc="lower right", fontsize=9)

        # ── Titles / labels ────────────────────────────────────────────
        set_title(ax, f"PDF \u2014 {qty.name}")
        ax.set_xlabel(qty.name, fontsize=12)
        ax.set_ylabel("Density", fontsize=12)

        # ── Legend ─────────────────────────────────────────────────────
        apply_oldschool_axes(
            ax, legend=True,
            legend_kwargs={"fontsize": 8.5, "loc": "upper right", "ncol": 1},
        )

        # ── X-axis ±kσ labels (placed after apply_oldschool_axes) ──────
        _add_sigma_axis_labels(ax, mean, std, fontsize=9.0 if own_fig else 8.5)

        # Give enough vertical room below the axis for the ±kσ labels.
        # Only adjust when we own the figure; for embedded axes the parent
        # layout manager is responsible.
        if own_fig:
            fig.subplots_adjust(bottom=0.18)

    return fig, ax


# ---------------------------------------------------------------------------
# plot_dispersion_cdf
# ---------------------------------------------------------------------------

def plot_dispersion_cdf(
    qty: QuantityDispersion,
    n: int = 10000,
    ax: Axes | None = None,
    color: str | tuple | None = None,
    rng: np.random.Generator | None = None,
) -> tuple:
    """Empirical CDF with ±σ / ±2σ / ±3σ sigma marks and coverage textbox.

    The CDF value at each ±kσ position is annotated with an arrow using
    :func:`plotting.annotate_point`.  Empirical coverage probabilities are
    shown in the stats textbox.  The ±kσ positions are also labelled on
    the x-axis.

    Parameters
    ----------
    qty:
        Quantity to sample.
    n:
        Number of samples.
    ax:
        Existing axes.  If *None*, a new figure is created.
    color:
        Line colour.  Defaults to ``"C0"``.
    rng:
        Optional random generator.

    Returns
    -------
    fig, ax
    """
    own_fig = ax is None
    with _ctx(own_fig):
        if own_fig:
            fig, ax = plt.subplots(figsize=(9, 5.5), layout="none")
        else:
            fig = ax.get_figure()

        c = color if color is not None else "C0"
        samples = qty.sample(n, rng=rng)
        mean = float(np.mean(samples))
        std = float(np.std(samples))
        coverage = _empirical_coverage(samples, mean, std)

        xs = np.sort(samples)
        ys = np.arange(1, n + 1) / n

        # ── CDF curve ─────────────────────────────────────────────────
        ax.plot(xs, ys, color=c, lw=2, zorder=3)

        # ── Sigma marks ───────────────────────────────────────────────
        if std > 1e-10:
            for k in (1, 2, 3):
                for sign in (-1, +1):
                    xpos = mean + sign * k * std
                    cdf_val = float(np.interp(xpos, xs, ys))

                    # Dotted guide lines
                    ax.plot([xs[0], xpos], [cdf_val, cdf_val],
                            color="0.60", ls=":", lw=0.9, zorder=2)
                    ax.plot([xpos, xpos], [0.0, cdf_val],
                            color="0.60", ls=":", lw=0.9, zorder=2)

                    # Marker dot
                    ax.scatter([xpos], [cdf_val],
                               color=c, s=50, edgecolors="white", linewidths=1.0, zorder=6)

                    # Arrow annotation via plotting helper
                    klab = "" if k == 1 else str(k)
                    sign_char = "+" if sign > 0 else "\u2212"
                    label_text = f"{sign_char}{klab}\u03c3\nP = {cdf_val:.1%}"
                    offset = _CDF_SIGMA_OFFSETS[(k, sign)]
                    annotate_point(ax, label_text, xy=(xpos, cdf_val),
                                   offset=offset, fontsize=8)

        # ── Textbox: E[X], σ, empirical coverage ──────────────────────
        add_textbox(ax, _stats_textbox(mean, std, coverage), loc="upper left", fontsize=10)

        # ── Titles / labels ────────────────────────────────────────────
        set_title(ax, f"CDF \u2014 {qty.name}")
        ax.set_xlabel(qty.name, fontsize=12)
        ax.set_ylabel("CDF", fontsize=12)
        ax.set_ylim(-0.03, 1.06)

        apply_oldschool_axes(ax, legend=False)

        # ── X-axis ±kσ labels ──────────────────────────────────────────
        _add_sigma_axis_labels(ax, mean, std, fontsize=9.0)

        if own_fig:
            fig.subplots_adjust(bottom=0.18)

    return fig, ax


# ---------------------------------------------------------------------------
# plot_dispersion_dashboard
# ---------------------------------------------------------------------------

def plot_dispersion_dashboard(
    qty: QuantityDispersion,
    n: int = 10000,
    rng: np.random.Generator | None = None,
    **kwargs,
) -> tuple:
    """3-panel dashboard: bias type shape | PDF | scale type shape.

    Parameters
    ----------
    qty:
        Quantity to visualise.
    n:
        Number of PDF samples.
    rng:
        Optional random generator.
    **kwargs:
        Forwarded to ``plt.subplots`` (e.g. ``figsize``).

    Returns
    -------
    fig, axes  — axes is a shape-(3,) ndarray

    Examples
    --------
    ::

        fig, axes = plot_dispersion_dashboard(qty)
        fig.savefig("out.png", dpi=150)
    """
    figsize = kwargs.pop("figsize", (16, 5.0))

    with style_context(_PROFILE):
        fig, axes = plt.subplots(1, 3, figsize=figsize, layout="none", **kwargs)

        plot_dispersion_type(qty.bias, ax=axes[0])
        plot_dispersion_pdf(qty, n=n, ax=axes[1], rng=rng)
        plot_dispersion_type(qty.scale, ax=axes[2])

        # Panel titles — override the generic label set by plot_dispersion_type
        set_title(axes[0], f"Bias \u2014 {qty.bias.label}", fontsize=10)
        set_title(axes[2], f"Scale \u2014 {qty.scale.label}", fontsize=10)

        # Figure suptitle: name + nominal + full spec summary
        b, sc = qty.bias, qty.scale
        sup = (
            f"{qty.name}     [nominal = {qty.nominal:.4g}]\n"
            f"Bias: {b.label}  moy={b.moy:.4g}, var={b.var:.4g}, \u03c3={b.sigma:.4g}"
            f"   \u00b7   "
            f"Scale: {sc.label}  moy={sc.moy:.4g}, var={sc.var:.4g}, \u03c3={sc.sigma:.4g}"
        )
        set_suptitle(fig, sup, fontsize=10)
        fig.subplots_adjust(bottom=0.18, top=0.82)

    return fig, axes


# ---------------------------------------------------------------------------
# plot_dispersion_matrix
# ---------------------------------------------------------------------------

def plot_dispersion_matrix(
    qty_list: list[QuantityDispersion],
    n: int = 10000,
    share_x: bool = True,
    rng: np.random.Generator | None = None,
    ncols: int | None = None,
    bins: int = 60,
) -> tuple:
    """Grid of PDF subplots — one per quantity — for side-by-side comparison.

    Each subplot shows the histogram, KDE, E[X] / Nominal lines, and three
    nested ±kσ shaded bands.

    Parameters
    ----------
    qty_list:
        Ordered list of quantities to compare.
    n:
        Number of samples per quantity.
    share_x:
        When *True*, all subplots share the same x-axis span so distributions
        are visually comparable.
    rng:
        Optional random generator.
    ncols:
        Number of columns.  Defaults to ``min(len(qty_list), 4)``.
    bins:
        Histogram bins per subplot.

    Returns
    -------
    fig, axes  — axes is a 2-D ndarray (nrows × ncols)
    """
    m = len(qty_list)
    if m == 0:
        raise ValueError("qty_list must not be empty")

    nc = ncols if ncols is not None else min(m, 4)
    nr = int(np.ceil(m / nc))

    with style_context(_PROFILE):
        fig, axes = plt.subplots(nr, nc, figsize=(5.5 * nc, 5.0 * nr), squeeze=False, layout="none")

        all_samples: list[np.ndarray] = [qty.sample(n, rng=rng) for qty in qty_list]

        if share_x:
            gmin = min(s.min() for s in all_samples)
            gmax = max(s.max() for s in all_samples)
            margin = (gmax - gmin) * 0.06
            xlim: tuple | None = (gmin - margin, gmax + margin)
        else:
            xlim = None

        prop_colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]

        for idx, (qty, samples) in enumerate(zip(qty_list, all_samples)):
            row, col = divmod(idx, nc)
            ax = axes[row, col]
            c = prop_colors[idx % len(prop_colors)]
            mean_s = float(np.mean(samples))
            std_s = float(np.std(samples))
            x_range = samples.max() - samples.min()

            # Histogram
            ax.hist(samples, bins=bins, density=True, color=c, alpha=0.22, zorder=2)

            # KDE
            if x_range > 0:
                try:
                    kde = gaussian_kde(samples)
                    x_lo = xlim[0] if xlim else samples.min() - 0.08 * x_range
                    x_hi = xlim[1] if xlim else samples.max() + 0.08 * x_range
                    x_grid = np.linspace(x_lo, x_hi, 500)
                    ax.plot(x_grid, kde(x_grid), color=c, lw=2, label="KDE", zorder=4)
                except Exception:
                    pass

            # Reference lines
            ax.axvline(qty.nominal, color="0.20", ls="--", lw=1.5, label="Nominal", zorder=5)
            ax.axvline(mean_s, color=c, ls=(0, (4, 2)), lw=2.2, label="E[X]", zorder=6)

            # Sigma bands (no legend labels — kept compact for matrix panels)
            if std_s > 1e-10:
                for k, alpha in [(1, 0.13), (2, 0.08), (3, 0.04)]:
                    ax.axvspan(
                        mean_s - k * std_s, mean_s + k * std_s,
                        alpha=alpha, color=c, zorder=1,
                    )
                # Edge lines for ±1σ (just the innermost band for clarity)
                for sign in (-1, +1):
                    ax.axvline(
                        mean_s + sign * std_s,
                        color="0.65", ls="-", lw=0.8, alpha=0.5, zorder=3,
                    )
                    ax.axvline(
                        mean_s + sign * 2 * std_s,
                        color="0.65", ls="--", lw=0.7, alpha=0.4, zorder=3,
                    )
                    ax.axvline(
                        mean_s + sign * 3 * std_s,
                        color="0.65", ls=":", lw=0.6, alpha=0.3, zorder=3,
                    )

            # Stats textbox (compact — E[X] and σ only)
            add_textbox(ax, _stats_textbox(mean_s, std_s), loc="upper left", fontsize=9)

            if xlim:
                ax.set_xlim(xlim)

            set_title(ax, qty.name, fontsize=11)
            ax.set_xlabel(qty.name, fontsize=10)
            ax.set_ylabel("Density", fontsize=10)

            apply_oldschool_axes(
                ax, legend=True,
                legend_kwargs={"fontsize": 8.5, "loc": "upper right", "ncol": 1},
            )

            # Sigma axis labels
            _add_sigma_axis_labels(ax, mean_s, std_s, fontsize=8.5)

        for idx in range(m, nr * nc):
            row, col = divmod(idx, nc)
            axes[row, col].set_visible(False)

        set_suptitle(fig, "Dispersion comparison", fontsize=13, fontweight="bold")
        fig.subplots_adjust(bottom=0.18, hspace=0.45)

    return fig, axes
