"""Hard constraints that make a core count unusable.

A constraint rejects a configuration outright; it is not a preference.  Each
violation carries a human-readable explanation, because "rejected" without a
reason is the single most frustrating thing a sizing tool can say.
"""

from __future__ import annotations

from dataclasses import dataclass

from cfd_perf.data.machine import Machine
from cfd_perf.data.mesh import Mesh

# Below ~10k cells/core, MPI halo exchange dominates real solver work for
# typical unstructured finite-volume RANS. This is a floor, not a target.
MIN_CELLS_PER_CORE_DEFAULT = 10_000


@dataclass(frozen=True)
class Constraints:
    """User-tunable feasibility limits."""

    min_cells_per_core: int = MIN_CELLS_PER_CORE_DEFAULT
    min_ram_per_core_gb: float | None = None
    max_walltime_hours: float | None = None
    max_core_hours: float | None = None

    def __post_init__(self) -> None:
        if self.min_cells_per_core <= 0:
            raise ValueError(f"min_cells_per_core must be positive, got {self.min_cells_per_core}")
        for name in ("min_ram_per_core_gb", "max_walltime_hours", "max_core_hours"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive when set, got {value}")


@dataclass(frozen=True)
class Violation:
    """A single failed constraint."""

    code: str
    detail: str


def check(
    nc: int,
    *,
    mesh: Mesh,
    machine: Machine,
    constraints: Constraints,
    runtime_hours: float,
    core_hours: float,
) -> list[Violation]:
    """Return every constraint *nc* violates (empty list means feasible)."""
    violations: list[Violation] = []

    cpc = mesh.cells_per_core(nc)
    if cpc < constraints.min_cells_per_core:
        violations.append(
            Violation(
                "cells_per_core",
                f"{cpc:,.0f} cells/core < {constraints.min_cells_per_core:,} minimum",
            )
        )

    if constraints.min_ram_per_core_gb is not None:
        rpc = mesh.ram_per_core_gb(nc)
        if rpc is not None and rpc < constraints.min_ram_per_core_gb:
            violations.append(
                Violation(
                    "ram_per_core",
                    f"{rpc:.2f} GB/core < {constraints.min_ram_per_core_gb:.2f} GB minimum",
                )
            )

    if machine.ram_per_node_gb is not None and mesh.total_ram_gb is not None:
        nodes = machine.nodes_for(nc)
        ram_needed_per_node = mesh.total_ram_gb / nodes
        if ram_needed_per_node > machine.ram_per_node_gb:
            violations.append(
                Violation(
                    "node_ram",
                    f"needs {ram_needed_per_node:.1f} GB/node but nodes have "
                    f"{machine.ram_per_node_gb:.1f} GB",
                )
            )

    if machine.max_nodes is not None and machine.nodes_for(nc) > machine.max_nodes:
        violations.append(
            Violation(
                "max_nodes",
                f"{machine.nodes_for(nc)} nodes > {machine.max_nodes} allowed on "
                f"'{machine.name}'",
            )
        )

    walltime_cap = _min_optional(constraints.max_walltime_hours, machine.max_walltime_hours)
    if walltime_cap is not None and runtime_hours > walltime_cap:
        violations.append(
            Violation(
                "walltime",
                f"{runtime_hours:.1f} h exceeds the {walltime_cap:.1f} h limit",
            )
        )

    if constraints.max_core_hours is not None and core_hours > constraints.max_core_hours:
        violations.append(
            Violation(
                "core_hours",
                f"{core_hours:,.0f} core-h exceeds the {constraints.max_core_hours:,.0f} "
                "core-h budget",
            )
        )

    return violations


def _min_optional(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)
