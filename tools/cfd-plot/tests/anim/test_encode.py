"""Tests for ``cfd_plot.anim.encode`` — presets, sequencing and the two encoders."""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from cfd_plot.anim import PRESETS, AnimPreset, ffmpeg_available, frames_to_gif, frames_to_mp4
from cfd_plot.anim import encode as enc

from .conftest import BACKENDS, gif_duration_ms, gif_frame_count, gif_info, gif_palettes


class TestPresets:
    def test_resolves_by_name(self):
        assert enc.resolve_preset("readme").width_px == 800

    def test_resolves_an_instance_unchanged(self):
        custom = AnimPreset("x", 111, 7, 32, "none", 0.0, 0.0)
        assert enc.resolve_preset(custom) is custom

    def test_none_gives_the_default(self):
        assert enc.resolve_preset(None).name == enc.DEFAULT_PRESET

    def test_unknown_name_lists_the_valid_ones(self):
        with pytest.raises(ValueError, match="unknown preset"):
            enc.resolve_preset("nope")

    @pytest.mark.parametrize("name", sorted(PRESETS))
    def test_shipped_fps_divide_100(self, name):
        # GIF stores its delay in centiseconds, so any fps that does not divide
        # 100 is silently rounded by every viewer and the animation plays at a
        # rate nobody asked for. The shipped presets must not have that flaw.
        assert 100 % PRESETS[name].fps == 0

    @pytest.mark.parametrize("name", sorted(PRESETS))
    def test_shipped_presets_are_sane(self, name):
        p = PRESETS[name]
        assert p.width_px > 0
        assert 2 <= p.max_colors <= 256
        assert p.hold_last >= 0.0


class TestBuildSequence:
    def _paths(self, n):
        return [f"f{i}" for i in range(n)]

    def test_plain_sequence_is_unchanged(self):
        assert enc.build_sequence(self._paths(4), fps=10) == self._paths(4)

    def test_hold_last_repeats_the_final_frame(self):
        seq = enc.build_sequence(self._paths(3), fps=10, hold_last=0.5)
        assert len(seq) == 3 + 5
        assert seq[-5:] == ["f2"] * 5

    def test_hold_first_repeats_the_opening_frame(self):
        seq = enc.build_sequence(self._paths(3), fps=20, hold_first=0.1)
        assert seq[:2] == ["f0", "f0"]
        assert len(seq) == 5

    def test_boomerang_mirrors_without_stuttering_at_the_turns(self):
        seq = enc.build_sequence(self._paths(4), fps=10, boomerang=True)
        # 0 1 2 3 then back down 2 1 — the endpoints are not repeated, which
        # would read as a pause at each end of the swing.
        assert seq == ["f0", "f1", "f2", "f3", "f2", "f1"]

    def test_holds_are_applied_before_the_mirror(self):
        # So the boomerang lingers at its turning point too, not only at the end.
        seq = enc.build_sequence(self._paths(3), fps=10, hold_last=0.2, boomerang=True)
        assert seq[:5] == ["f0", "f1", "f2", "f2", "f2"]
        assert seq[-1] == "f1"

    def test_empty_input_says_what_to_do(self):
        with pytest.raises(ValueError, match="capture"):
            enc.build_sequence([], fps=10)


class TestGifEncoding:
    @pytest.mark.parametrize("backend", BACKENDS)
    def test_writes_one_frame_per_input(self, frame_files, tmp_path, backend):
        out = frames_to_gif(frame_files, tmp_path / "a.gif", backend=backend, hold_last=0.0, fps=10)
        assert gif_frame_count(out) == len(frame_files)

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_uses_a_single_palette_for_the_whole_sequence(self, frame_files, tmp_path, backend):
        # The core quality guarantee. A per-frame palette is what makes a
        # Matplotlib GIF visibly boil.
        out = frames_to_gif(frame_files, tmp_path / "a.gif", backend=backend, hold_last=0.0)
        assert len(gif_palettes(out)) == 1

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_loops_forever_by_default(self, frame_files, tmp_path, backend):
        out = frames_to_gif(frame_files, tmp_path / "a.gif", backend=backend, hold_last=0.0)
        assert gif_info(out)["loop"] == 0

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_frame_delay_follows_fps(self, frame_files, tmp_path, backend):
        out = frames_to_gif(frame_files, tmp_path / "a.gif", backend=backend, fps=20, hold_last=0.0)
        assert gif_info(out)["duration"] == pytest.approx(50, abs=10)

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_hold_last_lengthens_the_playback(self, frame_files, tmp_path, backend):
        # Asserted in milliseconds, not frames: Pillow merges the repeated
        # frames of a hold into one longer delay while ffmpeg keeps them, and
        # the playback time is the thing a hold actually promises.
        out = frames_to_gif(frame_files, tmp_path / "a.gif", fps=10, hold_last=0.5, backend=backend)
        assert gif_duration_ms(out) == pytest.approx(1000, abs=20)

    @pytest.mark.parametrize("backend", BACKENDS)
    def test_boomerang_roughly_doubles_the_playback(self, frame_files, tmp_path, backend):
        plain = frames_to_gif(frame_files, tmp_path / "p.gif", fps=10, hold_last=0.0, backend=backend)
        both_ways = frames_to_gif(frame_files, tmp_path / "b.gif", fps=10, hold_last=0.0, boomerang=True, backend=backend)
        # 5 frames out and 3 back (the endpoints are not repeated).
        assert gif_duration_ms(plain) == pytest.approx(500, abs=20)
        assert gif_duration_ms(both_ways) == pytest.approx(800, abs=20)

    @pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
    def test_ffmpeg_holds_by_repeating_frames(self, frame_files, tmp_path):
        # The representation, where it is guaranteed. Pillow reaches the same
        # playback time by a different route, so this is ffmpeg-only.
        out = frames_to_gif(frame_files, tmp_path / "a.gif", fps=10, hold_last=0.5, backend="ffmpeg")
        assert gif_frame_count(out) == len(frame_files) + 5

    def test_suffix_is_added_when_missing(self, frame_files, tmp_path):
        out = frames_to_gif(frame_files, tmp_path / "noext", hold_last=0.0)
        assert out.name == "noext.gif"
        assert out.is_file()

    def test_parent_directories_are_created(self, frame_files, tmp_path):
        out = frames_to_gif(frame_files, tmp_path / "deep" / "er" / "a.gif", hold_last=0.0)
        assert out.is_file()

    def test_max_colors_is_honoured(self, frame_files, tmp_path):
        out = frames_to_gif(frame_files, tmp_path / "a.gif", max_colors=8, hold_last=0.0, backend="pillow")
        assert len(gif_palettes(out)[0]) // 3 <= 8


class TestFrameInputTypes:
    def test_accepts_numpy_uint8_arrays(self, tmp_path):
        frames = [np.full((16, 24, 3), 20 * i, dtype=np.uint8) for i in range(4)]
        out = frames_to_gif(frames, tmp_path / "a.gif", hold_last=0.0)
        assert gif_frame_count(out) == 4

    def test_accepts_float_arrays_on_the_matplotlib_0_1_convention(self, tmp_path):
        frames = [np.full((16, 24, 3), 0.25 * i, dtype=float) for i in range(4)]
        out = frames_to_gif(frames, tmp_path / "a.gif", hold_last=0.0)
        assert gif_frame_count(out) == 4

    def test_accepts_pil_images(self, tmp_path):
        frames = [Image.new("RGB", (24, 16), (i * 50, 0, 0)) for i in range(4)]
        out = frames_to_gif(frames, tmp_path / "a.gif", hold_last=0.0)
        assert gif_frame_count(out) == 4

    def test_accepts_a_mixture(self, tmp_path, frame_files):
        # The three must differ: Pillow drops a frame identical to the one
        # before it, and `Image.new("RGB", ...)` defaults to black — the same
        # thing np.zeros produces.
        mixed = [
            frame_files[0],
            np.full((30, 40, 3), 90, np.uint8),
            Image.new("RGB", (40, 30), (200, 10, 10)),
        ]
        out = frames_to_gif(mixed, tmp_path / "a.gif", hold_last=0.0)
        assert gif_frame_count(out) == 3

    def test_a_missing_file_names_itself(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="frame 1"):
            frames_to_gif([Image.new("RGB", (8, 8)), tmp_path / "ghost.png"], tmp_path / "a.gif")

    def test_an_unusable_frame_names_its_type(self, tmp_path):
        with pytest.raises(TypeError, match="frame 0"):
            frames_to_gif([object()], tmp_path / "a.gif")

    def test_no_frames_at_all(self, tmp_path):
        with pytest.raises(ValueError, match="no frames"):
            frames_to_gif([], tmp_path / "a.gif")


class TestValidation:
    def test_rejects_non_positive_fps(self, frame_files, tmp_path):
        with pytest.raises(ValueError, match="fps must be positive"):
            frames_to_gif(frame_files, tmp_path / "a.gif", fps=0)

    @pytest.mark.parametrize("colors", [1, 257])
    def test_rejects_impossible_palette_sizes(self, frame_files, tmp_path, colors):
        with pytest.raises(ValueError, match="max_colors"):
            frames_to_gif(frame_files, tmp_path / "a.gif", max_colors=colors)

    def test_rejects_an_unknown_backend(self, frame_files, tmp_path):
        with pytest.raises(ValueError, match="backend must be"):
            frames_to_gif(frame_files, tmp_path / "a.gif", backend="imagemagick")

    def test_rejects_an_out_of_range_crf(self, frame_files, tmp_path):
        if not ffmpeg_available():
            pytest.skip("ffmpeg not installed")
        with pytest.raises(ValueError, match="crf"):
            frames_to_mp4(frame_files, tmp_path / "a.mp4", crf=99)


class TestBackendSelection:
    def test_auto_falls_back_to_pillow_without_ffmpeg(self, frame_files, tmp_path, monkeypatch):
        monkeypatch.setattr(enc, "ffmpeg_available", lambda: False)
        out = frames_to_gif(frame_files, tmp_path / "a.gif", hold_last=0.0)
        assert out.is_file()
        assert len(gif_palettes(out)) == 1

    def test_explicit_ffmpeg_refuses_to_fall_back_silently(self, frame_files, tmp_path, monkeypatch):
        monkeypatch.setattr(enc, "ffmpeg_available", lambda: False)
        with pytest.raises(RuntimeError, match="no ffmpeg binary"):
            frames_to_gif(frame_files, tmp_path / "a.gif", backend="ffmpeg")

    @pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
    def test_a_failing_ffmpeg_surfaces_its_own_message(self, frame_files, tmp_path):
        # A bad filter argument is the realistic failure mode; the point is that
        # ffmpeg's stderr reaches the caller instead of an empty output file.
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            frames_to_gif(frame_files, tmp_path / "a.gif", dither="not-a-dither", backend="ffmpeg")


class TestMp4:
    def test_requires_ffmpeg_and_says_how_to_get_it(self, frame_files, tmp_path, monkeypatch):
        monkeypatch.setattr(enc, "ffmpeg_available", lambda: False)
        with pytest.raises(RuntimeError, match="apt install ffmpeg"):
            frames_to_mp4(frame_files, tmp_path / "a.mp4")

    @pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
    def test_writes_a_playable_file(self, frame_files, tmp_path):
        out = frames_to_mp4(frame_files, tmp_path / "a.mp4", hold_last=0.0)
        assert out.is_file()
        assert out.stat().st_size > 0
        assert out.read_bytes()[4:8] == b"ftyp"  # ISO base media container signature

    @pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
    def test_odd_sized_frames_are_padded_to_an_even_size(self, tmp_path):
        # yuv420p, which is what every player can decode, requires even
        # dimensions; an odd render must not simply fail to encode.
        frames = [np.full((31, 41, 3), 30 * i, dtype=np.uint8) for i in range(4)]
        out = frames_to_mp4(frames, tmp_path / "a.mp4", hold_last=0.0)
        assert out.stat().st_size > 0

    @pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")
    def test_suffix_is_added_when_missing(self, frame_files, tmp_path):
        assert frames_to_mp4(frame_files, tmp_path / "noext", hold_last=0.0).name == "noext.mp4"
