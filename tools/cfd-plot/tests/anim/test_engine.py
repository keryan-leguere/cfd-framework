"""Tests for ``cfd_plot.anim.engine`` — capture, layout locking, results."""

from __future__ import annotations

import logging
import subprocess
import sys

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pytest
from PIL import Image

from cfd_plot import use_style
from cfd_plot.anim import AnimationResult, Animator, animate, animate_frames, ffmpeg_available
from cfd_plot.anim import encode as enc

from .conftest import FAST, TINY_FIGSIZE, gif_frame_count, gif_info, gif_palettes


def _run(fig, line, path, n=4, **kw):
    """Capture *n* frames of a growing line."""
    opts = {**FAST, **kw}
    with animate(fig, path, **opts) as anim:
        for i in range(n):
            line.set_data(np.linspace(0, 1, i + 2), np.linspace(0, 1, i + 2))
            anim.capture()
    return anim.result


class TestBasicCapture:
    def test_writes_a_gif_with_one_frame_per_capture(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "a.gif", n=4)
        assert result.n_captures == 4
        assert result.n_frames == 4
        assert gif_frame_count(result.paths[0]) == 4

    def test_render_width_is_exactly_the_requested_pixel_width(self, tiny_fig, tmp_path):
        # The style profiles ask for 150-600 dpi; on a 12-inch slides figure
        # that would be a 7200 px animation. The preset's width_px must win.
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "a.gif", width_px=240)
        assert result.size_px[0] == 240
        assert gif_info(result.paths[0])["size"][0] == 240

    def test_aspect_ratio_follows_the_figure(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "a.gif", width_px=240)
        expected_h = round(240 * TINY_FIGSIZE[1] / TINY_FIGSIZE[0])
        assert result.size_px[1] == pytest.approx(expected_h, abs=1)

    def test_the_gif_carries_one_palette(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "a.gif")
        assert len(gif_palettes(result.paths[0])) == 1

    def test_frames_are_fully_opaque(self, tiny_fig, tmp_path):
        # A transparent background quantises into grey fringes around every
        # glyph once the GIF palette is applied.
        fig, _, line = tiny_fig
        _run(fig, line, tmp_path / "a.gif", keep_frames=tmp_path / "frames")
        with Image.open(sorted((tmp_path / "frames").glob("*.png"))[0]) as im:
            assert im.mode == "RGB" or im.getchannel("A").getextrema() == (255, 255)


class TestLayoutIsLocked:
    """The reason this module exists.

    Both cfd_plot defaults conspire against a naive frame loop:
    ``savefig.bbox: tight`` re-crops the output to its ink on every save, and
    ``constrained_layout`` re-solves the axes position. Anything that changes
    the figure's extent mid-animation — a suptitle appearing, a tick label
    growing from ``9`` to ``10`` — then changes the frame size, and the
    animation shakes.
    """

    @staticmethod
    def _jittery_figure():
        fig, ax = plt.subplots(figsize=TINY_FIGSIZE)
        (line,) = ax.plot([], [])
        ax.set_xlim(0, 1)
        return fig, ax, line

    @staticmethod
    def _mutate(fig, ax, line, i):
        # Each of these changes the tight bounding box: the y tick labels go
        # from one character to five, and a suptitle appears at frame 1.
        ax.set_ylim(0, 10 ** (2 * i))
        line.set_data([0, 1], [0, 10 ** (2 * i)])
        if i:
            fig.suptitle("x" * (10 * i))

    def test_every_frame_has_the_same_pixel_size(self, tmp_path):
        fig, ax, line = self._jittery_figure()
        with animate(fig, tmp_path / "a.gif", keep_frames=tmp_path / "frames", **FAST) as anim:
            for i in range(4):
                self._mutate(fig, ax, line, i)
                anim.capture()

        sizes = set()
        for p in sorted((tmp_path / "frames").glob("*.png")):
            with Image.open(p) as im:
                sizes.add(im.size)
        assert len(sizes) == 1, f"frames differ in size: {sizes}"

    def test_the_naive_savefig_loop_really_does_jitter(self, tmp_path):
        # Proves the test above is not vacuous: the same mutations through a
        # plain savefig, under the package's own style, produce frames of
        # different sizes. If Matplotlib ever changes this, the guard above
        # stops being a regression test and we want to know.
        use_style("notebook")
        fig, ax, line = self._jittery_figure()
        sizes = set()
        for i in range(4):
            self._mutate(fig, ax, line, i)
            path = tmp_path / f"naive_{i}.png"
            fig.savefig(path, dpi=80)
            with Image.open(path) as im:
                sizes.add(im.size)
        assert len(sizes) > 1

    def test_constrained_layout_stops_moving_the_axes_after_the_first_frame(self, tmp_path):
        # constrained_layout shrinks the axes to make room for a suptitle. Left
        # running, that happens on the frame the suptitle appears — the axes
        # jump, mid-animation. It must be frozen at its first-frame solution.
        fig, ax = plt.subplots(figsize=TINY_FIGSIZE, layout="constrained")
        (line,) = ax.plot([0, 1], [0, 1])

        positions = []
        with animate(fig, tmp_path / "a.gif", **FAST) as anim:
            for i in range(3):
                if i:
                    fig.suptitle("a title tall enough to steal room\nfrom the axes")
                anim.capture()
                positions.append(tuple(ax.get_position().bounds))

        assert len(set(positions)) == 1, f"the axes moved between frames: {positions}"

    def test_resizing_the_figure_mid_capture_is_reported_clearly(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        with pytest.raises(RuntimeError, match="resized mid-capture"), animate(fig, tmp_path / "a.gif", **FAST) as anim:
            anim.capture()
            fig.set_size_inches(4, 3)
            anim.capture()


class TestHoldsAndBoomerang:
    def test_hold_on_a_capture_repeats_that_frame(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        with animate(fig, tmp_path / "a.gif", **FAST) as anim:
            for i in range(3):
                line.set_data([0, i], [0, i])
                anim.capture(hold=0.5 if i == 2 else 0.0)
        assert anim.result.n_captures == 3
        assert anim.result.n_frames == 3 + 5

    def test_repeat_is_frame_exact(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        with animate(fig, tmp_path / "a.gif", **FAST) as anim:
            anim.capture(repeat=3)
        assert anim.result.n_frames == 3

    def test_repeat_must_be_at_least_one(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        with pytest.raises(ValueError, match="repeat must be"), animate(fig, tmp_path / "a.gif", **FAST) as anim:
            anim.capture(repeat=0)

    def test_hold_last_lingers_on_the_final_state(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "a.gif", n=3, hold_last=1.0)
        assert result.n_frames == 3 + 10

    def test_boomerang_plays_back_down(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "a.gif", n=4, boomerang=True)
        assert result.n_frames == 6


class TestFormats:
    def test_the_suffix_selects_the_format(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "a.gif")
        assert [p.suffix for p in result.paths] == [".gif"]

    def test_a_bare_path_defaults_to_gif(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "bare")
        assert result.paths[0].name == "bare.gif"

    @pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
    def test_both_formats_share_one_render_pass(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "a", formats=("gif", "mp4"))
        assert [p.suffix for p in result.paths] == [".gif", ".mp4"]
        assert all(p.is_file() for p in result.paths)
        # One capture loop, two containers — the frames are not rendered twice.
        assert result.n_captures == 4

    def test_an_explicit_format_list_overrides_the_suffix(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "a.mp4", formats=("gif",))
        assert [p.suffix for p in result.paths] == [".gif"]

    def test_unsupported_format_lists_the_valid_ones(self, tiny_fig, tmp_path):
        fig, _, _ = tiny_fig
        with pytest.raises(ValueError, match="unsupported format"):
            Animator(fig, tmp_path / "a", formats=("webm",))

    def test_empty_format_list(self, tiny_fig, tmp_path):
        fig, _, _ = tiny_fig
        with pytest.raises(ValueError, match="formats is empty"):
            Animator(fig, tmp_path / "a", formats=())


class TestLifecycle:
    def test_capture_after_close_is_refused(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        anim = Animator(fig, tmp_path / "a.gif", **FAST)
        anim.capture()
        anim.close()
        with pytest.raises(RuntimeError, match="closed"):
            anim.capture()

    def test_double_close_is_refused(self, tiny_fig, tmp_path):
        fig, _, _ = tiny_fig
        anim = Animator(fig, tmp_path / "a.gif", **FAST)
        anim.capture()
        anim.close()
        with pytest.raises(RuntimeError, match="already closed"):
            anim.close()

    def test_closing_with_nothing_captured_says_so(self, tiny_fig, tmp_path):
        fig, _, _ = tiny_fig
        with pytest.raises(ValueError, match="nothing was captured"):
            Animator(fig, tmp_path / "a.gif", **FAST).close()

    def test_an_exception_in_the_loop_propagates_untouched(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        with pytest.raises(RuntimeError, match="solver diverged"), animate(fig, tmp_path / "a.gif", **FAST) as anim:
            anim.capture()
            raise RuntimeError("solver diverged")
        # No half-written animation is left behind to be mistaken for a result.
        assert not (tmp_path / "a.gif").exists()

    def test_temporary_frames_are_cleaned_up(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        anim = Animator(fig, tmp_path / "a.gif", **FAST)
        anim.capture()
        frames_dir = anim._frames_dir
        anim.close()
        assert not frames_dir.exists()

    def test_keep_frames_leaves_the_pngs_behind(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "a.gif", n=3, keep_frames=tmp_path / "kept")
        assert result.frames_dir == tmp_path / "kept"
        assert len(list(result.frames_dir.glob("*.png"))) == 3

    @pytest.mark.parametrize("kwargs", [{"fps": 0}, {"width_px": 0}])
    def test_nonsensical_settings_are_rejected_up_front(self, tiny_fig, tmp_path, kwargs):
        fig, _, _ = tiny_fig
        with pytest.raises(ValueError):
            Animator(fig, tmp_path / "a.gif", **kwargs)


class TestResult:
    def test_duration_reflects_holds(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "a.gif", n=5, fps=10, hold_last=1.0)
        assert result.duration_s == pytest.approx(1.5)

    def test_total_bytes_sums_every_file(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        result = _run(fig, line, tmp_path / "a.gif")
        assert result.total_bytes == result.paths[0].stat().st_size

    def test_str_is_a_one_line_summary(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        text = str(_run(fig, line, tmp_path / "a.gif", n=4))
        assert "a.gif" in text and "4 frames" in text and "kB" in text

    def test_report_prints_a_table(self, tiny_fig, tmp_path, capsys):
        fig, _, line = tiny_fig
        _run(fig, line, tmp_path / "a.gif").report()
        assert "a.gif" in capsys.readouterr().out

    def test_backend_names_the_encoder_that_ran(self, tiny_fig, tmp_path, monkeypatch):
        fig, _, line = tiny_fig
        monkeypatch.setattr(enc, "ffmpeg_available", lambda: False)
        assert _run(fig, line, tmp_path / "a.gif").backend == "pillow"

    def test_preset_is_echoed_back(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        assert _run(fig, line, tmp_path / "a.gif", preset="readme").preset == "readme"

    def test_frames_dir_is_none_when_frames_were_temporary(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        assert _run(fig, line, tmp_path / "a.gif").frames_dir is None


class TestSizeWarning:
    def test_a_heavy_file_gets_an_actionable_warning(self, tiny_fig, tmp_path, caplog):
        fig, _, line = tiny_fig
        with caplog.at_level(logging.WARNING, logger="cfd_plot.anim.engine"):
            _run(fig, line, tmp_path / "a.gif", warn_size_mb=1e-6)
        assert "max_colors" in caplog.text and "MB" in caplog.text

    def test_the_warning_can_be_switched_off(self, tiny_fig, tmp_path, caplog):
        fig, _, line = tiny_fig
        with caplog.at_level(logging.WARNING, logger="cfd_plot.anim.engine"):
            _run(fig, line, tmp_path / "a.gif", warn_size_mb=0)
        assert caplog.text == ""


class TestCallbackForm:
    def test_update_is_called_once_per_frame(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        seen = []

        def update(i):
            seen.append(i)
            line.set_data([0, i], [0, i])

        result = animate_frames(fig, update, 5, tmp_path / "a.gif", **FAST)
        assert seen == [0, 1, 2, 3, 4]
        assert result.n_captures == 5

    def test_zero_frames_is_refused(self, tiny_fig, tmp_path):
        fig, _, _ = tiny_fig
        with pytest.raises(ValueError, match="frames must be"):
            animate_frames(fig, lambda i: None, 0, tmp_path / "a.gif", **FAST)

    def test_it_returns_the_same_result_type(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        assert isinstance(animate_frames(fig, lambda i: None, 2, tmp_path / "a.gif", **FAST), AnimationResult)


class TestProgress:
    def test_progress_reports_the_running_count_on_a_terminal(self, tiny_fig, tmp_path, capsys, monkeypatch):
        from cfd_plot.anim import engine

        monkeypatch.setattr(engine, "_stderr_is_a_terminal", lambda: True)
        fig, _, line = tiny_fig
        _run(fig, line, tmp_path / "a.gif", n=3, progress=True)
        assert "3 frames captured" in capsys.readouterr().err

    def test_progress_stays_quiet_when_the_output_is_not_a_terminal(self, tiny_fig, tmp_path, capsys):
        # A carriage-return counter redrawn per frame is a live display on a
        # terminal and hundreds of concatenated lines in a log or CI transcript.
        fig, _, line = tiny_fig
        _run(fig, line, tmp_path / "a.gif", n=3, progress=True)
        assert capsys.readouterr().err == ""

    def test_silent_by_default(self, tiny_fig, tmp_path, capsys):
        fig, _, line = tiny_fig
        _run(fig, line, tmp_path / "a.gif", n=3)
        captured = capsys.readouterr()
        assert captured.out == "" and captured.err == ""


class TestBackendIsNotHijacked:
    """Animating must not switch the caller's Matplotlib backend.

    Same hazard as ``batch.py`` used to have: a module that forces ``Agg``
    breaks interactive plotting for the rest of the session (Spyder, Jupyter:
    "FigureCanvasAgg is non-interactive", no window ever appears) and closes
    figures the user already had open, because ``matplotlib.use()`` calls
    ``close("all")``. Frames go through ``fig.savefig``, which picks its own
    PNG renderer without touching the global backend.
    """

    def test_importing_the_module_leaves_the_backend_alone(self):
        code = (
            "import matplotlib; matplotlib.use('template');"
            "import cfd_plot.anim;"
            "print(matplotlib.get_backend())"
        )
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
        assert out.stdout.strip().lower() == "template"

    def test_a_full_animation_run_leaves_the_backend_alone(self, tmp_path):
        previous = matplotlib.get_backend()
        matplotlib.use("template")
        try:
            fig, ax = plt.subplots(figsize=TINY_FIGSIZE)
            (line,) = ax.plot([], [])
            result = _run(fig, line, tmp_path / "a.gif", n=2)
            assert result.paths[0].is_file()
            assert matplotlib.get_backend().lower() == "template"
        finally:
            matplotlib.use(previous)

    def test_figures_the_caller_opened_are_not_closed(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        other = plt.figure()
        _run(fig, line, tmp_path / "a.gif", n=2)
        assert plt.fignum_exists(other.number)
