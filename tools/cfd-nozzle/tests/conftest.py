"""Shared fixtures: published compressible-flow tables for γ = 1.4.

The reference values come from the standard gas-dynamics tables (Anderson,
*Modern Compressible Flow*, appendices A–C). They are the ground truth the
whole package is checked against.
"""

from __future__ import annotations

import pytest

from cfd_nozzle.core.gas import GAS_LIBRARY, GasModel

# (M, T/T0, p/p0, rho/rho0, A/A*)
ISENTROPIC_TABLE = [
    (0.5, 0.952381, 0.843019, 0.885170, 1.339844),
    (1.0, 0.833333, 0.528282, 0.633938, 1.000000),
    (2.0, 0.555556, 0.127805, 0.230048, 1.687500),
    (3.0, 0.357143, 0.027224, 0.076226, 4.234568),
    (5.0, 0.166667, 0.001890, 0.011340, 25.000000),
]

# (M1, M2, p2/p1, rho2/rho1, T2/T1, p02/p01)
NORMAL_SHOCK_TABLE = [
    (1.5, 0.701089, 2.458333, 1.862069, 1.320215, 0.929787),
    (2.0, 0.577350, 4.500000, 2.666667, 1.687500, 0.720874),
    (3.0, 0.475191, 10.333333, 3.857143, 2.679012, 0.328344),
    (5.0, 0.415227, 29.000000, 5.000000, 5.800000, 0.061716),
]

# (M, nu in degrees)
PRANDTL_MEYER_TABLE = [
    (1.0, 0.0),
    (1.5, 11.9052),
    (2.0, 26.3798),
    (3.0, 49.7573),
    (4.0, 65.7848),
]

# (M1, theta in degrees, beta of the weak solution in degrees)
OBLIQUE_SHOCK_TABLE = [
    (2.0, 10.0, 39.3138),
    (2.0, 20.0, 53.4229),
    (3.0, 20.0, 37.7636),
    (5.0, 30.0, 42.3443),
]

# (M1, theta_max in degrees) — the attached-shock detachment limit.
THETA_MAX_TABLE = [
    (1.5, 12.1123),
    (2.0, 22.9735),
    (3.0, 34.0734),
    (5.0, 41.1177),
]


@pytest.fixture
def air() -> GasModel:
    return GAS_LIBRARY["air"]


@pytest.fixture
def lox_rp1() -> GasModel:
    return GAS_LIBRARY["lox_rp1"]
