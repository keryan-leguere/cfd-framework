"""Pilot benchmark data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PilotPoint:
    """A single pilot measurement at a given core count."""

    cores: int
    time_per_iter_s: float
    peak_ram_total_gb: float

    def __post_init__(self) -> None:
        if self.cores <= 0:
            raise ValueError(f"cores must be positive, got {self.cores}")
        if self.time_per_iter_s <= 0:
            raise ValueError(f"time_per_iter_s must be positive, got {self.time_per_iter_s}")
        if self.peak_ram_total_gb <= 0:
            raise ValueError(f"peak_ram_total_gb must be positive, got {self.peak_ram_total_gb}")


@dataclass(frozen=True)
class PilotSeries:
    """Ordered collection of pilot measurements with a designated baseline."""

    points: tuple[PilotPoint, ...]
    n_iterations: int

    def __post_init__(self) -> None:
        if len(self.points) == 0:
            raise ValueError("At least one pilot point is required")
        if self.n_iterations <= 0:
            raise ValueError(f"n_iterations must be positive, got {self.n_iterations}")

    @property
    def baseline(self) -> PilotPoint:
        """The reference point is always the first (lowest core-count) entry."""
        return self.points[0]

    @property
    def baseline_cores(self) -> int:
        return self.baseline.cores

    @property
    def baseline_time_per_iter_s(self) -> float:
        return self.baseline.time_per_iter_s

    @property
    def baseline_peak_ram_total_gb(self) -> float:
        return self.baseline.peak_ram_total_gb
