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

#### `make_figure_legend(fig, axes=None, *, loc="center right", bbox_to_anchor=(1.02, 0.5), ncol=1, dedupe=True, ...) -> Legend`

Single legend for the whole figure, collecting handles from multiple axes.
Duplicate labels are removed by default.

```python
fig, (ax1, ax2) = plt.subplots(1, 2)
plot_line(ax1, x, y1, label="Exp")
plot_line(ax2, x, y2, label="CFD")
fig.tight_layout()
fig.subplots_adjust(right=0.85)
make_figure_legend(fig, bbox_to_anchor=(1.02, 0.5))
```

#### `add_shared_colorbar(fig, mappable, *, axes, location="right", size="2%", pad=0.02, match_axes=True, label=None, ...) -> Colorbar`

Shared colorbar whose height (or width) matches a group of axes.
The default `size` and `pad` are deliberately tight so the colorbar sits
close to the subplots without a large gap.

```python
fig, (ax1, ax2) = plt.subplots(1, 2)
cf1, _ = plot_contourf(ax1, x, y, Z1, colorbar=False)
cf2, _ = plot_contourf(ax2, x, y, Z2, colorbar=False)
fig.tight_layout()
fig.subplots_adjust(right=0.90)
add_shared_colorbar(fig, cf1, axes=[ax1, ax2], label="Pressure [Pa]")
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

---

## 2D field plotting

The package extends to practical 2D scalar and vector field visualization
for CFD post-processing.  The same philosophy applies: thin Matplotlib
wrappers, axes-first API, full `**kwargs` forwarding, and seamless use
with `use_style` / `save_figure`.

### Quick start (2D)

```python
import numpy as np
import matplotlib.pyplot as plt
from plotting import use_style, plot_contourf, plot_quiver, save_figure

use_style("paper")

x = np.linspace(-1, 1, 101)
y = np.linspace(-1, 1, 81)
X, Y = np.meshgrid(x, y, indexing="xy")
P = np.exp(-(X**2 + Y**2))
U, V = -Y, X

fig, ax = plt.subplots()
plot_contourf(ax, x, y, P, levels=20, cmap="coolwarm", cbar_label="Pressure")
plot_quiver(ax, x, y, U, V, stride=6, color="k", scale=30, aspect=None)
ax.set_xlabel("x")
ax.set_ylabel("y")
save_figure(fig, "output/field_2d", formats=("png",), report=True)
```

### Scalar field functions

All scalar field functions accept **either** 1D coordinate vectors
`x(nx,)`, `y(ny,)` **or** 2D meshgrid arrays `X(ny, nx)`, `Y(ny, nx)`,
plus a 2D scalar field `z(ny, nx)`.  They return `(artist, colorbar)`.

All accept an optional `bad_color` parameter (e.g. `bad_color="black"`)
that fills masked or `NaN` cells with a solid colour instead of leaving
them transparent.

#### `plot_contour(ax, x, y, z, *, levels=15, ...) -> (QuadContourSet, Colorbar | None)`

Contour lines.  Use for isolines (pressure levels, isotherms).

```python
cs, cbar = plot_contour(ax, x, y, Z, levels=10, colors="k", linewidths=0.5)
```

#### `plot_contourf(ax, x, y, z, *, levels=20, cmap="viridis", ...) -> (QuadContourSet, Colorbar | None)`

Filled contours.  Best for smooth report-style scalar maps.

```python
cf, cbar = plot_contourf(ax, x, y, Z, levels=30, cmap="inferno", cbar_label="T [K]")
```

#### `plot_pcolormesh(ax, x, y, z, *, cmap="viridis", shading="auto", ...) -> (QuadMesh, Colorbar | None)`

Pseudocolor mesh.  Best default for large structured CFD fields.

```python
qm, cbar = plot_pcolormesh(ax, x, y, Z, cmap="RdBu_r", cbar_label="Vorticity [1/s]")
```

#### `plot_imshow(ax, z, *, extent=None, origin="lower", ...) -> (AxesImage, Colorbar | None)`

Image display.  Use only for uniformly spaced Cartesian grids.  Always
provide `extent` for physical coordinates.

```python
im, cbar = plot_imshow(ax, Z, extent=(-1, 1, -1, 1), cbar_label="p [Pa]")
```

### Nodal interpolation

When CFD data is defined at **grid nodes** (not cell centers), `pcolormesh`
renders a blocky per-cell colouring.  The interpolation helpers refine the
grid with SciPy before plotting, producing smooth visuals.

#### `interpolate_field2d(x, y, z, *, factor=2, method="cubic") -> (xi, yi, zi)`

Refine a structured 2D scalar field onto a denser grid.

- `factor`: refinement multiplier per axis (e.g. `4` quadruples resolution).
- `method`: `"cubic"` (default, smooth) or `"linear"`.

```python
xi, yi, zi = interpolate_field2d(x, y, Z, factor=4, method="cubic")
plot_pcolormesh(ax, xi, yi, zi, cbar_label="Smooth field")
```

#### `plot_pcolormesh_interp(ax, x, y, z, *, factor=2, method="cubic", ...) -> (QuadMesh, Colorbar | None, (xi, yi, zi))`

One-call interpolation + plotting.  Returns the interpolated grid for reuse.

```python
qm, cbar, (xi, yi, zi) = plot_pcolormesh_interp(
    ax, x, y, Z_nodal, factor=4, cmap="inferno", cbar_label="Temperature [K]",
)
```

**Performance note**: high `factor` on large grids consumes memory
proportionally to `factor**2`.  A factor of 2--4 is usually sufficient.

### Vector field functions

#### `plot_quiver(ax, x, y, u, v, *, stride=None, magnitude_color=False, ...) -> (Quiver, Colorbar | None)`

Arrow plot.  Use `stride` to subsample dense grids for readability.

```python
q, cbar = plot_quiver(ax, x, y, U, V, stride=5, color="k", scale=40)
q, cbar = plot_quiver(ax, x, y, U, V, stride=4, magnitude_color=True,
                      colorbar=True, cbar_label="|V| [m/s]")
```

#### `plot_streamplot(ax, x, y, u, v, *, density=1.2, ...) -> (StreamplotSet, Colorbar | None)`

Streamlines.  Best for flow topology, separations, recirculation.
Requires monotonic 1D coordinates (extracted automatically from 2D arrays).

```python
speed = compute_speed(U, V)
sp, cbar = plot_streamplot(ax, x, y, U, V, color=speed, cmap="plasma",
                           colorbar=True, cbar_label="Speed [m/s]")
```

#### `compute_speed(u, v) -> ndarray`

Velocity magnitude: `sqrt(u**2 + v**2)`.

#### `subsample_vectors(x, y, u, v, *, stride=None, target=25) -> (xs, ys, us, vs)`

Downsample a vector field.  Pass `stride` as an int or `(sy, sx)` tuple,
or let `target` choose automatically.

### Combined plots

#### `plot_contour_quiver(ax, x, y, z, u, v, *, scalar_kind="contourf", ...) -> (artist, Quiver, Colorbar | None)`

Scalar background + quiver overlay in one call.

```python
artist, q, cbar = plot_contour_quiver(ax, x, y, P, U, V,
                                       quiver_stride=5, cbar_label="Pressure")
```

### Data preparation

#### `reshape_structured2d(x, y, values, *, order="yx") -> (X, Y, Z)`

Reshape flattened `(x, y, value)` exports into 2D arrays.  Detects grid
dimensions from unique coordinates and validates completeness.

```python
X, Y, Z = reshape_structured2d(x_flat, y_flat, p_flat)
```

Pass a dict to reshape multiple fields at once:

```python
X, Y, fields = reshape_structured2d(x_flat, y_flat, {"p": p_flat, "T": t_flat})
```

#### `dataframe_to_grid(df, *, x="x", y="y", values=None) -> (xg, yg, fields)`

Pivot a pandas DataFrame into structured 2D arrays.

```python
xg, yg, p = dataframe_to_grid(df, values="p")
xg, yg, fields = dataframe_to_grid(df, values=["p", "u", "v"])
```

#### `mask_field(z, condition, *, fill=None) -> MaskedArray | ndarray`

Mask a 2D field where *condition* is `True`.  Use when you already have
structured 2D arrays and want to hide certain regions (solid zones, cells
where `IND != 0`, etc.).

- Default: returns a `numpy.ma.MaskedArray`.
- Pass `fill=np.nan` to get a plain `ndarray` with `NaN` in excluded positions.

```python
IND = fields["IND"]
P_fluid = mask_field(fields["p"], IND != 0)           # masked array
P_fluid = mask_field(fields["p"], IND != 0, fill=np.nan)  # NaN variant
plot_pcolormesh(ax, xg, yg, P_fluid, cbar_label="Pressure [Pa]")
```

#### `dataframe_to_masked_grid(df, *, x="x", y="y", values=None, mask_column, mask_value, keep=True, fill=None) -> (xg, yg, fields)`

One-call workflow: pivot a DataFrame to a structured grid **and** mask
regions based on a filter column, preserving the full grid topology.

```python
xg, yg, P = dataframe_to_masked_grid(
    df, values="p", mask_column="IND", mask_value=0,
)
plot_pcolormesh(ax, xg, yg, P, cbar_label="Pressure [Pa]")
```

| Parameter      | Description                                                  |
|----------------|--------------------------------------------------------------|
| `mask_column`  | Column used for filtering (e.g. `"IND"`)                     |
| `mask_value`   | Value to compare against                                     |
| `keep`         | `True` keeps rows matching `mask_value`, masks the rest      |
| `fill`         | `None` for masked arrays, `np.nan` for NaN-filled ndarrays   |

#### `extract_slice2d(field, *, axis, index=None, coord=None, x=None, y=None, z=None) -> (c1, c2, slice2d)`

Extract a 2D plane from a 3D array.

```python
H, V, p_slice = extract_slice2d(pressure_3d, axis="x", coord=0.5, x=x, y=y, z=z)
plot_pcolormesh(ax, H, V, p_slice, cbar_label="p [Pa]")
```

### Region filtering (masking)

CFD datasets often carry an indicator column (`IND`, `zone`, `cellType`)
that marks fluid vs. solid regions.  A common first reaction is to drop
unwanted rows:

```python
df_fluid = df[df["IND"] == 0]      # DANGER: breaks the structured grid
```

This **destroys the rectangular lattice** — the surviving `(x, y)` pairs
no longer form a complete grid, `pivot()` produces `NaN` gaps, and the
plotting functions cannot reconstruct a proper mesh.

**Preferred approach: keep the full grid, mask excluded regions.**

```python
from plotting import dataframe_to_masked_grid, plot_pcolormesh

xg, yg, P = dataframe_to_masked_grid(
    df, values="p", mask_column="IND", mask_value=0,   # keep IND==0
)
plot_pcolormesh(ax, xg, yg, P, cbar_label="Pressure [Pa]")
```

Masked positions are never drawn — the figure shows holes where
`IND != 0`, while the full coordinate grid is preserved.

**Filling masked regions with a solid colour (e.g. black for walls):**

Pass `bad_color` to any scalar plotting function.  Masked / `NaN` cells
are drawn in that colour instead of being left transparent:

```python
plot_pcolormesh(ax, xg, yg, P, cbar_label="Pressure [Pa]", bad_color="black")
```

**Mask vs NaN — when to use each:**

| Method          | Returns             | Best for                                     |
|-----------------|---------------------|----------------------------------------------|
| `fill=None`     | `MaskedArray`       | General use; Matplotlib skips masked cells    |
| `fill=np.nan`   | plain `ndarray`     | Simple workflows; `NaN` cells are blank       |

Both produce the same visual result with `pcolormesh` and `contourf`.
Masked arrays are more explicit and preserve the original data underneath
the mask; `NaN` is simpler but irreversible.

**Drawing a boundary line around the masked region:**

Masking and `bad_color` control *visibility*; `mask_outline` draws a
**contour line along the fluid-solid interface**.  Pass the original
boolean mask (not the NaN-filled scalar) so the boundary is traced
cleanly:

```python
fluid_mask = fields["IND"] == 0
P_nan = mask_field(fields["p"], ~fluid_mask, fill=np.nan)

plot_pcolormesh(
    ax, xg, yg, P_nan,
    cmap="viridis",
    bad_color="lightgrey",
    mask_outline=fluid_mask,
    mask_outline_color="k",
    mask_outline_width=1.5,
)
```

| Parameter              | Default  | Description                                      |
|------------------------|----------|--------------------------------------------------|
| `mask_outline`         | `None`   | 2D boolean/numeric mask; `True`/1 = visible      |
| `mask_outline_color`   | `"k"`    | Line colour                                      |
| `mask_outline_width`   | `1.0`    | Line width                                       |
| `mask_outline_level`   | `0.5`    | Iso-value for the contour (rarely needs changing) |
| `mask_outline_zorder`  | `None`   | Drawing order                                    |

`mask_outline` is supported by `plot_pcolormesh`, `plot_contourf`, and
`plot_contour_quiver`.

**When masking is not enough — truly unstructured data:**

If, after filtering, the surviving points genuinely do not sit on any
rectangular lattice (e.g. an unstructured finite-element mesh), masking
will not help.  In that case use Matplotlib's triangulation directly:

```python
import matplotlib.tri as mtri
tri = mtri.Triangulation(x_flat, y_flat)
ax.tricontourf(tri, value_flat, levels=30, cmap="viridis")
```

### Data organization guide

#### Node-based vs cell-based data

CFD solvers store fields at either **mesh nodes** (vertices) or **cell
centers**.  The distinction matters for plotting:

| Location      | Description                                          | Rendering                                                     |
|---------------|------------------------------------------------------|---------------------------------------------------------------|
| **Nodes**     | One value per grid vertex                            | `pcolormesh` colors *cells* between nodes — can look blocky.  Use `plot_pcolormesh_interp` or `contourf` for smooth visuals. |
| **Cell centers** | One value per mesh cell                           | `pcolormesh` maps one quad per value — natural 1:1 mapping.   |

When your data is defined at **nodes** and looks blocky with `pcolormesh`,
refine the grid before plotting:

```python
qm, cbar, _ = plot_pcolormesh_interp(ax, x, y, Z_nodal, factor=4)
```

Or use `contourf`, which always computes smooth isolines regardless of the
data location.

#### How Matplotlib renders 2D scalar fields

Each plotting function works differently under the hood:

| Function         | What it draws                                                            |
|------------------|--------------------------------------------------------------------------|
| `pcolormesh`     | One coloured **quadrilateral** per cell.  Colour = scalar value mapped through the colormap. Fast, exact, but visually "blocky" on coarse grids. |
| `imshow`         | One coloured **pixel** per array element on a uniform raster.  Supports pixel-level interpolation (`bilinear`, `bicubic`, ...) for smooth appearance. |
| `contourf`       | Computes **iso-value curves** from the scalar field, then fills the regions between successive levels with solid colour. Always smooth, even on coarse grids. |
| `contour`        | Same iso-value algorithm as `contourf`, but draws **lines** instead of filling. |
| `tricontourf`    | Like `contourf`, but operates on a **Delaunay triangulation** of scattered `(x, y)` points. Use for genuinely unstructured data. |

All functions map scalar values to colours via a **colormap** + normalization
(`vmin`/`vmax` or a `Normalize` instance).

#### Structured Cartesian grid

Canonical layout:

- `x`: shape `(nx,)` — 1D coordinate vector
- `y`: shape `(ny,)` — 1D coordinate vector
- `X, Y = np.meshgrid(x, y, indexing="xy")` — 2D grids, shape `(ny, nx)`
- `Z`: shape `(ny, nx)` — scalar field
- `U, V`: shape `(ny, nx)` — vector components

When to use each function:

| Function       | Best for                                   |
|----------------|--------------------------------------------|
| `plot_imshow`      | Uniform Cartesian grids, fast rendering    |
| `plot_pcolormesh`  | Default for structured CFD data (any spacing) |
| `plot_contourf`    | Report-quality smooth scalar maps          |
| `plot_contour`     | Isolines (Cp levels, isotherms)            |

#### Flattened `(x, y, value)` data

If the data forms a complete structured grid (no duplicates, no gaps):

```python
X, Y, Z = reshape_structured2d(x_flat, y_flat, value_flat)
plot_pcolormesh(ax, X, Y, Z)
```

If it does not (unstructured mesh), use Matplotlib's triangulation directly:

```python
import matplotlib.tri as mtri
tri = mtri.Triangulation(x_flat, y_flat)
ax.tricontourf(tri, value_flat, levels=30, cmap="viridis")
```

#### From pandas DataFrame

**Complete grid (no filtering):**

```python
xg, yg, fields = dataframe_to_grid(df, values=["p", "u", "v"])
X, Y = np.meshgrid(xg, yg, indexing="xy")
plot_pcolormesh(ax, X, Y, fields["p"], cbar_label="Pressure")
plot_quiver(ax, X, Y, fields["u"], fields["v"], stride=5, color="k", aspect=None)
```

**Filtered by region indicator (e.g. keep only `IND == 0`):**

```python
xg, yg, P = dataframe_to_masked_grid(
    df, values="p", mask_column="IND", mask_value=0,
)
plot_pcolormesh(ax, xg, yg, P, cbar_label="Pressure [Pa]")
```

Pitfalls:

- `pivot()` fails on duplicate `(x, y)` rows — clean the data first.
- Missing grid points become `NaN` — use `mask_field` or `dataframe_to_masked_grid`.
- Always verify that `u`, `v`, and scalar fields share the same grid.
- **Never drop rows** to filter by region — use masking instead
  (see *Region filtering* above).

#### Vector fields

- Store components as separate arrays `u`, `v` on a common grid.
- Interpolate staggered-grid components to cell centers before plotting.
- Use `subsample_vectors` or `plot_quiver(..., stride=N)` for readability.
- Use `compute_speed(u, v)` for streamline colouring or magnitude overlays.

### CFD best practices

- Default to `aspect="equal"` for spatial plots (all 2D functions do this).
- Use `pcolormesh` for large fields, `contourf` for reports.
- Use diverging colormaps centered at zero for signed fields (vorticity,
  pressure fluctuation) — combine with `matplotlib.colors.TwoSlopeNorm`.
- Fix `vmin` / `vmax` across comparative plots.
- Keep vector overlays sparse: full-resolution scalar + downsampled arrows.
- Use `streamplot` for topology, not for noisy or non-colocated data.
- Include physical units in colorbar labels.
- Use `rasterized=True` in `plot_pcolormesh` for lighter SVG/PDF export.

---

## Batch plotting

Dictionary-driven batch plotting for multi-source curve comparisons (CFD vs analytics vs experiment) at every flight point.

### Input dictionaries

**`configuration_dict`** — one entry per curve/source:

```python
configuration_dict = {
    "KW": {
        "name": "KW",
        "label": r"$k$-$\omega$",
        "dir": "/path/to/data",
        "CDG": [0, 0, 0],
        "df": kw_df,          # pandas DataFrame (required)
        "color": "C0",        # optional — forwarded to plot_line
    },
}
```

**`y_axis_dict`** — QOIs to plot on the y-axis:

```python
y_axis_dict = {
    "CN": {
        "col_name": "CN",
        "literal_name": "",
        "symbol": r"$C_N$",
        "unit": "-",
        "y_save_name": "CN",
    },
}
```

**`sweep_dict`** — sweep / PDV variables (x-axis of each polar). One polar is generated per entry:

```python
sweep_dict = {
    "alpha": {
        "col_name": "alpha",
        "literal_name": "Angle of attack",
        "symbol": r"$\alpha$",
        "unit": "deg",
        "x_save_name": "alpha",
        "polar_prefix": "ALPHA_POLAR",
        "label": r"$\alpha$",
        "save_name": "ALPHA",
    },
    "beta": {
        "col_name": "beta",
        "symbol": r"$\beta$",
        "unit": "deg",
        "x_save_name": "beta",
        "polar_prefix": "BETA_POLAR",
        "label": r"$\beta$",
        "save_name": "BETA",
    },
}
```

For each sweep variable *s*, the module plots y vs. *s* at every flight point while holding all **other** sweep variables fixed at each of their unique values (cross-sweep / combinatorial PDV). Sweep keys listed in ``flight_point_dict`` are automatically excluded from the flight point.

Legacy ``x_axis_dict`` is still accepted (treated as a single-entry ``sweep_dict``).

Axis labels are built as ``{literal_name}, {symbol} ({unit})``. Set ``literal_name=""`` to omit the name and start with the symbol (e.g. ``$C_N$ (-)``).

Figure titles use **symbol and unit only**, plus context metadata (flight point + fixed sweeps):

```
$C_N$ (-) vs. $\alpha$ (deg) (M=0.8, Z=8000, $\beta$=2, $\delta_L$=$\delta_M$=$\delta_N$=0)
```

**`flight_point_dict`** — fixed parameters that define a flight point (sweep keys are excluded automatically):

```python
flight_point_dict = {
    "Mach": {"values": [], "label": "M", "save_name": "M"},
    "Altitude_m": {"values": [], "label": "Z", "save_name": "Z"},
    "DL": {"values": [], "label": r"$\delta_L$", "save_name": "DL"},
    "DM": {"values": [], "label": r"$\delta_M$", "save_name": "DM"},
    "DN": {"values": [], "label": r"$\delta_N$", "save_name": "DN"},
}
# ``label`` — display name used in figure titles (may contain LaTeX).
# ``save_name`` — filesystem-safe name used in output directory segments.
# Empty ``values`` lists are auto-filled from the concatenated configuration data.
```

### Usage

```python
from plotting import batch_plot

written = batch_plot(
    configuration_dict=configuration_dict,
    y_axis_dict=y_axis_dict,
    sweep_dict=sweep_dict,
    flight_point_dict=flight_point_dict,
    output_base="output/study",
    style_profile="paper",
    formats=("svg",),
)
```

Output paths use a polar prefix, then flight-point and fixed-sweep directory segments:

```
output/study/ALPHA_POLAR/M_0.8/Z_8000/BETA_2/CN_vs_alpha.svg
output/study/BETA_POLAR/M_0.8/Z_8000/ALPHA_3/CN_vs_beta.svg
```

Single-value parameters are omitted from the path. Fixed sweep segments appear only when the held sweep variable takes more than one unique value in the data.

### Flexibility hooks

- Per-source styling: any extra key in a configuration entry (``color``, ``linestyle``, ``marker``, …) is forwarded to `plot_line`.
- `include_curve(source_key, flight_point, x_key, y_key) -> bool` — skip sources for specific plots.
- `on_before_save(fig, ax, context)` — modify a figure before export (add a curve, tweak colors, etc.).

### E2E example

```bash
cd scripts/post/plot
PYTHONPATH=. python3 tests/E2E_MULTIPLE_PLOTTING/run_batch_plot.py
```

See `tests/E2E_MULTIPLE_PLOTTING/` for sample CSV fixtures (`kw.csv`, `sa.csv`, `exp.csv`) and the driver script.

---

## Dependencies

- **Required**: `matplotlib`, `numpy`
- **Optional**: `pandas` (DataFrame support), `rich` (pretty terminal output),
  Inkscape (EMF export)

## Files

```
scripts/post/plot/
    demo_plotting.py           # Tutorial / template (runnable)
    pyproject.toml             # Ruff configuration
    plotting/
        __init__.py            # Public API
        mpl_template.py        # Style, figure, 1D helpers, export
        field2d.py             # 2D scalar field plotting
        vector2d.py            # 2D vector field plotting
        composite2d.py         # Combined scalar + vector plots
        batch.py               # Batch curve plotting for multi-source comparisons
        prep.py                # Data reshaping, pivoting, slicing
        _grid.py               # Internal grid validators
        styles/
            notebook.mplstyle
            slides.mplstyle
            paper.mplstyle
```
