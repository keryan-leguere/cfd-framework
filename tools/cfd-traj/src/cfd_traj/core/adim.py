"""Non-dimensionalisation: from (Mach, altitude) to what the flow actually sees.

The trajectory logs Mach and altitude separately, but altitude is not a
parameter of the flow: it acts only through the free-stream state it sets. Two
flight points at the same Mach and the same Reynolds number are the same
aerodynamic problem whatever their altitudes. Collapsing altitude into Reynolds
is therefore the first and cheapest reduction of the whole method -- it acts on
the *exponent* of the curse of dimensionality, not on its base.

Everything here is a thin, vectorised wrapper over :mod:`cfd_atm`, which owns
the atmosphere model. The one modelling choice made in this module is that the
``Altitude`` column of the CSV files is a **geometric** altitude (metres above
sea level), converted to geopotential before entering the ISA relations.

SI units throughout: Pa, K, kg/m3, m/s, Pa.s.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from cfd_atm.core import altitudes, isa
from cfd_atm.core.atmosphere import AtmosphereModel
from cfd_atm.core.constants import GAMMA, H_TOP, R_AIR
from cfd_atm.core.thermo import reynolds_per_metre, speed_of_sound, viscosity_sutherland
from numpy.typing import ArrayLike, NDArray

#: Keys produced by :func:`nondimensionalise`, in report order.
FLOW_KEYS: tuple[str, ...] = (
    "p_inf",
    "T_inf",
    "rho_inf",
    "a_inf",
    "mu_inf",
    "V_inf",
    "q_inf",
    "Re_m",
    "Re_ref",
)


@dataclass(frozen=True)
class Reference:
    """Reference dimensions of the configuration."""

    length_m: float
    area_m2: float | None = None

    def __post_init__(self) -> None:
        if not np.isfinite(self.length_m) or self.length_m <= 0:
            raise ValueError(f"reference length must be positive, got {self.length_m}")
        if self.area_m2 is not None and (not np.isfinite(self.area_m2) or self.area_m2 <= 0):
            raise ValueError(f"reference area must be positive, got {self.area_m2}")


@dataclass(frozen=True)
class FlowState:
    """One fully non-dimensionalised flight point."""

    mach: float
    altitude_m: float
    p_inf: float
    t_inf: float
    rho_inf: float
    a_inf: float
    mu_inf: float
    v_inf: float
    q_inf: float
    re_per_metre: float
    re_ref: float


@lru_cache(maxsize=8)
def _model(delta_t_k: float) -> AtmosphereModel:
    """Atmosphere model for a constant ISA offset (cached: the grid build is not free)."""
    if delta_t_k == 0.0:
        return AtmosphereModel.isa()
    return AtmosphereModel.isa_offset(delta_t_k)


def _check_altitude(altitude_m: NDArray[np.float64]) -> None:
    """Reject altitudes outside the range the standard atmosphere is defined on.

    Slightly negative altitudes are accepted on purpose: a launch site below sea
    level, or a numerical undershoot at t = 0, is not a data error.
    """
    finite = altitude_m[np.isfinite(altitude_m)]
    if finite.size == 0:
        return
    if float(np.max(finite)) > H_TOP:
        raise ValueError(
            f"altitude {float(np.max(finite)):.0f} m exceeds the standard atmosphere ceiling "
            f"of {H_TOP:.0f} m"
        )
    if float(np.min(finite)) < -5000.0:
        raise ValueError(f"altitude {float(np.min(finite)):.0f} m is below -5000 m")


def nondimensionalise(
    mach: ArrayLike,
    altitude_m: ArrayLike,
    *,
    reference: Reference,
    delta_t_k: float = 0.0,
) -> dict[str, NDArray[np.float64]]:
    """Free-stream state and non-dimensional numbers for a cloud of flight points.

    ``altitude_m`` is a *geometric* altitude. Returns one array per key of
    :data:`FLOW_KEYS`, broadcast to the shape of the inputs.
    """
    m = np.asarray(mach, dtype=np.float64)
    z = np.asarray(altitude_m, dtype=np.float64)
    _check_altitude(z)
    m, z = np.broadcast_arrays(m, z)

    h = altitudes.geopotential_from_geometric(z)
    model = _model(float(delta_t_k))
    t_inf = model.temperature(h)
    p_inf = model.pressure_geopotential(h)
    rho_inf = p_inf / (R_AIR * t_inf)

    a_inf = speed_of_sound(t_inf)
    mu_inf = viscosity_sutherland(t_inf)
    v_inf = m * a_inf
    # Exact and cheaper than 0.5.rho.V^2, and identical to it by the perfect-gas law.
    q_inf = 0.5 * GAMMA * p_inf * m**2
    re_m = reynolds_per_metre(rho_inf, v_inf, t_inf)

    return {
        "p_inf": np.asarray(p_inf, dtype=np.float64),
        "T_inf": np.asarray(t_inf, dtype=np.float64),
        "rho_inf": np.asarray(rho_inf, dtype=np.float64),
        "a_inf": np.asarray(a_inf, dtype=np.float64),
        "mu_inf": np.asarray(mu_inf, dtype=np.float64),
        "V_inf": np.asarray(v_inf, dtype=np.float64),
        "q_inf": np.asarray(q_inf, dtype=np.float64),
        "Re_m": np.asarray(re_m, dtype=np.float64),
        "Re_ref": np.asarray(re_m * reference.length_m, dtype=np.float64),
    }


def flow_state(
    mach: float, altitude_m: float, *, reference: Reference, delta_t_k: float = 0.0
) -> FlowState:
    """Single flight point, as a readable record."""
    out = nondimensionalise(mach, altitude_m, reference=reference, delta_t_k=delta_t_k)
    return FlowState(
        mach=float(mach),
        altitude_m=float(altitude_m),
        p_inf=float(out["p_inf"]),
        t_inf=float(out["T_inf"]),
        rho_inf=float(out["rho_inf"]),
        a_inf=float(out["a_inf"]),
        mu_inf=float(out["mu_inf"]),
        v_inf=float(out["V_inf"]),
        q_inf=float(out["q_inf"]),
        re_per_metre=float(out["Re_m"]),
        re_ref=float(out["Re_ref"]),
    )


def isa_density(altitude_m: ArrayLike) -> NDArray[np.float64]:
    """ISA density at a geometric altitude, for the synthetic flight model."""
    h = altitudes.geopotential_from_geometric(np.asarray(altitude_m, dtype=np.float64))
    return np.asarray(isa.isa_density(h), dtype=np.float64)


def isa_speed_of_sound(altitude_m: ArrayLike) -> NDArray[np.float64]:
    """ISA speed of sound at a geometric altitude, for the synthetic flight model."""
    h = altitudes.geopotential_from_geometric(np.asarray(altitude_m, dtype=np.float64))
    return np.asarray(speed_of_sound(isa.isa_temperature(h)), dtype=np.float64)
