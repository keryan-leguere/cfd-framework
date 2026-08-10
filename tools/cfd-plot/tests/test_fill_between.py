"""Tests for ``fill_between_curves``."""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from cfd_plot import fill_between_curves, use_style


@pytest.fixture(autouse=True)
def _use_notebook_style():
    use_style("notebook")
    yield
    plt.close("all")


@pytest.fixture
def curves():
    x = np.linspace(0.0, 10.0, 41)
    return x, np.sin(x), np.cos(x)


class TestArtists:
    def test_returns_two_boundary_lines_and_one_fill(self, curves):
        _, ax = plt.subplots()
        lines, polys = fill_between_curves(ax, *curves)
        assert len(lines) == 2
        assert len(polys) == 1

    def test_lines_false_draws_the_shading_only(self, curves):
        _, ax = plt.subplots()
        lines, polys = fill_between_curves(ax, *curves, lines=False)
        assert lines == []
        assert len(polys) == 1
        assert ax.get_lines() == []

    def test_boundary_lines_carry_the_data(self, curves):
        x, y1, y2 = curves
        _, ax = plt.subplots()
        lines, _ = fill_between_curves(ax, x, y1, y2)
        assert np.allclose(lines[0].get_ydata(), y1)
        assert np.allclose(lines[1].get_ydata(), y2)

    def test_boundary_lines_have_no_markers(self, curves):
        """A boundary delimits a region; markers would read as measurements."""
        _, ax = plt.subplots()
        lines, _ = fill_between_curves(ax, *curves)
        assert all(ln.get_marker() in ("", "None", None) for ln in lines)

    def test_line_kwargs_reach_both_boundaries(self, curves):
        _, ax = plt.subplots()
        lines, _ = fill_between_curves(
            ax, *curves, line_kwargs={"ls": ":", "marker": "s"}
        )
        assert all(ln.get_linestyle() == ":" for ln in lines)
        assert all(ln.get_marker() == "s" for ln in lines)

    def test_fill_kwargs_reach_fill_between(self, curves):
        _, ax = plt.subplots()
        _, polys = fill_between_curves(ax, *curves, zorder=7)
        assert polys[0].get_zorder() == 7


class TestSecondCurveDefault:
    def test_defaults_to_the_zero_baseline(self):
        x = np.linspace(0.0, 1.0, 11)
        _, ax = plt.subplots()
        lines, _ = fill_between_curves(ax, x, x**2)
        assert np.allclose(lines[1].get_ydata(), 0.0)

    def test_accepts_a_scalar_second_curve(self):
        x = np.linspace(0.0, 1.0, 11)
        _, ax = plt.subplots()
        lines, polys = fill_between_curves(ax, x, x**2, 0.5)
        assert np.allclose(lines[1].get_ydata(), 0.5)
        assert len(polys) == 1


class TestColour:
    def test_explicit_colour_is_shared_by_fill_and_lines(self, curves):
        _, ax = plt.subplots()
        lines, polys = fill_between_curves(ax, *curves, color="tab:green")
        expected = matplotlib.colors.to_rgb("tab:green")
        assert all(matplotlib.colors.to_rgb(ln.get_color()) == expected for ln in lines)
        assert tuple(polys[0].get_facecolor()[0][:3]) == pytest.approx(expected)

    def test_boundary_lines_inherit_the_cycle_colour_of_the_fill(self, curves):
        """No explicit colour: the group must still read as one object."""
        _, ax = plt.subplots()
        lines, polys = fill_between_curves(ax, *curves)
        face = tuple(polys[0].get_facecolor()[0][:3])
        for ln in lines:
            assert matplotlib.colors.to_rgb(ln.get_color()) == pytest.approx(face)

    def test_boundary_lines_are_opaque_despite_the_translucent_fill(self, curves):
        _, ax = plt.subplots()
        lines, polys = fill_between_curves(ax, *curves, alpha=0.15)
        assert polys[0].get_facecolor()[0][3] == pytest.approx(0.15)
        assert all(ln.get_alpha() in (None, 1.0) for ln in lines)

    def test_line_kwargs_colour_overrides_the_fill_colour(self, curves):
        _, ax = plt.subplots()
        lines, _ = fill_between_curves(
            ax, *curves, color="tab:green", line_kwargs={"color": "black"}
        )
        assert all(matplotlib.colors.to_rgb(ln.get_color()) == (0.0, 0.0, 0.0) for ln in lines)


class TestSignedMode:
    def test_splits_into_two_fills(self, curves):
        _, ax = plt.subplots()
        _, polys = fill_between_curves(ax, *curves, signed=True)
        assert len(polys) == 2

    def test_the_two_halves_get_different_colours(self, curves):
        _, ax = plt.subplots()
        _, polys = fill_between_curves(ax, *curves, signed=True)
        above = tuple(polys[0].get_facecolor()[0][:3])
        below = tuple(polys[1].get_facecolor()[0][:3])
        assert above != below

    def test_signed_colours_and_labels_are_configurable(self, curves):
        _, ax = plt.subplots()
        _, polys = fill_between_curves(
            ax, *curves, signed=True,
            signed_colors=("red", "blue"),
            signed_labels=("A above B", "A below B"),
        )
        assert tuple(polys[0].get_facecolor()[0][:3]) == pytest.approx((1.0, 0.0, 0.0))
        assert tuple(polys[1].get_facecolor()[0][:3]) == pytest.approx((0.0, 0.0, 1.0))
        assert [p.get_label() for p in polys] == ["A above B", "A below B"]

    def test_each_half_only_covers_its_own_sign(self):
        """The 'above' fill must not extend where the first curve is below."""
        x = np.linspace(0.0, 1.0, 101)
        y1 = x - 0.5           # crosses y2 exactly at x = 0.5
        y2 = np.zeros_like(x)
        _, ax = plt.subplots()
        _, polys = fill_between_curves(ax, x, y1, y2, signed=True)

        above_pts = np.concatenate([p.vertices for p in polys[0].get_paths()])
        below_pts = np.concatenate([p.vertices for p in polys[1].get_paths()])
        assert above_pts[:, 0].min() >= 0.5 - 1e-9
        assert below_pts[:, 0].max() <= 0.5 + 1e-9

    def test_signed_mode_still_draws_the_boundaries(self, curves):
        _, ax = plt.subplots()
        lines, polys = fill_between_curves(ax, *curves, signed=True)
        assert len(lines) == 2
        assert len(polys) == 2

    def test_both_boundaries_share_one_neutral_colour(self, curves):
        """Regression: they used to take two successive cycle colours.

        That made the boundaries read as two unrelated series and fought with
        the fills, which are what actually carry the meaning here.
        """
        _, ax = plt.subplots()
        lines, _ = fill_between_curves(ax, *curves, signed=True)
        assert lines[0].get_color() == lines[1].get_color()
        assert matplotlib.colors.to_rgb(lines[0].get_color()) == matplotlib.colors.to_rgb(
            matplotlib.rcParams["axes.edgecolor"]
        )

    def test_an_explicit_colour_still_sets_the_boundaries(self, curves):
        _, ax = plt.subplots()
        lines, polys = fill_between_curves(ax, *curves, signed=True, color="black")
        assert all(matplotlib.colors.to_rgb(ln.get_color()) == (0.0, 0.0, 0.0) for ln in lines)
        # …without touching the fills, which keep their signed colours.
        assert tuple(polys[0].get_facecolor()[0][:3]) != tuple(polys[1].get_facecolor()[0][:3])


class TestLegend:
    def test_the_fill_is_labelled_not_the_boundaries(self, curves):
        _, ax = plt.subplots()
        lines, polys = fill_between_curves(ax, *curves, label="écart")
        assert polys[0].get_label() == "écart"
        # Matplotlib gives unlabelled artists an underscore-prefixed name,
        # which keeps them out of the legend.
        assert all(ln.get_label().startswith("_") for ln in lines)

    def test_only_the_fill_reaches_the_legend(self, curves):
        _, ax = plt.subplots()
        fill_between_curves(ax, *curves, label="écart")
        legend = ax.legend()
        assert [t.get_text() for t in legend.get_texts()] == ["écart"]
