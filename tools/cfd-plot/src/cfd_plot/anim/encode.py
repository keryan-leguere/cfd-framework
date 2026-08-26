"""
encode — turn a sequence of rendered frames into a GIF or an MP4.

This is the bottom layer of ``cfd_plot.anim``: it knows nothing about
Matplotlib.  Give it PNG files (or arrays, or PIL images) and it gives you a
well-encoded animation.

Why this is not a two-line wrapper around ``PIL.Image.save``
-----------------------------------------------------------
A GIF carries **at most 256 colours**, and the naive encoders pick those 256
colours *independently for every frame*.  On a Matplotlib figure that means the
anti-aliased greys of the axes, the text and the line colours land on slightly
different palette entries each frame, and the animation visibly boils.  On a
colour-mapped field it is worse: the colormap itself shifts.

Both backends here therefore build **one palette for the whole sequence** and
reuse it for every frame:

* ``ffmpeg`` — the good path.  Two passes, ``palettegen`` over the entire
  sequence then ``paletteuse``.  Also the only path to MP4.
* ``Pillow`` — the fallback, so the package still works with no external
  binary.  Builds a global palette from a sampled montage of the frames and
  quantises every frame against it.  Bigger files, same stability.

GIF timing is quantised to 10 ms by the format itself, so a frame rate that
does not divide 100 is silently rounded by every viewer.  The shipped presets
use 10, 20 and 25 fps for that reason — see :data:`PRESETS`.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_PRESET",
    "PRESETS",
    "AnimPreset",
    "build_sequence",
    "ffmpeg_available",
    "frames_to_gif",
    "frames_to_mp4",
    "resolve_preset",
]


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnimPreset:
    """A named bundle of "what should this animation look like" defaults.

    Attributes
    ----------
    name : str
        Preset name, echoed back in :class:`~cfd_plot.anim.engine.AnimationResult`.
    width_px : int
        Output width in pixels.  The height follows from the figure aspect
        ratio; the render DPI is derived from this, *not* from the style
        profile (``slides.mplstyle`` asks for 600 dpi, which on a 12-inch
        figure would be a 7200 px animation).
    fps : int
        Frames per second.  Chosen among the divisors of 100 so the GIF frame
        delay is exact — see the module docstring.
    max_colors : int
        Palette size, 2-256.  Lowering it shrinks the file and is usually
        invisible on line plots, which rarely use more than a few dozen
        distinct colours once anti-aliasing is accounted for.
    dither : str
        ``ffmpeg`` dither mode (``"sierra2_4a"``, ``"bayer"``, ``"none"``, …).
        The Pillow fallback understands only "some dithering" vs "none".
    hold_first, hold_last : float
        Seconds to freeze on the first / last frame.  ``hold_last`` matters:
        without it the final state of a convergence or a sweep flashes past in
        one frame time and the loop restarts before the eye lands on it.
    """

    name: str
    width_px: int
    fps: int
    max_colors: int
    dither: str
    hold_first: float
    hold_last: float


PRESETS: dict[str, AnimPreset] = {
    # Projected or pasted into slides: big enough to read from the back of a
    # room, slow enough to follow, and it lingers on the final state.
    "slides": AnimPreset("slides", width_px=1280, fps=20, max_colors=256, dither="sierra2_4a", hold_first=0.0, hold_last=1.0),
    # Inline in a README or a chat message: GitHub stops rendering images
    # inline past ~10 MB, so this preset trades resolution for weight.
    "readme": AnimPreset("readme", width_px=800, fps=10, max_colors=128, dither="sierra2_4a", hold_first=0.0, hold_last=1.0),
    # A written report or a high-DPI screen; file size unconstrained.
    "report": AnimPreset("report", width_px=1600, fps=25, max_colors=256, dither="sierra2_4a", hold_first=0.0, hold_last=1.5),
}

DEFAULT_PRESET = "slides"


def resolve_preset(preset: str | AnimPreset | None) -> AnimPreset:
    """Return the :class:`AnimPreset` named by *preset* (or *preset* itself)."""
    if preset is None:
        preset = DEFAULT_PRESET
    if isinstance(preset, AnimPreset):
        return preset
    try:
        return PRESETS[preset]
    except KeyError:
        raise ValueError(f"unknown preset {preset!r} — choose from {sorted(PRESETS)} or pass an AnimPreset") from None


# ---------------------------------------------------------------------------
# Frame sequencing (holds, boomerang)
# ---------------------------------------------------------------------------


def build_sequence(
    frames: Sequence[Path],
    *,
    fps: int,
    hold_first: float = 0.0,
    hold_last: float = 0.0,
    boomerang: bool = False,
) -> list[Path]:
    """Expand *frames* into the exact list of images to encode, in order.

    Holds are expressed by **repeating a frame**, not by per-frame delays.
    A repeated identical frame costs almost nothing in either container (GIF
    inter-frame compression and H.264 both collapse it to a near-empty delta),
    and it keeps the encoders on a single constant frame rate — variable delays
    are where GIF writers disagree with each other and with browsers.

    What the two backends then write out differs, harmlessly: ffmpeg keeps the
    repeats, while Pillow merges consecutive identical frames and rolls their
    delay into the survivor. Playback time is identical either way, which is
    the contract; the frame count is not.

    The holds are applied *before* the mirror, so a boomerang lingers at its
    turning point as well as at its ends.
    """
    if not frames:
        raise ValueError("no frames to encode — was capture() ever called?")

    seq = list(frames)
    seq = [seq[0]] * round(hold_first * fps) + seq + [seq[-1]] * round(hold_last * fps)

    if boomerang and len(seq) > 2:
        # Drop both endpoints from the reversed half: they are already the
        # last and first images of the forward half, and repeating them reads
        # as a stutter at each turn.
        seq = seq + seq[-2:0:-1]

    return seq


# ---------------------------------------------------------------------------
# Frame input normalisation
# ---------------------------------------------------------------------------

FrameInput = Iterable[Any]  # paths, str, np.ndarray (H, W, 3|4) or PIL.Image


def _materialise(frames: FrameInput, workdir: Path) -> list[Path]:
    """Return *frames* as PNG files on disk, writing any in-memory ones."""
    out: list[Path] = []
    for i, frame in enumerate(frames):
        if isinstance(frame, (str, os.PathLike)):
            path = Path(frame)
            if not path.is_file():
                raise FileNotFoundError(f"frame {i} does not exist: {path}")
            out.append(path)
            continue

        if isinstance(frame, np.ndarray):
            arr = frame
            if arr.dtype != np.uint8:
                # Accept the float 0-1 convention Matplotlib uses elsewhere.
                arr = (np.clip(arr, 0.0, 1.0) * 255).round().astype(np.uint8)
            img = Image.fromarray(arr).convert("RGB")
        elif isinstance(frame, Image.Image):
            img = frame.convert("RGB")
        else:
            raise TypeError(f"frame {i}: expected a path, a NumPy array or a PIL image, got {type(frame).__name__}")

        path = workdir / f"mem_{i:06d}.png"
        img.save(path)
        out.append(path)

    if not out:
        raise ValueError("no frames to encode")
    return out


def _numbered_input_dir(sequence: Sequence[Path], workdir: Path) -> Path:
    """Link *sequence* into a ``f_%06d.png`` directory for ffmpeg's image2 demuxer.

    The caller's frames may live anywhere and repeat (holds, boomerang), which
    no ffmpeg input pattern can express.  Hard-linking them into a contiguously
    numbered directory does, and costs no disk space; a copy is the fallback
    for filesystems that refuse the link.
    """
    link_dir = workdir / "seq"
    link_dir.mkdir(exist_ok=True)
    for i, src in enumerate(sequence):
        dst = link_dir / f"f_{i:06d}.png"
        try:
            os.link(src, dst)
        except OSError:
            shutil.copyfile(src, dst)
    return link_dir


# ---------------------------------------------------------------------------
# ffmpeg backend
# ---------------------------------------------------------------------------


def ffmpeg_available() -> bool:
    """``True`` if an ``ffmpeg`` binary is on ``PATH``."""
    return shutil.which("ffmpeg") is not None


def _run_ffmpeg(args: list[str], *, what: str) -> None:
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *args]
    logger.debug("ffmpeg: %s", " ".join(cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed while {what} (exit {proc.returncode}):\n{proc.stderr.strip()}")


def _ffmpeg_gif(
    link_dir: Path,
    out: Path,
    *,
    fps: int,
    max_colors: int,
    dither: str,
    loop: int,
) -> None:
    palette = link_dir.parent / "palette.png"
    pattern = str(link_dir / "f_%06d.png")

    # Pass 1 — one palette for the whole sequence. stats_mode=full weights
    # every frame equally; the alternative (`diff`) optimises for what changes
    # between frames, which on a mostly-static figure spends the palette on
    # the moving curve and quantises the axes badly.
    _run_ffmpeg(
        ["-framerate", str(fps), "-i", pattern, "-vf", f"palettegen=stats_mode=full:max_colors={max_colors}", str(palette)],
        what="building the palette",
    )

    # Pass 2 — apply it. new=0 keeps the single global palette rather than
    # re-deriving one per frame, which is the whole point.
    _run_ffmpeg(
        [
            "-framerate", str(fps),
            "-i", pattern,
            "-i", str(palette),
            "-lavfi", f"paletteuse=dither={dither}:new=0",
            "-loop", str(loop),
            "-f", "gif",
            str(out),
        ],
        what="encoding the GIF",
    )


def _ffmpeg_mp4(link_dir: Path, out: Path, *, fps: int, crf: int) -> None:
    pattern = str(link_dir / "f_%06d.png")
    _run_ffmpeg(
        [
            "-framerate", str(fps),
            "-i", pattern,
            # yuv420p is what every player and every browser can decode, and
            # it requires even dimensions — hence the trunc() scale, which is
            # a no-op when the render is already even.
            "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2:flags=lanczos,format=yuv420p",
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", "slow",
            "-movflags", "+faststart",
            str(out),
        ],
        what="encoding the MP4",
    )


# ---------------------------------------------------------------------------
# Pillow backend
# ---------------------------------------------------------------------------

_PALETTE_SAMPLE_FRAMES = 24
_PALETTE_SAMPLE_WIDTH = 320


def _global_palette(sequence: Sequence[Path], max_colors: int) -> Image.Image:
    """Derive one palette image representative of the whole *sequence*.

    Stacking every frame full-size would be hundreds of megabytes for a long
    animation, so this samples evenly through the sequence and downscales.
    Quantisation only needs the *distribution* of colours, which survives both.
    """
    idx = np.unique(np.linspace(0, len(sequence) - 1, min(_PALETTE_SAMPLE_FRAMES, len(sequence))).round().astype(int))
    tiles = []
    for i in idx:
        img = Image.open(sequence[i]).convert("RGB")
        if img.width > _PALETTE_SAMPLE_WIDTH:
            scale = _PALETTE_SAMPLE_WIDTH / img.width
            img = img.resize((_PALETTE_SAMPLE_WIDTH, max(1, round(img.height * scale))), Image.Resampling.BILINEAR)
        tiles.append(np.asarray(img))

    montage = Image.fromarray(np.concatenate(tiles, axis=0))
    return montage.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)


def _pillow_gif(
    sequence: Sequence[Path],
    out: Path,
    *,
    fps: int,
    max_colors: int,
    dither: str,
    loop: int,
) -> None:
    palette = _global_palette(sequence, max_colors)
    dither_mode = Image.Dither.NONE if dither in ("none", "", "false") else Image.Dither.FLOYDSTEINBERG

    def quantised(path: Path) -> Image.Image:
        return Image.open(path).convert("RGB").quantize(palette=palette, dither=dither_mode)

    # GIF delays are stored in centiseconds; round rather than truncate so a
    # 15 fps request lands on 70 ms instead of 60 ms.
    delay_ms = max(20, round(1000 / fps / 10) * 10)

    first = quantised(sequence[0])
    first.save(
        out,
        save_all=True,
        append_images=(quantised(p) for p in sequence[1:]),
        duration=delay_ms,
        loop=loop,
        # optimize=True lets Pillow rewrite per-frame palettes, undoing the
        # global palette we just built. Stability beats a few kilobytes.
        optimize=False,
        disposal=1,
    )


# ---------------------------------------------------------------------------
# Public encoders
# ---------------------------------------------------------------------------


def frames_to_gif(
    frames: FrameInput,
    path: str | Path,
    *,
    preset: str | AnimPreset | None = None,
    fps: int | None = None,
    max_colors: int | None = None,
    dither: str | None = None,
    hold_first: float | None = None,
    hold_last: float | None = None,
    boomerang: bool = False,
    loop: int = 0,
    backend: str = "auto",
) -> Path:
    """Encode *frames* into an animated GIF at *path*.

    Parameters
    ----------
    frames : iterable
        PNG paths, ``(H, W, 3|4)`` uint8 arrays, or PIL images — mixed freely.
    path : str or Path
        Output file.  A ``.gif`` suffix is added if missing.
    preset : str or AnimPreset, optional
        ``"slides"`` (default), ``"readme"`` or ``"report"``; see :data:`PRESETS`.
    fps, max_colors, dither, hold_first, hold_last
        Override the corresponding preset field.
    boomerang : bool
        Play the sequence forwards then backwards, so the loop does not snap
        back to the start.  Doubles the frame count.
    loop : int
        ``0`` (default) loops forever; ``n`` plays the sequence ``n`` times.
    backend : ``"auto"`` | ``"ffmpeg"`` | ``"pillow"``
        ``"auto"`` uses ffmpeg when it is installed.  ``"ffmpeg"`` raises if it
        is not.

    Returns
    -------
    Path
        The file that was written.
    """
    spec = resolve_preset(preset)
    fps = int(fps if fps is not None else spec.fps)
    max_colors = int(max_colors if max_colors is not None else spec.max_colors)
    dither = dither if dither is not None else spec.dither
    hold_first = spec.hold_first if hold_first is None else hold_first
    hold_last = spec.hold_last if hold_last is None else hold_last

    if fps <= 0:
        raise ValueError(f"fps must be positive, got {fps}")
    if not 2 <= max_colors <= 256:
        raise ValueError(f"max_colors must be between 2 and 256, got {max_colors}")

    out = Path(path)
    if out.suffix.lower() != ".gif":
        out = out.with_suffix(".gif")
    out.parent.mkdir(parents=True, exist_ok=True)

    use_ffmpeg = _choose_backend(backend)

    with tempfile.TemporaryDirectory(prefix="cfd_plot_gif_") as tmp:
        workdir = Path(tmp)
        materialised = _materialise(frames, workdir)
        sequence = build_sequence(materialised, fps=fps, hold_first=hold_first, hold_last=hold_last, boomerang=boomerang)

        if use_ffmpeg:
            link_dir = _numbered_input_dir(sequence, workdir)
            _ffmpeg_gif(link_dir, out, fps=fps, max_colors=max_colors, dither=dither, loop=loop)
        else:
            _pillow_gif(sequence, out, fps=fps, max_colors=max_colors, dither=dither, loop=loop)

    logger.info("wrote %s (%d frames, %.1f kB)", out, len(sequence), out.stat().st_size / 1024)
    return out


def frames_to_mp4(
    frames: FrameInput,
    path: str | Path,
    *,
    preset: str | AnimPreset | None = None,
    fps: int | None = None,
    crf: int = 18,
    hold_first: float | None = None,
    hold_last: float | None = None,
    boomerang: bool = False,
) -> Path:
    """Encode *frames* into an H.264 MP4 at *path*.  Requires ``ffmpeg``.

    MP4 has no 256-colour limit, which is what makes it the right container
    for a colour-mapped field — where it is also far smaller than the GIF,
    since GIF has to dither a continuous colormap into 256 entries and the
    dither noise defeats its compression.  On line plots the two land in the
    same ballpark: flat colours are exactly what GIF compresses well.

    It is the worse choice anywhere a still image is expected (README, chat,
    e-mail), because it will not auto-play there.

    Parameters
    ----------
    crf : int
        H.264 quality, 0 (lossless) to 51 (worst).  18 is visually lossless on
        line plots; raise it to shrink the file.
    """
    if not ffmpeg_available():
        raise RuntimeError(
            "MP4 export requires ffmpeg, which was not found on PATH. "
            "Install it (apt install ffmpeg / brew install ffmpeg) or export a GIF instead."
        )

    spec = resolve_preset(preset)
    fps = int(fps if fps is not None else spec.fps)
    hold_first = spec.hold_first if hold_first is None else hold_first
    hold_last = spec.hold_last if hold_last is None else hold_last

    if not 0 <= crf <= 51:
        raise ValueError(f"crf must be between 0 and 51, got {crf}")

    out = Path(path)
    if out.suffix.lower() != ".mp4":
        out = out.with_suffix(".mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cfd_plot_mp4_") as tmp:
        workdir = Path(tmp)
        materialised = _materialise(frames, workdir)
        sequence = build_sequence(materialised, fps=fps, hold_first=hold_first, hold_last=hold_last, boomerang=boomerang)
        link_dir = _numbered_input_dir(sequence, workdir)
        _ffmpeg_mp4(link_dir, out, fps=fps, crf=crf)

    logger.info("wrote %s (%d frames, %.1f kB)", out, len(sequence), out.stat().st_size / 1024)
    return out


def _choose_backend(backend: str) -> bool:
    """Resolve the *backend* request to "use ffmpeg" (True) or "use Pillow"."""
    if backend == "ffmpeg":
        if not ffmpeg_available():
            raise RuntimeError("backend='ffmpeg' was requested but no ffmpeg binary is on PATH")
        return True
    if backend == "pillow":
        return False
    if backend != "auto":
        raise ValueError(f"backend must be 'auto', 'ffmpeg' or 'pillow', got {backend!r}")

    if not ffmpeg_available():
        logger.info("ffmpeg not found — falling back to the Pillow GIF encoder (larger files)")
        return False
    return True
