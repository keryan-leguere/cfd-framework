"""The atmosphere block: an :class:`AtmosphereModel` maps an altitude to a full
:class:`AtmosphereState` under a chosen temperature model (ISA, ISA±ΔT, custom).

Design (see ``00_DOC/01_MODELE_ATMOSPHERE.md``): the temperature model is a
function of **geopotential** altitude ``H``. Every entry point resolves to one
consistent ``(H, p, T)`` triple:

- geometric / geopotential entry -> pressure from hydrostatic equilibrium of the
  actual temperature profile (closed form for pure ISA). This is what makes the
  pressure at a fixed *geometric* altitude depend on the temperature model, and
  therefore what makes diagram A of the example meaningful.
- pressure-altitude entry -> pressure is fixed by ``zp`` (ISA law), model
  independent. The temperature follows the aeronautical convention: for ISA/ISA±ΔT
  the deviation is referenced to ``zp`` (``T = T_ISA(zp) + ΔT``); for a custom
  physical profile it is read at the geopotential height ``H*`` where the model
  reaches that pressure. See :meth:`AtmosphereModel.state_from_pressure_altitude`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_atm.core import altitudes, isa, thermo
from cfd_atm.core.constants import G0, H_TOP, P0, R_AIR

TemperatureProfile = Callable[[NDArray[np.float64]], NDArray[np.float64]]


class ModelKind(Enum):
    """The three temperature-model families."""

    ISA = "ISA"
    ISA_OFFSET = "ISA_OFFSET"
    CUSTOM = "CUSTOM"


@dataclass(frozen=True)
class AtmosphereState:
    """A fully resolved atmospheric point. All quantities are SI.

    Altitudes: ``z`` geometric, ``h`` geopotential, ``zp`` pressure, ``zrho``
    density (all metres). Air: ``t`` (K), ``p`` (Pa), ``rho`` (kg/m³). Derived:
    ``a`` speed of sound (m/s), ``mu`` dynamic and ``nu`` kinematic viscosity,
    and the ratios ``theta``/``delta``/``sigma``.
    """

    z: float
    h: float
    zp: float
    zrho: float
    t: float
    p: float
    rho: float
    a: float
    mu: float
    nu: float
    theta: float
    delta: float
    sigma: float


def temperature_profile_from_table(
    h_points: ArrayLike, t_points: ArrayLike
) -> TemperatureProfile:
    """Build a custom ``T(H)`` profile by linear interpolation of a table.

    ``h_points`` are geopotential altitudes (m, increasing), ``t_points`` the
    matching temperatures (K). Values outside the table are clamped to its ends.
    """
    hp = np.asarray(h_points, dtype=np.float64)
    tp = np.asarray(t_points, dtype=np.float64)
    if hp.ndim != 1 or hp.shape != tp.shape:
        raise ValueError("h_points et t_points doivent être des vecteurs de même taille.")
    if np.any(np.diff(hp) <= 0):
        raise ValueError("h_points doit être strictement croissant.")

    def profile(h: NDArray[np.float64]) -> NDArray[np.float64]:
        return np.interp(h, hp, tp)

    return profile


class AtmosphereModel:
    """An atmosphere model: a temperature profile plus its pressure law.

    Construct via the factories :meth:`isa`, :meth:`isa_offset`, :meth:`custom`.
    """

    _GRID_POINTS = 8000

    def __init__(self, kind: ModelKind, temperature: TemperatureProfile, *, label: str) -> None:
        self.kind = kind
        self._temperature = temperature
        self.label = label
        # For non-ISA models the pressure law has no closed form, so precompute a
        # cumulative hydrostatic integral once and interpolate on it.
        self._h_grid: NDArray[np.float64] | None = None
        self._p_grid: NDArray[np.float64] | None = None
        if kind is not ModelKind.ISA:
            self._build_pressure_grid()

    # --- factories ---------------------------------------------------------

    @classmethod
    def isa(cls) -> AtmosphereModel:
        """The International Standard Atmosphere."""
        return cls(ModelKind.ISA, isa.isa_temperature, label="ISA")

    @classmethod
    def isa_offset(cls, delta_t: float) -> AtmosphereModel:
        """ISA shifted by a constant temperature offset ``ΔT`` (K)."""
        sign = "+" if delta_t >= 0 else "−"
        label = f"ISA{sign}{abs(delta_t):g}"

        def profile(h: NDArray[np.float64]) -> NDArray[np.float64]:
            return isa.isa_temperature(h) + delta_t

        return cls(ModelKind.ISA_OFFSET, profile, label=label)

    @classmethod
    def custom(cls, temperature: TemperatureProfile, *, label: str = "custom") -> AtmosphereModel:
        """A user-supplied temperature profile ``T(H)`` (geopotential)."""
        return cls(ModelKind.CUSTOM, temperature, label=label)

    # --- temperature & pressure laws --------------------------------------

    def temperature(self, h: ArrayLike) -> NDArray[np.float64]:
        """Temperature (K) at geopotential altitude ``H`` (m)."""
        return self._temperature(np.asarray(h, dtype=np.float64))

    def _build_pressure_grid(self) -> None:
        grid = np.linspace(0.0, H_TOP, self._GRID_POINTS)
        t_grid = self._temperature(grid)
        integrand = G0 / (R_AIR * t_grid)
        cum = np.concatenate(
            [[0.0], np.cumsum(0.5 * (integrand[1:] + integrand[:-1]) * np.diff(grid))]
        )
        self._h_grid = grid
        self._p_grid = P0 * np.exp(-cum)

    def pressure_geopotential(self, h: ArrayLike) -> NDArray[np.float64]:
        """Static pressure (Pa) at geopotential altitude ``H`` (m)."""
        if self.kind is ModelKind.ISA:
            return isa.isa_pressure(h)
        assert self._h_grid is not None and self._p_grid is not None
        return np.interp(np.asarray(h, dtype=np.float64), self._h_grid, self._p_grid)

    def _geopotential_from_pressure(self, p: float) -> float:
        """Invert the model's pressure law: geopotential altitude giving ``p``."""
        if self.kind is ModelKind.ISA:
            return float(isa.geopotential_from_pressure(p))
        assert self._h_grid is not None and self._p_grid is not None
        # p_grid decreases with h; np.interp needs an increasing x, so reverse.
        return float(np.interp(p, self._p_grid[::-1], self._h_grid[::-1]))

    # --- entry points ------------------------------------------------------

    def state_from_geopotential(self, h: float) -> AtmosphereState:
        """Full state at geopotential altitude ``H`` (m)."""
        t = float(self.temperature(h))
        p = float(self.pressure_geopotential(h))
        return self._assemble(h=float(h), p=p, t=t)

    def state_from_geometric(self, z: float) -> AtmosphereState:
        """Full state at geometric altitude ``z`` (m)."""
        h = float(altitudes.geopotential_from_geometric(z))
        return self.state_from_geopotential(h)

    def state_from_pressure_altitude(self, zp: float) -> AtmosphereState:
        """Full state at pressure altitude ``zp`` (m).

        ``p`` is always fixed by ``zp`` through the ISA law, independently of the
        model. The temperature is resolved differently depending on the model's
        nature (see ``00_DOC/01_MODELE_ATMOSPHERE.md`` §4):

        - **ISA / ISA±ΔT** are aeronautical conventions anchored to *pressure*
          altitude: by definition the ISA deviation ``ΔT`` is referenced to ``zp``
          (``ΔT = OAT − T_ISA(zp)``), so ``T = T_ISA(zp) + ΔT``. The temperature
          is therefore read at ``zp`` itself.
        - **CUSTOM** is a genuine physical temperature field ``T(H)`` versus
          *geopotential* altitude, in hydrostatic equilibrium with its own
          pressure law. The temperature is read at the geopotential height ``H*``
          where that atmosphere actually reaches pressure ``p`` — obtained by
          inverting the model's pressure law.

        In every case the reported geopotential altitude ``h`` is the physical
        height of the pressure surface (``H*``); for ISA it coincides with ``zp``.
        """
        p = float(isa.isa_pressure(zp))
        h = self._geopotential_from_pressure(p)
        if self.kind is ModelKind.CUSTOM:
            t = float(self.temperature(h))
        else:
            t = float(self.temperature(zp))
        return self._assemble(h=h, p=p, t=t)

    # --- assembly ----------------------------------------------------------

    def _assemble(self, *, h: float, p: float, t: float) -> AtmosphereState:
        rho = p / (R_AIR * t)
        return AtmosphereState(
            z=float(altitudes.geometric_from_geopotential(h)),
            h=h,
            zp=float(altitudes.pressure_altitude(p)),
            zrho=float(altitudes.density_altitude(rho)),
            t=t,
            p=p,
            rho=rho,
            a=float(thermo.speed_of_sound(t)),
            mu=float(thermo.viscosity_sutherland(t)),
            nu=float(thermo.kinematic_viscosity(t, rho)),
            theta=float(thermo.theta(t)),
            delta=float(thermo.delta(p)),
            sigma=float(thermo.sigma(rho)),
        )

    def pressure_at_geometric(self, z: ArrayLike) -> NDArray[np.float64]:
        """Vectorised static pressure (Pa) versus geometric altitude ``z`` (m).

        Convenience for figures (diagram A): converts geometric to geopotential
        and evaluates the model's pressure law over an array.
        """
        h = altitudes.geopotential_from_geometric(z)
        return self.pressure_geopotential(h)
