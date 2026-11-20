"""Time-driven animation: timeline, PathReveal, animate_path."""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.colors import to_hex

from cfd_plot import tidy_axes3d, true_proportions
from cfd_plot.anim import PathReveal, animate_path, ffmpeg_available, timeline

from .conftest import FAST


class TestTimeline:
    def test_duration_sets_frame_count_and_ends_are_shown(self):
        tl = timeline(0.0, 10.0, fps=10, duration=2.0)
        assert len(tl) == 21
        assert tl.times[0] == 0.0 and tl.times[-1] == 10.0
        assert np.allclose(np.diff(tl.times), 0.5)

    def test_speed_and_real_time(self):
        assert len(timeline(0.0, 4.0, fps=5, speed=2.0)) == 11
        assert len(timeline(0.0, 4.0, fps=5)) == 21

    def test_hold_inserts_the_exact_instant(self):
        tl = timeline(0.0, 10.0, fps=10, duration=2.0, holds={3.3: 1.5, 99.0: 4.0})
        i = int(np.flatnonzero(tl.times == 3.3)[0])
        assert tl.holds[i] == 1.5 and tl.holds.sum() == 1.5
        assert np.all(np.diff(tl.times) > 0)
        assert tl.duration_s == pytest.approx(len(tl) / 10 + 1.5)

    def test_hold_on_an_existing_frame_does_not_duplicate_it(self):
        tl = timeline(0.0, 10.0, fps=10, duration=2.0, holds={5.0: 1.0})
        assert len(tl) == 21 and tl.holds[10] == 1.0

    @pytest.mark.parametrize("kw", [{"duration": 1.0, "speed": 1.0}, {"duration": 0.0}, {"speed": -1.0}])
    def test_rejects_bad_arguments(self, kw):
        with pytest.raises(ValueError):
            timeline(0.0, 1.0, fps=10, **kw)


class TestPathReveal:
    def _data(self):
        t = np.array([0.0, 1.0, 1.1, 5.0])  # uneven sampling on purpose
        return t, t * 10, t**2, -t

    def test_head_is_interpolated_in_time_not_by_index(self):
        fig, ax = plt.subplots()
        t, x, y, _ = self._data()
        r = PathReveal(ax, t, x, y)
        head = r.update(3.0)
        assert head == pytest.approx([30.0, np.interp(3.0, t, y)])
        xs, _ = r.line.get_data()
        assert list(xs) == pytest.approx([0.0, 10.0, 11.0, 30.0])

    def test_trail_keeps_only_the_last_seconds(self):
        fig, ax = plt.subplots()
        t, x, y, _ = self._data()
        r = PathReveal(ax, t, x, y, trail=0.5)
        r.update(1.2)
        xs, _ = r.line.get_data()
        assert list(xs) == pytest.approx([10.0, 11.0, 12.0])

    def test_3d_axes(self):
        fig = plt.figure()
        ax = fig.add_subplot(projection="3d")
        t, x, y, z = self._data()
        r = PathReveal(ax, t, x, y, z)
        r.update(5.0)
        xs, ys, zs = r.line.get_data_3d()
        assert zs[-1] == pytest.approx(-5.0) and len(xs) == 5

    def test_colour_is_fixed_outside_the_style(self):
        fig, ax = plt.subplots()
        t, x, y, _ = self._data()
        r = PathReveal(ax, t, x, y)
        assert r.line.get_color().startswith("#") and r.head.get_color() == r.line.get_color()

    @pytest.mark.parametrize("bad", ["z_on_2d", "decreasing", "short"])
    def test_rejects(self, bad):
        fig, ax = plt.subplots()
        t, x, y, z = self._data()
        with pytest.raises(ValueError):
            if bad == "z_on_2d":
                PathReveal(ax, t, x, y, z)
            elif bad == "decreasing":
                PathReveal(ax, t[::-1], x, y)
            else:
                PathReveal(ax, t[:1], x[:1], y[:1])


class TestAxes3d:
    def test_true_proportions_and_ticks_per_side(self):
        fig = plt.figure()
        ax = fig.add_subplot(projection="3d")
        true_proportions(ax, [0, 0, 0], [1000, 200, 5000])
        tidy_axes3d(ax, nbins=6)
        aspect = np.asarray(ax.get_box_aspect())
        assert aspect / aspect.max() == pytest.approx([0.2, 0.04, 1.0])
        assert ax.get_xlim() == pytest.approx((0, 1000)) and ax.get_zlim() == pytest.approx((0, 5000))
        # Fewer ticks on the short sides; never a minor grid.
        n = [len(a.get_major_locator().tick_values(*lim))
             for a, lim in zip((ax.xaxis, ax.yaxis, ax.zaxis), (ax.get_xlim(), ax.get_ylim(), ax.get_zlim()))]
        assert n[2] > n[0] >= n[1]
        assert all(len(a.get_minor_locator().tick_values(0, 1)) == 0 for a in (ax.xaxis, ax.yaxis, ax.zaxis))

    def test_refuses_a_2d_axes(self):
        fig, ax = plt.subplots()
        with pytest.raises(ValueError, match="3-D"):
            tidy_axes3d(ax)


class TestAnimatePath:
    def test_2d_gif_with_events(self, tmp_path):
        t = np.linspace(0, 10, 50)
        result = animate_path(t, t, np.sin(t), path=tmp_path / "p.gif", duration=1.0,
                              events={"pic": 1.6}, event_hold=0.5, close_fig=False, **FAST)
        assert result.paths[0].exists()
        assert result.n_captures == 12  # 11 grid frames + the inserted event instant
        legend = result.axes.get_legend()
        assert [x.get_text() for x in legend.get_texts()] == ["pic (1.6 s)"]
        plt.close(result.fig)

    @pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
    def test_3d_mp4_streams_with_orbit_and_true_proportions(self, tmp_path):
        t = np.linspace(0, 10, 100)
        seen = []
        result = animate_path(t, 100 * t, 10 * np.ones_like(t) * t, 500 * t - 25 * t**2,
                              path=tmp_path / "p.mp4", duration=1.0, equal=True, orbit=30.0,
                              view=(20.0, -60.0), on_frame=lambda i, tn, ax: seen.append(ax.azim),
                              close_fig=False, **FAST)
        assert result.backend == "ffmpeg-stream"
        assert seen[0] == pytest.approx(-60.0) and seen[-1] == pytest.approx(-30.0)
        aspect = np.asarray(result.axes.get_box_aspect())
        assert aspect[2] > aspect[0] > aspect[1]
        plt.close(result.fig)

    def test_event_colours_survive_leaving_the_style(self, tmp_path):
        t = np.linspace(0, 10, 50)
        result = animate_path(t, t, t, path=tmp_path / "c.gif", duration=0.5, events={"a": 2.0},
                              profile="paper", close_fig=False, **FAST)
        marker = result.axes.get_legend().legend_handles[0]
        assert to_hex(marker.get_color()) == marker.get_color()
        plt.close(result.fig)
