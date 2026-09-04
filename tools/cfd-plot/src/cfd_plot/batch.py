"""
batch — dictionary-driven batch plotting for multi-source curve comparisons.

Iterates over flight points and sweep-variable combinations, plotting every
source curve on shared axes and exporting SVG figures via the existing helpers.

For each sweep variable a *polar* is generated: y vs. that sweep at every
flight point, with all other sweep variables held fixed (cross-sweep / PDV).
"""

from __future__ import annotations

import os
import pickle
import re
import warnings
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Any, Union

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.artist import ArtistInspector
from matplotlib.lines import Line2D

from cfd_plot._compat import figure_set_layout_pad, zip_strict

from .cleanup import CleanReport, clean_figure_dir
from .mpl_template import (
    make_legend,
    plot_line,
    save_figure,
    set_suptitle,
    set_title,
    sync_axes_limits,
    use_style,
)
from .pdf import PdfReportSpec
from .pdf.assemble import ReportBuilder

# NOTE: do *not* call matplotlib.use("Agg") in this module. It is re-exported by
# cfd_plot/__init__.py, so an import-time backend switch applies to anyone who
# merely writes `import cfd_plot` — silently breaking interactive sessions
# (Spyder, Jupyter, IPython: "FigureCanvasAgg is non-interactive", and no window
# ever appears) and closing figures the user already had open, since
# matplotlib.use() forces a switch_backend() that calls close("all").
#
# Only the batch *worker processes* need a headless backend, and they get it
# from _init_worker() below. Everything else honours whatever backend the caller
# chose. Batch rendering is safe under a GUI backend anyway: every figure is
# closed right after being saved and none is ever shown.

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )
    from rich.table import Table

    _RICH = True
except ImportError:  # pragma: no cover - optional dependency
    _RICH = False
    Console = None  # type: ignore[misc, assignment]
    Panel = None  # type: ignore[misc, assignment]
    Progress = None  # type: ignore[misc, assignment]
    Table = None  # type: ignore[misc, assignment]

_console = Console() if _RICH else None

DEFAULT_FLIGHT_POINT_KEYS: tuple[str, ...] = (
    "Mach",
    "Altitude_m",
    "DL",
    "DM",
    "DN",
)

_CONFIG_METADATA_KEYS = frozenset({"name", "label", "dir", "CDG", "df", "style"})

# Line2D setters that would collide with the data the batch itself supplies,
# or with ax.plot's own "data" keyword mechanism.
_NON_STYLE_LINE_PROPERTIES = frozenset({"data", "xdata", "ydata", "figure"})


@dataclass(frozen=True)
class BatchPlotContext:
    """Metadata passed to optional batch-plot hooks."""

    flight_point: dict[str, float]
    fixed_sweeps: dict[str, float]
    sweep_key: str
    y_key: str
    x_spec: dict[str, Any]
    y_spec: dict[str, Any]
    polar_prefix: str
    output_path: Path
    compare_name: str | None = None
    panel_index: int | None = None
    fold_kind: str | None = None
    fold_layout: str | None = None
    fold_label: str | None = None


@dataclass(frozen=True)
class _SourceCurve:
    """One source series ready to draw (pre-filtered / sorted)."""

    label: str
    x: np.ndarray
    y: np.ndarray
    style_kwargs: dict[str, Any]


@dataclass(frozen=True)
class _BatchPlotJob:
    """Self-contained description of a single figure to render or preview."""

    flight_point: dict[str, float]
    fixed_sweeps: dict[str, float]
    flight_point_keys: tuple[str, ...]
    sweep_key: str
    y_key: str
    x_spec: dict[str, Any]
    y_spec: dict[str, Any]
    polar_prefix: str
    output_path: Path
    title: str
    flight_point_label: str
    case_label: str
    curves: tuple[_SourceCurve, ...]


@dataclass(frozen=True)
class _ComparePanel:
    """One flight-point panel inside a compare figure."""

    name: str
    flight_point: dict[str, float]
    curves: tuple[_SourceCurve, ...]
    title: str


@dataclass(frozen=True)
class _ComparePlotJob:
    """Multi-panel figure comparing the same polar across named flight points."""

    fixed_sweeps: dict[str, float]
    flight_point_keys: tuple[str, ...]
    sweep_key: str
    y_key: str
    x_spec: dict[str, Any]
    y_spec: dict[str, Any]
    polar_prefix: str
    output_path: Path
    suptitle: str
    case_label: str
    panels: tuple[_ComparePanel, ...]
    max_cols: int


def _concat_configurations(configuration_dict: dict[str, dict[str, Any]]) -> pd.DataFrame:
    frames = [entry["df"] for entry in configuration_dict.values() if "df" in entry]
    if not frames:
        raise ValueError("configuration_dict must contain at least one entry with a 'df' key.")
    return pd.concat(frames, ignore_index=True)


def _normalize_param_spec(key: str, spec: Any, *, default_save_name: str | None = None) -> dict[str, Any]:
    """Normalize a flight-point or sweep entry to ``{values, label, save_name, ...}``."""
    save_default = default_save_name if default_save_name is not None else key.upper()
    if isinstance(spec, dict):
        values = spec.get("values", spec.get("list", []))
        normalized = {
            "values": list(values) if values else [],
            "label": spec.get("label", key),
            "save_name": spec.get("save_name", save_default),
        }
        for meta_key in ("col_name", "literal_name", "symbol", "unit", "x_save_name", "polar_prefix"):
            if meta_key in spec:
                normalized[meta_key] = spec[meta_key]
        return normalized
    if isinstance(spec, list):
        return {"values": spec, "label": key, "save_name": save_default}
    return {"values": [], "label": key, "save_name": save_default}


def _normalize_flight_point_spec(key: str, spec: Any) -> dict[str, Any]:
    return _normalize_param_spec(key, spec)


def _normalize_sweep_spec(key: str, spec: Any) -> dict[str, Any]:
    normalized = _normalize_param_spec(key, spec)
    x_save = normalized.get("x_save_name", key)
    normalized.setdefault("col_name", key)
    normalized.setdefault("x_save_name", x_save)
    normalized.setdefault("polar_prefix", f"{x_save.upper()}_POLAR")
    return normalized


def _resolve_flight_point_keys(flight_point_dict: dict[str, Any] | None) -> list[str]:
    if flight_point_dict:
        return list(flight_point_dict.keys())
    return list(DEFAULT_FLIGHT_POINT_KEYS)


def _coalesce_sweep_dict(
    sweep_dict: dict[str, dict[str, Any]] | None,
    x_axis_dict: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    if sweep_dict is not None:
        return sweep_dict
    if x_axis_dict is None:
        raise ValueError("Either sweep_dict or x_axis_dict must be provided.")
    result: dict[str, dict[str, Any]] = {}
    for key, spec in x_axis_dict.items():
        save_name = spec.get("x_save_name", key)
        result[key] = {
            **spec,
            "polar_prefix": spec.get("polar_prefix", f"{save_name.upper()}_POLAR"),
        }
    return result


def _format_path_value(value: float | int) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def discover_flight_point_values(
    configuration_dict: dict[str, dict[str, Any]],
    keys: Iterable[str],
) -> dict[str, list[float]]:
    """Return sorted unique values for each flight-parameter key."""
    combined = _concat_configurations(configuration_dict)
    discovered: dict[str, list[float]] = {}
    for key in keys:
        if key not in combined.columns:
            raise KeyError(f"Flight parameter {key!r} not found in configuration data.")
        values = sorted(combined[key].drop_duplicates().tolist())
        discovered[key] = values
    return discovered


def varying_flight_keys(
    configuration_dict: dict[str, dict[str, Any]],
    keys: Iterable[str],
) -> list[str]:
    """Return flight-parameter keys that take more than one unique value."""
    combined = _concat_configurations(configuration_dict)
    return [key for key in keys if key in combined.columns and combined[key].nunique() > 1]


def iter_flight_points(
    configuration_dict: dict[str, dict[str, Any]],
    keys: Iterable[str],
) -> Iterator[dict[str, float]]:
    """Yield unique flight-point combinations from all configuration data."""
    combined = _concat_configurations(configuration_dict)
    key_list = list(keys)
    if not key_list:
        yield {}
        return
    missing = [key for key in key_list if key not in combined.columns]
    if missing:
        raise KeyError(f"Flight parameters not found in configuration data: {missing}")

    unique_rows = combined[key_list].drop_duplicates()
    for _, row in unique_rows.iterrows():
        yield {key: float(row[key]) for key in key_list}


def iter_fixed_sweep_combinations(
    configuration_dict: dict[str, dict[str, Any]],
    sweep_keys: Sequence[str],
    x_sweep_key: str,
) -> Iterator[dict[str, float]]:
    """Yield every combination of sweep variables held fixed for one polar."""
    other_keys = [key for key in sweep_keys if key != x_sweep_key]
    if not other_keys:
        yield {}
        return
    yield from iter_flight_points(configuration_dict, other_keys)


def build_output_path(
    base: str | Path,
    flight_point: dict[str, float],
    varying_flight_keys: Sequence[str],
    fixed_sweeps: dict[str, float],
    varying_fixed_sweep_keys: Sequence[str],
    polar_prefix: str,
    x_save_name: str,
    y_save_name: str,
    flight_point_specs: dict[str, dict[str, Any]] | None = None,
    sweep_specs: dict[str, dict[str, Any]] | None = None,
) -> Path:
    """Build an output path: ``base/polar/{flight}/{fixed_sweeps}/y_vs_x``."""
    flight_specs = flight_point_specs or {}
    sweep_spec_map = sweep_specs or {}
    parts: list[str | Path] = [Path(base), polar_prefix]

    for key in varying_flight_keys:
        value = flight_point[key]
        save_name = flight_specs.get(key, {}).get("save_name", key.upper())
        parts.append(f"{save_name}_{_format_path_value(value)}")

    for key in varying_fixed_sweep_keys:
        value = fixed_sweeps[key]
        save_name = sweep_spec_map.get(key, {}).get("save_name", key.upper())
        parts.append(f"{save_name}_{_format_path_value(value)}")

    parts.append(f"{y_save_name}_vs_{x_save_name}")
    return Path(*parts)


def build_compare_output_path(
    base: str | Path,
    fixed_sweeps: dict[str, float],
    varying_fixed_sweep_keys: Sequence[str],
    polar_prefix: str,
    x_save_name: str,
    y_save_name: str,
    sweep_specs: dict[str, dict[str, Any]] | None = None,
    *,
    compare_folder: str = "COMPARE",
) -> Path:
    """Build path for a multi-flight-point compare figure (no per-FP folders)."""
    sweep_spec_map = sweep_specs or {}
    parts: list[str | Path] = [Path(base), polar_prefix, compare_folder]
    for key in varying_fixed_sweep_keys:
        value = fixed_sweeps[key]
        save_name = sweep_spec_map.get(key, {}).get("save_name", key.upper())
        parts.append(f"{save_name}_{_format_path_value(value)}")
    parts.append(f"{y_save_name}_vs_{x_save_name}")
    return Path(*parts)


_COMPARE_PANEL_HEIGHT_FACTOR = 1.25
_COMPARE_LAYOUT_H_PAD = 0.02


def _subplot_grid_shape(n_panels: int, max_cols: int = 3) -> tuple[int, int]:
    """Return ``(nrows, ncols)`` with at most *max_cols* panels per row."""
    if n_panels < 1:
        raise ValueError("n_panels must be >= 1.")
    if max_cols < 1 or max_cols > 3:
        raise ValueError("max_cols must be between 1 and 3.")
    ncols = min(n_panels, max_cols)
    nrows = (n_panels + ncols - 1) // ncols
    return nrows, ncols


def _normalize_compare_flight_points(
    compare_flight_points: dict[str, dict[str, Any]],
    flight_point_keys: Sequence[str],
) -> dict[str, dict[str, float]]:
    """Validate and coerce named flight points to the active flight-point keys."""
    if not compare_flight_points:
        raise ValueError("compare_flight_points must contain at least one entry.")
    if len(compare_flight_points) > 12:
        raise ValueError("compare_flight_points supports at most 12 named points.")

    normalized: dict[str, dict[str, float]] = {}
    key_list = list(flight_point_keys)
    for name, raw in compare_flight_points.items():
        if not isinstance(raw, dict):
            raise TypeError(
                f"compare_flight_points[{name!r}] must be a dict of parameter values."
            )
        missing = [key for key in key_list if key not in raw]
        if missing:
            raise KeyError(
                f"compare_flight_points[{name!r}] missing flight-point keys: {missing}"
            )
        normalized[str(name)] = {key: float(raw[key]) for key in key_list}
    return normalized


def _filter_df_by_context(
    df: pd.DataFrame,
    context: dict[str, float],
    context_keys: Sequence[str],
) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    for key in context_keys:
        mask &= df[key] == context[key]
    return df.loc[mask]


def _filter_df_by_flight_point(
    df: pd.DataFrame,
    flight_point: dict[str, float],
    flight_point_keys: Sequence[str],
) -> pd.DataFrame:
    return _filter_df_by_context(df, flight_point, flight_point_keys)


@lru_cache(maxsize=1)
def _line_style_keys() -> frozenset[str]:
    """Every keyword ``ax.plot`` accepts for a ``Line2D``, aliases included.

    Asked of Matplotlib rather than hardcoded, so the set follows whatever
    version is installed (``gapcolor`` exists in 3.6, not in 3.4).
    """
    inspector = ArtistInspector(Line2D)
    names = set(inspector.get_setters())
    for prop, aliases in (getattr(inspector, "aliasd", None) or {}).items():
        names.add(prop)
        names.update(aliases)
    names -= _NON_STYLE_LINE_PROPERTIES
    names.update({"scalex", "scaley"})
    return frozenset(names)


def config_style_keys(config: dict[str, Any]) -> list[str]:
    """Keys of one ``configuration_dict`` entry that reach ``plot_line``."""
    return sorted(_extract_plot_style_kwargs(config))


def config_extra_keys(config: dict[str, Any]) -> list[str]:
    """Keys of one entry that are the caller's own, and are never plotted.

    A configuration entry is also a natural place to record what the source
    *is* — its mass, its mesh, its run directory. Those keys stay available
    to the caller (they never leave the dict) and are listed here so a
    misspelt style keyword is still discoverable.
    """
    allowed = _line_style_keys()
    return sorted(
        key
        for key in config
        if key not in _CONFIG_METADATA_KEYS and key not in allowed
    )


def ignored_config_keys(
    configuration_dict: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    """Per source, the keys carried as metadata instead of plotted."""
    found = {
        source: config_extra_keys(config)
        for source, config in configuration_dict.items()
    }
    return {source: keys for source, keys in found.items() if keys}


def _extract_plot_style_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    """Keep only what Matplotlib can actually draw with.

    Callers routinely overload an entry with their own bookkeeping
    (``"masse": 1200``, ``"maillage": "fin"``); forwarding that to ``ax.plot``
    used to fail with *Line2D has no property 'masse'*. Anything Matplotlib
    does not know is therefore left in the dict for the caller, and a
    ``style`` sub-dict is the explicit escape hatch — it is merged last and
    never filtered, so an exotic keyword can always be forced through.
    """
    allowed = _line_style_keys()
    kwargs = {
        key: value
        for key, value in config.items()
        if key not in _CONFIG_METADATA_KEYS and key in allowed
    }
    explicit = config.get("style")
    if explicit is None:
        return kwargs
    if not isinstance(explicit, dict):
        raise TypeError(
            f"configuration entry 'style' must be a dict of plot keywords, "
            f"got {type(explicit).__name__}."
        )
    kwargs.update(explicit)
    return kwargs


def format_axis_label(spec: dict[str, Any], default_name: str) -> str:
    """Build an axis label from ``literal_name``, ``symbol``, and ``unit``."""
    legacy = spec.get("ylabel") or spec.get("xlabel")
    has_new_keys = any(key in spec for key in ("literal_name", "symbol", "unit"))
    if legacy and not has_new_keys:
        return legacy

    literal = spec.get("literal_name", default_name)
    if literal == "":
        literal = None
    symbol = spec.get("symbol")
    unit = spec.get("unit")

    if literal and symbol and unit:
        return f"{literal}, {symbol} ({unit})"
    if literal and symbol:
        return f"{literal}, {symbol}"
    if symbol and unit:
        return f"{symbol} ({unit})"
    if symbol:
        return symbol
    if literal and unit:
        return f"{literal} ({unit})"
    if literal:
        return literal
    return default_name


def format_axis_title_label(spec: dict[str, Any], default_name: str) -> str:
    """Build a compact title fragment using *symbol* only (no unit)."""
    symbol = spec.get("symbol")
    if symbol:
        return symbol
    # Fall back without grafting units into the Y/X title fragment.
    stripped = {key: value for key, value in spec.items() if key != "unit"}
    return format_axis_label(stripped, default_name)


def _format_title_value(value: float | int, unit: str | None) -> str:
    """Format a numeric title value, appending *unit* when meaningful."""
    formatted = _format_path_value(value)
    if not unit or unit == "-":
        return formatted
    if unit.startswith(("°", "˚")) or unit in {"%", "‰"}:
        return f"{formatted}{unit}"
    return f"{formatted} {unit}"


def format_flight_point_title_suffix(
    flight_point: dict[str, float],
    flight_point_keys: Sequence[str],
    flight_point_specs: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Format flight-point metadata for figure titles (units after values when set)."""
    specs = flight_point_specs or {}
    parts: list[str] = []
    skip: set[str] = set()

    for key in flight_point_keys:
        if key in skip:
            continue
        if key == "DL" and all(param in flight_point for param in ("DL", "DM", "DN")):
            dl, dm, dn = flight_point["DL"], flight_point["DM"], flight_point["DN"]
            if dl == dm == dn:
                dl_label = specs.get("DL", {}).get("label", "DL")
                dm_label = specs.get("DM", {}).get("label", "DM")
                dn_label = specs.get("DN", {}).get("label", "DN")
                unit = specs.get("DL", {}).get("unit")
                parts.append(
                    f"{dl_label}={dm_label}={dn_label}={_format_title_value(dl, unit)}"
                )
                skip.update({"DM", "DN"})
                continue
        label = specs.get(key, {}).get("label", key)
        unit = specs.get(key, {}).get("unit")
        parts.append(f"{label}={_format_title_value(flight_point[key], unit)}")

    return ", ".join(parts)


def _combined_flight_point_suffix(
    flight_point: dict[str, float],
    flight_point_keys: Sequence[str],
    flight_point_specs: dict[str, dict[str, Any]] | None = None,
    fixed_sweeps: dict[str, float] | None = None,
    sweep_specs: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Merge a flight point with any fixed-sweep values into one title suffix."""
    context = dict(flight_point)
    context_keys = list(flight_point_keys)
    if fixed_sweeps:
        context.update(fixed_sweeps)
        context_keys.extend(fixed_sweeps.keys())
    combined_specs = dict(flight_point_specs or {})
    if sweep_specs:
        combined_specs.update(sweep_specs)
    return format_flight_point_title_suffix(context, context_keys, combined_specs)


def format_plot_title(
    y_spec: dict[str, Any],
    y_key: str,
    x_spec: dict[str, Any],
    x_key: str,
    flight_point: dict[str, float],
    flight_point_keys: Sequence[str],
    flight_point_specs: dict[str, dict[str, Any]] | None = None,
    fixed_sweeps: dict[str, float] | None = None,
    sweep_specs: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Build ``QOI vs. variable (context metadata)`` figure title.

    The Y/X fragment uses symbols only. Units appear on context values in the
    brackets when provided on the corresponding specs (``unit`` key).
    """
    y_label = format_axis_title_label(y_spec, y_key)
    x_label = format_axis_title_label(x_spec, x_key)
    flight_suffix = _combined_flight_point_suffix(
        flight_point, flight_point_keys, flight_point_specs, fixed_sweeps, sweep_specs
    )
    return f"{y_label} vs. {x_label} ({flight_suffix})"


def _prepare_flight_point_dict(
    configuration_dict: dict[str, dict[str, Any]],
    flight_point_dict: dict[str, Any] | None,
    sweep_keys: Sequence[str],
) -> dict[str, dict[str, Any]]:
    all_keys = _resolve_flight_point_keys(flight_point_dict)
    flight_keys = [key for key in all_keys if key not in sweep_keys]
    discovered = discover_flight_point_values(configuration_dict, flight_keys)
    if not flight_point_dict:
        return {
            key: {"values": discovered[key], "label": key, "save_name": key.upper()}
            for key in flight_keys
        }

    completed: dict[str, dict[str, Any]] = {}
    for key in flight_keys:
        spec = _normalize_flight_point_spec(key, flight_point_dict[key])
        values = spec["values"] or discovered[key]
        completed[key] = {
            "values": list(values),
            "label": spec["label"],
            "save_name": spec["save_name"],
        }
        if "unit" in spec:
            completed[key]["unit"] = spec["unit"]
    return completed


def _prepare_sweep_dict(
    configuration_dict: dict[str, dict[str, Any]],
    sweep_dict: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    discovered = discover_flight_point_values(configuration_dict, sweep_dict.keys())
    completed: dict[str, dict[str, Any]] = {}
    for key, raw_spec in sweep_dict.items():
        spec = _normalize_sweep_spec(key, raw_spec)
        values = spec["values"] or discovered[key]
        completed[key] = {**spec, "values": list(values)}
    return completed


def _collect_source_curves(
    configuration_dict: dict[str, dict[str, Any]],
    *,
    flight_point: dict[str, float],
    fixed_sweeps: dict[str, float],
    flight_point_keys: Sequence[str],
    x_key: str,
    y_key: str,
    x_col: str,
    y_col: str,
    include_curve: Callable[..., bool] | None,
) -> list[_SourceCurve]:
    """Filter and extract drawable curves for one figure."""
    filter_context = {**flight_point, **fixed_sweeps}
    filter_keys = list(flight_point_keys) + list(fixed_sweeps.keys())
    curves: list[_SourceCurve] = []

    for source_key, config in configuration_dict.items():
        if include_curve is not None and not include_curve(
            source_key,
            flight_point,
            x_key,
            y_key,
            fixed_sweeps,
        ):
            continue

        filtered = _filter_df_by_context(config["df"], filter_context, filter_keys)
        if filtered.empty:
            continue

        missing_cols = [col for col in (x_col, y_col) if col not in filtered.columns]
        if missing_cols:
            raise KeyError(
                f"Columns {missing_cols} not found in configuration {source_key!r}."
            )

        sorted_df = filtered.sort_values(x_col)
        x_values = sorted_df[x_col].to_numpy()
        y_values = sorted_df[y_col].to_numpy()
        if len(x_values) == 0:
            continue

        curves.append(
            _SourceCurve(
                label=config.get("label", source_key),
                x=np.asarray(x_values),
                y=np.asarray(y_values),
                style_kwargs=_extract_plot_style_kwargs(config),
            )
        )
    return curves


def _enumerate_jobs(
    *,
    configuration_dict: dict[str, dict[str, Any]],
    y_axis_dict: dict[str, dict[str, Any]],
    completed_sweeps: dict[str, dict[str, Any]],
    completed_flight_points: dict[str, dict[str, Any]],
    output_base: str | Path,
    include_curve: Callable[..., bool] | None,
) -> list[_BatchPlotJob]:
    """Build the ordered list of plot jobs (non-empty figures only)."""
    sweep_keys = list(completed_sweeps.keys())
    flight_point_keys = list(completed_flight_points.keys())
    varying_fp_keys = varying_flight_keys(configuration_dict, flight_point_keys)
    varying_sw_keys = varying_flight_keys(configuration_dict, sweep_keys)
    jobs: list[_BatchPlotJob] = []

    for x_key, x_spec in completed_sweeps.items():
        polar_prefix = x_spec["polar_prefix"]
        x_col = x_spec["col_name"]
        x_save_name = x_spec.get("x_save_name", x_key)
        other_sweep_keys = [key for key in sweep_keys if key != x_key]
        varying_other_sweep_keys = [key for key in other_sweep_keys if key in varying_sw_keys]

        for flight_point in iter_flight_points(configuration_dict, flight_point_keys):
            for fixed_sweeps in iter_fixed_sweep_combinations(
                configuration_dict,
                sweep_keys,
                x_key,
            ):
                for y_key, y_spec in y_axis_dict.items():
                    y_col = y_spec["col_name"]
                    y_save_name = y_spec.get("y_save_name", y_key)
                    curves = _collect_source_curves(
                        configuration_dict,
                        flight_point=flight_point,
                        fixed_sweeps=fixed_sweeps,
                        flight_point_keys=flight_point_keys,
                        x_key=x_key,
                        y_key=y_key,
                        x_col=x_col,
                        y_col=y_col,
                        include_curve=include_curve,
                    )
                    if not curves:
                        continue

                    output_path = build_output_path(
                        output_base,
                        flight_point,
                        varying_fp_keys,
                        fixed_sweeps,
                        varying_other_sweep_keys,
                        polar_prefix,
                        x_save_name,
                        y_save_name,
                        completed_flight_points,
                        completed_sweeps,
                    )
                    title = format_plot_title(
                        y_spec,
                        y_key,
                        x_spec,
                        x_key,
                        flight_point,
                        flight_point_keys,
                        completed_flight_points,
                        fixed_sweeps,
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
                    jobs.append(
                        _BatchPlotJob(
                            flight_point=flight_point,
                            fixed_sweeps=fixed_sweeps,
                            flight_point_keys=tuple(flight_point_keys),
                            sweep_key=x_key,
                            y_key=y_key,
                            x_spec=x_spec,
                            y_spec=y_spec,
                            polar_prefix=polar_prefix,
                            output_path=output_path,
                            title=title,
                            flight_point_label=flight_point_label,
                            case_label=case_label,
                            curves=tuple(curves),
                        )
                    )
    return jobs



# ---------------------------------------------------------------------------
# Folded figures
# ---------------------------------------------------------------------------
#
# A batch run answers "one figure per (polar, flight point, fixed sweep, Y)",
# which is the right unit to *produce* and the wrong unit to *read*: comparing
# CN and CA at one condition means opening two files, and comparing one Y
# across five altitudes means opening five files in five directories.
#
# Folding adds bonus figures that gather those siblings onto one sheet. It
# never replaces the individual figures — they stay exactly where they were,
# and the fold is an extra file next to them (kind="y") or in its own
# sub-directory (kind="context").
#
# Two axes of variation are worth folding, and they are folded differently:
#
# kind="y"        every Y of one condition, as subplots. Never overlaid: the
#                 quantities have different units, so a shared Y axis would be
#                 meaningless, and for the same reason the panels are never
#                 axis-synchronised by default.
# kind="context"  one Y across the conditions that only differ by a directory
#                 level (altitudes, Mach numbers, a fixed sweep). Same
#                 quantity, same unit, so both layouts make sense: subplots
#                 (one panel per condition) or overlay (one axes, all
#                 conditions).

#: Filename stem of a ``kind="y"`` fold, written beside the figures it gathers.
FOLD_Y_STEM = "FOLD_Y"

_FOLD_KINDS = ("y", "context")
_FOLD_LAYOUTS = ("subplot", "overlay")
_FOLD_SYNC_VALUES = ("x", "y", "both")
_FOLD_OVERLAY_COLOR = ("fold", "source")

# Line styles cycled per folded condition when overlay_color="source", so the
# source keeps its colour and the condition is read off the dash pattern.
_OVERLAY_LINESTYLES = ("-", "--", ":", "-.", (0, (3, 1, 1, 1)), (0, (5, 1)))

# An overlay legend can carry n_conditions x n_sources entries; past this many
# it goes to two columns rather than off the bottom of the axes.
_OVERLAY_LEGEND_NCOL_THRESHOLD = 8

_FOLD_PANEL_HEIGHT_FACTOR = 1.15
_FOLD_OVERLAY_SIZE_FACTOR = (1.25, 1.1)


@dataclass(frozen=True)
class FoldSpec:
    """How to fold a family of batch figures onto one sheet.

    Parameters
    ----------
    kind :
        ``"y"`` gathers every Y of one condition (one panel per Y);
        ``"context"`` gathers one Y across several conditions.
    layout :
        ``"subplot"`` (one panel each) or ``"overlay"`` (one axes, every
        condition drawn together). ``"overlay"`` is rejected for ``kind="y"``:
        stacking quantities with different units on one axis is not a figure,
        it is a coincidence.
    over :
        For ``kind="context"``, the flight-point / sweep keys to fold over —
        e.g. ``("Altitude_m",)`` to put every altitude on one sheet and keep a
        separate sheet per Mach. Defaults to *every* key that varies inside the
        polar, i.e. one sheet per Y covering the whole study.
    max_panels :
        Panels (or overlaid conditions) per figure. A family larger than this
        is split into several numbered figures rather than shrunk to
        illegibility.
    max_cols :
        Columns in the subplot grid, 1–3.
    folder :
        Sub-directory of the polar holding ``kind="context"`` folds. Defaults
        to ``FOLD`` for subplots and ``FOLD_OVERLAY`` for overlays, so
        requesting both layouts does not make them collide. Ignored by
        ``kind="y"``, which writes beside the figures it folds.
    sync_axes :
        ``"x"``, ``"y"``, ``"both"`` or ``None``. The default ``"auto"`` means
        ``"both"`` for ``kind="context"`` subplots — same quantity, same units,
        so a shared scale is what makes the panels comparable — and ``None``
        everywhere else. Synchronisation happens *before* ``on_before_save``,
        so a hook that sets its own limits still wins.
    overlay_color :
        ``"fold"`` (default) gives each condition its own colour and leaves the
        marker/linestyle from ``configuration_dict`` to identify the source —
        the readable choice when there is one source, or few. ``"source"``
        keeps each source's own colour and cycles the linestyle per condition.
    """

    kind: str = "y"
    layout: str = "subplot"
    over: tuple[str, ...] | None = None
    max_panels: int = 6
    max_cols: int = 3
    folder: str | None = None
    sync_axes: str | None = "auto"
    overlay_color: str = "fold"

    def __post_init__(self) -> None:
        if self.kind not in _FOLD_KINDS:
            raise ValueError(f"FoldSpec.kind must be one of {_FOLD_KINDS}, got {self.kind!r}.")
        if self.layout not in _FOLD_LAYOUTS:
            raise ValueError(f"FoldSpec.layout must be one of {_FOLD_LAYOUTS}, got {self.layout!r}.")
        if self.kind == "y" and self.layout == "overlay":
            raise ValueError(
                "FoldSpec(kind='y', layout='overlay') is not supported: the Y quantities "
                "have different units, so a single shared axis would be meaningless. "
                "Use layout='subplot' for kind='y'."
            )
        if self.max_panels < 2:
            raise ValueError(f"FoldSpec.max_panels must be >= 2, got {self.max_panels}.")
        if not 1 <= self.max_cols <= 3:
            raise ValueError(f"FoldSpec.max_cols must be between 1 and 3, got {self.max_cols}.")
        if self.sync_axes not in (None, "auto", *_FOLD_SYNC_VALUES):
            raise ValueError(
                f"FoldSpec.sync_axes must be None, 'auto' or one of {_FOLD_SYNC_VALUES}, "
                f"got {self.sync_axes!r}."
            )
        if self.overlay_color not in _FOLD_OVERLAY_COLOR:
            raise ValueError(
                f"FoldSpec.overlay_color must be one of {_FOLD_OVERLAY_COLOR}, "
                f"got {self.overlay_color!r}."
            )
        if self.over is not None and not isinstance(self.over, tuple):
            object.__setattr__(self, "over", tuple(self.over))

    @property
    def resolved_folder(self) -> str:
        if self.folder is not None:
            return self.folder
        return "FOLD_OVERLAY" if self.layout == "overlay" else "FOLD"

    @property
    def resolved_sync(self) -> str | None:
        if self.sync_axes != "auto":
            return self.sync_axes
        if self.kind == "context" and self.layout == "subplot":
            return "both"
        return None


# What batch_plot(fold=...) accepts. ``True`` means "the two obvious folds".
FoldArg = Union[bool, str, FoldSpec, Sequence[Union[str, "FoldSpec"]], None]

_FOLD_ALIASES: dict[str, FoldSpec] = {
    "y": FoldSpec(kind="y"),
    "context": FoldSpec(kind="context", layout="subplot"),
    "context-overlay": FoldSpec(kind="context", layout="overlay"),
    "overlay": FoldSpec(kind="context", layout="overlay"),
}


def _resolve_fold_specs(fold: FoldArg) -> tuple[FoldSpec, ...]:
    """Normalise the ``fold=`` argument to a tuple of specs."""
    if fold is None or fold is False:
        return ()
    if fold is True:
        return (_FOLD_ALIASES["y"], _FOLD_ALIASES["context"])
    if isinstance(fold, FoldSpec):
        return (fold,)
    if isinstance(fold, str):
        return (_fold_from_alias(fold),)
    specs: list[FoldSpec] = []
    for item in fold:
        if isinstance(item, FoldSpec):
            specs.append(item)
        elif isinstance(item, str):
            specs.append(_fold_from_alias(item))
        else:
            raise TypeError(f"fold entries must be FoldSpec or str, got {type(item).__name__}.")
    return tuple(specs)


def _fold_from_alias(name: str) -> FoldSpec:
    try:
        return _FOLD_ALIASES[name]
    except KeyError:
        raise ValueError(
            f"Unknown fold shorthand {name!r}. Use one of "
            f"{sorted(_FOLD_ALIASES)}, or a FoldSpec."
        ) from None


@dataclass(frozen=True)
class _FoldPanel:
    """One panel (or one overlaid condition) of a folded figure."""

    title: str
    curves: tuple[_SourceCurve, ...]
    y_key: str
    y_spec: dict[str, Any]
    flight_point: dict[str, float]
    fixed_sweeps: dict[str, float]


@dataclass(frozen=True)
class _FoldJob:
    """A bonus figure gathering several batch figures onto one sheet."""

    kind: str
    layout: str
    polar_prefix: str
    sweep_key: str
    x_spec: dict[str, Any]
    flight_point_keys: tuple[str, ...]
    output_path: Path
    suptitle: str
    subtitle: str
    panels: tuple[_FoldPanel, ...]
    max_cols: int
    sync_axes: str | None
    overlay_color: str
    y_key: str | None
    context_label: str
    part: tuple[int, int]

    @property
    def label(self) -> str:
        """Short description used by the CLI report and the PDF outline."""
        target = self.y_key if self.y_key is not None else "all Y"
        return f"{target} vs {self.sweep_key} [{self.kind}/{self.layout}]"


def _job_context(job: _BatchPlotJob) -> dict[str, float]:
    """Every value that places a job in the directory tree, flight point first."""
    return {**job.flight_point, **job.fixed_sweeps}


def _chunk(items: Sequence[Any], size: int) -> list[list[Any]]:
    return [list(items[i : i + size]) for i in range(0, len(items), size)]


def _part_suffix(index: int, total: int) -> str:
    """``""`` for a single-part fold, ``_p2of3`` otherwise (1-based)."""
    return "" if total <= 1 else f"_p{index}of{total}"


def _fold_context_label(job: _BatchPlotJob) -> str:
    """Flight point and fixed sweeps of *job*, as one title fragment."""
    return ", ".join(part for part in (job.flight_point_label, job.case_label) if part)


def _join_subtitle(parts: Sequence[str]) -> str:
    return " — ".join(part for part in parts if part)


def _enumerate_fold_jobs(
    jobs: Sequence[_BatchPlotJob],
    specs: Sequence[FoldSpec],
    *,
    y_axis_dict: dict[str, dict[str, Any]],
    completed_sweeps: dict[str, dict[str, Any]],
    completed_flight_points: dict[str, dict[str, Any]],
    output_base: str | Path,
) -> list[_FoldJob]:
    """Build every folded figure requested by *specs* from the rendered *jobs*."""
    if not jobs or not specs:
        return []

    known_keys = set(completed_flight_points) | set(completed_sweeps)
    for spec in specs:
        if spec.over:
            unknown = [key for key in spec.over if key not in known_keys]
            if unknown:
                raise ValueError(
                    f"FoldSpec.over refers to unknown keys {unknown}. "
                    f"Available: {sorted(known_keys)}."
                )

    fold_jobs: list[_FoldJob] = []
    for spec in specs:
        if spec.kind == "y":
            fold_jobs.extend(
                _enumerate_y_folds(jobs, spec, y_axis_dict=y_axis_dict)
            )
        else:
            fold_jobs.extend(
                _enumerate_context_folds(
                    jobs,
                    spec,
                    completed_sweeps=completed_sweeps,
                    completed_flight_points=completed_flight_points,
                    output_base=output_base,
                )
            )
    return fold_jobs


def _enumerate_y_folds(
    jobs: Sequence[_BatchPlotJob],
    spec: FoldSpec,
    *,
    y_axis_dict: dict[str, dict[str, Any]],
) -> list[_FoldJob]:
    """One sheet per condition, gathering that condition's Y figures."""
    y_order = {key: index for index, key in enumerate(y_axis_dict)}
    groups: dict[tuple[Any, ...], list[_BatchPlotJob]] = {}
    for job in jobs:
        key = (
            job.polar_prefix,
            job.sweep_key,
            tuple(sorted(job.flight_point.items())),
            tuple(sorted(job.fixed_sweeps.items())),
        )
        groups.setdefault(key, []).append(job)

    fold_jobs: list[_FoldJob] = []
    for group in groups.values():
        if len(group) < 2:
            # A one-panel fold is a copy of the figure it folds.
            continue
        group = sorted(group, key=lambda job: y_order.get(job.y_key, len(y_order)))
        head = group[0]
        x_save_name = head.x_spec.get("x_save_name", head.sweep_key)
        x_label = format_axis_title_label(head.x_spec, head.sweep_key)
        context_label = _fold_context_label(head)
        chunks = _chunk(group, spec.max_panels)

        for index, chunk in enumerate(chunks, start=1):
            panels = tuple(
                _FoldPanel(
                    title=format_axis_title_label(job.y_spec, job.y_key),
                    curves=job.curves,
                    y_key=job.y_key,
                    y_spec=job.y_spec,
                    flight_point=job.flight_point,
                    fixed_sweeps=job.fixed_sweeps,
                )
                for job in chunk
            )
            stem = f"{FOLD_Y_STEM}_vs_{x_save_name}{_part_suffix(index, len(chunks))}"
            fold_jobs.append(
                _FoldJob(
                    kind="y",
                    layout="subplot",
                    polar_prefix=head.polar_prefix,
                    sweep_key=head.sweep_key,
                    x_spec=head.x_spec,
                    flight_point_keys=head.flight_point_keys,
                    output_path=head.output_path.parent / stem,
                    suptitle=_fold_y_suptitle(panels, x_label),
                    subtitle=_join_subtitle(
                        [context_label, _part_text(index, len(chunks))]
                    ),
                    panels=panels,
                    max_cols=spec.max_cols,
                    sync_axes=spec.resolved_sync,
                    overlay_color=spec.overlay_color,
                    y_key=None,
                    context_label=context_label,
                    part=(index, len(chunks)),
                )
            )
    return fold_jobs


def _fold_y_suptitle(panels: Sequence[_FoldPanel], x_label: str) -> str:
    """List the quantities when short enough, else count them."""
    names = [panel.title for panel in panels]
    joined = ", ".join(names)
    if len(names) <= 4 and len(joined) <= 60:
        return f"{joined} vs. {x_label}"
    return f"{len(names)} quantities vs. {x_label}"


def _part_text(index: int, total: int) -> str:
    return "" if total <= 1 else f"part {index}/{total}"


def _enumerate_context_folds(
    jobs: Sequence[_BatchPlotJob],
    spec: FoldSpec,
    *,
    completed_sweeps: dict[str, dict[str, Any]],
    completed_flight_points: dict[str, dict[str, Any]],
    output_base: str | Path,
) -> list[_FoldJob]:
    """One sheet per Y, gathering the conditions that only differ by a folded key."""
    all_specs: dict[str, dict[str, Any]] = {**completed_flight_points, **completed_sweeps}
    fold_jobs: list[_FoldJob] = []

    by_polar: dict[str, list[_BatchPlotJob]] = {}
    for job in jobs:
        by_polar.setdefault(job.polar_prefix, []).append(job)

    for polar_jobs in by_polar.values():
        head = polar_jobs[0]
        # Candidate keys, in the order they appear in the directory tree.
        candidates = [key for key in completed_flight_points if key in _job_context(head)]
        candidates += [
            key
            for key in completed_sweeps
            if key != head.sweep_key and key in _job_context(head)
        ]
        varying = [
            key
            for key in candidates
            if len({_job_context(job)[key] for job in polar_jobs}) > 1
        ]
        fold_keys = [key for key in candidates if key in spec.over] if spec.over else list(varying)
        fold_keys = [key for key in fold_keys if key in varying]
        if not fold_keys:
            # Nothing varies over the requested keys inside this polar: folding
            # would produce one-panel sheets that duplicate existing figures.
            continue
        remaining = [key for key in varying if key not in fold_keys]

        groups: dict[tuple[Any, ...], list[_BatchPlotJob]] = {}
        for job in polar_jobs:
            context = _job_context(job)
            key = (job.y_key, tuple((name, context[name]) for name in remaining))
            groups.setdefault(key, []).append(job)

        for (y_key, remaining_values), group in groups.items():
            if len(group) < 2:
                continue
            group = sorted(
                group, key=lambda job: tuple(_job_context(job)[name] for name in fold_keys)
            )
            first = group[0]
            x_save_name = first.x_spec.get("x_save_name", first.sweep_key)
            y_save_name = first.y_spec.get("y_save_name", y_key)
            y_label = format_axis_title_label(first.y_spec, y_key)
            x_label = format_axis_title_label(first.x_spec, first.sweep_key)

            fold_names = "_".join(
                str(all_specs.get(name, {}).get("save_name", name.upper())) for name in fold_keys
            )
            fold_labels = ", ".join(
                str(all_specs.get(name, {}).get("label", name)) for name in fold_keys
            )
            remaining_label = format_flight_point_title_suffix(
                dict(remaining_values), [name for name, _ in remaining_values], all_specs
            )

            directory = Path(output_base) / first.polar_prefix / spec.resolved_folder
            for name, value in remaining_values:
                save_name = str(all_specs.get(name, {}).get("save_name", name.upper()))
                directory = directory / f"{save_name}_{_format_path_value(value)}"

            chunks = _chunk(group, spec.max_panels)
            for index, chunk in enumerate(chunks, start=1):
                panels = tuple(
                    _FoldPanel(
                        title=format_flight_point_title_suffix(
                            _job_context(job), fold_keys, all_specs
                        ),
                        curves=job.curves,
                        y_key=job.y_key,
                        y_spec=job.y_spec,
                        flight_point=job.flight_point,
                        fixed_sweeps=job.fixed_sweeps,
                    )
                    for job in chunk
                )
                stem = (
                    f"{y_save_name}_vs_{x_save_name}_by_{fold_names}"
                    f"{_part_suffix(index, len(chunks))}"
                )
                fold_jobs.append(
                    _FoldJob(
                        kind="context",
                        layout=spec.layout,
                        polar_prefix=first.polar_prefix,
                        sweep_key=first.sweep_key,
                        x_spec=first.x_spec,
                        flight_point_keys=first.flight_point_keys,
                        output_path=directory / stem,
                        suptitle=f"{y_label} vs. {x_label}",
                        subtitle=_join_subtitle(
                            [
                                remaining_label,
                                f"{fold_labels} folded",
                                _part_text(index, len(chunks)),
                            ]
                        ),
                        panels=panels,
                        max_cols=spec.max_cols,
                        sync_axes=spec.resolved_sync,
                        overlay_color=spec.overlay_color,
                        y_key=y_key,
                        context_label=remaining_label,
                        part=(index, len(chunks)),
                    )
                )
    return fold_jobs


def _merge_render_order(
    jobs: Sequence[_BatchPlotJob], fold_jobs: Sequence[_FoldJob]
) -> list[Any]:
    """Interleave folds after the jobs of the polar they belong to.

    Keeps the PDF outline and the terminal report telling one story per polar
    instead of appending an orphan "folds" chapter at the very end.
    """
    pending: dict[str, list[_FoldJob]] = {}
    for fold_job in fold_jobs:
        pending.setdefault(fold_job.polar_prefix, []).append(fold_job)

    order: list[Any] = []
    current: str | None = None
    for job in jobs:
        if current is not None and job.polar_prefix != current:
            order.extend(pending.pop(current, []))
        current = job.polar_prefix
        order.append(job)
    if current is not None:
        order.extend(pending.pop(current, []))
    for leftover in pending.values():
        order.extend(leftover)
    return order


def _fold_panel_style(
    job: _FoldJob, style_kwargs: dict[str, Any], panel_index: int
) -> dict[str, Any]:
    """Style for one overlaid condition: colour by condition, or by source."""
    resolved = dict(style_kwargs)
    if job.overlay_color == "source":
        resolved["linestyle"] = _OVERLAY_LINESTYLES[panel_index % len(_OVERLAY_LINESTYLES)]
        return resolved
    colors = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    if colors:
        resolved["color"] = colors[panel_index % len(colors)]
    return resolved


def _fold_curve_label(curve: _SourceCurve, panel: _FoldPanel, *, single_source: bool) -> str:
    """Overlay legend entry: the condition alone when there is one source."""
    if single_source:
        return panel.title
    return f"{curve.label} · {panel.title}"


def _render_fold_subplot(job: _FoldJob) -> tuple[plt.Figure, list[plt.Axes]]:
    n_panels = len(job.panels)
    nrows, ncols = _subplot_grid_shape(n_panels, job.max_cols)
    base_w, base_h = plt.rcParams["figure.figsize"]
    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(base_w * ncols, base_h * _FOLD_PANEL_HEIGHT_FACTOR * nrows),
        squeeze=False,
    )
    axes_flat = list(axes.ravel())
    used = axes_flat[:n_panels]

    label_sets = {tuple(curve.label for curve in panel.curves) for panel in job.panels}
    one_legend = len(label_sets) == 1

    for index, (ax, panel) in enumerate(zip_strict(used, job.panels)):
        for curve in panel.curves:
            plot_line(ax, curve.x, curve.y, label=curve.label, **curve.style_kwargs)
        ax.set_xlabel(format_axis_label(job.x_spec, job.sweep_key))
        ax.set_ylabel(format_axis_label(panel.y_spec, panel.y_key))
        set_title(ax, panel.title)
        if not one_legend or index == 0:
            make_legend(ax)

    for ax in axes_flat[n_panels:]:
        ax.set_visible(False)
    return fig, used


def _render_fold_overlay(job: _FoldJob) -> tuple[plt.Figure, list[plt.Axes]]:
    base_w, base_h = plt.rcParams["figure.figsize"]
    width_factor, height_factor = _FOLD_OVERLAY_SIZE_FACTOR
    fig, ax = plt.subplots(figsize=(base_w * width_factor, base_h * height_factor))

    sources = {curve.label for panel in job.panels for curve in panel.curves}
    single_source = len(sources) == 1

    n_entries = 0
    for index, panel in enumerate(job.panels):
        for curve in panel.curves:
            plot_line(
                ax,
                curve.x,
                curve.y,
                label=_fold_curve_label(curve, panel, single_source=single_source),
                **_fold_panel_style(job, curve.style_kwargs, index),
            )
            n_entries += 1

    head = job.panels[0]
    ax.set_xlabel(format_axis_label(job.x_spec, job.sweep_key))
    ax.set_ylabel(format_axis_label(head.y_spec, head.y_key))
    ncol = 2 if n_entries > _OVERLAY_LEGEND_NCOL_THRESHOLD else 1
    make_legend(ax, ncol=ncol)
    return fig, [ax]


def _render_one_fold_job(
    job: _FoldJob,
    style_profile: str,
    formats: tuple[str, ...],
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None,
    builder: ReportBuilder | None = None,
) -> list[Path]:
    """Render and export one folded figure (safe for process workers)."""
    use_style(style_profile)

    if job.layout == "overlay":
        fig, axes = _render_fold_overlay(job)
    else:
        fig, axes = _render_fold_subplot(job)

    panel_titlesize = plt.rcParams["axes.titlesize"]
    heading = job.suptitle if not job.subtitle else f"{job.suptitle}\n{job.subtitle}"
    set_suptitle(fig, heading, fontsize=panel_titlesize * 1.25, fontweight="bold")

    # Before the hooks, never after: on_before_save is the caller's last word,
    # and a hook that pins its own limits must not be undone by the sync.
    if job.sync_axes is not None and len(axes) > 1:
        sync_axes_limits(axes, which=job.sync_axes)

    if on_before_save is not None:
        # One call per axes. An overlay has a single axes carrying every
        # condition, so its one call reports them all rather than pretending
        # the figure only shows the first.
        overlay_label = " / ".join(panel.title for panel in job.panels)
        for index, (ax, panel) in enumerate(zip_strict(axes, job.panels[: len(axes)])):
            on_before_save(
                fig,
                ax,
                BatchPlotContext(
                    flight_point=panel.flight_point,
                    fixed_sweeps=panel.fixed_sweeps,
                    sweep_key=job.sweep_key,
                    y_key=panel.y_key,
                    x_spec=job.x_spec,
                    y_spec=panel.y_spec,
                    polar_prefix=job.polar_prefix,
                    output_path=job.output_path,
                    panel_index=index,
                    fold_kind=job.kind,
                    fold_layout=job.layout,
                    fold_label=overlay_label if job.layout == "overlay" else panel.title,
                ),
            )

    figure_set_layout_pad(fig, h_pad=_COMPARE_LAYOUT_H_PAD)

    written = save_figure(fig, job.output_path, formats=formats)
    if builder is not None:
        builder.add(fig)
    plt.close(fig)
    return written


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------

# What batch_plot(pdf_report=...) accepts: a path for the common case, a spec
# when the defaults are not enough.
PdfReportArg = Union[str, Path, PdfReportSpec, None]


def _resolve_pdf_spec(pdf_report: PdfReportArg, *, style_profile: str, title: str) -> PdfReportSpec | None:
    """Normalise the ``pdf_report`` argument to a spec, or None."""
    if pdf_report is None:
        return None
    if isinstance(pdf_report, PdfReportSpec):
        return pdf_report
    return PdfReportSpec(path=pdf_report, title=title, profile=style_profile)


def _report_entries(jobs: Sequence[Any]) -> list[tuple[tuple[str, ...], str]]:
    """Section trail and label for every job, in render order.

    Grouped polar -> flight point, the same two levels ``_print_batch_file_report``
    already uses, so the PDF, the terminal report and the directory tree all tell
    the same story. Labels go through ``_cli_text``: the table of contents is
    plain text, and a literal ``$\\alpha$`` there would look broken.
    """
    entries: list[tuple[tuple[str, ...], str]] = []
    for job in jobs:
        if isinstance(job, _FoldJob):
            entries.append(
                (
                    (job.polar_prefix, "Folded"),
                    f"{job.output_path.stem} - {_cli_text(job.subtitle)}"
                    if job.subtitle
                    else job.output_path.stem,
                )
            )
            continue
        trail: tuple[str, ...] = (job.polar_prefix,)
        if job.flight_point_label:
            trail += (_cli_text(job.flight_point_label),)
        label = job.output_path.stem
        if job.case_label:
            label = f"{label} - {_cli_text(job.case_label)}"
        entries.append((trail, label))
    return entries


def _compare_report_entries(jobs: Sequence[_ComparePlotJob]) -> list[tuple[tuple[str, ...], str]]:
    """As :func:`_report_entries`, for compare jobs (grouped polar -> fixed sweep)."""
    entries: list[tuple[tuple[str, ...], str]] = []
    for job in jobs:
        trail: tuple[str, ...] = (job.polar_prefix,)
        if job.case_label:
            trail += (_cli_text(job.case_label),)
        entries.append((trail, job.output_path.stem))
    return entries


def _study_title(jobs: Sequence[object]) -> str:
    """Fallback cover title: the polars covered, or a plain word.

    Deliberately dull. A wrong-looking guessed title on a cover page is worse
    than an obviously generic one, and the caller can always pass a spec.
    """
    prefixes = sorted({getattr(job, "polar_prefix", "") for job in jobs} - {""})
    if not prefixes:
        return "Figures"
    if len(prefixes) <= 3:
        return ", ".join(prefixes)
    return f"{len(prefixes)} polars"


def _report_summary(
    jobs: Sequence[_BatchPlotJob],
    formats: Sequence[str],
    fold_jobs: Sequence[_FoldJob] = (),
) -> list[tuple[str, str]]:
    """Cover-page facts for a batch run."""
    polars = {job.polar_prefix for job in jobs}
    points = {job.flight_point_label for job in jobs if job.flight_point_label}
    sources: set[str] = set()
    for job in jobs:
        sources.update(curve.label for curve in job.curves)
    rows = [
        ("Figures", str(len(jobs))),
        ("Polars", str(len(polars))),
    ]
    if fold_jobs:
        rows.append(("Folded sheets", str(len(fold_jobs))))
    if points:
        rows.append(("Flight points", str(len(points))))
    if sources:
        rows.append(("Sources", ", ".join(sorted(sources))))
    if formats:
        rows.append(("Also exported", ", ".join(formats)))
    return rows


def _paths_for_formats(output_path: Path, formats: Sequence[str]) -> list[Path]:
    """Mirror ``save_figure`` path naming (stem + ``.{fmt}``)."""
    return [output_path.with_suffix(f".{fmt}") for fmt in formats]


def _is_picklable(obj: Any) -> bool:
    if obj is None:
        return True
    try:
        pickle.dumps(obj)
        return True
    except Exception:
        return False


def _resolve_n_jobs(n_jobs: int) -> int:
    if n_jobs == -1:
        return os.cpu_count() or 1
    if n_jobs < 1:
        raise ValueError(f"n_jobs must be >= 1 or -1, got {n_jobs}.")
    return n_jobs


def _format_values_preview(values: Sequence[Any], *, max_items: int = 12) -> str:
    """Compact preview of a unique-value list for CLI tables."""
    items = [_format_path_value(v) if isinstance(v, (int, float)) else str(v) for v in values]
    if len(items) <= max_items:
        return ", ".join(items)
    head = ", ".join(items[: max_items - 1])
    return f"{head}, … (+{len(items) - (max_items - 1)} more)"


_LATEX_CMD_RE = re.compile(r"\\([a-zA-Z]+)")


def _cli_text(text: str) -> str:
    """Strip simple LaTeX math markup (``$\\alpha$`` → ``alpha``) for CLI display.

    Figure titles keep the LaTeX form (matplotlib renders it); this is only for
    console/table output, where a literal ``$\\beta$`` would look broken.
    """
    return _LATEX_CMD_RE.sub(r"\1", text.replace("$", ""))


def _print_batch_plan(
    *,
    configuration_dict: dict[str, dict[str, Any]],
    y_axis_dict: dict[str, dict[str, Any]],
    completed_sweeps: dict[str, dict[str, Any]],
    completed_flight_points: dict[str, dict[str, Any]],
    jobs: Sequence[_BatchPlotJob],
    output_base: str | Path,
    formats: Sequence[str],
    style_profile: str,
    n_jobs: int,
    dry_run: bool,
    include_curve: Callable[..., bool] | None,
    on_before_save: Callable[..., Any] | None,
    excluded_from_flight_point: Sequence[str] = (),
    fold_jobs: Sequence[_FoldJob] = (),
    fold_specs: Sequence[FoldSpec] = (),
    clean: bool | str = False,
) -> None:
    """Pretty-print the batch execution plan (Rich when available)."""
    workers = _resolve_n_jobs(n_jobs)
    parallel_ok = workers > 1 and _is_picklable(on_before_save)
    effective_workers = workers if parallel_ok else 1
    if workers > 1 and not parallel_ok:
        parallel_note = f"requested {workers}, falling back to sequential (hooks not picklable)"
    elif effective_workers > 1:
        parallel_note = f"{effective_workers} process workers"
    else:
        parallel_note = "sequential (n_jobs=1)"

    n_figures = len(jobs) + len(fold_jobs)
    n_files = n_figures * len(formats)
    jobs_by_polar = Counter(job.polar_prefix for job in jobs)
    folds_by_polar = Counter(job.polar_prefix for job in fold_jobs)
    sources = list(configuration_dict.keys())
    y_keys = list(y_axis_dict.keys())

    overview_lines = [
        f"Sources      : {', '.join(sources)}  ({len(sources)})",
        f"Y axes       : {', '.join(y_keys)}  ({len(y_keys)})",
        f"Sweeps       : {', '.join(completed_sweeps.keys())}  ({len(completed_sweeps)})",
        f"Flight params: {', '.join(completed_flight_points.keys())}  ({len(completed_flight_points)})",
    ]
    if excluded_from_flight_point:
        overview_lines.append(
            f"FP excluded  : {', '.join(excluded_from_flight_point)}  "
            "(listed in flight_point_dict but used as sweep vars)"
        )
    ignored_keys = sorted(
        {key for keys in ignored_config_keys(configuration_dict).values() for key in keys}
    )
    if ignored_keys:
        overview_lines.append(
            f"Metadata keys: {', '.join(ignored_keys)}  "
            "(kept in configuration_dict, not sent to plot_line)"
        )
    overview_lines.extend(
        [
            f"Output base  : {output_base}",
            f"Formats      : {', '.join(formats)}",
            f"Style        : {style_profile}",
            f"Mode         : {'dry-run (no files written)' if dry_run else 'write'}",
            f"Hooks        : include_curve={'yes' if include_curve else 'no'}, "
            f"on_before_save={'yes' if on_before_save else 'no'}",
            f"Parallel     : {parallel_note}",
            f"Clean        : {_clean_note(clean)}",
            f"Fold         : {_fold_note(fold_specs, fold_jobs)}",
            f"Figures      : {len(jobs)} + {len(fold_jobs)} folded  →  {n_files} file(s)",
        ]
    )

    if _RICH and _console is not None:
        _console.print(
            Panel("\n".join(overview_lines), title="Batch plan", border_style="cyan")
        )

        fp_table = Table(title="Flight-point loops", show_header=True, header_style="bold")
        fp_table.add_column("Parameter", style="cyan")
        fp_table.add_column("n", justify="right", style="magenta")
        fp_table.add_column("Unique values")
        for key, spec in completed_flight_points.items():
            values = spec.get("values", [])
            label = spec.get("label", key)
            unit = spec.get("unit")
            name = f"{label}" if not unit or unit == "-" else f"{label} ({unit})"
            fp_table.add_row(f"{key}  [{name}]", str(len(values)), _format_values_preview(values))
        _console.print(fp_table)

        sw_table = Table(title="Sweep / polar loops", show_header=True, header_style="bold")
        sw_table.add_column("Sweep key", style="cyan")
        sw_table.add_column("Polar")
        sw_table.add_column("n", justify="right", style="magenta")
        sw_table.add_column("Unique values")
        for key, spec in completed_sweeps.items():
            values = spec.get("values", [])
            sw_table.add_row(
                key,
                str(spec.get("polar_prefix", "")),
                str(len(values)),
                _format_values_preview(values),
            )
        _console.print(sw_table)

        if jobs_by_polar:
            polar_table = Table(title="Figures per polar", show_header=True, header_style="bold")
            polar_table.add_column("Polar", style="cyan")
            polar_table.add_column("Figures", justify="right", style="green")
            polar_table.add_column("Folded", justify="right", style="yellow")
            for polar, count in sorted(jobs_by_polar.items()):
                polar_table.add_row(polar, str(count), str(folds_by_polar.get(polar, 0)))
            _console.print(polar_table)

        if fold_jobs:
            _console.print(_fold_plan_table(fold_specs, fold_jobs))
        return

    # Plain-text fallback
    print("=== Batch plan ===")
    for line in overview_lines:
        print(line)
    print("\nFlight-point loops:")
    for key, spec in completed_flight_points.items():
        values = spec.get("values", [])
        print(f"  {key}: n={len(values)}  [{_format_values_preview(values)}]")
    print("\nSweep / polar loops:")
    for key, spec in completed_sweeps.items():
        values = spec.get("values", [])
        print(
            f"  {key} ({spec.get('polar_prefix', '')}): "
            f"n={len(values)}  [{_format_values_preview(values)}]"
        )
    if jobs_by_polar:
        print("\nFigures per polar:")
        for polar, count in sorted(jobs_by_polar.items()):
            print(f"  {polar}: {count} (+{folds_by_polar.get(polar, 0)} folded)")
    for fold_label, fold_count in _fold_plan_rows(fold_specs, fold_jobs):
        print(f"  fold {fold_label}: {fold_count} sheet(s)")


def _clean_note(clean: bool | str) -> str:
    if not clean:
        return "no"
    mode = "figures" if clean is True else str(clean)
    return f"yes ({mode})"


def _fold_note(fold_specs: Sequence[FoldSpec], fold_jobs: Sequence[_FoldJob]) -> str:
    if not fold_specs:
        return "no"
    kinds = ", ".join(f"{spec.kind}/{spec.layout}" for spec in fold_specs)
    return f"{kinds}  →  {len(fold_jobs)} sheet(s)"


def _fold_spec_label(spec: FoldSpec) -> str:
    over = ", ".join(spec.over) if spec.over else "every varying key"
    if spec.kind == "y":
        over = "every Y"
    return f"{spec.kind}/{spec.layout} over {over} (max {spec.max_panels}/sheet)"


def _fold_plan_rows(
    fold_specs: Sequence[FoldSpec], fold_jobs: Sequence[_FoldJob]
) -> list[tuple[str, int]]:
    """Sheets produced per requested fold, matched on (kind, layout).

    A spec that produced nothing still gets a row with a zero: silently
    dropping it is how a typo in ``over=`` looks exactly like a study where
    nothing varies.
    """
    counts = Counter((job.kind, job.layout) for job in fold_jobs)
    return [
        (_fold_spec_label(spec), counts.get((spec.kind, spec.layout), 0))
        for spec in fold_specs
    ]


def _fold_plan_table(fold_specs: Sequence[FoldSpec], fold_jobs: Sequence[_FoldJob]) -> Any:
    table = Table(title="Folded sheets", show_header=True, header_style="bold")
    table.add_column("Fold", style="cyan")
    table.add_column("Sheets", justify="right", style="green")
    for label, count in _fold_plan_rows(fold_specs, fold_jobs):
        table.add_row(label, str(count))
    return table


def _progress_columns() -> list[Any]:
    return [
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TextColumn("ETA"),
        TimeRemainingColumn(),
    ]


def _init_worker() -> None:
    """Force a headless backend inside one batch worker process.

    Passed as the ``initializer`` of the process pools below, so it runs once
    per worker at start-up and never in the parent. A worker has no display of
    its own, and under the default *fork* start method it would otherwise
    inherit a live GUI backend from the parent — which is precisely the setup
    that deadlocks or crashes in a child process.

    Being an initializer rather than a call inside the render functions is what
    keeps the caller's session intact: those functions also run in-process when
    ``n_jobs=1`` (the default), where switching the global backend would break
    interactive plotting for everything the user does afterwards.
    """
    matplotlib.use("Agg")


def _render_one_job(
    job: _BatchPlotJob,
    style_profile: str,
    formats: tuple[str, ...],
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None,
    builder: ReportBuilder | None = None,
) -> list[Path]:
    """Render and export a single batch plot job (safe for process workers).

    *builder*, when given, receives the figure before it is closed, so the PDF
    report gets the real vector figure rather than a re-read raster. It is
    keyword-only in effect: the process pool submits the first four arguments
    positionally and never a builder, which could not be pickled anyway.
    """
    use_style(style_profile)

    fig, ax = plt.subplots()
    for curve in job.curves:
        plot_line(
            ax,
            curve.x,
            curve.y,
            label=curve.label,
            **curve.style_kwargs,
        )

    ax.set_xlabel(format_axis_label(job.x_spec, job.sweep_key))
    ax.set_ylabel(format_axis_label(job.y_spec, job.y_key))
    make_legend(ax)
    set_title(ax, job.title)

    context = BatchPlotContext(
        flight_point=job.flight_point,
        fixed_sweeps=job.fixed_sweeps,
        sweep_key=job.sweep_key,
        y_key=job.y_key,
        x_spec=job.x_spec,
        y_spec=job.y_spec,
        polar_prefix=job.polar_prefix,
        output_path=job.output_path,
    )
    if on_before_save is not None:
        on_before_save(fig, ax, context)

    written = save_figure(fig, job.output_path, formats=formats)
    if builder is not None:
        builder.add(fig)
    plt.close(fig)
    return written


def _render_any(
    job: Any,
    style_profile: str,
    formats: tuple[str, ...],
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None,
    builder: ReportBuilder | None = None,
) -> list[Path]:
    """Render whichever kind of job this is.

    A single entry point is what lets folded sheets travel the same pipeline as
    ordinary figures — the same process pool, the same progress bar, the same
    PDF builder — instead of needing a second pass with its own copy of all of
    it. It is also what the pool submits, so it must stay picklable-by-name
    (module level) and take its arguments positionally.
    """
    if isinstance(job, _FoldJob):
        return _render_one_fold_job(job, style_profile, formats, on_before_save, builder)
    return _render_one_job(job, style_profile, formats, on_before_save, builder)


def _any_job_label(job: Any) -> str:
    """Progress-bar description for either kind of job."""
    if isinstance(job, _FoldJob):
        context = _cli_text(job.context_label) or "all conditions"
        return f"{job.polar_prefix} · fold · {context} · {_cli_text(job.label)}"
    point = _cli_text(job.flight_point_label)
    if job.case_label:
        point = f"{point}, {_cli_text(job.case_label)}"
    return f"{job.polar_prefix} · {point} · {job.y_key} vs {job.sweep_key}"


def _run_jobs(
    jobs: Sequence[Any],
    *,
    style_profile: str,
    formats: tuple[str, ...],
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None,
    n_jobs: int,
    verbose: bool,
    pdf_spec: PdfReportSpec | None = None,
    pdf_summary: Sequence[tuple[str, str]] = (),
) -> list[Path]:
    """Execute plot jobs sequentially or via a process pool.

    A PDF report forces sequential rendering: the pages must be written in order
    and ``PdfPages`` cannot cross a process boundary. That is the same trade the
    picklability fallback below already makes, and it is warned about the same way.
    """
    workers = _resolve_n_jobs(n_jobs)
    use_parallel = workers > 1

    if use_parallel and pdf_spec is not None:
        warnings.warn(
            "pdf_report requires sequential rendering; falling back to n_jobs=1. "
            "Run without pdf_report for parallel rendering, then assemble the "
            "report from the PNGs with cfd_plot.pdf.pdf_report().",
            UserWarning,
            stacklevel=3,
        )
        use_parallel = False
        workers = 1

    if use_parallel and not _is_picklable(on_before_save):
        warnings.warn(
            "on_before_save is not picklable; falling back to sequential rendering. "
            "Use a top-level named function for n_jobs > 1.",
            UserWarning,
            stacklevel=3,
        )
        use_parallel = False
        workers = 1

    written_paths: list[Path] = []
    total = len(jobs)
    show_progress = verbose and total > 0
    task_desc = f"batch ({workers} worker{'s' if workers != 1 else ''})"

    _job_label = _any_job_label

    if not use_parallel:
        use_style(style_profile)
        with ExitStack() as stack:
            builder: ReportBuilder | None = None
            if pdf_spec is not None and jobs:
                spec = replace(pdf_spec, summary=pdf_spec.summary or tuple(pdf_summary))
                builder = stack.enter_context(ReportBuilder(spec, _report_entries(jobs)))

            if show_progress and _RICH and Progress is not None and _console is not None:
                with Progress(*_progress_columns(), console=_console, transient=False) as progress:
                    task_id = progress.add_task(task_desc, total=total)
                    for job in jobs:
                        progress.update(task_id, description=_job_label(job))
                        written_paths.extend(
                            _render_any(job, style_profile, formats, on_before_save, builder)
                        )
                        progress.advance(task_id)
                return written_paths

            for index, job in enumerate(jobs, start=1):
                if verbose:
                    print(f"[batch] [{index}/{total}] writing {_job_label(job)}")
                written_paths.extend(
                    _render_any(job, style_profile, formats, on_before_save, builder)
                )
        return written_paths

    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as executor:
        futures = [
            executor.submit(_render_any, job, style_profile, formats, on_before_save)
            for job in jobs
        ]
        if show_progress and _RICH and Progress is not None and _console is not None:
            with Progress(*_progress_columns(), console=_console, transient=False) as progress:
                task_id = progress.add_task(task_desc, total=total)
                for job, future in zip_strict(jobs, futures):
                    progress.update(task_id, description=_job_label(job))
                    written_paths.extend(future.result())
                    progress.advance(task_id)
            return written_paths

        for index, (job, future) in enumerate(zip_strict(jobs, futures), start=1):
            if verbose:
                print(f"[batch] [{index}/{total}] writing {_job_label(job)}")
            written_paths.extend(future.result())
    return written_paths


def _print_batch_file_report(jobs: Sequence[_BatchPlotJob], formats: Sequence[str]) -> None:
    """Pretty-print exported batch figures, grouped by polar then flight point.

    A flat file listing repeats the same ``Y_vs_X.svg`` filename once per
    flight point (and fixed-sweep combination), which makes them
    indistinguishable. Each flight point (the real loop variable in
    ``batch_plot``) gets its own section per polar; rows within a section only
    need to show what still varies there — the fixed-sweep case (if any) and
    the Y variable.
    """
    groups: dict[str, dict[str, list[_BatchPlotJob]]] = {}
    for job in jobs:
        groups.setdefault(job.polar_prefix, {}).setdefault(job.flight_point_label, []).append(job)

    if _RICH and _console is not None:
        for polar, points in groups.items():
            for flight_point_label, point_jobs in points.items():
                point = _cli_text(flight_point_label) if flight_point_label else "(none)"
                n_files = len(point_jobs) * len(formats)
                table = Table(
                    title=f"{polar}  —  {point}  —  {n_files} file(s)",
                    show_header=True,
                    header_style="bold",
                )
                table.add_column("Fixed sweep", style="cyan")
                table.add_column("Figure")
                table.add_column("Format", style="magenta")
                table.add_column("Size", justify="right", style="green")
                for job in point_jobs:
                    case = _cli_text(job.case_label) if job.case_label else "—"
                    for path in _paths_for_formats(job.output_path, formats):
                        size_kb = path.stat().st_size / 1024
                        table.add_row(
                            case,
                            f"{job.y_key} vs {job.sweep_key}",
                            path.suffix.lstrip(".").upper(),
                            f"{size_kb:.1f} kB",
                        )
                _console.print(table)
        return

    # Plain-text fallback
    print("=== Batch plot outputs ===")
    for polar, points in groups.items():
        print(f"\n{polar}:")
        for flight_point_label, point_jobs in points.items():
            point = _cli_text(flight_point_label) if flight_point_label else "(none)"
            print(f"  {point}:")
            for job in point_jobs:
                case = _cli_text(job.case_label) if job.case_label else "—"
                for path in _paths_for_formats(job.output_path, formats):
                    size_kb = path.stat().st_size / 1024
                    print(
                        f"    [{case}] {job.y_key} vs {job.sweep_key:8s} "
                        f"{path.suffix.lstrip('.').upper():>4s}  {size_kb:>7.1f} kB"
                    )


def _print_fold_file_report(jobs: Sequence[_FoldJob], formats: Sequence[str]) -> None:
    """Pretty-print the folded sheets, grouped by polar.

    Kept separate from :func:`_print_batch_file_report` because the two answer
    different questions: that one is "what exists for this flight point", this
    one is "what did folding collapse, and into how many sheets". Merging them
    would bury a handful of bonus figures inside hundreds of ordinary rows.
    """
    if not jobs:
        return

    groups: dict[str, list[_FoldJob]] = {}
    for job in jobs:
        groups.setdefault(job.polar_prefix, []).append(job)

    if _RICH and _console is not None:
        for polar, polar_jobs in groups.items():
            n_files = len(polar_jobs) * len(formats)
            table = Table(
                title=f"{polar}  —  folded  —  {n_files} file(s)",
                show_header=True,
                header_style="bold",
            )
            table.add_column("Fold", style="cyan")
            table.add_column("Sheet")
            table.add_column("Panels", justify="right")
            table.add_column("Format", style="magenta")
            table.add_column("Size", justify="right", style="green")
            for job in polar_jobs:
                kind = f"{job.kind}/{job.layout}"
                for path in _paths_for_formats(job.output_path, formats):
                    size_kb = path.stat().st_size / 1024
                    table.add_row(
                        kind,
                        path.stem,
                        str(len(job.panels)),
                        path.suffix.lstrip(".").upper(),
                        f"{size_kb:.1f} kB",
                    )
            _console.print(table)
        return

    # Plain-text fallback
    print("=== Folded sheets ===")
    for polar, polar_jobs in groups.items():
        print(f"\n{polar}:")
        for job in polar_jobs:
            for path in _paths_for_formats(job.output_path, formats):
                size_kb = path.stat().st_size / 1024
                print(
                    f"  [{job.kind}/{job.layout}] {path.stem} "
                    f"({len(job.panels)} panels) "
                    f"{path.suffix.lstrip('.').upper():>4s}  {size_kb:>7.1f} kB"
                )


def _print_clean_report(clean_report: CleanReport) -> None:
    """Say what the pre-run clean removed — silence here is indistinguishable
    from a clean that never ran, and this one deletes files."""
    line = clean_report.summary()
    if _RICH and _console is not None:
        _console.print(f"[yellow]{line}[/yellow]")
    else:
        print(line)


def batch_plot(
    *,
    configuration_dict: dict[str, dict[str, Any]],
    y_axis_dict: dict[str, dict[str, Any]],
    sweep_dict: dict[str, dict[str, Any]] | None = None,
    x_axis_dict: dict[str, dict[str, Any]] | None = None,
    flight_point_dict: dict[str, Any] | None = None,
    output_base: str | Path,
    style_profile: str = "paper",
    formats: tuple[str, ...] = ("svg",),
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None = None,
    include_curve: Callable[..., bool] | None = None,
    report: bool = True,
    verbose: bool = False,
    dry_run: bool = False,
    n_jobs: int = 1,
    pdf_report: PdfReportArg = None,
    clean: bool | str = False,
    fold: FoldArg = None,
) -> list[Path]:
    """Generate polar figures for every flight point and sweep combination.

    For each sweep variable *s* (the x-axis of a polar):

    1. Flight-point keys are taken from ``flight_point_dict`` minus all sweep keys.
    2. Every other sweep variable is held fixed at each of its unique values.
    3. At each (flight point, fixed-sweep combo), y is plotted vs. *s* for every source.

    Output layout::

        output_base/ALPHA_POLAR/M_0.8/Z_8000/BETA_2/CN_vs_alpha.svg
        output_base/BETA_POLAR/M_0.8/Z_8000/ALPHA_3/CN_vs_beta.svg

    Parameters
    ----------
    report :
        Pretty-print exported files, grouped by polar then flight point, after
        a real run.
    verbose :
        Print a Rich plan summary (sweeps, flight points, figure counts,
        parallel setup) and a progress bar with elapsed time / ETA.
    dry_run :
        Enumerate output paths without creating figures or writing files.
    n_jobs :
        Parallel workers (``1`` = sequential, ``-1`` = all CPUs). Parallel mode
        requires a picklable ``on_before_save`` (top-level function); otherwise
        rendering falls back to sequential.
    pdf_report :
        Also assemble every figure into one navigable PDF — cover page, table of
        contents, a divider per polar, and a clickable outline where ``pypdf`` is
        installed. Pass a path, or a
        :class:`~cfd_plot.pdf.PdfReportSpec` to control the layout.

        The figures go in as **vector**, because they are written while they are
        still open; a report assembled afterwards from the files on disk can only
        be raster. The cost is that rendering becomes sequential (``n_jobs`` is
        forced to 1, with a warning).

        ``formats=()`` is legal alongside it, and means "the report is the
        deliverable" — no loose figure files at all.
    clean :
        Wipe ``output_base`` before rendering. ``True`` (or ``"figures"``)
        deletes only files with a figure extension and prunes the directories
        left empty; ``"all"`` removes the whole tree. Renaming a Y variable or
        dropping a flight point otherwise leaves the previous run's figures in
        place, and nothing in the new run overwrites them — you end up reading
        a directory that mixes two studies. Honours ``dry_run``: it then
        reports what it would delete and deletes nothing. See
        :func:`cfd_plot.clean_figure_dir` for the safety guards.
    fold :
        Also write *bonus sheets* that gather sibling figures, so a comparison
        does not mean opening one file per directory. Accepts a
        :class:`FoldSpec`, a shorthand string, or a sequence of either:

        ``"y"``
            One sheet per condition, with every Y of ``y_axis_dict`` as a
            panel, written **beside** the figures it folds
            (``FOLD_Y_vs_alpha.svg``). Panels keep independent axes — the
            quantities have different units.
        ``"context"``
            One sheet per Y, with one panel per condition that differs only by
            a directory level (every altitude, say), written under
            ``<POLAR>/FOLD/``. Panels share their scales by default.
        ``"context-overlay"`` (alias ``"overlay"``)
            The same family drawn on a *single* axes instead of panels, under
            ``<POLAR>/FOLD_OVERLAY/``. The readable choice for one source over
            a handful of conditions.
        ``True``
            Shorthand for ``("y", "context")``.

        Use a :class:`FoldSpec` to choose which keys to fold over
        (``over=("Altitude_m",)``), how many panels per sheet (``max_panels``,
        default 6 — a larger family is split into numbered sheets rather than
        shrunk), the grid width, or the axis synchronisation. Folded sheets go
        through the same hooks, PDF report and parallel pipeline as ordinary
        figures.
    """
    if not y_axis_dict:
        raise ValueError("y_axis_dict must contain at least one entry.")

    resolved_sweep_dict = _coalesce_sweep_dict(sweep_dict, x_axis_dict)
    if not resolved_sweep_dict:
        raise ValueError("Either sweep_dict or x_axis_dict must be provided.")

    completed_sweeps = _prepare_sweep_dict(configuration_dict, resolved_sweep_dict)
    completed_flight_points = _prepare_flight_point_dict(
        configuration_dict,
        flight_point_dict,
        list(resolved_sweep_dict.keys()),
    )

    jobs = _enumerate_jobs(
        configuration_dict=configuration_dict,
        y_axis_dict=y_axis_dict,
        completed_sweeps=completed_sweeps,
        completed_flight_points=completed_flight_points,
        output_base=output_base,
        include_curve=include_curve,
    )
    fold_specs = _resolve_fold_specs(fold)
    fold_jobs = _enumerate_fold_jobs(
        jobs,
        fold_specs,
        y_axis_dict=y_axis_dict,
        completed_sweeps=completed_sweeps,
        completed_flight_points=completed_flight_points,
        output_base=output_base,
    )
    render_order = _merge_render_order(jobs, fold_jobs)

    if verbose:
        requested_fp_keys = list(flight_point_dict.keys()) if flight_point_dict else []
        excluded_from_flight_point = [
            key for key in requested_fp_keys if key in completed_sweeps
        ]
        _print_batch_plan(
            configuration_dict=configuration_dict,
            y_axis_dict=y_axis_dict,
            completed_sweeps=completed_sweeps,
            completed_flight_points=completed_flight_points,
            jobs=jobs,
            output_base=output_base,
            formats=formats,
            style_profile=style_profile,
            n_jobs=n_jobs,
            dry_run=dry_run,
            include_curve=include_curve,
            on_before_save=on_before_save,
            excluded_from_flight_point=excluded_from_flight_point,
            fold_jobs=fold_jobs,
            fold_specs=fold_specs,
            clean=clean,
        )

    # Cleaning runs after the plan is printed and before anything is written,
    # so a dry run still shows both what would go and what would arrive.
    if clean:
        clean_report = clean_figure_dir(output_base, mode=clean, dry_run=dry_run)
        if verbose or report:
            _print_clean_report(clean_report)

    if dry_run:
        planned: list[Path] = []
        for job in render_order:
            planned.extend(_paths_for_formats(job.output_path, formats))
        if verbose:
            fold_note = f" (incl. {len(fold_jobs)} folded)" if fold_jobs else ""
            msg = (
                f"Dry run complete: {len(render_order)} figure(s){fold_note} → "
                f"{len(planned)} file(s) (nothing written)."
            )
            if _RICH and _console is not None:
                _console.print(f"[yellow]{msg}[/yellow]")
            else:
                print(msg)
        return planned

    spec = _resolve_pdf_spec(pdf_report, style_profile=style_profile, title=_study_title(jobs))
    written_paths = _run_jobs(
        render_order,
        style_profile=style_profile,
        formats=formats,
        on_before_save=on_before_save,
        n_jobs=n_jobs,
        verbose=verbose,
        pdf_spec=spec,
        pdf_summary=_report_summary(jobs, formats, fold_jobs),
    )

    if spec is not None and render_order:
        written_paths.append(Path(spec.path))

    if report and written_paths:
        _print_batch_file_report(jobs, formats)
        _print_fold_file_report(fold_jobs, formats)

    return written_paths



def _enumerate_compare_jobs(
    *,
    configuration_dict: dict[str, dict[str, Any]],
    y_axis_dict: dict[str, dict[str, Any]],
    completed_sweeps: dict[str, dict[str, Any]],
    completed_flight_points: dict[str, dict[str, Any]],
    compare_flight_points: dict[str, dict[str, float]],
    output_base: str | Path,
    max_cols: int,
    include_curve: Callable[..., bool] | None,
) -> list[_ComparePlotJob]:
    """Build compare jobs: one multi-panel figure per polar / fixed-sweep / Y."""
    sweep_keys = list(completed_sweeps.keys())
    flight_point_keys = list(completed_flight_points.keys())
    varying_sw_keys = varying_flight_keys(configuration_dict, sweep_keys)
    compare_folder_name = "_".join(compare_flight_points.keys())
    jobs: list[_ComparePlotJob] = []

    for x_key, x_spec in completed_sweeps.items():
        polar_prefix = x_spec["polar_prefix"]
        x_col = x_spec["col_name"]
        x_save_name = x_spec.get("x_save_name", x_key)
        other_sweep_keys = [key for key in sweep_keys if key != x_key]
        varying_other_sweep_keys = [key for key in other_sweep_keys if key in varying_sw_keys]

        for fixed_sweeps in iter_fixed_sweep_combinations(
            configuration_dict,
            sweep_keys,
            x_key,
        ):
            for y_key, y_spec in y_axis_dict.items():
                y_col = y_spec["col_name"]
                y_save_name = y_spec.get("y_save_name", y_key)
                panels: list[_ComparePanel] = []

                for name, flight_point in compare_flight_points.items():
                    curves = _collect_source_curves(
                        configuration_dict,
                        flight_point=flight_point,
                        fixed_sweeps=fixed_sweeps,
                        flight_point_keys=flight_point_keys,
                        x_key=x_key,
                        y_key=y_key,
                        x_col=x_col,
                        y_col=y_col,
                        include_curve=include_curve,
                    )
                    if not curves:
                        continue
                    panel_title = (
                        f"{name} "
                        f"({format_flight_point_title_suffix(flight_point, flight_point_keys, completed_flight_points)})"
                    )
                    panels.append(
                        _ComparePanel(
                            name=name,
                            flight_point=flight_point,
                            curves=tuple(curves),
                            title=panel_title,
                        )
                    )

                if not panels:
                    continue

                output_path = build_compare_output_path(
                    output_base,
                    fixed_sweeps,
                    varying_other_sweep_keys,
                    polar_prefix,
                    x_save_name,
                    y_save_name,
                    completed_sweeps,
                    compare_folder=compare_folder_name,
                )
                y_label = format_axis_title_label(y_spec, y_key)
                x_label = format_axis_title_label(x_spec, x_key)
                if fixed_sweeps:
                    case_label = format_flight_point_title_suffix(
                        fixed_sweeps,
                        list(fixed_sweeps.keys()),
                        completed_sweeps,
                    )
                    suptitle = f"{y_label} vs. {x_label} ({case_label})"
                else:
                    case_label = ""
                    suptitle = f"{y_label} vs. {x_label}"

                jobs.append(
                    _ComparePlotJob(
                        fixed_sweeps=fixed_sweeps,
                        flight_point_keys=tuple(flight_point_keys),
                        sweep_key=x_key,
                        y_key=y_key,
                        x_spec=x_spec,
                        y_spec=y_spec,
                        polar_prefix=polar_prefix,
                        output_path=output_path,
                        suptitle=suptitle,
                        case_label=case_label,
                        panels=tuple(panels),
                        max_cols=max_cols,
                    )
                )
    return jobs


def _render_one_compare_job(
    job: _ComparePlotJob,
    style_profile: str,
    formats: tuple[str, ...],
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None,
    builder: ReportBuilder | None = None,
) -> list[Path]:
    """Render a multi-panel compare figure (safe for process workers).

    *builder* takes the figure before it is closed; see ``_render_one_job``.
    """
    use_style(style_profile)

    n_panels = len(job.panels)
    nrows, ncols = _subplot_grid_shape(n_panels, job.max_cols)
    base_w, base_h = plt.rcParams["figure.figsize"]
    panel_h = base_h * _COMPARE_PANEL_HEIGHT_FACTOR
    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=(base_w * ncols, panel_h * nrows),
        squeeze=False,
        sharex=False,
        sharey=False,
    )
    axes_flat = list(axes.ravel())

    for index, panel in enumerate(job.panels):
        ax = axes_flat[index]
        for curve in panel.curves:
            plot_line(
                ax,
                curve.x,
                curve.y,
                label=curve.label,
                **curve.style_kwargs,
            )
        ax.set_xlabel(format_axis_label(job.x_spec, job.sweep_key))
        ax.set_ylabel(format_axis_label(job.y_spec, job.y_key))
        make_legend(ax)
        set_title(ax, panel.title)

        context = BatchPlotContext(
            flight_point=panel.flight_point,
            fixed_sweeps=job.fixed_sweeps,
            sweep_key=job.sweep_key,
            y_key=job.y_key,
            x_spec=job.x_spec,
            y_spec=job.y_spec,
            polar_prefix=job.polar_prefix,
            output_path=job.output_path,
            compare_name=panel.name,
            panel_index=index,
        )
        if on_before_save is not None:
            on_before_save(fig, ax, context)

    for ax in axes_flat[n_panels:]:
        ax.set_visible(False)

    panel_titlesize = plt.rcParams["axes.titlesize"]
    set_suptitle(fig, job.suptitle, fontsize=panel_titlesize * 1.3, fontweight="bold")

    # All style profiles enable constrained_layout (see .mplstyle files), which makes
    # fig.tight_layout() a no-op: Figure.set_layout_engine(None) re-selects 'constrained'
    # from rcParams in its `finally` clause, silently discarding any tight_layout rect/pad.
    # Tune the actual active engine's padding instead of the ineffective tight_layout call.
    # (figure_set_layout_pad also covers Matplotlib < 3.6, which has no engine
    # object — see cfd_plot._compat.)
    figure_set_layout_pad(fig, h_pad=_COMPARE_LAYOUT_H_PAD)

    written = save_figure(fig, job.output_path, formats=formats)
    if builder is not None:
        builder.add(fig)
    plt.close(fig)
    return written


def _run_compare_jobs(
    jobs: list[_ComparePlotJob],
    *,
    style_profile: str,
    formats: tuple[str, ...],
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None,
    n_jobs: int,
    verbose: bool,
    pdf_spec: PdfReportSpec | None = None,
) -> list[Path]:
    """Execute compare jobs sequentially or via a process pool.

    As in ``_run_jobs``, a PDF report forces sequential rendering.
    """
    workers = _resolve_n_jobs(n_jobs)
    use_parallel = workers > 1

    if use_parallel and pdf_spec is not None:
        warnings.warn(
            "pdf_report requires sequential rendering; falling back to n_jobs=1.",
            UserWarning,
            stacklevel=3,
        )
        use_parallel = False
        workers = 1

    if use_parallel and not _is_picklable(on_before_save):
        warnings.warn(
            "on_before_save is not picklable; falling back to sequential rendering. "
            "Use a top-level named function for n_jobs > 1.",
            UserWarning,
            stacklevel=3,
        )
        use_parallel = False
        workers = 1

    written_paths: list[Path] = []
    total = len(jobs)
    show_progress = verbose and total > 0
    task_desc = f"compare ({workers} worker{'s' if workers != 1 else ''})"

    def _job_label(job: _ComparePlotJob) -> str:
        case = _cli_text(job.case_label) if job.case_label else "no fixed sweep"
        return f"{job.polar_prefix} · {case} · {job.y_key} vs {job.sweep_key}"

    if not use_parallel:
        use_style(style_profile)
        with ExitStack() as stack:
            builder: ReportBuilder | None = None
            if pdf_spec is not None and jobs:
                builder = stack.enter_context(ReportBuilder(pdf_spec, _compare_report_entries(jobs)))

            if show_progress and _RICH and Progress is not None and _console is not None:
                with Progress(*_progress_columns(), console=_console, transient=False) as progress:
                    task_id = progress.add_task(task_desc, total=total)
                    for job in jobs:
                        progress.update(task_id, description=_job_label(job))
                        written_paths.extend(
                            _render_one_compare_job(job, style_profile, formats, on_before_save, builder)
                        )
                        progress.advance(task_id)
                return written_paths

            for index, job in enumerate(jobs, start=1):
                if verbose:
                    print(f"[batch] [{index}/{total}] writing {_job_label(job)}")
                written_paths.extend(
                    _render_one_compare_job(job, style_profile, formats, on_before_save, builder)
                )
        return written_paths

    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as executor:
        futures = [
            executor.submit(
                _render_one_compare_job, job, style_profile, formats, on_before_save
            )
            for job in jobs
        ]
        if show_progress and _RICH and Progress is not None and _console is not None:
            with Progress(*_progress_columns(), console=_console, transient=False) as progress:
                task_id = progress.add_task(task_desc, total=total)
                for job, future in zip_strict(jobs, futures):
                    progress.update(task_id, description=_job_label(job))
                    written_paths.extend(future.result())
                    progress.advance(task_id)
            return written_paths

        for index, (job, future) in enumerate(zip_strict(jobs, futures), start=1):
            if verbose:
                print(f"[batch] [{index}/{total}] writing {_job_label(job)}")
            written_paths.extend(future.result())
    return written_paths


def _print_compare_plan(
    *,
    configuration_dict: dict[str, dict[str, Any]],
    y_axis_dict: dict[str, dict[str, Any]],
    completed_sweeps: dict[str, dict[str, Any]],
    completed_flight_points: dict[str, dict[str, Any]],
    normalized_compare: dict[str, dict[str, float]],
    jobs: Sequence[_ComparePlotJob],
    output_base: str | Path,
    formats: Sequence[str],
    style_profile: str,
    max_cols: int,
    n_jobs: int,
    dry_run: bool,
    include_curve: Callable[..., bool] | None,
    on_before_save: Callable[..., Any] | None,
) -> None:
    """Pretty-print the compare-mode execution plan (Rich when available).

    Unlike :func:`_print_batch_plan`, this describes what is actually
    happening in compare mode: a fixed, named set of flight points rendered
    as subplots, repeated once per polar / fixed-sweep-value / Y — it does
    not claim to "loop" over flight-point parameters the way ``batch_plot``
    does.
    """
    workers = _resolve_n_jobs(n_jobs)
    parallel_ok = workers > 1 and _is_picklable(on_before_save)
    effective_workers = workers if parallel_ok else 1
    if workers > 1 and not parallel_ok:
        parallel_note = f"requested {workers}, falling back to sequential (hooks not picklable)"
    elif effective_workers > 1:
        parallel_note = f"{effective_workers} process workers"
    else:
        parallel_note = "sequential (n_jobs=1)"

    n_files = len(jobs) * len(formats)
    jobs_by_polar = Counter(job.polar_prefix for job in jobs)
    sources = list(configuration_dict.keys())
    y_keys = list(y_axis_dict.keys())

    overview_lines = [
        f"Sources         : {', '.join(sources)}  ({len(sources)})",
        f"Y axes          : {', '.join(y_keys)}  ({len(y_keys)})",
        f"Sweeps          : {', '.join(completed_sweeps.keys())}  ({len(completed_sweeps)})",
        f"Compared points : {', '.join(normalized_compare.keys())}  ({len(normalized_compare)})",
        f"Panels / figure : up to {max_cols} column(s)",
        f"Output base     : {output_base}",
        f"Formats         : {', '.join(formats)}",
        f"Style           : {style_profile}",
        f"Mode            : {'dry-run (no files written)' if dry_run else 'write'}",
        f"Hooks           : include_curve={'yes' if include_curve else 'no'}, "
        f"on_before_save={'yes' if on_before_save else 'no'}",
        f"Parallel        : {parallel_note}",
        f"Figures         : {len(jobs)}  →  {n_files} file(s)",
    ]

    if _RICH and _console is not None:
        _console.print(
            Panel(
                "\n".join(overview_lines),
                title="Compare plan",
                border_style="cyan",
            )
        )

        cmp_table = Table(
            title="Compared flight points", show_header=True, header_style="bold"
        )
        cmp_table.add_column("Name", style="cyan")
        cmp_table.add_column("Values")
        fp_keys = list(completed_flight_points.keys())
        for name, values in normalized_compare.items():
            cmp_table.add_row(
                name,
                _cli_text(
                    format_flight_point_title_suffix(values, fp_keys, completed_flight_points)
                ),
            )
        _console.print(cmp_table)

        sw_table = Table(title="Sweep / polar loops", show_header=True, header_style="bold")
        sw_table.add_column("Sweep key", style="cyan")
        sw_table.add_column("Polar")
        sw_table.add_column("n", justify="right", style="magenta")
        sw_table.add_column("Unique values")
        for key, spec in completed_sweeps.items():
            values = spec.get("values", [])
            sw_table.add_row(
                key,
                str(spec.get("polar_prefix", "")),
                str(len(values)),
                _format_values_preview(values),
            )
        _console.print(sw_table)

        if jobs_by_polar:
            polar_table = Table(title="Figures per polar", show_header=True, header_style="bold")
            polar_table.add_column("Polar", style="cyan")
            polar_table.add_column("Figures", justify="right", style="green")
            for polar, count in sorted(jobs_by_polar.items()):
                polar_table.add_row(polar, str(count))
            _console.print(polar_table)
        return

    # Plain-text fallback
    print("=== Compare plan ===")
    for line in overview_lines:
        print(line)
    print("\nCompared flight points:")
    fp_keys = list(completed_flight_points.keys())
    for name, values in normalized_compare.items():
        suffix = _cli_text(
            format_flight_point_title_suffix(values, fp_keys, completed_flight_points)
        )
        print(f"  {name}: {suffix}")
    print("\nSweep / polar loops:")
    for key, spec in completed_sweeps.items():
        values = spec.get("values", [])
        print(
            f"  {key} ({spec.get('polar_prefix', '')}): "
            f"n={len(values)}  [{_format_values_preview(values)}]"
        )
    if jobs_by_polar:
        print("\nFigures per polar:")
        for polar, count in sorted(jobs_by_polar.items()):
            print(f"  {polar}: {count}")


def _print_compare_file_report(
    jobs: Sequence[_ComparePlotJob], formats: Sequence[str]
) -> None:
    """Pretty-print exported compare figures, grouped by polar then flight point.

    Each exported figure is named after its Y variable (e.g. ``CN_vs_alpha.svg``),
    and that same filename repeats once per fixed-sweep flight point (e.g. once
    for beta=0, once for beta=2). A flat file listing makes those repeats
    indistinguishable, so results are grouped by polar and annotated with the
    flight point each row belongs to.
    """
    groups: dict[str, dict[str, list[_ComparePlotJob]]] = {}
    for job in jobs:
        groups.setdefault(job.polar_prefix, {}).setdefault(job.case_label, []).append(job)

    if _RICH and _console is not None:
        for polar, cases in groups.items():
            n_files = sum(len(js) for js in cases.values()) * len(formats)
            table = Table(
                title=f"{polar}  —  {n_files} file(s)",
                show_header=True,
                header_style="bold",
            )
            table.add_column("Flight point", style="cyan")
            table.add_column("Figure")
            table.add_column("Format", style="magenta")
            table.add_column("Size", justify="right", style="green")
            for case_label, case_jobs in cases.items():
                label = _cli_text(case_label) if case_label else "(no fixed sweep)"
                for job in case_jobs:
                    for path in _paths_for_formats(job.output_path, formats):
                        size_kb = path.stat().st_size / 1024
                        table.add_row(
                            label,
                            f"{job.y_key} vs {job.sweep_key}",
                            path.suffix.lstrip(".").upper(),
                            f"{size_kb:.1f} kB",
                        )
            _console.print(table)
        return

    # Plain-text fallback
    print("=== Batch compare outputs ===")
    for polar, cases in groups.items():
        print(f"\n{polar}:")
        for case_label, case_jobs in cases.items():
            label = _cli_text(case_label) if case_label else "(no fixed sweep)"
            print(f"  {label}:")
            for job in case_jobs:
                for path in _paths_for_formats(job.output_path, formats):
                    size_kb = path.stat().st_size / 1024
                    print(
                        f"    {job.y_key} vs {job.sweep_key:8s} "
                        f"{path.suffix.lstrip('.').upper():>4s}  {size_kb:>7.1f} kB"
                    )


def batch_compare_flight_points(
    *,
    configuration_dict: dict[str, dict[str, Any]],
    y_axis_dict: dict[str, dict[str, Any]],
    compare_flight_points: dict[str, dict[str, Any]],
    sweep_dict: dict[str, dict[str, Any]] | None = None,
    x_axis_dict: dict[str, dict[str, Any]] | None = None,
    flight_point_dict: dict[str, Any] | None = None,
    output_base: str | Path,
    style_profile: str = "paper",
    formats: tuple[str, ...] = ("svg",),
    max_cols: int = 3,
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None = None,
    include_curve: Callable[..., bool] | None = None,
    report: bool = True,
    verbose: bool = False,
    dry_run: bool = False,
    n_jobs: int = 1,
    pdf_report: PdfReportArg = None,
    clean: bool | str = False,
) -> list[Path]:
    """Compare several named flight points as subplots on shared polars.

    Unlike ``batch_plot`` (one figure per flight point), this builds **one figure
    per polar / fixed-sweep / Y** with one subplot panel per entry in
    ``compare_flight_points``.

    Parameters
    ----------
    compare_flight_points :
        Mapping ``{name: {Mach: ..., Altitude_m: ..., ...}}``. Subplot titles
        use *name* plus the flight-point values. Keys that are also sweep
        variables (via ``flight_point_dict`` exclusion) are not required.
    max_cols :
        Maximum subplot columns per row (1–3, default 3).
    flight_point_dict :
        Optional metadata (labels / units / template keys). Sweep keys listed
        here are excluded automatically, same as ``batch_plot``.
    clean :
        Wipe ``output_base`` before rendering — same argument and same guards
        as :func:`batch_plot`. There is no ``fold`` here: a compare figure is
        already several flight points on one sheet.

    Output layout (folder named from the joined ``compare_flight_points`` keys,
    e.g. ``design`` / ``off_design``)::

        output_base/ALPHA_POLAR/design_off_design/BETA_2/CN_vs_alpha.svg
        output_base/BETA_POLAR/design_off_design/ALPHA_3/CN_vs_beta.svg
    """
    if not y_axis_dict:
        raise ValueError("y_axis_dict must contain at least one entry.")
    if max_cols < 1 or max_cols > 3:
        raise ValueError("max_cols must be between 1 and 3.")

    resolved_sweep_dict = _coalesce_sweep_dict(sweep_dict, x_axis_dict)
    if not resolved_sweep_dict:
        raise ValueError("Either sweep_dict or x_axis_dict must be provided.")

    completed_sweeps = _prepare_sweep_dict(configuration_dict, resolved_sweep_dict)
    completed_flight_points = _prepare_flight_point_dict(
        configuration_dict,
        flight_point_dict,
        list(resolved_sweep_dict.keys()),
    )
    if not completed_flight_points and flight_point_dict is None:
        # Infer keys from the first compare entry (minus sweep keys).
        first = next(iter(compare_flight_points.values()))
        inferred = {
            key: {"values": [], "label": key, "save_name": key.upper()}
            for key in first
            if key not in completed_sweeps
        }
        completed_flight_points = _prepare_flight_point_dict(
            configuration_dict,
            inferred,
            list(resolved_sweep_dict.keys()),
        )

    normalized_compare = _normalize_compare_flight_points(
        compare_flight_points,
        list(completed_flight_points.keys()),
    )

    jobs = _enumerate_compare_jobs(
        configuration_dict=configuration_dict,
        y_axis_dict=y_axis_dict,
        completed_sweeps=completed_sweeps,
        completed_flight_points=completed_flight_points,
        compare_flight_points=normalized_compare,
        output_base=output_base,
        max_cols=max_cols,
        include_curve=include_curve,
    )

    if verbose:
        _print_compare_plan(
            configuration_dict=configuration_dict,
            y_axis_dict=y_axis_dict,
            completed_sweeps=completed_sweeps,
            completed_flight_points=completed_flight_points,
            normalized_compare=normalized_compare,
            jobs=jobs,
            output_base=output_base,
            formats=formats,
            style_profile=style_profile,
            max_cols=max_cols,
            n_jobs=n_jobs,
            dry_run=dry_run,
            include_curve=include_curve,
            on_before_save=on_before_save,
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
            msg = (
                f"Dry run complete: {len(jobs)} figure(s) → "
                f"{len(planned)} file(s) (nothing written)."
            )
            if _RICH and _console is not None:
                _console.print(f"[yellow]{msg}[/yellow]")
            else:
                print(msg)
        return planned

    spec = _resolve_pdf_spec(pdf_report, style_profile=style_profile, title=_study_title(jobs))
    written_paths = _run_compare_jobs(
        jobs,
        style_profile=style_profile,
        formats=formats,
        on_before_save=on_before_save,
        n_jobs=n_jobs,
        verbose=verbose,
        pdf_spec=spec,
    )

    if spec is not None and jobs:
        written_paths.append(Path(spec.path))

    if report and written_paths:
        _print_compare_file_report(jobs, formats)

    return written_paths
