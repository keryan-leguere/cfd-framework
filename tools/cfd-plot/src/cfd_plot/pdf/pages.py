"""Painters for the pages a report has that are not figures.

Cover, table of contents, section dividers, footers.  Each painter builds a
plain Matplotlib figure sized to the page and hands it back; :mod:`assemble`
decides when to draw them and writes them out.  Nothing here touches global
state — the caller wraps everything in ``style_context``.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

__all__ = [
    "PAGE_SIZES",
    "TocEntry",
    "blank_page",
    "cover_page",
    "page_inches",
    "page_rc",
    "paint_footer",
    "section_page",
    "toc_entries_per_page",
    "toc_pages",
]


# Page sizes in inches, portrait (width, height).
PAGE_SIZES: dict[str, tuple[float, float]] = {
    "a4": (8.268, 11.693),
    "a3": (11.693, 16.535),
    "a5": (5.827, 8.268),
    "letter": (8.5, 11.0),
    "legal": (8.5, 14.0),
}

# Margins in inches. Generous on purpose: a report is read on screen and
# printed, and a figure that runs to the paper edge loses a strip to both.
_MARGIN = 0.6
_FOOTER_HEIGHT = 0.35


@contextmanager
def page_rc() -> Iterator[None]:
    """Turn off the style profiles' tight bounding box while writing pages.

    All three profiles set ``savefig.bbox: tight`` (see ``styles/*.mplstyle``),
    which crops a saved figure to its ink.  That is right for a standalone
    figure and wrong for a page: it yields a document whose pages are all
    slightly different sizes, and a *page size* that silently ignores the one
    the caller asked for.

    Passing ``bbox_inches=None`` per call does **not** work — Matplotlib reads
    that as "unset" and falls back to the rcParam — so the rcParam itself has to
    go, which is what this does.
    """
    with mpl.rc_context({"savefig.bbox": None, "savefig.pad_inches": 0.0}):
        yield


def page_inches(page_size: str | tuple[float, float], *, landscape: bool = False) -> tuple[float, float]:
    """Resolve a page size to ``(width, height)`` in inches.

    Parameters
    ----------
    page_size : str or tuple
        A key of :data:`PAGE_SIZES` (case-insensitive) or an explicit
        ``(width, height)`` in inches.
    landscape : bool
        Swap the two dimensions.  Applied to explicit tuples as well, so
        ``page_inches((4, 3), landscape=True)`` is ``(4, 3)`` reordered to the
        wider-first convention rather than left alone.

    Raises
    ------
    ValueError
        If the name is unknown, or the explicit size is not two positive numbers.
    """
    if isinstance(page_size, str):
        try:
            width, height = PAGE_SIZES[page_size.lower()]
        except KeyError:
            known = ", ".join(sorted(PAGE_SIZES))
            raise ValueError(f"Unknown page size {page_size!r}. Known sizes: {known}.") from None
    else:
        size = tuple(float(value) for value in page_size)
        if len(size) != 2 or size[0] <= 0 or size[1] <= 0:
            raise ValueError(f"page_size must be two positive numbers in inches, got {page_size!r}.")
        width, height = size

    if landscape:
        width, height = max(width, height), min(width, height)
    return width, height


def blank_page(page: tuple[float, float]) -> tuple[Figure, Axes]:
    """A page-sized figure with one full-bleed, invisible, 0-1 axes."""
    fig = plt.figure(figsize=page)
    # No constrained layout here: these pages position everything in figure
    # coordinates, and a layout engine would fight that (and warn about it).
    fig.set_layout_engine("none")
    ax = fig.add_axes((0.0, 0.0, 1.0, 1.0))
    ax.set_axis_off()
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    return fig, ax


def paint_footer(fig: Figure, text: str) -> None:
    """Write *text* centred in the bottom margin of *fig*."""
    fig.text(0.5, 0.025, text, ha="center", va="bottom", fontsize=8, color="0.35")


def cover_page(
    page: tuple[float, float],
    *,
    title: str,
    subtitle: str | None = None,
    summary: Sequence[tuple[str, str]] = (),
    date: str | None = None,
) -> Figure:
    """Title page: title, optional subtitle, a date, and a key/value summary.

    Parameters
    ----------
    summary : sequence of (label, value)
        Drawn as two aligned columns under a rule.  Meant for run facts —
        figure count, sweeps, sources — not for prose.
    date : str, optional
        Defaults to today, ISO format.
    """
    fig, ax = blank_page(page)
    width, height = page

    # Title block sits at the optical centre (~62 % up), not the true centre.
    ax.text(0.5, 0.66, title, ha="center", va="bottom", fontsize=26, wrap=True)
    if subtitle:
        ax.text(0.5, 0.625, subtitle, ha="center", va="top", fontsize=14, color="0.3")

    ax.plot([0.22, 0.78], [0.60, 0.60], color="0.75", linewidth=0.8, clip_on=False)

    stamp = date if date is not None else _dt.date.today().isoformat()
    ax.text(0.5, 0.575, stamp, ha="center", va="top", fontsize=10, color="0.45")

    if summary:
        # One line per entry, label right-aligned against value left-aligned,
        # so the two columns meet at the centre and read as a table.
        line_height = 0.30 / max(len(summary), 10)
        y = 0.46
        for label, value in summary:
            ax.text(0.48, y, f"{label}", ha="right", va="top", fontsize=10, color="0.4")
            ax.text(0.52, y, f"{value}", ha="left", va="top", fontsize=10)
            y -= line_height

    del width, height
    return fig


@dataclass(frozen=True)
class TocEntry:
    """One line of the table of contents."""

    text: str
    page: int
    depth: int = 0


def toc_entries_per_page(page: tuple[float, float]) -> int:
    """How many TOC lines fit on a page of this size.

    Derived from the page height rather than fixed, so A5 and A3 both behave.
    """
    _, height = page
    usable = height - 2 * _MARGIN - _FOOTER_HEIGHT - 0.9  # 0.9in for the heading
    lines = int(usable / 0.22)  # 0.22in per line at fontsize 10
    return max(lines, 1)


def toc_pages(
    page: tuple[float, float],
    entries: Sequence[TocEntry],
    *,
    title: str = "Contents",
) -> list[Figure]:
    """Paint the table of contents, one figure per page.

    Leader dots are deliberately absent: they need text metrics to look right,
    and a wrong-length dot run reads worse than none at all.  The page number is
    right-aligned instead, which is unambiguous at any width.
    """
    per_page = toc_entries_per_page(page)
    chunks = [entries[i : i + per_page] for i in range(0, len(entries), per_page)] or [[]]

    width, height = page
    left = _MARGIN / width
    right = 1.0 - _MARGIN / width
    line_height = 0.22 / height

    figures: list[Figure] = []
    for index, chunk in enumerate(chunks):
        fig, ax = blank_page(page)
        heading = title if index == 0 else f"{title} (cont.)"
        ax.text(left, 1.0 - _MARGIN / height, heading, ha="left", va="top", fontsize=18)

        y = 1.0 - (_MARGIN + 0.75) / height
        for entry in chunk:
            indent = left + entry.depth * (0.22 / width)
            color = "0.15" if entry.depth == 0 else "0.4"
            size = 10.5 if entry.depth == 0 else 9.5
            ax.text(indent, y, entry.text, ha="left", va="top", fontsize=size, color=color)
            ax.text(right, y, str(entry.page), ha="right", va="top", fontsize=size, color=color)
            y -= line_height
        figures.append(fig)
    return figures


def section_page(page: tuple[float, float], *, title: str, caption: str | None = None) -> Figure:
    """A divider page announcing a section."""
    fig, ax = blank_page(page)
    ax.text(0.5, 0.54, title, ha="center", va="bottom", fontsize=22, wrap=True)
    ax.plot([0.3, 0.7], [0.51, 0.51], color="0.75", linewidth=0.8, clip_on=False)
    if caption:
        ax.text(0.5, 0.48, caption, ha="center", va="top", fontsize=11, color="0.35", wrap=True)
    return fig
