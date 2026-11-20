"""
anim — high-quality GIF and MP4 animations from Matplotlib figures.

Three layers, use whichever one matches how much control you need.

1. Sugar — one call
~~~~~~~~~~~~~~~~~~~
    animate_sweep(alpha, cn, "polar.gif", reveal=True,
                  xlabel="alpha [deg]", ylabel="CN [-]")

2. Engine — you write the loop
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    with animate(fig, "run.gif", preset="slides") as anim:
        for step in steps:
            line.set_data(...)
            anim.capture()
    print(anim.result)

3. Encoder — you already have images
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    frames_to_gif(sorted(Path("frames").glob("*.png")), "out.gif")
    frames_to_mp4(frames, "out.mp4")

Public API
----------
Sugar
~~~~~
    animate_sweep         — reveal one curve point by point, or one curve per frame
    animate_path          — a 2-D/3-D trajectory flown in time: trail, head, clock,
                            events, true proportions, slow orbit of a 3-D view

Time-driven building blocks
~~~~~~~~~~~~~~~~~~~~~~~~~~~
    timeline              — physical instant (and hold) of every frame, from a
                            duration or a playback speed
    PathReveal            — ghost / trail / interpolated head of a path, 2-D or 3-D
    lock_limits           — fixed limits, optionally in true proportions (3-D too)

Engine
~~~~~~
    animate               — context manager; capture frames from a live figure
    animate_frames        — callback form, ``update(i)`` over ``range(frames)``
    Animator              — the object behind both
    AnimationResult       — paths, frame count, size, duration, encoder used

Encoder
~~~~~~~
    frames_to_gif         — images -> GIF (global palette, ffmpeg or Pillow)
    frames_to_mp4         — images -> H.264 MP4 (ffmpeg only)
    Mp4Stream             — raw frames piped into ffmpeg as they are drawn
    ffmpeg_available      — is the good encoder installed?
    ffmpeg_executable     — which one: $CFD_PLOT_FFMPEG, PATH, then imageio-ffmpeg

Presets
~~~~~~~
    AnimPreset            — width / fps / palette / holds bundle
    PRESETS               — "slides" (default), "readme", "report"

Why not ``FuncAnimation`` + ``PillowWriter``?
---------------------------------------------
Because the result shakes and boils.  Every cfd_plot style profile sets
``savefig.bbox: tight`` and ``constrained_layout``, both of which re-measure
the figure on every frame; and the stock GIF writers pick a fresh 256-colour
palette per frame, so the colours drift.  This package pins all three.  See
:mod:`cfd_plot.anim.engine` and :mod:`cfd_plot.anim.encode` for the details.
"""

from .encode import (
    PRESETS,
    AnimPreset,
    ffmpeg_available,
    ffmpeg_executable,
    frames_to_gif,
    frames_to_mp4,
    resolve_preset,
)
from .engine import (
    AnimationResult,
    Animator,
    animate,
    animate_frames,
)
from .path import PathReveal, animate_path, lock_limits
from .stream import Mp4Stream
from .sweep import animate_sweep
from .timeline import Timeline, timeline

__all__ = [
    # Sugar
    "animate_sweep",
    "animate_path",
    # Time-driven building blocks
    "PathReveal",
    "Timeline",
    "lock_limits",
    "timeline",
    # Engine
    "animate",
    "animate_frames",
    "Animator",
    "AnimationResult",
    # Encoder
    "frames_to_gif",
    "frames_to_mp4",
    "ffmpeg_available",
    "ffmpeg_executable",
    "Mp4Stream",
    # Presets
    "AnimPreset",
    "PRESETS",
    "resolve_preset",
]
