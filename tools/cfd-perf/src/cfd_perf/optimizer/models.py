"""Optimizer result data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class CandidateConfig:
    """A core-count configuration with all predicted metrics."""

    cores: int
    time_per_iter_s: float
    runtime_hours: float
    speedup: float
    efficiency: float
    efficiency_loss: float
    ram_total_gb: float
    ram_per_core_gb: float


@dataclass(frozen=True)
class RejectedConfig:
    """A core-count configuration that was rejected with reasons."""

    cores: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class OptimizationResult:
    """Full result of the optimization pipeline."""

    mode: Literal["efficiency", "deadline", "min_runtime"]
    optimal: CandidateConfig | None
    accepted: tuple[CandidateConfig, ...]
    rejected: tuple[RejectedConfig, ...]
    metadata: dict[str, Any] = field(default_factory=dict)
    min_runtime_candidate: CandidateConfig | None = None
