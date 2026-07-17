"""Description of the target cluster.

Schedulers allocate whole *nodes*, not arbitrary core counts.  A
recommendation of "531 cores" is unusable on a 48-core-per-node machine: the
user has to ask for 12 nodes (576 cores) and gets billed for all of them.
This module exists so the tool answers in the units the user actually
requests resources in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Machine:
    """Target cluster partition."""

    name: str = "generic"
    cores_per_node: int = 1
    ram_per_node_gb: float | None = None
    max_nodes: int | None = None
    max_walltime_hours: float | None = None

    def __post_init__(self) -> None:
        if self.cores_per_node <= 0:
            raise ValueError(f"cores_per_node must be positive, got {self.cores_per_node}")
        if self.ram_per_node_gb is not None and self.ram_per_node_gb <= 0:
            raise ValueError(f"ram_per_node_gb must be positive, got {self.ram_per_node_gb}")
        if self.max_nodes is not None and self.max_nodes <= 0:
            raise ValueError(f"max_nodes must be positive, got {self.max_nodes}")
        if self.max_walltime_hours is not None and self.max_walltime_hours <= 0:
            raise ValueError(
                f"max_walltime_hours must be positive, got {self.max_walltime_hours}"
            )

    @property
    def allocates_whole_nodes(self) -> bool:
        return self.cores_per_node > 1

    @property
    def max_cores(self) -> int | None:
        if self.max_nodes is None:
            return None
        return self.max_nodes * self.cores_per_node

    def nodes_for(self, nc: int) -> int:
        """Nodes the scheduler will reserve for *nc* cores (rounded up)."""
        return math.ceil(nc / self.cores_per_node)

    def is_full_nodes(self, nc: int) -> bool:
        return nc % self.cores_per_node == 0

    def candidate_core_counts(self, nc_min: int, nc_max: int) -> list[int]:
        """Core counts worth evaluating between *nc_min* and *nc_max*.

        On a multi-core-per-node machine only whole-node counts are offered,
        because those are the only ones the user can actually request.  The
        baseline is always included even when it is not a whole node, so the
        pilot's reference point stays visible on the curve.
        """
        if nc_min <= 0 or nc_max < nc_min:
            raise ValueError(f"need 0 < nc_min <= nc_max, got {nc_min}, {nc_max}")

        if not self.allocates_whole_nodes:
            return list(range(nc_min, nc_max + 1))

        step = self.cores_per_node
        first = math.ceil(nc_min / step) * step
        counts = list(range(first, nc_max + 1, step))
        if nc_min not in counts:
            counts.insert(0, nc_min)
        return counts
