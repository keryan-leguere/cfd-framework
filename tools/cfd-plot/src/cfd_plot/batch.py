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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .mpl_template import (
    make_legend,
    plot_line,
    save_figure,
    set_suptitle,
    set_title,
    use_style,
)

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

_CONFIG_METADATA_KEYS = frozenset({"name", "label", "dir", "CDG", "df"})


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


def _extract_plot_style_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in config.items() if key not in _CONFIG_METADATA_KEYS}


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

    n_files = len(jobs) * len(formats)
    jobs_by_polar = Counter(job.polar_prefix for job in jobs)
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
    overview_lines.extend(
        [
            f"Output base  : {output_base}",
            f"Formats      : {', '.join(formats)}",
            f"Style        : {style_profile}",
            f"Mode         : {'dry-run (no files written)' if dry_run else 'write'}",
            f"Hooks        : include_curve={'yes' if include_curve else 'no'}, "
            f"on_before_save={'yes' if on_before_save else 'no'}",
            f"Parallel     : {parallel_note}",
            f"Figures      : {len(jobs)}  →  {n_files} file(s)",
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
            for polar, count in sorted(jobs_by_polar.items()):
                polar_table.add_row(polar, str(count))
            _console.print(polar_table)
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
            print(f"  {polar}: {count}")


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
) -> list[Path]:
    """Render and export a single batch plot job (safe for process workers)."""
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
    plt.close(fig)
    return written


def _run_jobs(
    jobs: list[_BatchPlotJob],
    *,
    style_profile: str,
    formats: tuple[str, ...],
    on_before_save: Callable[[plt.Figure, plt.Axes, BatchPlotContext], None] | None,
    n_jobs: int,
    verbose: bool,
) -> list[Path]:
    """Execute plot jobs sequentially or via a process pool."""
    workers = _resolve_n_jobs(n_jobs)
    use_parallel = workers > 1

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

    def _job_label(job: _BatchPlotJob) -> str:
        point = _cli_text(job.flight_point_label)
        if job.case_label:
            point = f"{point}, {_cli_text(job.case_label)}"
        return f"{job.polar_prefix} · {point} · {job.y_key} vs {job.sweep_key}"

    if not use_parallel:
        use_style(style_profile)
        if show_progress and _RICH and Progress is not None and _console is not None:
            with Progress(*_progress_columns(), console=_console, transient=False) as progress:
                task_id = progress.add_task(task_desc, total=total)
                for job in jobs:
                    progress.update(task_id, description=_job_label(job))
                    written_paths.extend(
                        _render_one_job(job, style_profile, formats, on_before_save)
                    )
                    progress.advance(task_id)
            return written_paths

        for index, job in enumerate(jobs, start=1):
            if verbose:
                print(f"[batch] [{index}/{total}] writing {_job_label(job)}")
            written_paths.extend(
                _render_one_job(job, style_profile, formats, on_before_save)
            )
        return written_paths

    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as executor:
        futures = [
            executor.submit(_render_one_job, job, style_profile, formats, on_before_save)
            for job in jobs
        ]
        if show_progress and _RICH and Progress is not None and _console is not None:
            with Progress(*_progress_columns(), console=_console, transient=False) as progress:
                task_id = progress.add_task(task_desc, total=total)
                for job, future in zip(jobs, futures, strict=True):
                    progress.update(task_id, description=_job_label(job))
                    written_paths.extend(future.result())
                    progress.advance(task_id)
            return written_paths

        for index, (job, future) in enumerate(zip(jobs, futures, strict=True), start=1):
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
        )

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

    written_paths = _run_jobs(
        jobs,
        style_profile=style_profile,
        formats=formats,
        on_before_save=on_before_save,
        n_jobs=n_jobs,
        verbose=verbose,
    )

    if report and written_paths:
        _print_batch_file_report(jobs, formats)

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
) -> list[Path]:
    """Render a multi-panel compare figure (safe for process workers)."""
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
    layout_engine = fig.get_layout_engine()
    if layout_engine is not None:
        # h_pad is accepted by the tight/constrained engines actually in use;
        # the base LayoutEngine.set signature does not declare it.
        layout_engine.set(h_pad=_COMPARE_LAYOUT_H_PAD)  # type: ignore[call-arg]

    written = save_figure(fig, job.output_path, formats=formats)
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
) -> list[Path]:
    """Execute compare jobs sequentially or via a process pool."""
    workers = _resolve_n_jobs(n_jobs)
    use_parallel = workers > 1

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
        if show_progress and _RICH and Progress is not None and _console is not None:
            with Progress(*_progress_columns(), console=_console, transient=False) as progress:
                task_id = progress.add_task(task_desc, total=total)
                for job in jobs:
                    progress.update(task_id, description=_job_label(job))
                    written_paths.extend(
                        _render_one_compare_job(job, style_profile, formats, on_before_save)
                    )
                    progress.advance(task_id)
            return written_paths

        for index, job in enumerate(jobs, start=1):
            if verbose:
                print(f"[batch] [{index}/{total}] writing {_job_label(job)}")
            written_paths.extend(
                _render_one_compare_job(job, style_profile, formats, on_before_save)
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
                for job, future in zip(jobs, futures, strict=True):
                    progress.update(task_id, description=_job_label(job))
                    written_paths.extend(future.result())
                    progress.advance(task_id)
            return written_paths

        for index, (job, future) in enumerate(zip(jobs, futures, strict=True), start=1):
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

    written_paths = _run_compare_jobs(
        jobs,
        style_profile=style_profile,
        formats=formats,
        on_before_save=on_before_save,
        n_jobs=n_jobs,
        verbose=verbose,
    )

    if report and written_paths:
        _print_compare_file_report(jobs, formats)

    return written_paths
