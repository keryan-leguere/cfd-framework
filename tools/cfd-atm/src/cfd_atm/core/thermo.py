"""Derived thermodynamic quantities: speed of sound, viscosity, ratios.

All functions take temperature (and, where needed, pressure/density) in SI and
return SI. They are shape-preserving over NumPy arrays.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_atm.core.constants import (
    GAMMA,
    MU0,
    P0,
    R_AIR,
    RHO0,
    SUTHERLAND_S,
    SUTHERLAND_T_REF,
    T0,
)


def speed_of_sound(t: ArrayLike) -> NDArray[np.float64]:
    """Speed of sound ``a = sqrt(gamma R T)`` (m/s)."""
    return np.sqrt(GAMMA * R_AIR * np.asarray(t, dtype=np.float64))


def viscosity_sutherland(t: ArrayLike) -> NDArray[np.float64]:
    """Dynamic viscosity (Pa·s) from Sutherland's law."""
    t_arr = np.asarray(t, dtype=np.float64)
    return (
        MU0
        * (t_arr / SUTHERLAND_T_REF) ** 1.5
        * (SUTHERLAND_T_REF + SUTHERLAND_S)
        / (t_arr + SUTHERLAND_S)
    )


def kinematic_viscosity(t: ArrayLike, rho: ArrayLike) -> NDArray[np.float64]:
    """Kinematic viscosity ``nu = mu / rho`` (m²/s)."""
    return viscosity_sutherland(t) / np.asarray(rho, dtype=np.float64)


def theta(t: ArrayLike) -> NDArray[np.float64]:
    """Temperature ratio ``T / T0``."""
    return np.asarray(t, dtype=np.float64) / T0


def delta(p: ArrayLike) -> NDArray[np.float64]:
    """Pressure ratio ``p / p0``."""
    return np.asarray(p, dtype=np.float64) / P0


def sigma(rho: ArrayLike) -> NDArray[np.float64]:
    """Density ratio ``rho / rho0``."""
    return np.asarray(rho, dtype=np.float64) / RHO0


def reynolds_per_metre(rho: ArrayLike, velocity: ArrayLike, t: ArrayLike) -> NDArray[np.float64]:
    """Reynolds number per metre ``rho V / mu``."""
    rho_arr = np.asarray(rho, dtype=np.float64)
    v_arr = np.asarray(velocity, dtype=np.float64)
    return rho_arr * v_arr / viscosity_sutherland(t)
