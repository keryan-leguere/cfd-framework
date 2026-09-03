"""PDF reports: turn a pile of figures into one document you can hand over.

Grouped by layer, which is how the module is meant to be read.

Pages (the parts that are not figures)
    PAGE_SIZES, page_inches   — page geometry
    cover_page, toc_pages, section_page, paint_footer

Contact sheets (triage: many figures, one page)
    contact_sheet             — tile saved rasters N-up and write .pdf / .png
    image_grid_page           — one such page, as a Figure
    load_image                — read a raster (and explain why SVG will not do)

Reports (the document)
    pdf_report                — figures and sections -> one navigable PDF
    ReportSection             — a titled, nestable group
    PdfReportSpec             — the options as a value, for batch_plot(pdf_report=...)

Outline (optional)
    attach_outline, HAS_PYPDF — clickable bookmarks, needs pypdf
"""

from __future__ import annotations

from .assemble import (
    PdfReportSpec,
    ReportItem,
    ReportSection,
    pdf_report,
)
from .bookmarks import (
    HAS_PYPDF,
    attach_outline,
    count_pages,
)
from .pages import (
    PAGE_SIZES,
    TocEntry,
    cover_page,
    page_inches,
    paint_footer,
    section_page,
    toc_pages,
)
from .sheet import (
    contact_sheet,
    image_grid_page,
    load_image,
)

__all__ = [
    # Pages
    "PAGE_SIZES",
    "TocEntry",
    "cover_page",
    "page_inches",
    "paint_footer",
    "section_page",
    "toc_pages",
    # Contact sheets
    "contact_sheet",
    "image_grid_page",
    "load_image",
    # Reports
    "PdfReportSpec",
    "ReportItem",
    "ReportSection",
    "pdf_report",
    # Outline
    "HAS_PYPDF",
    "attach_outline",
    "count_pages",
]
