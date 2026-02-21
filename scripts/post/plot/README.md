# plotting -- Matplotlib Figure Template

A thin wrapper around Matplotlib that adds professional defaults
(old-school framed axes, white-filled markers, thick legend borders)
while keeping full access to the underlying API.

## Quick start

```python
import numpy as np
import matplotlib.pyplot as plt
from plotting import use_style, plot_line, make_legend, save_figure

use_style("notebook")                       # or "slides", "paper"

x = np.linspace(0, 2 * np.pi, 25)
fig, ax = plt.subplots()
plot_line(ax, x, np.sin(x), label="sin(x)")
plot_line(ax, x, np.cos(x), marker="s", label="cos(x)")
ax.set_xlabel("x")
ax.set_ylabel("f(x)")
make_legend(ax)

save_figure(fig, "output/my_figure", formats=("png", "svg"), report=True)
```

## Style profiles

| Profile    | Target                  | Grid | Font   | Figsize  |
|------------|-------------------------|------|--------|----------|
| `notebook` | Interactive exploration | On   | Sans   | 8 x 5    |
| `slides`   | Presentations           | On   | Sans   | 12 x 7   |
| `paper`    | Publication / report    | Off  | Serif  | 6 x 4    |

All three profiles share: 4 visible spines, inward ticks, opaque framed legend,
`patch.linewidth` for thick legend borders, and `mathtext.fontset` matching the body font.

## Function reference

### Style management

#### `use_style(profile="notebook")`

Apply a profile globally (modifies rcParams in place).

```python
use_style("paper")
```

#### `style_context(profile="notebook")`

Context manager -- profile applies only inside the `with` block.

```python
with style_context("slides"):
    fig, ax = plt.subplots()
    ...
```

#### `new_figure(nrows=1, ncols=1, *, profile=None, figsize=None, **subplots_kw)`

Wrapper around `plt.subplots()` that optionally applies a profile to this figure only.

```python
fig, ax = new_figure(profile="paper", figsize=(10, 3))
```

### Line plotting

#### `plot_line(ax, x, y, *, marker="o", label=None, **kwargs) -> Line2D`

Like `ax.plot()` but automatically sets white-filled markers with edge color matching
the line. All `ax.plot()` kwargs are forwarded.

```python
plot_line(ax, x, y, marker="s", label="data", linestyle="--")
```

#### `apply_marker_style(line)`

Retrofit the white-face + colored-edge marker style onto an existing `Line2D`.

```python
line, = ax.plot(x, y, "o-", label="data")
apply_marker_style(line)
```

#### `plot_with_band(ax, x, y, *, y_low=None, y_high=None, band_alpha=0.15, band_color=None, band_label=None, **line_kwargs) -> (Line2D, PolyCollection | None)`

Line + shaded uncertainty band via `fill_between`.

- Pass `y_low` only for a symmetric band (y +/- y_low).
- Pass both `y_low` and `y_high` for explicit boundaries.

```python
plot_with_band(ax, x, y, y_low=0.1, label="mean", marker="o")
plot_with_band(ax, x, y, y_low=y - err, y_high=y + err, label="range")
```

#### `plot_bar(ax, categories, values, *, label=None, color=None, edgecolor="0.15", edgewidth=None, **kwargs) -> BarContainer`

Bar chart with old-style edge styling. All `ax.bar()` kwargs forwarded.

```python
plot_bar(ax, ["A", "B", "C"], [3, 7, 5], label="y+", color="C0")
```

### Legend and annotations

#### `make_legend(ax, *, frame_linewidth=None, **kwargs) -> Legend`

Creates a legend with old-style defaults (square corners, opaque white background,
thick frame). Returns the `Legend` for further tweaking.

```python
make_legend(ax)
make_legend(ax, loc="upper left", ncol=2, title="Curves", frame_linewidth=2.0)
```

#### `add_textbox(ax, text, *, loc="upper right", fontsize=None, **kwargs) -> Text`

Anchored text box for case metadata. Four corner positions: `"upper left"`,
`"upper right"`, `"lower left"`, `"lower right"`.

```python
add_textbox(ax, "Ma = 0.85\nRe = 6.5e6\nMesh: 12M cells", loc="lower right")
```

#### `annotate_point(ax, text, xy, *, xytext=None, offset=(30, 20), **kwargs) -> Annotation`

Clean annotation arrow. Uses offset in points by default, or explicit data
coordinates when `xytext` is given.

```python
annotate_point(ax, "peak", xy=(np.pi/2, 1.0), offset=(40, -20))
annotate_point(ax, "origin", xy=(0, 0), xytext=(1, 0.5))
```

### Axes helpers

#### `add_reference_lines(ax, *, hlines=None, vlines=None, **kwargs) -> list[Line2D]`

Draw horizontal and/or vertical dashed reference lines.

```python
add_reference_lines(ax, hlines=[0, 1], vlines=[np.pi], color="0.5", linestyle=":")
```

#### `apply_oldschool_axes(ax, *, legend=True, legend_kwargs=None)`

Cosmetic polish: enforces spine width/color, inward ticks on all four sides,
and optionally creates the legend via `make_legend`.

```python
apply_oldschool_axes(ax)
apply_oldschool_axes(ax, legend=False)
```

#### `set_axis_sci(ax, axis="y", *, scilimits=(0, 0), useMathText=True, useOffset=True)`

Force clean scientific notation on an axis. Useful for residuals or small quantities.

```python
set_axis_sci(ax, axis="y")
set_axis_sci(ax, axis="both", scilimits=(-2, 2))
```

#### `dual_axis(ax, *, ylabel="", color=None) -> Axes`

Create a styled secondary Y-axis (twinx) with inward ticks. Optional `color`
tints the right spine, ticks, and label.

```python
ax2 = dual_axis(ax, ylabel="Temperature (K)", color="C1")
ax2.plot(x, temp, color="C1")
```

### Export

#### `save_figure(fig, path, *, formats=("png",), dpi=None, transparent=None, declassify=None, declassify_label="DECLASSIFIE", declassify_stamp_kw=None, report=False) -> list[Path]`

Export the figure to one or more formats. Optionally produces a declassified
variant with ticks/labels stripped and a boxed stamp.

| Parameter              | Description                                            |
|------------------------|--------------------------------------------------------|
| `formats`              | `("png",)`, `("png", "svg")`, `("png", "svg", "emf")` |
| `declassify`           | `"x"`, `"y"`, `"both"`, or `None`                     |
| `declassify_label`     | Custom stamp text (default `"DECLASSIFIE"`)            |
| `declassify_stamp_kw`  | Override stamp style (fontsize, color, bbox, ...)      |
| `report`               | Print a Rich summary table of exported files           |

```python
save_figure(fig, "output/fig1", formats=("png", "svg"), declassify="both", report=True)
```

#### `print_file_report(files, *, title="Exported files")`

Pretty-print a summary table of files (uses Rich when installed, plain text otherwise).

```python
print_file_report(files, title="CFD results")
```

## Dependencies

- **Required**: `matplotlib`, `numpy`
- **Optional**: `rich` (pretty terminal output), Inkscape (EMF export)

## Files

```
scripts/post/plot/
    demo_plotting.py           # Tutorial / template (runnable)
    pyproject.toml             # Ruff configuration
    plotting/
        __init__.py            # Public API
        mpl_template.py        # All helpers
        styles/
            notebook.mplstyle
            slides.mplstyle
            paper.mplstyle
```
