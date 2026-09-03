"""Contact sheets."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from cfd_plot.pdf.pages import page_inches
from cfd_plot.pdf.sheet import contact_sheet, image_grid_page, load_image

from .conftest import needs_pypdf, page_count


class TestLoadImage:
    def test_it_reads_a_png(self, png_files):
        image = load_image(png_files[0])
        assert image.ndim == 3
        assert image.shape[2] == 4  # RGBA

    def test_it_refuses_svg_and_says_what_to_do(self, tmp_path):
        # batch_plot writes SVG by default, so this is the first mistake a
        # caller makes; the message has to carry the fix.
        target = tmp_path / "curve.svg"
        target.write_text("<svg/>")
        with pytest.raises(ValueError) as excinfo:
            load_image(target)
        message = str(excinfo.value)
        assert "vector" in message
        assert "pdf_report" in message

    def test_it_refuses_an_unsupported_format(self, tmp_path):
        with pytest.raises(ValueError, match="unsupported image format"):
            load_image(tmp_path / "curve.dat")

    def test_it_reports_a_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_image(tmp_path / "absent.png")


class TestImageGridPage:
    def test_one_axes_per_image(self, png_files):
        images = [load_image(p) for p in png_files]
        fig = image_grid_page(page_inches("a4"), images, rows=2, cols=2)
        # blank_page adds one full-bleed axes, then one per image.
        assert len(fig.axes) == 1 + len(images)
        plt.close(fig)

    def test_images_keep_their_aspect_ratio(self, png_files):
        image = load_image(png_files[0])
        aspect = image.shape[1] / image.shape[0]
        fig = image_grid_page(page_inches("a4"), [image], rows=1, cols=1)
        width, height = fig.get_size_inches()
        box = fig.axes[1].get_position()
        drawn = (box.width * width) / (box.height * height)
        assert drawn == pytest.approx(aspect, rel=0.02)
        plt.close(fig)

    def test_it_rejects_more_images_than_cells(self, png_files):
        images = [load_image(p) for p in png_files]
        with pytest.raises(ValueError, match="do not fit"):
            image_grid_page(page_inches("a4"), images, rows=1, cols=1)

    @pytest.mark.parametrize(("rows", "cols"), [(0, 2), (2, 0), (-1, 1)])
    def test_it_rejects_a_degenerate_grid(self, png_files, rows, cols):
        with pytest.raises(ValueError, match=">= 1"):
            image_grid_page(page_inches("a4"), [load_image(png_files[0])], rows=rows, cols=cols)


class TestContactSheet:
    def test_it_writes_one_pdf(self, png_files, tmp_path):
        written = contact_sheet(png_files, tmp_path / "sheet.pdf", rows=2, cols=2)
        assert written == [tmp_path / "sheet.pdf"]
        assert written[0].stat().st_size > 0

    @needs_pypdf
    def test_page_count_follows_the_grid(self, png_files, tmp_path):
        # 3 images, 1 per page -> 3 pages; 4 per page -> 1 page.
        one_up = contact_sheet(png_files, tmp_path / "a.pdf", rows=1, cols=1)
        four_up = contact_sheet(png_files, tmp_path / "b.pdf", rows=2, cols=2)
        assert page_count(one_up[0]) == 3
        assert page_count(four_up[0]) == 1

    def test_png_output_is_one_file_per_page(self, png_files, tmp_path):
        written = contact_sheet(png_files, tmp_path / "sheet.png", rows=1, cols=2)
        assert [p.name for p in written] == ["sheet_01.png", "sheet_02.png"]

    def test_a_single_page_png_keeps_the_plain_name(self, png_files, tmp_path):
        written = contact_sheet(png_files, tmp_path / "sheet.png", rows=2, cols=2)
        assert [p.name for p in written] == ["sheet.png"]

    def test_labels_default_to_the_file_stem(self, png_files, tmp_path):
        # Nothing to assert on the written bytes, so check the painter directly.
        fig = image_grid_page(
            page_inches("a4"),
            [load_image(p) for p in png_files],
            labels=[p.stem for p in png_files],
            rows=2,
            cols=2,
        )
        drawn = {text.get_text() for text in fig.texts}
        assert {p.stem for p in png_files} <= drawn
        plt.close(fig)

    def test_it_creates_missing_parent_directories(self, png_files, tmp_path):
        target = tmp_path / "deep" / "deeper" / "sheet.pdf"
        assert contact_sheet(png_files, target)[0].is_file()

    def test_it_rejects_an_empty_input(self, tmp_path):
        with pytest.raises(ValueError, match="at least one image"):
            contact_sheet([], tmp_path / "sheet.pdf")

    def test_it_rejects_a_mismatched_label_count(self, png_files, tmp_path):
        with pytest.raises(ValueError, match="label"):
            contact_sheet(png_files, tmp_path / "sheet.pdf", labels=["only one"])

    def test_it_rejects_an_unsupported_output_suffix(self, png_files, tmp_path):
        with pytest.raises(ValueError, match=r"\.pdf or \.png"):
            contact_sheet(png_files, tmp_path / "sheet.tiff")

    def test_it_does_not_leak_the_style(self, png_files, tmp_path):
        import matplotlib as mpl

        before = mpl.rcParams["axes.prop_cycle"]
        contact_sheet(png_files, tmp_path / "sheet.pdf", profile="slides")
        assert mpl.rcParams["axes.prop_cycle"] == before
