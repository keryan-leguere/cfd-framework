"""Memory prediction model.

Assumes total memory is fixed (scales with cells, not cores).
Per-core memory = total / Nc.
"""

from __future__ import annotations

from cfd_perf.mesh.models import MeshStats

GB_TO_BYTES = 1 << 30


def total_ram_gb(mesh: MeshStats) -> float | None:
    """Predicted total RAM in GB, or None if mem/cell is unknown."""
    if mesh.estimated_mem_per_cell_bytes is None:
        return None
    return mesh.estimated_mem_per_cell_bytes * mesh.num_cells / GB_TO_BYTES


def ram_per_core_gb(mesh: MeshStats, nc: int) -> float | None:
    """Predicted per-core RAM in GB."""
    total = total_ram_gb(mesh)
    if total is None:
        return None
    return total / nc
