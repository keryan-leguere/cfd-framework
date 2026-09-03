"""Page geometry and the front-matter painters."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from cfd_plot.pdf.pages import (
    PAGE_SIZES,
    TocEntry,
    cover_page,
    page_inches,
    section_page,
    toc_entries_per_page,
    toc_pages,
)


class TestPageInches:
    def test_it_resolves_a_named_size(self):
        assert page_inches("a4") == PAGE_SIZES["a4"]

    def test_it_is_case_insensitive(self):
        assert page_inches("A4") == page_inches("a4")

    def test_landscape_swaps_the_dimensions(self):
        portrait = page_inches("a4")
        landscape = page_inches("a4", landscape=True)
        assert landscape == (portrait[1], portrait[0])
        assert landscape[0] > landscape[1]

    def test_landscape_is_idempotent(self):
        # Already-wide input must stay as it is, not flip back to portrait.
        once = page_inches("a4", landscape=True)
        assert page_inches(once, landscape=True) == once

    def test_it_accepts_an_explicit_size(self):
        assert page_inches((6.0, 4.0)) == (6.0, 4.0)

    def test_it_rejects_an_unknown_name(self):
        with pytest.raises(ValueError, match="Unknown page size"):
            page_inches("a9")

    @pytest.mark.parametrize("bad", [(1.0,), (0.0, 3.0), (-1.0, 2.0), (1.0, 2.0, 3.0)])
    def test_it_rejects_a_degenerate_size(self, bad):
        with pytest.raises(ValueError, match="two positive numbers"):
            page_inches(bad)


class TestFrontMatter:
    def test_cover_is_page_sized(self):
        page = page_inches("a4")
        fig = cover_page(page, title="Etude")
        assert tuple(fig.get_size_inches()) == pytest.approx(page)
        plt.close(fig)

    def test_cover_renders_every_summary_row(self):
        fig = cover_page(
            page_inches("a4"),
            title="Etude",
            subtitle="sub",
            summary=[("Figures", "12"), ("Polars", "3")],
        )
        drawn = {text.get_text() for text in fig.axes[0].texts}
        assert {"Etude", "sub", "Figures", "12", "Polars", "3"} <= drawn
        plt.close(fig)

    def test_section_page_carries_title_and_caption(self):
        fig = section_page(page_inches("a4"), title="ALPHA_POLAR", caption="M 0.8")
        drawn = {text.get_text() for text in fig.axes[0].texts}
        assert {"ALPHA_POLAR", "M 0.8"} <= drawn
        plt.close(fig)


class TestToc:
    def test_capacity_scales_with_the_page(self):
        # A5 is half of A4; it must not claim the same capacity.
        assert toc_entries_per_page(page_inches("a5")) < toc_entries_per_page(page_inches("a4"))
        assert toc_entries_per_page(page_inches("a3")) > toc_entries_per_page(page_inches("a4"))

    def test_a_short_toc_is_one_page(self):
        figs = toc_pages(page_inches("a4"), [TocEntry("x", 1)])
        assert len(figs) == 1
        for fig in figs:
            plt.close(fig)

    def test_it_paginates_a_long_toc(self):
        page = page_inches("a4")
        per_page = toc_entries_per_page(page)
        entries = [TocEntry(f"e{i}", i) for i in range(per_page * 2 + 1)]
        figs = toc_pages(page, entries)
        assert len(figs) == 3
        for fig in figs:
            plt.close(fig)

    def test_page_count_does_not_depend_on_the_numbers(self):
        # The two-pass numbering in pdf_report relies on this: the probe pass
        # counts pages from unnumbered entries and the real pass must agree.
        page = page_inches("a4")
        entries = [TocEntry(f"e{i}", 0) for i in range(60)]
        renumbered = [TocEntry(e.text, 9999, e.depth) for e in entries]
        first, second = toc_pages(page, entries), toc_pages(page, renumbered)
        assert len(first) == len(second)
        for fig in first + second:
            plt.close(fig)

    def test_an_empty_toc_still_paints_one_page(self):
        figs = toc_pages(page_inches("a4"), [])
        assert len(figs) == 1
        plt.close(figs[0])
