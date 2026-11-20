"""
stream — encode an MP4 while the frames are being drawn, with no PNG on disk.

The file path of :mod:`cfd_plot.anim.engine` writes one PNG per frame and
encodes them all at the end. That is the right shape for a GIF, which needs the
whole sequence to build its palette, and for a boomerang, which plays the
sequence twice. It is the wrong shape for a long MP4: a 60-second video at
30 fps is 1 800 PNGs compressed by zlib, written, read back and decompressed by
ffmpeg — most of the time goes into a round-trip whose only purpose is to be
undone.

Here each frame is rendered by Agg straight to raw RGBA (``savefig(format=
"rgba")``) and written to ffmpeg's standard input. Same encoder, same filter
(:data:`~cfd_plot.anim.encode.MP4_VIDEO_FILTER`) and therefore the same output
as the file path; only the PNG detour is gone.

ffmpeg's ``stderr`` goes to a temporary file rather than a pipe: nobody reads a
pipe while frames are being written, and once its buffer fills ffmpeg blocks,
then so does our ``write`` — a deadlock that shows up only on long videos.
"""

from __future__ import annotations

import contextlib
import subprocess
import tempfile
from pathlib import Path
from typing import IO

from .encode import MP4_VIDEO_FILTER, _ffmpeg

__all__ = ["Mp4Stream"]


class Mp4Stream:
    """An H.264 MP4 fed one raw RGBA frame at a time.

    Parameters
    ----------
    path : str or Path
        Output file; the suffix is forced to ``.mp4``.
    width, height : int
        Size of every frame in pixels.
    fps : int
    crf : int
        H.264 quality, 0 (lossless) to 51.
    speed : str
        x264 preset. ``"medium"`` rather than the file path's ``"slow"``:
        a long video is where encoding time is felt, and on flat-coloured
        figures the size difference is a few percent.

    Use as a context manager, or call :meth:`close` (success) / :meth:`abort`
    (failure) yourself.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        width: int,
        height: int,
        fps: int,
        crf: int = 18,
        speed: str = "medium",
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError(f"frame size must be positive, got {width}x{height}")
        if fps <= 0:
            raise ValueError(f"fps must be positive, got {fps}")
        if not 0 <= crf <= 51:
            raise ValueError(f"crf must be between 0 and 51, got {crf}")
        out = Path(path)
        if out.suffix.lower() != ".mp4":
            out = out.with_suffix(".mp4")
        out.parent.mkdir(parents=True, exist_ok=True)
        self.path = out
        self.width, self.height, self.fps = int(width), int(height), int(fps)
        self.n_frames = 0
        self._frame_bytes = self.width * self.height * 4
        # Closed in _finish/abort, not in a with block: it must outlive this method.
        self._log: IO[bytes] = tempfile.TemporaryFile(prefix="cfd_plot_ffmpeg_")  # noqa: SIM115
        cmd = [
            _ffmpeg(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "rawvideo", "-pix_fmt", "rgba",
            "-s", f"{self.width}x{self.height}", "-framerate", str(self.fps),
            "-i", "-",
            "-vf", MP4_VIDEO_FILTER,
            "-c:v", "libx264", "-crf", str(crf), "-preset", speed,
            "-movflags", "+faststart",
            str(out),
        ]
        self._proc: subprocess.Popen[bytes] | None = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self._log
        )

    def write(self, rgba: bytes | memoryview, repeat: int = 1) -> None:
        """Append *rgba* (``width × height × 4`` bytes) *repeat* times."""
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("this stream is closed")
        if len(rgba) != self._frame_bytes:
            raise ValueError(
                f"frame is {len(rgba)} bytes, expected {self._frame_bytes} "
                f"({self.width}x{self.height} RGBA) — was the figure resized mid-capture?"
            )
        try:
            for _ in range(repeat):
                self._proc.stdin.write(rgba)
        except BrokenPipeError:
            # ffmpeg died; close() reports why, from its log.
            self._finish(expect_success=True)
        self.n_frames += repeat

    def close(self) -> Path:
        """Finish the file; raises with ffmpeg's own message if it failed."""
        self._finish(expect_success=True)
        return self.path

    def abort(self) -> None:
        """Stop ffmpeg and delete the partial file."""
        if self._proc is not None:
            self._proc.kill()
            self._proc.wait()
            self._proc = None
        self._log.close()
        self.path.unlink(missing_ok=True)

    def _finish(self, *, expect_success: bool) -> None:
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        if proc.stdin is not None:
            with contextlib.suppress(BrokenPipeError):
                proc.stdin.close()
        code = proc.wait()
        self._log.seek(0)
        message = self._log.read().decode("utf-8", errors="replace").strip()
        self._log.close()
        if expect_success and code != 0:
            self.path.unlink(missing_ok=True)
            raise RuntimeError(f"ffmpeg failed while streaming the MP4 (exit {code}):\n{message}")

    def __enter__(self) -> Mp4Stream:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None:
            self.abort()
        else:
            self.close()
