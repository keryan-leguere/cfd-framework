"""Panel labels for multi-panel figures."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pytest

from cfd_plot import new_figure, panel_labels
from cfd_plot.layout import _default_labels


@pytest.fixture
def grid():
    fig, axes = new_figure(2, 2)
    yield fig, axes
    plt.close(fig)


class TestDefaultLabels:
    def test_it_starts_at_a(self):
        assert _default_labels(3) == ["a", "b", "c"]

    def test_it_continues_past_z_without_repeating(self):
        labels = _default_labels(30)
        assert labels[25:28] == ["z", "aa", "ab"]
        assert len(set(labels)) == len(labels)

    def test_none_is_empty(self):
        assert _default_labels(0) == []


class TestPanelLabels:
    def test_one_label_per_panel_in_reading_order(self, grid):
        _, axes = grid
        texts = panel_labels(axes)
        assert [t.get_text() for t in texts] == ["(a)", "(b)", "(c)", "(d)"]
        # Row-major: the second label belongs to the top-right panel.
        assert texts[1].axes is axes[0][1]

    def test_it_accepts_a_single_axes(self):
        fig, ax = new_figure()
        assert [t.get_text() for t in panel_labels(ax)] == ["(a)"]
        plt.close(fig)

    def test_it_accepts_a_plain_list(self, grid):
        _, axes = grid
        flat = list(axes.ravel())
        assert len(panel_labels(flat)) == 4

    def test_fmt_controls_the_decoration(self, grid):
        _, axes = grid
        assert [t.get_text() for t in panel_labels(axes, fmt="{}.")] == ["a.", "b.", "c.", "d."]

    def test_explicit_labels_are_used_verbatim(self, grid):
        _, axes = grid
        texts = panel_labels(axes, labels=["i", "ii", "iii", "iv"], fmt="{}")
        assert [t.get_text() for t in texts] == ["i", "ii", "iii", "iv"]

    def test_extra_labels_are_ignored(self, grid):
        _, axes = grid
        assert len(panel_labels(axes, labels=list("abcdefgh"))) == 4

    def test_labels_are_positioned_in_axes_coordinates(self, grid):
        _, axes = grid
        text = panel_labels(axes)[0]
        assert text.get_transform() is axes[0][0].transAxes

    def test_the_label_survives_a_limit_change(self, grid):
        # The whole point of axes coordinates: rescaling must not move it.
        _, axes = grid
        text = panel_labels(axes)[0]
        before = text.get_position()
        axes[0][0].set_xlim(-100, 100)
        assert text.get_position() == before

    @pytest.mark.parametrize(
        ("loc", "expected"),
        [
            ("upper left", ("left", "top")),
            ("upper right", ("right", "top")),
            ("lower left", ("left", "bottom")),
            ("lower right", ("right", "bottom")),
        ],
    )
    def test_each_corner_anchors_correctly(self, grid, loc, expected):
        _, axes = grid
        text = panel_labels(axes, loc=loc)[0]
        assert (text.get_ha(), text.get_va()) == expected

    def test_outside_places_the_label_above_the_axes(self, grid):
        _, axes = grid
        text = panel_labels(axes, outside=True)[0]
        assert text.get_position()[1] > 1.0
        assert text.get_va() == "bottom"

    def test_invisible_panels_are_skipped(self):
        # plt.subplots on an over-large grid leaves blank axes; labelling them
        # would shift every subsequent letter onto the wrong panel.
        fig, axes = new_figure(1, 3)
        axes[2].set_visible(False)
        assert [t.get_text() for t in panel_labels(axes)] == ["(a)", "(b)"]
        plt.close(fig)

    def test_invisible_panels_can_be_kept(self):
        fig, axes = new_figure(1, 3)
        axes[2].set_visible(False)
        assert len(panel_labels(axes, skip_invisible=False)) == 3
        plt.close(fig)

    def test_text_kwargs_are_forwarded(self, grid):
        _, axes = grid
        text = panel_labels(axes, fontsize=17, color="red")[0]
        assert text.get_fontsize() == 17
        assert text.get_color() == "red"

    def test_it_rejects_an_unknown_loc(self, grid):
        _, axes = grid
        with pytest.raises(ValueError, match="Unknown loc"):
            panel_labels(axes, loc="middle")

    def test_it_rejects_too_few_labels(self, grid):
        _, axes = grid
        with pytest.raises(ValueError, match="4 panel"):
            panel_labels(axes, labels=["a"])
