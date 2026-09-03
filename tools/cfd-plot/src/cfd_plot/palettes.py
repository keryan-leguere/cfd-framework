"""Named colour cycles for figure series.

Matplotlib's default cycle (``tab10``) is fine on screen and poor everywhere
else: two of its ten colours are indistinguishable to the ~8 % of men with a
red-green deficiency, and the whole cycle collapses when a reviewer prints the
paper in black and white.  This module ships a handful of cycles that survive
both, and a way to apply one **without** touching the caller's rcParams.

    from cfd_plot import palette_context, plot_line

    with palette_context("okabe_ito"):
        fig, ax = plt.subplots()
        for label, y in series.items():
            plot_line(ax, x, y, label=label)

``set_palette(ax=...)`` is the other scoped form, and the one to reach for in a
library: it sets the cycle on a single Axes and leaves the global state alone.
``set_palette`` without *ax* mutates rcParams, which is occasionally what you
want in a notebook and almost never what you want anywhere else.

The palettes
------------
``okabe_ito``
    Okabe & Ito's 8-colour qualitative set, designed for all three common forms
    of colour blindness.  The default recommendation.
``tol_bright``, ``tol_muted``
    Paul Tol's qualitative schemes — 7 and 9 colours.  ``tol_muted`` also
    carries a light grey meant for "bad data", kept as the last entry.
``grayscale``
    Six greys from near-black to light.  For print, and for checking that a
    figure still reads when the colour is gone.  Pair it with distinct markers
    (``plot_line`` already varies nothing — set ``marker=`` yourself).
``tab10``
    Matplotlib's default, for when you deliberately want it.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING

import matplotlib as mpl
from matplotlib.colors import to_hex, to_rgba

if TYPE_CHECKING:  # pragma: no cover - typing only
    from matplotlib.axes import Axes

__all__ = [
    "PALETTES",
    "palette_colors",
    "palette_context",
    "set_palette",
]


# Hex rather than named colours on purpose: these are exact published values,
# and a matplotlib named-colour lookup would be one indirection away from
# silently drifting if the name is ever remapped.
PALETTES: dict[str, tuple[str, ...]] = {
    # Okabe & Ito (2008), "Color Universal Design".  Black first so a
    # single-series figure comes out black, as a paper figure should.
    "okabe_ito": (
        "#000000",  # black
        "#E69F00",  # orange
        "#56B4E9",  # sky blue
        "#009E73",  # bluish green
        "#F0E442",  # yellow
        "#0072B2",  # blue
        "#D55E00",  # vermillion
        "#CC79A7",  # reddish purple
    ),
    # Paul Tol, "Colour Schemes" (SRON/EPS/TN/09-002), qualitative "bright".
    "tol_bright": (
        "#4477AA",
        "#EE6677",
        "#228833",
        "#CCBB44",
        "#66CCEE",
        "#AA3377",
        "#BBBBBB",
    ),
    # Same note, qualitative "muted".  The trailing pale grey is Tol's
    # designated "bad data" colour — kept last so it is reached only by a
    # figure with nine series, which is already too many.
    "tol_muted": (
        "#332288",
        "#88CCEE",
        "#44AA99",
        "#117733",
        "#999933",
        "#DDCC77",
        "#CC6677",
        "#882255",
        "#AA4499",
    ),
    # Evenly spaced in luminance, not in RGB: equal RGB steps read as
    # bunched-up darks because perceived lightness is roughly a power law.
    "grayscale": (
        "#000000",
        "#404040",
        "#6E6E6E",
        "#949494",
        "#B8B8B8",
        "#DADADA",
    ),
    "tab10": (
        "#1F77B4",
        "#FF7F0E",
        "#2CA02C",
        "#D62728",
        "#9467BD",
        "#8C564B",
        "#E377C2",
        "#7F7F7F",
        "#BCBD22",
        "#17BECF",
    ),
}

DEFAULT_PALETTE = "okabe_ito"


def _resolve(palette: str | Sequence[str]) -> tuple[str, ...]:
    """Turn a palette name or an explicit colour sequence into hex colours.

    Raises
    ------
    ValueError
        If *palette* names an unknown cycle, is empty, or contains something
        Matplotlib does not accept as a colour.
    """
    if isinstance(palette, str):
        try:
            return PALETTES[palette]
        except KeyError:
            known = ", ".join(sorted(PALETTES))
            raise ValueError(f"Unknown palette {palette!r}. Known palettes: {known}.") from None

    colors = tuple(palette)
    if not colors:
        raise ValueError("Palette is empty; give at least one colour.")

    resolved: list[str] = []
    for index, color in enumerate(colors):
        try:
            resolved.append(to_hex(to_rgba(color), keep_alpha=False))
        except ValueError:
            raise ValueError(f"Palette entry {index} ({color!r}) is not a valid Matplotlib colour.") from None
    return tuple(resolved)


def palette_colors(palette: str | Sequence[str] = DEFAULT_PALETTE, n: int | None = None) -> tuple[str, ...]:
    """Return the colours of *palette*, as hex strings.

    Parameters
    ----------
    palette : str or sequence of colours
        A key of :data:`PALETTES`, or an explicit sequence of Matplotlib colours.
    n : int, optional
        Number of colours wanted.  Longer than the palette, it **cycles** — the
        same thing Matplotlib's prop cycle does, made explicit here so a caller
        assigning colours by hand behaves identically to one that does not.

    Returns
    -------
    tuple of str
    """
    colors = _resolve(palette)
    if n is None:
        return colors
    if n < 0:
        raise ValueError(f"n must be >= 0, got {n}.")
    return tuple(colors[index % len(colors)] for index in range(n))


def set_palette(palette: str | Sequence[str] = DEFAULT_PALETTE, *, ax: Axes | None = None) -> tuple[str, ...]:
    """Apply *palette* as the colour cycle.

    Parameters
    ----------
    palette : str or sequence of colours
        A key of :data:`PALETTES`, or an explicit sequence of colours.
    ax : Axes, optional
        Set the cycle on this Axes only, leaving global rcParams untouched.
        **Prefer this form.**  With ``ax=None`` the change is global and
        permanent, which is rarely what a library caller wants — use
        :func:`palette_context` for a scoped global change.

    Returns
    -------
    tuple of str
        The colours applied, as hex.

    Notes
    -----
    Setting the cycle on an Axes that already has lines does not recolour them;
    Matplotlib draws the colour at plot time.  Call this before plotting.
    """
    colors = _resolve(palette)
    if ax is None:
        # matplotlib re-exports cycler() at the top level (it hard-depends on
        # the cycler package); its type stubs just do not declare it. Going
        # through matplotlib keeps cycler out of our dependency list.
        mpl.rcParams["axes.prop_cycle"] = mpl.cycler(color=list(colors))  # type: ignore[attr-defined]
    else:
        ax.set_prop_cycle(color=list(colors))
    return colors


@contextmanager
def palette_context(palette: str | Sequence[str] = DEFAULT_PALETTE) -> Iterator[tuple[str, ...]]:
    """Apply *palette* globally for the duration of the block, then restore.

    The previous ``axes.prop_cycle`` is restored exactly, including the case
    where it carried more than colour (a style sheet may cycle linestyle or
    marker alongside it — restoring only the colour would quietly drop those).
    """
    previous = mpl.rcParams["axes.prop_cycle"]
    colors = set_palette(palette)
    try:
        yield colors
    finally:
        mpl.rcParams["axes.prop_cycle"] = previous
