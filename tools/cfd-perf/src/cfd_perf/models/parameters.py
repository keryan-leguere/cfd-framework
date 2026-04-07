"""Scaling model parameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

BETA_MIN = 0.01
BETA_MAX = 0.5
BETA_DEFAULT = 0.25


@dataclass(frozen=True)
class ModelParameters:
    """Parameters for the strong-scaling performance model.

    Supports two model kinds:

    - ``"beta"``: classical single-parameter model
      ``T(Nc) = T0 * [Nc0/Nc + beta*(1 - Nc0/Nc)]``
    - ``"empirical"``: quadratic fit in log-space
      ``T(Nc) = a*ln(Nc)^2 + b*ln(Nc) + c``
      which can capture the communication-dominated uptick at high core counts.
    """

    beta: float
    beta_source: Literal["fixed", "fitted"]
    model_kind: Literal["beta", "empirical"] = "beta"
    empirical_coeffs: tuple[float, float, float] | None = None
    empirical_nc_range: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        if not (BETA_MIN <= self.beta <= BETA_MAX):
            raise ValueError(f"beta must be in [{BETA_MIN}, {BETA_MAX}], got {self.beta}")
        if self.model_kind == "empirical" and self.empirical_coeffs is None:
            raise ValueError("empirical_coeffs required when model_kind='empirical'")
