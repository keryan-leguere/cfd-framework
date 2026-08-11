"""Calorically perfect gas model.

Everything downstream of this module assumes a single gas with constant γ and
R: no chemistry, no freezing, no real-gas effects. For a rocket nozzle that
means γ and R must come from an equilibrium combustion calculation (CEA, RPA)
evaluated at the chamber conditions — the values in :data:`GAS_LIBRARY` are
order-of-magnitude placeholders, adequate for a preliminary sizing and nothing
more.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "G0",
    "GAS_LIBRARY",
    "R_UNIVERSAL",
    "GasModel",
    "gas_from_name",
]

#: Standard gravitational acceleration [m/s²] — the g₀ of the Isp definition.
G0 = 9.80665

#: Universal gas constant [J/(kmol·K)].
R_UNIVERSAL = 8314.46


@dataclass(frozen=True)
class GasModel:
    """A calorically perfect gas.

    Attributes:
        gamma: ratio of specific heats cp/cv [-].
        r: specific gas constant [J/(kg·K)].
        name: free-form label used by the reports.
    """

    gamma: float = 1.4
    r: float = 287.05
    name: str = "air"

    def __post_init__(self) -> None:
        if not self.gamma > 1.0:
            raise ValueError(f"γ doit être > 1 (reçu {self.gamma})")
        if not self.r > 0.0:
            raise ValueError(f"R doit être > 0 (reçu {self.r})")

    # --- derived thermodynamic properties ---------------------------------
    @property
    def cp(self) -> float:
        """Specific heat at constant pressure [J/(kg·K)]."""
        return self.gamma * self.r / (self.gamma - 1.0)

    @property
    def cv(self) -> float:
        """Specific heat at constant volume [J/(kg·K)]."""
        return self.r / (self.gamma - 1.0)

    @property
    def vandenkerckhove(self) -> float:
        """Vandenkerckhove function Γ(γ), the choked-mass-flow constant.

        Γ = √γ · (2/(γ+1))^((γ+1)/(2(γ-1))), so that a sonic throat passes
        ṁ = Γ · p0 · At / √(R·T0).
        """
        g = self.gamma
        return float(math.sqrt(g) * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0))))

    # --- local flow quantities ---------------------------------------------
    def sound_speed(self, t: float) -> float:
        """Speed of sound a = √(γ·R·T) [m/s]."""
        if t < 0.0:
            raise ValueError(f"T doit être ≥ 0 (reçu {t})")
        return math.sqrt(self.gamma * self.r * t)

    def velocity(self, mach: float, t: float) -> float:
        """Flow velocity V = M · a [m/s]."""
        return mach * self.sound_speed(t)

    def density(self, p: float, t: float) -> float:
        """Density from the perfect-gas law p = ρ·R·T [kg/m³]."""
        if t <= 0.0:
            raise ValueError(f"T doit être > 0 (reçu {t})")
        return p / (self.r * t)

    def limit_velocity(self, t0: float) -> float:
        """Limit velocity of an expansion to vacuum, √(2·cp·T0) [m/s].

        This is the M → ∞ asymptote: no nozzle can exceed it, whatever ε.
        """
        return math.sqrt(2.0 * self.cp * t0)

    @classmethod
    def from_molar_mass(cls, gamma: float, molar_mass: float, name: str = "gaz") -> GasModel:
        """Build the model from a molar mass [kg/kmol] instead of R."""
        if not molar_mass > 0.0:
            raise ValueError(f"la masse molaire doit être > 0 (reçue {molar_mass})")
        return cls(gamma=gamma, r=R_UNIVERSAL / molar_mass, name=name)


#: Common working gases and rough combustion-product estimates.
#:
#: The propellant entries are *orders of magnitude only*: real γ and R depend on
#: the mixture ratio, the chamber pressure and the degree of freezing along the
#: expansion. Use them to explore, not to size a flight engine.
GAS_LIBRARY: dict[str, GasModel] = {
    "air": GasModel(1.400, 287.05, "air"),
    "air_chaud": GasModel(1.330, 287.05, "air chaud (~1000 K)"),
    "n2": GasModel(1.400, 296.80, "azote"),
    "co2": GasModel(1.289, 188.92, "dioxyde de carbone"),
    "he": GasModel(1.667, 2077.0, "hélium"),
    "vapeur": GasModel(1.330, 461.50, "vapeur d'eau"),
    "lox_lh2": GasModel(1.200, 692.0, "LOX/LH2 (ordre de grandeur)"),
    "lox_rp1": GasModel(1.220, 345.0, "LOX/RP-1 (ordre de grandeur)"),
    "n2o4_mmh": GasModel(1.230, 322.0, "N2O4/MMH (ordre de grandeur)"),
    "apcp": GasModel(1.180, 300.0, "propergol solide APCP (ordre de grandeur)"),
}


def gas_from_name(name: str) -> GasModel:
    """Look up a gas in :data:`GAS_LIBRARY`.

    Raises:
        KeyError: with the list of known names, so the CLI and the YAML loader
            can report the same helpful message.
    """
    try:
        return GAS_LIBRARY[name]
    except KeyError:
        known = ", ".join(sorted(GAS_LIBRARY))
        raise KeyError(f"gaz inconnu « {name} » — gaz disponibles : {known}") from None
