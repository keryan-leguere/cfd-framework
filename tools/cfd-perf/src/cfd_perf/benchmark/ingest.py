"""Ingest pilot benchmark data from JSON files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cfd_perf.benchmark.models import PilotPoint, PilotSeries


def load_pilot(path: Path) -> PilotSeries:
    """Load pilot metrics from a JSON file.

    Expected schema::

        {
            "n_iterations": 5000,
            "points": [
                {"cores": 64, "time_per_iter_s": 1.2, "peak_ram_total_gb": 48.0},
                {"cores": 128, "time_per_iter_s": 0.72, "peak_ram_total_gb": 48.0}
            ]
        }

    Points are sorted by ascending core count; the first becomes the baseline.
    """
    data: dict[str, Any] = json.loads(path.read_text())

    n_iterations: int = int(data["n_iterations"])
    raw_points: list[dict[str, Any]] = data["points"]

    if not raw_points:
        raise ValueError("pilot JSON must contain at least one point")

    points = sorted(
        [
            PilotPoint(
                cores=int(p["cores"]),
                time_per_iter_s=float(p["time_per_iter_s"]),
                peak_ram_total_gb=float(p["peak_ram_total_gb"]),
            )
            for p in raw_points
        ],
        key=lambda p: p.cores,
    )

    return PilotSeries(points=tuple(points), n_iterations=n_iterations)
