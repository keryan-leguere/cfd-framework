"""Conversions between the four equivalent altitudes.

- geometric ``z``      : true height above mean sea level;
- geopotential ``H``   : height corrected for the variation of gravity;
- pressure ``zp``      : ISA geopotential altitude matching a given pressure;
- density ``zrho``     : ISA geopotential altitude matching a given density.

``z`` <-> ``H`` is a pure geometric relation; ``zp`` and ``zrho`` come from
inverting the ISA laws (see :mod:`cfd_atm.core.isa`).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_atm.core.constants import EARTH_RADIUS
from cfd_atm.core.isa import geopotential_from_density, geopotential_from_pressure


def geopotential_from_geometric(z: ArrayLike) -> NDArray[np.float64]:
    """Geopotential altitude ``H`` (m) from geometric altitude ``z`` (m)."""
    z_arr = np.asarray(z, dtype=np.float64)
    return EARTH_RADIUS * z_arr / (EARTH_RADIUS + z_arr)


def geometric_from_geopotential(h: ArrayLike) -> NDArray[np.float64]:
    """Geometric altitude ``z`` (m) from geopotential altitude ``H`` (m)."""
    h_arr = np.asarray(h, dtype=np.float64)
    return EARTH_RADIUS * h_arr / (EARTH_RADIUS - h_arr)


def pressure_altitude(p: ArrayLike) -> NDArray[np.float64]:
    """Pressure altitude ``zp`` (m, geopotential) from pressure ``p`` (Pa)."""
    return geopotential_from_pressure(p)


def density_altitude(rho: ArrayLike) -> NDArray[np.float64]:
    """Density altitude ``zrho`` (m, geopotential) from density ``rho`` (kg/m³)."""
    return geopotential_from_density(rho)
