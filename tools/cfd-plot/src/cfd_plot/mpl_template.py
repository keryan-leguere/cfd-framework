"""
mpl_template — Matplotlib figure template with style profiles and smart export.

Provides:
    use_style(profile)            — apply a style profile globally
    style_context(profile)        — context-manager for temporary style
    new_figure(...)               — wrapper around plt.subplots with profile support
    save_figure(...)              — export normal + optional "declassified" variant
    plot_line(ax, x, y, ...)      — line+marker plot with white-filled markers
    apply_marker_style(line)      — retrofit marker style on an existing Line2D
    make_legend(ax, ...)          — legend with old-style frame defaults
    plot_with_band(ax, ...)       — line + shaded uncertainty band
    fill_between_curves(ax, ...)  — shade the area between two curves
    add_reference_lines(ax, ...)  — horizontal / vertical reference lines
    sync_axes_limits(axes, ...)   — match x/y limits across subplots to their shared data range
    apply_oldschool_axes(ax)      — cosmetic polish (spines, ticks, legend)
    add_textbox(ax, text, ...)    — anchored metadata text box
    set_axis_sci(ax, ...)         — clean scientific notation on axis
    annotate_point(ax, ...)       — annotation arrow with consistent styling
    plot_bar(ax, ...)             — bar chart with old-style edge styling
    dual_axis(ax, ...)            — styled twinx secondary Y-axis
    set_subtitle(ax, text, ...)   — subtitle line below the axes title
    print_file_report(files)      — pretty-print exported file summary (Rich / plain)

Font setup:
    TITLE_FONT                    — font family string for titles (TeX Gyre Heros)
    BODY_FONT                     — font family string for body text (TeX Gyre Termes)
    register_fonts()              — (re-)register bundled fonts with Matplotlib

Profiles: "notebook", "slides", "paper"
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.artist import Artist
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from cfd_plot._compat import zip_strict

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PKG_DIR = Path(__file__).resolve().parent
_STYLES_DIR = _PKG_DIR / "styles"
_FONTS_DIR = _PKG_DIR / "fonts"

_VALID_PROFILES = ("notebook", "slides", "paper")

DeclassifyAxis = Literal["x", "y", "both"]

# ---------------------------------------------------------------------------
# Font registration — bundled TeX Gyre fonts
# ---------------------------------------------------------------------------
# TeX Gyre Heros  ≈ Helvetica   (sans-serif, used for titles)
# TeX Gyre Termes ≈ Times New Roman (serif, used for body/labels/ticks)

TITLE_FONT: str = "TeX Gyre Heros"
BODY_FONT: str = "TeX Gyre Termes"

_TITLE_FALLBACKS = ("Helvetica", "Nimbus Sans", "Arial", "DejaVu Sans")
_BODY_FALLBACKS = ("Times New Roman", "Nimbus Roman", "DejaVu Serif")


def register_fonts() -> None:
    """Register all ``.otf`` / ``.ttf`` fonts in the bundled ``fonts/`` dir.

    Called automatically at import time.  Safe to call again if you add
    fonts to the directory at runtime.
    """
    if not _FONTS_DIR.is_dir():
        logger.debug("No bundled fonts directory: %s", _FONTS_DIR)
        return
    from matplotlib import font_manager

    for ext in ("*.otf", "*.ttf"):
        for font_path in _FONTS_DIR.glob(ext):
            font_manager.fontManager.addfont(str(font_path))
    logger.debug("Registered bundled fonts from %s", _FONTS_DIR)


def _resolve_font(preferred: str, fallbacks: tuple[str, ...]) -> str:
    """Return *preferred* if registered, otherwise the first available fallback."""
    from matplotlib import font_manager

    available = {f.name for f in font_manager.fontManager.ttflist}
    if preferred in available:
        return preferred
    for fb in fallbacks:
        if fb in available:
            logger.info("Font %r not found, falling back to %r", preferred, fb)
            return fb
    logger.warning("No suitable font found for %r; using matplotlib default", preferred)
    return preferred


# Run once at import time
register_fonts()
TITLE_FONT = _resolve_font(TITLE_FONT, _TITLE_FALLBACKS)
BODY_FONT = _resolve_font(BODY_FONT, _BODY_FALLBACKS)


# ---------------------------------------------------------------------------
# Style application
# ---------------------------------------------------------------------------


def _style_path(profile: str) -> str:
    """Return the absolute path to a .mplstyle file for *profile*."""
    if profile not in _VALID_PROFILES:
        raise ValueError(f"Unknown profile {profile!r}. Choose from {_VALID_PROFILES}.")
    path = _STYLES_DIR / f"{profile}.mplstyle"
    if not path.exists():
        raise FileNotFoundError(f"Style file not found: {path}")
    return str(path)


def use_style(profile: str = "notebook") -> None:
    """Apply a style profile **globally** (modifies rcParams in place).

    Parameters
    ----------
    profile : str
        One of ``"notebook"``, ``"slides"``, ``"paper"``.
    """
    mpl.style.use(_style_path(profile))


@contextmanager
def style_context(profile: str = "notebook"):
    """Temporarily apply a style profile (context manager).

    Usage::

        with style_context("slides"):
            fig, ax = plt.subplots()
            ...
    """
    with mpl.style.context(_style_path(profile)):
        yield


# ---------------------------------------------------------------------------
# Figure creation helper
# ---------------------------------------------------------------------------


def new_figure(
    nrows: int = 1,
    ncols: int = 1,
    *,
    profile: str | None = None,
    figsize: tuple[float, float] | None = None,
    **subplots_kw,
) -> tuple[Figure, Any]:
    """Create a new figure (thin wrapper around ``plt.subplots``).

    Parameters
    ----------
    nrows, ncols : int
        Subplot grid dimensions.
    profile : str, optional
        If given, the style is applied via a context manager so only this
        figure inherits the profile settings.
    figsize : tuple, optional
        Override ``figsize`` from the profile.
    **subplots_kw
        Forwarded to ``plt.subplots``.

    Returns
    -------
    fig, axes
    """
    ctx = style_context(profile) if profile else _noop_context()
    with ctx:
        kw = dict(subplots_kw)
        if figsize is not None:
            kw["figsize"] = figsize
        fig, axes = plt.subplots(nrows, ncols, **kw)
    return fig, axes


@contextmanager
def _noop_context():
    yield


# ---------------------------------------------------------------------------
# Marker helpers
# ---------------------------------------------------------------------------

# NB: the marker look is applied by apply_marker_style() below, not by a
# defaults dict. A `_MARKER_DEFAULTS` constant used to sit here, unreferenced
# by anything — editing its markerfacecolor changed nothing, which is exactly
# the sort of trap that wastes an afternoon. Change apply_marker_style().


def plot_line(
    ax,
    x,
    y,
    *,
    marker: str = "o",
    label: str | None = None,
    **kwargs,
) -> Line2D:
    """Plot a line with **white-filled markers** whose edge matches the line color.

    All extra *kwargs* are forwarded to ``ax.plot``.  The returned object is
    the ``Line2D`` instance.
    """
    # Let matplotlib pick the color from the cycle if not explicit
    (line,) = ax.plot(x, y, marker=marker, label=label, **kwargs)
    apply_marker_style(line)
    return line


def apply_marker_style(line: Line2D) -> None:
    """Set white face + edge-color matching the line color on *line*."""
    color = line.get_color()
    line.set_markerfacecolor("white")
    line.set_markeredgecolor(color)
    # Use rcParams markeredgewidth if not already overridden
    if line.get_markeredgewidth() == mpl.rcParams.get("lines.markeredgewidth", 1.0):
        pass  # already set by the style sheet — keep it
    # Ensure marker edge width is at least reasonable
    mew = line.get_markeredgewidth()
    if mew < 1.0:
        line.set_markeredgewidth(1.2)


# ---------------------------------------------------------------------------
# Legend helper
# ---------------------------------------------------------------------------

_LEGEND_DEFAULTS: dict = dict(
    frameon=True,
    fancybox=False,
    framealpha=1.0,
)


def _resolve_legend_edgecolor(edge):
    """Resolve a legend edge colour, honouring Matplotlib's ``"inherit"``.

    ``legend.edgecolor`` legally accepts the string ``"inherit"`` (it is what
    Matplotlib's own ``classic`` style ships), meaning "use ``axes.edgecolor``".
    Passing it straight to ``set_edgecolor`` raises
    ``ValueError: Invalid RGBA argument: 'inherit'``, so translate it here.
    """
    if edge is None:
        edge = mpl.rcParams.get("legend.edgecolor", "0.15")
    if isinstance(edge, str) and edge == "inherit":
        edge = mpl.rcParams.get("axes.edgecolor", "0.15")
    return edge


def make_legend(ax, **kwargs):
    """Create a legend with old-style defaults and a guaranteed thick frame.

    Calls ``ax.legend()`` with sensible defaults (square frame, opaque
    background) then enforces a visible frame linewidth.  Every kwarg
    accepted by ``ax.legend()`` is forwarded — explicit values always
    win over the defaults.

    Extra keyword ``frame_linewidth`` (not a Matplotlib kwarg) is
    intercepted and applied to the legend frame after creation.

    Returns the ``Legend`` object so you can keep tweaking it.
    """
    frame_lw = kwargs.pop("frame_linewidth", None)
    edge = kwargs.get("edgecolor")

    merged = {**_LEGEND_DEFAULTS, **kwargs}
    leg = ax.legend(**merged)

    if frame_lw is None:
        frame_lw = mpl.rcParams.get("patch.linewidth", 1.0)
        frame_lw = max(frame_lw, 1.2)
    leg.get_frame().set_linewidth(frame_lw)

    leg.get_frame().set_edgecolor(_resolve_legend_edgecolor(edge))

    return leg


def make_figure_legend(
    fig: Figure,
    axes=None,
    *,
    loc: str = "center right",
    bbox_to_anchor: tuple[float, float] = (1.02, 0.5),
    ncol: int = 1,
    dedupe: bool = True,
    frame_linewidth: float | None = None,
    **kwargs,
):
    """Create a single legend for the whole figure, aggregating handles from
    multiple axes.

    Useful when several subplots share the same series and you want one
    legend placed outside the plot area (e.g. to the right).

    Parameters
    ----------
    fig : Figure
    axes : Axes or sequence of Axes, optional
        Axes to collect handles from.  ``None`` means all axes in *fig*.
    loc : str
        Legend location string (Matplotlib convention).
    bbox_to_anchor : tuple
        Anchor point in figure coordinates.
    ncol : int
        Number of columns.
    dedupe : bool
        Remove duplicate labels (keeps first occurrence).
    frame_linewidth : float, optional
        Legend frame thickness.  Defaults to ``patch.linewidth`` from
        rcParams (at least 1.2).
    **kwargs
        Forwarded to ``fig.legend()``.

    Returns
    -------
    Legend
    """
    if axes is None:
        axes = fig.get_axes()
    elif not hasattr(axes, "__iter__"):
        axes = [axes]

    handles: list[Artist] = []
    labels: list[str] = []
    seen: set[str] = set()
    for ax in axes:
        for h, lbl in zip_strict(*ax.get_legend_handles_labels()):
            if dedupe and lbl in seen:
                continue
            seen.add(lbl)
            handles.append(h)
            labels.append(lbl)

    merged = {**_LEGEND_DEFAULTS, **kwargs}
    # `loc` is a plain str here (Matplotlib accepts any location string at
    # runtime); the stub narrows it to a Literal union.
    leg = fig.legend(  # type: ignore[call-overload]
        handles,
        labels,
        loc=loc,
        bbox_to_anchor=bbox_to_anchor,
        ncol=ncol,
        **merged,
    )

    if frame_linewidth is None:
        frame_linewidth = mpl.rcParams.get("patch.linewidth", 1.0)
        frame_linewidth = max(frame_linewidth, 1.2)
    leg.get_frame().set_linewidth(frame_linewidth)

    edge = kwargs.get("edgecolor")
    leg.get_frame().set_edgecolor(_resolve_legend_edgecolor(edge))

    return leg


def add_shared_colorbar(
    fig: Figure,
    mappable,
    *,
    axes=None,
    location: str = "right",
    size: str = "2%",
    pad: float = 0.02,
    match_axes: bool = True,
    label: str | None = None,
    **kwargs,
):
    """Add a single colorbar shared across multiple axes.

    When *match_axes* is ``True`` (default), the colorbar height (or
    width for horizontal layouts) is computed from the bounding box of
    the target axes so it aligns visually.

    Parameters
    ----------
    fig : Figure
    mappable : ScalarMappable
        The artist to attach the colorbar to (e.g. a QuadMesh from
        ``pcolormesh`` or a ContourSet from ``contourf``).
    axes : Axes or sequence of Axes, optional
        Axes the colorbar should span.  ``None`` means all axes.
    location : str
        ``"right"`` or ``"bottom"``.
    size : str
        Width of the colorbar axis as a percentage string (e.g.
        ``"2%"``).  Interpreted as a fraction of the figure dimension.
    pad : float
        Padding between the axes group and the colorbar (in figure
        fraction).
    match_axes : bool
        Resize the colorbar axis to match the vertical (or horizontal)
        extent of the target axes group.
    label : str, optional
        Colorbar label text.
    **kwargs
        Forwarded to ``fig.colorbar()``.

    Returns
    -------
    Colorbar
    """
    if axes is None:
        axes = fig.get_axes()
    elif not hasattr(axes, "__iter__"):
        axes = [axes]

    if match_axes and len(axes) >= 1:
        fig.canvas.draw_idle()

        bboxes = [ax.get_position() for ax in axes]
        pct = float(size.strip().rstrip("%")) / 100.0

        if location == "right":
            x0 = max(b.x1 for b in bboxes) + pad
            y0 = min(b.y0 for b in bboxes)
            y1 = max(b.y1 for b in bboxes)
            cax = fig.add_axes((x0, y0, pct, y1 - y0))
        elif location == "bottom":
            x0 = min(b.x0 for b in bboxes)
            x1 = max(b.x1 for b in bboxes)
            y0 = min(b.y0 for b in bboxes) - pad
            cax = fig.add_axes((x0, y0 - pct, x1 - x0, pct))
        else:
            raise ValueError(
                f"location={location!r} not supported; use 'right' or 'bottom'"
            )
        kwargs["cax"] = cax

    cbar = fig.colorbar(mappable, **kwargs)
    if label:
        cbar.set_label(label)
    return cbar


# ---------------------------------------------------------------------------
# Multi-panel axes helpers
# ---------------------------------------------------------------------------


def sync_axes_limits(axes, *, which: str = "y", margin: float | None = None) -> None:
    """Give every axis in *axes* the same data-driven limits.

    For each requested dimension, scans every axis's plotted data for its
    min/max, takes the overall min/max across *all* axes, pads it the same
    way Matplotlib's own autoscale would, and applies that shared range to
    every individual axis — so panels sharing a figure (e.g. subplots
    comparing several flight points) become directly comparable.

    Every kind of drawn data is scanned, not just curves:

    - **lines** — ``ax.plot`` / :func:`plot_line`, and the line part of
      ``ax.errorbar``;
    - **collections** — ``ax.scatter``, ``ax.fill_between`` (so the band of
      :func:`plot_with_band` is included, not clipped), ``pcolormesh``, …;
    - **patches** — ``ax.bar`` / :func:`plot_bar`;
    - **images** — ``ax.imshow`` (via its extent).

    Artists drawn in a *blended* transform are deliberately ignored, because
    they mark a position rather than carry data: reference lines from
    ``ax.axhline`` / ``ax.axvline`` (:func:`add_reference_lines`) and spans
    from ``ax.axhspan`` / ``ax.axvspan``. A reference line at an arbitrary
    value therefore cannot blow up the shared scale. Invisible artists are
    skipped too.

    Parameters
    ----------
    axes : Axes or array-like of Axes
        The axes to synchronize, e.g. ``fig.axes`` or the array returned by
        ``plt.subplots``.
    which : {"y", "x", "both"}
        Which axis/axes to synchronize. Defaults to ``"y"``.
    margin : float, optional
        Fractional padding added on each side of the shared min/max, as a
        fraction of the data span (same convention as ``ax.margins()``).
        Defaults to :rc:`axes.xmargin` / :rc:`axes.ymargin` (Matplotlib's own
        autoscale default, normally 0.05) so synced axes keep the same
        natural breathing room a single autoscaled axis would have.

    Returns
    -------
    None
    """
    import numpy as _np

    if hasattr(axes, "ravel"):
        axes = axes.ravel()
    elif not hasattr(axes, "__iter__"):
        axes = [axes]
    axes = list(axes)

    if which not in ("x", "y", "both"):
        raise ValueError(f"which={which!r} not supported; use 'x', 'y', or 'both'")
    dims = ("x", "y") if which == "both" else (which,)

    def _bbox_span(bbox, dim: str) -> tuple[float, float] | None:
        lo, hi = (bbox.x0, bbox.x1) if dim == "x" else (bbox.y0, bbox.y1)
        if not (_np.isfinite(lo) and _np.isfinite(hi)):
            return None
        return (lo, hi) if lo <= hi else (hi, lo)

    def _data_bounds(ax, dim: str) -> tuple[float, float] | None:
        spans: list[tuple[float, float]] = []

        # Lines. A pure-data transform tells a real curve apart from an
        # axhline/axvline, which uses a blended (axes, data) transform.
        for line in ax.get_lines():
            if not line.get_visible() or line.get_transform() is not ax.transData:
                continue
            data = _np.asarray(
                line.get_xdata() if dim == "x" else line.get_ydata(), dtype=float
            )
            data = data[_np.isfinite(data)]
            if data.size:
                spans.append((float(data.min()), float(data.max())))

        # Collections: scatter, fill_between, pcolormesh, … Their transform is
        # not comparable to transData (scatter positions points through an
        # *offset* transform), so ask them to project their own extent onto it
        # — the same call Matplotlib uses to build ax.dataLim.
        for coll in ax.collections:
            if not coll.get_visible():
                continue
            try:
                span = _bbox_span(coll.get_datalim(ax.transData), dim)
            except (ValueError, TypeError, AttributeError):
                continue
            if span is not None:
                spans.append(span)

        # Patches: bar charts. axhspan/axvspan are excluded by the transform
        # check, consistently with axhline/axvline above.
        for patch in ax.patches:
            if not patch.get_visible() or patch.get_data_transform() is not ax.transData:
                continue
            span = _bbox_span(patch.get_path().get_extents(patch.get_patch_transform()), dim)
            if span is not None:
                spans.append(span)

        # Images carry their extent rather than point data.
        for image in ax.images:
            if not image.get_visible():
                continue
            extent = image.get_extent()
            span = (extent[0], extent[1]) if dim == "x" else (extent[2], extent[3])
            if all(_np.isfinite(v) for v in span):
                spans.append((min(span), max(span)))

        if not spans:
            return None
        return min(s[0] for s in spans), max(s[1] for s in spans)

    def _sticky_values(ax, dim: str) -> list[float]:
        """Values the padding must not cross, e.g. the y=0 baseline of bars."""
        values: list[float] = []
        for artist in (*ax.get_lines(), *ax.collections, *ax.patches, *ax.images):
            if not artist.get_visible():
                continue
            edges = getattr(artist, "sticky_edges", None)
            if edges is None:
                continue
            values.extend(
                float(v)
                for v in (edges.x if dim == "x" else edges.y)
                if _np.isfinite(v)
            )
        return values

    for dim in dims:
        bounds = [b for ax in axes if (b := _data_bounds(ax, dim)) is not None]
        if not bounds:
            continue
        lo = min(b[0] for b in bounds)
        hi = max(b[1] for b in bounds)

        pad_frac = (
            margin
            if margin is not None
            # Key is built at runtime; the RcParams stub only accepts literals.
            else mpl.rcParams[f"axes.{dim}margin"]  # type: ignore[index]
        )
        span = hi - lo
        pad = span * pad_frac if span > 0 else (abs(lo) or 1.0) * pad_frac

        # Honour sticky edges the way Matplotlib's own autoscale does, so a bar
        # chart keeps sitting on its baseline instead of floating above it.
        sticky = [v for ax in axes for v in _sticky_values(ax, dim)]
        below = [v for v in sticky if v <= lo]
        above = [v for v in sticky if v >= hi]
        lo = max(lo - pad, max(below)) if below else lo - pad
        hi = min(hi + pad, min(above)) if above else hi + pad

        for ax in axes:
            ax.set_xlim(lo, hi) if dim == "x" else ax.set_ylim(lo, hi)


# ---------------------------------------------------------------------------
# Matplotlib-native plot helpers
# ---------------------------------------------------------------------------


def plot_with_band(
    ax,
    x,
    y,
    *,
    y_low=None,
    y_high=None,
    band_alpha: float = 0.15,
    band_color: str | None = None,
    band_label: str | None = None,
    **line_kwargs,
) -> tuple[Line2D, mpl.collections.PolyCollection | None]:
    """Plot a line with an optional shaded uncertainty band.

    Thin wrapper around ``plot_line`` + ``ax.fill_between``.  Returns
    ``(line, poly)`` where *poly* is ``None`` when no band is drawn.

    Parameters
    ----------
    y_low, y_high : array-like, optional
        Lower / upper band boundaries.  If only *y_low* is given it is
        treated as a symmetric half-width (band = y +/- y_low).
    band_alpha : float
        Opacity of the shaded area.
    band_color : str, optional
        Band colour.  Defaults to the line colour.
    **line_kwargs
        Forwarded to ``plot_line`` (marker, label, linestyle, …).
    """
    line = plot_line(ax, x, y, **line_kwargs)
    poly = None

    if y_low is not None:
        import numpy as _np

        y_low = _np.asarray(y_low)
        if y_high is None:
            y_high = _np.asarray(y) + y_low
            y_low = _np.asarray(y) - y_low
        else:
            y_high = _np.asarray(y_high)

        color = band_color or line.get_color()
        poly = ax.fill_between(
            x,
            y_low,
            y_high,
            alpha=band_alpha,
            color=color,
            label=band_label,
        )

    return line, poly


# Default colours of the signed mode: warm where the first curve is above the
# second, cold where it is below. Deliberately the two ends of a diverging
# scale, so "which one wins here" reads without consulting the legend.
_SIGNED_COLORS: tuple[str, str] = ("tab:red", "tab:blue")


def fill_between_curves(
    ax,
    x,
    y1,
    y2=0.0,
    *,
    color=None,
    alpha: float = 0.15,
    label: str | None = None,
    lines: bool = True,
    line_kwargs: dict | None = None,
    signed: bool = False,
    signed_colors: tuple[Any, Any] = _SIGNED_COLORS,
    signed_labels: tuple[str | None, str | None] = (None, None),
    **fill_kwargs,
) -> tuple[list[Line2D], list[mpl.collections.PolyCollection]]:
    """Shade the area between two curves.

    Where :func:`plot_with_band` shades an *uncertainty band around a central
    line*, this shades the *gap between two curves that both matter* — a
    baseline against a modified configuration, a CFD result against wind-tunnel
    data, an envelope's upper and lower bounds.  Neither curve is privileged
    and there is no central line.

    Returns ``(lines, polys)``: the boundary ``Line2D`` artists (empty when
    ``lines=False``) and the ``PolyCollection`` fills (one, or two in signed
    mode).

    Parameters
    ----------
    y1 : array-like
        First curve.
    y2 : array-like or float
        Second curve, or a constant to fill down to.  Defaults to ``0.0``,
        which shades a signed quantity against its zero baseline.
    color : optional
        Colour of the fill *and* of both boundary lines.  When omitted, the
        next colour of the property cycle is used for all three, so the group
        reads as one object.  In signed mode the fills take *signed_colors*
        instead and this only sets the boundary lines, which default to the
        axes' own edge colour.
    alpha : float
        Opacity of the shaded area.  Boundary lines are always opaque.
    label : str, optional
        Legend entry for the fill.  Boundary lines are never labelled; pass
        ``line_kwargs={"label": ...}`` if you want them in the legend too.
    lines : bool
        Draw the two boundary curves.  ``False`` shades the area only, which
        is what you want when the curves are already plotted.
    line_kwargs : dict, optional
        Forwarded to ``ax.plot`` for both boundaries.  Markers are off by
        default: boundaries are read as regions, not as sampled measurements.
    signed : bool
        Split the fill in two, coloured by which curve is on top.  This is the
        useful mode for "where does A beat B?" comparisons.
    signed_colors, signed_labels : 2-tuples
        ``(above, below)`` colours and legend entries for the signed mode,
        where *above* means ``y1 >= y2``.
    **fill_kwargs
        Forwarded to ``ax.fill_between`` (``zorder``, ``hatch``, ``where``, …).
    """
    import numpy as _np

    x = _np.asarray(x, dtype=float)
    y1 = _np.asarray(y1, dtype=float)
    y2 = _np.broadcast_to(_np.asarray(y2, dtype=float), x.shape)

    polys: list[mpl.collections.PolyCollection] = []

    if signed:
        above, below = signed_colors
        lab_above, lab_below = signed_labels
        # interpolate=True makes the fill stop exactly at the crossing points
        # instead of at the last sample before them, which otherwise leaves
        # visible notches wherever the two curves swap places.
        for cond, col, lab in (
            (y1 >= y2, above, lab_above),
            (y1 < y2, below, lab_below),
        ):
            polys.append(
                ax.fill_between(
                    x, y1, y2,
                    where=cond, interpolate=True,
                    color=col, alpha=alpha, label=lab,
                    **fill_kwargs,
                )
            )
        # In signed mode the *fills* carry the meaning, so the boundaries must
        # not compete with them: both get one neutral colour rather than two
        # successive cycle colours, which would read as unrelated series.
        line_color = color if color is not None else mpl.rcParams["axes.edgecolor"]
    else:
        # Passing no colour lets fill_between draw from the property cycle;
        # we then read the colour back so the boundary lines match it.
        if color is not None:
            fill_kwargs["color"] = color
        polys.append(
            ax.fill_between(x, y1, y2, alpha=alpha, label=label, **fill_kwargs)
        )
        line_color = color if color is not None else _facecolor_rgb(polys[0])

    drawn: list[Line2D] = []
    if lines:
        lk: dict[str, Any] = dict(marker="", linewidth=mpl.rcParams["lines.linewidth"])
        if line_color is not None:
            lk["color"] = line_color
        lk.update(line_kwargs or {})
        for y in (y1, y2):
            drawn.extend(ax.plot(x, y, **lk))

    return drawn, polys


def _facecolor_rgb(poly) -> tuple[float, float, float] | None:
    """RGB of a filled collection, alpha dropped, or None if it has no face.

    ``get_facecolor()`` returns an ``(N, 4)`` array with the *fill* alpha
    already baked in; boundary lines want the same hue at full opacity.
    """
    face = poly.get_facecolor()
    if len(face) == 0:
        return None
    return tuple(float(c) for c in face[0][:3])  # type: ignore[return-value]


def add_reference_lines(
    ax,
    *,
    hlines: Sequence[float] | None = None,
    vlines: Sequence[float] | None = None,
    **kwargs,
) -> list:
    """Draw horizontal and/or vertical reference lines.

    Returns a flat list of the ``Line2D`` artists created.

    Parameters
    ----------
    hlines : sequence of float, optional
        Y-values for horizontal lines.
    vlines : sequence of float, optional
        X-values for vertical lines.
    **kwargs
        Forwarded to ``ax.axhline`` / ``ax.axvline``
        (color, linewidth, linestyle, zorder, …).
    """
    defaults = dict(color="0.4", linewidth=0.8, linestyle="--", zorder=0)
    defaults.update(kwargs)

    artists: list = []
    for y_val in hlines or []:
        artists.append(ax.axhline(y=y_val, **defaults))
    for x_val in vlines or []:
        artists.append(ax.axvline(x=x_val, **defaults))
    return artists


def apply_oldschool_axes(
    ax,
    *,
    legend: bool = True,
    legend_kwargs: dict | None = None,
) -> None:
    """Apply old-school finishing touches to *ax* (spines, ticks, legend).

    Does **not** change data or labels — only cosmetic polish.
    """
    for spine in ax.spines.values():
        spine.set_linewidth(mpl.rcParams.get("axes.linewidth", 1.0))
        spine.set_edgecolor(mpl.rcParams.get("axes.edgecolor", "0.15"))

    ax.tick_params(
        axis="both",
        which="major",
        direction="in",
        top=True,
        right=True,
    )
    ax.tick_params(
        axis="both",
        which="minor",
        direction="in",
        top=True,
        right=True,
    )

    if legend and ax.get_legend_handles_labels()[1]:
        make_legend(ax, **(legend_kwargs or {}))


# ---------------------------------------------------------------------------
# Title with TITLE_FONT
# ---------------------------------------------------------------------------


def set_title(ax, text: str, **kwargs) -> mpl.text.Text:
    """Set the axes title using ``TITLE_FONT`` (TeX Gyre Heros ≈ Helvetica).

    All keyword arguments accepted by ``ax.set_title()`` are forwarded;
    ``fontfamily`` defaults to :data:`TITLE_FONT` but can be overridden.

    Returns the ``Text`` object so you can keep tweaking.
    """
    kwargs.setdefault("fontfamily", TITLE_FONT)
    return ax.set_title(text, **kwargs)


def set_suptitle(fig: Figure, text: str, **kwargs) -> mpl.text.Text:
    """Set the figure super-title using ``TITLE_FONT``.

    Thin wrapper around ``fig.suptitle()`` — same interface.
    """
    kwargs.setdefault("fontfamily", TITLE_FONT)
    return fig.suptitle(text, **kwargs)


def set_subtitle(ax, text: str, **kwargs) -> mpl.text.Text:
    """Place a subtitle line just below the axes title.

    The subtitle uses ``TITLE_FONT`` by default, with a font size one
    point smaller than the current title.  The main title is
    automatically shifted upward to avoid overlap.

    Call **after** ``set_title`` (or ``ax.set_title``) so the title
    font size is already resolved.

    Parameters
    ----------
    text : str
        Subtitle text (e.g. ``"M = 0.3, α = 2°"``).
    **kwargs
        Forwarded to ``ax.text`` (``fontsize``, ``color``,
        ``fontfamily``, …).  ``fontsize`` defaults to the title
        font size minus one point.

    Returns
    -------
    matplotlib.text.Text
    """
    from matplotlib.transforms import ScaledTranslation

    title_fontsize = ax.title.get_fontsize()
    fontsize = kwargs.pop("fontsize", title_fontsize - 1)

    kwargs.setdefault("fontfamily", TITLE_FONT)
    kwargs.setdefault("color", "0.40")

    # The title pad lives on the Axes, not on the title Text: there is no
    # Text.get_pad/set_pad (calling them raises AttributeError). Going through
    # ax.set_title() is the public way to change it, but it resets the title's
    # font properties, so save and restore them around the call.
    pad = float(mpl.rcParams["axes.titlepad"])
    title_fp = ax.title.get_fontproperties().copy()
    title_color = ax.title.get_color()
    ax.set_title(ax.get_title(), pad=pad + fontsize + 2)
    ax.title.set_fontproperties(title_fp)
    ax.title.set_color(title_color)

    trans = ax.transAxes + ScaledTranslation(
        0, pad / 72.0, ax.figure.dpi_scale_trans
    )
    return ax.text(
        0.5,
        1.0,
        text,
        transform=trans,
        fontsize=fontsize,
        ha="center",
        va="baseline",
        **kwargs,
    )


def add_textbox(
    ax,
    text: str,
    *,
    loc: str = "upper right",
    fontsize: float | None = None,
    **kwargs,
) -> mpl.text.Text:
    """Place a styled text box inside the axes for case metadata.

    Typical use: display Mach number, Reynolds number, mesh size, or
    solver settings directly on the figure.

    Parameters
    ----------
    text : str
        Content (supports newlines).
    loc : str
        Anchor position.  One of ``"upper left"``, ``"upper right"``,
        ``"center left"``, ``"center right"``,
        ``"lower left"``, ``"lower right"``.
    fontsize : float, optional
        Override font size (defaults to ``font.size`` from rcParams).
    **kwargs
        Forwarded to ``ax.text`` (color, fontfamily, bbox overrides, …).

    Returns
    -------
    matplotlib.text.Text
    """
    _loc_map = {
        "upper left": (0.04, 0.96, "left", "top"),
        "upper right": (0.96, 0.96, "right", "top"),
        "center left": (0.04, 0.50, "left", "center"),
        "center right": (0.96, 0.50, "right", "center"),
        "lower left": (0.04, 0.04, "left", "bottom"),
        "lower right": (0.96, 0.04, "right", "bottom"),
    }
    if loc not in _loc_map:
        raise ValueError(f"loc={loc!r} not in {list(_loc_map)}")

    x_pos, y_pos, ha, va = _loc_map[loc]

    defaults = dict(
        transform=ax.transAxes,
        fontsize=fontsize or mpl.rcParams.get("font.size", 10),
        verticalalignment=va,
        horizontalalignment=ha,
        bbox=dict(
            boxstyle="round,pad=0.4",
            facecolor="white",
            edgecolor="0.30",
            linewidth=mpl.rcParams.get("patch.linewidth", 1.0),
            alpha=0.92,
        ),
    )
    defaults.update(kwargs)
    return ax.text(x_pos, y_pos, text, **defaults)


def set_axis_sci(
    ax,
    axis: str = "y",
    *,
    scilimits: tuple[int, int] = (0, 0),
    useMathText: bool = True,
    useOffset: bool = True,
) -> None:
    """Force scientific notation on an axis with clean formatting.

    Useful for residuals, small pressure differences, etc.

    Parameters
    ----------
    axis : ``"x"``, ``"y"``, or ``"both"``
    scilimits : tuple
        ``(m, n)`` — use sci notation when value < 10^m or > 10^n.
        ``(0, 0)`` means always.
    useMathText : bool
        Render the exponent with Matplotlib's mathtext (e.g. ``x10^3``).
    useOffset : bool
        Allow an additive offset in the tick labels.
    """
    from matplotlib.ticker import ScalarFormatter

    fmt = ScalarFormatter(useMathText=useMathText, useOffset=useOffset)
    fmt.set_powerlimits(scilimits)

    targets = []
    if axis in ("x", "both"):
        targets.append(ax.xaxis)
    if axis in ("y", "both"):
        targets.append(ax.yaxis)

    for ax_obj in targets:
        ax_obj.set_major_formatter(fmt)

    ax.ticklabel_format(style="sci", axis=axis, scilimits=scilimits)


def annotate_point(
    ax,
    text: str,
    xy: tuple[float, float],
    *,
    xytext: tuple[float, float] | None = None,
    offset: tuple[float, float] = (30, 20),
    **kwargs,
) -> mpl.text.Annotation:
    """Add a clean annotation arrow pointing at *xy*.

    Parameters
    ----------
    text : str
        Annotation label.
    xy : tuple
        Data coordinates of the point.
    xytext : tuple, optional
        Text position in data coords.  If ``None``, *offset* (in points)
        is used instead.
    offset : tuple
        ``(dx, dy)`` in points from *xy* (used when *xytext* is ``None``).
    **kwargs
        Forwarded to ``ax.annotate`` (fontsize, color, arrowprops, …).

    Returns
    -------
    matplotlib.text.Annotation
    """
    defaults = dict(
        fontsize=mpl.rcParams.get("font.size", 10),
        color="0.20",
        arrowprops=dict(
            arrowstyle="->",
            color="0.30",
            linewidth=1.2,
            connectionstyle="arc3,rad=0.15",
        ),
        bbox=dict(
            boxstyle="round,pad=0.25",
            facecolor="white",
            edgecolor="0.50",
            linewidth=0.8,
            alpha=0.90,
        ),
    )
    if "arrowprops" in kwargs:
        defaults["arrowprops"].update(kwargs.pop("arrowprops"))
    if "bbox" in kwargs:
        defaults["bbox"].update(kwargs.pop("bbox"))
    defaults.update(kwargs)

    if xytext is not None:
        defaults["xytext"] = xytext
        defaults["textcoords"] = "data"
    else:
        defaults["xytext"] = offset
        defaults["textcoords"] = "offset points"

    return ax.annotate(text, xy=xy, **defaults)


def plot_bar(
    ax,
    categories,
    values,
    *,
    label: str | None = None,
    color: str | None = None,
    edgecolor: str = "0.15",
    edgewidth: float | None = None,
    **kwargs,
) -> mpl.container.BarContainer:
    """Draw a bar chart with old-style edge styling.

    Thin wrapper around ``ax.bar()`` that adds consistent edge colours
    and linewidths matching the library's old-school look.

    Parameters
    ----------
    categories : sequence
        Tick positions or labels.
    values : sequence
        Bar heights.
    edgecolor : str
        Bar border colour (default dark grey).
    edgewidth : float, optional
        Bar border width.  Defaults to ``patch.linewidth`` from rcParams.
    **kwargs
        Forwarded to ``ax.bar`` (width, bottom, align, …).

    Returns
    -------
    BarContainer
    """
    if edgewidth is None:
        edgewidth = mpl.rcParams.get("patch.linewidth", 1.0)

    bars = ax.bar(
        categories,
        values,
        label=label,
        color=color,
        edgecolor=edgecolor,
        linewidth=edgewidth,
        **kwargs,
    )
    return bars


def dual_axis(
    ax,
    *,
    ylabel: str = "",
    color: str | None = None,
) -> mpl.axes.Axes:
    """Create a styled secondary Y-axis (twinx).

    Returns a new ``Axes`` that shares the X-axis with *ax*.  Spine
    color and tick direction are set to match the library's old-school
    look.  If *color* is given the right spine, ticks, and label are
    all tinted to that color for visual distinction.

    Parameters
    ----------
    ylabel : str
        Label for the secondary Y-axis.
    color : str, optional
        Tint the secondary axis elements with this color.

    Returns
    -------
    matplotlib.axes.Axes
        The new right-hand axis.
    """
    ax2 = ax.twinx()

    ax2.set_ylabel(ylabel)

    ax2.tick_params(
        axis="y",
        which="both",
        direction="in",
    )

    if color:
        ax2.set_ylabel(ylabel, color=color)
        ax2.tick_params(axis="y", colors=color)
        ax2.spines["right"].set_edgecolor(color)

    return ax2


# ---------------------------------------------------------------------------
# Rich / plain-text output helpers
# ---------------------------------------------------------------------------

try:
    from rich.console import Console as _Console
    from rich.table import Table as _Table

    _RICH = True
except ImportError:
    _RICH = False

_console = _Console() if _RICH else None


def print_file_report(files: list[Path], *, title: str = "Exported files") -> None:
    """Pretty-print a summary table of exported files.

    Uses Rich when available; falls back to plain ``print``.
    """
    if _RICH and _console is not None:
        table = _Table(title=title, show_lines=False)
        table.add_column("File", style="cyan")
        table.add_column("Format", style="magenta")
        table.add_column("Size", justify="right", style="green")
        for f in files:
            size_kb = f.stat().st_size / 1024
            table.add_row(f.name, f.suffix.lstrip(".").upper(), f"{size_kb:.1f} kB")
        _console.print(table)
    else:
        print(title)
        for f in files:
            size_kb = f.stat().st_size / 1024
            print(f"  {f.name:45s}  {f.suffix.lstrip('.').upper():>4s}  {size_kb:>7.1f} kB")


# ---------------------------------------------------------------------------
# Declassify helpers (internal)
# ---------------------------------------------------------------------------


def _declassify_axes(
    fig: Figure,
    axes_to_modify: Literal["x", "y", "both"],
    label: str = "DECLASSIFIE",
    stamp_kw: dict | None = None,
) -> dict:
    """Remove ticks + ticklabels on requested axes and add a stamped label.

    Returns a *restore_info* dict that ``_restore_axes`` can use to undo
    everything.

    Parameters
    ----------
    label : str
        Text shown on the stamp (default ``"DECLASSIFIE"``).
    stamp_kw : dict, optional
        Override any property of the stamp ``fig.text()`` call.
        Useful keys: ``fontsize``, ``x``, ``y``, ``color``,
        ``bbox`` (dict with ``boxstyle``, ``edgecolor``, ``linewidth``, ...).
    """
    restore: dict[str, list[Any]] = {"axes": [], "texts": []}

    for ax in fig.get_axes():
        info: dict = {"ax": ax}

        if axes_to_modify in ("x", "both"):
            info["xtick_params"] = {
                "labelbottom": True,
                "bottom": True,
            }
            info["xtick_labels"] = [t.get_text() for t in ax.get_xticklabels()]
            info["xtick_locs"] = list(ax.get_xticks())
            ax.tick_params(axis="x", which="both", bottom=False, labelbottom=False)

        if axes_to_modify in ("y", "both"):
            info["ytick_params"] = {
                "labelleft": True,
                "left": True,
            }
            info["ytick_labels"] = [t.get_text() for t in ax.get_yticklabels()]
            info["ytick_locs"] = list(ax.get_yticks())
            ax.tick_params(axis="y", which="both", left=False, labelleft=False)

        restore["axes"].append(info)

    defaults: dict = dict(
        x=0.05,
        y=0.02,
        fontsize=11,
        color="0.20",
        fontfamily="sans-serif",
        fontweight="bold",
        fontstyle="italic",
        ha="left",
        va="bottom",
        bbox=dict(
            boxstyle="square,pad=0.3",
            edgecolor="0.20",
            facecolor="white",
            linewidth=1.6,
            alpha=0.95,
        ),
    )
    if stamp_kw:
        for key, val in stamp_kw.items():
            if key == "bbox" and isinstance(val, dict):
                defaults.setdefault("bbox", {}).update(val)
            else:
                defaults[key] = val

    txt = fig.text(defaults.pop("x"), defaults.pop("y"), label, **defaults)
    restore["texts"].append(txt)

    return restore


def _restore_axes(fig: Figure, restore: dict) -> None:
    """Undo the changes made by ``_declassify_axes``."""
    for info in restore["axes"]:
        ax = info["ax"]
        if "xtick_params" in info:
            ax.tick_params(axis="x", which="both", bottom=True, labelbottom=True)
        if "ytick_params" in info:
            ax.tick_params(axis="y", which="both", left=True, labelleft=True)

    for txt in restore["texts"]:
        txt.remove()

    fig.canvas.draw_idle()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _inkscape_available() -> bool:
    return shutil.which("inkscape") is not None


def _convert_svg_to_emf(svg_path: Path, emf_path: Path) -> None:
    """Convert an SVG file to EMF using Inkscape."""
    try:
        subprocess.run(
            ["inkscape", str(svg_path), f"--export-filename={emf_path}"],
            check=True,
            capture_output=True,
        )
        logger.info("Converted %s -> %s", svg_path, emf_path)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.warning("SVG->EMF conversion failed: %s", exc)


def save_figure(
    fig: Figure,
    path: str | Path,
    *,
    formats: Sequence[str] = ("png",),
    dpi: int | None = None,
    transparent: bool | None = None,
    declassify: DeclassifyAxis | None = None,
    declassify_label: str = "DECLASSIFIE",
    declassify_stamp_kw: dict | None = None,
    report: bool = False,
) -> list[Path]:
    """Save *fig* to disk, optionally producing a declassified variant.

    Parameters
    ----------
    fig : Figure
        The matplotlib figure to save.
    path : str or Path
        Base path **without extension** (e.g. ``"output/fig1"``).
        Directories are created automatically.
    formats : sequence of str
        File formats to export (``"png"``, ``"svg"``, ``"pdf"``, ``"emf"``).
        ``"emf"`` triggers an SVG intermediate + Inkscape conversion.
    dpi : int, optional
        Override DPI (otherwise uses the style's ``savefig.dpi``).
    transparent : bool, optional
        Override transparency.
    declassify : ``"x"`` | ``"y"`` | ``"both"`` | None
        If set, **also** export a second variant with ticks/ticklabels
        removed on the specified axis(es) and a stamped label in the
        bottom-left corner.
    declassify_label : str
        Text shown on the declassified stamp (default ``"DECLASSIFIE"``).
    declassify_stamp_kw : dict, optional
        Override stamp appearance (fontsize, bbox properties, etc.).
        Passed through to ``_declassify_axes``.
    report : bool
        If ``True``, print a summary table of exported files
        (uses Rich when available, plain text otherwise).

    Returns
    -------
    list of Path
        All files that were written.
    """
    base = Path(path)
    base.parent.mkdir(parents=True, exist_ok=True)

    save_kw: dict = {"bbox_inches": "tight"}
    if dpi is not None:
        save_kw["dpi"] = dpi
    if transparent is not None:
        save_kw["transparent"] = transparent

    written: list[Path] = []

    # ---- normal export ----------------------------------------------------
    for fmt in formats:
        if fmt == "emf":
            # Export SVG first, then convert
            svg_tmp = base.with_suffix(".svg")
            fig.savefig(svg_tmp, format="svg", **save_kw)
            emf_out = base.with_suffix(".emf")
            if _inkscape_available():
                _convert_svg_to_emf(svg_tmp, emf_out)
                written.append(emf_out)
            else:
                logger.warning(
                    "Inkscape not found — EMF export skipped.  SVG saved: %s",
                    svg_tmp,
                )
            written.append(svg_tmp)
        else:
            out = base.with_suffix(f".{fmt}")
            fig.savefig(out, format=fmt, **save_kw)
            written.append(out)

    # ---- declassified export ----------------------------------------------
    if declassify is not None:
        restore = _declassify_axes(
            fig,
            declassify,
            label=declassify_label,
            stamp_kw=declassify_stamp_kw,
        )
        suffix_tag = {"x": "declass_x", "y": "declass_y", "both": "declass_xy"}[declassify]
        declass_base = base.parent / f"{base.stem}_{suffix_tag}"

        for fmt in formats:
            if fmt == "emf":
                svg_tmp = declass_base.with_suffix(".svg")
                fig.savefig(svg_tmp, format="svg", **save_kw)
                emf_out = declass_base.with_suffix(".emf")
                if _inkscape_available():
                    _convert_svg_to_emf(svg_tmp, emf_out)
                    written.append(emf_out)
                written.append(svg_tmp)
            else:
                out = declass_base.with_suffix(f".{fmt}")
                fig.savefig(out, format=fmt, **save_kw)
                written.append(out)

        _restore_axes(fig, restore)

    if report:
        print_file_report(written)

    return written
