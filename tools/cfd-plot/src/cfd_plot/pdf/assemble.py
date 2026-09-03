"""Assemble figures into a single, navigable PDF report.

    pdf_report([fig1, fig2, fig3], "etude.pdf", title="Etude X")

    pdf_report(
        [
            ReportSection("ALPHA_POLAR", [fig_a, fig_b]),
            ReportSection("BETA_POLAR", [fig_c]),
        ],
        "etude.pdf",
        title="Etude X",
        subtitle="k-omega vs SA vs essais",
    )

Items are live ``Figure`` objects, paths to raster images, or nested
:class:`ReportSection`.  A ``Figure`` goes in as **vector** and stays sharp at
any zoom; a path is a raster and cannot be otherwise (Matplotlib has no
vector-to-vector import).  Prefer figures — which is why ``batch_plot`` builds
its report during the run rather than from the files it wrote.

Page numbering is resolved in two passes: the table of contents needs the page
of every entry, and its own length changes those pages.  The first pass lays out
the page plan and counts, the second paints it.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator, Sequence
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Union

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from PIL import Image

from ..mpl_template import style_context
from .pages import TocEntry, cover_page, page_inches, page_rc, paint_footer, section_page, toc_pages
from .sheet import image_grid_page, load_image

__all__ = [
    "PdfReportSpec",
    "ReportBuilder",
    "ReportItem",
    "ReportSection",
    "pdf_report",
]

logger = logging.getLogger(__name__)

# What a caller may put in a report. Recursive, hence the string form.
ReportItem = Union[str, Path, Figure, "ReportSection", "_Pending"]

# Raster DPI used when a vector figure has to be flattened, which happens only
# under n_up (several figures share one page and must be composited).
_RASTER_DPI = 200


@dataclass(frozen=True)
class ReportSection:
    """A titled group of items, nestable.

    Parameters
    ----------
    title : str
        Shown on the divider page and in the table of contents.
    items : sequence
        Figures, image paths, or further sections.
    caption : str, optional
        One line under the section title on its divider page.
    """

    title: str
    items: Sequence[ReportItem] = field(default_factory=tuple)
    caption: str | None = None


@dataclass(frozen=True)
class _Pending:
    """Stand-in for a figure supplied later, by :class:`ReportBuilder`.

    Lets the page plan (and therefore the table of contents) be computed before
    a single figure has been drawn — which is what allows a batch run of several
    hundred figures to stream into the PDF instead of being held in memory.
    """

    label: str


@dataclass(frozen=True)
class PdfReportSpec:
    """Report options, for callers that pass a report through another API.

    ``batch_plot(pdf_report=...)`` accepts a path for the common case and one of
    these when the defaults are not enough.
    """

    path: str | Path
    title: str | None = None
    subtitle: str | None = None
    toc: bool = True
    toc_depth: int = 1
    divider_depth: int = 0
    page_size: str | tuple[float, float] = "a4"
    landscape: bool = True
    n_up: tuple[int, int] | None = None
    footer: bool | Callable[[int, int], str] = True
    metadata: dict[str, str] | None = None
    profile: str = "paper"
    summary: Sequence[tuple[str, str]] = ()
    bookmarks: bool = True


# --------------------------------------------------------------------------
# Page plan
# --------------------------------------------------------------------------


@dataclass
class _Leaf:
    """One figure destined for the report, with the section path above it."""

    item: Figure | Path | _Pending
    trail: tuple[str, ...]
    label: str


@dataclass
class _ContentPage:
    leaves: list[_Leaf]
    heading: str


@dataclass
class _DividerPage:
    title: str
    caption: str | None
    depth: int


_PlanPage = Union[_ContentPage, _DividerPage]


def _label_for(item: Figure | Path | _Pending) -> str:
    if isinstance(item, _Pending):
        return item.label
    if isinstance(item, Path):
        return item.stem
    label = str(item.get_label())
    # Matplotlib names figures "figure 1", "figure 2", … by default; that is
    # noise in a table of contents, so treat it as unlabelled.
    return "" if not label or label.startswith("figure ") else label


def _walk(
    items: Sequence[ReportItem],
    trail: tuple[str, ...],
    plan: list[_PlanPage],
    *,
    n_up: tuple[int, int] | None,
    divider_depth: int,
    toc_depth: int,
    toc: list[TocEntry],
    depth: int,
) -> None:
    """Flatten the item tree into an ordered page plan, collecting TOC entries.

    Page numbers in *toc* are placeholders here; :func:`_number` fills them in
    once the front matter length is known.
    """
    per_page = 1 if n_up is None else n_up[0] * n_up[1]
    pending: list[_Leaf] = []

    def _flush() -> None:
        while pending:
            chunk = pending[:per_page]
            del pending[:per_page]
            plan.append(_ContentPage(leaves=chunk, heading=" / ".join(trail)))

    for item in items:
        if isinstance(item, ReportSection):
            _flush()
            # Capture the target page BEFORE the divider is appended: the entry
            # must point at the divider itself, or — when this depth gets no
            # divider — at the section's first content page. Recording it after
            # the append puts every section one page late.
            target = len(plan)
            if depth <= divider_depth:
                plan.append(_DividerPage(title=item.title, caption=item.caption, depth=depth))
            if depth <= toc_depth:
                toc.append(TocEntry(text=item.title, page=target, depth=depth))
            _walk(
                item.items,
                (*trail, item.title),
                plan,
                n_up=n_up,
                divider_depth=divider_depth,
                toc_depth=toc_depth,
                toc=toc,
                depth=depth + 1,
            )
        else:
            resolved: Figure | Path | _Pending = item if isinstance(item, (Figure, _Pending)) else Path(item)
            leaf = _Leaf(item=resolved, trail=trail, label=_label_for(resolved))
            if depth <= toc_depth and leaf.label:
                # pending is always shorter than per_page here (it is flushed
                # the moment it fills), so the next page appended is the one
                # this leaf lands on.
                toc.append(TocEntry(text=leaf.label, page=len(plan), depth=depth))
            pending.append(leaf)
            if len(pending) >= per_page:
                _flush()
    _flush()


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def _rasterise(fig: Figure) -> np.ndarray:
    """Flatten a figure to an RGBA array, for compositing under ``n_up``."""
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=_RASTER_DPI, bbox_inches="tight")
    buffer.seek(0)
    with Image.open(buffer) as handle:
        return np.asarray(handle.convert("RGBA"))


def _savefig_page(pdf: PdfPages, fig: Figure) -> None:
    """Write *fig* as one page, with the profiles' tight bbox forced off.

    The override has to sit here, at the write, not once around the whole
    document: anything that re-applies a style sheet in between — ``use_style``
    inside ``batch_plot``'s render loop, for one — puts ``savefig.bbox: tight``
    straight back, and the pages silently go back to being all different sizes.
    """
    with page_rc():
        pdf.savefig(fig)


@contextmanager
def _as_page(fig: Figure, page: tuple[float, float] | None, footer_text: str | None) -> Iterator[Figure]:
    """Temporarily size *fig* to the page and stamp a footer on it.

    The figure belongs to the caller, so the original size is restored and the
    footer artist removed on the way out — a report must not be a side effect
    that silently reshapes the figures it was handed.
    """
    original = tuple(fig.get_size_inches())
    artist = None
    try:
        if page is not None:
            fig.set_size_inches(*page)
        if footer_text:
            paint_footer(fig, footer_text)
            artist = fig.texts[-1]
        yield fig
    finally:
        if artist is not None:
            artist.remove()
        if page is not None:
            fig.set_size_inches(*original)


def _footer_text(footer: bool | Callable[[int, int], str], number: int, total: int) -> str | None:
    if callable(footer):
        return footer(number, total)
    return f"page {number} / {total}" if footer else None


def pdf_report(
    items: Sequence[ReportItem],
    output: str | Path,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    toc: bool = True,
    toc_depth: int = 1,
    divider_depth: int = 0,
    page_size: str | tuple[float, float] = "a4",
    landscape: bool = True,
    n_up: tuple[int, int] | None = None,
    footer: bool | Callable[[int, int], str] = True,
    metadata: dict[str, str] | None = None,
    profile: str = "paper",
    summary: Sequence[tuple[str, str]] = (),
    bookmarks: bool = True,
) -> Path:
    """Write *items* to a single multipage PDF.

    Parameters
    ----------
    items : sequence
        ``Figure`` objects (kept vector), paths to raster images, or
        :class:`ReportSection` groups.  Sections may nest.
    output : path
        Destination ``.pdf``.  Parent directories are created.
    title, subtitle : str, optional
        Give *title* to get a cover page.  Without it there is no cover.
    toc : bool
        Include a table of contents.  Ignored when there is nothing to list.
    toc_depth : int
        How deep to list.  ``0`` lists top-level sections only, ``1`` adds their
        immediate children, and so on.  Figures are listed at their own depth
        and only when they carry a label (``fig.set_label(...)``).
    divider_depth : int
        Insert a divider page for sections down to this depth.  The default
        ``0`` gives one divider per top-level section; deeper sections are
        announced by a heading on their content pages instead, which is what
        keeps a 200-figure report from being half divider pages.
    page_size, landscape : str or tuple, bool
        See :func:`~cfd_plot.pdf.pages.page_inches`.  ``page_size=None`` keeps
        each figure at its natural size, giving a PDF of mixed page sizes.
    n_up : tuple, optional
        ``(rows, cols)`` to put several figures on a page.  **Figures are
        rasterised** in this mode: compositing them is not possible otherwise.
    footer : bool or callable
        ``True`` stamps ``page n / N``.  A callable receives ``(number, total)``
        and returns the string.
    metadata : dict, optional
        PDF document metadata (``Title``, ``Author``, ``Subject``, ``Keywords``).
        *title* fills ``Title`` when not given explicitly.
    summary : sequence of (label, value)
        Rows for the cover page — run facts, not prose.
    bookmarks : bool
        Attach a clickable PDF outline mirroring the sections.  Needs ``pypdf``
        (``pip install 'cfd-plot[pdf]'``); without it the report is written
        exactly the same, minus the outline.

    Returns
    -------
    Path
        The file written.

    Raises
    ------
    ValueError
        If *items* is empty, or *n_up* is not two positive integers.
    """
    if not items:
        raise ValueError("pdf_report() needs at least one item.")
    if n_up is not None and (len(n_up) != 2 or n_up[0] < 1 or n_up[1] < 1):
        raise ValueError(f"n_up must be (rows, cols) with both >= 1, got {n_up!r}.")

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    page = None if page_size is None else page_inches(page_size, landscape=landscape)

    plan: list[_PlanPage] = []
    toc_entries: list[TocEntry] = []
    _walk(
        items,
        (),
        plan,
        n_up=n_up,
        divider_depth=divider_depth,
        toc_depth=toc_depth,
        toc=toc_entries,
        depth=0,
    )

    # ---- pass 1: how long is the front matter, and therefore every page number
    front = 1 if title else 0
    toc_figs: list[Figure] = []
    want_toc = toc and bool(toc_entries)
    if want_toc:
        # Painted twice: once to learn how many pages it needs (which shifts
        # every entry), then again with the corrected numbers.
        probe = toc_pages(page or page_inches("a4", landscape=landscape), toc_entries)
        for fig in probe:
            plt.close(fig)
        front += len(probe)

    offset = front + 1  # 1-based page numbers
    numbered = [TocEntry(text=e.text, page=e.page + offset, depth=e.depth) for e in toc_entries]
    total = front + len(plan)

    doc_metadata = {"Title": title} if title else {}
    if metadata:
        doc_metadata.update(metadata)

    written_outline: list[tuple[str, int, int]] = []

    with style_context(profile), page_rc(), PdfPages(out, metadata=doc_metadata or None) as pdf:
        number = 1

        if title:
            cover = cover_page(page or page_inches("a4"), title=title, subtitle=subtitle, summary=summary)
            _savefig_page(pdf, cover)
            plt.close(cover)
            number += 1

        if want_toc:
            toc_figs = toc_pages(page or page_inches("a4", landscape=landscape), numbered)
            for fig in toc_figs:
                _savefig_page(pdf, fig)
                plt.close(fig)
                number += 1

        for entry in plan:
            if isinstance(entry, _DividerPage):
                written_outline.append((entry.title, number - 1, entry.depth))
                fig = section_page(page or page_inches("a4"), title=entry.title, caption=entry.caption)
                text = _footer_text(footer, number, total)
                if text:
                    paint_footer(fig, text)
                _savefig_page(pdf, fig)
                plt.close(fig)
            else:
                _render_content_page(pdf, entry, page, n_up, footer, number, total)
            number += 1

    if bookmarks and written_outline:
        from .bookmarks import attach_outline

        attach_outline(out, written_outline)

    logger.debug("pdf_report: %d page(s) -> %s", total, out)
    return out


def _render_content_page(
    pdf: PdfPages,
    entry: _ContentPage,
    page: tuple[float, float] | None,
    n_up: tuple[int, int] | None,
    footer: bool | Callable[[int, int], str],
    number: int,
    total: int,
) -> None:
    """Draw one page of figures."""
    text = _footer_text(footer, number, total)

    # Narrow away the streaming placeholder once, here, rather than at each use.
    items: list[Figure | Path] = []
    for leaf in entry.leaves:
        if isinstance(leaf.item, _Pending):  # pragma: no cover - planner invariant
            raise RuntimeError("A placeholder reached the renderer; stream through ReportBuilder instead.")
        items.append(leaf.item)

    if n_up is None:
        leaf, only = entry.leaves[0], items[0]
        if isinstance(only, Figure):
            # The vector path: the caller's own figure goes straight in.
            with _as_page(only, page, text) as fig:
                _savefig_page(pdf, fig)
            return
        images = [load_image(only)]
        fig = image_grid_page(
            page or page_inches("a4"),
            images,
            labels=[leaf.label] if leaf.label else None,
            rows=1,
            cols=1,
            title=entry.heading or None,
        )
    else:
        rows, cols = n_up
        images = [_rasterise(item) if isinstance(item, Figure) else load_image(item) for item in items]
        fig = image_grid_page(
            page or page_inches("a4"),
            images,
            labels=[leaf.label for leaf in entry.leaves],
            rows=rows,
            cols=cols,
            title=entry.heading or None,
        )

    if text:
        paint_footer(fig, text)
    _savefig_page(pdf, fig)
    plt.close(fig)


# --------------------------------------------------------------------------
# Streaming builder
# --------------------------------------------------------------------------


def _tree_from_trails(entries: Sequence[tuple[tuple[str, ...], str]]) -> list[ReportItem]:
    """Rebuild a nested section tree from a flat, ordered list of trails.

    ``[(("A", "M1"), "f1"), (("A", "M1"), "f2"), (("A", "M2"), "f3")]`` becomes
    ``[Section("A", [Section("M1", [f1, f2]), Section("M2", [f3])])]``.

    Grouping is by *consecutive* runs, not by set membership: the caller's order
    is the report's order, and a trail that reappears later legitimately makes a
    second section rather than reordering the document.
    """
    root: list[ReportItem] = []
    stack: list[tuple[str, list[ReportItem]]] = []

    def close_to(depth: int) -> None:
        while len(stack) > depth:
            name, items = stack.pop()
            parent = stack[-1][1] if stack else root
            parent.append(ReportSection(name, tuple(items)))

    current: tuple[str, ...] = ()
    for trail, label in entries:
        common = 0
        while common < len(current) and common < len(trail) and current[common] == trail[common]:
            common += 1
        close_to(common)
        for name in trail[len(stack) :]:
            stack.append((name, []))
        target = stack[-1][1] if stack else root
        target.append(_Pending(label))
        current = trail

    close_to(0)
    return root


class ReportBuilder:
    """Write a report while the figures are still being produced.

    The page plan — and therefore every table-of-contents page number — is
    computed up front from the *labels alone*, so figures can be handed over one
    at a time and closed immediately.  That is the difference between a report
    of 500 figures costing one figure of memory and costing 500.

        with ReportBuilder(spec, [(("ALPHA_POLAR",), "CN vs alpha"), ...]) as builder:
            for job in jobs:
                fig = render(job)
                builder.add(fig)
                plt.close(fig)

    Parameters
    ----------
    spec : PdfReportSpec
        Output path and report options.
    entries : sequence of (trail, label)
        One per figure, **in the order they will be added**.  ``trail`` is the
        tuple of section titles above that figure.

    Raises
    ------
    ValueError
        If *entries* is empty, or if more figures are added than were declared.
    """

    def __init__(self, spec: PdfReportSpec, entries: Sequence[tuple[tuple[str, ...], str]]) -> None:
        if not entries:
            raise ValueError("ReportBuilder needs at least one entry.")
        self.spec = spec
        self._expected = len(entries)
        self._added = 0
        self._page = None if spec.page_size is None else page_inches(spec.page_size, landscape=spec.landscape)
        self._buffer: list[np.ndarray] = []
        self._outline: list[tuple[str, int, int]] = []
        self._number = 1
        self._plan_index = 0
        self._pdf: PdfPages | None = None
        self._style: Any = None

        tree = _tree_from_trails(entries)
        self._plan: list[_PlanPage] = []
        toc_entries: list[TocEntry] = []
        _walk(
            tree,
            (),
            self._plan,
            n_up=spec.n_up,
            divider_depth=spec.divider_depth,
            toc_depth=spec.toc_depth,
            toc=toc_entries,
            depth=0,
        )

        front = 1 if spec.title else 0
        self._want_toc = spec.toc and bool(toc_entries)
        if self._want_toc:
            probe = toc_pages(self._page or page_inches("a4", landscape=spec.landscape), toc_entries)
            for fig in probe:
                plt.close(fig)
            front += len(probe)
        self._front = front
        self._toc = [TocEntry(text=e.text, page=e.page + front + 1, depth=e.depth) for e in toc_entries]
        self.total_pages = front + len(self._plan)

    # -- lifecycle ---------------------------------------------------------

    def __enter__(self) -> ReportBuilder:
        out = Path(self.spec.path)
        out.parent.mkdir(parents=True, exist_ok=True)

        metadata = {"Title": self.spec.title} if self.spec.title else {}
        if self.spec.metadata:
            metadata.update(self.spec.metadata)

        self._style = ExitStack()
        self._style.enter_context(style_context(self.spec.profile))
        self._style.enter_context(page_rc())
        self._pdf = PdfPages(out, metadata=metadata or None)

        page = self._page or page_inches("a4")
        if self.spec.title:
            cover = cover_page(page, title=self.spec.title, subtitle=self.spec.subtitle, summary=self.spec.summary)
            _savefig_page(self._pdf, cover)
            plt.close(cover)
            self._number += 1
        if self._want_toc:
            for fig in toc_pages(self._page or page_inches("a4", landscape=self.spec.landscape), self._toc):
                _savefig_page(self._pdf, fig)
                plt.close(fig)
                self._number += 1
        return self

    def __exit__(self, *exc_info: object) -> None:
        try:
            if self._pdf is not None:
                self._flush_dividers(to_end=True)
                self._pdf.close()
        finally:
            self._pdf = None
            if self._style is not None:
                self._style.close()
                self._style = None

        if exc_info[0] is None and self.spec.bookmarks and self._outline:
            from .bookmarks import attach_outline

            attach_outline(self.spec.path, self._outline)

    # -- feeding -----------------------------------------------------------

    def add(self, fig: Figure) -> None:
        """Append *fig* to the report.

        The figure is not closed and not permanently resized — that stays the
        caller's business.  Under ``n_up`` it is rasterised immediately, so it
        is safe to close it as soon as this returns.
        """
        if self._pdf is None:
            raise RuntimeError("ReportBuilder.add() outside the context manager.")
        if self._added >= self._expected:
            raise ValueError(f"More figures added than declared ({self._expected}).")
        self._added += 1

        self._flush_dividers()
        page_entry = self._plan[self._plan_index]
        assert isinstance(page_entry, _ContentPage)

        if self.spec.n_up is None:
            text = _footer_text(self.spec.footer, self._number, self.total_pages)
            with _as_page(fig, self._page, text) as sized:
                _savefig_page(self._pdf, sized)
            self._advance()
            return

        self._buffer.append(_rasterise(fig))
        if len(self._buffer) >= len(page_entry.leaves):
            self._emit_grid(page_entry)

    def _emit_grid(self, page_entry: _ContentPage) -> None:
        rows, cols = self.spec.n_up  # type: ignore[misc]
        assert self._pdf is not None
        fig = image_grid_page(
            self._page or page_inches("a4"),
            self._buffer,
            labels=[leaf.label for leaf in page_entry.leaves],
            rows=rows,
            cols=cols,
            title=page_entry.heading or None,
        )
        text = _footer_text(self.spec.footer, self._number, self.total_pages)
        if text:
            paint_footer(fig, text)
        _savefig_page(self._pdf, fig)
        plt.close(fig)
        self._buffer.clear()
        self._advance()

    def _advance(self) -> None:
        self._plan_index += 1
        self._number += 1

    def _flush_dividers(self, *, to_end: bool = False) -> None:
        """Emit divider pages sitting between here and the next content page."""
        assert self._pdf is not None
        page = self._page or page_inches("a4")
        while self._plan_index < len(self._plan):
            entry = self._plan[self._plan_index]
            if isinstance(entry, _ContentPage):
                if not to_end:
                    return
                # Reached at exit with content still planned: fewer figures were
                # added than declared. Stop rather than emit blank pages.
                return
            self._outline.append((entry.title, self._number - 1, entry.depth))
            fig = section_page(page, title=entry.title, caption=entry.caption)
            text = _footer_text(self.spec.footer, self._number, self.total_pages)
            if text:
                paint_footer(fig, text)
            _savefig_page(self._pdf, fig)
            plt.close(fig)
            self._advance()
