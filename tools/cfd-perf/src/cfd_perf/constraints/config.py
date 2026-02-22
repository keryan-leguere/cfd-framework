"""Hard constraint configuration."""

from __future__ import annotations

from dataclasses import dataclass

MIN_CELLS_PER_CORE_DEFAULT = 100_000
MIN_RAM_PER_CORE_GB_DEFAULT = 2.0


@dataclass(frozen=True)
class HardConstraints:
    """User-overridable hard resource constraints."""

    min_cells_per_core: int = MIN_CELLS_PER_CORE_DEFAULT
    min_ram_per_core_gb: float = MIN_RAM_PER_CORE_GB_DEFAULT

    def __post_init__(self) -> None:
        if self.min_cells_per_core <= 0:
            raise ValueError(f"min_cells_per_core must be positive, got {self.min_cells_per_core}")
        if self.min_ram_per_core_gb <= 0:
            raise ValueError(f"min_ram_per_core_gb must be positive, got {self.min_ram_per_core_gb}")
