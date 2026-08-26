"""
sweep — the one-liner on top of :mod:`cfd_plot.anim.engine`.

Two shapes of animation cover most curve work, and both come out of the same
function:

**Reveal** — one curve drawn point by point.  A convergence history filling in,
a polar being traced.  ``y`` is 1-D (or a few curves of the same length racing
together)::

    animate_sweep(iterations, residual, "conv.gif",
                  reveal=True, yscale="log",
                  xlabel="iteration", ylabel="residual")

**Sweep** — one complete curve per frame.  A polar per Mach number, a profile
per configuration.  ``y`` is 2-D, one row per frame::

    animate_sweep(alpha, cn_per_mach, "sweep.gif",
                  labels=[f"M = {m:.2f}" for m in mach],
                  boomerang=True)

Everything the engine accepts (``preset``, ``fps``, ``formats``, ``hold_last``,
``keep_frames``, …) passes straight through.

When you outgrow it
-------------------
The escape hatches, in increasing order of control:

``ax=``
    Pass an axes you already built and decorated.  Nothing about it is
    overwritten except the limits (and not even those if you pass
    ``lock_axes=False``).
``on_frame=``
    A ``callback(i, ax)`` run after the data for frame *i* is set and before
    the frame is captured.  Move an annotation, recolour something, redraw a
    marker.
``close_fig=False``
    The figure comes back on the result (``result.fig``, ``result.axes``)
    instead of being closed, so you can save a still of the final state.

Past that, drop to :func:`cfd_plot.animate` and write the loop — it is about
eight more lines and there is nothing this module can do that it cannot.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from cfd_plot._compat import zip_strict

from ..mpl_template import make_legend, new_figure, plot_line, set_title
from .engine import AnimationResult, animate

__all__ = ["animate_sweep"]


def animate_sweep(
    x: Any,
    y: Any,
    path: str | Path,
    *,
    reveal: bool | None = None,
    labels: Sequence[str] | None = None,
    ax: Any = None,
    profile: str | None = None,
    figsize: tuple[float, float] | None = None,
    xlabel: str | None = None,
    ylabel: str | None = None,
    title: str | None = None,
    xscale: str | None = None,
    yscale: str | None = None,
    marker: str = "",
    head: bool = True,
    head_kwargs: dict | None = None,
    keep_previous: bool = False,
    ghost_alpha: float = 0.25,
    lock_axes: bool = True,
    margin: float = 0.05,
    legend: bool | None = None,
    on_frame: Callable[[int, Any], Any] | None = None,
    close_fig: bool = True,
    **anim_kwargs: Any,
) -> AnimationResult:
    """Animate a curve being revealed, or a family of curves one per frame.

    Parameters
    ----------
    x : array-like
        Shared abscissa, or one abscissa array per frame (sweep mode only).
    y : array-like
        1-D for reveal mode.  2-D ``(n_frames, n_points)`` — or a sequence of
        1-D arrays — for sweep mode.
    path : str or Path
        Output path; a ``.gif`` or ``.mp4`` suffix selects the format.
    reveal : bool, optional
        Force reveal (``True``) or sweep (``False``) mode.  Inferred from the
        shape of *y* when omitted: 1-D reveals, 2-D sweeps.
    labels : sequence of str, optional
        In **sweep** mode, one label per frame, shown in the title (this is
        where ``"M = 0.80"`` goes).  In **reveal** mode, one label per curve,
        shown in the legend.
    ax : Axes, optional
        Draw into an existing axes instead of creating a figure.  Its labels,
        title and styling are left untouched.
    profile, figsize
        Forwarded to :func:`cfd_plot.new_figure` when *ax* is not given.
    xlabel, ylabel, title, xscale, yscale
        Applied to the axes before the first frame.
    marker : str
        Marker for the animated line(s).  Empty by default — a marker per data
        point competes with the reveal head.
    head : bool
        In reveal mode, draw a dot at the leading point so the first frame is
        not blank and the eye can follow the front.
    head_kwargs : dict, optional
        Overrides for that dot (``markersize``, ``marker``, …).
    keep_previous : bool
        In sweep mode, leave already-shown curves on screen, faded.  Turns the
        animation into an accumulating family plot.  Note that past ten curves
        the property cycle repeats, so the trail reuses colours; it reads as a
        trail rather than as distinct series, which is the intent, but do not
        rely on ghost colour to identify a frame — the title does that.
    ghost_alpha : float
        Opacity of those faded curves.
    lock_axes : bool
        Set the axis limits once, from the full dataset, so nothing rescales
        mid-animation.  Disable only if you set the limits yourself — leaving
        Matplotlib to autoscale per frame is what makes an animation twitch.
    margin : float
        Fractional padding added around the data extent when locking.
    legend : bool, optional
        Draw a legend.  Defaults to ``True`` when any label would appear in it.
    on_frame : callable, optional
        ``callback(i, ax)`` run just before each frame is captured.
    close_fig : bool
        Close the figure afterwards.  ``False`` returns it on the result.
    **anim_kwargs
        Forwarded to :class:`cfd_plot.anim.Animator` — ``preset``, ``fps``,
        ``formats``, ``hold_last``, ``boomerang``, ``keep_frames``, ``report``…

    Returns
    -------
    AnimationResult
    """
    xs, ys, multi = _normalise(x, y)
    if reveal is None:
        reveal = not multi

    # Reveal walks the points of a curve; sweep walks the curves themselves.
    # Key this off the *resolved* mode, not off the shape of the input — an
    # explicit reveal=False on a single curve is a legitimate one-frame sweep.
    n_frames = len(xs[0]) if reveal else len(xs)
    if n_frames < 1:
        raise ValueError("nothing to animate — x and y are empty")
    if reveal and multi and len({len(a) for a in xs}) != 1:
        raise ValueError("reveal mode needs every curve to have the same number of points")

    fig, axes = (None, ax)
    if ax is None:
        fig, axes = new_figure(profile=profile, figsize=figsize)

    _decorate(axes, xlabel=xlabel, ylabel=ylabel, xscale=xscale, yscale=yscale)
    if lock_axes:
        _lock_axes(axes, xs, ys, margin=margin)

    lines, heads = _build_artists(
        axes,
        n_curves=len(xs),
        reveal=reveal,
        keep_previous=keep_previous,
        labels=labels,
        marker=marker,
        head=head,
        head_kwargs=head_kwargs,
    )

    if legend is None:
        legend = any(ln.get_label() and not ln.get_label().startswith("_") for ln in lines)
    if legend:
        make_legend(axes)

    fig_for_capture = axes.get_figure()
    with animate(fig_for_capture, path, **anim_kwargs) as anim:
        for i in range(n_frames):
            if reveal:
                _set_reveal_frame(lines, heads, xs, ys, i)
            else:
                _set_sweep_frame(lines, xs, ys, i, keep_previous=keep_previous, ghost_alpha=ghost_alpha)

            _set_frame_title(axes, title, labels, i, per_frame=not reveal)
            if on_frame is not None:
                on_frame(i, axes)
            anim.capture()

    result = anim.result
    if close_fig:
        import matplotlib.pyplot as plt

        plt.close(fig_for_capture)
        return result

    return AnimationResult(
        paths=result.paths,
        n_frames=result.n_frames,
        n_captures=result.n_captures,
        fps=result.fps,
        size_px=result.size_px,
        preset=result.preset,
        backend=result.backend,
        frames_dir=result.frames_dir,
        fig=fig if fig is not None else fig_for_capture,
        axes=axes,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _normalise(x: Any, y: Any) -> tuple[list[np.ndarray], list[np.ndarray], bool]:
    """Return ``(xs, ys, multi)`` as lists of 1-D arrays, one entry per curve."""
    ys_arr = [np.atleast_1d(np.asarray(row, dtype=float)) for row in _rows(y)]
    multi = len(ys_arr) > 1 or _is_2d(y)

    xs_raw = list(_rows(x)) if _is_2d(x) else None
    if xs_raw is not None:
        xs_arr = [np.atleast_1d(np.asarray(row, dtype=float)) for row in xs_raw]
        if len(xs_arr) != len(ys_arr):
            raise ValueError(f"got {len(xs_arr)} x-arrays for {len(ys_arr)} y-curves — they must match")
    else:
        shared = np.atleast_1d(np.asarray(x, dtype=float))
        xs_arr = [shared] * len(ys_arr)

    for i, (xi, yi) in enumerate(zip_strict(xs_arr, ys_arr)):
        if xi.size != yi.size:
            raise ValueError(f"curve {i}: x has {xi.size} points but y has {yi.size}")

    return xs_arr, ys_arr, multi


def _is_2d(a: Any) -> bool:
    """True if *a* is a 2-D array or a sequence of sequences."""
    if isinstance(a, np.ndarray):
        return a.ndim >= 2
    if isinstance(a, str) or not isinstance(a, Sequence):
        return False
    return len(a) > 0 and all(isinstance(row, (np.ndarray, Sequence)) and not isinstance(row, str) for row in a)


def _rows(a: Any) -> list[Any]:
    return list(a) if _is_2d(a) else [a]


def _decorate(ax: Any, *, xlabel: str | None, ylabel: str | None, xscale: str | None, yscale: str | None) -> None:
    if xscale is not None:
        ax.set_xscale(xscale)
    if yscale is not None:
        ax.set_yscale(yscale)
    if xlabel is not None:
        ax.set_xlabel(xlabel)
    if ylabel is not None:
        ax.set_ylabel(ylabel)


def _lock_axes(ax: Any, xs: list[np.ndarray], ys: list[np.ndarray], *, margin: float) -> None:
    """Fix the limits to the full dataset so no frame rescales the axes."""
    ax.set_xlim(*_padded_range(xs, margin, log=ax.get_xscale() == "log"))
    ax.set_ylim(*_padded_range(ys, margin, log=ax.get_yscale() == "log"))


def _padded_range(arrays: list[np.ndarray], margin: float, *, log: bool) -> tuple[float, float]:
    stacked = np.concatenate([a.ravel() for a in arrays])
    if log:
        # A log axis cannot show non-positive data, and including it would drag
        # the lower limit to zero and blow the range up.
        stacked = stacked[stacked > 0]
    stacked = stacked[np.isfinite(stacked)]
    if stacked.size == 0:
        return (0.1, 1.0) if log else (0.0, 1.0)

    lo, hi = float(stacked.min()), float(stacked.max())
    if log:
        decades = np.log10(hi) - np.log10(lo)
        pad = margin * (decades if decades > 0 else 1.0)
        return 10.0 ** (np.log10(lo) - pad), 10.0 ** (np.log10(hi) + pad)

    span = hi - lo
    if span == 0.0:
        # A flat curve still needs a visible window around it.
        pad = abs(lo) * margin or 1.0
        return lo - pad, hi + pad
    return lo - margin * span, hi + margin * span


def _build_artists(
    ax: Any,
    *,
    n_curves: int,
    reveal: bool,
    keep_previous: bool,
    labels: Sequence[str] | None,
    marker: str,
    head: bool,
    head_kwargs: dict | None,
) -> tuple[list[Any], list[Any]]:
    """Create the Line2D objects the frames will mutate.

    Reveal mode needs one line per curve (they all grow together).  Sweep mode
    needs one line per *frame* when previous curves stay on screen, and a
    single recycled line when they do not.
    """
    n_lines = n_curves if (reveal or keep_previous) else 1

    # Only reveal mode legends its curves. In sweep mode a label names the
    # *frame*, not a series, so it belongs in the title — and a legend built
    # up front would list every curve including the ones not drawn yet, then
    # repeat colours once the family outgrows the ten-entry property cycle.
    labelled = reveal and labels is not None

    lines = []
    for k in range(n_lines):
        label = labels[k] if (labelled and labels is not None and k < len(labels)) else None
        lines.append(plot_line(ax, [], [], marker=marker, label=label))

    heads: list[Any] = []
    if reveal and head:
        opts = {"marker": "o", "linestyle": "none", "markersize": 7, "zorder": 5}
        opts.update(head_kwargs or {})
        for line in lines:
            (dot,) = ax.plot([], [], color=line.get_color(), **opts)
            dot.set_markerfacecolor(line.get_color())
            dot.set_markeredgecolor(line.get_color())
            heads.append(dot)

    return lines, heads


def _set_reveal_frame(lines: list[Any], heads: list[Any], xs: list[np.ndarray], ys: list[np.ndarray], i: int) -> None:
    for k, line in enumerate(lines):
        line.set_data(xs[k][: i + 1], ys[k][: i + 1])
        if heads:
            heads[k].set_data(xs[k][i : i + 1], ys[k][i : i + 1])


def _set_sweep_frame(
    lines: list[Any],
    xs: list[np.ndarray],
    ys: list[np.ndarray],
    i: int,
    *,
    keep_previous: bool,
    ghost_alpha: float,
) -> None:
    if not keep_previous:
        lines[0].set_data(xs[i], ys[i])
        return

    for k, line in enumerate(lines):
        if k > i:
            line.set_data([], [])
        else:
            line.set_data(xs[k], ys[k])
            line.set_alpha(1.0 if k == i else ghost_alpha)


def _set_frame_title(ax: Any, title: str | None, labels: Sequence[str] | None, i: int, *, per_frame: bool) -> None:
    frame_label = labels[i] if (per_frame and labels is not None and i < len(labels)) else None

    if title is None and frame_label is None:
        return
    if frame_label is None:
        # Static title: setting it every frame is wasteful but harmless, and it
        # keeps this function the single place a title is written.
        set_title(ax, title or "")
        return
    set_title(ax, f"{title} — {frame_label}" if title else frame_label)
