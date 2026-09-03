"""Named colour cycles."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib as mpl
import matplotlib.pyplot as plt
import pytest
from matplotlib.colors import to_rgba

from cfd_plot import (
    PALETTES,
    new_figure,
    palette_colors,
    palette_context,
    set_palette,
)


class TestPalettes:
    @pytest.mark.parametrize("name", sorted(PALETTES))
    def test_every_palette_is_valid_and_non_empty(self, name):
        colors = PALETTES[name]
        assert colors
        for color in colors:
            to_rgba(color)  # raises if invalid

    @pytest.mark.parametrize("name", sorted(PALETTES))
    def test_no_palette_repeats_a_colour(self, name):
        # A repeated colour means two series drawn identically.
        assert len(set(PALETTES[name])) == len(PALETTES[name])

    def test_grayscale_is_monotonically_lighter(self):
        # It exists for print; a non-monotonic ramp would defeat that.
        values = [to_rgba(c)[0] for c in PALETTES["grayscale"]]
        assert values == sorted(values)


class TestPaletteColors:
    def test_it_returns_the_whole_palette_by_default(self):
        assert palette_colors("tol_bright") == PALETTES["tol_bright"]

    def test_it_truncates(self):
        assert palette_colors("okabe_ito", 3) == PALETTES["okabe_ito"][:3]

    def test_it_cycles_past_the_end(self):
        colors = palette_colors("grayscale", len(PALETTES["grayscale"]) + 2)
        assert colors[-2:] == PALETTES["grayscale"][:2]

    def test_zero_is_empty(self):
        assert palette_colors("tab10", 0) == ()

    def test_it_accepts_an_explicit_sequence(self):
        assert palette_colors(["red", "#00FF00"]) == ("#ff0000", "#00ff00")

    def test_it_rejects_an_unknown_name_and_lists_the_known_ones(self):
        with pytest.raises(ValueError) as excinfo:
            palette_colors("chartreuse_dreams")
        assert "okabe_ito" in str(excinfo.value)

    def test_it_rejects_an_empty_sequence(self):
        with pytest.raises(ValueError, match="empty"):
            palette_colors([])

    def test_it_rejects_an_invalid_colour_and_says_which(self):
        with pytest.raises(ValueError, match="entry 1"):
            palette_colors(["red", "not-a-colour"])

    def test_negative_n_is_rejected(self):
        with pytest.raises(ValueError, match="n must be"):
            palette_colors("tab10", -1)


class TestSetPalette:
    def test_the_scoped_form_leaves_rcparams_alone(self):
        # Global mutation is the sore spot this API exists to avoid.
        before = mpl.rcParams["axes.prop_cycle"]
        fig, ax = new_figure()
        set_palette("tol_muted", ax=ax)
        assert mpl.rcParams["axes.prop_cycle"] == before
        plt.close(fig)

    def test_the_scoped_form_colours_that_axes(self):
        fig, ax = new_figure()
        set_palette("grayscale", ax=ax)
        (line,) = ax.plot([0, 1], [0, 1])
        assert to_rgba(line.get_color()) == to_rgba(PALETTES["grayscale"][0])
        plt.close(fig)

    def test_the_global_form_changes_rcparams(self):
        before = mpl.rcParams["axes.prop_cycle"]
        try:
            set_palette("okabe_ito")
            assert mpl.rcParams["axes.prop_cycle"] != before
        finally:
            mpl.rcParams["axes.prop_cycle"] = before

    def test_it_returns_the_applied_colours(self):
        fig, ax = new_figure()
        assert set_palette("tab10", ax=ax) == PALETTES["tab10"]
        plt.close(fig)


class TestPaletteContext:
    def test_it_restores_the_previous_cycle_exactly(self):
        before = mpl.rcParams["axes.prop_cycle"]
        with palette_context("grayscale"):
            assert mpl.rcParams["axes.prop_cycle"] != before
        assert mpl.rcParams["axes.prop_cycle"] == before

    def test_it_restores_after_an_exception(self):
        before = mpl.rcParams["axes.prop_cycle"]
        with pytest.raises(RuntimeError), palette_context("tol_bright"):
            raise RuntimeError("boom")
        assert mpl.rcParams["axes.prop_cycle"] == before

    def test_it_restores_a_cycle_carrying_more_than_colour(self):
        # A style sheet may cycle linestyle alongside colour; restoring only the
        # colour would quietly drop that.
        before = mpl.rcParams["axes.prop_cycle"]
        rich = mpl.cycler(color=["red", "blue"]) + mpl.cycler(linestyle=["-", "--"])
        try:
            mpl.rcParams["axes.prop_cycle"] = rich
            with palette_context("tab10"):
                pass
            assert mpl.rcParams["axes.prop_cycle"] == rich
            assert "linestyle" in mpl.rcParams["axes.prop_cycle"].keys
        finally:
            mpl.rcParams["axes.prop_cycle"] = before

    def test_it_yields_the_colours(self):
        with palette_context("okabe_ito") as colors:
            assert colors == PALETTES["okabe_ito"]
