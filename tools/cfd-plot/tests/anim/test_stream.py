"""Streaming MP4: frames piped into ffmpeg, no PNG on disk."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import numpy as np
import pytest

from cfd_plot.anim import Mp4Stream, animate, encode, ffmpeg_available, ffmpeg_executable

from .conftest import FAST

needs_ffmpeg = pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")


def _probe(path: Path) -> tuple[int, int, int]:
    """(width, height, frame count) of an MP4, decoded by ffmpeg (no ffprobe needed)."""
    out = subprocess.run([ffmpeg_executable(), "-hide_banner", "-i", str(path), "-map", "0:v:0",
                          "-f", "null", "-"], capture_output=True, text=True)
    text = out.stderr
    w, h = map(int, re.search(r", (\d+)x(\d+)", text).groups())
    frames = int(re.findall(r"frame=\s*(\d+)", text)[-1])
    return w, h, frames


class TestFfmpegLookup:
    def test_env_variable_wins(self, tmp_path, monkeypatch):
        fake = tmp_path / "my-ffmpeg"
        fake.write_text("#!/bin/sh\n")
        fake.chmod(0o755)
        monkeypatch.setenv(encode.ENV_FFMPEG, str(fake))
        assert ffmpeg_executable() == str(fake)

    def test_env_variable_naming_nothing_finds_nothing(self, monkeypatch):
        monkeypatch.setenv(encode.ENV_FFMPEG, "no-such-ffmpeg-binary")
        assert ffmpeg_executable() is None

    def test_falls_back_to_imageio_ffmpeg(self, monkeypatch):
        imageio_ffmpeg = pytest.importorskip("imageio_ffmpeg")
        monkeypatch.delenv(encode.ENV_FFMPEG, raising=False)
        monkeypatch.setattr(encode.shutil, "which", lambda name: None)
        assert ffmpeg_executable() == imageio_ffmpeg.get_ffmpeg_exe()


@needs_ffmpeg
class TestMp4Stream:
    def test_frames_and_size(self, tmp_path):
        with Mp4Stream(tmp_path / "s.mp4", width=64, height=48, fps=10) as s:
            for i in range(5):
                frame = np.zeros((48, 64, 4), dtype=np.uint8)
                frame[..., 3] = 255
                frame[:, i * 10:(i * 10) + 8, 0] = 255
                s.write(frame.tobytes(), repeat=2)
        assert s.n_frames == 10
        assert _probe(tmp_path / "s.mp4") == (64, 48, 10)

    def test_odd_size_is_made_even(self, tmp_path):
        with Mp4Stream(tmp_path / "o.mp4", width=65, height=49, fps=10) as s:
            s.write(bytes(65 * 49 * 4), repeat=3)
        assert _probe(tmp_path / "o.mp4")[:2] == (64, 48)

    def test_wrong_frame_size_is_named(self, tmp_path):
        s = Mp4Stream(tmp_path / "w.mp4", width=8, height=8, fps=10)
        with pytest.raises(ValueError, match="resized mid-capture"):
            s.write(bytes(10))
        s.abort()
        assert not (tmp_path / "w.mp4").exists()

    def test_error_inside_block_leaves_no_file(self, tmp_path):
        with pytest.raises(KeyError), Mp4Stream(tmp_path / "x.mp4", width=8, height=8, fps=10) as s:
            s.write(bytes(8 * 8 * 4))
            raise KeyError("boom")
        assert not (tmp_path / "x.mp4").exists()


@needs_ffmpeg
class TestAnimatorStreams:
    def _run(self, fig, line, path, **kw):
        with animate(fig, path, **{**FAST, **kw}) as anim:
            for i in range(4):
                line.set_data([0, (i + 1) / 4], [0, (i + 1) / 4])
                anim.capture(hold=0.2 if i == 1 else 0.0)
        return anim.result

    def test_mp4_only_streams_and_writes_no_png(self, tiny_fig, tmp_path, monkeypatch):
        fig, _, line = tiny_fig
        written = []
        real = fig.savefig
        monkeypatch.setattr(fig, "savefig", lambda f, **kw: (written.append(kw.get("format")), real(f, **kw)))
        result = self._run(fig, line, tmp_path / "a.mp4", hold_first=0.3, hold_last=0.5)
        assert result.backend == "ffmpeg-stream" and result.frames_dir is None
        assert set(written) == {"rgba"}
        # 4 captures + 2 held (0.2 s at 10 fps) + 3 first + 5 last.
        assert result.n_frames == 14 and result.n_captures == 4
        assert _probe(result.paths[0])[2] == 14
        assert not list(tmp_path.glob("*.png"))

    def test_same_size_as_file_path(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        streamed = self._run(fig, line, tmp_path / "s.mp4")
        filed = self._run(fig, line, tmp_path / "f.mp4", stream=False)
        assert filed.backend != "ffmpeg-stream"
        assert streamed.size_px == filed.size_px
        assert _probe(streamed.paths[0]) == _probe(filed.paths[0])

    def test_gif_and_boomerang_cannot_stream(self, tiny_fig, tmp_path):
        fig, _, _ = tiny_fig
        with pytest.raises(ValueError, match="stream=True"):
            animate(fig, tmp_path / "a.gif", stream=True).__enter__()
        with pytest.raises(ValueError, match="stream=True"):
            animate(fig, tmp_path / "a.mp4", stream=True, boomerang=True).__enter__()

    def test_failure_in_loop_leaves_no_file(self, tiny_fig, tmp_path):
        fig, _, line = tiny_fig
        with pytest.raises(ZeroDivisionError), animate(fig, tmp_path / "z.mp4", **FAST) as anim:
            anim.capture()
            raise ZeroDivisionError
        assert not (tmp_path / "z.mp4").exists()

    def test_resize_mid_capture_is_caught(self, tiny_fig, tmp_path):
        fig, _, _ = tiny_fig
        with pytest.raises(RuntimeError, match="resized"), animate(fig, tmp_path / "r.mp4", **FAST) as anim:
            anim.capture()
            fig.set_size_inches(4, 3)
            anim.capture()
