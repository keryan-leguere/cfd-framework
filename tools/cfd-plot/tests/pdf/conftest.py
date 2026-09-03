"""Shared fixtures for the PDF report tests.

``pypdf`` is an optional dependency (``cfd-plot[pdf]``): it is what gives the
report a clickable outline, and it is also the only way to *read a PDF back*.
Tests that need to count pages are therefore skipped without it, while the tests
that assert the library still works when it is absent run either way.
"""

from __future__ import annotations

import matplotlib
import pytest

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from cfd_plot import new_figure, plot_line

try:
    import pypdf

    HAS_PYPDF = True
except ImportError:  # pragma: no cover - depends on the environment
    pypdf = None
    HAS_PYPDF = False


needs_pypdf = pytest.mark.skipif(not HAS_PYPDF, reason="pypdf is not installed")


def page_count(path) -> int:
    """Number of pages in a PDF. Only call under ``needs_pypdf``."""
    assert pypdf is not None
    return len(pypdf.PdfReader(str(path)).pages)


def page_texts(path) -> list[str]:
    """Extracted text of every page, whitespace-normalised."""
    assert pypdf is not None
    return [" ".join(page.extract_text().split()) for page in pypdf.PdfReader(str(path)).pages]


def outline_entries(path) -> list[tuple[int, str, int]]:
    """``(depth, title, 1-based page)`` for every outline entry."""
    assert pypdf is not None
    reader = pypdf.PdfReader(str(path))

    def walk(items, depth=0):
        found = []
        for item in items:
            if isinstance(item, list):
                found.extend(walk(item, depth + 1))
            else:
                found.append((depth, item.title, reader.get_destination_page_number(item) + 1))
        return found

    return walk(reader.outline)


@pytest.fixture
def make_figure():
    """Factory for small labelled figures; every one is closed at teardown."""
    created = []

    def _make(label: str = "fig"):
        fig, ax = new_figure()
        plot_line(ax, [0, 1, 2, 3], [0, 1, 4, 9], label=label)
        fig.set_label(label)
        created.append(fig)
        return fig

    yield _make
    for fig in created:
        plt.close(fig)


@pytest.fixture
def png_files(tmp_path, make_figure):
    """Three PNG figures on disk, for the raster paths."""
    from cfd_plot import save_figure

    paths = []
    for index in range(3):
        fig = make_figure(f"src_{index}")
        paths.extend(save_figure(fig, tmp_path / f"src_{index}", formats=("png",)))
    return paths
