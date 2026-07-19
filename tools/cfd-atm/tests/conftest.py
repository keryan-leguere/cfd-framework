"""Shared fixtures: canonical ISA reference points (from published tables)."""

from __future__ import annotations

import pytest

# (geopotential altitude m, T K, p Pa, rho kg/m³) — standard ISA tabulated values.
ISA_REFERENCE = [
    (0.0, 288.15, 101325.0, 1.22500),
    (5000.0, 255.65, 54019.9, 0.73643),
    (11000.0, 216.65, 22632.0, 0.36392),
    (20000.0, 216.65, 5474.9, 0.08803),
    (32000.0, 228.65, 868.0, 0.01322),
]


@pytest.fixture
def isa_reference() -> list[tuple[float, float, float, float]]:
    return ISA_REFERENCE
