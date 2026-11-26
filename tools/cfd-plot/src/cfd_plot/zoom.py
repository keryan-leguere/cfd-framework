"""
zoom — magnified views of part of the x axis, for ``batch_plot``.

A zoom is declared on a sweep entry (``sweep_dict`` / ``x_axis_dict``) under
the ``"zoom"`` key and shows one x range of every figure drawn against that
sweep, in one of two ways:

``mode="figure"``
    an extra figure written **beside** the full one,
    ``CN_vs_alpha_ZOOM_0_4.svg``, with the x axis restricted to the range and
    the y axis fitted to what the curves do inside it.
``mode="inset"``
    an inset drawn **on** the full figure, placed where it hides the least
    data, linked to the magnified region by a rectangle and connectors, and
    titled so a reader knows it is a zoom (``Zoom ×4`` by default).
``mode="both"``
    both.

Accepted forms for the ``"zoom"`` value::

    "zoom": (0, 4)                                   # one zoom, default mode
    "zoom": {"xlim": (0, 4), "mode": "inset"}        # options as a dict
    "zoom": ZoomSpec(xlim=(0, 4), mode="both")       # or as a spec
    "zoom": [(0, 4), {"xlim": (8, 12), "mode": "inset"}]   # several

Placement of an inset (``loc="auto"``) is measured, not guessed: the inset's
*whole footprint* — box, tick labels and title — is tried at the eight
corner/edge positions of the axes, and the one covering the fewest samples of
the data actually drawn wins. The magnified region itself and any earlier
inset are hard obstacles: an inset hiding what it magnifies, or another inset,
is never a solution while a free spot exists. When every spot at the default
size covers data, smaller sizes are tried before giving up and taking the
least-covered spot. The legend is then told about the inset (an invisible
rectangle on the parent axes), so ``loc="best"`` steers around it.
"""

from __future__ import annotations

import itertools
import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, fields
from typing import Any

import matplotlib as mpl
import numpy as np
from matplotlib.collections import PolyCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.transforms import Bbox

__all__ = [
    "ZOOM_MODES",
    "ZoomSpec",
    "add_zoom_insets",
    "resolve_zooms",
    "zoom_data_ylim",
    "zoom_factor_label",
]

ZOOM_MODES = ("figure", "inset", "both")

#: Named inset positions accepted by ``loc``, as (horizontal, vertical)
#: anchors in axes fraction: 0 = left/bottom, 0.5 = centre, 1 = right/top.
_NAMED_LOCS: dict[str, tuple[float, float]] = {
    "upper left": (0.0, 1.0),
    "upper center": (0.5, 1.0),
    "upper right": (1.0, 1.0),
    "center left": (0.0, 0.5),
    "center right": (1.0, 0.5),
    "lower left": (0.0, 0.0),
    "lower center": (0.5, 0.0),
    "lower right": (1.0, 0.0),
}

#: Anchors tried by ``loc="auto"``: a 5 x 5 grid over the free room of the
#: axes (0 = flush left/bottom, 1 = flush right/top), ordered corners first,
#: then edges, then the interior — an inset in a corner leaves the middle of
#: the axes, where curves usually cross, alone. The order only breaks ties.
_GRID = (0.0, 0.25, 0.5, 0.75, 1.0)


_CORNER_ORDER = {(0.0, 1.0): 0, (1.0, 1.0): 1, (1.0, 0.0): 2, (0.0, 0.0): 3}


def _anchor_key(anchor: tuple[float, float]) -> tuple[int, int, float]:
    """Sort key: corners (upper left, then clockwise), edges, interior."""
    off_edge = sum(v not in (0.0, 1.0) for v in anchor)
    centrality = abs(anchor[0] - 0.5) + abs(anchor[1] - 0.5)
    return (off_edge, _CORNER_ORDER.get(anchor, 4), -centrality)


_AUTO_ANCHORS: tuple[tuple[float, float], ...] = tuple(
    sorted(
        ((x, y) for x in _GRID for y in _GRID if not (x == 0.5 and y == 0.5)),
        key=_anchor_key,
    )
)


#: Sizes tried, as fractions of the declared one, when nothing fits.
_SHRINK_STEPS = (1.0, 0.85, 0.7)

#: Gap kept between an inset's footprint and the axes frame (axes fraction).
_FRAME_PAD = 0.02

#: Resampling step along each curve when counting what an inset would hide,
#: in axes fraction: a 3-point polyline crossing the box must count as
#: crossing it, not slip between two samples.
_SAMPLE_STEP = 0.004

#: gid of the invisible rectangle that reserves an inset's place for the
#: legend's "best" placement — so it can be found (and is not mistaken for data).
RESERVE_GID = "cfd_plot_zoom_reserve"


@dataclass(frozen=True)
class ZoomSpec:
    """One zoom on the x axis of a batch figure.

    Parameters
    ----------
    xlim :
        ``(xmin, xmax)`` — the x range shown, in data units.
    mode :
        ``"figure"`` (default) writes an extra figure beside the full one;
        ``"inset"`` draws the zoom on the full figure; ``"both"`` does both.
    ylim :
        ``(ymin, ymax)`` to pin the y range; by default it is fitted to every
        curve inside ``xlim`` (values interpolated at the bounds included),
        padded by ``margin``.
    name :
        Suffix of the extra figure's filename, ``<Y>_vs_<X>_ZOOM_<name>``.
        Defaults to the bounds, ``0_4``.
    label :
        Text saying it is a zoom — the inset's title, and the bracketed
        suffix of the extra figure's title. ``None`` gives ``Zoom ×k`` (*k* =
        full x span / zoomed span); ``""`` writes nothing.
    loc :
        Inset position: ``"auto"`` (least hidden data), one of the eight
        Matplotlib names (``"upper left"``, ``"lower center"``, …), or explicit
        bounds ``(x0, y0, width, height)`` in axes fraction.
    size :
        ``(width, height)`` of the inset box in axes fraction. ``"auto"`` may
        shrink it (down to 70 %) when no spot is free.
    margin :
        Fraction of the fitted y span added above and below.
    connectors :
        Draw the lines joining the magnified region to the inset (the
        rectangle around the region is always drawn).
    """

    xlim: tuple[float, float]
    mode: str = "figure"
    ylim: tuple[float, float] | None = None
    name: str | None = None
    label: str | None = None
    loc: str | tuple[float, float, float, float] = "auto"
    size: tuple[float, float] = (0.4, 0.4)
    margin: float = 0.05
    connectors: bool = True

    def __post_init__(self) -> None:
        xlim = _pair(self.xlim, "xlim")
        object.__setattr__(self, "xlim", xlim)
        if not xlim[0] < xlim[1]:
            raise ValueError(f"zoom xlim must be increasing, got {xlim}.")
        if self.ylim is not None:
            ylim = _pair(self.ylim, "ylim")
            if not ylim[0] < ylim[1]:
                raise ValueError(f"zoom ylim must be increasing, got {ylim}.")
            object.__setattr__(self, "ylim", ylim)
        if self.mode not in ZOOM_MODES:
            raise ValueError(f"zoom mode must be one of {ZOOM_MODES}, got {self.mode!r}.")
        if isinstance(self.loc, str):
            if self.loc != "auto" and self.loc not in _NAMED_LOCS:
                raise ValueError(
                    f"zoom loc must be 'auto', one of {sorted(_NAMED_LOCS)} or "
                    f"(x0, y0, width, height), got {self.loc!r}."
                )
        else:
            bounds = tuple(float(v) for v in self.loc)
            if len(bounds) != 4 or bounds[2] <= 0 or bounds[3] <= 0:
                raise ValueError(
                    f"zoom loc bounds must be (x0, y0, width, height) with a "
                    f"positive size, got {self.loc!r}."
                )
            object.__setattr__(self, "loc", bounds)
        size = _pair(self.size, "size")
        if not (0 < size[0] <= 1 and 0 < size[1] <= 1):
            raise ValueError(f"zoom size must lie in (0, 1], got {size}.")
        object.__setattr__(self, "size", size)
        if self.margin < 0:
            raise ValueError(f"zoom margin must be >= 0, got {self.margin}.")
        if self.name is not None and not str(self.name).strip():
            raise ValueError("zoom name must not be empty (omit it for the default).")

    @property
    def wants_figure(self) -> bool:
        return self.mode in ("figure", "both")

    @property
    def wants_inset(self) -> bool:
        return self.mode in ("inset", "both")

    @property
    def file_suffix(self) -> str:
        """``ZOOM_<name>``, the stem suffix of the extra figure."""
        name = self.name if self.name is not None else "_".join(
            _format_bound(v) for v in self.xlim
        )
        return f"ZOOM_{name}"

    def overlaps(self, x: np.ndarray) -> bool:
        """Does a curve sampled at *x* cross the zoomed range at all?"""
        finite = x[np.isfinite(x)]
        if finite.size == 0:
            return False
        return bool(finite.min() <= self.xlim[1] and finite.max() >= self.xlim[0])


def _pair(value: Any, what: str) -> tuple[float, float]:
    try:
        first, second = value
        pair = (float(first), float(second))
    except (TypeError, ValueError):
        raise ValueError(f"zoom {what} must be a pair of numbers, got {value!r}.") from None
    if not all(math.isfinite(v) for v in pair):
        raise ValueError(f"zoom {what} must be finite, got {pair}.")
    return pair


def _format_bound(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.4g}"


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and not isinstance(value, bool)


_SPEC_KEYS = frozenset(f.name for f in fields(ZoomSpec) if not f.name.startswith("_"))


def _one_zoom(value: Any, where: str) -> ZoomSpec:
    try:
        return _build_zoom(value, where)
    except (TypeError, ValueError) as exc:
        message = str(exc)
        if message.startswith(where):
            raise
        raise ValueError(f"{where}: {message}") from None


def _build_zoom(value: Any, where: str) -> ZoomSpec:
    if isinstance(value, ZoomSpec):
        return value
    if isinstance(value, dict):
        unknown = sorted(set(value) - _SPEC_KEYS)
        if unknown:
            raise ValueError(
                f"{where}: unknown zoom key(s) {unknown}; accepted: {sorted(_SPEC_KEYS)}."
            )
        if "xlim" not in value:
            raise ValueError(f"{where}: a zoom dict needs 'xlim': (xmin, xmax).")
        return ZoomSpec(**value)
    if isinstance(value, (list, tuple)) and len(value) == 2 and all(map(_is_number, value)):
        return ZoomSpec(xlim=(value[0], value[1]))
    raise ValueError(
        f"{where}: a zoom is (xmin, xmax), a dict with 'xlim', or a ZoomSpec; got {value!r}."
    )


def resolve_zooms(value: Any, where: str = "zoom") -> tuple[ZoomSpec, ...]:
    """Normalise a sweep entry's ``"zoom"`` value to a tuple of specs.

    A bare pair of numbers is *one* zoom; any other list or tuple is a list of
    zooms. Errors name *where* so a study with ten sweeps says which one is
    wrong. Two zooms that would write the same file are refused.
    """
    if value is None:
        return ()
    if isinstance(value, (ZoomSpec, dict)) or (
        isinstance(value, (list, tuple)) and len(value) == 2 and all(map(_is_number, value))
    ):
        specs: tuple[ZoomSpec, ...] = (_one_zoom(value, where),)
    elif isinstance(value, (list, tuple)):
        specs = tuple(_one_zoom(item, f"{where}[{i}]") for i, item in enumerate(value))
    else:
        raise ValueError(
            f"{where}: a zoom is (xmin, xmax), a dict with 'xlim', a ZoomSpec, or a "
            f"list of those; got {value!r}."
        )
    suffixes = [spec.file_suffix for spec in specs if spec.wants_figure]
    duplicated = sorted({s for s in suffixes if suffixes.count(s) > 1})
    if duplicated:
        raise ValueError(
            f"{where}: several zooms would write the same file {duplicated}; give them "
            "distinct 'name's."
        )
    return specs


# ---------------------------------------------------------------------------
# Limits and labels
# ---------------------------------------------------------------------------


def _y_inside(x: np.ndarray, y: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """y values of a polyline within [lo, hi], bounds interpolated."""
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    if x.size == 0:
        return np.empty(0)
    order = np.argsort(x, kind="stable")
    xs, ys = x[order], y[order]
    inside = ys[(xs >= lo) & (xs <= hi)]
    ends = [b for b in (lo, hi) if xs[0] <= b <= xs[-1]]
    if ends:
        inside = np.concatenate([inside, np.interp(ends, xs, ys)])
    return inside


def zoom_data_ylim(
    spec: ZoomSpec,
    series: Sequence[tuple[np.ndarray, np.ndarray]],
) -> tuple[float, float] | None:
    """The y range a zoom shows: ``spec.ylim``, or fitted to *series* inside it.

    ``None`` when no series has a point in the range (nothing to fit).
    """
    if spec.ylim is not None:
        return spec.ylim
    lo, hi = spec.xlim
    chunks = [_y_inside(np.asarray(x, float), np.asarray(y, float), lo, hi) for x, y in series]
    values = np.concatenate(chunks) if chunks else np.empty(0)
    if values.size == 0:
        return None
    ymin, ymax = float(values.min()), float(values.max())
    span = ymax - ymin
    if span <= 0:
        span = abs(ymin) if ymin != 0 else 1.0
        pad = 0.5 * span * max(spec.margin, 0.05) * 2
    else:
        pad = span * spec.margin
    return ymin - pad, ymax + pad


def zoom_factor_label(spec: ZoomSpec, full_span: float | None) -> str:
    """The zoom's annotation: ``spec.label``, or ``Zoom ×k``."""
    if spec.label is not None:
        return spec.label
    zoom_span = spec.xlim[1] - spec.xlim[0]
    if full_span is None or not math.isfinite(full_span) or full_span <= zoom_span * 1.05:
        return "Zoom"
    factor = full_span / zoom_span
    text = f"{factor:.0f}" if factor >= 10 else f"{factor:.2g}"
    # Plain text: no "$", so the text font draws the sign. A title mixing it
    # with mathtext goes through mathtext_safe where that title is composed.
    return f"Zoom ×{text}"


# ---------------------------------------------------------------------------
# Inset placement
# ---------------------------------------------------------------------------


def _renderer(fig: Any) -> Any:
    getter = getattr(fig.canvas, "get_renderer", None)
    if getter is not None:
        return getter()
    private = getattr(fig, "_get_renderer", None)  # Matplotlib >= 3.6
    if private is not None:
        return private()
    fig.canvas.draw()
    return fig.canvas.get_renderer()


def _data_artists(ax: Any) -> tuple[list[Line2D], list[PolyCollection]]:
    """Lines and filled polygons drawn in data coordinates on *ax*.

    Those are what an inset magnifies and what it must not hide. Artists in
    other coordinates — ``axhline``, annotations, the zoom's own reserve — are
    left out: they are decoration, not data.
    """
    lines = [
        line
        for line in ax.get_lines()
        if line.get_visible() and line.get_transform() is ax.transData
    ]
    polys = [
        coll
        for coll in ax.collections
        if isinstance(coll, PolyCollection)
        and coll.get_visible()
        and coll.get_transform() is ax.transData
    ]
    return lines, polys


def _samples_in_axes(ax: Any, polylines: Sequence[tuple[np.ndarray, bool]]) -> np.ndarray:
    """Every polyline, resampled finely, in axes fraction (inside [0, 1]²).

    Each entry is ``(xy, joined)``: the data points, and whether they are
    drawn joined (a line, a band outline) or as bare markers.
    """
    to_axes = ax.transData + ax.transAxes.inverted()
    chunks: list[np.ndarray] = []
    for raw, joined in polylines:
        xy = np.asarray(raw, float)
        if xy.ndim != 2 or len(xy) == 0:
            continue
        xy = xy[np.all(np.isfinite(xy), axis=1)]
        if len(xy) == 0:
            continue
        pts = to_axes.transform(xy)
        if joined and len(pts) > 1:
            seg = np.diff(pts, axis=0)
            lengths = np.hypot(seg[:, 0], seg[:, 1])
            dense = [pts[:1]]
            for start, step, length in zip(pts[:-1], seg, lengths):
                n = max(math.ceil(length / _SAMPLE_STEP), 1)
                t = np.arange(1, n + 1)[:, None] / n
                dense.append(start + t * step)
            pts = np.concatenate(dense)
        chunks.append(pts)
    if not chunks:
        return np.empty((0, 2))
    pts = np.concatenate(chunks)
    keep = np.all((pts >= 0) & (pts <= 1), axis=1)
    return pts[keep]


def _polylines(lines: Sequence[Line2D], polys: Sequence[PolyCollection]) -> list[tuple[np.ndarray, bool]]:
    out: list[tuple[np.ndarray, bool]] = []
    for line in lines:
        joined = line.get_linestyle() not in ("None", "none", "", " ")
        out.append((np.asarray(line.get_xydata(), float), joined))
    for coll in polys:
        out.extend((np.asarray(path.vertices, float), True) for path in coll.get_paths())
    return out


def _bbox_in_axes(ax: Any, bbox_display: Bbox) -> Bbox:
    return bbox_display.transformed(ax.transAxes.inverted())


def _overlap_area(a: Bbox, b: Bbox) -> float:
    w = min(a.x1, b.x1) - max(a.x0, b.x0)
    h = min(a.y1, b.y1) - max(a.y0, b.y0)
    return max(w, 0.0) * max(h, 0.0)


@dataclass(frozen=True)
class _Footprint:
    """How far an inset's ink reaches beyond its box, in axes fraction."""

    left: float
    bottom: float
    right: float
    top: float


def _measure_footprint(ax: Any, inset: Any, bounds: tuple[float, float, float, float]) -> _Footprint:
    renderer = _renderer(ax.figure)
    tight = _bbox_in_axes(ax, inset.get_tightbbox(renderer))
    x0, y0, w, h = bounds
    return _Footprint(
        left=max(x0 - tight.x0, 0.0),
        bottom=max(y0 - tight.y0, 0.0),
        right=max(tight.x1 - (x0 + w), 0.0),
        top=max(tight.y1 - (y0 + h), 0.0),
    )


def _bounds_at(
    anchor: tuple[float, float], size: tuple[float, float], fp: _Footprint
) -> tuple[tuple[float, float, float, float], Bbox]:
    """Inset box bounds and the footprint bbox, anchored inside the axes."""
    w, h = size
    total_w = w + fp.left + fp.right
    total_h = h + fp.bottom + fp.top
    ax_, ay_ = anchor
    fx0 = _FRAME_PAD + ax_ * (1 - 2 * _FRAME_PAD - total_w)
    fy0 = _FRAME_PAD + ay_ * (1 - 2 * _FRAME_PAD - total_h)
    footprint = Bbox.from_bounds(fx0, fy0, total_w, total_h)
    return (fx0 + fp.left, fy0 + fp.bottom, w, h), footprint


@dataclass(frozen=True)
class _Candidate:
    """One possible spot for one inset."""

    bounds: tuple[float, float, float, float]
    footprint: Bbox
    hidden: int        # data samples the footprint would cover
    shrink: int        # index in _SHRINK_STEPS (0 = declared size)
    rank: int          # position in the preference order, for ties


def _candidates(spec: ZoomSpec, fp: _Footprint, samples: np.ndarray) -> list[_Candidate]:
    if not isinstance(spec.loc, str):
        x0, y0, w, h = spec.loc
        footprint = Bbox.from_bounds(
            x0 - fp.left, y0 - fp.bottom, w + fp.left + fp.right, h + fp.bottom + fp.top
        )
        return [_Candidate((x0, y0, w, h), footprint, _hidden(footprint, samples), 0, 0)]
    anchors = _AUTO_ANCHORS if spec.loc == "auto" else (_NAMED_LOCS[spec.loc],)
    steps = _SHRINK_STEPS if spec.loc == "auto" else (1.0,)
    out: list[_Candidate] = []
    for shrink, scale in enumerate(steps):
        size = (spec.size[0] * scale, spec.size[1] * scale)
        for rank, anchor in enumerate(anchors):
            bounds, footprint = _bounds_at(anchor, size, fp)
            if footprint.width > 1 or footprint.height > 1:
                continue
            out.append(_Candidate(bounds, footprint, _hidden(footprint, samples), shrink, rank))
    if not out:  # the footprint is larger than the axes at every size
        bounds, footprint = _bounds_at(_NAMED_LOCS["upper left"], spec.size, fp)
        out.append(_Candidate(bounds, footprint, _hidden(footprint, samples), 0, 0))
    return out


def _hidden(footprint: Bbox, samples: np.ndarray) -> int:
    if not len(samples):
        return 0
    inside = (
        (samples[:, 0] >= footprint.x0)
        & (samples[:, 0] <= footprint.x1)
        & (samples[:, 1] >= footprint.y0)
        & (samples[:, 1] <= footprint.y1)
    )
    return int(np.count_nonzero(inside))


#: Cost of a forbidden overlap: an inset on a magnified region (its own or
#: another's), on another inset, or on a legend pinned at a fixed spot.
_BLOCKED = 1e6
#: Hidden samples a one-step shrink must save to be worth it — a smaller
#: inset is harder to read, so it is not taken to spare a single point.
_SHRINK_COST = 5.0
#: Above this many insets the joint search gives way to a greedy one, inset
#: after inset.
_JOINT_MAX = 3
#: Candidates kept per inset for the joint search (the cheapest on their
#: own): 3 insets x 24 = 13 824 layouts at most.
_JOINT_KEEP = 24


def _choose_layout(
    options: Sequence[list[_Candidate]],
    regions: Sequence[Bbox],
    obstacles: Sequence[Bbox],
) -> list[_Candidate]:
    """One candidate per inset, minimising the total cost of the layout.

    Placed jointly, not one after the other: a first inset greedily taking
    the best corner can leave the second only a spot on top of the region
    the first one magnifies. Each layout costs the data its insets hide, plus
    a prohibitive price for any inset covering a magnified region, another
    inset or a fixed obstacle, plus a small one per shrink step; ties go to
    the preference order (corners first).
    """

    def own_cost(c: _Candidate) -> float:
        cost = c.hidden + _SHRINK_COST * c.shrink + 1e-3 * c.rank
        cost += _BLOCKED * sum(_overlap_area(c.footprint, r) > 0 for r in regions)
        cost += _BLOCKED * sum(_overlap_area(c.footprint, o) > 0 for o in obstacles)
        return cost

    own = [[own_cost(c) for c in cands] for cands in options]

    if len(options) <= _JOINT_MAX:
        kept = [
            sorted(range(len(cands)), key=costs.__getitem__)[:_JOINT_KEEP]
            for cands, costs in zip(options, own)
        ]
        options = [[cands[j] for j in idx] for cands, idx in zip(options, kept)]
        own = [[costs[j] for j in idx] for costs, idx in zip(own, kept)]
        best: tuple[float, tuple[int, ...]] | None = None
        for combo in itertools.product(*(range(len(c)) for c in options)):
            cost = sum(own[i][j] for i, j in enumerate(combo))
            if best is not None and cost >= best[0]:
                continue
            for a in range(len(combo)):
                for b in range(a + 1, len(combo)):
                    fa = options[a][combo[a]].footprint
                    fb = options[b][combo[b]].footprint
                    if _overlap_area(fa, fb) > 0:
                        cost += _BLOCKED
            if best is None or cost < best[0]:
                best = (cost, combo)
        assert best is not None
        return [options[i][j] for i, j in enumerate(best[1])]

    chosen: list[_Candidate] = []
    for i, cands in enumerate(options):
        def total(j: int, i: int = i, cands: list[_Candidate] = cands) -> float:
            fp = cands[j].footprint
            return own[i][j] + _BLOCKED * sum(
                _overlap_area(fp, c.footprint) > 0 for c in chosen
            )

        chosen.append(cands[min(range(len(cands)), key=total)])
    return chosen


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def _copy_line(src: Line2D, dst_ax: Any) -> None:
    x, y = src.get_xdata(), src.get_ydata()
    dst_ax.plot(
        x,
        y,
        color=src.get_color(),
        linestyle=src.get_linestyle(),
        linewidth=src.get_linewidth(),
        marker=src.get_marker(),
        markersize=src.get_markersize(),
        markerfacecolor=src.get_markerfacecolor(),
        markeredgecolor=src.get_markeredgecolor(),
        markeredgewidth=src.get_markeredgewidth(),
        drawstyle=src.get_drawstyle(),
        alpha=src.get_alpha(),
        zorder=src.get_zorder(),
        label="_nolegend_",
    )


def _copy_poly(src: PolyCollection, dst_ax: Any) -> None:
    verts = [path.vertices for path in src.get_paths()]
    copy = PolyCollection(
        verts,
        facecolors=src.get_facecolor(),
        edgecolors=src.get_edgecolor(),
        linewidths=src.get_linewidth(),
        zorder=src.get_zorder(),
    )
    hatch = src.get_hatch()
    if hatch:
        copy.set_hatch(hatch)
    dst_ax.add_collection(copy, autolim=False)


def _fixed_legend_bbox(ax: Any) -> Bbox | None:
    """The legend's bbox when it sits at a fixed spot — ``best`` will move."""
    legend = ax.get_legend()
    if legend is None or not legend.get_visible():
        return None
    if getattr(legend, "_loc", 0) == 0:  # "best": it will avoid the inset itself
        return None
    return _bbox_in_axes(ax, legend.get_window_extent(_renderer(ax.figure)))


def _data_x_span(series: Sequence[tuple[np.ndarray, np.ndarray]]) -> float | None:
    """Span of the data along x — the same basis the extra figure uses."""
    xs = [np.asarray(x, float) for x, _ in series]
    xs = [x[np.isfinite(x)] for x in xs]
    xs = [x for x in xs if x.size]
    if not xs:
        return None
    return float(max(x.max() for x in xs) - min(x.min() for x in xs))


def add_zoom_insets(ax: Any, specs: Sequence[ZoomSpec]) -> list[tuple[Any, Bbox]]:
    """Draw every zoom of *specs* as an inset on *ax*.

    Returns ``(inset_axes, footprint)`` per inset actually drawn — a zoom
    whose range holds no data is skipped. Everything drawn on *ax* in data
    coordinates (the batch curves and whatever a hook added: a dispersion
    band, a reference curve) is replicated in each inset, so it magnifies the
    figure as it ships.

    The parent's limits are frozen first: autoscaling after the insets are
    placed would move the data out from under them.
    """
    lines, polys = _data_artists(ax)
    series = [
        (np.asarray(line.get_xdata(), float), np.asarray(line.get_ydata(), float))
        for line in lines
    ]
    for coll in polys:
        for path in coll.get_paths():
            vertices = np.asarray(path.vertices, float)
            series.append((vertices[:, 0], vertices[:, 1]))

    planned: list[tuple[ZoomSpec, tuple[float, float], str]] = []
    full_span = _data_x_span(series)
    for spec in specs:
        if not any(spec.overlaps(x) for x, _ in series):
            continue
        ylim = zoom_data_ylim(spec, series)
        if ylim is None:
            continue
        planned.append((spec, ylim, zoom_factor_label(spec, full_span)))
    if not planned:
        return []

    ax.set_xlim(ax.get_xlim())
    ax.set_ylim(ax.get_ylim())

    def build(
        spec: ZoomSpec, ylim: tuple[float, float], label: str,
        bounds: tuple[float, float, float, float],
    ) -> Any:
        inset = ax.inset_axes(list(bounds))
        for poly in polys:
            _copy_poly(poly, inset)
        for line in lines:
            _copy_line(line, inset)
        if ax.get_xscale() != "linear":
            inset.set_xscale(ax.get_xscale())
        if ax.get_yscale() != "linear":
            inset.set_yscale(ax.get_yscale())
        inset.set_xlim(*spec.xlim)
        inset.set_ylim(*ylim)
        small = 0.8 * float(mpl.rcParams["font.size"])
        inset.tick_params(labelsize=small)
        inset.minorticks_off()
        if label:
            inset.set_title(label, fontsize=small, pad=3)
        return inset

    samples = _samples_in_axes(ax, _polylines(lines, polys))
    to_axes = ax.transData + ax.transAxes.inverted()
    options: list[list[_Candidate]] = []
    regions: list[Bbox] = []
    for spec, ylim, label in planned:
        probe_bounds = (0.3, 0.3, *spec.size)
        probe = build(spec, ylim, label, probe_bounds)
        margins = _measure_footprint(ax, probe, probe_bounds)
        probe.remove()
        options.append(_candidates(spec, margins, samples))
        (rx0, ry0), (rx1, ry1) = to_axes.transform(
            [(spec.xlim[0], ylim[0]), (spec.xlim[1], ylim[1])]
        )
        regions.append(
            Bbox.from_extents(min(rx0, rx1), min(ry0, ry1), max(rx0, rx1), max(ry0, ry1))
        )

    obstacles = [box for box in (_fixed_legend_bbox(ax),) if box is not None]
    layout = _choose_layout(options, regions, obstacles)

    drawn: list[tuple[Any, Bbox]] = []
    for (spec, ylim, label), choice in zip(planned, layout):
        inset = build(spec, ylim, label, choice.bounds)
        with warnings.catch_warnings():
            # Matplotlib may warn about a connector it cannot route; harmless.
            warnings.simplefilter("ignore", UserWarning)
            if spec.connectors:
                ax.indicate_inset_zoom(inset, edgecolor="0.35", alpha=1.0)
            else:
                ax.indicate_inset(
                    (spec.xlim[0], ylim[0], spec.xlim[1] - spec.xlim[0], ylim[1] - ylim[0]),
                    edgecolor="0.35",
                    alpha=1.0,
                )
        # Invisible, but a Rectangle child of the axes: legend loc="best"
        # counts it as an obstacle and steers around the inset.
        ax.add_patch(
            Rectangle(
                (choice.footprint.x0, choice.footprint.y0),
                choice.footprint.width,
                choice.footprint.height,
                transform=ax.transAxes,
                fill=False,
                visible=False,
                gid=RESERVE_GID,
            )
        )
        drawn.append((inset, choice.footprint))
    return drawn
