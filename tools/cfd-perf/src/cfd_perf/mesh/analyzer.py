"""Mesh analysis: convert raw mesh data to canonical MeshStats."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Union

from cfd_perf.benchmark.models import PilotPoint
from cfd_perf.mesh.adapters import MeshAdapter, get_adapter
from cfd_perf.mesh.models import MeshStats, MeshStatsRaw

if TYPE_CHECKING:
    import pandas as pd

GB_TO_BYTES = 1 << 30


def _row_to_raw(row: dict[str, Any]) -> MeshStatsRaw:
    """Build MeshStatsRaw from a single row (dict)."""
    cell_dist = row.get("cell_type_distribution")
    if cell_dist is None:
        cell_dist = {}
    elif not isinstance(cell_dist, dict):
        cell_dist = dict(cell_dist)
    return MeshStatsRaw(
        num_cells=int(row["num_cells"]),
        num_faces=int(row["num_faces"]),
        cell_type_distribution={k: float(v) for k, v in cell_dist.items()},
    )


def mesh_from_data(
    data: Union[dict[str, Any], "pd.DataFrame"],
    *,
    pilot_baseline: PilotPoint | None = None,
    user_mem_per_cell_bytes: float | None = None,
) -> MeshStats:
    """Build MeshStats from in-memory data (dict or one-row DataFrame). No file I/O."""
    if isinstance(data, dict):
        raw = _row_to_raw(data)
    else:
        try:
            import pandas as _pd
        except ImportError:
            raise TypeError("data must be a dict or pandas DataFrame (install pandas)") from None
        if not isinstance(data, _pd.DataFrame):
            raise TypeError("data must be a dict or pandas DataFrame")
        if len(data) == 0:
            raise ValueError("mesh DataFrame must have at least one row")
        row = data.iloc[0].to_dict()
        raw = _row_to_raw(row)

    mem_per_cell = _estimate_mem_per_cell(raw, pilot_baseline, user_mem_per_cell_bytes)
    return MeshStats(
        num_cells=raw.num_cells,
        num_faces=raw.num_faces,
        cell_type_distribution=raw.cell_type_distribution or None,
        estimated_mem_per_cell_bytes=mem_per_cell,
    )


def _estimate_mem_per_cell(
    raw: MeshStatsRaw,
    pilot_baseline: PilotPoint | None,
    user_mem_per_cell_bytes: float | None,
) -> float | None:
    """Deterministic hierarchy for memory-per-cell estimation.

    1. User-supplied value wins.
    2. Infer from pilot baseline: total_ram / num_cells.
    3. None (unknown).
    """
    if user_mem_per_cell_bytes is not None:
        return user_mem_per_cell_bytes
    if pilot_baseline is not None:
        return (pilot_baseline.peak_ram_total_gb * GB_TO_BYTES) / raw.num_cells
    return None


def analyze_mesh(
    path: Path,
    *,
    adapter_name: str | None = None,
    pilot_baseline: PilotPoint | None = None,
    user_mem_per_cell_bytes: float | None = None,
) -> MeshStats:
    """Read mesh via adapter and compute canonical stats."""
    adapter: MeshAdapter = get_adapter(path, adapter_name)
    raw: MeshStatsRaw = adapter.read(path)

    mem_per_cell = _estimate_mem_per_cell(raw, pilot_baseline, user_mem_per_cell_bytes)

    return MeshStats(
        num_cells=raw.num_cells,
        num_faces=raw.num_faces,
        cell_type_distribution=raw.cell_type_distribution or None,
        estimated_mem_per_cell_bytes=mem_per_cell,
    )
