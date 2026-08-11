"""Isentropic relations for a calorically perfect gas, and their inversions.

All of the ratios below follow from energy conservation plus the isentropic
law, and depend on nothing but the local Mach number and γ. The area ratio is
the integrated form of Hugoniot's relation and is the reason a de Laval nozzle
works at all: A/A* is minimum at M = 1, so a given ε ≥ 1 always admits two
solutions — one subsonic, one supersonic.

See ``00_DOC/01_MODELE_QUASI_1D.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from cfd_nozzle.core.numerics import find_root

__all__ = [
    "Branch",
    "IsentropicState",
    "area_ratio",
    "isentropic_state",
    "mach_angle",
    "mach_from_area_ratio",
    "mach_from_p0_over_p",
    "mach_from_t0_over_t",
    "mach_star",
    "p0_over_p",
    "rho0_over_rho",
    "t0_over_t",
]

#: Which of the two roots of the A/A* relation to return.
Branch = Literal["sub", "sup"]


def t0_over_t(mach: float, gamma: float = 1.4) -> float:
    """Stagnation temperature ratio T0/T = 1 + (γ-1)/2 · M²."""
    return 1.0 + 0.5 * (gamma - 1.0) * mach * mach


def p0_over_p(mach: float, gamma: float = 1.4) -> float:
    """Stagnation pressure ratio p0/p = (T0/T)^(γ/(γ-1))."""
    return float(t0_over_t(mach, gamma) ** (gamma / (gamma - 1.0)))


def rho0_over_rho(mach: float, gamma: float = 1.4) -> float:
    """Stagnation density ratio ρ0/ρ = (T0/T)^(1/(γ-1))."""
    return float(t0_over_t(mach, gamma) ** (1.0 / (gamma - 1.0)))


def area_ratio(mach: float, gamma: float = 1.4) -> float:
    """Area ratio A/A* [-].

    A/A* = (1/M) · [ (2/(γ+1)) · (1 + (γ-1)/2 · M²) ] ^ ((γ+1)/(2(γ-1)))
    """
    if not mach > 0.0:
        raise ValueError(f"M doit être > 0 (reçu {mach})")
    exponent = (gamma + 1.0) / (2.0 * (gamma - 1.0))
    return float((1.0 / mach) * ((2.0 / (gamma + 1.0)) * t0_over_t(mach, gamma)) ** exponent)


def mach_angle(mach: float) -> float:
    """Mach angle μ = asin(1/M) [rad], defined for M ≥ 1."""
    if mach < 1.0:
        raise ValueError(f"l'angle de Mach n'est défini que pour M ≥ 1 (reçu {mach})")
    return math.asin(min(1.0, 1.0 / mach))


def mach_star(mach: float, gamma: float = 1.4) -> float:
    """Critical Mach number M* = V/a* [-].

    Unlike M, M* stays finite as M → ∞ (it tends to √((γ+1)/(γ-1))), which is
    what makes it the natural variable across a shock.
    """
    m2 = mach * mach
    return math.sqrt(((gamma + 1.0) * m2) / (2.0 + (gamma - 1.0) * m2))


# --- inversions -----------------------------------------------------------


def mach_from_area_ratio(ratio: float, gamma: float = 1.4, branch: Branch = "sub") -> float:
    """Invert A/A* → M on the requested branch.

    Args:
        ratio: A/A*, must be ≥ 1.
        gamma: ratio of specific heats.
        branch: ``"sub"`` for the subsonic root (M < 1), ``"sup"`` for the
            supersonic one (M > 1).
    """
    if ratio < 1.0 - 1e-12:
        raise ValueError(f"A/A* doit être ≥ 1 — le col est sonique (reçu {ratio})")
    if abs(ratio - 1.0) < 1e-12:
        return 1.0
    if branch not in ("sub", "sup"):
        raise ValueError(f"branch doit valoir « sub » ou « sup » (reçu {branch!r})")

    def residual(mach: float) -> float:
        return area_ratio(mach, gamma) - ratio

    if branch == "sub":
        return find_root(residual, 1e-6, 1.0 - 1e-12)
    high = 2.0
    while area_ratio(high, gamma) < ratio and high < 1e4:
        high *= 2.0
    return find_root(residual, 1.0 + 1e-12, high)


def mach_from_p0_over_p(ratio: float, gamma: float = 1.4) -> float:
    """Invert p0/p → M. The relation is monotonic, so the root is explicit."""
    if ratio < 1.0:
        raise ValueError(f"p0/p doit être ≥ 1 (reçu {ratio})")
    return math.sqrt(2.0 / (gamma - 1.0) * (ratio ** ((gamma - 1.0) / gamma) - 1.0))


def mach_from_t0_over_t(ratio: float, gamma: float = 1.4) -> float:
    """Invert T0/T → M."""
    if ratio < 1.0:
        raise ValueError(f"T0/T doit être ≥ 1 (reçu {ratio})")
    return math.sqrt(2.0 / (gamma - 1.0) * (ratio - 1.0))


@dataclass(frozen=True)
class IsentropicState:
    """Every isentropic ratio at one Mach number.

    ``mu`` and ``nu`` (Mach angle and Prandtl-Meyer function, both in degrees)
    are only defined in supersonic flow and are None below M = 1.
    """

    mach: float
    gamma: float
    t_over_t0: float
    p_over_p0: float
    rho_over_rho0: float
    area_ratio: float
    mach_star: float
    mu_deg: float | None = None
    nu_deg: float | None = None


def isentropic_state(mach: float, gamma: float = 1.4) -> IsentropicState:
    """Build the full :class:`IsentropicState` at ``mach``."""
    from cfd_nozzle.core.shocks import prandtl_meyer  # circular at import time only

    mu_deg = nu_deg = None
    if mach >= 1.0:
        mu_deg = math.degrees(mach_angle(mach))
        nu_deg = math.degrees(prandtl_meyer(mach, gamma))
    return IsentropicState(
        mach=mach,
        gamma=gamma,
        t_over_t0=1.0 / t0_over_t(mach, gamma),
        p_over_p0=1.0 / p0_over_p(mach, gamma),
        rho_over_rho0=1.0 / rho0_over_rho(mach, gamma),
        area_ratio=area_ratio(mach, gamma),
        mach_star=mach_star(mach, gamma),
        mu_deg=mu_deg,
        nu_deg=nu_deg,
    )
