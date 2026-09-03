"""Optional PDF outline (the sidebar "bookmarks" panel), via ``pypdf``.

A 200-page report without an outline is a scroll bar.  Matplotlib's PDF backend
cannot write one, so this is the single place the package reaches for a library
outside its hard dependencies — and it is entirely optional: without ``pypdf``
the report is written exactly the same, minus the outline.

    pip install 'cfd-plot[pdf]'
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Any

__all__ = ["HAS_PYPDF", "attach_outline", "count_pages"]

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised by whichever environment is installed
    import pypdf as _pypdf

    HAS_PYPDF = True
except ImportError:  # pragma: no cover
    _pypdf = None  # type: ignore[assignment]
    HAS_PYPDF = False

_WARNED = False


def _warn_once() -> None:
    """Log the missing-pypdf notice once per process, not once per report."""
    global _WARNED
    if not _WARNED:
        logger.info("pypdf is not installed — PDF written without an outline. pip install 'cfd-plot[pdf]'")
        _WARNED = True


def attach_outline(path: str | Path, entries: Sequence[tuple[str, int, int]]) -> bool:
    """Add a clickable outline to an existing PDF, rewriting it in place.

    Parameters
    ----------
    path : path
        The PDF to modify.
    entries : sequence of (title, page_index, depth)
        ``page_index`` is 0-based.  ``depth`` nests an entry under the most
        recent entry of a smaller depth.

    Returns
    -------
    bool
        ``True`` if the outline was written, ``False`` if ``pypdf`` is missing
        or the file could not be rewritten.  Never raises: an outline is a
        convenience, and losing a finished report to it would be a poor trade.
    """
    if not HAS_PYPDF or _pypdf is None:
        _warn_once()
        return False

    target = Path(path)
    try:
        reader = _pypdf.PdfReader(str(target))
        writer = _pypdf.PdfWriter()
        writer.append_pages_from_reader(reader)

        # Carry the document metadata across. append_pages_from_reader copies
        # pages only, so without this the Title/Author that PdfPages wrote are
        # replaced by a bare "/Producer: pypdf" — the metadata= argument would
        # silently do nothing for anyone who has pypdf installed.
        if reader.metadata:
            writer.add_metadata(reader.metadata)

        n_pages = len(reader.pages)
        parents: dict[int, Any] = {}
        for title, page_index, depth in entries:
            if not 0 <= page_index < n_pages:
                continue
            parent = parents.get(depth - 1) if depth > 0 else None
            item = writer.add_outline_item(title, page_index, parent=parent)
            parents[depth] = item
            # A new entry at this depth invalidates anything nested deeper.
            for deeper in [key for key in parents if key > depth]:
                del parents[deeper]

        # Write to a sibling then replace, so an error midway leaves the
        # original report intact rather than a truncated file.
        temporary = target.with_name(f"{target.stem}.outline-tmp{target.suffix}")
        with temporary.open("wb") as handle:
            writer.write(handle)
        temporary.replace(target)
    except Exception:
        logger.warning("Could not attach the PDF outline to %s; the report itself is fine.", target, exc_info=True)
        return False
    return True


def count_pages(path: str | Path) -> int:
    """Page count of a PDF, for tests and reporting.

    Raises
    ------
    RuntimeError
        If ``pypdf`` is not installed.
    """
    if not HAS_PYPDF or _pypdf is None:
        raise RuntimeError("count_pages() needs pypdf. pip install 'cfd-plot[pdf]'")
    return len(_pypdf.PdfReader(str(path)).pages)
