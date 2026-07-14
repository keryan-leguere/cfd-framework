#!/usr/bin/env python3
"""End-to-end driver for dictionary-driven batch plotting.

Loads three post-processed CSV sources, builds the configuration dictionaries,
and generates SVG comparison curves for every flight point and sweep polar.

Usage (from ``scripts/post/plot/``)::

    PYTHONPATH=. python tests/E2E_MULTIPLE_PLOTTING/run_batch_plot.py
    PYTHONPATH=. python tests/E2E_MULTIPLE_PLOTTING/run_batch_plot.py --output-base /tmp/batch_out
    PYTHONPATH=. python tests/E2E_MULTIPLE_PLOTTING/run_batch_plot.py --dry-run --verbose
    PYTHONPATH=. python tests/E2E_MULTIPLE_PLOTTING/run_batch_plot.py --n-jobs -1
    PYTHONPATH=. python tests/E2E_MULTIPLE_PLOTTING/run_batch_plot.py --demo-hooks

Regenerate CSV fixtures (162 rows per source) with::

    python3 tests/E2E_MULTIPLE_PLOTTING/generate_fixture_data.py
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from plotting import batch_compare_flight_points, batch_plot, discover_flight_point_values

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
    """Reusable flight-point template (alpha/beta included on purpose).

    Sweep variables that also appear in ``sweep_dict`` are dropped automatically
    inside ``batch_plot``, so this dict can be copied across projects without
    matching the sweep choice by hand.
    """
    keys = ["Mach", "Altitude_m", "alpha", "beta", "DL", "DM", "DN"]
    labels = {
        "Mach": "M",
        "Altitude_m": "Z",
        "alpha": r"$\alpha$",
        "beta": r"$\beta$",
        "DL": r"$\delta_L$",
        "DM": r"$\delta_M$",
        "DN": r"$\delta_N$",
    }
    save_names = {
        "Mach": "M",
        "Altitude_m": "Z",
        "alpha": "ALPHA",
        "beta": "BETA",
        "DL": "DL",
        "DM": "DM",
        "DN": "DN",
    }
    units = {
        "Mach": "-",
        "Altitude_m": "m",
        "alpha": "°",
        "beta": "°",
        "DL": "°",
        "DM": "°",
        "DN": "°",
    }
    discovered = discover_flight_point_values(configuration_dict, keys)
    return {
        key: {
            "values": discovered[key],
            "label": labels[key],
            "save_name": save_names[key],
            "unit": units[key],
        }
        for key in keys
    }


def include_curve(source_key, flight_point, x_key, y_key, fixed_sweeps):
    """Demo hook: omit the EXP reference series from CA polars."""
    if y_key == "CA" and source_key == "EXP":
        return False
    return True


def on_before_save(fig, ax, context):
    """Demo hook: global zero line, plus a few targeted edits.

    Branch on ``context`` to apply changes to all figures, one Y, one sweep,
    one flight point, or any combination (see README § Flexibility hooks).
    """
    fp = context.flight_point
    fixed = context.fixed_sweeps

    # All figures
    ax.axhline(0.0, color="0.6", lw=0.6, zorder=0)

    # One Y variable
    if context.y_key == "CN":
        ax.set_ylim(bottom=0.0)

    # One sweep / polar
    if context.sweep_key == "beta":
        ax.grid(True, which="major", alpha=0.25)

    # One flight point (any Y / sweep at that condition)
    if fp.get("Mach") == 0.8 and fp.get("Altitude_m") == 8000.0:
        ax.text(
            0.02,
            0.98,
            "design pt",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=7,
            color="0.4",
        )

    # Combine: CN vs alpha at M=0.7, Z=5000, beta fixed to 2
    if (
        context.y_key == "CN"
        and context.sweep_key == "alpha"
        and fp.get("Mach") == 0.7
        and fp.get("Altitude_m") == 5000.0
        and fixed.get("beta") == 2.0
    ):
        ax.axvline(4.0, color="C3", ls="--", lw=0.8)


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
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-figure progress.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List planned output paths without writing files.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Disable the Rich/plain file report after export.",
    )
    parser.add_argument(
        "--n-jobs",
        type=int,
        default=1,
        help="Parallel workers (1=sequential, -1=all CPUs).",
    )
    parser.add_argument(
        "--demo-hooks",
        action="store_true",
        help="Enable include_curve and on_before_save demo hooks.",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Compare two named flight points as subplots (batch_compare_flight_points).",
    )
    args = parser.parse_args()

    configuration_dict = _load_configuration_dict(args.data_dir)
    y_axis_dict, sweep_dict = _build_axis_dicts()
    flight_point_dict = _build_flight_point_dict(configuration_dict)

    common = dict(
        configuration_dict=configuration_dict,
        y_axis_dict=y_axis_dict,
        sweep_dict=sweep_dict,
        flight_point_dict=flight_point_dict,
        output_base=args.output_base,
        style_profile="paper",
        formats=("svg",),
        report=not args.quiet,
        verbose=args.verbose,
        dry_run=args.dry_run,
        n_jobs=args.n_jobs,
        include_curve=include_curve if args.demo_hooks else None,
        on_before_save=on_before_save if args.demo_hooks else None,
    )

    if args.compare:
        compare_flight_points = {
            "design": {
                "Mach": 0.8,
                "Altitude_m": 8000,
                "DL": 0.0,
                "DM": 0.0,
                "DN": 0.0,
            },
            "off_design": {
                "Mach": 0.7,
                "Altitude_m": 5000,
                "DL": 0.0,
                "DM": 0.0,
                "DN": 0.0,
            },
        }
        written = batch_compare_flight_points(
            compare_flight_points=compare_flight_points,
            max_cols=3,
            **common,
        )
    else:
        written = batch_plot(**common)

    if args.dry_run:
        print(f"Dry run: {len(written)} figure(s) would be written under {args.output_base}")


if __name__ == "__main__":
    main()
