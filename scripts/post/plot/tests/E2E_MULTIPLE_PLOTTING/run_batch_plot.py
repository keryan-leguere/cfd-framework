#!/usr/bin/env python3
"""End-to-end driver for dictionary-driven batch plotting.

Loads three post-processed CSV sources, builds the configuration dictionaries,
and generates SVG comparison curves for every flight point and sweep polar.

Usage (from ``scripts/post/plot/``)::

    PYTHONPATH=. python tests/E2E_MULTIPLE_PLOTTING/run_batch_plot.py
    PYTHONPATH=. python tests/E2E_MULTIPLE_PLOTTING/run_batch_plot.py --output-base /tmp/batch_out

Regenerate CSV fixtures (162 rows per source) with::

    python3 tests/E2E_MULTIPLE_PLOTTING/generate_fixture_data.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from plotting import batch_plot, discover_flight_point_values

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / "output"


def _load_configuration_dict(data_dir: Path) -> dict:
    """Load the three source CSV files into a configuration dictionary."""
    sources = {
        "KW": {
            "name": "KW",
            "label": r"$k$-$\omega$",
            "dir": str(data_dir),
            "CDG": [0, 0, 0],
            "color": "C0",
            "marker": "o",
        },
        "SA": {
            "name": "SA",
            "label": "SA",
            "dir": str(data_dir),
            "CDG": [0, 0, 0],
            "color": "C1",
            "marker": "s",
        },
        "EXP": {
            "name": "REF",
            "label": "Ref.",
            "dir": str(data_dir),
            "CDG": [0, 0, 0],
            "color": "C2",
            "marker": "^",
            "linestyle": "--",
        },
    }

    file_map = {"KW": "kw.csv", "SA": "sa.csv", "EXP": "exp.csv"}
    configuration_dict = {}
    for key, meta in sources.items():
        entry = dict(meta)
        entry["df"] = pd.read_csv(data_dir / file_map[key])
        configuration_dict[key] = entry
    return configuration_dict


def _build_axis_dicts() -> tuple[dict, dict]:
    y_axis_dict = {
        "CN": {
            "col_name": "CN",
            "literal_name": "",
            "symbol": r"$C_N$",
            "unit": "-",
            "y_save_name": "CN",
        },
        "CA": {
            "col_name": "CA",
            "literal_name": "Axial force coefficient",
            "symbol": r"$C_A$",
            "unit": "-",
            "y_save_name": "CA",
        },
    }
    sweep_dict = {
        "alpha": {
            "col_name": "alpha",
            "literal_name": "Angle of attack",
            "symbol": r"$\alpha$",
            "unit": "°",
            "x_save_name": "alpha",
            "polar_prefix": "ALPHA_POLAR",
            "label": r"$\alpha$",
            "save_name": "ALPHA",
        },
        "beta": {
            "col_name": "beta",
            "literal_name": "Sideslip angle",
            "symbol": r"$\beta$",
            "unit": "°",
            "x_save_name": "beta",
            "polar_prefix": "BETA_POLAR",
            "label": r"$\beta$",
            "save_name": "BETA",
        },
    }
    return y_axis_dict, sweep_dict


def _build_flight_point_dict(configuration_dict: dict) -> dict:
    """Fixed flight-point parameters (sweep variables are excluded automatically)."""
    keys = ["Mach", "Altitude_m", "DL", "DM", "DN"]
    labels = {
        "Mach": "M",
        "Altitude_m": "Z",
        "DL": r"$\delta_L$",
        "DM": r"$\delta_M$",
        "DN": r"$\delta_N$",
    }
    save_names = {
        "Mach": "M",
        "Altitude_m": "Z",
        "DL": "DL",
        "DM": "DM",
        "DN": "DN",
    }
    discovered = discover_flight_point_values(configuration_dict, keys)
    return {
        key: {
            "values": discovered[key],
            "label": labels[key],
            "save_name": save_names[key],
        }
        for key in keys
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run batch plotting E2E example.")
    parser.add_argument(
        "--output-base",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Base directory for generated SVG figures.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=HERE,
        help="Directory containing kw.csv, sa.csv, and exp.csv.",
    )
    args = parser.parse_args()

    configuration_dict = _load_configuration_dict(args.data_dir)
    y_axis_dict, sweep_dict = _build_axis_dicts()
    flight_point_dict = _build_flight_point_dict(configuration_dict)

    written = batch_plot(
        configuration_dict=configuration_dict,
        y_axis_dict=y_axis_dict,
        sweep_dict=sweep_dict,
        flight_point_dict=flight_point_dict,
        output_base=args.output_base,
        style_profile="paper",
        formats=("svg",),
    )

    print(f"Generated {len(written)} figure(s) under {args.output_base}:")
    for path in written:
        print(f"  {path}")


if __name__ == "__main__":
    main()
