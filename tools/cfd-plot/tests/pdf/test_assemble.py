"""Report assembly: page plan, two-pass numbering, streaming."""

from __future__ import annotations

import matplotlib as mpl
import matplotlib.pyplot as plt
import pytest

from cfd_plot.pdf import PdfReportSpec, ReportSection, pdf_report
from cfd_plot.pdf.assemble import ReportBuilder, _tree_from_trails

from .conftest import needs_pypdf, outline_entries, page_count, page_texts


class TestTreeFromTrails:
    def test_it_nests_by_trail(self):
        tree = _tree_from_trails([(("A", "M1"), "f1"), (("A", "M1"), "f2"), (("A", "M2"), "f3")])
        assert len(tree) == 1
        top = tree[0]
        assert isinstance(top, ReportSection)
        assert top.title == "A"
        assert [section.title for section in top.items] == ["M1", "M2"]
        assert [leaf.label for leaf in top.items[0].items] == ["f1", "f2"]

    def test_an_empty_trail_stays_flat(self):
        tree = _tree_from_trails([((), "a"), ((), "b")])
        assert [leaf.label for leaf in tree] == ["a", "b"]

    def test_a_repeated_trail_makes_a_second_section(self):
        # Order is the document's order. Merging non-adjacent runs would
        # silently reorder the report relative to the caller's job list.
        tree = _tree_from_trails([(("A",), "f1"), (("B",), "f2"), (("A",), "f3")])
        assert [section.title for section in tree] == ["A", "B", "A"]


class TestPdfReport:
    def test_it_writes_a_file(self, make_figure, tmp_path):
        out = pdf_report([make_figure("a")], tmp_path / "r.pdf", title="T")
        assert out.is_file() and out.stat().st_size > 0

    @needs_pypdf
    def test_page_count_is_cover_plus_toc_plus_figures(self, make_figure, tmp_path):
        figures = [make_figure(f"f{i}") for i in range(3)]
        out = pdf_report(figures, tmp_path / "r.pdf", title="T")
        assert page_count(out) == 1 + 1 + 3

    @needs_pypdf
    def test_without_a_title_there_is_no_cover(self, make_figure, tmp_path):
        out = pdf_report([make_figure("a")], tmp_path / "r.pdf", toc=False)
        assert page_count(out) == 1

    @needs_pypdf
    def test_sections_add_one_divider_each(self, make_figure, tmp_path):
        sections = [ReportSection(f"S{i}", [make_figure(f"f{i}")]) for i in range(2)]
        out = pdf_report(sections, tmp_path / "r.pdf", title="T")
        assert page_count(out) == 1 + 1 + 2 + 2

    @needs_pypdf
    def test_toc_page_numbers_point_at_the_right_pages(self, make_figure, tmp_path):
        sections = [ReportSection(f"S{i}", [make_figure(f"f{i}{k}") for k in range(2)]) for i in range(2)]
        out = pdf_report(sections, tmp_path / "r.pdf", title="T")
        texts = page_texts(out)

        # Layout: 1 cover, 2 toc, 3 divider S0, 4-5 figures, 6 divider S1, 7-8 figures.
        assert "S0 3" in texts[1]
        assert "S1 6" in texts[1]
        assert texts[2].startswith("S0")
        assert texts[5].startswith("S1")

    @needs_pypdf
    def test_a_nested_section_without_a_divider_points_at_its_first_figure(self, make_figure, tmp_path):
        tree = [ReportSection("P", [ReportSection("M1", [make_figure("a")]), ReportSection("M2", [make_figure("b")])])]
        out = pdf_report(tree, tmp_path / "r.pdf", title="T", toc_depth=2)
        # 1 cover, 2 toc, 3 divider P, 4 figure a, 5 figure b.
        toc = page_texts(out)[1]
        assert "P 3" in toc and "M1 4" in toc and "M2 5" in toc

    @needs_pypdf
    def test_n_up_groups_figures_onto_one_page(self, make_figure, tmp_path):
        figures = [make_figure(f"f{i}") for i in range(7)]
        out = pdf_report(figures, tmp_path / "r.pdf", title="T", n_up=(2, 2))
        assert page_count(out) == 1 + 1 + 2  # 7 figures, 4 per page -> 2 pages

    @needs_pypdf
    def test_it_accepts_image_paths(self, png_files, tmp_path):
        out = pdf_report(png_files, tmp_path / "r.pdf", title="T")
        assert page_count(out) == 1 + 1 + 3

    @needs_pypdf
    def test_it_accepts_figures_and_paths_together(self, make_figure, png_files, tmp_path):
        out = pdf_report([make_figure("a"), *png_files], tmp_path / "r.pdf", title="T")
        assert page_count(out) == 1 + 1 + 4

    @needs_pypdf
    def test_it_attaches_an_outline(self, make_figure, tmp_path):
        sections = [ReportSection(f"S{i}", [make_figure(f"f{i}")]) for i in range(2)]
        out = pdf_report(sections, tmp_path / "r.pdf", title="T")
        assert outline_entries(out) == [(0, "S0", 3), (0, "S1", 5)]

    @needs_pypdf
    def test_metadata_survives_the_outline_pass(self, make_figure, tmp_path):
        # Attaching the outline rewrites the file through pypdf, and
        # append_pages_from_reader copies pages only. Without an explicit
        # hand-over the Title/Author written by PdfPages are replaced by a bare
        # "/Producer: pypdf", so the metadata= argument would do nothing for
        # anyone who has pypdf installed — the usual case.
        import pypdf

        sections = [ReportSection("S", [make_figure("a")])]
        out = pdf_report(sections, tmp_path / "r.pdf", title="Mach sweep", metadata={"Author": "Someone"})
        meta = dict(pypdf.PdfReader(str(out)).metadata or {})
        assert meta.get("/Title") == "Mach sweep"
        assert meta.get("/Author") == "Someone"
        # …and the outline it was rewritten for is still there.
        assert [item.title for item in pypdf.PdfReader(str(out)).outline] == ["S"]

    def test_the_callers_figure_survives_untouched(self, make_figure, tmp_path):
        fig = make_figure("a")
        size = tuple(fig.get_size_inches())
        texts = len(fig.texts)
        pdf_report([fig], tmp_path / "r.pdf", title="T")
        # A report must not be a side effect that reshapes or annotates the
        # figures it was handed.
        assert tuple(fig.get_size_inches()) == size
        assert len(fig.texts) == texts
        assert plt.fignum_exists(fig.number)

    def test_it_does_not_leak_the_style(self, make_figure, tmp_path):
        before = mpl.rcParams["axes.prop_cycle"]
        pdf_report([make_figure("a")], tmp_path / "r.pdf", title="T", profile="slides")
        assert mpl.rcParams["axes.prop_cycle"] == before

    def test_it_creates_missing_parent_directories(self, make_figure, tmp_path):
        out = pdf_report([make_figure("a")], tmp_path / "deep" / "r.pdf", title="T")
        assert out.is_file()

    def test_it_rejects_an_empty_report(self, tmp_path):
        with pytest.raises(ValueError, match="at least one item"):
            pdf_report([], tmp_path / "r.pdf")

    @pytest.mark.parametrize("bad", [(0, 2), (2, 0), (1,)])
    def test_it_rejects_a_degenerate_n_up(self, make_figure, tmp_path, bad):
        with pytest.raises(ValueError, match="n_up"):
            pdf_report([make_figure("a")], tmp_path / "r.pdf", n_up=bad)

    @needs_pypdf
    def test_page_size_none_keeps_each_figure_size(self, make_figure, tmp_path):
        import pypdf

        fig = make_figure("a")
        fig.set_size_inches(5.0, 3.0)
        out = pdf_report([fig], tmp_path / "r.pdf", page_size=None, toc=False)
        box = pypdf.PdfReader(str(out)).pages[0].mediabox
        assert float(box.width) / 72 == pytest.approx(5.0, abs=0.05)

    @needs_pypdf
    def test_every_page_is_the_same_size_by_default(self, make_figure, tmp_path):
        import pypdf

        figures = [make_figure(f"f{i}") for i in range(3)]
        figures[1].set_size_inches(4.0, 9.0)  # deliberately the odd one out
        out = pdf_report(figures, tmp_path / "r.pdf", title="T")
        sizes = {
            (round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in pypdf.PdfReader(str(out)).pages
        }
        assert len(sizes) == 1


class TestReportBuilder:
    def _entries(self, n=4):
        return [(("P", f"M{i // 2}"), f"f{i}") for i in range(n)]

    @needs_pypdf
    def test_planned_total_matches_what_is_written(self, make_figure, tmp_path):
        entries = self._entries()
        builder = ReportBuilder(PdfReportSpec(path=tmp_path / "r.pdf", title="T"), entries)
        planned = builder.total_pages
        with builder:
            for _ in entries:
                builder.add(make_figure("x"))
        assert page_count(tmp_path / "r.pdf") == planned

    @needs_pypdf
    def test_it_streams_without_holding_figures(self, tmp_path, make_figure):
        # Each figure is closed the moment it has been added; the report must
        # still come out whole. This is the property batch_plot relies on.
        entries = self._entries(6)
        spec = PdfReportSpec(path=tmp_path / "r.pdf", title="T")
        with ReportBuilder(spec, entries) as builder:
            for _ in entries:
                fig = make_figure("x")
                builder.add(fig)
                plt.close(fig)
        assert page_count(tmp_path / "r.pdf") == 1 + 1 + 1 + 6  # cover, toc, divider P, figures

    def test_it_rejects_more_figures_than_declared(self, make_figure, tmp_path):
        entries = self._entries(1)
        with (
            pytest.raises(ValueError, match="More figures added"),
            ReportBuilder(PdfReportSpec(path=tmp_path / "r.pdf"), entries) as builder,
        ):
            builder.add(make_figure("a"))
            builder.add(make_figure("b"))

    def test_it_rejects_an_empty_plan(self, tmp_path):
        with pytest.raises(ValueError, match="at least one entry"):
            ReportBuilder(PdfReportSpec(path=tmp_path / "r.pdf"), [])

    def test_add_outside_the_context_is_an_error(self, make_figure, tmp_path):
        builder = ReportBuilder(PdfReportSpec(path=tmp_path / "r.pdf"), self._entries(1))
        with pytest.raises(RuntimeError, match="outside the context"):
            builder.add(make_figure("a"))

    @needs_pypdf
    def test_a_short_run_still_produces_a_readable_pdf(self, make_figure, tmp_path):
        # Fewer figures than declared (a run that stopped early) must not emit
        # blank pages or corrupt the file.
        entries = self._entries(4)
        spec = PdfReportSpec(path=tmp_path / "r.pdf", title="T")
        with ReportBuilder(spec, entries) as builder:
            builder.add(make_figure("a"))
        assert page_count(tmp_path / "r.pdf") == 1 + 1 + 1 + 1

    def test_it_does_not_leak_the_style(self, make_figure, tmp_path):
        before = mpl.rcParams["axes.prop_cycle"]
        entries = self._entries(1)
        with ReportBuilder(PdfReportSpec(path=tmp_path / "r.pdf", profile="slides"), entries) as builder:
            builder.add(make_figure("a"))
        assert mpl.rcParams["axes.prop_cycle"] == before


class TestWithoutPypdf:
    def test_the_report_is_written_anyway(self, make_figure, tmp_path, monkeypatch):
        # The outline is a convenience; losing pypdf must cost the outline and
        # nothing else.
        import cfd_plot.pdf.bookmarks as bookmarks

        monkeypatch.setattr(bookmarks, "HAS_PYPDF", False)
        monkeypatch.setattr(bookmarks, "_WARNED", False)
        sections = [ReportSection("S", [make_figure("a")])]
        out = pdf_report(sections, tmp_path / "r.pdf", title="T")
        assert out.is_file() and out.stat().st_size > 0

    def test_attach_outline_reports_failure_rather_than_raising(self, tmp_path, monkeypatch):
        import cfd_plot.pdf.bookmarks as bookmarks

        monkeypatch.setattr(bookmarks, "HAS_PYPDF", False)
        assert bookmarks.attach_outline(tmp_path / "absent.pdf", [("S", 0, 0)]) is False

    def test_attach_outline_survives_a_broken_file(self, tmp_path):
        import cfd_plot.pdf.bookmarks as bookmarks

        if not bookmarks.HAS_PYPDF:
            pytest.skip("pypdf is not installed")
        broken = tmp_path / "broken.pdf"
        broken.write_text("not a pdf")
        assert bookmarks.attach_outline(broken, [("S", 0, 0)]) is False
        assert broken.read_text() == "not a pdf"  # left intact
