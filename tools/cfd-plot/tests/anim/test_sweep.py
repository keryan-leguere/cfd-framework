"""Tests for ``cfd_plot.anim.sweep`` — the one-liner and its escape hatches."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest

from cfd_plot import animate_sweep

from .conftest import FAST, TINY_FIGSIZE, gif_frame_count

ALPHA = np.linspace(-4.0, 16.0, 11)
CN = 0.11 * ALPHA + 0.004 * ALPHA**2
MACH = np.array([0.3, 0.6, 0.9])
CN_PER_MACH = np.array([(0.11 + 0.05 * m) * ALPHA for m in MACH])

TINY = {**FAST, "figsize": TINY_FIGSIZE}


class TestModeInference:
    def test_a_one_dimensional_y_reveals_point_by_point(self, tmp_path):
        result = animate_sweep(ALPHA, CN, tmp_path / "a.gif", **TINY)
        assert result.n_captures == len(ALPHA)

    def test_a_two_dimensional_y_gives_one_frame_per_curve(self, tmp_path):
        result = animate_sweep(ALPHA, CN_PER_MACH, tmp_path / "a.gif", **TINY)
        assert result.n_captures == len(MACH)

    def test_a_list_of_curves_counts_as_two_dimensional(self, tmp_path):
        result = animate_sweep(ALPHA, [CN, CN * 1.1], tmp_path / "a.gif", **TINY)
        assert result.n_captures == 2

    def test_reveal_can_be_forced_on_a_curve_family(self, tmp_path):
        # All three polars grow together, one point per frame.
        result = animate_sweep(ALPHA, CN_PER_MACH, tmp_path / "a.gif", reveal=True, **TINY)
        assert result.n_captures == len(ALPHA)

    def test_sweep_can_be_forced_on_a_single_curve(self, tmp_path):
        result = animate_sweep(ALPHA, CN, tmp_path / "a.gif", reveal=False, **TINY)
        assert result.n_captures == 1

    def test_each_frame_can_have_its_own_abscissa(self, tmp_path):
        xs = [ALPHA, ALPHA[:5], ALPHA[:3]]
        ys = [CN, CN[:5], CN[:3]]
        result = animate_sweep(xs, ys, tmp_path / "a.gif", **TINY)
        assert result.n_captures == 3

    def test_the_encoded_gif_matches_the_capture_count(self, tmp_path):
        result = animate_sweep(ALPHA, CN, tmp_path / "a.gif", **TINY)
        assert gif_frame_count(result.paths[0]) == result.n_frames


class TestInputValidation:
    def test_mismatched_lengths_name_the_offending_curve(self, tmp_path):
        with pytest.raises(ValueError, match="curve 1"):
            animate_sweep(ALPHA, [CN, CN[:5]], tmp_path / "a.gif", **TINY)

    def test_mismatched_curve_counts_are_reported(self, tmp_path):
        with pytest.raises(ValueError, match="must match"):
            animate_sweep([ALPHA, ALPHA], [CN, CN, CN], tmp_path / "a.gif", **TINY)

    def test_empty_input_is_refused(self, tmp_path):
        with pytest.raises(ValueError, match="nothing to animate"):
            animate_sweep([], [], tmp_path / "a.gif", **TINY)

    def test_reveal_needs_curves_of_equal_length(self, tmp_path):
        with pytest.raises(ValueError, match="same number of points"):
            animate_sweep([ALPHA, ALPHA[:5]], [CN, CN[:5]], tmp_path / "a.gif", reveal=True, **TINY)


class TestAxesAreLocked:
    def test_limits_cover_the_whole_dataset_from_the_first_frame(self, tmp_path):
        # Autoscaling per frame is what makes a revealed curve appear to
        # shrink as it grows; the window must be the final one from frame 0.
        result = animate_sweep(ALPHA, CN, tmp_path / "a.gif", close_fig=False, **TINY)
        lo, hi = result.axes.get_ylim()
        assert lo <= CN.min() and hi >= CN.max()

    def test_margin_pads_the_data_range(self, tmp_path):
        result = animate_sweep(ALPHA, CN, tmp_path / "a.gif", margin=0.25, close_fig=False, **TINY)
        span = CN.max() - CN.min()
        assert result.axes.get_ylim()[0] == pytest.approx(CN.min() - 0.25 * span)

    def test_lock_axes_false_leaves_the_caller_in_charge(self, tmp_path):
        fig, ax = plt.subplots(figsize=TINY_FIGSIZE)
        ax.set_ylim(-99.0, 99.0)
        animate_sweep(ALPHA, CN, tmp_path / "a.gif", ax=ax, lock_axes=False, **FAST)
        assert ax.get_ylim() == (-99.0, 99.0)

    def test_a_log_axis_ignores_non_positive_data(self, tmp_path):
        # log10 of a residual history that touches zero would otherwise drag
        # the lower limit to -inf and blow the range up.
        y = np.array([1.0, 1e-3, 0.0, 1e-6])
        result = animate_sweep(np.arange(4), y, tmp_path / "a.gif", yscale="log", close_fig=False, **TINY)
        lo, hi = result.axes.get_ylim()
        assert lo > 0 and lo < 1e-6 and hi > 1.0

    def test_a_flat_curve_still_gets_a_visible_window(self, tmp_path):
        result = animate_sweep(ALPHA, np.full_like(ALPHA, 2.0), tmp_path / "a.gif", close_fig=False, **TINY)
        lo, hi = result.axes.get_ylim()
        assert hi > lo

    def test_all_nan_data_does_not_crash(self, tmp_path):
        result = animate_sweep(ALPHA, np.full_like(ALPHA, np.nan), tmp_path / "a.gif", close_fig=False, **TINY)
        assert result.axes.get_ylim() == (0.0, 1.0)


class TestLabellingAndDecoration:
    def test_axis_labels_and_scales_are_applied(self, tmp_path):
        result = animate_sweep(
            ALPHA, CN, tmp_path / "a.gif",
            xlabel="alpha [deg]", ylabel="CN [-]", close_fig=False, **TINY,
        )
        assert result.axes.get_xlabel() == "alpha [deg]"
        assert result.axes.get_ylabel() == "CN [-]"

    def test_in_sweep_mode_labels_end_up_in_the_title(self, tmp_path):
        labels = [f"M = {m:.2f}" for m in MACH]
        result = animate_sweep(ALPHA, CN_PER_MACH, tmp_path / "a.gif", labels=labels, close_fig=False, **TINY)
        assert result.axes.get_title() == labels[-1]

    def test_a_static_title_is_joined_to_the_frame_label(self, tmp_path):
        result = animate_sweep(
            ALPHA, CN_PER_MACH, tmp_path / "a.gif",
            title="Polar", labels=["a", "b", "c"], close_fig=False, **TINY,
        )
        assert result.axes.get_title() == "Polar — c"

    def test_a_static_title_survives_without_labels(self, tmp_path):
        result = animate_sweep(ALPHA, CN, tmp_path / "a.gif", title="Polar", close_fig=False, **TINY)
        assert result.axes.get_title() == "Polar"

    def test_in_reveal_mode_labels_are_legend_entries(self, tmp_path):
        result = animate_sweep(
            ALPHA, CN_PER_MACH, tmp_path / "a.gif",
            reveal=True, labels=["SA", "KW", "SST"], close_fig=False, **TINY,
        )
        assert [t.get_text() for t in result.axes.get_legend().get_texts()] == ["SA", "KW", "SST"]
        # ...and not in the title, which is where sweep-mode labels go.
        assert result.axes.get_title() == ""

    def test_no_legend_when_there_is_nothing_to_name(self, tmp_path):
        result = animate_sweep(ALPHA, CN, tmp_path / "a.gif", close_fig=False, **TINY)
        assert result.axes.get_legend() is None

    def test_a_legend_can_be_suppressed(self, tmp_path):
        result = animate_sweep(
            ALPHA, CN_PER_MACH, tmp_path / "a.gif",
            reveal=True, labels=["a", "b", "c"], legend=False, close_fig=False, **TINY,
        )
        assert result.axes.get_legend() is None


class TestRevealHead:
    def test_a_head_marker_is_drawn_by_default(self, tmp_path):
        result = animate_sweep(ALPHA, CN, tmp_path / "a.gif", close_fig=False, **TINY)
        # The curve plus its leading dot.
        assert len(result.axes.get_lines()) == 2

    def test_the_head_sits_on_the_last_revealed_point(self, tmp_path):
        result = animate_sweep(ALPHA, CN, tmp_path / "a.gif", close_fig=False, **TINY)
        head = result.axes.get_lines()[1]
        assert head.get_xdata()[0] == pytest.approx(ALPHA[-1])
        assert head.get_ydata()[0] == pytest.approx(CN[-1])

    def test_the_head_can_be_switched_off(self, tmp_path):
        result = animate_sweep(ALPHA, CN, tmp_path / "a.gif", head=False, close_fig=False, **TINY)
        assert len(result.axes.get_lines()) == 1

    def test_the_head_is_customisable(self, tmp_path):
        result = animate_sweep(
            ALPHA, CN, tmp_path / "a.gif",
            head_kwargs={"markersize": 20, "marker": "s"}, close_fig=False, **TINY,
        )
        head = result.axes.get_lines()[1]
        assert head.get_markersize() == 20
        assert head.get_marker() == "s"

    def test_no_head_in_sweep_mode(self, tmp_path):
        result = animate_sweep(ALPHA, CN_PER_MACH, tmp_path / "a.gif", close_fig=False, **TINY)
        assert len(result.axes.get_lines()) == 1


class TestKeepPrevious:
    def test_every_curve_stays_on_screen(self, tmp_path):
        result = animate_sweep(ALPHA, CN_PER_MACH, tmp_path / "a.gif", keep_previous=True, close_fig=False, **TINY)
        assert len(result.axes.get_lines()) == len(MACH)

    def test_earlier_curves_are_faded_and_the_current_one_is_not(self, tmp_path):
        result = animate_sweep(
            ALPHA, CN_PER_MACH, tmp_path / "a.gif",
            keep_previous=True, ghost_alpha=0.3, close_fig=False, **TINY,
        )
        alphas = [ln.get_alpha() for ln in result.axes.get_lines()]
        assert alphas[:-1] == [0.3, 0.3]
        assert alphas[-1] == 1.0

    def test_labels_stay_out_of_the_legend(self, tmp_path):
        # Regression: keep_previous used to legend every curve from frame 0,
        # naming curves not yet drawn — and past ten of them the property
        # cycle repeats, so two entries would share a colour. Sweep-mode
        # labels identify the frame, and the title is where that belongs.
        result = animate_sweep(
            ALPHA, CN_PER_MACH, tmp_path / "a.gif",
            keep_previous=True, labels=["M = 0.30", "M = 0.60", "M = 0.90"],
            close_fig=False, **TINY,
        )
        assert result.axes.get_legend() is None
        assert result.axes.get_title() == "M = 0.90"

    def test_off_by_default_a_single_line_is_recycled(self, tmp_path):
        result = animate_sweep(ALPHA, CN_PER_MACH, tmp_path / "a.gif", close_fig=False, **TINY)
        assert len(result.axes.get_lines()) == 1


class TestEscapeHatches:
    def test_an_existing_axes_is_reused_and_its_decoration_kept(self, tmp_path):
        fig, ax = plt.subplots(figsize=TINY_FIGSIZE)
        ax.set_xlabel("mine")
        ax.axhline(0.0, color="k")
        result = animate_sweep(ALPHA, CN, tmp_path / "a.gif", ax=ax, close_fig=False, **FAST)
        assert result.axes is ax
        assert ax.get_xlabel() == "mine"
        # The reference line the caller drew is still there, alongside the
        # animated curve and its head.
        assert len(ax.get_lines()) == 3

    def test_on_frame_runs_once_per_frame_with_the_index_and_axes(self, tmp_path):
        seen = []
        animate_sweep(
            ALPHA, CN_PER_MACH, tmp_path / "a.gif",
            on_frame=lambda i, ax: seen.append((i, ax)), **TINY,
        )
        assert [i for i, _ in seen] == [0, 1, 2]
        assert all(a is seen[0][1] for _, a in seen)

    def test_on_frame_sees_the_data_already_set(self, tmp_path):
        # So a callback can annotate the current point without recomputing it.
        widths = []
        animate_sweep(ALPHA, CN, tmp_path / "a.gif", on_frame=lambda i, ax: widths.append(len(ax.get_lines()[0].get_xdata())), **TINY)
        assert widths == list(range(1, len(ALPHA) + 1))

    def test_close_fig_false_hands_the_figure_back(self, tmp_path):
        result = animate_sweep(ALPHA, CN, tmp_path / "a.gif", close_fig=False, **TINY)
        assert result.fig is not None
        assert plt.fignum_exists(result.fig.number)

    def test_close_fig_true_leaves_no_figure_open(self, tmp_path):
        before = set(plt.get_fignums())
        animate_sweep(ALPHA, CN, tmp_path / "a.gif", **TINY)
        assert set(plt.get_fignums()) == before

    def test_engine_options_pass_straight_through(self, tmp_path):
        result = animate_sweep(
            ALPHA, CN, tmp_path / "a.gif",
            preset="readme", fps=10, hold_last=0.5, boomerang=True, width_px=120,
        )
        assert result.preset == "readme"
        assert result.size_px[0] == 120
        # 11 captures, +5 held, then mirrored without repeating the endpoints.
        assert result.n_frames == 2 * (11 + 5) - 2
