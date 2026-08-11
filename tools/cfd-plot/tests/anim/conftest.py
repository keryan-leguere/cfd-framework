"""Shared fixtures for the animation tests.

Everything here is deliberately tiny. Each GIF assertion runs a real encode
(two ffmpeg passes, or a full Pillow quantisation), so frame counts stay in the
single digits and the figures are a couple of inches across — the tests are
about *correctness of the sequencing and the palette*, and neither needs
pixels.
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest
from PIL import Image

from cfd_plot import use_style
from cfd_plot.anim import ffmpeg_available

# Small enough that a whole test module encodes in a second or two.
TINY_FIGSIZE = (2.0, 1.5)
TINY_WIDTH_PX = 160

#: Applied to every animation call in the suite so a slow default never
#: silently makes the tests expensive.
FAST = {"width_px": TINY_WIDTH_PX, "hold_last": 0.0, "hold_first": 0.0, "fps": 10}


@pytest.fixture(autouse=True)
def _clean_style():
    use_style("notebook")
    yield
    plt.close("all")


@pytest.fixture
def tiny_fig():
    """A small figure with one line the test can mutate between captures."""
    fig, ax = plt.subplots(figsize=TINY_FIGSIZE)
    (line,) = ax.plot([], [])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    return fig, ax, line


@pytest.fixture
def frame_files(tmp_path):
    """Five 40x30 PNG frames of a moving block, as paths on disk."""
    paths = []
    for i in range(5):
        arr = np.zeros((30, 40, 3), dtype=np.uint8)
        arr[:, :, 2] = 40
        arr[10:20, i * 6 : i * 6 + 8] = (220, 30, 30)
        path = tmp_path / f"src_{i:03d}.png"
        Image.fromarray(arr).save(path)
        paths.append(path)
    return paths


def gif_palettes(path) -> list[tuple]:
    """Return the non-empty palettes carried by the frames of a GIF.

    A well-encoded animation has exactly one: the global palette on the first
    frame, with every later frame inheriting it (Pillow reports an empty
    palette for those). More than one means the encoder re-quantised
    mid-sequence, which is what makes colours boil.
    """
    with Image.open(path) as im:
        out = []
        for f in range(im.n_frames):
            im.seek(f)
            pal = tuple(im.getpalette() or ())
            if pal:
                out.append(pal)
    return out


def gif_frame_count(path) -> int:
    with Image.open(path) as im:
        return im.n_frames


def gif_duration_ms(path) -> int:
    """Total playback time of one loop, in milliseconds.

    This — not the frame count — is what a hold or a boomerang is *for*, and
    it is the only measure the two backends agree on. Pillow collapses
    consecutive identical frames and rolls their delay into the survivor, so a
    five-frame hold becomes one frame held five times as long; ffmpeg keeps the
    repeats. Both play for exactly the same time, which is the contract.
    """
    total = 0
    with Image.open(path) as im:
        for f in range(im.n_frames):
            im.seek(f)
            total += im.info.get("duration", 0)
    return total


def gif_info(path) -> dict:
    with Image.open(path) as im:
        return {"size": im.size, "n_frames": im.n_frames, **im.info}


#: Parametrises a test over both encoders, skipping ffmpeg where absent.
BACKENDS = [
    pytest.param("ffmpeg", marks=pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not installed")),
    pytest.param("pillow"),
]
