"""Contact sheets: many saved figures, N-up on a page.

The point is triage.  A parametric study writes hundreds of figures into a
nested tree; a contact sheet puts them all in front of you at once so you can
spot the one that went wrong, then go open it full size.

Images are placed by fitting each one's own aspect ratio inside its grid cell
and sizing the axes to match, rather than by letting ``imshow`` letterbox inside
a fixed cell.  Letterboxing leaves grey margins that make a regular grid look
ragged, and it is the default outcome of the obvious implementation.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from PIL import Image

from ..mpl_template import style_context
from .pages import blank_page, page_inches, page_rc, paint_footer

__all__ = ["contact_sheet", "image_grid_page", "load_image"]

logger = logging.getLogger(__name__)

# Raster formats Pillow reads and Matplotlib can draw. SVG is deliberately not
# here — see load_image.
_RASTER_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".webp"})


def load_image(path: str | Path) -> np.ndarray:
    """Read a raster image as an RGB(A) array.

    Raises
    ------
    ValueError
        If *path* is an SVG or PDF.  Neither can be embedded in a Matplotlib
        page: there is no vector-to-vector path in Matplotlib, so a report built
        from files on disk has to read rasters.  The message says what to do
        instead, because this is the mistake a caller makes first — ``batch_plot``
        writes SVG by default.
    FileNotFoundError
        If the file does not exist.
    """
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix in {".svg", ".svgz", ".pdf", ".eps", ".emf"}:
        raise ValueError(
            f"{p.name}: {suffix} is a vector format and cannot be placed on a Matplotlib page. "
            "Either export the figures as PNG too (batch_plot(..., formats=('svg', 'png'))) "
            "and point this at the PNGs, or build the report during the run with "
            "batch_plot(..., pdf_report=...), which keeps the figures vector."
        )
    if suffix not in _RASTER_SUFFIXES:
        known = ", ".join(sorted(_RASTER_SUFFIXES))
        raise ValueError(f"{p.name}: unsupported image format {suffix!r}. Expected one of: {known}.")
    if not p.is_file():
        raise FileNotFoundError(f"Image not found: {p}")

    with Image.open(p) as handle:
        return np.asarray(handle.convert("RGBA"))


def _fit(cell: tuple[float, float], aspect: float) -> tuple[float, float]:
    """Largest ``(w, h)`` of the given *aspect* (w/h) fitting inside *cell*."""
    cell_w, cell_h = cell
    if cell_w / cell_h > aspect:
        return aspect * cell_h, cell_h
    return cell_w, cell_w / aspect


def image_grid_page(
    page: tuple[float, float],
    images: Sequence[np.ndarray],
    *,
    labels: Sequence[str] | None = None,
    rows: int,
    cols: int,
    title: str | None = None,
    margin: float = 0.5,
    label_height: float = 0.22,
) -> Figure:
    """Lay *images* out ``rows × cols`` on one page-sized figure.

    Parameters
    ----------
    page : tuple
        ``(width, height)`` in inches.
    images : sequence of ndarray
        At most ``rows * cols``; a short sequence leaves the trailing cells empty.
    labels : sequence of str, optional
        One caption per image, drawn under it and truncated to fit.
    margin, label_height : float
        Inches.  ``label_height`` is reserved under every cell whether or not
        there is a label, so the grid stays regular.
    """
    if rows < 1 or cols < 1:
        raise ValueError(f"rows and cols must be >= 1, got rows={rows}, cols={cols}.")
    if len(images) > rows * cols:
        raise ValueError(f"{len(images)} images do not fit in a {rows}x{cols} grid.")

    width, height = page
    fig, _ = blank_page(page)

    top = margin
    if title:
        fig.text(margin / width, 1.0 - margin / height, title, ha="left", va="top", fontsize=13)
        top = margin + 0.45

    grid_w = width - 2 * margin
    grid_h = height - top - margin
    cell_w = grid_w / cols
    cell_h = grid_h / rows
    reserved = label_height if labels else 0.0
    inner = (cell_w * 0.94, max(cell_h - reserved, 0.1) * 0.94)

    for index, image in enumerate(images):
        row, col = divmod(index, cols)
        aspect = image.shape[1] / image.shape[0]
        draw_w, draw_h = _fit(inner, aspect)

        # Cell origin, measured from the top of the grid downwards.
        cell_x = margin + col * cell_w
        cell_y = height - top - (row + 1) * cell_h

        # Image and caption are placed as one block, centred in the cell.
        # Centring them independently is what leaves a caption stranded at the
        # bottom of a tall cell, half a page from the figure it names.
        block_h = draw_h + reserved
        block_y = cell_y + (cell_h - block_h) / 2

        x = cell_x + (cell_w - draw_w) / 2
        y = block_y + reserved

        ax = fig.add_axes((x / width, y / height, draw_w / width, draw_h / height))
        ax.imshow(image, aspect="auto", interpolation="antialiased")
        ax.set_axis_off()

        if labels is not None and index < len(labels):
            fig.text(
                (cell_x + cell_w / 2) / width,
                (block_y + reserved * 0.45) / height,
                labels[index],
                ha="center",
                va="center",
                fontsize=7,
                color="0.3",
            )
    return fig


def contact_sheet(
    images: Sequence[str | Path],
    output: str | Path,
    *,
    cols: int = 3,
    rows: int = 4,
    labels: Sequence[str] | None = None,
    page_size: str | tuple[float, float] = "a4",
    landscape: bool = False,
    title: str | None = None,
    profile: str = "paper",
    footer: bool = True,
) -> list[Path]:
    """Tile saved raster figures onto pages and write them out.

    Parameters
    ----------
    images : sequence of path
        Raster images (PNG, JPEG, …).  **Not SVG** — see :func:`load_image` for
        why, and what to do instead.
    output : path
        ``.pdf`` writes one multipage document; ``.png`` writes one file per
        page, numbered ``name_01.png``, ``name_02.png``, …
    cols, rows : int
        Grid per page.  ``rows * cols`` images per page.
    labels : sequence of str, optional
        Captions, one per image.  Defaults to each file's stem.
    title : str, optional
        Printed at the top of every page, with the page number appended.
    footer : bool
        Draw ``page n / N`` in the bottom margin.

    Returns
    -------
    list of Path
        The file(s) written.

    Raises
    ------
    ValueError
        If *images* is empty, the grid is degenerate, or the output suffix is
        neither ``.pdf`` nor a supported raster format.
    """
    paths = [Path(p) for p in images]
    if not paths:
        raise ValueError("contact_sheet() needs at least one image.")
    if rows < 1 or cols < 1:
        raise ValueError(f"rows and cols must be >= 1, got rows={rows}, cols={cols}.")
    if labels is not None and len(labels) != len(paths):
        raise ValueError(f"Got {len(labels)} label(s) for {len(paths)} image(s).")

    out = Path(output)
    suffix = out.suffix.lower()
    if suffix not in {".pdf", ".png"}:
        raise ValueError(f"contact_sheet() writes .pdf or .png, got {out.suffix!r}.")
    out.parent.mkdir(parents=True, exist_ok=True)

    captions = list(labels) if labels is not None else [p.stem for p in paths]
    page = page_inches(page_size, landscape=landscape)
    per_page = rows * cols
    chunks = [(paths[i : i + per_page], captions[i : i + per_page]) for i in range(0, len(paths), per_page)]
    total = len(chunks)

    written: list[Path] = []
    with style_context(profile), page_rc():
        if suffix == ".pdf":
            with PdfPages(out) as pdf:
                for index, (chunk, chunk_labels) in enumerate(chunks, start=1):
                    fig = _sheet_figure(page, chunk, chunk_labels, rows, cols, title, index, total, footer)
                    with page_rc():
                        pdf.savefig(fig)
                    plt.close(fig)
            written.append(out)
        else:
            for index, (chunk, chunk_labels) in enumerate(chunks, start=1):
                fig = _sheet_figure(page, chunk, chunk_labels, rows, cols, title, index, total, footer)
                target = out if total == 1 else out.with_name(f"{out.stem}_{index:02d}{out.suffix}")
                with page_rc():
                    fig.savefig(target)
                plt.close(fig)
                written.append(target)

    logger.debug("contact_sheet: %d image(s) over %d page(s) -> %s", len(paths), total, out)
    return written


def _sheet_figure(
    page: tuple[float, float],
    chunk: Sequence[Path],
    chunk_labels: Sequence[str],
    rows: int,
    cols: int,
    title: str | None,
    index: int,
    total: int,
    footer: bool,
) -> Figure:
    """One page of a contact sheet."""
    loaded = [load_image(p) for p in chunk]
    heading = None if title is None else (title if total == 1 else f"{title} — {index}/{total}")
    fig = image_grid_page(page, loaded, labels=list(chunk_labels), rows=rows, cols=cols, title=heading)
    if footer:
        paint_footer(fig, f"page {index} / {total}")
    return fig
