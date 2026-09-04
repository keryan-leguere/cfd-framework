"""
engine — drive a Matplotlib figure frame by frame and encode the result.

Usage::

    fig, ax = new_figure()
    line = plot_line(ax, [], [], marker="")
    ax.set(xlim=(0, 10), ylim=(-1, 1))          # lock the axes *before* capturing

    with animate(fig, "wave.gif", preset="slides") as anim:
        for t in times:
            line.set_data(x, np.sin(x - t))
            set_title(ax, f"t = {t:.2f} s")
            anim.capture()

What the engine does that a hand-rolled ``savefig`` loop does not
----------------------------------------------------------------
* **Defeats ``bbox_inches="tight"``.**  All three cfd_plot style profiles set
  ``savefig.bbox: tight``, which re-crops the figure to its ink on every save.
  Adding a suptitle or growing a tick label from ``9`` to ``10`` then changes
  the output size, and the animation shakes — or the encoder refuses it
  outright.  Note that ``savefig(bbox_inches=None)`` does *not* disable this:
  ``None`` means "use the rcParam".  Frames are rendered inside an
  ``rc_context`` that sets ``savefig.bbox`` to ``None`` for real.
* **Freezes the layout engine.**  ``constrained_layout`` is on in every
  profile.  Left running, it nudges the axes whenever the title or the tick
  labels change width, producing the same shake one level down.  It is run once
  for the first frame, then switched off so every later frame inherits those
  exact positions.
* **Sizes from pixels, not from the style DPI.**  ``slides.mplstyle`` asks for
  600 dpi, which on its 12-inch figure is a 7200 px animation.  The render DPI
  is derived from the preset's ``width_px`` instead.
* **Forces an opaque background.**  A transparent PNG quantised into a GIF
  palette leaves grey fringes around every glyph.
* **Guards the figure size.**  Resizing the figure mid-capture silently
  produces frames of different pixel sizes, which the encoders reject much
  later with an unhelpful message; it is caught at ``capture()`` instead.

The global Matplotlib backend is never touched — frames go through
``fig.savefig``, which picks its own renderer for PNG regardless of the
interactive backend in use.  Animating from Spyder or Jupyter leaves the
session's plotting exactly as it was.
"""

from __future__ import annotations

import logging
import sys
import tempfile
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib as mpl
from matplotlib.colors import to_rgba
from matplotlib.figure import Figure
from PIL import Image

from .._compat import figure_disable_layout
from ..mpl_template import print_file_report
from .encode import AnimPreset, _choose_backend, build_sequence, frames_to_gif, frames_to_mp4, resolve_preset

logger = logging.getLogger(__name__)

__all__ = ["AnimationResult", "Animator", "animate", "animate_frames"]

_KNOWN_FORMATS = ("gif", "mp4")


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnimationResult:
    """What an animation run produced.

    Attributes
    ----------
    paths : list of Path
        The animation files written, in the order the formats were requested.
    n_frames : int
        Frames actually encoded, i.e. *after* holds and boomerang expansion.
        Use :attr:`n_captures` for the number of ``capture()`` calls.
    n_captures : int
        Distinct frames rendered from the figure.
    fps : int
    size_px : tuple of int
        ``(width, height)`` of every frame.
    preset : str
    backend : str
        ``"ffmpeg"`` or ``"pillow"`` — which encoder produced the GIF.
    frames_dir : Path or None
        Where the individual PNG frames were kept, if ``keep_frames`` was set.
    fig, axes
        Only populated when the caller asked not to close the figure; lets a
        one-liner hand back the figure for further tweaking.
    """

    paths: list[Path]
    n_frames: int
    n_captures: int
    fps: int
    size_px: tuple[int, int]
    preset: str
    backend: str
    frames_dir: Path | None = None
    fig: Figure | None = field(default=None, repr=False)
    axes: Any = field(default=None, repr=False)

    @property
    def duration_s(self) -> float:
        """Playback duration of one loop, in seconds."""
        return self.n_frames / self.fps

    @property
    def total_bytes(self) -> int:
        """Combined size on disk of every file written."""
        return sum(p.stat().st_size for p in self.paths)

    def __str__(self) -> str:
        names = ", ".join(p.name for p in self.paths)
        w, h = self.size_px
        return (
            f"{names} — {self.n_frames} frames at {self.fps} fps "
            f"({self.duration_s:.1f} s), {w}x{h} px, {self.total_bytes / 1024:.0f} kB"
        )

    def report(self) -> None:
        """Print the same table :func:`cfd_plot.save_figure` prints."""
        print_file_report(self.paths, title="Animation")


# ---------------------------------------------------------------------------
# Animator
# ---------------------------------------------------------------------------


class Animator:
    """Collects frames from a figure, then encodes them.

    Prefer the :func:`animate` context manager; instantiate this directly only
    when the capture loop cannot be wrapped in a ``with`` block, in which case
    you are responsible for calling :meth:`close`.

    Parameters
    ----------
    fig : Figure
        The figure to photograph.  Mutate its artists between captures.
    path : str or Path
        Output path.  A recognised suffix (``.gif``, ``.mp4``) selects the
        format; otherwise pass *formats* explicitly.
    formats : sequence of str, optional
        Any of ``"gif"``, ``"mp4"``.  Defaults to the suffix of *path*, or
        ``("gif",)``.
    preset : str or AnimPreset
        ``"slides"`` (default), ``"readme"`` or ``"report"``.
    fps, width_px, max_colors, dither, hold_first, hold_last
        Override individual preset fields.
    boomerang : bool
        Play forwards then backwards so the loop does not snap back.
    loop : int
        GIF loop count; ``0`` is forever.
    crf : int
        MP4 quality, 0-51 (lower is better).
    keep_frames : str or Path, optional
        Keep the individual PNG frames in this directory instead of a
        temporary one.  Useful to re-encode later without re-rendering, or to
        hand single frames to a report.
    warn_size_mb : float
        Log a warning when a written file exceeds this. ``0`` disables.
    progress : bool
        Print a one-line progress counter to stderr while capturing.
    report : bool
        Print the exported-file table on close, like ``save_figure(report=True)``.
    """

    def __init__(
        self,
        fig: Figure,
        path: str | Path,
        *,
        formats: Sequence[str] | None = None,
        preset: str | AnimPreset | None = None,
        fps: int | None = None,
        width_px: int | None = None,
        max_colors: int | None = None,
        dither: str | None = None,
        hold_first: float | None = None,
        hold_last: float | None = None,
        boomerang: bool = False,
        loop: int = 0,
        crf: int = 18,
        backend: str = "auto",
        keep_frames: str | Path | None = None,
        warn_size_mb: float = 10.0,
        progress: bool = False,
        report: bool = False,
    ) -> None:
        self._fig = fig
        self._spec = resolve_preset(preset)
        self._base, self._formats = _split_path_and_formats(path, formats)

        self._fps = int(fps if fps is not None else self._spec.fps)
        self._width_px = int(width_px if width_px is not None else self._spec.width_px)
        self._max_colors = max_colors
        self._dither = dither
        self._hold_first = self._spec.hold_first if hold_first is None else hold_first
        self._hold_last = self._spec.hold_last if hold_last is None else hold_last
        self._boomerang = boomerang
        self._loop = loop
        self._crf = crf
        self._backend = backend
        self._warn_size_mb = warn_size_mb
        self._progress = progress
        self._report = report

        if self._fps <= 0:
            raise ValueError(f"fps must be positive, got {self._fps}")
        if self._width_px <= 0:
            raise ValueError(f"width_px must be positive, got {self._width_px}")

        if keep_frames is not None:
            self._frames_dir = Path(keep_frames)
            self._frames_dir.mkdir(parents=True, exist_ok=True)
            self._tmp: tempfile.TemporaryDirectory | None = None
        else:
            self._tmp = tempfile.TemporaryDirectory(prefix="cfd_plot_frames_")
            self._frames_dir = Path(self._tmp.name)

        self._sequence: list[Path] = []
        self._n_captures = 0
        self._size_px: tuple[int, int] | None = None
        self._dpi: float | None = None
        self._facecolor: tuple[float, float, float, float] | None = None
        self._encoder_used = "pillow"
        self._closed = False
        #: Populated on exit from the ``with`` block (see :func:`animate`).
        self.result: AnimationResult | None = None

    # -- capture ---------------------------------------------------------

    def capture(self, *, hold: float = 0.0, repeat: int = 1) -> Path:
        """Render the figure's current state as one frame.

        Parameters
        ----------
        hold : float
            Extra seconds to linger on this frame, on top of the normal
            ``1 / fps``.  Implemented by repeating it, so it costs almost
            nothing in the encoded file.
        repeat : int
            Repeat this frame *repeat* times.  ``hold`` is usually what you
            want; this is here for frame-exact control.

        Returns
        -------
        Path
            The PNG that was written.
        """
        if self._closed:
            raise RuntimeError("this Animator is closed — capture() cannot be called after close()")
        if repeat < 1:
            raise ValueError(f"repeat must be >= 1, got {repeat}")

        if self._dpi is None:
            self._prepare()

        path = self._frames_dir / f"frame_{self._n_captures:06d}.png"
        # The rc_context is the anti-jitter guarantee, and it has to be done
        # this way: passing bbox_inches=None to savefig does *not* mean "no
        # cropping", it means "fall back to rcParams['savefig.bbox']" — which
        # every cfd_plot profile sets to "tight". Overriding the rcParam is the
        # only way to actually switch tight cropping off.
        with mpl.rc_context({"savefig.bbox": None, "savefig.pad_inches": 0.0}):
            self._fig.savefig(
                path,
                format="png",
                dpi=self._dpi,
                facecolor=self._facecolor,
                edgecolor="none",
                transparent=False,
            )

        if self._size_px is None:
            self._size_px = _png_size(path)
            # The layout engine has now run against a real renderer, so the
            # axes are where they will stay. Freeze them.
            figure_disable_layout(self._fig)
        else:
            self._check_size(path)

        total = repeat + round(hold * self._fps)
        self._sequence.extend([path] * total)
        self._n_captures += 1

        if self._progress and _stderr_is_a_terminal():
            # Only on a terminal: a carriage return redrawn once per frame is
            # a counter on screen but hundreds of concatenated lines in a log
            # file or a CI transcript.
            print(f"\rcfd_plot.anim: {self._n_captures} frames captured", end="", file=sys.stderr, flush=True)

        return path

    def _prepare(self) -> None:
        """Compute the render DPI and background, once, before the first frame."""
        fig_w_in = self._fig.get_figwidth()
        if fig_w_in <= 0:
            raise ValueError("the figure has no width")
        self._dpi = self._width_px / fig_w_in

        # An alpha < 1 survives into the PNG and then quantises into grey
        # fringes around every glyph once the GIF palette is applied.
        self._facecolor = to_rgba(self._fig.get_facecolor(), alpha=1.0)

    def _check_size(self, path: Path) -> None:
        size = _png_size(path)
        if size != self._size_px:
            first = self._size_px or (0, 0)
            raise RuntimeError(
                f"frame {self._n_captures} is {size[0]}x{size[1]} px but earlier frames are "
                f"{first[0]}x{first[1]} px — the figure was resized mid-capture. "
                "Set the figure size before the first capture() and leave it alone."
            )

    # -- finish ----------------------------------------------------------

    def close(self, *, fig: Figure | None = None, axes: Any = None) -> AnimationResult:
        """Encode everything captured so far and return an :class:`AnimationResult`."""
        if self._closed:
            raise RuntimeError("this Animator is already closed")
        self._closed = True

        if self._progress and _stderr_is_a_terminal():
            print(file=sys.stderr, flush=True)

        try:
            if not self._sequence:
                raise ValueError("nothing was captured — call capture() at least once before close()")

            full = build_sequence(
                self._sequence,
                fps=self._fps,
                hold_first=self._hold_first,
                hold_last=self._hold_last,
                boomerang=self._boomerang,
            )
            paths = self._encode(full)
        finally:
            if self._tmp is not None:
                self._tmp.cleanup()

        # A non-empty sequence implies at least one captured frame, which sets both.
        size_px = self._size_px or (0, 0)
        result = AnimationResult(
            paths=paths,
            n_frames=len(full),
            n_captures=self._n_captures,
            fps=self._fps,
            size_px=size_px,
            preset=self._spec.name,
            backend=self._encoder_used,
            frames_dir=self._frames_dir if self._tmp is None else None,
            fig=fig,
            axes=axes,
        )
        self._warn_if_heavy(result)
        if self._report:
            result.report()
        return result

    def _encode(self, sequence: list[Path]) -> list[Path]:
        # The holds and the mirror are already baked into `sequence`; tell the
        # encoders not to apply them a second time.
        common = {"preset": self._spec, "fps": self._fps, "hold_first": 0.0, "hold_last": 0.0, "boomerang": False}
        paths: list[Path] = []

        for fmt in self._formats:
            if fmt == "gif":
                # Resolve first, so the reported backend is the one that ran.
                self._encoder_used = "ffmpeg" if _choose_backend(self._backend) else "pillow"
                out = frames_to_gif(
                    sequence,
                    self._base.with_suffix(".gif"),
                    max_colors=self._max_colors,
                    dither=self._dither,
                    loop=self._loop,
                    backend=self._backend,
                    **common,  # type: ignore[arg-type]
                )
            elif fmt == "mp4":
                out = frames_to_mp4(sequence, self._base.with_suffix(".mp4"), crf=self._crf, **common)  # type: ignore[arg-type]
                self._encoder_used = "ffmpeg"
            else:  # pragma: no cover — guarded in _split_path_and_formats
                raise ValueError(f"unsupported format {fmt!r}")
            paths.append(out)

        return paths

    def _warn_if_heavy(self, result: AnimationResult) -> None:
        if self._warn_size_mb <= 0:
            return
        for path in result.paths:
            mb = path.stat().st_size / 1024**2
            if mb > self._warn_size_mb:
                logger.warning(
                    "%s is %.1f MB (over the %.0f MB threshold). Shrink it with a smaller width_px, "
                    "a lower fps, max_colors=64, preset='readme', or export MP4 instead of GIF.",
                    path.name,
                    mb,
                    self._warn_size_mb,
                )

    # -- context manager -------------------------------------------------

    def __enter__(self) -> Animator:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            # The loop blew up mid-way; drop the temp frames and let the real
            # exception propagate rather than burying it under "nothing was
            # captured".
            self._closed = True
            if self._tmp is not None:
                self._tmp.cleanup()
            return
        self.result = self.close()


# ---------------------------------------------------------------------------
# Front doors
# ---------------------------------------------------------------------------


@contextmanager
def animate(fig: Figure, path: str | Path, **kwargs: Any):
    """Context manager yielding an :class:`Animator` for *fig*.

    The animation is encoded when the block exits normally; if the block
    raises, nothing is written and the exception propagates untouched.

    All keyword arguments are forwarded to :class:`Animator`.  The finished
    :class:`AnimationResult` is available as ``anim.result`` after the block::

        with animate(fig, "out.gif") as anim:
            for i in range(n):
                ...
                anim.capture()
        print(anim.result)
    """
    anim = Animator(fig, path, **kwargs)
    with anim:
        yield anim


def animate_frames(
    fig: Figure,
    update: Callable[[int], Any],
    frames: int,
    path: str | Path,
    **kwargs: Any,
) -> AnimationResult:
    """Callback form: call ``update(i)`` for ``i`` in ``range(frames)``, capturing each.

    Convenience wrapper over :func:`animate` for the case where every frame
    really is a pure function of an integer index.  When the loop needs to read
    a file per frame, skip frames or hold one, write the loop yourself with
    :func:`animate`.
    """
    if frames < 1:
        raise ValueError(f"frames must be >= 1, got {frames}")

    with animate(fig, path, **kwargs) as anim:
        for i in range(frames):
            update(i)
            anim.capture()
    return anim.result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _split_path_and_formats(path: str | Path, formats: Sequence[str] | None) -> tuple[Path, tuple[str, ...]]:
    """Resolve ``("out.gif", None)`` → ``(out, ("gif",))`` and validate."""
    p = Path(path)
    suffix = p.suffix.lower().lstrip(".")

    if suffix in _KNOWN_FORMATS:
        base = p.with_suffix("")
        resolved = tuple(formats) if formats is not None else (suffix,)
    else:
        base = p
        resolved = tuple(formats) if formats is not None else ("gif",)

    if not resolved:
        raise ValueError("formats is empty — nothing to write")
    unknown = [f for f in resolved if f not in _KNOWN_FORMATS]
    if unknown:
        raise ValueError(f"unsupported format(s) {unknown} — choose from {list(_KNOWN_FORMATS)}")

    base.parent.mkdir(parents=True, exist_ok=True)
    return base, resolved


def _stderr_is_a_terminal() -> bool:
    try:
        return bool(sys.stderr.isatty())
    except (AttributeError, ValueError):
        # A captured or already-closed stream is not a terminal.
        return False


def _png_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size
