# %% [markdown]
# # Plotting Template — Tutorial & Quick-Reference
#
# This file is **both** a runnable demo and a **copy/paste template**.
# It showcases every feature of the `cfd_plot` package while keeping
# full access to Matplotlib underneath.
#
# ## How to use this template
#
# 1. Copy the section(s) you need into your own script.
# 2. Replace the dummy data with your own arrays.
# 3. Uncomment the optional parameters you want to tweak.
#
# > **Principle**: Matplotlib is the real API.
# > This package only adds `use_style(...)` at the top and
# > `plot_line` / `save_figure` for finishing touches.
#
# ---
# ## Table of contents
#
# 1. Quickstart — minimal figure
# 2. Style profiles comparison (`notebook`, `slides`, `paper`)
# 3. `plot_line` — white-filled markers
# 4. `apply_marker_style` — restyle existing curves
# 5. `style_context` — temporary profile
# 6. `new_figure` — create with embedded profile
# 7. Export with `save_figure` — normal + DECLASSIFIE variant
# 8. Subplots
# 9. Multi-format export (PNG + SVG + EMF)
# 10. Realistic CFD example
# 11. `make_legend` — legend helper with old-style frame
# 12. `plot_with_band` — line + uncertainty band
# 13. `add_reference_lines` + `apply_oldschool_axes`
# 14. Rich output with `report=True` and `print_file_report`
# 15. `add_textbox` — metadata box on the figure
# 16. `set_axis_sci` — scientific notation on axes
# 17. `annotate_point` — annotation arrow
# 18. `plot_bar` — bar chart with old-style edges
# 19. `dual_axis` — styled secondary Y-axis (twinx)
# 20. `set_subtitle` — subtitle below the axes title
# 21. **Exhaustive parameter checklist** (uncomment what you need)
# 22. Copy/paste template function

# %%
import matplotlib.pyplot as plt
import numpy as np

from cfd_plot import (
    BODY_FONT,
    TITLE_FONT,
    add_reference_lines,
    add_shared_colorbar,
    add_textbox,
    annotate_point,
    apply_marker_style,
    apply_oldschool_axes,
    compute_speed,
    dataframe_to_grid,
    dataframe_to_masked_grid,
    dual_axis,
    extract_slice2d,
    make_figure_legend,
    make_legend,
    mask_field,
    new_figure,
    plot_bar,
    plot_contour,
    plot_contour_quiver,
    plot_contourf,
    plot_imshow,
    plot_line,
    plot_pcolormesh,
    plot_pcolormesh_interp,
    plot_quiver,
    plot_streamplot,
    plot_with_band,
    print_file_report,
    reshape_structured2d,
    save_figure,
    set_axis_sci,
    set_subtitle,
    set_suptitle,
    set_title,
    style_context,
    use_style,
)

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------
x = np.linspace(0, 2 * np.pi, 25)
y_sin = np.sin(x)
y_cos = np.cos(x)
y_damped = np.exp(-x / 5) * np.sin(2 * x)

for profile in ["notebook", "slides", "paper"]:
    use_style(profile)

    fig, (ax1, ax2) = plt.subplots(1, 2)

    plot_line(ax1, x, y_sin, label="sin(x)")
    set_title(ax1, "Panel A")
    ax1.set_xlabel("x")
    ax1.set_ylabel("f(x)")
    ax1.legend()

    plot_line(ax2, x, y_cos, marker="s", label="cos(x)")
    set_title(ax2, "Panel B")
    ax2.set_xlabel("x")
    ax2.set_ylabel("f(x)")
    ax2.legend()

    set_suptitle(fig, f"Figure suptitle in {profile}", fontweight="bold", fontsize=14)

    save_figure(fig, f"demo_output/example_{profile}", formats=("png",), declassify=None, report=True)
    plt.close(fig)

from IPython.display import display, Image as IPImage

print("=== NORMAL ===")

# %% [markdown]
# ---
# ## 1. Quickstart — minimal figure
#
# The shortest path from data to a publication-ready figure.


# %%
use_style("notebook")

fig, ax = plt.subplots()
plot_line(ax, x, y_sin, label="sin(x)")
plot_line(ax, x, y_cos, marker="s", label="cos(x)")

ax.set_xlabel("Angle (rad)")
ax.set_ylabel("Amplitude")
ax.set_title("Quickstart")
ax.legend()
plt.show()

# %% [markdown]
# ---
# ## 1b. Mixed fonts — Helvetica titles + Times body
#
# The package bundles **TeX Gyre Heros** (≈ Helvetica) and
# **TeX Gyre Termes** (≈ Times New Roman) in `cfd_plot/fonts/`.
# They are registered automatically at import time.
#
# - **Body text** (axis labels, ticks, legend): TeX Gyre Termes — set via
#   the `.mplstyle` files, nothing extra needed.
# - **Titles**: use `set_title(ax, ...)` or `set_suptitle(fig, ...)` —
#   they default to `TITLE_FONT`.  Or pass `fontfamily=TITLE_FONT`
#   manually to `ax.set_title()`.
#
# You can also use `TITLE_FONT` / `BODY_FONT` constants anywhere you
# need the font name as a string.

# %%
use_style("notebook")
print(f"TITLE_FONT = {TITLE_FONT!r}")
print(f"BODY_FONT  = {BODY_FONT!r}")

fig, ax = plt.subplots()
plot_line(ax, x, y_sin, label="sin(x)")
plot_line(ax, x, y_cos, marker="s", label="cos(x)")

ax.set_xlabel("Angle (rad)")
ax.set_ylabel("Amplitude")

# Option A (preferred): use the set_title helper
set_title(ax, "Helvetica Title — Times Body")

# Option B: manual override
# ax.set_title("Helvetica Title — Times Body", fontfamily=TITLE_FONT)

ax.legend()
plt.show()

# %%
# Works with suptitle too
use_style("paper")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

plot_line(ax1, x, y_sin, label="sin(x)")
set_title(ax1, "Panel A")
ax1.set_xlabel("x")
ax1.set_ylabel("f(x)")
ax1.legend()

plot_line(ax2, x, y_cos, marker="s", label="cos(x)")
set_title(ax2, "Panel B")
ax2.set_xlabel("x")
ax2.set_ylabel("f(x)")
ax2.legend()

set_suptitle(fig, "Figure suptitle in Helvetica", fontweight="bold", fontsize=14)
plt.show()

# %% [markdown]
# ---
# ## 2. Style profiles comparison
#
# Three built-in profiles adjust figure size, font sizes, line widths,
# DPI, legend framing, etc.  Pick the one that matches your target and
# override what you need via standard Matplotlib calls.

# %%
for profile in ["notebook", "slides", "paper"]:
    use_style(profile)

    fig, ax = plt.subplots()
    plot_line(ax, x, y_sin, label="sin(x)")
    plot_line(ax, x, y_cos, marker="s", label="cos(x)")
    plot_line(ax, x, y_damped, marker="D", label="damped")

    ax.set_xlabel("Angle (rad)")
    ax.set_ylabel("Amplitude")
    ax.set_title(f"Profile: {profile}")
    ax.legend()
    plt.show()

# %% [markdown]
# ---
# ## 3. `plot_line` — white-filled markers
#
# Works exactly like `ax.plot()` but automatically sets
# `markerfacecolor="white"` and `markeredgecolor` to the line color.
# All `ax.plot()` kwargs are forwarded.

# %%
use_style("notebook")

fig, ax = plt.subplots()
plot_line(ax, x, y_sin, marker="o", label="circles (o)")
plot_line(ax, x, y_cos, marker="s", label="squares (s)")
plot_line(ax, x, y_damped, marker="D", label="diamonds (D)")
plot_line(ax, x, -y_cos, marker="^", label="triangles (^)")

ax.set_xlabel("x")
ax.set_ylabel("f(x)")
ax.set_title("plot_line: white-filled markers")
ax.legend()
plt.show()

# %% [markdown]
# ---
# ## 4. `apply_marker_style` — restyle existing curves
#
# Already plotted with plain `ax.plot()`?  Apply the marker style
# after the fact.

# %%
use_style("notebook")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

ax1.plot(x, y_sin, "o-", label="sin(x)")
ax1.plot(x, y_cos, "s-", label="cos(x)")
ax1.set_title("ax.plot() — default markers")
ax1.set_xlabel("x")
ax1.set_ylabel("f(x)")
ax1.legend()

(line1,) = ax2.plot(x, y_sin, "o-", label="sin(x)")
(line2,) = ax2.plot(x, y_cos, "s-", label="cos(x)")
apply_marker_style(line1)
apply_marker_style(line2)
ax2.set_title("After apply_marker_style()")
ax2.set_xlabel("x")
ax2.set_ylabel("f(x)")
ax2.legend()

fig.suptitle("With vs without apply_marker_style", fontweight="bold", y=1.02)
plt.show()

# %% [markdown]
# ---
# ## 5. `style_context` — temporary profile
#
# Context manager: the profile only applies inside the `with` block.

# %%
use_style("notebook")

fig1, ax1 = plt.subplots()
plot_line(ax1, x, y_sin, label="sin(x)")
ax1.set_xlabel("x")
ax1.set_ylabel("f(x)")
ax1.set_title("Global style: notebook")
ax1.legend()
plt.show()

with style_context("slides"):
    fig2, ax2 = plt.subplots()
    plot_line(ax2, x, y_sin, label="sin(x)")
    ax2.set_xlabel("x")
    ax2.set_ylabel("f(x)")
    ax2.set_title("Temporary: slides (via style_context)")
    ax2.legend()
    plt.show()

fig3, ax3 = plt.subplots()
plot_line(ax3, x, y_sin, label="sin(x)")
ax3.set_xlabel("x")
ax3.set_ylabel("f(x)")
ax3.set_title("Back to: notebook")
ax3.legend()
plt.show()

# %% [markdown]
# ---
# ## 6. `new_figure` — create with embedded profile
#
# Shortcut for `plt.subplots()` that applies the profile automatically.
# You can still override `figsize` or pass any `subplots()` kwarg.

# %%
fig, ax = new_figure(profile="paper")
plot_line(ax, x, y_damped, marker="D", label="damped oscillation")
ax.set_xlabel("Time (s)")
ax.set_ylabel("Amplitude")
ax.set_title("new_figure(profile='paper')")
ax.legend()
plt.show()

fig, ax = new_figure(profile="paper", figsize=(10, 3))
plot_line(ax, x, y_damped, marker="D", label="damped oscillation")
ax.set_xlabel("Time (s)")
ax.set_ylabel("Amplitude")
ax.set_title("new_figure + custom figsize")
ax.legend()
plt.show()

# %% [markdown]
# ---
# ## 7. Export with `save_figure` — normal + DECLASSIFIE variant
#
# `save_figure()` exports the figure and optionally a **declassified**
# copy where ticks/ticklabels are stripped and a boxed DECLASSIFIE
# stamp is added.
#
# | `declassify=` | Effect |
# |---|---|
# | `"x"` | Strip X ticks/labels |
# | `"y"` | Strip Y ticks/labels |
# | `"both"` | Strip both axes |
# | `None` | No declassified copy |
#
# You can also customise the stamp text and appearance:
#
# ```python
# save_figure(fig, "out/fig", declassify="both",
#             declassify_label="RESTRICTED",
#             declassify_stamp_kw=dict(fontsize=14, color="red",
#                                      bbox=dict(edgecolor="red", linewidth=2)))
# ```

# %%
import os

os.makedirs("demo_output", exist_ok=True)

use_style("notebook")

fig, ax = plt.subplots()
plot_line(ax, x, y_sin, label="sin(x)")
plot_line(ax, x, y_cos, marker="s", label="cos(x)")
ax.set_xlabel("Angle (rad)")
ax.set_ylabel("Amplitude")
ax.set_title("Export with declassify='both'")
ax.legend()

files = save_figure(
    fig,
    "demo_output/example_both",
    formats=("png",),
    declassify="both",
    declassify_label="DECLASSIFIE",
    declassify_stamp_kw=dict(fontsize=14, color="red", bbox=dict(edgecolor="red", linewidth=2)),
    report=True,
)
plt.close(fig)

# %% [markdown]
# ### Side-by-side: normal vs declassified

# %%

print("=== NORMAL ===")
display(IPImage(filename="demo_output/example_both.png"))

print("\n=== DECLASSIFIED (both) ===")
display(IPImage(filename="demo_output/example_both_declass_xy.png"))

# %% [markdown]
# ### Variants: declassify on X, Y, or both

# %%
use_style("notebook")

for axis_choice in ["x", "y", "both"]:
    fig, ax = plt.subplots()
    plot_line(ax, x, y_sin, label="sin(x)")
    plot_line(ax, x, y_cos, marker="s", label="cos(x)")
    ax.set_xlabel("Angle (rad)")
    ax.set_ylabel("Amplitude")
    ax.set_title(f'declassify="{axis_choice}"')
    ax.legend()

    save_figure(
        fig,
        f"demo_output/demo_declass_{axis_choice}",
        formats=("png",),
        declassify=axis_choice,
    )
    plt.close(fig)

for axis_choice in ["x", "y", "both"]:
    tag = {"x": "x", "y": "y", "both": "xy"}[axis_choice]
    print(f'\n=== declassify="{axis_choice}" ===')
    display(IPImage(filename=f"demo_output/demo_declass_{axis_choice}_declass_{tag}.png"))

# %% [markdown]
# ---
# ## 8. Subplots
#
# The wrapper works naturally with any Matplotlib subplot layout.

# %%
use_style("notebook")

fig, axes = plt.subplots(2, 2, figsize=(12, 8))

plot_line(axes[0, 0], x, y_sin, label="sin(x)")
axes[0, 0].set_title("sin(x)")
axes[0, 0].set_xlabel("x")
axes[0, 0].set_ylabel("y")
axes[0, 0].legend()

plot_line(axes[0, 1], x, y_cos, marker="s", label="cos(x)")
axes[0, 1].set_title("cos(x)")
axes[0, 1].set_xlabel("x")
axes[0, 1].set_ylabel("y")
axes[0, 1].legend()

plot_line(axes[1, 0], x, y_damped, marker="D", label="damped")
axes[1, 0].set_title("Damped oscillation")
axes[1, 0].set_xlabel("t")
axes[1, 0].set_ylabel("A")
axes[1, 0].legend()

plot_line(axes[1, 1], x, y_sin, label="sin")
plot_line(axes[1, 1], x, y_cos, marker="s", label="cos")
plot_line(axes[1, 1], x, y_damped, marker="^", label="damped")
axes[1, 1].set_title("Combined")
axes[1, 1].set_xlabel("x")
axes[1, 1].set_ylabel("f(x)")
axes[1, 1].legend()

fig.suptitle("Multiple subplots", fontweight="bold", fontsize=14)
plt.show()

save_figure(fig, "demo_output/subplots_demo", formats=("png",), declassify="y", report=True)

# %% [markdown]
# ---
# ## 9. Multi-format export (PNG + SVG + EMF)
#
# Export to several formats at once.  EMF conversion requires Inkscape.

# %%
use_style("paper")

fig, ax = plt.subplots()
plot_line(ax, x, y_sin, label="sin(x)")
plot_line(ax, x, y_cos, marker="s", label="cos(x)")
ax.set_xlabel("Angle (rad)")
ax.set_ylabel("Amplitude")
ax.set_title("Multi-format export")
ax.legend()

files = save_figure(
    fig,
    "demo_output/multi_format",
    formats=("png", "svg", "emf"),
    declassify="x",
    report=True,
)
plt.close(fig)

# %% [markdown]
# ---
# ## 10. Realistic CFD example
#
# Simulated residual convergence + Cp distribution.

# %%
np.random.seed(42)
iterations = np.arange(0, 500)
residual_mass = 1e-1 * np.exp(-iterations / 80) + 1e-6 * np.random.randn(len(iterations))
residual_momentum = 5e-2 * np.exp(-iterations / 60) + 1e-6 * np.random.randn(len(iterations))

chord = np.linspace(0, 1, 50)
cp_upper = -2.0 * np.sin(np.pi * chord) + 0.1 * np.random.randn(len(chord))
cp_lower = 0.3 * np.ones_like(chord) + 0.05 * np.random.randn(len(chord))

use_style("paper")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

plot_line(ax1, iterations[::10], np.abs(residual_mass[::10]), marker="o", label="mass")
plot_line(ax1, iterations[::10], np.abs(residual_momentum[::10]), marker="s", label="momentum")
ax1.set_yscale("log")
ax1.set_xlabel("Iterations")
ax1.set_ylabel("Residual (L2 norm)")
ax1.set_title("Residual convergence")
ax1.legend()

plot_line(ax2, chord, cp_upper, marker="^", label="upper surface")
plot_line(ax2, chord, cp_lower, marker="v", label="lower surface")
ax2.invert_yaxis()
ax2.set_xlabel("x/c")
ax2.set_ylabel("$C_p$")
ax2.set_title("Pressure distribution")
ax2.legend()

plt.show()

save_figure(fig, "demo_output/cfd_example", formats=("png", "svg"), declassify="both", report=True)

# %% [markdown]
# ---
# ## 11. `make_legend` — legend helper with old-style frame
#
# `make_legend(ax)` replaces `ax.legend()` and guarantees a thick,
# square-cornered, opaque frame.  All `ax.legend()` kwargs are forwarded.

# %%
use_style("notebook")

fig, ax = plt.subplots()
plot_line(ax, x, y_sin, label="sin(x)")
plot_line(ax, x, y_cos, marker="s", label="cos(x)")
ax.set_xlabel("x")
ax.set_ylabel("f(x)")
ax.set_title("make_legend — default old-style frame")

make_legend(ax)
plt.show()

# With overrides
fig, ax = plt.subplots()
plot_line(ax, x, y_sin, label="sin(x)")
plot_line(ax, x, y_cos, marker="s", label="cos(x)")
ax.set_xlabel("x")
ax.set_ylabel("f(x)")
ax.set_title("make_legend — custom position + title")

make_legend(ax, loc="lower left", ncol=2, title="Curves", frame_linewidth=2.0)
plt.show()

# %% [markdown]
# ---
# ## 12. `plot_with_band` — line + uncertainty band
#
# Thin wrapper around `plot_line` + `ax.fill_between`.
#
# - Pass `y_low` only → symmetric band (`y +/- y_low`).
# - Pass both `y_low` and `y_high` → explicit boundaries.

# %%
use_style("notebook")

noise = 0.2 * np.abs(np.sin(x))

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

plot_with_band(ax1, x, y_sin, y_low=noise, label="sin(x)", marker="o")
ax1.set_xlabel("x")
ax1.set_ylabel("f(x)")
ax1.set_title("Symmetric band (y +/- delta)")
make_legend(ax1)

plot_with_band(
    ax2,
    x,
    y_cos,
    y_low=y_cos - 0.3,
    y_high=y_cos + 0.15,
    label="cos(x)",
    marker="s",
)
ax2.set_xlabel("x")
ax2.set_ylabel("f(x)")
ax2.set_title("Explicit low/high boundaries")
make_legend(ax2)

plt.show()

# %% [markdown]
# ---
# ## 13. `add_reference_lines` + `apply_oldschool_axes`
#
# - `add_reference_lines(ax, hlines=[...], vlines=[...])` draws
#   dashed reference lines (all `ax.axhline`/`axvline` kwargs forwarded).
# - `apply_oldschool_axes(ax)` polishes spines, inward ticks, and
#   optionally creates the legend via `make_legend`.

# %%
use_style("notebook")

fig, ax = plt.subplots()
plot_line(ax, x, y_sin, label="sin(x)")
plot_line(ax, x, y_cos, marker="s", label="cos(x)")
ax.set_xlabel("x")
ax.set_ylabel("f(x)")
ax.set_title("Reference lines + oldschool axes polish")

add_reference_lines(ax, hlines=[0], vlines=[np.pi], linestyle=":", color="0.5")
apply_oldschool_axes(ax)
plt.show()

# %% [markdown]
# ---
# ## 14. Rich output with `report=True` and `print_file_report`
#
# Pass `report=True` to `save_figure()` for an automatic summary.
# Or call `print_file_report(files)` on any list of Paths.
# Falls back to plain text when Rich is not installed.

# %%
use_style("notebook")

fig, ax = plt.subplots()
plot_line(ax, x, y_sin, label="sin(x)")
plot_line(ax, x, y_cos, marker="s", label="cos(x)")
ax.set_xlabel("x")
ax.set_ylabel("f(x)")
ax.set_title("Rich report demo")
make_legend(ax)

files = save_figure(
    fig,
    "demo_output/rich_demo",
    formats=("png", "svg"),
    declassify="both",
    report=True,
)
plt.close(fig)

# You can also call print_file_report on any list of Paths:
print_file_report(files, title="Same files via standalone call")

# %% [markdown]
# ---
# ## 15. `add_textbox` — metadata box on the figure
#
# Place case metadata (Mach, Re, mesh info, solver settings) directly
# on the figure.  Anchored via `loc` (four corners).

# %%
use_style("notebook")

fig, ax = plt.subplots()
plot_line(ax, x, y_sin, label="sin(x)")
plot_line(ax, x, y_cos, marker="s", label="cos(x)")
ax.set_xlabel("x")
ax.set_ylabel("f(x)")
ax.set_title("add_textbox demo")
make_legend(ax, loc="upper left")

add_textbox(ax, "Ma = 0.85\nRe = 6.5e6\nMesh: 12M cells", loc="lower right")
plt.show()

# With a different location and custom styling
fig, ax = plt.subplots()
plot_line(ax, x, y_damped, marker="D", label="damped")
ax.set_xlabel("x")
ax.set_ylabel("f(x)")
ax.set_title("Textbox — upper left, custom color")
make_legend(ax, loc="upper right")

add_textbox(
    ax,
    "Case: NACA0012\nAoA = 2.5 deg",
    loc="upper left",
    fontsize=9,
    color="0.30",
)
plt.show()

# %% [markdown]
# ---
# ## 16. `set_axis_sci` — scientific notation on axes
#
# Force clean scientific notation (e.g. x10^-3) on an axis.
# Very useful for residuals or small quantities.

# %%
use_style("notebook")

y_small = y_sin * 1e-5

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

plot_line(ax1, x, y_small, label="sin(x) * 1e-5")
ax1.set_xlabel("x")
ax1.set_ylabel("Value")
ax1.set_title("Default tick formatting")
make_legend(ax1)

plot_line(ax2, x, y_small, label="sin(x) * 1e-5")
set_axis_sci(ax2, axis="y")
ax2.set_xlabel("x")
ax2.set_ylabel("Value")
ax2.set_title("After set_axis_sci(ax, axis='y')")
make_legend(ax2)

plt.show()

# %% [markdown]
# ---
# ## 17. `annotate_point` — annotation arrow
#
# Add a clean annotation with an arrow pointing at a data coordinate.
# Offset-based positioning by default (in points), or explicit data coords.

# %%
use_style("notebook")

fig, ax = plt.subplots()
plot_line(ax, x, y_sin, label="sin(x)")
ax.set_xlabel("x")
ax.set_ylabel("f(x)")
ax.set_title("annotate_point demo")
make_legend(ax, loc="lower left")

annotate_point(ax, "peak", xy=(np.pi / 2, 1.0), offset=(40, -20))
annotate_point(ax, "trough", xy=(3 * np.pi / 2, -1.0), offset=(40, 20))
annotate_point(ax, "zero crossing", xy=(np.pi, 0.0), offset=(-50, 30), fontsize=9)
plt.show()

# %% [markdown]
# ---
# ## 18. `plot_bar` — bar chart with old-style edges
#
# Thin wrapper around `ax.bar()` with consistent edge styling.
# All `ax.bar()` kwargs are forwarded.

# %%
use_style("notebook")

categories = ["Mesh A", "Mesh B", "Mesh C", "Mesh D"]
y_plus_values = [0.8, 1.2, 2.5, 5.1]

fig, ax = plt.subplots()
plot_bar(ax, categories, y_plus_values, label="Max y+", color="C0")
add_reference_lines(ax, hlines=[1.0], color="red", linestyle="--", linewidth=1.0, zorder=3)
ax.set_ylabel("$y^+$")
ax.set_title("Mesh quality comparison")
make_legend(ax)
plt.show()

# Grouped bars
fig, ax = plt.subplots()
bar_x = np.arange(len(categories))
width = 0.35
plot_bar(ax, bar_x - width / 2, y_plus_values, label="Max y+", color="C0", width=width)
plot_bar(ax, bar_x + width / 2, [v * 0.6 for v in y_plus_values], label="Mean y+", color="C1", width=width)
ax.set_xticks(bar_x)
ax.set_xticklabels(categories)
ax.set_ylabel("$y^+$")
ax.set_title("Grouped bar chart")
make_legend(ax)
plt.show()

# %% [markdown]
# ---
# ## 19. `dual_axis` — styled secondary Y-axis (twinx)
#
# Creates a twinx axis with matching old-school styling.
# Optional `color` tints the right spine, ticks, and label.

# %%
use_style("notebook")

fig, ax = plt.subplots()
plot_line(ax, x, y_sin, label="sin(x)", color="C0")
ax.set_xlabel("x")
ax.set_ylabel("sin(x)", color="C0")
ax.set_title("dual_axis — two Y scales")
ax.tick_params(axis="y", colors="C0")

ax2 = dual_axis(ax, ylabel="cos(x)", color="C1")
plot_line(ax2, x, y_cos * 100, marker="s", label="cos(x) * 100", color="C1")

make_legend(ax, loc="upper left")
make_legend(ax2, loc="upper right")
plt.show()

# %% [markdown]
# ---
# ## 20. `set_subtitle` — subtitle below the axes title
#
# Call `set_subtitle(ax, ...)` **after** `set_title(ax, ...)` to place
# a secondary line below the title (one point smaller by default).
# Handy for flow conditions, mesh info, or any metadata that belongs
# next to the title without cluttering the plot area.

# %%
use_style("notebook")

fig, ax = plt.subplots()
plot_line(ax, x, y_sin, label="sin(x)")
plot_line(ax, x, y_cos, marker="s", label="cos(x)")
ax.set_xlabel("Angle (rad)")
ax.set_ylabel("Amplitude")

set_title(ax, "Evolution of amplitude vs angle")
set_subtitle(ax, r"$M = 0.3$, $\alpha = 2°$")
make_legend(ax)
plt.show()

# With subplots
use_style("paper")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

plot_line(ax1, x, y_sin, label="sin(x)")
set_title(ax1, "Residual convergence")
set_subtitle(ax1, "SA turbulence model, CFL = 10")
ax1.set_xlabel("Iterations")
ax1.set_ylabel("Residual")
make_legend(ax1)

plot_line(ax2, x, y_cos, marker="s", label="cos(x)")
set_title(ax2, "Pressure distribution")
set_subtitle(ax2, r"$M_\infty = 0.85$, $Re = 6.5 \times 10^6$")
ax2.set_xlabel("x/c")
ax2.set_ylabel("$C_p$")
make_legend(ax2)

set_suptitle(fig, "CFD Post-processing", fontweight="bold")
plt.show()

# %% [markdown]
# ---
# ## 21. Exhaustive parameter checklist
#
# **One example plot with every useful Matplotlib knob listed as a
# comment.  Uncomment the lines you need.**
#
# This is the main reference block: copy it, strip what you don't need.

# %%
use_style("notebook")

fig, ax = plt.subplots(
    # figsize=(10, 6),           # (width, height) in inches
    # dpi=150,                   # screen resolution
)

# === ax.plot / plot_line kwargs ============================================
plot_line(
    ax,
    x,
    y_sin,
    label="sin(x)",
    marker="o",
    # ---------- line style -------------------------------------------------
    # color="#1f77b4",           # explicit color (hex, named, RGB tuple …)
    # linestyle="-",             # "-", "--", "-.", ":", "None"
    # linewidth=2.0,             # line thickness (float)
    # alpha=1.0,                 # transparency 0..1
    # zorder=2,                  # drawing order (higher = on top)
    # dashes=(5, 2, 1, 2),      # custom dash pattern (on, off, on, off …)
    # drawstyle="default",       # "default", "steps", "steps-pre/mid/post"
    # solid_capstyle="round",    # "butt", "round", "projecting"
    # solid_joinstyle="round",   # "miter", "round", "bevel"
    # dash_capstyle="butt",      # cap style for dashed lines
    # dash_joinstyle="round",    # join style for dashed lines
    # ---------- marker style -----------------------------------------------
    # marker="o",                # "o","s","D","^","v","<",">","p","*","h","+"
    # markersize=7,              # marker diameter (float)
    # markevery=2,               # plot a marker every N points (int/slice)
    # markeredgewidth=1.4,       # edge thickness of the marker
    # markeredgecolor="black",   # overrides auto edge-color from plot_line
    # markerfacecolor="white",   # already set by plot_line
    # fillstyle="full",          # "full","left","right","bottom","top","none"
    # ---------- error bars (use ax.errorbar instead of plot_line) ----------
    # ax.errorbar(x, y, yerr=0.1, xerr=None, fmt="o-", capsize=3,
    #             ecolor="gray", elinewidth=0.8)
)

plot_line(
    ax,
    x,
    y_cos,
    label="cos(x)",
    marker="s",
    # linestyle="--",
    # color="#e03a3e",
)

# === Axis labels & title ===================================================
ax.set_xlabel("Angle (rad)")
ax.set_ylabel("Amplitude")
ax.set_title("Exhaustive parameter checklist")
# ax.set_xlabel("x", fontsize=12, fontweight="bold", labelpad=8)
# ax.set_ylabel("y", fontsize=12, fontweight="bold", labelpad=8)
# ax.set_title("Title", fontsize=14, fontweight="bold", pad=12, loc="left")

# === Axis limits & scale ===================================================
# ax.set_xlim(0, 7)
# ax.set_ylim(-1.5, 1.5)
# ax.set_xscale("log")          # "linear", "log", "symlog", "logit"
# ax.set_yscale("log")
# ax.set_aspect("equal")        # "equal", "auto", or a float ratio
# ax.invert_yaxis()
# ax.invert_xaxis()

# === Ticks =================================================================
# ax.tick_params(axis="both", which="major",
#     direction="in",            # "in", "out", "inout"
#     length=6,                  # tick length in points
#     width=1.0,                 # tick width
#     labelsize=10,
#     labelcolor="0.2",
#     pad=4,                     # distance between tick and label
#     top=True, right=True,      # show ticks on secondary spines
#     bottom=True, left=True,
# )
# ax.tick_params(axis="both", which="minor",
#     direction="in", length=3, width=0.6,
# )
# ax.minorticks_on()
# ax.set_xticks([0, np.pi, 2*np.pi])
# ax.set_xticklabels(["0", "$\\pi$", "$2\\pi$"])
# ax.set_yticks(np.arange(-1, 1.5, 0.5))
# from matplotlib.ticker import MultipleLocator, AutoMinorLocator
# ax.xaxis.set_major_locator(MultipleLocator(1.0))
# ax.xaxis.set_minor_locator(AutoMinorLocator(2))

# === Grid ==================================================================
# ax.grid(True, which="major", axis="both",
#     color="0.85", linewidth=0.6, linestyle="-", alpha=0.7,
# )
# ax.grid(True, which="minor", axis="both",
#     color="0.92", linewidth=0.4, linestyle=":", alpha=0.5,
# )

# === Spines ================================================================
# for spine in ax.spines.values():
#     spine.set_linewidth(1.2)
#     spine.set_edgecolor("0.15")
# ax.spines["top"].set_visible(False)
# ax.spines["right"].set_visible(False)

# === Legend =================================================================
leg = ax.legend(
    # ---------- position ---------------------------------------------------
    loc="best",
    # loc="upper right",        # "upper/lower/center left/right", "best"
    # bbox_to_anchor=(1.05, 1), # manual placement (x, y) in axes coords
    # ncol=2,                   # number of columns
    # ---------- frame ------------------------------------------------------
    # frameon=True,
    # fancybox=False,            # False = square corners (old-school)
    # edgecolor="0.15",
    # facecolor="white",
    # framealpha=1.0,
    # ---------- text -------------------------------------------------------
    # fontsize=10,
    # title="Legend title",
    # title_fontsize=11,
    # labelspacing=0.4,          # vertical space between entries
    # handlelength=1.8,          # length of the legend line sample
    # handleheight=0.7,
    # handletextpad=0.6,         # space between handle and text
    # columnspacing=1.0,         # space between columns (if ncol > 1)
    # ---------- shadow & padding -------------------------------------------
    # shadow=False,
    # borderpad=0.5,
    # borderaxespad=0.5,
)
# leg.get_frame().set_linewidth(1.4)  # force legend frame thickness

# === Annotations / reference lines =========================================
# ax.axhline(y=0, color="0.4", linewidth=0.8, linestyle="--", zorder=0)
# ax.axvline(x=np.pi, color="0.4", linewidth=0.8, linestyle=":", zorder=0)
# ax.axhspan(ymin=-0.5, ymax=0.5, color="0.9", alpha=0.3, zorder=0)
# ax.axvspan(xmin=2, xmax=4, color="lightyellow", alpha=0.5, zorder=0)
# ax.fill_between(x, y_sin - 0.2, y_sin + 0.2, alpha=0.15, color="C0")
# ax.annotate("peak", xy=(np.pi/2, 1), xytext=(np.pi/2 + 1, 0.8),
#             arrowprops=dict(arrowstyle="->", color="0.3"),
#             fontsize=10, color="0.3")
# ax.text(0.95, 0.05, "some note", transform=ax.transAxes,
#         ha="right", va="bottom", fontsize=9, color="0.4",
#         bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="0.7"))

# === Secondary axis ========================================================
# ax2 = ax.twinx()
# ax2.set_ylabel("Secondary Y")
# ax2.plot(x, y_damped, color="gray", linestyle="--", label="damped")
# ax2.legend(loc="lower right")

# === Figure-level tweaks ===================================================
# fig.suptitle("Super title", fontsize=14, fontweight="bold", y=1.02)
# fig.subplots_adjust(left=0.12, right=0.95, top=0.90, bottom=0.12)
# fig.tight_layout()

plt.show()

# === Save ==================================================================
# save_figure(
#     fig, "demo_output/checklist_example",
#     formats=("png",),          # ("png",), ("png", "svg"), ("png", "svg", "emf")
#     # dpi=300,                  # override profile DPI
#     # transparent=False,
#     # declassify="both",        # "x", "y", "both", or None
#     # declassify_label="DECLASSIFIE",
#     # declassify_stamp_kw=dict(
#     #     fontsize=14,
#     #     color="0.20",
#     #     bbox=dict(edgecolor="0.20", linewidth=2.0),
#     # ),
# )

# %% [markdown]
# ---
# ## 22. Copy/paste template function
#
# Drop this function into your script, adjust the body, call it.


# %%
def make_figure(
    x_data,
    y_datasets: dict,
    *,
    profile="notebook",
    xlabel="x",
    ylabel="y",
    title="",
    save_path=None,
    declassify=None,
):
    """Ready-to-use template: one figure, N curves, optional export.

    Parameters
    ----------
    x_data : array-like
    y_datasets : dict
        ``{label: (y_array, marker)}``  — marker can be ``None``.
    profile : str
        ``"notebook"``, ``"slides"``, or ``"paper"``.
    save_path : str or None
        Base path without extension.  ``None`` = no export.
    declassify : str or None
        ``"x"``, ``"y"``, ``"both"``, or ``None``.
    """
    use_style(profile)

    fig, ax = plt.subplots()

    for label, (y, mkr) in y_datasets.items():
        kw = dict(label=label)
        if mkr:
            kw["marker"] = mkr
        plot_line(ax, x_data, y, **kw)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    make_legend(ax)

    if save_path:
        save_figure(fig, save_path, formats=("png",), declassify=declassify, report=True)
    else:
        plt.show()

    return fig, ax


# --- Example call ---
fig, ax = make_figure(
    x,
    {
        "sin(x)": (y_sin, "o"),
        "cos(x)": (y_cos, "s"),
        "damped": (y_damped, "D"),
    },
    xlabel="Angle (rad)",
    ylabel="Amplitude",
    title="Template function demo",
    save_path="demo_output/template_demo",
    declassify="both",
)

# %% [markdown]
# ---
# ---
# # Part 2 — 2D Field Visualization
#
# The sections below demonstrate the 2D scalar and vector field helpers
# added to the `cfd_plot` package.  The same principle holds:
# **Matplotlib is the real API.**  These helpers add validation,
# colorbar handling, and CFD-friendly defaults.
#
# ---
# ## 23. Scalar field — `plot_contourf`
#
# Filled contours on a Gaussian scalar field.  Coordinates can be
# 1D vectors **or** 2D meshgrid arrays — the package normalises them.

# %%
np.random.seed(0)
x2d = np.linspace(-2, 2, 161)
y2d = np.linspace(-1.5, 1.5, 121)
X2d, Y2d = np.meshgrid(x2d, y2d, indexing="xy")

P_field = np.exp(-(X2d**2 + Y2d**2))

use_style("paper")
fig, ax = plt.subplots()
cf, cbar = plot_contourf(ax, x2d, y2d, P_field, levels=20, cmap="viridis",
                         cbar_label="Pressure coefficient")
set_title(ax, "Filled contour — Gaussian field")
ax.set_xlabel("x")
ax.set_ylabel("y")
save_figure(fig, "demo_output/2d_contourf", formats=("png",), report=True)
plt.show()

# %% [markdown]
# ---
# ## 24. Scalar field — `plot_pcolormesh`
#
# Pseudocolor mesh — the best default for large structured CFD fields.
# Supports non-uniform grids and the `rasterized` flag for lighter
# SVG/PDF export.

# %%
use_style("notebook")
fig, ax = plt.subplots()
qm, cbar = plot_pcolormesh(ax, X2d, Y2d, P_field, cmap="coolwarm",
                           cbar_label="Pressure")
set_title(ax, "pcolormesh — 2D meshgrid input")
ax.set_xlabel("x")
ax.set_ylabel("y")
plt.show()

# %% [markdown]
# ---
# ## 25. Scalar field — `plot_imshow`
#
# Best for uniformly spaced Cartesian grids.  Always pass `extent`
# to get physical coordinates.  Uses `origin="lower"` by default.

# %%
use_style("notebook")
fig, ax = plt.subplots()
im, cbar = plot_imshow(ax, P_field,
                       extent=(x2d.min(), x2d.max(), y2d.min(), y2d.max()),
                       cmap="inferno", cbar_label="Scalar")
set_title(ax, "imshow — uniform Cartesian grid")
ax.set_xlabel("x")
ax.set_ylabel("y")
plt.show()

# %% [markdown]
# ---
# ## 26. Contour lines — `plot_contour`
#
# Isolines overlaid on a filled contour background.  Pass `colors="k"`
# for black lines or use a colormap.

# %%
use_style("paper")
fig, ax = plt.subplots()
plot_contourf(ax, x2d, y2d, P_field, levels=20, cmap="viridis", cbar_label="Pressure")
plot_contour(ax, x2d, y2d, P_field, levels=8, colors="k", linewidths=0.5,
             aspect=None)
set_title(ax, "Filled contours + isolines overlay")
ax.set_xlabel("x")
ax.set_ylabel("y")
plt.show()

# %% [markdown]
# ---
# ## 27. Vector field — `plot_quiver`
#
# Solid-body rotation field.  Use `stride` to keep the plot readable
# on dense grids.  `magnitude_color=True` colours arrows by speed.

# %%
U2d = -Y2d
V2d = X2d

use_style("notebook")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

plot_quiver(ax1, x2d, y2d, U2d, V2d, stride=8, color="k", scale=30)
set_title(ax1, "Quiver — black arrows, stride=8")
ax1.set_xlabel("x")
ax1.set_ylabel("y")

plot_quiver(ax2, x2d, y2d, U2d, V2d, stride=6, magnitude_color=True,
            colorbar=True, cbar_label="|V|", scale=30)
set_title(ax2, "Quiver — magnitude colouring")
ax2.set_xlabel("x")
ax2.set_ylabel("y")

plt.tight_layout()
plt.show()

# %% [markdown]
# ---
# ## 28. Streamlines — `plot_streamplot`
#
# Streamlines show flow topology better than quiver.  Colour by speed
# or another scalar for extra information.

# %%
speed = compute_speed(U2d, V2d)

use_style("paper")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

plot_streamplot(ax1, x2d, y2d, U2d, V2d, density=1.5, color="0.3")
set_title(ax1, "Streamlines — uniform colour")
ax1.set_xlabel("x")
ax1.set_ylabel("y")

plot_streamplot(ax2, x2d, y2d, U2d, V2d, color=speed, cmap="plasma",
                density=1.5, colorbar=True, cbar_label="Speed")
set_title(ax2, "Streamlines — coloured by speed")
ax2.set_xlabel("x")
ax2.set_ylabel("y")

plt.tight_layout()
plt.show()

# %% [markdown]
# ---
# ## 29. Combined — `plot_contour_quiver`
#
# Scalar background + quiver overlay in one call.  Use for pressure
# with velocity direction, temperature with recirculation, etc.

# %%
use_style("paper")
fig, ax = plt.subplots(figsize=(8, 5))
artist, q, cbar = plot_contour_quiver(
    ax, x2d, y2d, P_field, U2d, V2d,
    scalar_kind="contourf",
    levels=24,
    cmap="coolwarm",
    cbar_label="Pressure coefficient",
    quiver_stride=8,
    quiver_color="k",
    quiver_scale=30,
)
set_title(ax, "Pressure field + velocity vectors")
set_subtitle(ax, "Solid-body rotation, Gaussian pressure")
ax.set_xlabel("x")
ax.set_ylabel("y")
save_figure(fig, "demo_output/2d_contour_quiver", formats=("png",), report=True)
plt.show()

# %% [markdown]
# ---
# ## 30. Data prep — `reshape_structured2d`
#
# Reconstruct 2D arrays from flattened `(x, y, value)` exports — common
# after CSV or text-file extraction from a CFD solver.

# %%
x_flat = X2d.ravel()
y_flat = Y2d.ravel()
p_flat = P_field.ravel()
u_flat = U2d.ravel()

X_rec, Y_rec, fields = reshape_structured2d(
    x_flat, y_flat, {"p": p_flat, "u": u_flat}
)
print(f"Reconstructed grid: {X_rec.shape}")
assert np.allclose(fields["p"], P_field)
print("reshape_structured2d: round-trip validated")

# %% [markdown]
# ---
# ## 31. Data prep — `dataframe_to_grid`
#
# Pivot a pandas DataFrame into structured 2D arrays.

# %%
import pandas as pd

df = pd.DataFrame({
    "x": x_flat,
    "y": y_flat,
    "p": p_flat,
    "u": u_flat,
    "v": V2d.ravel(),
})

xg, yg, flds = dataframe_to_grid(df, values=["p", "u", "v"])
print(f"Grid from DataFrame: xg({len(xg)}), yg({len(yg)}), p{flds['p'].shape}")

use_style("notebook")
fig, ax = plt.subplots()
Xg, Yg = np.meshgrid(xg, yg, indexing="xy")
plot_pcolormesh(ax, Xg, Yg, flds["p"], cmap="viridis", cbar_label="Pressure")
plot_quiver(ax, Xg, Yg, flds["u"], flds["v"], stride=8, color="k",
            scale=30, aspect=None)
set_title(ax, "Field from DataFrame")
ax.set_xlabel("x")
ax.set_ylabel("y")
plt.show()

# %% [markdown]
# ---
# ## 32. 3D slice extraction — `extract_slice2d`
#
# Extract a 2D plane from a 3D scalar array and plot it directly.
# The function returns meshgrid coordinates ready for plotting.

# %%
x3 = np.linspace(-1, 1, 41)
y3 = np.linspace(-1, 1, 51)
z3 = np.linspace(0, 2, 31)
X3, Y3, Z3 = np.meshgrid(x3, y3, z3, indexing="ij")
field_3d = np.exp(-(X3**2 + Y3**2 + (Z3 - 1)**2))

H, V, p_slice = extract_slice2d(
    field_3d, axis="z", coord=1.0, x=x3, y=y3, z=z3,
)
print(f"Slice shape: {p_slice.shape}, coord grids: {H.shape}")

use_style("paper")
fig, ax = plt.subplots()
plot_pcolormesh(ax, H, V, p_slice, cmap="inferno", cbar_label="Scalar")
set_title(ax, "2D slice from 3D field (z = 1.0)")
ax.set_xlabel("x")
ax.set_ylabel("y")
save_figure(fig, "demo_output/2d_slice", formats=("png",), report=True)
plt.show()

# %% [markdown]
# ---
# ## 33. Diverging colormaps — signed fields
#
# Use `TwoSlopeNorm` for fields with a meaningful zero (vorticity,
# pressure fluctuation).  Fix `vmin`/`vmax` for comparative plots.

# %%
from matplotlib.colors import TwoSlopeNorm

vorticity = np.sin(2 * np.pi * X2d) * np.cos(2 * np.pi * Y2d)

use_style("paper")
fig, ax = plt.subplots()
norm = TwoSlopeNorm(vmin=-1, vcenter=0, vmax=1)
plot_pcolormesh(ax, x2d, y2d, vorticity, cmap="RdBu_r", norm=norm,
                cbar_label="Vorticity [1/s]")
set_title(ax, "Signed field — diverging colormap")
ax.set_xlabel("x")
ax.set_ylabel("y")
plt.show()

# %% [markdown]
# ---
# ## 34. 2D with metadata — `add_textbox` + `set_title`
#
# All existing annotation helpers work seamlessly with 2D plots.

# %%
use_style("paper")
fig, ax = plt.subplots(figsize=(8, 5))
plot_contourf(ax, x2d, y2d, P_field, levels=20, cmap="viridis",
              cbar_label="Pressure coefficient")
set_title(ax, r"Pressure field — $M_\infty = 0.85$, $Re = 6.5 \times 10^6$")
add_textbox(ax, "SA turbulence model\nMesh: 12M cells", loc="lower right",
            fontsize=8)
ax.set_xlabel("x/c")
ax.set_ylabel("y/c")
save_figure(fig, "demo_output/2d_annotated", formats=("png",), report=True)
plt.show()

# %% [markdown]
# ---
# ## 35. Figure-level legend — `make_figure_legend`
#
# When multiple subplots share the same series, collect all labels into
# a single legend placed outside the plot area (e.g. to the right).

# %%
use_style("paper")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

plot_line(ax1, x, y_sin, label="sin(x)")
plot_line(ax1, x, y_cos, marker="s", label="cos(x)")
set_title(ax1, "Panel A")
ax1.set_xlabel("x")
ax1.set_ylabel("f(x)")

plot_line(ax2, x, y_sin, label="sin(x)")
plot_line(ax2, x, -y_sin, marker="^", label="-sin(x)")
set_title(ax2, "Panel B")
ax2.set_xlabel("x")
ax2.set_ylabel("f(x)")

fig.tight_layout()
fig.subplots_adjust(right=0.82)
make_figure_legend(fig, bbox_to_anchor=(1.0, 0.5))
plt.show()

# %% [markdown]
# ---
# ## 36. Shared colorbar — `add_shared_colorbar`
#
# For multi-panel 2D plots with the **same** scalar range, disable
# per-axes colorbars and add one shared colorbar whose height matches
# the axes group.

# %%
use_style("paper")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))

cf1, _ = plot_contourf(ax1, x2d, y2d, P_field, levels=20,
                        cmap="viridis", colorbar=False)
set_title(ax1, "Field A")
ax1.set_xlabel("x")
ax1.set_ylabel("y")

vorticity = np.sin(2 * np.pi * X2d) * np.cos(2 * np.pi * Y2d)
cf2, _ = plot_contourf(ax2, x2d, y2d, P_field * 0.8, levels=20,
                        cmap="viridis", colorbar=False)
set_title(ax2, "Field B (scaled)")
ax2.set_xlabel("x")
ax2.set_ylabel("y")

fig.tight_layout()
fig.subplots_adjust(right=0.88)
add_shared_colorbar(fig, cf1, axes=[ax1, ax2], label="Pressure coefficient")
save_figure(fig, "demo_output/2d_shared_cbar", formats=("png",), report=True)
plt.show()

# %% [markdown]
# ---
# ## 37. Nodal interpolation — `plot_pcolormesh_interp`
#
# When data lives at mesh **nodes** (not cell centers), `pcolormesh`
# draws a blocky per-cell colouring.  `plot_pcolormesh_interp`
# refines the grid with SciPy before plotting.

# %%
x_coarse = np.linspace(-2, 2, 21)
y_coarse = np.linspace(-1.5, 1.5, 16)
Xc, Yc = np.meshgrid(x_coarse, y_coarse, indexing="xy")
Z_coarse = np.exp(-(Xc**2 + Yc**2))

use_style("paper")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

plot_pcolormesh(ax1, x_coarse, y_coarse, Z_coarse, cmap="inferno",
                cbar_label="Raw nodal (blocky)")
set_title(ax1, "Before interpolation")
ax1.set_xlabel("x")
ax1.set_ylabel("y")

plot_pcolormesh_interp(ax2, x_coarse, y_coarse, Z_coarse, factor=4,
                       method="cubic", cmap="inferno",
                       cbar_label="Interpolated (smooth)")
set_title(ax2, "After interpolation (factor=4)")
ax2.set_xlabel("x")
ax2.set_ylabel("y")

save_figure(fig, "demo_output/2d_interpolation", formats=("png",), report=True)
plt.show()

# %% [markdown]
# ---
# ## 38. Threshold dead zone — overlay on an existing plot
#
# Plot a scalar field normally (with its own colorbar), then overlay
# a black dead zone where an indicator `IND < threshold`.  The dead
# zone is a simple `contourf` call with `colors="black"` on top of
# whatever was already drawn — no extra colorbar, no interaction with
# the existing colormap.

# %%
IND = P_field.copy()
threshold = 0.9

use_style("paper")
fig, ax = plt.subplots(figsize=(8, 5))

plot_contourf(ax, x2d, y2d, P_field, levels=20, cmap="coolwarm",
              cbar_label="Pressure coefficient")

ax.contourf(X2d, Y2d, IND, levels=[-np.inf, threshold], colors="black")

set_title(ax, f"Pressure field + dead zone (IND < {threshold})")
ax.set_xlabel("x")
ax.set_ylabel("y")

save_figure(fig, "demo_output/2d_threshold", formats=("png",), report=True)
plt.show()

# %% [markdown]
# ---
# ## 39. Region filtering with masking — `mask_field` / `dataframe_to_masked_grid`
#
# When your DataFrame carries a region indicator such as `IND`, **do not
# drop rows** to filter.  Instead, pivot the *full* grid and mask excluded
# regions.  Masked positions become transparent holes in the plot while
# the structured grid topology stays intact.
#
# This section shows two approaches:
#
# 1. **`dataframe_to_masked_grid`** — end-to-end from DataFrame.
# 2. **`mask_field`** — standalone, when you already have 2D arrays.

# %%
import pandas as pd

x_mg = np.linspace(-2, 2, 81)
y_mg = np.linspace(-1.5, 1.5, 61)
Xm, Ym = np.meshgrid(x_mg, y_mg, indexing="xy")
Pm = np.exp(-(Xm**2 + Ym**2))
IND_mg = np.where(Xm**2 + Ym**2 < 0.5, 1, 0).astype(float)

df_cfd = pd.DataFrame({
    "x": Xm.ravel(), "y": Ym.ravel(),
    "p": Pm.ravel(), "IND": IND_mg.ravel(),
})

# --- Approach 1: dataframe_to_masked_grid (masked array output) ----------
use_style("paper")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

xg, yg, P_masked = dataframe_to_masked_grid(
    df_cfd, values="p", mask_column="IND", mask_value=0,
)
plot_pcolormesh(ax1, xg, yg, P_masked, cmap="viridis",
                cbar_label="Pressure (masked array)")
set_title(ax1, "keep IND==0  →  MaskedArray")
ax1.set_xlabel("x")
ax1.set_ylabel("y")

# --- Approach 2: mask_field with fill=np.nan on existing 2D arrays -------
xg2, yg2, fields = dataframe_to_grid(df_cfd, values=["p", "IND"])
P_nan = mask_field(fields["p"], fields["IND"] != 0, fill=np.nan)
plot_pcolormesh(ax2, xg2, yg2, P_nan, cmap="viridis",
                cbar_label="Pressure (NaN fill)")
set_title(ax2, "mask_field(fill=np.nan)")
ax2.set_xlabel("x")
ax2.set_ylabel("y")

fig.tight_layout()
save_figure(fig, "demo_output/2d_masked_filtering", formats=("png",), report=True)
plt.show()

# %% [markdown]
# Both approaches produce the same visual: a Gaussian field with the
# inner circle removed.  The left panel uses a `MaskedArray` (preferred
# when you may need the original values later); the right panel uses
# `NaN` fill (simpler, but irreversible).

# %% [markdown]
# ---
# ## 40. Filling masked regions with a colour — `bad_color`
#
# By default, masked / `NaN` cells are transparent.  Pass `bad_color`
# to any scalar plotting function to fill them with a solid colour
# instead — useful for walls, solid zones, or out-of-domain regions.

# %%
use_style("paper")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)

plot_pcolormesh(ax1, xg, yg, P_masked, cmap="viridis",
                cbar_label="Pressure", bad_color="black")
set_title(ax1, "bad_color='black' (solid walls)")
ax1.set_xlabel("x")
ax1.set_ylabel("y")

plot_contourf(ax2, xg, yg, P_masked, levels=20, cmap="coolwarm",
              cbar_label="Pressure", bad_color="0.3")
set_title(ax2, "bad_color='0.3' (dark grey)")
ax2.set_xlabel("x")
ax2.set_ylabel("y")
save_figure(fig, "demo_output/2d_bad_color", formats=("png",), report=True)
plt.show()

# %% [markdown]
# ---
# ## 41. Outlining the fluid-solid boundary — `mask_outline`
#
# Masking hides the solid region; `bad_color` fills it.  To **draw a
# black line along the interface** without altering the colour fill,
# pass the original indicator mask via `mask_outline`.  The boundary
# is traced with `ax.contour` at the 0.5 iso-level of a float version
# of the mask, so it works with both `MaskedArray` and `NaN` workflows.

# %%
use_style("paper")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5), constrained_layout=True)

fluid_mask = IND_mg == 0

plot_pcolormesh(ax1, xg, yg, P_masked, cmap="viridis",
                cbar_label="Pressure", bad_color="lightgrey",
                mask_outline=fluid_mask, mask_outline_color="k",
                mask_outline_width=1.5)
set_title(ax1, "pcolormesh + mask_outline")
ax1.set_xlabel("x")
ax1.set_ylabel("y")

plot_contourf(ax2, xg, yg, P_masked, levels=20, cmap="coolwarm",
              cbar_label="Pressure", bad_color="lightgrey",
              mask_outline=fluid_mask, mask_outline_color="k",
              mask_outline_width=1.5)
set_title(ax2, "contourf + mask_outline")
ax2.set_xlabel("x")
ax2.set_ylabel("y")

save_figure(fig, "demo_output/2d_mask_outline", formats=("png",), report=True)
plt.show()

# %% [markdown]
# The left panel uses `plot_pcolormesh` and the right `plot_contourf`.
# In both cases the solid region is filled light grey (`bad_color`) and
# the fluid-solid interface is cleanly delineated with a black contour.
# You can customise `mask_outline_width`, `mask_outline_color`, and
# `mask_outline_zorder` as needed.

# %% [markdown]
# ---
# ## Function reference
#
# | Function | Purpose |
# |---|---|
# | `use_style("notebook"\|"slides"\|"paper")` | Apply a profile globally |
# | `style_context("slides")` | Context manager for a temporary profile |
# | `new_figure(profile="paper", figsize=...)` | Create a figure with an embedded profile |
# | `plot_line(ax, x, y, marker="o", ...)` | Plot with white-filled markers |
# | `apply_marker_style(line)` | Restyle an existing `Line2D` |
# | `make_legend(ax, ...)` | Legend with old-style thick frame (returns `Legend`) |
# | `plot_with_band(ax, x, y, y_low=..., ...)` | Line + shaded uncertainty band |
# | `add_reference_lines(ax, hlines=..., vlines=...)` | Horizontal / vertical reference lines |
# | `apply_oldschool_axes(ax)` | Cosmetic polish (spines, ticks, legend) |
# | `add_textbox(ax, text, loc=..., ...)` | Anchored metadata text box |
# | `set_subtitle(ax, text, ...)` | Subtitle line below the axes title (title font − 1 pt) |
# | `set_axis_sci(ax, axis="y", ...)` | Clean scientific notation on axis |
# | `annotate_point(ax, text, xy=..., ...)` | Annotation arrow with consistent styling |
# | `plot_bar(ax, categories, values, ...)` | Bar chart with old-style edge styling |
# | `dual_axis(ax, ylabel=..., color=...)` | Styled secondary Y-axis (twinx) |
# | `make_figure_legend(fig, ...)` | Single legend for multi-axes figures |
# | `add_shared_colorbar(fig, mappable, ...)` | Shared colorbar matching axes height |
# | `plot_contour(ax, x, y, z, ...)` | 2D contour lines |
# | `plot_contourf(ax, x, y, z, ...)` | 2D filled contours |
# | `plot_pcolormesh(ax, x, y, z, ...)` | 2D pseudocolor mesh |
# | `plot_pcolormesh_interp(ax, x, y, z, ...)` | Interpolated 2D pseudocolor mesh |
# | `interpolate_field2d(x, y, z, ...)` | Refine a nodal field (SciPy) |
# | `plot_imshow(ax, z, ...)` | 2D image display (uniform grids) |
# | `plot_quiver(ax, x, y, u, v, ...)` | 2D quiver (arrow) plot |
# | `plot_streamplot(ax, x, y, u, v, ...)` | 2D streamlines |
# | `plot_contour_quiver(ax, x, y, z, u, v, ...)` | Scalar background + quiver overlay |
# | `compute_speed(u, v)` | Velocity magnitude |
# | `subsample_vectors(x, y, u, v, ...)` | Downsample vectors for readability |
# | `reshape_structured2d(x, y, values)` | Flattened export → 2D arrays |
# | `dataframe_to_grid(df, ...)` | DataFrame → structured 2D arrays |
# | `mask_field(z, condition, ...)` | Mask a 2D field (returns MaskedArray or NaN) |
# | `dataframe_to_masked_grid(df, ...)` | DataFrame → masked structured 2D arrays |
# | `extract_slice2d(field, axis=..., ...)` | 3D array → 2D slice |
# | `save_figure(fig, path, ..., report=True)` | Export + optional Rich summary table |
# | `print_file_report(files)` | Pretty-print a list of exported files |
#
# ### Cleanup

# %%
import shutil

if os.path.isdir("demo_output"):
    shutil.rmtree("demo_output")
    print("demo_output/ removed.")
else:
    print("Nothing to clean up.")
