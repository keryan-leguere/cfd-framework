"""Mesh description and memory-footprint estimation."""

from __future__ import annotations

from dataclasses import dataclass

from cfd_perf.data.pilot import PilotSeries

GB_TO_BYTES = 1 << 30


@dataclass(frozen=True)
class Mesh:
    """Canonical mesh statistics.

    ``mem_per_cell_bytes`` is what turns cell count into a RAM figure.  It is
    either measured (inferred from a pilot run) or supplied by the user; it is
    never guessed, because a wrong guess silently produces a confident and
    wrong node count.
    """

    num_cells: int
    num_faces: int | None = None
    cell_type_distribution: dict[str, float] | None = None
    mem_per_cell_bytes: float | None = None
    mem_source: str = "unknown"

    def __post_init__(self) -> None:
        if self.num_cells <= 0:
            raise ValueError(f"num_cells must be positive, got {self.num_cells}")
        if self.num_faces is not None and self.num_faces <= 0:
            raise ValueError(f"num_faces must be positive when given, got {self.num_faces}")
        if self.mem_per_cell_bytes is not None and self.mem_per_cell_bytes <= 0:
            raise ValueError(
                f"mem_per_cell_bytes must be positive when given, got {self.mem_per_cell_bytes}"
            )

    @property
    def total_ram_gb(self) -> float | None:
        """Estimated total RAM across all ranks, or None if unknown."""
        if self.mem_per_cell_bytes is None:
            return None
        return self.mem_per_cell_bytes * self.num_cells / GB_TO_BYTES

    def ram_per_core_gb(self, nc: int) -> float | None:
        """Estimated per-core RAM at *nc* cores, or None if unknown.

        Assumes total footprint is fixed and splits evenly.  Halo duplication
        makes this mildly optimistic at very high core counts; the pilot's
        measured peak RAM is used in preference wherever it is available.
        """
        total = self.total_ram_gb
        if total is None:
            return None
        if nc <= 0:
            raise ValueError(f"nc must be positive, got {nc}")
        return total / nc

    def cells_per_core(self, nc: int) -> float:
        if nc <= 0:
            raise ValueError(f"nc must be positive, got {nc}")
        return self.num_cells / nc


def mesh_from_data(
    *,
    num_cells: int,
    num_faces: int | None = None,
    cell_type_distribution: dict[str, float] | None = None,
    mem_per_cell_bytes: float | None = None,
    pilot: PilotSeries | None = None,
) -> Mesh:
    """Build a Mesh, resolving memory-per-cell by a deterministic hierarchy.

    1. an explicit ``mem_per_cell_bytes`` from the user;
    2. otherwise inferred from the pilot's measured peak RAM;
    3. otherwise left unknown, and memory constraints are skipped.
    """
    # Validate before the pilot-inference division below, so a bad cell count
    # surfaces as a clear ValueError rather than a ZeroDivisionError.
    if num_cells <= 0:
        raise ValueError(f"num_cells must be positive, got {num_cells}")

    resolved = mem_per_cell_bytes
    source = "unknown"

    if resolved is not None:
        source = "user"
    elif pilot is not None and pilot.peak_ram_total_gb is not None:
        resolved = pilot.peak_ram_total_gb * GB_TO_BYTES / num_cells
        source = "measured (pilot)"

    return Mesh(
        num_cells=num_cells,
        num_faces=num_faces,
        cell_type_distribution=cell_type_distribution or None,
        mem_per_cell_bytes=resolved,
        mem_source=source,
    )
