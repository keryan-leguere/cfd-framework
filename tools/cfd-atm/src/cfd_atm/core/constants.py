"""Physical constants and the ISA layer table (all SI units).

The core of ``cfd-atm`` works exclusively in SI: metres, m/s, pascals, kelvin.
Aeronautical display units (feet, knots) live in :mod:`cfd_atm.report.units`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# --- Fundamental constants -------------------------------------------------

G0: float = 9.80665
"""Standard gravitational acceleration (m/s²)."""

R_AIR: float = 287.05287
"""Specific gas constant of dry air (J/(kg·K))."""

GAMMA: float = 1.4
"""Ratio of specific heats for air (-)."""

EARTH_RADIUS: float = 6356766.0
"""Nominal Earth radius used for the geopotential altitude (m)."""

# --- Sea-level ISA reference -----------------------------------------------

T0: float = 288.15
"""Sea-level standard temperature (K)."""

P0: float = 101325.0
"""Sea-level standard pressure (Pa)."""

RHO0: float = P0 / (R_AIR * T0)
"""Sea-level standard density (kg/m³) — derived, ≈ 1.225."""

A0: float = math.sqrt(GAMMA * R_AIR * T0)
"""Sea-level standard speed of sound (m/s) — derived, ≈ 340.294."""

# --- Sutherland viscosity law (air) ----------------------------------------

MU0: float = 1.716e-5
"""Sutherland reference viscosity (Pa·s)."""

SUTHERLAND_T_REF: float = 273.15
"""Sutherland reference temperature (K)."""

SUTHERLAND_S: float = 110.4
"""Sutherland constant for air (K)."""


@dataclass(frozen=True)
class IsaLayer:
    """One ISA layer, indexed on geopotential altitude.

    ``p_base`` is filled in by :func:`_build_layers` by chaining the hydrostatic
    relation upward from sea level, so the table below only carries the
    independent quantities (base altitude, base temperature, lapse rate).
    """

    h_base: float  # geopotential altitude of the layer base (m)
    t_base: float  # temperature at the layer base (K)
    lapse: float  # temperature gradient dT/dH (K/m); 0 for isothermal layers
    p_base: float  # pressure at the layer base (Pa)


# (h_base [m], t_base [K], lapse [K/m]); p_base is computed below.
_LAYER_SEED: tuple[tuple[float, float, float], ...] = (
    (0.0, 288.15, -6.5e-3),
    (11000.0, 216.65, 0.0),
    (20000.0, 216.65, 1.0e-3),
    (32000.0, 228.65, 2.8e-3),
    (47000.0, 270.65, 0.0),
    (51000.0, 270.65, -2.8e-3),
    (71000.0, 214.65, -2.0e-3),
)

H_TOP: float = 84852.0
"""Top of the modelled atmosphere, in geopotential metres."""


def _pressure_step(p_base: float, t_base: float, lapse: float, h_base: float, h_top: float) -> float:
    """Pressure at ``h_top`` given the base of a single layer."""
    if lapse == 0.0:
        return float(p_base * math.exp(-G0 * (h_top - h_base) / (R_AIR * t_base)))
    t_top = t_base + lapse * (h_top - h_base)
    return float(p_base * (t_top / t_base) ** (-G0 / (lapse * R_AIR)))


def _build_layers() -> tuple[IsaLayer, ...]:
    """Chain the base pressures upward from sea level to build the full table."""
    layers: list[IsaLayer] = []
    p_base = P0
    for i, (h_base, t_base, lapse) in enumerate(_LAYER_SEED):
        layers.append(IsaLayer(h_base=h_base, t_base=t_base, lapse=lapse, p_base=p_base))
        if i + 1 < len(_LAYER_SEED):
            h_next = _LAYER_SEED[i + 1][0]
            p_base = _pressure_step(p_base, t_base, lapse, h_base, h_next)
    return tuple(layers)


ISA_LAYERS: tuple[IsaLayer, ...] = _build_layers()
"""The seven ISA layers with their base pressures resolved."""
