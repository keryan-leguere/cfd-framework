"""carto — maps of a quantity over a *pair* of sweep variables.

``batch_plot`` answers "how does CN vary with alpha?", one curve at a time.
Past two sweeps that stops scaling: a study over Mach × alpha × altitude is a
hundred polars, and the shape of ``CN(Mach, alpha)`` is spread across all of
them. A cartography puts that shape on one sheet.

    from cfd_plot import batch_carto

    batch_carto(
        configuration_dict=configuration_dict,   # one panel per source
        y_axis_dict=y_axis_dict,                 # one figure per quantity
        sweep_dict=sweep_dict,                   # one figure per PAIR of sweeps
        flight_point_dict=flight_point_dict,
        output_base="FIGURE",
    )

The loop is ``batch_plot``'s, one dimension wider: every **pair** of sweep
variables becomes a map, every *other* sweep is pinned as a directory level,
and flight points loop as usual. Inside one figure there is one **panel per
configuration** — the CFD, the model, the wind tunnel — drawn as filled
contours with black iso-lines labelled in place.

Reading a map honestly
----------------------
Panels of the same quantity from different sources share their colour scale by
default (``shared_scale=True``): the level *values* are computed once from the
combined range and handed to every panel, so a band means the same thing left
and right and one colorbar can describe them all. Independently levelled panels
would make two different fields look alike, which is the one thing a
side-by-side map exists to rule out.

That is also why the panels must then agree on ``cmap`` and on an explicit
``levels`` array: a single colorbar cannot describe two colormaps. Disagreeing
sources raise rather than produce a figure whose colorbar is wrong for half of
it. ``shared_scale=False`` is the way out — each panel then gets its own scale
*and* its own colorbar, and anything goes.

Overriding the look
-------------------
Defaults come from the ``carto=`` argument (a :class:`CartoSpec` or a plain
dict). A ``"CARTO"`` sub-dict overrides them, on a ``y_axis_dict`` entry (the
quantity: its colormap, its levels) and then on a ``configuration_dict`` entry
(that source's panel)::

    y_axis_dict = {
        "CN": {"col_name": "CN", "symbol": r"$C_N$", "unit": "-",
               "CARTO": {"cmap": "RdBu_r", "levels": 13}},
    }
    configuration_dict = {
        "CFD":   {"label": "CFD", "df": df_cfd},
        "MODEL": {"label": "Model", "df": df_model,
                  "CARTO": {"line_color": "0.2", "clabel": False}},
    }

``"CARTO"`` is metadata like ``df`` or ``label``: it never reaches
``plot_line``, so the same ``configuration_dict`` drives ``batch_plot`` and
``batch_carto`` unchanged.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Union

import matplotlib.pyplot as plt
import numpy as np

from ._compat import zip_strict
from .batch import (
    BatchPlotContext,
    PdfReportArg,
    _cli_text,
    _coalesce_sweep_dict,
    _filter_df_by_context,
    _paths_for_formats,
    _prepare_flight_point_dict,
    _prepare_sweep_dict,
    _print_clean_report,
    _resolve_pdf_spec,
    _run_jobs,
    _subplot_grid_shape,
    build_output_path,
    format_axis_label,
    format_axis_title_label,
    format_flight_point_title_suffix,
    iter_flight_points,
    varying_flight_keys,
)
from .cleanup import clean_figure_dir
from .field2d import plot_contour, plot_contourf
from .mpl_template import (
    add_shared_colorbar,
    print_file_report,
    save_figure,
    set_suptitle,
    set_title,
    use_style,
)
from .prep import dataframe_to_grid

__all__ = [
    "CARTO_KEY",
    "CartoSpec",
    "batch_carto",
]

#: Key of the override sub-dict, in a ``y_axis_dict`` or ``configuration_dict``
#: entry. Also listed in ``batch._CONFIG_METADATA_KEYS`` so it never reaches
#: ``plot_line``.
CARTO_KEY = "CARTO"

# Maps are squarer than curves and carry a colorbar; the default figsize is
# sized for one wide curve panel.
_CARTO_PANEL_SIZE_FACTOR = (0.95, 1.05)

# 'level' is the spelling that comes to mind at the call site (and the one
# Matplotlib does *not* use). Accepted, mapped, documented — a silent no-op
# would be the worst of the three options.
_CARTO_ALIASES = {"level": "levels", "line_level": "line_levels"}


@dataclass(frozen=True)
class CartoSpec:
    """How one cartography panel is drawn.

    Parameters
    ----------
    cmap :
        Colormap of the filled contours.
    levels :
        Number of level boundaries, or the explicit values. An int is turned
        into that many evenly spaced values across the shared range, so the
        bands are reproducible from one figure to the next — Matplotlib's own
        "nice round numbers" would differ per panel.
    line_levels :
        Levels of the black iso-lines. ``None`` (default) reuses the fill's, so
        a labelled line is exactly the edge of a colour band. An int or an
        explicit list draws fewer lines than bands, which is the readable
        choice past ~10 levels.
    line_color, line_width :
        Iso-line style. ``None`` as the colour drops the lines entirely.
    clabel, clabel_fmt, clabel_fontsize :
        In-place labels on the iso-lines (``ax.clabel``).
    colorbar :
        One colorbar for the figure when ``shared_scale`` is on, one per panel
        otherwise.
    shared_scale :
        Give every panel the same level values, computed from the combined
        range of all panels. See the module docstring.
    max_cols :
        Panels per row (1–3).
    extend :
        Colorbar arrows: ``"neither"``, ``"both"``, ``"min"``, ``"max"``.
    aspect :
        Axes aspect. ``None`` (default) leaves it auto — a map over
        (Mach, alpha) has two unrelated units, and forcing ``"equal"`` would
        squash it to a sliver.
    """

    cmap: str = "viridis"
    levels: int | tuple[float, ...] = 11
    line_levels: int | tuple[float, ...] | None = None
    line_color: str | None = "black"
    line_width: float = 0.6
    clabel: bool = True
    clabel_fmt: str = "%.3g"
    clabel_fontsize: float | None = None
    colorbar: bool = True
    shared_scale: bool = True
    max_cols: int = 3
    extend: str = "neither"
    aspect: str | float | None = None

    def __post_init__(self) -> None:
        for name, value in (("levels", self.levels), ("line_levels", self.line_levels)):
            if isinstance(value, int) and not isinstance(value, bool):
                if value < 2:
                    raise ValueError(f"CartoSpec.{name} must be >= 2, got {value}.")
            elif value is not None and not isinstance(value, (list, tuple, np.ndarray)):
                raise TypeError(
                    f"CartoSpec.{name} must be an int or a sequence of values, "
                    f"got {type(value).__name__}."
                )
        if self.max_cols < 1 or self.max_cols > 3:
            raise ValueError(f"CartoSpec.max_cols must be between 1 and 3, got {self.max_cols}.")
        if self.extend not in ("neither", "both", "min", "max"):
            raise ValueError(
                f"CartoSpec.extend must be 'neither', 'both', 'min' or 'max', "
                f"got {self.extend!r}."
            )

    @property
    def figure_keys(self) -> tuple[Any, ...]:
        """What every panel of one figure must agree on to share a colorbar."""
        return (self.cmap, _levels_key(self.levels))


CartoArg = Union[CartoSpec, Mapping[str, Any], None]


def _levels_key(levels: int | tuple[float, ...] | None) -> Any:
    """Hashable form of a *levels* value, for comparing two specs."""
    if levels is None or isinstance(levels, int):
        return levels
    return tuple(float(value) for value in levels)


def _spec_field_names() -> tuple[str, ...]:
    return tuple(field.name for field in fields(CartoSpec))


def _override_spec(base: CartoSpec, overrides: Mapping[str, Any], *, where: str) -> CartoSpec:
    """Apply one ``CARTO`` sub-dict on top of *base*."""
    known = _spec_field_names()
    resolved: dict[str, Any] = {}
    for key, value in overrides.items():
        name = _CARTO_ALIASES.get(key, key)
        if name not in known:
            raise ValueError(
                f"unknown CARTO key {key!r} in {where}; expected one of {list(known)}."
            )
        resolved[name] = tuple(value) if name in ("levels", "line_levels") and isinstance(
            value, (list, np.ndarray)
        ) else value
    return replace(base, **resolved)


def _resolve_carto_arg(carto: CartoArg) -> CartoSpec:
    if carto is None:
        return CartoSpec()
    if isinstance(carto, CartoSpec):
        return carto
    if isinstance(carto, Mapping):
        return _override_spec(CartoSpec(), carto, where="carto=")
    raise TypeError(
        f"carto must be a CartoSpec, a dict or None, got {type(carto).__name__}."
    )


def _spec_for(base: CartoSpec, entry: Mapping[str, Any], *, where: str) -> CartoSpec:
    overrides = entry.get(CARTO_KEY)
    if overrides is None:
        return base
    if not isinstance(overrides, Mapping):
        raise TypeError(
            f"{CARTO_KEY!r} in {where} must be a dict of options, "
            f"got {type(overrides).__name__}."
        )
    return _override_spec(base, overrides, where=where)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CartoPanel:
    """One source's map, gridded and ready to draw."""

    source: str
    label: str
    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    spec: CartoSpec

    @property
    def finite_range(self) -> tuple[float, float]:
        finite = self.z[np.isfinite(self.z)]
        return float(finite.min()), float(finite.max())


@dataclass(frozen=True)
class _CartoPlotJob:
    """One cartography figure: a quantity over a sweep pair, panel per source."""

    flight_point: dict[str, float]
    fixed_sweeps: dict[str, float]
    flight_point_keys: tuple[str, ...]
    sweep_x_key: str
    sweep_y_key: str
    qoi_key: str
    sweep_x_spec: dict[str, Any]
    sweep_y_spec: dict[str, Any]
    qoi_spec: dict[str, Any]
    polar_prefix: str
    output_path: Path
    suptitle: str
    subtitle: str
    flight_point_label: str
    case_label: str
    panels: tuple[_CartoPanel, ...]
    spec: CartoSpec

    def cli_label(self) -> str:
        """Progress-bar description (``batch._any_job_label`` calls this)."""
        context = _cli_text(self.subtitle) or "all conditions"
        pair = f"{self.sweep_x_key} x {self.sweep_y_key}"
        return f"{self.polar_prefix} · carto · {context} · {self.qoi_key} over {pair}"

    def render(
        self,
        style_profile: str,
        formats: tuple[str, ...],
        on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None,
        builder: Any = None,
    ) -> list[Path]:
        """Draw and export this figure (``batch._render_any`` calls this)."""
        return _render_one_carto_job(self, style_profile, formats, on_before_save, builder)


def _shared_levels(job: _CartoPlotJob) -> np.ndarray | None:
    """The level boundaries every panel shares, or ``None`` for per-panel levels."""
    spec = job.spec
    if not spec.shared_scale:
        return None
    if not isinstance(spec.levels, int) or isinstance(spec.levels, bool):
        return np.asarray(spec.levels, dtype=float)

    ranges = [panel.finite_range for panel in job.panels]
    low = min(bounds[0] for bounds in ranges)
    high = max(bounds[1] for bounds in ranges)
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        # A quantity constant over the whole map is a real result (a model that
        # ignores one of the two sweeps), not an error. Give it a band to sit
        # in rather than handing Matplotlib non-increasing levels.
        span = max(abs(low), 1.0) * 1e-3
        low, high = low - span, high + span
    return np.linspace(low, high, int(spec.levels))


def _line_levels(spec: CartoSpec, fill_levels: np.ndarray | int) -> Any:
    """Levels of the black iso-lines, defaulting to the fill's own."""
    if spec.line_levels is None:
        return fill_levels
    if isinstance(spec.line_levels, int) and not isinstance(spec.line_levels, bool):
        if isinstance(fill_levels, np.ndarray):
            return np.linspace(fill_levels[0], fill_levels[-1], spec.line_levels)
        return spec.line_levels
    return np.asarray(spec.line_levels, dtype=float)


def _check_panels_agree(job: _CartoPlotJob) -> None:
    """Refuse a shared colorbar over panels it cannot describe."""
    if not job.spec.shared_scale or len(job.panels) < 2:
        return
    grouped: dict[tuple[Any, ...], list[str]] = {}
    for panel in job.panels:
        grouped.setdefault(panel.spec.figure_keys, []).append(panel.source)
    if len(grouped) > 1:
        disagreeing = " vs ".join(
            f"{sources} → cmap={keys[0]!r}, levels={keys[1]!r}"
            for keys, sources in grouped.items()
        )
        raise ValueError(
            f"cartography {job.output_path.name}: panels disagree on the colour "
            f"scale ({disagreeing}). One colorbar cannot describe two of them — "
            f"make the {CARTO_KEY!r} entries agree on 'cmap' and 'levels', or pass "
            "shared_scale=False to give each panel its own scale and colorbar."
        )


def _render_one_carto_job(
    job: _CartoPlotJob,
    style_profile: str,
    formats: tuple[str, ...],
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None,
    builder: Any = None,
) -> list[Path]:
    """Render one cartography figure (safe for process workers)."""
    use_style(style_profile)
    _check_panels_agree(job)

    spec = job.spec
    n_panels = len(job.panels)
    nrows, ncols = _subplot_grid_shape(n_panels, spec.max_cols)
    base_w, base_h = plt.rcParams["figure.figsize"]
    width_factor, height_factor = _CARTO_PANEL_SIZE_FACTOR
    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(base_w * width_factor * ncols, base_h * height_factor * nrows),
        squeeze=False,
    )
    axes_flat = list(axes.ravel())
    used_axes = axes_flat[:n_panels]

    shared = _shared_levels(job)
    x_label = format_axis_label(job.sweep_x_spec, job.sweep_x_key)
    y_label = format_axis_label(job.sweep_y_spec, job.sweep_y_key)
    qoi_label = format_axis_label(job.qoi_spec, job.qoi_key)

    last_fill = None
    for ax, panel in zip_strict(used_axes, list(job.panels)):
        panel_spec = panel.spec
        fill_levels: Any = shared if shared is not None else panel_spec.levels
        fill, _ = plot_contourf(
            ax,
            panel.x,
            panel.y,
            panel.z,
            levels=fill_levels,
            cmap=panel_spec.cmap,
            colorbar=not spec.shared_scale and spec.colorbar,
            cbar_label=qoi_label,
            extend=panel_spec.extend,
            aspect=panel_spec.aspect,
        )
        last_fill = fill

        if panel_spec.line_color is not None:
            lines, _ = plot_contour(
                ax,
                panel.x,
                panel.y,
                panel.z,
                levels=_line_levels(panel_spec, fill_levels),
                colors=panel_spec.line_color,
                linewidths=panel_spec.line_width,
                colorbar=False,
                aspect=panel_spec.aspect,
            )
            if panel_spec.clabel:
                clabel_kwargs: dict[str, Any] = {"fmt": panel_spec.clabel_fmt, "inline": True}
                if panel_spec.clabel_fontsize is not None:
                    clabel_kwargs["fontsize"] = panel_spec.clabel_fontsize
                ax.clabel(lines, **clabel_kwargs)

        ax.set_xlabel(x_label)
        ax.set_ylabel(y_label)
        set_title(ax, panel.label)

    for ax in axes_flat[n_panels:]:
        ax.set_visible(False)

    if spec.shared_scale and spec.colorbar and last_fill is not None:
        # match_axes=False keeps constrained_layout in charge: the manual
        # placement reads axes positions that the engine has not settled yet,
        # and every style profile here runs constrained.
        add_shared_colorbar(
            fig, last_fill, match_axes=False, label=qoi_label, ax=used_axes
        )

    panel_titlesize = plt.rcParams["axes.titlesize"]
    heading = f"{job.suptitle}\n{job.subtitle}" if job.subtitle else job.suptitle
    set_suptitle(fig, heading, fontsize=panel_titlesize * 1.25, fontweight="bold")

    if on_before_save is not None:
        for index, (ax, panel) in enumerate(zip_strict(used_axes, list(job.panels))):
            on_before_save(
                fig,
                ax,
                BatchPlotContext(
                    flight_point=job.flight_point,
                    fixed_sweeps=job.fixed_sweeps,
                    sweep_key=job.sweep_x_key,
                    y_key=job.qoi_key,
                    x_spec=job.sweep_x_spec,
                    y_spec=job.qoi_spec,
                    polar_prefix=job.polar_prefix,
                    output_path=job.output_path,
                    panel_index=index,
                    carto_sweep_key=job.sweep_y_key,
                    carto_sweep_spec=job.sweep_y_spec,
                    carto_source=panel.source,
                ),
            )

    written = save_figure(fig, job.output_path, formats=formats)
    if builder is not None:
        builder.add(fig)
    plt.close(fig)
    return written


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------


def _carto_prefix(x_spec: Mapping[str, Any], y_spec: Mapping[str, Any], x_key: str, y_key: str) -> str:
    """Top directory level of a pair, mirroring ``ALPHA_POLAR``."""
    x_save = str(x_spec.get("x_save_name", x_key)).upper()
    y_save = str(y_spec.get("x_save_name", y_key)).upper()
    return f"{x_save}_{y_save}_CARTO"


def _resolve_pairs(
    pairs: Sequence[tuple[str, str]] | None,
    sweep_keys: Sequence[str],
) -> list[tuple[str, str]]:
    """Which sweep pairs to map — every combination by default."""
    if pairs is None:
        if len(sweep_keys) < 2:
            raise ValueError(
                "batch_carto needs at least two sweep variables to make a map; "
                f"got {list(sweep_keys)}. Use batch_plot for a single sweep."
            )
        return list(itertools.combinations(sweep_keys, 2))

    resolved: list[tuple[str, str]] = []
    for pair in pairs:
        if len(pair) != 2:
            raise ValueError(f"each entry of pairs must be two sweep keys, got {pair!r}.")
        x_key, y_key = pair
        unknown = [key for key in pair if key not in sweep_keys]
        if unknown:
            raise KeyError(
                f"pairs entry {pair!r} names sweep keys not in sweep_dict: {unknown}."
            )
        if x_key == y_key:
            raise ValueError(f"pairs entry {pair!r} maps a sweep against itself.")
        resolved.append((x_key, y_key))
    return resolved


def _grid_panel(
    source: str,
    config: Mapping[str, Any],
    *,
    flight_point: dict[str, float],
    fixed_sweeps: dict[str, float],
    flight_point_keys: Sequence[str],
    x_col: str,
    y_col: str,
    qoi_col: str,
    spec: CartoSpec,
) -> _CartoPanel | None:
    """Pivot one source's rows into a map, or ``None`` when it has none here."""
    context = {**flight_point, **fixed_sweeps}
    keys = list(flight_point_keys) + list(fixed_sweeps.keys())
    frame = _filter_df_by_context(config["df"], context, keys)
    if frame.empty:
        return None

    missing = [col for col in (x_col, y_col, qoi_col) if col not in frame.columns]
    if missing:
        raise KeyError(f"Columns {missing} not found in configuration {source!r}.")

    try:
        x_values, y_values, field = dataframe_to_grid(
            frame, x=x_col, y=y_col, values=qoi_col
        )
    except ValueError as error:
        # The usual cause is a dimension nobody pinned: two rows share
        # (x, y) because they differ by a column that is in neither
        # sweep_dict nor flight_point_dict, so it never became a directory.
        raise ValueError(
            f"cannot grid {qoi_col!r} over ({x_col}, {y_col}) for configuration "
            f"{source!r} at {context or 'the whole table'}: {error} "
            "Every column that varies must appear in sweep_dict or "
            "flight_point_dict, or the map has several values per cell."
        ) from error

    field = np.asarray(field, dtype=float)
    if not np.any(np.isfinite(field)):
        return None

    return _CartoPanel(
        source=source,
        label=str(config.get("label", source)),
        x=np.asarray(x_values, dtype=float),
        y=np.asarray(y_values, dtype=float),
        z=field,
        spec=spec,
    )


def _enumerate_carto_jobs(
    *,
    configuration_dict: dict[str, dict[str, Any]],
    y_axis_dict: dict[str, dict[str, Any]],
    completed_sweeps: dict[str, dict[str, Any]],
    completed_flight_points: dict[str, dict[str, Any]],
    output_base: str | Path,
    base_spec: CartoSpec,
    pairs: Sequence[tuple[str, str]] | None,
    include_panel: Callable[..., bool] | None,
) -> list[_CartoPlotJob]:
    """Build one job per (sweep pair, flight point, pinned sweeps, quantity)."""
    sweep_keys = list(completed_sweeps.keys())
    flight_point_keys = list(completed_flight_points.keys())
    varying_fp_keys = varying_flight_keys(configuration_dict, flight_point_keys)
    varying_sw_keys = varying_flight_keys(configuration_dict, sweep_keys)
    jobs: list[_CartoPlotJob] = []

    for x_key, y_key in _resolve_pairs(pairs, sweep_keys):
        x_spec = completed_sweeps[x_key]
        y_spec = completed_sweeps[y_key]
        prefix = _carto_prefix(x_spec, y_spec, x_key, y_key)
        x_col = x_spec["col_name"]
        y_col = y_spec["col_name"]
        x_save = str(x_spec.get("x_save_name", x_key))
        y_save = str(y_spec.get("x_save_name", y_key))
        other_sweeps = [key for key in sweep_keys if key not in (x_key, y_key)]
        varying_other_sweeps = [key for key in other_sweeps if key in varying_sw_keys]

        for flight_point in iter_flight_points(configuration_dict, flight_point_keys):
            for fixed_sweeps in iter_flight_points(configuration_dict, other_sweeps):
                for qoi_key, qoi_spec in y_axis_dict.items():
                    qoi_col = qoi_spec.get("col_name", qoi_key)
                    qoi_save = qoi_spec.get("y_save_name", qoi_key)
                    figure_spec = _spec_for(
                        base_spec, qoi_spec, where=f"y_axis_dict[{qoi_key!r}]"
                    )

                    panels: list[_CartoPanel] = []
                    for source, config in configuration_dict.items():
                        if include_panel is not None and not include_panel(
                            source, flight_point, (x_key, y_key), qoi_key, fixed_sweeps
                        ):
                            continue
                        panel = _grid_panel(
                            source,
                            config,
                            flight_point=flight_point,
                            fixed_sweeps=fixed_sweeps,
                            flight_point_keys=flight_point_keys,
                            x_col=x_col,
                            y_col=y_col,
                            qoi_col=qoi_col,
                            spec=_spec_for(
                                figure_spec,
                                config,
                                where=f"configuration_dict[{source!r}]",
                            ),
                        )
                        if panel is not None:
                            panels.append(panel)
                    if not panels:
                        continue

                    output_path = build_output_path(
                        output_base,
                        flight_point,
                        varying_fp_keys,
                        fixed_sweeps,
                        varying_other_sweeps,
                        prefix,
                        f"{x_save}_{y_save}",
                        qoi_save,
                        completed_flight_points,
                        completed_sweeps,
                    )
                    flight_point_label = format_flight_point_title_suffix(
                        flight_point, flight_point_keys, completed_flight_points
                    )
                    case_label = (
                        format_flight_point_title_suffix(
                            fixed_sweeps, list(fixed_sweeps.keys()), completed_sweeps
                        )
                        if fixed_sweeps
                        else ""
                    )
                    subtitle = ", ".join(part for part in (flight_point_label, case_label) if part)
                    suptitle = (
                        f"{format_axis_title_label(qoi_spec, qoi_key)} over "
                        f"{format_axis_title_label(x_spec, x_key)} × "
                        f"{format_axis_title_label(y_spec, y_key)}"
                    )
                    jobs.append(
                        _CartoPlotJob(
                            flight_point=flight_point,
                            fixed_sweeps=fixed_sweeps,
                            flight_point_keys=tuple(flight_point_keys),
                            sweep_x_key=x_key,
                            sweep_y_key=y_key,
                            qoi_key=qoi_key,
                            sweep_x_spec=x_spec,
                            sweep_y_spec=y_spec,
                            qoi_spec=qoi_spec,
                            polar_prefix=prefix,
                            output_path=output_path,
                            suptitle=suptitle,
                            subtitle=subtitle,
                            flight_point_label=flight_point_label,
                            case_label=case_label,
                            panels=tuple(panels),
                            spec=figure_spec,
                        )
                    )
    return jobs


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def batch_carto(
    *,
    configuration_dict: dict[str, dict[str, Any]],
    y_axis_dict: dict[str, dict[str, Any]],
    sweep_dict: dict[str, dict[str, Any]] | None = None,
    x_axis_dict: dict[str, dict[str, Any]] | None = None,
    flight_point_dict: dict[str, Any] | None = None,
    output_base: str | Path,
    pairs: Sequence[tuple[str, str]] | None = None,
    carto: CartoArg = None,
    style_profile: str = "paper",
    formats: tuple[str, ...] = ("svg",),
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None = None,
    include_panel: Callable[..., bool] | None = None,
    report: bool = True,
    verbose: bool = False,
    dry_run: bool = False,
    n_jobs: int = 1,
    pdf_report: PdfReportArg = None,
    clean: bool | str = False,
) -> list[Path]:
    """Map every quantity over every pair of sweep variables.

    One figure per (sweep pair, flight point, pinned sweeps, quantity), with one
    **panel per configuration** — filled contours, black iso-lines, labels in
    place. Every other sweep becomes a directory level, exactly as in
    :func:`~cfd_plot.batch_plot`.

    Output layout::

        output_base/ALPHA_MACH_CARTO/Z_8000/BETA_2/CN_vs_alpha_Mach.svg
        output_base/ALPHA_BETA_CARTO/Z_8000/MACH_0.8/CN_vs_alpha_beta.svg

    Parameters
    ----------
    configuration_dict, y_axis_dict, sweep_dict, x_axis_dict, flight_point_dict :
        The same four dictionaries :func:`~cfd_plot.batch_plot` takes, read the
        same way. ``sweep_dict`` needs at least two entries. A ``"CARTO"``
        sub-dict on a ``y_axis_dict`` or ``configuration_dict`` entry overrides
        the drawing options — see the module docstring.
    pairs :
        Which sweep pairs to map, e.g. ``[("alpha", "Mach")]``. Default: every
        combination, in ``sweep_dict`` order, first key on the horizontal axis.
    carto :
        Defaults for every panel: a :class:`CartoSpec` or a plain dict of the
        same keys.
    include_panel :
        ``f(source, flight_point, (x_key, y_key), qoi_key, fixed_sweeps) -> bool``
        — the cartography analogue of ``batch_plot``'s ``include_curve``.
    on_before_save :
        Called once per panel with the panel's axes and a
        :class:`~cfd_plot.BatchPlotContext` whose ``carto_sweep_key`` /
        ``carto_sweep_spec`` describe the vertical sweep and whose
        ``carto_source`` names the configuration.
    report, verbose, dry_run, n_jobs, pdf_report, clean :
        As in :func:`~cfd_plot.batch_plot`.

    Notes
    -----
    Each source's rows are pivoted onto a grid, so a ``(x, y)`` cell that the
    study never ran comes out ``NaN`` and is left blank rather than
    interpolated. Two rows landing in the same cell is an error naming the
    configuration: some column varies that is in neither ``sweep_dict`` nor
    ``flight_point_dict``, so it never became a directory.
    """
    if not y_axis_dict:
        raise ValueError("y_axis_dict must contain at least one entry.")

    base_spec = _resolve_carto_arg(carto)
    resolved_sweep_dict = _coalesce_sweep_dict(sweep_dict, x_axis_dict)
    if not resolved_sweep_dict:
        raise ValueError("Either sweep_dict or x_axis_dict must be provided.")

    completed_sweeps = _prepare_sweep_dict(configuration_dict, resolved_sweep_dict)
    completed_flight_points = _prepare_flight_point_dict(
        configuration_dict,
        flight_point_dict,
        list(resolved_sweep_dict.keys()),
    )

    jobs = _enumerate_carto_jobs(
        configuration_dict=configuration_dict,
        y_axis_dict=y_axis_dict,
        completed_sweeps=completed_sweeps,
        completed_flight_points=completed_flight_points,
        output_base=output_base,
        base_spec=base_spec,
        pairs=pairs,
        include_panel=include_panel,
    )

    if verbose:
        _print_carto_plan(
            configuration_dict=configuration_dict,
            y_axis_dict=y_axis_dict,
            completed_sweeps=completed_sweeps,
            completed_flight_points=completed_flight_points,
            jobs=jobs,
            output_base=output_base,
            formats=formats,
            style_profile=style_profile,
            spec=base_spec,
            n_jobs=n_jobs,
            dry_run=dry_run,
            clean=clean,
        )

    if clean:
        clean_report = clean_figure_dir(output_base, mode=clean, dry_run=dry_run)
        if verbose or report:
            _print_clean_report(clean_report)

    if dry_run:
        planned: list[Path] = []
        for job in jobs:
            planned.extend(_paths_for_formats(job.output_path, formats))
        if verbose:
            print(
                f"Dry run complete: {len(jobs)} cartography figure(s) → "
                f"{len(planned)} file(s) (nothing written)."
            )
        return planned

    spec = _resolve_pdf_spec(
        pdf_report, style_profile=style_profile, title=_carto_study_title(jobs)
    )
    written_paths = _run_jobs(
        jobs,
        style_profile=style_profile,
        formats=formats,
        on_before_save=on_before_save,
        n_jobs=n_jobs,
        verbose=verbose,
        pdf_spec=spec,
        pdf_summary=_carto_summary(jobs, formats),
    )
    if spec is not None and jobs:
        written_paths.append(Path(spec.path))

    if report and written_paths:
        print_file_report(written_paths, title="Cartographies")

    return written_paths


def _carto_study_title(jobs: Sequence[_CartoPlotJob]) -> str:
    prefixes = sorted({job.polar_prefix for job in jobs})
    if not prefixes:
        return "Cartographies"
    if len(prefixes) <= 3:
        return ", ".join(prefixes)
    return f"{len(prefixes)} cartographies"


def _carto_summary(
    jobs: Sequence[_CartoPlotJob], formats: Sequence[str]
) -> list[tuple[str, str]]:
    """Cover-page facts for a cartography run."""
    pairs = {f"{job.sweep_x_key} × {job.sweep_y_key}" for job in jobs}
    sources: set[str] = set()
    for job in jobs:
        sources.update(panel.label for panel in job.panels)
    rows = [("Cartographies", str(len(jobs))), ("Sweep pairs", ", ".join(sorted(pairs)))]
    if sources:
        rows.append(("Sources", ", ".join(sorted(sources))))
    if formats:
        rows.append(("Also exported", ", ".join(formats)))
    return rows


def _print_carto_plan(
    *,
    configuration_dict: dict[str, dict[str, Any]],
    y_axis_dict: dict[str, dict[str, Any]],
    completed_sweeps: dict[str, dict[str, Any]],
    completed_flight_points: dict[str, dict[str, Any]],
    jobs: Sequence[_CartoPlotJob],
    output_base: str | Path,
    formats: Sequence[str],
    style_profile: str,
    spec: CartoSpec,
    n_jobs: int,
    dry_run: bool,
    clean: bool | str,
) -> None:
    """Print what the run will do — pairs, panels, files."""
    from . import batch as _batch

    pairs = sorted({f"{job.sweep_x_key} × {job.sweep_y_key}" for job in jobs})
    panels = sum(len(job.panels) for job in jobs)
    lines = [
        f"Sources      : {', '.join(configuration_dict)}  ({len(configuration_dict)})",
        f"Quantities   : {', '.join(y_axis_dict)}  ({len(y_axis_dict)})",
        f"Sweeps       : {', '.join(completed_sweeps)}  ({len(completed_sweeps)})",
        f"Sweep pairs  : {', '.join(pairs) if pairs else 'none'}",
        f"Flight params: {', '.join(completed_flight_points)}"
        f"  ({len(completed_flight_points)})",
        f"Output base  : {output_base}",
        f"Formats      : {', '.join(formats)}",
        f"Style        : {style_profile}",
        f"Mode         : {'dry-run (no files written)' if dry_run else 'write'}",
        f"Colour scale : {'shared across panels' if spec.shared_scale else 'per panel'}"
        f", cmap={spec.cmap}, levels={spec.levels}  (defaults)",
        f"Parallel     : {'sequential (n_jobs=1)' if n_jobs == 1 else f'{n_jobs} workers'}",
        f"Clean        : {_batch._clean_note(clean)}",
        f"Figures      : {len(jobs)}  ({panels} panels)  →  "
        f"{len(jobs) * len(formats)} file(s)",
    ]
    overriding = [
        f"y_axis_dict[{key!r}]" for key, entry in y_axis_dict.items() if CARTO_KEY in entry
    ] + [
        f"configuration_dict[{key!r}]"
        for key, entry in configuration_dict.items()
        if CARTO_KEY in entry
    ]
    if overriding:
        # Without this the "defaults" line above reads as what was drawn, and a
        # CARTO override is invisible until you open the figure.
        lines.insert(-1, f"{CARTO_KEY} overrides: {', '.join(overriding)}")
    if _batch._RICH and _batch._console is not None and _batch.Panel is not None:
        _batch._console.print(
            _batch.Panel("\n".join(lines), title="Cartography plan", border_style="cyan")
        )
        return
    print("=== Cartography plan ===")
    for line in lines:
        print(line)
