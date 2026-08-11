"""
demo_animation.py — Runnable showcase for the ``anim`` package.

Run from ``tools/cfd-plot``::

    PYTHONPATH=. python 01_EXEMPLE/demo_animation.py

Output GIFs (and one MP4, if ffmpeg is installed) go to ``demo_output/``.

Sections
--------
A  Reveal a polar                (the one-liner)
B  Sweep across Mach             (one curve per frame, accumulating)
C  Multi-panel on one clock      (the engine — you write the loop)
D  An irregular loop             (skip frames, hold on an event)
E  Escape hatches                (your own axes, per-frame callback)
F  Re-encode kept frames         (the encoder on its own)
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from cfd_plot import (
    add_reference_lines,
    animate,
    animate_sweep,
    annotate_point,
    ffmpeg_available,
    frames_to_gif,
    make_legend,
    new_figure,
    plot_line,
    print_file_report,
    set_suptitle,
    set_title,
    use_style,
)

use_style("notebook")

OUT_DIR = Path(__file__).with_name("demo_output")
OUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Shared synthetic data
# ---------------------------------------------------------------------------

ALPHA = np.linspace(-4.0, 16.0, 41)
CN = 0.11 * ALPHA + 0.004 * ALPHA**2

MACH = np.linspace(0.30, 0.85, 12)
CN_PER_MACH = np.array([(0.11 + 0.09 * (m - 0.30)) * ALPHA + 0.004 * ALPHA**2 for m in MACH])

ITER = np.arange(1, 121)
RESIDUAL = 10.0 ** (-ITER / 22.0) * (1.0 + 0.35 * np.sin(ITER / 4.0))

# ---------------------------------------------------------------------------
# A — Reveal a polar
# ---------------------------------------------------------------------------
# The whole point of `reveal`: the axes are locked to the *final* extent from
# frame 0, so the curve grows into a fixed window instead of the window
# shrinking around it.

print("A: revealing a polar …")
result = animate_sweep(
    ALPHA, CN, OUT_DIR / "A_reveal.gif",
    reveal=True,
    xlabel=r"$\alpha$ (°)", ylabel=r"$C_N$ (-)",
    title="Normal-force polar",
    preset="slides",
)
print(f"   {result}")

# ---------------------------------------------------------------------------
# B — Sweep across Mach
# ---------------------------------------------------------------------------
# One complete polar per frame. `keep_previous` leaves a faded trail, so the
# trend across the sweep is legible in any single frame; `boomerang` plays
# back down instead of snapping to the start.

print("B: sweeping across Mach …")
result = animate_sweep(
    ALPHA, CN_PER_MACH, OUT_DIR / "B_sweep.gif",
    labels=[f"M = {m:.2f}" for m in MACH],
    keep_previous=True,
    boomerang=True,
    xlabel=r"$\alpha$ (°)", ylabel=r"$C_N$ (-)",
    title="Polar",
    preset="slides",
)
print(f"   {result}")

# ---------------------------------------------------------------------------
# C — Multi-panel on one clock
# ---------------------------------------------------------------------------
# Two axes advancing together is where the sugar stops and the engine starts.
# Note that the limits are set *before* the loop: nothing may rescale once the
# first frame is captured, or the animation twitches.

print("C: convergence + polar on one clock …")

fig, (ax_conv, ax_polar) = new_figure(1, 2, figsize=(11.5, 4.6))

line_res = plot_line(ax_conv, [], [], marker="", label="residual")
ax_conv.set(xlim=(1, ITER[-1]), ylim=(1e-6, 3.0), yscale="log")
ax_conv.set(xlabel="iteration", ylabel="residual (-)")
add_reference_lines(ax_conv, hlines=[1e-5])
make_legend(ax_conv)

line_pol = plot_line(ax_polar, [], [], marker="", label=r"$C_N$")
ax_polar.set(xlim=(ALPHA[0], ALPHA[-1]), ylim=(CN.min() - 0.2, CN.max() + 0.2))
ax_polar.set(xlabel=r"$\alpha$ (°)", ylabel=r"$C_N$ (-)")
make_legend(ax_polar)

with animate(fig, OUT_DIR / "C_panels.gif", preset="slides", progress=True) as anim:
    for i in range(len(ITER)):
        line_res.set_data(ITER[: i + 1], RESIDUAL[: i + 1])
        # The polar fills in at its own pace, driven by the same clock.
        n = min(i // 3 + 1, ALPHA.size)
        line_pol.set_data(ALPHA[:n], CN[:n])
        set_suptitle(fig, f"iteration {ITER[i]:>4d}   —   residual {RESIDUAL[i]:.2e}")
        anim.capture()

print(f"   {anim.result}")
plt.close(fig)

# ---------------------------------------------------------------------------
# D — An irregular loop
# ---------------------------------------------------------------------------
# What the callback form cannot express: frames that are skipped, and a frame
# held because something happened there. In a real run the `continue` would
# guard a diverged timestep and the `hold` would mark the moment convergence
# is reached.

print("D: an irregular loop …")

fig, ax = new_figure(figsize=(8, 5))
line = plot_line(ax, [], [], marker="", label="residual")
ax.set(xlim=(1, ITER[-1]), ylim=(1e-6, 3.0), yscale="log")
ax.set(xlabel="iteration", ylabel="residual (-)")
make_legend(ax)

converged_at = int(ITER[np.argmax(RESIDUAL < 1e-5)])

with animate(fig, OUT_DIR / "D_irregular.gif", preset="slides") as anim:
    for i in range(len(ITER)):
        if i % 2:
            continue  # every other step is not worth a frame
        line.set_data(ITER[: i + 1], RESIDUAL[: i + 1])
        reached = ITER[i] >= converged_at
        set_title(ax, f"iteration {ITER[i]}" + ("  —  converged" if reached else ""))
        # Linger for a second the first time the criterion is met.
        anim.capture(hold=1.0 if ITER[i] == converged_at else 0.0)

print(f"   {anim.result}")
plt.close(fig)

# ---------------------------------------------------------------------------
# E — Escape hatches
# ---------------------------------------------------------------------------
# `ax=` keeps decoration the one-liner knows nothing about; `on_frame` runs
# per frame; `close_fig=False` hands the figure back so a still of the final
# state can be saved next to the animation.

print("E: escape hatches …")

fig, ax = new_figure(figsize=(8, 5))
ax.axhspan(2.0, 3.5, color="0.9", zorder=0)          # a "beyond linear range" band
ax.set(xlabel=r"$\alpha$ (°)", ylabel=r"$C_N$ (-)")

label = ax.text(0.97, 0.05, "", transform=ax.transAxes, ha="right", va="bottom", fontsize=11)


def annotate(i, axes):
    """Track the current point with a live readout."""
    label.set_text(rf"$\alpha$ = {ALPHA[i]:5.1f}°    $C_N$ = {CN[i]:5.2f}")
    if i == ALPHA.size - 1:
        annotate_point(axes, "end of sweep", (ALPHA[-1], CN[-1]), offset=(-95, 25))


result = animate_sweep(
    ALPHA, CN, OUT_DIR / "E_hooks.gif",
    ax=ax, on_frame=annotate, close_fig=False,
    preset="slides", hold_last=1.5,
)
print(f"   {result}")

# The figure survived, so the last frame doubles as a static figure.
result.fig.savefig(OUT_DIR / "E_final_frame.png", dpi=110)
plt.close(result.fig)

# ---------------------------------------------------------------------------
# F — Re-encode kept frames
# ---------------------------------------------------------------------------
# `keep_frames` writes the PNGs somewhere you choose. They can then be
# re-encoded at will — a different preset, a different loop, an MP4 — without
# re-rendering anything. The same call takes frames produced by anything else
# (ParaView snapshots, an earlier batch_plot run).

print("F: re-encoding kept frames …")

frames_dir = OUT_DIR / "F_frames"
animate_sweep(
    ALPHA, CN, OUT_DIR / "F_source.gif",
    keep_frames=frames_dir, preset="slides",
)

kept = sorted(frames_dir.glob("*.png"))
light = frames_to_gif(kept, OUT_DIR / "F_reencoded_readme.gif", preset="readme", max_colors=64)
print(f"   {len(kept)} frames -> {light.name} ({light.stat().st_size / 1024:.0f} kB)")

if ffmpeg_available():
    from cfd_plot import frames_to_mp4

    mp4 = frames_to_mp4(kept, OUT_DIR / "F_reencoded.mp4", preset="slides")
    print(f"   {len(kept)} frames -> {mp4.name} ({mp4.stat().st_size / 1024:.0f} kB)")
else:
    print("   ffmpeg not installed — skipping the MP4 (GIFs above used the Pillow fallback)")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

produced = sorted(p for p in OUT_DIR.iterdir() if p.suffix in {".gif", ".mp4"})
print()
print_file_report(produced, title="demo_animation — output files")
