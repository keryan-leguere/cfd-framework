"""
path — a trajectory drawn as it is flown, in 2-D or 3-D.

Two pieces, the same split as the rest of :mod:`cfd_plot.anim`:

:class:`PathReveal`
    The artists. A faint *ghost* of the whole path (so the eye knows where it
    is going), the *trail* flown so far, and a *head* marker, all updated by
    ``update(t)``. The head is **interpolated** at ``t``, so the motion is
    smooth whatever the sampling of the data. Works on a plain axes or on a
    ``projection="3d"`` one; build your own figure around it and drive it from
    :func:`cfd_plot.animate` when you need more than the sugar below.

:func:`animate_path`
    The one call: figure, locked limits, optional true proportions, a clock,
    named events that light up when reached (and may hold the frame), an
    optional slow orbit of a 3-D view — then the loop, timed by
    :func:`~cfd_plot.anim.timeline.timeline`.

Two 3-D traps it handles
------------------------
* **Autoscaling.** ``Line3D.set_data_3d`` does not rescale, but the very first
  ``plot`` call does — on the first point only, giving a degenerate box. The
  limits are set from the *whole* path after the artists exist.
* **Proportions.** ``set_aspect("equal")`` on a 3-D axes is a recent addition
  and behaves differently across Matplotlib versions; ``set_box_aspect`` with
  the data spans is what gives a box whose sides are in true proportion, on
  every version this package supports.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_hex
from numpy.typing import ArrayLike, NDArray

from ..axes3d import tidy_axes3d, true_proportions
from ..mpl_template import new_figure, style_context
from .encode import resolve_preset
from .engine import AnimationResult, animate
from .timeline import timeline

__all__ = ["PathReveal", "animate_path"]

Array = NDArray[np.float64]


def _is_3d(ax: Any) -> bool:
    return getattr(ax, "name", "") == "3d"


class PathReveal:
    """Ghost, trail and head of a time-parametrised path on *ax*.

    Parameters
    ----------
    ax : Axes or Axes3D
    t : array (n,)
        Strictly increasing instants.
    x, y : arrays (n,)
    z : array (n,), optional
        Give it on a 3-D axes, and only there.
    ghost : bool
        Draw the whole path faintly underneath.
    trail : float, optional
        Keep only the last *trail* seconds of the flown path (a comet tail).
        ``None`` keeps all of it.
    ghost_kw, trail_kw, head_kw : dict, optional
        Extra ``plot`` keywords for each artist. The trail colour defaults to
        the axes' next cycle colour, and the head follows it.
    """

    def __init__(
        self,
        ax: Any,
        t: ArrayLike,
        x: ArrayLike,
        y: ArrayLike,
        z: ArrayLike | None = None,
        *,
        ghost: bool = True,
        trail: float | None = None,
        ghost_kw: Mapping[str, Any] | None = None,
        trail_kw: Mapping[str, Any] | None = None,
        head_kw: Mapping[str, Any] | None = None,
    ) -> None:
        self.ax = ax
        self.t = np.asarray(t, dtype=float).ravel()
        columns = [np.asarray(c, dtype=float).ravel() for c in (x, y) + ((z,) if z is not None else ())]
        if any(len(c) != len(self.t) for c in columns):
            raise ValueError("t, x, y (and z) must have the same length")
        if len(self.t) < 2:
            raise ValueError("a path needs at least two points")
        if not np.all(np.diff(self.t) > 0):
            raise ValueError("t must be strictly increasing")
        if (z is not None) != _is_3d(ax):
            raise ValueError("pass z exactly when ax is a 3-D axes (projection='3d')")
        if trail is not None and not trail > 0:
            raise ValueError(f"trail must be positive seconds, got {trail}")
        self.points: Array = np.column_stack(columns)
        self.trail = trail
        self._3d = z is not None

        self.ghost = None
        if ghost:
            kw = {"color": "0.78", "linewidth": 0.9 * plt.rcParams["lines.linewidth"], "zorder": 1.0}
            kw.update(ghost_kw or {})
            (self.ghost,) = ax.plot(*self.points.T, **kw)
        kw = {"zorder": 2.0}
        kw.update(trail_kw or {})
        (self.line,) = ax.plot(*self.points[:1].T, **kw)
        # "C0"-style names resolve at *draw* time against whatever cycle is active then:
        # fixed here, the colour survives leaving the style context (a still saved later).
        colour = to_hex(self.line.get_color())
        self.line.set_color(colour)
        kw = {"marker": "o", "linestyle": "none", "color": colour, "markeredgecolor": "white",
              "markeredgewidth": 0.8, "zorder": 3.0}
        kw.update(head_kw or {})
        (self.head,) = ax.plot(*self.points[:1].T, **kw)

    @property
    def artists(self) -> list[Any]:
        """Every artist this object drives."""
        return [a for a in (self.ghost, self.line, self.head) if a is not None]

    @property
    def extent(self) -> tuple[Array, Array]:
        """``(mins, maxs)`` of the whole path, one entry per coordinate."""
        return self.points.min(axis=0), self.points.max(axis=0)

    def position(self, t_now: float) -> Array:
        """The path interpolated at *t_now* (clamped to its time span)."""
        return np.array([np.interp(t_now, self.t, c) for c in self.points.T])

    def update(self, t_now: float) -> Array:
        """Show the path as flown up to *t_now*; returns the head position."""
        head = self.position(t_now)
        stop = int(np.searchsorted(self.t, t_now, side="right"))
        start = 0 if self.trail is None else int(np.searchsorted(self.t, t_now - self.trail, side="left"))
        start = min(start, stop)
        flown = np.vstack([self.points[start:stop], head[None, :]])
        if len(flown) < 2:
            flown = np.vstack([head, head])
        self._set(self.line, flown)
        self._set(self.head, head[None, :])
        return head

    def _set(self, line: Any, pts: Array) -> None:
        if self._3d:
            line.set_data_3d(pts[:, 0], pts[:, 1], pts[:, 2])
        else:
            line.set_data(pts[:, 0], pts[:, 1])


def lock_limits(
    ax: Any, mins: Array, maxs: Array, *, margin: float = 0.04, equal: bool = False, zoom: float = 1.0
) -> None:
    """Fix the limits to ``[mins, maxs]`` padded by *margin* (fraction of the largest span).

    ``equal=True`` gives true proportions: equal data aspect on a 2-D axes, a
    box with sides proportional to the spans on a 3-D one. A 3-D axes is also
    given the paper look of :func:`cfd_plot.axes3d.tidy_axes3d`.
    """
    mins, maxs = np.asarray(mins, dtype=float), np.asarray(maxs, dtype=float)
    spans = maxs - mins
    pad = margin * float(spans.max()) if spans.max() > 0 else 1.0
    lo, hi = mins - pad, maxs + pad
    if _is_3d(ax):
        ax.set_xlim(lo[0], hi[0])
        ax.set_ylim(lo[1], hi[1])
        ax.set_zlim(lo[2], hi[2])
        if equal:
            true_proportions(ax, lo, hi, zoom=zoom)
        tidy_axes3d(ax)
        return
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[1], hi[1])
    if equal:
        ax.set_aspect("equal", adjustable="box")


def animate_path(
    t: ArrayLike,
    x: ArrayLike,
    y: ArrayLike,
    z: ArrayLike | None = None,
    path: str | Path = "path.gif",
    *,
    events: Mapping[str, float] | None = None,
    event_hold: float = 0.0,
    duration: float | None = None,
    speed: float | None = None,
    fps: int | None = None,
    preset: str | None = None,
    xlabel: str = "",
    ylabel: str = "",
    zlabel: str = "",
    title: str | None = None,
    equal: bool = False,
    view: tuple[float, float] | None = None,
    orbit: float = 0.0,
    clock: str | None = "t = {t:.1f} s",
    ghost: bool = True,
    trail: float | None = None,
    profile: str | None = None,
    figsize: tuple[float, float] | None = None,
    ax: Any = None,
    on_frame: Callable[[int, float, Any], Any] | None = None,
    close_fig: bool = True,
    **anim_kwargs: Any,
) -> AnimationResult:
    """Animate a trajectory flown in time — 2-D, or 3-D when *z* is given.

    Parameters
    ----------
    t, x, y, z : arrays
        The path. ``t`` strictly increasing, in any unit (the clock says "s").
    path : str or Path
        Output; ``.mp4`` streams (see :mod:`cfd_plot.anim.stream`).
    events : mapping, optional
        ``{name: instant}``. Each gets a marker and its name, shown from the
        moment it is reached; the legend lists them with their instants.
    event_hold : float
        Seconds to hold the frame on each event.
    duration, speed : float, optional
        Seconds of video for the whole path, or physical seconds per video
        second (see :func:`~cfd_plot.anim.timeline.timeline`). Real time when
        neither is given.
    fps, preset
        As for :func:`cfd_plot.animate`; *fps* defaults to the preset's.
    equal : bool
        True proportions (no axis stretched).
    view : (elev, azim), optional
        3-D viewpoint, in degrees.
    orbit : float
        Degrees of azimuth the 3-D view turns over the whole animation; 0
        keeps it still. A slow orbit is what makes depth readable on a still
        screen.
    clock : str or None
        Format of the clock in the corner, with ``{t}``; ``None`` hides it.
    trail : float, optional
        Comet tail length in time units; ``None`` keeps the whole flown path.
    ax : Axes, optional
        Draw into an axes you built (2-D, or 3-D with *z*). Its limits are set
        to the path unless you lock them afterwards in *on_frame*.
    on_frame : callable, optional
        ``on_frame(i, t_now, ax)`` after the path is updated, before capture.
    close_fig : bool
        Close the figure afterwards; ``False`` returns it on the result.

    Every other keyword goes to :class:`cfd_plot.anim.Animator`.
    """
    three_d = z is not None
    spec = resolve_preset(preset)
    rate = int(fps if fps is not None else spec.fps)
    if ax is None:
        if three_d:
            fig, ax = new_figure(profile=profile, figsize=figsize, subplot_kw={"projection": "3d"})
        else:
            fig, ax = new_figure(profile=profile, figsize=figsize)
    else:
        fig = ax.figure
    if three_d and not _is_3d(ax):
        raise ValueError("z given but ax is not a 3-D axes")

    with style_context(profile) if profile else nullcontext():
        reveal = PathReveal(ax, t, x, y, z, ghost=ghost, trail=trail)
        mins, maxs = reveal.extent
        lock_limits(ax, mins, maxs, equal=equal, zoom=0.85 if three_d else 1.0)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        if three_d:
            ax.set_zlabel(zlabel)
        if title:
            ax.set_title(title)
        elev, azim = view if view is not None else ((30.0, -60.0) if three_d else (0.0, 0.0))
        if three_d:
            ax.view_init(elev=elev, azim=azim)

        marks: list[tuple[float, Any, Any]] = []
        for k, (name, instant) in enumerate(sorted((events or {}).items(), key=lambda e: e[1])):
            p = reveal.position(instant)
            marker = "sDv^<>Ph*"[k % 9]
            (m,) = ax.plot(*p[:, None], marker=marker, linestyle="none", color=to_hex(f"C{(k + 1) % 10}"),
                           markeredgecolor="black", markeredgewidth=0.6, zorder=4.0,
                           label=f"{name} ({instant:.1f} s)")
            label = (ax.text(*p, f"  {name}", zorder=5.0, va="center") if three_d
                     else ax.annotate(name, p, xytext=(6, 4), textcoords="offset points", zorder=5.0))
            label.set_visible(False)
            marks.append((float(instant), m, label))
        if marks:
            # The legend copies each marker as it is now, so it is built before they are hidden.
            ax.legend(handles=[m for _, m, _ in marks], loc="upper right")
            for _, m, _ in marks:
                m.set_visible(False)

        text = None
        if clock is not None:
            place = ax.text2D if three_d else ax.text
            text = place(0.02, 0.97, "", transform=ax.transAxes, va="top", ha="left")

        t_arr = reveal.t
        tl = timeline(float(t_arr[0]), float(t_arr[-1]), fps=rate, duration=duration, speed=speed,
                      holds={instant: event_hold for instant, _, _ in marks} if event_hold > 0 else None)
        with animate(fig, path, preset=spec, fps=rate, **anim_kwargs) as anim:
            for i, (t_now, hold) in enumerate(tl):
                reveal.update(t_now)
                for instant, m, label in marks:
                    reached = t_now >= instant - 1e-12
                    m.set_visible(reached)
                    label.set_visible(reached)
                if text is not None and clock is not None:
                    text.set_text(clock.format(t=t_now))
                if three_d and orbit:
                    ax.view_init(elev=elev, azim=azim + orbit * i / max(1, len(tl) - 1))
                if on_frame is not None:
                    on_frame(i, t_now, ax)
                anim.capture(hold=hold)

    result = anim.result
    assert result is not None
    if close_fig:
        plt.close(fig)
        return result
    return AnimationResult(**{**result.__dict__, "fig": fig, "axes": ax})
