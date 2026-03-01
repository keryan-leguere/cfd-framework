"""Ingest pilot benchmark data from JSON files or in-memory structures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Union

from cfd_perf.benchmark.models import PilotPoint, PilotSeries

if TYPE_CHECKING:
    import pandas as pd


def pilot_from_data(
    data: Union[dict[str, Any], "pd.DataFrame"],
    n_iterations: int,
) -> PilotSeries:
    """Build PilotSeries from in-memory data (dict with \"points\" or DataFrame). No file I/O.

    Dict schema: {"points": [{"cores": N, "time_per_iter_s": T, "peak_ram_total_gb": R}, ...]}.
    DataFrame: columns cores, time_per_iter_s, peak_ram_total_gb (one row per point).
    Points are sorted by cores; the first becomes the baseline.
    """
    try:
        import pandas as _pd
    except ImportError:
        _pd = None  # type: ignore[assignment]

    if isinstance(data, dict):
        raw_points = data.get("points")
        if raw_points is None:
            raise ValueError('dict data must contain key "points" (list of point dicts)')
        if not raw_points:
            raise ValueError("pilot data must contain at least one point")
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

    if _pd is not None and isinstance(data, _pd.DataFrame):
        required = {"cores", "time_per_iter_s", "peak_ram_total_gb"}
        missing = required - set(data.columns)
        if missing:
            raise ValueError(f"pilot DataFrame must have columns {required}, missing: {missing}")
        df = data.sort_values("cores")
        points = [
            PilotPoint(
                cores=int(row["cores"]),
                time_per_iter_s=float(row["time_per_iter_s"]),
                peak_ram_total_gb=float(row["peak_ram_total_gb"]),
            )
            for _, row in df.iterrows()
        ]
        if not points:
            raise ValueError("pilot DataFrame must have at least one row")
        return PilotSeries(points=tuple(points), n_iterations=n_iterations)

    raise TypeError("data must be a dict (with 'points' key) or a pandas DataFrame")


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
    return pilot_from_data(data, n_iterations=int(data["n_iterations"]))
