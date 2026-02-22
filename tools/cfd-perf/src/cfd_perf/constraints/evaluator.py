"""Hard constraint evaluator for candidate core counts."""

from __future__ import annotations

from cfd_perf.constraints.config import HardConstraints
from cfd_perf.mesh.models import MeshStats
from cfd_perf.models.memory import ram_per_core_gb


def check_hard_constraints(
    nc: int,
    mesh: MeshStats,
    constraints: HardConstraints,
) -> list[str]:
    """Return a list of violated constraint names (empty = feasible)."""
    violations: list[str] = []

    if mesh.num_cells / nc < constraints.min_cells_per_core:
        violations.append("cells_per_core")

    rpc = ram_per_core_gb(mesh, nc)
    if rpc is not None and rpc < constraints.min_ram_per_core_gb:
        violations.append("ram_per_core")

    return violations
