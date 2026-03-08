"""CLI entry point for cfd-perf.

Reads a plain-text input file describing mesh, pilot measurements and
optimisation settings, then produces a scaling figure.

Usage::

    cfd-perf <input_file> <output_figure>

Input file format (lines starting with ``#`` are comments)::

    num_cells       = 200000000
    num_faces       = 600000000
    hex             = 0.78
    prism           = 0.14

    n_iterations    = 20000

    mode                = efficiency
    max_efficiency_loss = 0.3
    cores_max           = 512
    stride              = 32

    pilot 32 120 140.0
    pilot 64  65 140.0
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

import cfd_perf
from cfd_perf.constraints.config import HardConstraints
from cfd_perf.io.display import print_fit_result, print_optimization_result

_CELL_TYPES = frozenset({"hex", "prism", "tet", "pyramid", "poly", "wedge"})

_DEFAULTS: dict[str, object] = {
    "mode": "efficiency",
    "max_efficiency_loss": 0.3,
    "cores_max": 512,
    "stride": 32,
    "min_cells_per_core": 100_000,
    "min_ram_per_core_gb": 0.5,
}


def parse_input(filepath: str | Path) -> dict:
    """Parse the plain-text cfd-perf input file into a config dict."""
    config: dict[str, object] = {
        "num_cells": None,
        "num_faces": None,
        "cell_type_distribution": {},
        "n_iterations": None,
        "pilot_points": [],
        **_DEFAULTS,
    }
    cell_dist: dict[str, float] = {}

    with open(filepath) as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("pilot"):
                parts = line.split()
                if len(parts) < 3:
                    print(f"Warning: ignoring malformed pilot line: {line}", file=sys.stderr)
                    continue
                config["pilot_points"].append({  # type: ignore[union-attr]
                    "cores": int(parts[1]),
                    "time_per_iter_s": float(parts[2]),
                    "peak_ram_total_gb": float(parts[3]) if len(parts) > 3 else 0.0,
                })
                continue

            if "=" not in line:
                continue

            key, val = (s.strip() for s in line.split("=", 1))

            if key == "num_cells":
                config["num_cells"] = int(val)
            elif key == "num_faces":
                config["num_faces"] = int(val)
            elif key in _CELL_TYPES:
                cell_dist[key] = float(val)
            elif key == "n_iterations":
                config["n_iterations"] = int(val)
            elif key in ("mode",):
                config[key] = val
            elif key in ("max_efficiency_loss", "min_ram_per_core_gb", "deadline_hours"):
                config[key] = float(val)
            elif key in ("cores_max", "stride", "min_cells_per_core"):
                config[key] = int(val)

    if cell_dist:
        config["cell_type_distribution"] = cell_dist
    return config


def _validate(config: dict) -> None:
    errors: list[str] = []
    if config["num_cells"] is None:
        errors.append("num_cells is required")
    if config["n_iterations"] is None:
        errors.append("n_iterations is required")
    if not config["pilot_points"]:
        errors.append("at least one pilot line is required")
    if errors:
        for e in errors:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]

    if len(args) < 2:
        print("Usage: cfd-perf <input_file> <output_figure>", file=sys.stderr)
        sys.exit(1)

    input_file, output_figure = Path(args[0]), Path(args[1])
    if not input_file.is_file():
        print(f"Error: input file not found: {input_file}", file=sys.stderr)
        sys.exit(1)

    config = parse_input(input_file)
    _validate(config)

    num_faces = config["num_faces"] or int(config["num_cells"]) * 3  # type: ignore[arg-type]
    mesh_data = {
        "num_cells": config["num_cells"],
        "num_faces": num_faces,
        "cell_type_distribution": config["cell_type_distribution"] or {"hex": 1.0},
    }

    pilot_df = pd.DataFrame(config["pilot_points"])
    n_iterations: int = config["n_iterations"]  # type: ignore[assignment]

    pilot = cfd_perf.pilot_from_data(pilot_df, n_iterations=n_iterations)
    mesh = cfd_perf.mesh_from_data(mesh_data, pilot_baseline=pilot.baseline)
    params = cfd_perf.fit_beta(pilot)
    print_fit_result(params, pilot)

    constraints = HardConstraints(
        min_cells_per_core=int(config["min_cells_per_core"]),  # type: ignore[arg-type]
        min_ram_per_core_gb=float(config["min_ram_per_core_gb"]),  # type: ignore[arg-type]
    )

    opt_kwargs: dict[str, object] = {
        "mode": config["mode"],
        "max_efficiency_loss": config["max_efficiency_loss"],
        "cores_max": config["cores_max"],
        "stride": config["stride"],
    }
    if "deadline_hours" in config:
        opt_kwargs["deadline_hours"] = config["deadline_hours"]

    result = cfd_perf.optimize(mesh, pilot, params, constraints=constraints, **opt_kwargs)
    print_optimization_result(result)

    fig_result = cfd_perf.plot_scaling(
        result, pilot=pilot, mesh=mesh, params=params, return_figure=True,
    )
    if fig_result is not None:
        fig, _axes = fig_result
        output_figure.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_figure), dpi=180, bbox_inches="tight")
        plt.close(fig)
        print(f"Figure saved to: {output_figure}")
    else:
        print("Warning: no figure produced (empty result set)", file=sys.stderr)


if __name__ == "__main__":
    main()
