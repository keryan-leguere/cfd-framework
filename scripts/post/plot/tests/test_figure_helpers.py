"""Tests for figure-level legend and shared colorbar helpers."""

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from plotting import (
    add_shared_colorbar,
    make_figure_legend,
    plot_contourf,
    plot_line,
    sync_axes_limits,
    use_style,
)


@pytest.fixture(autouse=True)
def _use_notebook_style():
    use_style("notebook")
    yield
    plt.close("all")


@pytest.fixture()
def twin_line_fig():
    """Two subplots sharing overlapping line labels."""
    x = np.linspace(0, 6, 30)
    fig, (ax1, ax2) = plt.subplots(1, 2)
    plot_line(ax1, x, np.sin(x), label="sin")
    plot_line(ax1, x, np.cos(x), marker="s", label="cos")
    plot_line(ax2, x, np.sin(x), label="sin")
    plot_line(ax2, x, -np.sin(x), marker="^", label="-sin")
    return fig, (ax1, ax2)


@pytest.fixture()
def twin_contour_fig():
    """Two filled-contour subplots without per-axes colorbars."""
    x = np.linspace(-1, 1, 41)
    y = np.linspace(-1, 1, 31)
    X, Y = np.meshgrid(x, y, indexing="xy")
    Z = np.exp(-(X**2 + Y**2))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    cf1, _ = plot_contourf(ax1, x, y, Z, levels=15, colorbar=False)
    cf2, _ = plot_contourf(ax2, x, y, Z * 0.5, levels=15, colorbar=False)
    return fig, (ax1, ax2), cf1


# -----------------------------------------------------------------------
# make_figure_legend
# -----------------------------------------------------------------------
class TestMakeFigureLegend:
    def test_returns_legend(self, twin_line_fig):
        fig, _ = twin_line_fig
        leg = make_figure_legend(fig)
        assert leg is not None

    def test_deduplicates_labels(self, twin_line_fig):
        fig, _ = twin_line_fig
        leg = make_figure_legend(fig, dedupe=True)
        texts = [t.get_text() for t in leg.get_texts()]
        assert texts == ["sin", "cos", "-sin"]

    def test_no_dedupe(self, twin_line_fig):
        fig, _ = twin_line_fig
        leg = make_figure_legend(fig, dedupe=False)
        texts = [t.get_text() for t in leg.get_texts()]
        assert texts.count("sin") == 2

    def test_subset_axes(self, twin_line_fig):
        fig, (ax1, _) = twin_line_fig
        leg = make_figure_legend(fig, axes=[ax1])
        texts = [t.get_text() for t in leg.get_texts()]
        assert "sin" in texts
        assert "-sin" not in texts

    def test_single_ax(self, twin_line_fig):
        fig, (ax1, _) = twin_line_fig
        leg = make_figure_legend(fig, axes=ax1)
        assert len(leg.get_texts()) > 0

    def test_frame_linewidth(self, twin_line_fig):
        fig, _ = twin_line_fig
        leg = make_figure_legend(fig, frame_linewidth=3.0)
        assert leg.get_frame().get_linewidth() == 3.0

    def test_custom_kwargs(self, twin_line_fig):
        fig, _ = twin_line_fig
        leg = make_figure_legend(
            fig, loc="lower center", bbox_to_anchor=(0.5, -0.05), ncol=3,
        )
        assert leg is not None


# -----------------------------------------------------------------------
# add_shared_colorbar
# -----------------------------------------------------------------------
class TestAddSharedColorbar:
    def test_returns_colorbar_right(self, twin_contour_fig):
        fig, (ax1, ax2), cf = twin_contour_fig
        fig.set_layout_engine("none")
        cbar = add_shared_colorbar(
            fig, cf, axes=[ax1, ax2], label="p [Pa]",
        )
        assert cbar is not None
        assert cbar.ax is not None

    def test_returns_colorbar_bottom(self, twin_contour_fig):
        fig, (ax1, ax2), cf = twin_contour_fig
        fig.set_layout_engine("none")
        fig.subplots_adjust(bottom=0.25)
        cbar = add_shared_colorbar(
            fig, cf, axes=[ax1, ax2], location="bottom", label="T [K]",
        )
        assert cbar is not None

    def test_invalid_location(self, twin_contour_fig):
        fig, (ax1, ax2), cf = twin_contour_fig
        with pytest.raises(ValueError, match="location=.*not supported"):
            add_shared_colorbar(fig, cf, axes=[ax1, ax2], location="top")

    def test_single_axes(self, twin_contour_fig):
        fig, (ax1, _), cf = twin_contour_fig
        fig.set_layout_engine("none")
        cbar = add_shared_colorbar(fig, cf, axes=ax1, label="single")
        assert cbar is not None

    def test_default_axes_all(self, twin_contour_fig):
        fig, _, cf = twin_contour_fig
        fig.set_layout_engine("none")
        cbar = add_shared_colorbar(fig, cf)
        assert cbar is not None

    def test_match_axes_false(self, twin_contour_fig):
        fig, (ax1, ax2), cf = twin_contour_fig
        cbar = add_shared_colorbar(
            fig, cf, axes=[ax1, ax2], match_axes=False, label="no match",
        )
        assert cbar is not None

    def test_colorbar_tight_to_axes(self, twin_contour_fig):
        """Colorbar should sit close to the rightmost axis."""
        fig, (ax1, ax2), cf = twin_contour_fig
        fig.set_layout_engine("none")
        fig.subplots_adjust(right=0.90)
        cbar = add_shared_colorbar(
            fig, cf, axes=[ax1, ax2], label="tight",
        )
        axes_right = max(
            ax.get_position().x1 for ax in [ax1, ax2]
        )
        cbar_left = cbar.ax.get_position().x0
        gap = cbar_left - axes_right
        assert 0 < gap <= 0.05, f"gap={gap:.4f} is too large"

    def test_colorbar_height_spans_axes(self, twin_contour_fig):
        """Colorbar axis should span the full height of the subplot group."""
        fig, (ax1, ax2), cf = twin_contour_fig
        fig.set_layout_engine("none")
        cbar = add_shared_colorbar(
            fig, cf, axes=[ax1, ax2], label="span",
        )
        axes_y0 = min(ax.get_position().y0 for ax in [ax1, ax2])
        axes_y1 = max(ax.get_position().y1 for ax in [ax1, ax2])
        cbar_pos = cbar.ax.get_position()
        assert abs(cbar_pos.y0 - axes_y0) < 1e-6
        assert abs(cbar_pos.y1 - axes_y1) < 1e-6

    def test_colorbar_narrow_width(self, twin_contour_fig):
        """Default colorbar width should be slim (2% of figure)."""
        fig, (ax1, ax2), cf = twin_contour_fig
        fig.set_layout_engine("none")
        cbar = add_shared_colorbar(
            fig, cf, axes=[ax1, ax2], label="narrow",
        )
        cbar_width = cbar.ax.get_position().width
        assert cbar_width < 0.04, f"cbar width={cbar_width:.4f} is too wide"


# -----------------------------------------------------------------------
# sync_axes_limits
# -----------------------------------------------------------------------
class TestSyncAxesLimits:
    def test_matches_y_limits_to_global_range(self, twin_line_fig):
        fig, (ax1, ax2) = twin_line_fig
        sync_axes_limits((ax1, ax2), which="y")
        assert ax1.get_ylim() == ax2.get_ylim()
        lo, hi = ax1.get_ylim()
        # ax2 has -sin(x) which reaches lower than anything on ax1/ax2's sin/cos
        assert lo <= -0.99
        assert hi >= 0.99

    def test_matches_x_limits(self, twin_line_fig):
        fig, (ax1, ax2) = twin_line_fig
        ax1.set_xlim(0, 3)
        ax2.set_xlim(0, 6)
        sync_axes_limits((ax1, ax2), which="x")
        assert ax1.get_xlim() == ax2.get_xlim()

    def test_both_syncs_x_and_y(self, twin_line_fig):
        fig, (ax1, ax2) = twin_line_fig
        sync_axes_limits((ax1, ax2), which="both")
        assert ax1.get_xlim() == ax2.get_xlim()
        assert ax1.get_ylim() == ax2.get_ylim()

    def test_accepts_axes_array_from_subplots(self):
        x = np.linspace(0, 6, 30)
        fig, axes = plt.subplots(1, 2)
        plot_line(axes[0], x, np.sin(x) * 2, label="big")
        plot_line(axes[1], x, np.sin(x) * 0.5, label="small")
        sync_axes_limits(axes, which="y")
        assert axes[0].get_ylim() == axes[1].get_ylim()

    def test_ignores_reference_lines(self, twin_line_fig):
        """axhline/axvline use a blended transform and shouldn't skew bounds."""
        fig, (ax1, ax2) = twin_line_fig
        ax1.axhline(50.0, color="0.5")
        sync_axes_limits((ax1, ax2), which="y")
        lo, hi = ax1.get_ylim()
        assert hi < 50.0

    def test_invalid_which_raises(self, twin_line_fig):
        fig, (ax1, ax2) = twin_line_fig
        with pytest.raises(ValueError):
            sync_axes_limits((ax1, ax2), which="z")

    @staticmethod
    def _raw_y_bounds():
        """Global (unpadded) y min/max across the twin_line_fig curves."""
        x = np.linspace(0, 6, 30)
        values = np.concatenate([np.sin(x), np.cos(x), -np.sin(x)])
        return float(values.min()), float(values.max())

    def test_default_margin_matches_rcparam(self, twin_line_fig):
        """Bounds should breathe like a normal autoscaled axis, not sit flush on the data."""
        fig, (ax1, ax2) = twin_line_fig
        sync_axes_limits((ax1, ax2), which="y")
        lo, hi = ax1.get_ylim()
        raw_lo, raw_hi = self._raw_y_bounds()
        margin = plt.rcParams["axes.ymargin"]
        expected_pad = (raw_hi - raw_lo) * margin
        assert lo == pytest.approx(raw_lo - expected_pad, abs=1e-6)
        assert hi == pytest.approx(raw_hi + expected_pad, abs=1e-6)

    def test_custom_margin_overrides_default(self, twin_line_fig):
        fig, (ax1, ax2) = twin_line_fig
        sync_axes_limits((ax1, ax2), which="y", margin=0.5)
        lo, hi = ax1.get_ylim()
        raw_lo, raw_hi = self._raw_y_bounds()
        expected_pad = (raw_hi - raw_lo) * 0.5
        assert lo == pytest.approx(raw_lo - expected_pad, abs=1e-6)
        assert hi == pytest.approx(raw_hi + expected_pad, abs=1e-6)

    def test_zero_margin_is_flush_with_data(self, twin_line_fig):
        fig, (ax1, ax2) = twin_line_fig
        sync_axes_limits((ax1, ax2), which="y", margin=0.0)
        lo, hi = ax1.get_ylim()
        raw_lo, raw_hi = self._raw_y_bounds()
        assert lo == pytest.approx(raw_lo, abs=1e-6)
        assert hi == pytest.approx(raw_hi, abs=1e-6)
