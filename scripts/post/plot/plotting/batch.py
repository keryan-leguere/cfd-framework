"""
batch — dictionary-driven batch plotting for multi-source curve comparisons.

Iterates over flight points and sweep-variable combinations, plotting every
source curve on shared axes and exporting SVG figures via the existing helpers.

For each sweep variable a *polar* is generated: y vs. that sweep at every
flight point, with all other sweep variables held fixed (cross-sweep / PDV).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd

from .mpl_template import make_legend, plot_line, save_figure, set_title, use_style

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
    parts = [Path(base), polar_prefix]

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
    """Build a compact title fragment using *symbol* and *unit* only."""
    symbol = spec.get("symbol")
    unit = spec.get("unit")
    if symbol and unit:
        return f"{symbol} ({unit})"
    if symbol:
        return symbol
    return format_axis_label(spec, default_name)


def format_flight_point_title_suffix(
    flight_point: dict[str, float],
    flight_point_keys: Sequence[str],
    flight_point_specs: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Format flight-point metadata for figure titles."""
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
                parts.append(
                    f"{dl_label}={dm_label}={dn_label}={_format_path_value(dl)}"
                )
                skip.update({"DM", "DN"})
                continue
        label = specs.get(key, {}).get("label", key)
        parts.append(f"{label}={_format_path_value(flight_point[key])}")

    return ", ".join(parts)


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
    """Build ``QOI vs. variable (context metadata)`` figure title."""
    y_label = format_axis_title_label(y_spec, y_key)
    x_label = format_axis_title_label(x_spec, x_key)
    context = dict(flight_point)
    context_keys = list(flight_point_keys)
    if fixed_sweeps:
        context.update(fixed_sweeps)
        context_keys.extend(fixed_sweeps.keys())
    combined_specs = dict(flight_point_specs or {})
    if sweep_specs:
        combined_specs.update(sweep_specs)
    flight_suffix = format_flight_point_title_suffix(context, context_keys, combined_specs)
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
) -> list[Path]:
    """Generate polar figures for every flight point and sweep combination.

    For each sweep variable *s* (the x-axis of a polar):

    1. Flight-point keys are taken from ``flight_point_dict`` minus all sweep keys.
    2. Every other sweep variable is held fixed at each of its unique values.
    3. At each (flight point, fixed-sweep combo), y is plotted vs. *s* for every source.

    Output layout::

        output_base/ALPHA_POLAR/M_0.8/Z_8000/BETA_2/CN_vs_alpha.svg
        output_base/BETA_POLAR/M_0.8/Z_8000/ALPHA_3/CN_vs_beta.svg
    """
    if not y_axis_dict:
        raise ValueError("y_axis_dict must contain at least one entry.")

    resolved_sweep_dict = _coalesce_sweep_dict(sweep_dict, x_axis_dict)
    if not resolved_sweep_dict:
        raise ValueError("Either sweep_dict or x_axis_dict must be provided.")

    use_style(style_profile)
    sweep_keys = list(resolved_sweep_dict.keys())
    completed_sweeps = _prepare_sweep_dict(configuration_dict, resolved_sweep_dict)
    completed_flight_points = _prepare_flight_point_dict(
        configuration_dict,
        flight_point_dict,
        sweep_keys,
    )
    flight_point_keys = list(completed_flight_points.keys())
    varying_fp_keys = varying_flight_keys(configuration_dict, flight_point_keys)
    varying_sw_keys = varying_flight_keys(configuration_dict, sweep_keys)

    written_paths: list[Path] = []
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
                filter_context = {**flight_point, **fixed_sweeps}
                filter_keys = flight_point_keys + list(fixed_sweeps.keys())

                for y_key, y_spec in y_axis_dict.items():
                    y_col = y_spec["col_name"]
                    y_save_name = y_spec.get("y_save_name", y_key)

                    fig, ax = plt.subplots()
                    has_curve = False

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

                        style_kwargs = _extract_plot_style_kwargs(config)
                        plot_line(
                            ax,
                            x_values,
                            y_values,
                            label=config.get("label", source_key),
                            **style_kwargs,
                        )
                        has_curve = True

                    if not has_curve:
                        plt.close(fig)
                        continue

                    ax.set_xlabel(format_axis_label(x_spec, x_key))
                    ax.set_ylabel(format_axis_label(y_spec, y_key))
                    make_legend(ax)
                    set_title(
                        ax,
                        format_plot_title(
                            y_spec,
                            y_key,
                            x_spec,
                            x_key,
                            flight_point,
                            flight_point_keys,
                            completed_flight_points,
                            fixed_sweeps,
                            completed_sweeps,
                        ),
                    )

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
                    context = BatchPlotContext(
                        flight_point=flight_point,
                        fixed_sweeps=fixed_sweeps,
                        sweep_key=x_key,
                        y_key=y_key,
                        x_spec=x_spec,
                        y_spec=y_spec,
                        polar_prefix=polar_prefix,
                        output_path=output_path,
                    )
                    if on_before_save is not None:
                        on_before_save(fig, ax, context)

                    written_paths.extend(save_figure(fig, output_path, formats=formats))
                    plt.close(fig)

    return written_paths
