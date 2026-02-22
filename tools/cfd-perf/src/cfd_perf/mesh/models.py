"""Mesh-related data models."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MeshStats:
    """Canonical mesh statistics extracted by an adapter."""

    num_cells: int
    num_faces: int
    cell_type_distribution: dict[str, float] | None = None
    estimated_mem_per_cell_bytes: float | None = None

    def __post_init__(self) -> None:
        if self.num_cells <= 0:
            raise ValueError(f"num_cells must be positive, got {self.num_cells}")
        if self.num_faces <= 0:
            raise ValueError(f"num_faces must be positive, got {self.num_faces}")


@dataclass(frozen=True)
class MeshStatsRaw:
    """Raw mesh data returned by adapters before normalization."""

    num_cells: int
    num_faces: int
    cell_type_distribution: dict[str, float] = field(default_factory=dict)
