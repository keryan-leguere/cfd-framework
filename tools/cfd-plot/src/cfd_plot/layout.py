"""Figure-assembly helpers: labelling the panels of a multi-panel figure.

A journal wants ``(a)``, ``(b)``, ``(c)`` on the panels so the caption can refer
to them.  Doing it by hand is four ``ax.text`` calls with four sets of
hand-tuned coordinates, redone every time the layout changes.

    fig, axes = new_figure(2, 2)
    ...
    panel_labels(axes)

Labels are placed in **axes coordinates**, so they stay put when the data limits
change, when the axes are shared, or when constrained layout reflows the figure.
"""

from __future__ import annotations

from collections.abc import Sequence
from string import ascii_lowercase
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - typing only
    from matplotlib.axes import Axes
    from matplotlib.text import Text

__all__ = ["panel_labels"]


# (x, y, ha, va) in axes coordinates, before the *offset* is applied.
_CORNERS: dict[str, tuple[float, float, str, str]] = {
    "upper left": (0.0, 1.0, "left", "top"),
    "upper right": (1.0, 1.0, "right", "top"),
    "lower left": (0.0, 0.0, "left", "bottom"),
    "lower right": (1.0, 0.0, "right", "bottom"),
}


def _flatten_axes(axes: Axes | Sequence[Axes] | np.ndarray) -> list[Axes]:
    """Accept a single Axes, a nested sequence, or the array ``new_figure`` returns."""
    if hasattr(axes, "flat") and not isinstance(axes, (list, tuple)):
        # A numpy object array from plt.subplots(nrows, ncols) — row-major,
        # which is the reading order the labels should follow.
        return list(np.asarray(axes).ravel())
    if isinstance(axes, (list, tuple)):
        flat: list[Axes] = []
        for item in axes:
            flat.extend(_flatten_axes(item))
        return flat
    return [axes]  # type: ignore[list-item]


def _default_labels(n: int) -> list[str]:
    """``a … z``, then ``aa, ab, …`` so a 30-panel figure does not repeat itself."""
    labels: list[str] = []
    for index in range(n):
        name = ""
        value = index
        while True:
            name = ascii_lowercase[value % 26] + name
            value = value // 26 - 1
            if value < 0:
                break
        labels.append(name)
    return labels


def panel_labels(
    axes: Axes | Sequence[Axes] | np.ndarray,
    *,
    labels: Sequence[str] | None = None,
    fmt: str = "({})",
    loc: str = "upper left",
    offset: tuple[float, float] = (0.02, -0.02),
    outside: bool = False,
    skip_invisible: bool = True,
    **text_kw: Any,
) -> list[Text]:
    """Tag each panel of a multi-panel figure with ``(a)``, ``(b)``, ``(c)``, …

    Parameters
    ----------
    axes : Axes, sequence of Axes, or ndarray of Axes
        Typically the second value returned by :func:`~cfd_plot.new_figure`.
        A 2-D array is flattened **row-major**, i.e. reading order.
    labels : sequence of str, optional
        Explicit labels.  Default is ``a``, ``b``, … continuing to ``aa``, ``ab``
        past 26 panels.  Must be at least as long as the number of panels.
    fmt : str
        Format applied to each label.  ``"({})"`` gives ``(a)``, ``"{}."`` gives
        ``a.``, ``"{}"`` gives a bare letter.
    loc : {"upper left", "upper right", "lower left", "lower right"}
        Which corner of the axes to anchor to.
    offset : tuple of float
        ``(dx, dy)`` in axes coordinates, added to the corner.  The default nudges
        the label just inside the upper-left corner.
    outside : bool
        Place the label *above* the axes (clear of the frame and any title)
        instead of inside it.  Use when the panels are tight and a label inside
        would land on the data.
    skip_invisible : bool
        Skip axes with ``visible=False``.  ``plt.subplots`` on a grid larger than
        the number of panels leaves blank axes behind; labelling those would
        shift every subsequent letter.
    **text_kw
        Forwarded to ``ax.text`` (``fontsize``, ``color``, ``bbox``, …).

    Returns
    -------
    list of Text
        One per labelled panel, in the order they were labelled.

    Raises
    ------
    ValueError
        If *loc* is not one of the four corners, or *labels* is too short.

    Examples
    --------
    >>> fig, axes = new_figure(2, 2)                        # doctest: +SKIP
    >>> panel_labels(axes, fmt="{}.", loc="upper right")    # doctest: +SKIP
    """
    if loc not in _CORNERS:
        known = ", ".join(sorted(_CORNERS))
        raise ValueError(f"Unknown loc {loc!r}. Expected one of: {known}.")

    panels = _flatten_axes(axes)
    if skip_invisible:
        panels = [ax for ax in panels if ax.get_visible()]

    if labels is None:
        texts_wanted = _default_labels(len(panels))
    else:
        texts_wanted = list(labels)
        if len(texts_wanted) < len(panels):
            raise ValueError(f"Got {len(texts_wanted)} label(s) for {len(panels)} panel(s).")

    x0, y0, ha, va = _CORNERS[loc]
    dx, dy = offset

    if outside:
        # Above the axes, on the same side as the anchor corner. The vertical
        # anchor flips to "bottom" so the text sits clear of the frame rather
        # than straddling it.
        x, y, va = x0 + dx, 1.0 + abs(dy), "bottom"
    else:
        x, y = x0 + dx, y0 + dy

    kw: dict[str, Any] = {"fontweight": "bold"}
    kw.update(text_kw)

    out: list[Text] = []
    for ax, label in zip(panels, texts_wanted):
        out.append(
            ax.text(
                x,
                y,
                fmt.format(label),
                transform=ax.transAxes,
                ha=ha,
                va=va,
                **kw,
            )
        )
    return out
