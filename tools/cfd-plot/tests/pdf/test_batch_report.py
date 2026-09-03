"""``batch_plot(pdf_report=...)`` — the report built during the run."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from cfd_plot import PdfReportSpec, batch_compare_flight_points, batch_plot
from cfd_plot.batch import _report_entries, _study_title

from .conftest import needs_pypdf, outline_entries, page_count, page_texts


def _row(mach, alt, alpha, cn, scheme):
    return {
        "Mach": mach,
        "Altitude_m": alt,
        "alpha": alpha,
        "beta": 0.0,
        "DL": 0.0,
        "DM": 0.0,
        "DN": 0.0,
        "CN": cn,
        "scheme": scheme,
    }


@pytest.fixture
def config():
    rows_kw = [_row(m, 8000, a, 0.1 + 0.01 * a, "KW") for m in (0.8, 0.85) for a in (0.0, 2.0, 4.0)]
    rows_sa = [_row(m, 8000, a, 0.12 + 0.01 * a, "SA") for m in (0.8, 0.85) for a in (0.0, 2.0, 4.0)]
    return {
        "KW": {"name": "KW", "label": "KW", "dir": "", "CDG": [0, 0, 0], "df": pd.DataFrame(rows_kw)},
        "SA": {"name": "SA", "label": "SA", "dir": "", "CDG": [0, 0, 0], "df": pd.DataFrame(rows_sa)},
    }


_Y = {"CN": {"col_name": "CN", "literal_name": "Normal force", "symbol": r"$C_N$", "unit": "-", "y_save_name": "CN"}}
_SWEEP = {
    "alpha": {
        "col_name": "alpha",
        "literal_name": "Angle of attack",
        "symbol": r"$\alpha$",
        "unit": "deg",
        "x_save_name": "alpha",
        "polar_prefix": "ALPHA_POLAR",
    }
}
_FP = {
    "Mach": {"values": [], "label": "M", "save_name": "M"},
    "Altitude_m": {"values": [], "label": "H", "save_name": "H"},
    "beta": {"values": [], "label": "beta", "save_name": "BETA"},
    "DL": {"values": [], "label": "DL", "save_name": "DL"},
    "DM": {"values": [], "label": "DM", "save_name": "DM"},
    "DN": {"values": [], "label": "DN", "save_name": "DN"},
}


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


def _run(config, tmp_path, **kwargs):
    return batch_plot(
        configuration_dict=config,
        y_axis_dict=_Y,
        sweep_dict=_SWEEP,
        flight_point_dict=_FP,
        output_base=tmp_path,
        report=False,
        **kwargs,
    )


class TestHelpers:
    def test_report_entries_group_polar_then_flight_point(self, config, tmp_path):
        from cfd_plot.batch import _enumerate_jobs, _prepare_flight_point_dict, _prepare_sweep_dict

        sweeps = _prepare_sweep_dict(config, _SWEEP)
        points = _prepare_flight_point_dict(config, _FP, ["alpha"])
        jobs = _enumerate_jobs(
            configuration_dict=config,
            y_axis_dict=_Y,
            completed_sweeps=sweeps,
            completed_flight_points=points,
            output_base=tmp_path,
            include_curve=None,
        )
        entries = _report_entries(jobs)
        assert len(entries) == len(jobs)
        assert all(trail[0] == "ALPHA_POLAR" for trail, _ in entries)
        # LaTeX is stripped: a table of contents is plain text.
        assert not any("$" in label for _, label in entries)
        assert not any("$" in part for trail, _ in entries for part in trail)

    def test_study_title_lists_the_polars(self):
        class Job:
            def __init__(self, prefix):
                self.polar_prefix = prefix

        assert _study_title([Job("A"), Job("B"), Job("A")]) == "A, B"
        assert _study_title([Job(f"P{i}") for i in range(5)]) == "5 polars"
        assert _study_title([]) == "Figures"


class TestBatchPdfReport:
    def test_it_writes_the_pdf_and_returns_its_path(self, config, tmp_path):
        target = tmp_path / "ETUDE.pdf"
        written = _run(config, tmp_path, formats=("svg",), pdf_report=target)
        assert target.is_file()
        assert target in written

    @needs_pypdf
    def test_page_count_is_front_matter_plus_dividers_plus_figures(self, config, tmp_path):
        target = tmp_path / "ETUDE.pdf"
        written = _run(config, tmp_path, formats=("svg",), pdf_report=target)
        svgs = [p for p in written if p.suffix == ".svg"]
        # cover + toc + one divider (a single polar) + one page per figure
        assert page_count(target) == 1 + 1 + 1 + len(svgs)

    @needs_pypdf
    def test_formats_empty_makes_the_report_the_only_output(self, config, tmp_path):
        target = tmp_path / "ETUDE.pdf"
        written = _run(config, tmp_path, formats=(), pdf_report=target)
        assert written == [target]
        assert list(tmp_path.rglob("*.svg")) == []
        assert page_count(target) > 3

    @needs_pypdf
    def test_the_outline_follows_the_polars(self, config, tmp_path):
        target = tmp_path / "ETUDE.pdf"
        _run(config, tmp_path, formats=(), pdf_report=target)
        assert [title for _, title, _ in outline_entries(target)] == ["ALPHA_POLAR"]

    @needs_pypdf
    def test_the_cover_reports_the_run(self, config, tmp_path):
        target = tmp_path / "ETUDE.pdf"
        written = _run(config, tmp_path, formats=("svg",), pdf_report=target)
        svgs = [p for p in written if p.suffix == ".svg"]
        cover = page_texts(target)[0]
        assert "ALPHA_POLAR" in cover
        assert str(len(svgs)) in cover
        assert "KW" in cover and "SA" in cover

    @needs_pypdf
    def test_the_toc_pages_match_the_document(self, config, tmp_path):
        target = tmp_path / "ETUDE.pdf"
        _run(config, tmp_path, formats=(), pdf_report=target)
        texts = page_texts(target)
        # The divider named in the TOC must really be on the page it claims.
        assert "ALPHA_POLAR 3" in texts[1]
        assert texts[2].startswith("ALPHA_POLAR")

    def test_a_spec_overrides_the_defaults(self, config, tmp_path):
        target = tmp_path / "ETUDE.pdf"
        _run(
            config,
            tmp_path,
            formats=(),
            pdf_report=PdfReportSpec(path=target, title="Custom title", toc=False, bookmarks=False),
        )
        assert target.is_file()

    @needs_pypdf
    def test_a_spec_without_a_toc_is_shorter(self, config, tmp_path):
        with_toc = tmp_path / "a.pdf"
        without = tmp_path / "b.pdf"
        _run(config, tmp_path / "a", formats=(), pdf_report=PdfReportSpec(path=with_toc, title="T"))
        _run(config, tmp_path / "b", formats=(), pdf_report=PdfReportSpec(path=without, title="T", toc=False))
        assert page_count(with_toc) == page_count(without) + 1

    def test_parallel_falls_back_to_sequential_with_a_warning(self, config, tmp_path):
        target = tmp_path / "ETUDE.pdf"
        with pytest.warns(UserWarning, match="sequential"):
            _run(config, tmp_path, formats=(), pdf_report=target, n_jobs=2)
        # The point of the fallback: it still produces the report.
        assert target.is_file()

    def test_no_pdf_is_written_without_the_argument(self, config, tmp_path):
        _run(config, tmp_path, formats=("svg",))
        assert list(tmp_path.rglob("*.pdf")) == []

    def test_a_dry_run_writes_nothing(self, config, tmp_path):
        target = tmp_path / "ETUDE.pdf"
        _run(config, tmp_path, formats=("svg",), pdf_report=target, dry_run=True)
        assert not target.exists()

    @needs_pypdf
    def test_every_page_is_the_same_size(self, config, tmp_path):
        # batch_plot calls use_style() once per job, which re-applies the style
        # sheet — and with it savefig.bbox=tight. An rc override taken once
        # around the document gets clobbered by that on the second figure, and
        # the pages come out at three different sizes. Caught in a real 202-page
        # run, not by the small fixtures above.
        import pypdf

        target = tmp_path / "ETUDE.pdf"
        _run(config, tmp_path, formats=(), pdf_report=target)
        pages = pypdf.PdfReader(str(target)).pages
        sizes = {(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in pages}
        assert len(sizes) == 1, f"pages came out at {len(sizes)} different sizes: {sizes}"

    def test_it_does_not_leak_the_style(self, config, tmp_path):
        import matplotlib as mpl

        before = mpl.rcParams["savefig.bbox"]
        _run(config, tmp_path, formats=(), pdf_report=tmp_path / "r.pdf")
        # page_rc() turns the profiles' tight bbox off; it must go back on.
        assert mpl.rcParams["savefig.bbox"] == before


class TestCompareReport:
    @needs_pypdf
    def test_compare_figures_go_into_a_report(self, config, tmp_path):
        target = tmp_path / "COMPARE.pdf"
        written = batch_compare_flight_points(
            configuration_dict=config,
            y_axis_dict=_Y,
            sweep_dict=_SWEEP,
            flight_point_dict=_FP,
            compare_flight_points={
                "design": {"Mach": 0.8, "Altitude_m": 8000, "beta": 0.0, "DL": 0.0, "DM": 0.0, "DN": 0.0},
                "off": {"Mach": 0.85, "Altitude_m": 8000, "beta": 0.0, "DL": 0.0, "DM": 0.0, "DN": 0.0},
            },
            output_base=tmp_path,
            formats=(),
            report=False,
            pdf_report=target,
        )
        assert written == [target]
        assert page_count(target) >= 3
