"""Shade and name the regions a curve passes through.

A CFD sweep is rarely one regime. A polar crosses attached flow, then buffet,
then stall; a Mach sweep goes subsonic, transonic, supersonic. The model
usually says so already, as an integer column sampled at the same points as the
curve — ``iDomain``, ``regime``, ``flag``. This module turns that column into
what a reader needs: a light tint behind each region and its **name** written
above it.

    from cfd_plot import plot_domains

    plot_line(ax, mach, cn)
    plot_domains(ax, mach, idomain, domains={
        0: "Subsonic",
        1: {"name": "Transonic", "color": "#D55E00"},
        2: "Supersonic",
    })

The column is read as *runs*: consecutive points sharing a value form one
region, and a value that comes back later (subsonic, transonic, subsonic again)
gets a second region rather than one stretched over the gap.

Ways to delimit, from lightest to heaviest
------------------------------------------
The default — ``alpha=0.12`` fill plus a name above each region — is the
quietest thing that still reads at a glance. The alternatives are there because
the right answer depends on how busy the figure already is:

``alternate=True``
    Tint every *other* region only. The bands still read, and half the figure
    keeps a white background. The best choice when the curve is dense or
    several curves overlap.
``lines=True``
    A thin rule at each boundary. Says exactly *where* the region changes,
    which a soft fill deliberately blurs. Combine with ``fill=False`` for a
    figure that must survive a black-and-white printer.
``Domain(hatch="//")``
    Hatching instead of (or over) colour — the other black-and-white answer,
    and the one that still works when the figure is photocopied.
``legend=True``
    Names in the legend rather than on the figure. For narrow regions, long
    names, or a grid of small panels where a label would not fit.
``label_box=True``
    Each name on a coloured chip. Reads as a ribbon above the axes, and ties
    the name to its tint when the fill is too pale to be sure.

Colour stability across figures
-------------------------------
Region colours are picked from the palette by the domain *value* when it is a
non-negative integer, not by order of appearance: ``iDomain = 2`` is the third
palette colour whether or not domains 0 and 1 happen to occur in this
particular sweep. A figure missing a regime therefore keeps the colours of the
one next to it. Pass explicit colours in *domains* when a study must be pinned
harder than that.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Union

import matplotlib as mpl
import numpy as np
from matplotlib.transforms import ScaledTranslation

from .palettes import DEFAULT_PALETTE, palette_colors

__all__ = [
    "Domain",
    "DomainSpan",
    "domain_segments",
    "plot_domains",
]

# Where a region ends when two samples straddle the change. "midpoint" is the
# default because the model only tells us that the switch happened *between*
# the two, and the midpoint is the only unbiased reading of that.
_BOUNDARY_MODES = ("midpoint", "left", "right")
_LABEL_LOCATIONS = ("top", "inside", "bottom", "none")
_EXTEND_MODES = ("data", "axes")

# Labels below this fraction of the x range are dropped: a name that does not
# fit its own region is worse than no name, because it lands on its neighbour.
_DEFAULT_MIN_LABEL_WIDTH = 0.04

_TITLE_BUMP_MARKER = "_cfd_plot_domain_title_bumped"

# Sentinel for a point the model gave no domain for.
_MISSING = object()


@dataclass(frozen=True)
class Domain:
    """How one value of the domain column is drawn."""

    name: str
    color: str | None = None
    hatch: str | None = None
    alpha: float | None = None


@dataclass(frozen=True)
class DomainSpan:
    """One drawn region, returned so the caller can keep tweaking it."""

    value: Any
    name: str
    start: float
    end: float
    color: str
    alpha: float = 0.0
    patch: Any = None
    text: Any = None

    @property
    def width(self) -> float:
        return self.end - self.start


DomainArg = Union[str, Mapping[str, Any], Domain]


def _is_missing(value: Any) -> bool:
    """True for None / NaN / pandas NA — a point with no domain."""
    if value is None:
        return True
    try:
        return bool(value != value)  # NaN is the only value unequal to itself
    except (TypeError, ValueError):  # pragma: no cover - exotic objects
        return False


def domain_segments(
    x: Sequence[float],
    domain: Sequence[Any],
    *,
    boundary: str = "midpoint",
) -> list[tuple[Any, float, float]]:
    """Split ``(x, domain)`` into ``(value, start, end)`` runs.

    Pure and Matplotlib-free, so the geometry can be checked on its own.

    Points are sorted by *x* first: a sweep read back from a solver is not
    always monotonic, and an unsorted run would produce regions that overlap
    each other. Points whose *x* or domain is missing are dropped, and they
    break the run — a gap in the model is not a region.

    Parameters
    ----------
    boundary : {"midpoint", "left", "right"}
        Where to cut between two samples that disagree: halfway (default), at
        the last point of the region ending, or at the first point of the one
        starting.
    """
    if boundary not in _BOUNDARY_MODES:
        raise ValueError(f"boundary must be one of {_BOUNDARY_MODES}, got {boundary!r}.")

    x_arr = np.asarray(x, dtype=float)
    values = list(domain)
    if x_arr.ndim != 1:
        raise ValueError(f"x must be one-dimensional, got shape {x_arr.shape}.")
    if len(values) != x_arr.size:
        raise ValueError(
            f"x and domain must have the same length, got {x_arr.size} and {len(values)}."
        )

    # A point with no x cannot be placed at all, so it is dropped outright; a
    # point with no domain stays in the sequence and *breaks* the run, because
    # shading straight through it would claim a region the model never gave.
    placed = [index for index in range(x_arr.size) if not np.isnan(x_arr[index])]
    if not placed:
        return []

    order = sorted(placed, key=lambda index: x_arr[index])
    xs = [float(x_arr[index]) for index in order]
    # NumPy scalars become plain Python: they are dict keys and repr'd in
    # labels, and np.int64(2) printing as "2" but comparing oddly is a trap.
    vals: list[Any] = []
    for index in order:
        value = values[index]
        if _is_missing(value):
            vals.append(_MISSING)
        else:
            vals.append(value.item() if isinstance(value, np.generic) else value)

    # Runs of equal consecutive values, as index ranges into the sorted arrays.
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(vals):
        if value is _MISSING:
            if start is not None:
                runs.append((start, index - 1))
            start = None
        elif start is None:
            start = index
        elif value != vals[start]:
            runs.append((start, index - 1))
            start = index
    if start is not None:
        runs.append((start, len(vals) - 1))

    # Each edge is cut against the immediately neighbouring *sample*, missing or
    # not: a region next to a hole then stops halfway into it, leaving the
    # unknown stretch blank instead of half-shaded.
    segments: list[tuple[Any, float, float]] = []
    for first, last in runs:
        left = xs[first] if first == 0 else _cut(xs[first - 1], xs[first], boundary)
        right = xs[last] if last == len(xs) - 1 else _cut(xs[last], xs[last + 1], boundary)
        segments.append((vals[first], left, right))
    return segments


def _cut(before: float, after: float, boundary: str) -> float:
    if boundary == "midpoint":
        return 0.5 * (before + after)
    return before if boundary == "left" else after


def _as_domain(value: Any, spec: DomainArg | None) -> Domain:
    if spec is None:
        return Domain(name=str(value))
    if isinstance(spec, Domain):
        return spec
    if isinstance(spec, str):
        return Domain(name=spec)
    if isinstance(spec, Mapping):
        unknown = set(spec) - {"name", "color", "hatch", "alpha"}
        if unknown:
            raise ValueError(
                f"unknown domain keys for {value!r}: {sorted(unknown)}; "
                "expected name, color, hatch, alpha."
            )
        return Domain(
            name=str(spec.get("name", value)),
            color=spec.get("color"),
            hatch=spec.get("hatch"),
            alpha=spec.get("alpha"),
        )
    raise TypeError(
        f"domain entry for {value!r} must be a str, a dict or a Domain, "
        f"got {type(spec).__name__}."
    )


def _color_index(value: Any, ordered_values: Sequence[Any]) -> int:
    """Palette slot for *value* — its own integer when it is one.

    Keyed on the value rather than on the order of appearance so that the same
    regime keeps its colour on a figure where a neighbouring regime is absent.
    """
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool) and value >= 0:
        return int(value)
    return ordered_values.index(value)


def plot_domains(
    ax: Any,
    x: Sequence[float],
    domain: Sequence[Any],
    *,
    domains: Mapping[Any, DomainArg] | None = None,
    palette: str | Sequence[str] = DEFAULT_PALETTE,
    alpha: float = 0.12,
    fill: bool = True,
    alternate: bool = False,
    lines: bool | Mapping[str, Any] = False,
    labels: bool = True,
    label_loc: str = "top",
    label_rotation: float = 0.0,
    label_box: bool = False,
    label_kwargs: Mapping[str, Any] | None = None,
    min_label_width: float = _DEFAULT_MIN_LABEL_WIDTH,
    legend: bool = False,
    boundary: str = "midpoint",
    extend: str = "data",
    zorder: float = 0.0,
    **kwargs: Any,
) -> list[DomainSpan]:
    """Shade and name the regions described by a per-point domain column.

    Parameters
    ----------
    ax
        The axes to draw on. Draw the curves first: the regions are sized from
        *x*, and ``extend="axes"`` reads the current limits.
    x, domain
        Same length. *domain* holds one value per point — typically an integer
        such as ``iDomain``. Consecutive equal values form one region.
    domains
        ``{value: name}``, ``{value: {"name": …, "color": …, "hatch": …,
        "alpha": …}}`` or ``{value: Domain(...)}``. Values missing from the
        mapping are named after themselves and coloured from *palette*.
    alpha
        Fill opacity. The default is deliberately faint: the regions are
        context, and must never compete with the curve.
    alternate
        Tint every other region only, leaving the rest white.
    lines
        Draw a rule at each internal boundary. Pass a dict to restyle it.
    label_loc : {"top", "inside", "bottom", "none"}
        ``"top"`` writes the names in a row just above the frame and pushes the
        axes title up to make room; ``"inside"`` writes them inside, under the
        top spine, which is the one to use when the header is already busy
        (a subtitle, a two-line suptitle).
    min_label_width
        Regions narrower than this fraction of the x range go unlabelled.
        Use ``legend=True`` to name them anyway.
    boundary : {"midpoint", "left", "right"}
        Where consecutive samples that disagree are cut. See
        :func:`domain_segments`.
    extend : {"data", "axes"}
        Whether the first and last regions stop at the data or run out to the
        current axis limits. ``"axes"`` leaves no white sliver at the edges,
        but reads the limits now — call it last.
    **kwargs
        Forwarded to ``ax.axvspan`` (``edgecolor``, ``linewidth``, …).

    Returns
    -------
    list of DomainSpan
        One per region, in x order, carrying the patch and the label.
    """
    if label_loc not in _LABEL_LOCATIONS:
        raise ValueError(
            f"label_loc must be one of {_LABEL_LOCATIONS}, got {label_loc!r}."
        )
    if extend not in _EXTEND_MODES:
        raise ValueError(f"extend must be one of {_EXTEND_MODES}, got {extend!r}.")

    segments = domain_segments(x, domain, boundary=boundary)
    if not segments:
        return []

    if extend == "axes":
        left, right = ax.get_xlim()
        value, start, end = segments[0]
        segments[0] = (value, min(start, left, right), end)
        value, start, end = segments[-1]
        segments[-1] = (value, start, max(end, left, right))

    mapping = dict(domains or {})
    ordered_values: list[Any] = []
    for value, _start, _end in segments:
        if value not in ordered_values:
            ordered_values.append(value)
    for value in mapping:
        if value not in ordered_values:
            ordered_values.append(value)

    n_colors = max(_color_index(value, ordered_values) for value in ordered_values) + 1
    colors = palette_colors(palette, n=n_colors)

    span_left = min(start for _value, start, _end in segments)
    span_right = max(end for _value, _start, end in segments)
    total_width = span_right - span_left

    labelled: set[Any] = set()
    spans: list[DomainSpan] = []

    for position, (value, start, end) in enumerate(segments):
        spec = _as_domain(value, mapping.get(value))
        color = spec.color or colors[_color_index(value, ordered_values) % len(colors)]
        patch = None
        span_alpha = spec.alpha if spec.alpha is not None else alpha
        shaded = fill and not (alternate and position % 2)
        if shaded:
            span_kwargs: dict[str, Any] = {
                "facecolor": color,
                "alpha": span_alpha,
                "edgecolor": "none",
                "zorder": zorder,
            }
            if spec.hatch:
                # The hatch must stay visible where the fill is nearly white,
                # so it takes the domain colour at full strength.
                span_kwargs["hatch"] = spec.hatch
                span_kwargs["edgecolor"] = color
                span_kwargs["linewidth"] = 0.0
            span_kwargs.update(kwargs)
            patch = ax.axvspan(start, end, **span_kwargs)

        text = None
        wide_enough = total_width <= 0 or (end - start) / total_width >= min_label_width
        if labels and label_loc != "none" and wide_enough:
            text = _draw_label(
                ax,
                spec.name,
                0.5 * (start + end),
                color=color,
                label_loc=label_loc,
                rotation=label_rotation,
                box=label_box,
                extra=dict(label_kwargs or {}),
            )

        spans.append(
            DomainSpan(
                value=value,
                name=spec.name,
                start=start,
                end=end,
                color=color,
                alpha=span_alpha,
                patch=patch,
                text=text,
            )
        )

    if legend:
        # One entry per value, added in x order so the legend reads left to
        # right like the figure. Every entry is a zero-width span rather than
        # the real patch: labelling the patches would order the legend by when
        # they were created, which puts an unshaded region (fill=False,
        # alternate, …) last instead of in its place.
        for span in spans:
            if span.value in labelled:
                continue
            labelled.add(span.value)
            ax.axvspan(
                span.start,
                span.start,
                facecolor=span.color,
                alpha=span.alpha or alpha,
                edgecolor="none",
                zorder=zorder,
                label=span.name,
            )

    if lines:
        line_kwargs = {
            "color": "0.55",
            "linewidth": 0.8,
            "linestyle": (0, (4, 3)),
            "zorder": zorder + 0.1,
        }
        if isinstance(lines, Mapping):
            line_kwargs.update(lines)
        for _value, start, _end in segments[1:]:
            ax.axvline(start, **line_kwargs)

    return spans


def _draw_label(
    ax: Any,
    name: str,
    x_center: float,
    *,
    color: str,
    label_loc: str,
    rotation: float,
    box: bool,
    extra: dict[str, Any],
) -> Any:
    """One region name, positioned in x data / y axes coordinates."""
    fontsize = extra.pop("fontsize", float(mpl.rcParams["font.size"]) * 0.9)
    kwargs: dict[str, Any] = {
        "ha": "center",
        "rotation": rotation,
        "fontsize": fontsize,
        "color": extra.pop("color", "0.25"),
        "clip_on": label_loc != "top",
        "zorder": 3.0,
    }
    if box:
        kwargs["bbox"] = {
            "boxstyle": "square,pad=0.35",
            "facecolor": color,
            "alpha": 0.25,
            "edgecolor": "none",
        }
    kwargs.update(extra)

    if label_loc == "top":
        # Just above the frame, with the title pushed up out of the way.
        transform = ax.get_xaxis_transform() + ScaledTranslation(
            0, 2 / 72.0, ax.figure.dpi_scale_trans
        )
        _bump_title(ax, fontsize + 4)
        return ax.text(x_center, 1.0, name, transform=transform, va="baseline", **kwargs)

    if label_loc == "inside":
        return ax.text(
            x_center,
            0.965,
            name,
            transform=ax.get_xaxis_transform(),
            va="top",
            **kwargs,
        )

    return ax.text(
        x_center,
        0.02,
        name,
        transform=ax.get_xaxis_transform(),
        va="bottom",
        **kwargs,
    )


def _bump_title(ax: Any, extra_points: float) -> None:
    """Make room above the frame for a row of region names.

    Once per axes: a second call would stack a second gap under a title that
    has already moved. The title's font properties are saved and restored
    because ``ax.set_title`` resets them — the same trap ``set_subtitle``
    documents.
    """
    if getattr(ax, _TITLE_BUMP_MARKER, False) or not ax.get_title():
        setattr(ax, _TITLE_BUMP_MARKER, True)
        return
    pad = float(mpl.rcParams["axes.titlepad"])
    font_properties = ax.title.get_fontproperties().copy()
    color = ax.title.get_color()
    ax.set_title(ax.get_title(), pad=pad + extra_points)
    ax.title.set_fontproperties(font_properties)
    ax.title.set_color(color)
    setattr(ax, _TITLE_BUMP_MARKER, True)
