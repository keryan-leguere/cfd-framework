"""Scaling model parameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BETA_MIN = 0.01
BETA_MAX = 0.5
BETA_DEFAULT = 0.25


@dataclass(frozen=True)
class ModelParameters:
    """Parameters for the strong-scaling performance model."""

    beta: float
    beta_source: Literal["fixed", "fitted"]

    def __post_init__(self) -> None:
        if not (BETA_MIN <= self.beta <= BETA_MAX):
            raise ValueError(f"beta must be in [{BETA_MIN}, {BETA_MAX}], got {self.beta}")
