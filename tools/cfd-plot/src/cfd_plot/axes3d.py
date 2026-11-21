"""
axes3d — make a Matplotlib 3-D axes read like the rest of a paper.

The style profiles are written for 2-D axes, and three of their choices go
wrong in 3-D:

* ``xtick.minor.visible: True`` (paper) draws a grid line per *minor* tick on
  every pane — a mesh so dense the panes turn grey.
* A box in true proportion (``set_box_aspect``) can have one side five times
  shorter than another, and the default locator puts as many ticks on the
  short side as on the long one: the labels run into each other.
* The panes are tinted grey by default, which prints as a muddy block.

:func:`tidy_axes3d` fixes the three, idempotently; :func:`true_proportions`
sets limits and box together so no axis is stretched.

Sizing a 3-D figure
-------------------
Matplotlib draws a 3-D box inside a **square** (the side is the smaller of the
axes' width and height), whatever the box looks like. A tall box — a rocket
climbing 8 km while drifting 2 km — therefore either overflows the axes and is
cut, or sits in a sea of white; and ``bbox_inches="tight"`` does not help, since
a 3-D axes reports its whole square as its extent. Two helpers fix both:

:func:`fit_box3d`
    Zooms the box until its projection fills the square, then sizes the
    (square) figure so the projected box is exactly *width* inches wide.
:func:`bbox3d`
    The real extent of what is drawn — projected box, tick labels, axis labels,
    title, figure legends and texts — to pass as ``savefig(bbox_inches=...)``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from matplotlib.ticker import MaxNLocator, NullLocator
from matplotlib.transforms import Bbox
from numpy.typing import ArrayLike

__all__ = ["bbox3d", "box3d_corners_px", "fit_box3d", "tidy_axes3d", "true_proportions"]


def _axes(ax: Any) -> tuple[Any, Any, Any]:
    if getattr(ax, "name", "") != "3d":
        raise ValueError("expected a 3-D axes (projection='3d')")
    return ax.xaxis, ax.yaxis, ax.zaxis


def true_proportions(
    ax: Any, mins: ArrayLike, maxs: ArrayLike, *, margin: float = 0.0, zoom: float = 1.0
) -> None:
    """Limits ``[mins, maxs]`` (padded by *margin* × largest span) and a box in the same proportions.

    *zoom* < 1 shrinks the box inside the axes: a tall box seen from a turning
    viewpoint (an orbit) otherwise pokes out of the figure at some azimuths.
    """
    _axes(ax)
    lo, hi = np.asarray(mins, dtype=float), np.asarray(maxs, dtype=float)
    spans = hi - lo
    if not spans.max() > 0:
        raise ValueError("the box has no extent")
    pad = margin * float(spans.max())
    lo, hi = lo - pad, hi + pad
    spans = np.maximum(hi - lo, 1e-9 * float(spans.max()))
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[1], hi[1])
    ax.set_zlim(lo[2], hi[2])
    ax.set_box_aspect(tuple(spans), zoom=zoom)


def tidy_axes3d(
    ax: Any,
    *,
    nbins: int = 6,
    min_bins: int = 2,
    pane_color: Any = "white",
    pane_edge: Any = "0.0",
    grid: bool = True,
) -> None:
    """Paper look for a 3-D axes: no minor ticks, white panes, ticks per side length.

    Parameters
    ----------
    nbins : int
        Tick intervals on the **longest** side of the box; the others get
        proportionally fewer (never below *min_bins*), so labels keep the same
        spacing on every side. Call it after the box aspect is set.
    pane_color, pane_edge
        Pane fill and outline.
    grid : bool
        Major grid lines on the panes (colour and width from ``grid.*`` rcParams).
    """
    axes = _axes(ax)
    aspect = np.asarray(ax.get_box_aspect(), dtype=float)
    longest = float(aspect.max()) if aspect.max() > 0 else 1.0
    for axis, side in zip(axes, aspect):
        axis.set_minor_locator(NullLocator())
        bins = max(min_bins, round(nbins * side / longest))
        axis.set_major_locator(MaxNLocator(nbins=bins, steps=[1, 2, 2.5, 5, 10]))
        axis.set_pane_color(pane_color)
        axis.pane.set_edgecolor(pane_edge)
    ax.grid(grid)


def box3d_corners_px(ax: Any) -> np.ndarray:
    """The 8 corners of the axes box, projected, in display pixels ``(8, 2)``."""
    from mpl_toolkits.mplot3d import proj3d

    _axes(ax)
    (x0, x1), (y0, y1), (z0, z1) = ax.get_xlim(), ax.get_ylim(), ax.get_zlim()
    c = np.array([[x, y, z] for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)], dtype=float)
    xs, ys, _ = proj3d.proj_transform(c[:, 0], c[:, 1], c[:, 2], ax.get_proj())
    return np.asarray(ax.transData.transform(np.column_stack([xs, ys])))


def fit_box3d(ax: Any, width: float | None = None, *, fill: float = 0.9, iterations: int = 3) -> float:
    """Fill the axes square with the box and, given *width*, make the projected box that wide.

    With *width*, the figure is made square (that is the shape Matplotlib
    draws 3-D into) and the axes should cover it; crop the result with
    :func:`bbox3d`. Without it — a video frame, whose size is imposed — only
    the zoom changes, so the box fits the axes instead of being cut.
    Returns the zoom applied (also set on the axes).

    Parameters
    ----------
    width : float, optional
        Width of the projected box in inches — tick and axis labels come on top.
    fill : float
        Share of the square the box's larger projected side occupies; the rest
        is room for tick labels that stick out of the square.
    """
    _axes(ax)
    if not 0 < fill <= 1:
        raise ValueError(f"fill must be in (0, 1], got {fill}")
    if width is not None and not width > 0:
        raise ValueError(f"width must be positive, got {width}")
    fig = ax.figure
    aspect = ax.get_box_aspect()
    zoom = 1.0
    for _ in range(max(1, iterations)):
        fig.canvas.draw()
        corners = box3d_corners_px(ax)
        extent = ax.get_window_extent()
        side = min(extent.width, extent.height)
        frac = max(np.ptp(corners[:, 0]), np.ptp(corners[:, 1])) / side
        zoom *= fill / frac
        ax.set_box_aspect(aspect, zoom=zoom)
        if width is None:
            continue
        fig.canvas.draw()
        box_w = np.ptp(box3d_corners_px(ax)[:, 0]) / fig.dpi
        side_in = fig.get_size_inches()[0] * width / box_w
        fig.set_size_inches(side_in, side_in)
    return zoom


def _clipped_out(ax: Any, text: Any) -> bool:
    """A 3-D text clipped to the view limits (``axlim_clip``, Matplotlib ≥ 3.10) and outside them.

    Matplotlib skips drawing it, but its window extent is still computed at its projected
    position, which, once the view is zoomed in, can be kilometres of data away.
    """
    if not getattr(text, "_axlim_clip", False) or not hasattr(text, "get_position_3d"):
        return False
    point = text.get_position_3d()
    limits = (ax.get_xlim(), ax.get_ylim(), ax.get_zlim())
    return any(not min(lim) <= float(v) <= max(lim) for v, lim in zip(point, limits))


def _text3d_extent(ax: Any, text: Any, renderer: Any) -> list[Bbox]:
    """Window extent of a 3-D text **where it is drawn**.

    Outside ``draw``, a ``Text3D`` holds its *data* x, y as its 2-D position, so its
    plain ``get_window_extent`` lands that many pixels away (millions, for metres).
    It is measured at its projected position, then put back.
    """
    from mpl_toolkits.mplot3d import proj3d

    if not text.get_visible() or not text.get_text():
        return []
    position = text.get_position_3d()
    x, y, z = (np.array([float(v)]) for v in position)
    xs, ys, _ = proj3d.proj_transform(x, y, z, ax.get_proj())
    try:
        text.set_position((float(xs[0]), float(ys[0])))
        bb = text.get_window_extent(renderer)
    finally:
        text.set_position_3d(position)
    return [bb] if bb.width > 0 or bb.height > 0 else []


def bbox3d(fig: Any, *, pad: float = 0.04) -> Bbox:
    """Extent (inches) of what is drawn, for ``fig.savefig(..., bbox_inches=bbox3d(fig))``.

    Per 3-D axes: the projected box, the visible tick labels, axis labels,
    title and 3-D texts (except those ``axlim_clip`` hides outside the view
    limits); plus every figure-level legend and text, and the 2-D axes as they
    are. *pad* is added on each side, in inches.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    boxes: list[Bbox] = []

    def add(artist: Any) -> None:
        if artist is None or not artist.get_visible():
            return
        if hasattr(artist, "get_text") and not artist.get_text():
            return
        bb = artist.get_window_extent(renderer)
        if bb.width > 0 or bb.height > 0:
            boxes.append(bb)

    for ax in fig.axes:
        if getattr(ax, "name", "") != "3d":
            boxes.append(ax.get_tightbbox(renderer))
            continue
        corners = box3d_corners_px(ax)
        boxes.append(Bbox([corners.min(axis=0), corners.max(axis=0)]))
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            # Only ticks inside the view: a 3-D axis skips drawing the others but
            # leaves their labels at stale, sometimes astronomical, positions.
            lo, hi = sorted(axis.get_view_interval())
            for tick, loc in zip(axis.get_major_ticks(), axis.get_majorticklocs()):
                if lo - 1e-9 * (hi - lo) <= loc <= hi + 1e-9 * (hi - lo):
                    add(tick.label1)
            add(axis.label)
        add(ax.title)
        for text in ax.texts:
            if _clipped_out(ax, text):
                continue
            if hasattr(text, "get_position_3d"):
                boxes.extend(_text3d_extent(ax, text, renderer))
            else:
                add(text)
        legend = ax.get_legend()
        if legend is not None:
            add(legend)
    for legend in fig.legends:
        add(legend)
    for text in fig.texts:
        add(text)
    union = Bbox.union(boxes).transformed(fig.dpi_scale_trans.inverted())
    return Bbox.from_extents(union.x0 - pad, union.y0 - pad, union.x1 + pad, union.y1 + pad)
