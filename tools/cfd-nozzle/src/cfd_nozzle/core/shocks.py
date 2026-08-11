"""Normal shocks, oblique shocks and Prandtl-Meyer expansions.

A shock is the only place in the quasi-1D model where entropy is created: T0 is
conserved, p0 is not. That single fact drives the whole regime map of a de
Laval nozzle — the stagnation-pressure loss across an internal shock raises the
effective sonic area downstream (A2* = At / (p02/p01)), which is what lets the
flow leave the nozzle subsonically at the imposed back pressure.

See ``00_DOC/02_CHOCS_ET_DETENTES.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cfd_nozzle.core.gas import GasModel
from cfd_nozzle.core.isentropic import mach_angle, p0_over_p
from cfd_nozzle.core.numerics import find_root, maximise

__all__ = [
    "NormalShockState",
    "ObliqueShockState",
    "beta_from_theta",
    "mach_from_prandtl_meyer",
    "mach_from_shock_p0_ratio",
    "normal_shock_state",
    "nu_max",
    "oblique_shock",
    "pitot_p0_ratio",
    "prandtl_meyer",
    "shock_entropy_rise",
    "shock_m2",
    "shock_p0_ratio",
    "shock_p_ratio",
    "shock_rho_ratio",
    "shock_t_ratio",
    "theta_from_beta",
    "theta_max_oblique",
]


def _check_supersonic(mach: float) -> None:
    if mach < 1.0:
        raise ValueError(f"un choc n'existe que pour M1 ≥ 1 (reçu {mach})")


# --- normal shock ---------------------------------------------------------


def shock_m2(m1: float, gamma: float = 1.4) -> float:
    """Downstream Mach number of a normal shock (always < 1)."""
    _check_supersonic(m1)
    numerator = 1.0 + 0.5 * (gamma - 1.0) * m1 * m1
    denominator = gamma * m1 * m1 - 0.5 * (gamma - 1.0)
    return math.sqrt(numerator / denominator)


def shock_p_ratio(m1: float, gamma: float = 1.4) -> float:
    """Static pressure jump p2/p1 across a normal shock."""
    _check_supersonic(m1)
    return (2.0 * gamma * m1 * m1 - (gamma - 1.0)) / (gamma + 1.0)


def shock_rho_ratio(m1: float, gamma: float = 1.4) -> float:
    """Density jump ρ2/ρ1 across a normal shock.

    Bounded by (γ+1)/(γ-1) as M1 → ∞: a shock cannot compress indefinitely.
    """
    _check_supersonic(m1)
    return ((gamma + 1.0) * m1 * m1) / ((gamma - 1.0) * m1 * m1 + 2.0)


def shock_t_ratio(m1: float, gamma: float = 1.4) -> float:
    """Static temperature jump T2/T1 (T0 itself is conserved)."""
    return shock_p_ratio(m1, gamma) / shock_rho_ratio(m1, gamma)


def shock_p0_ratio(m1: float, gamma: float = 1.4) -> float:
    """Stagnation pressure loss p02/p01 across a normal shock (≤ 1)."""
    _check_supersonic(m1)
    left = ((gamma + 1.0) * m1 * m1 / ((gamma - 1.0) * m1 * m1 + 2.0)) ** (gamma / (gamma - 1.0))
    right = ((gamma + 1.0) / (2.0 * gamma * m1 * m1 - (gamma - 1.0))) ** (1.0 / (gamma - 1.0))
    return float(left * right)


def shock_entropy_rise(m1: float, gas: GasModel) -> float:
    """Entropy created by the shock, Δs = -R·ln(p02/p01) [J/(kg·K)]."""
    return -gas.r * math.log(shock_p0_ratio(m1, gas.gamma))


def mach_from_shock_p0_ratio(ratio: float, gamma: float = 1.4) -> float:
    """Invert p02/p01 → M1. Used to locate a shock inside a divergent."""
    if not 0.0 < ratio <= 1.0:
        raise ValueError(f"p02/p01 doit être dans ]0, 1] (reçu {ratio})")
    if abs(ratio - 1.0) < 1e-14:
        return 1.0
    high = 2.0
    while shock_p0_ratio(high, gamma) > ratio and high < 1e3:
        high *= 2.0
    return find_root(lambda m: shock_p0_ratio(m, gamma) - ratio, 1.0 + 1e-12, high)


@dataclass(frozen=True)
class NormalShockState:
    """Every jump across a normal shock at ``m1``."""

    m1: float
    gamma: float
    m2: float
    p_ratio: float
    rho_ratio: float
    t_ratio: float
    p0_ratio: float


def normal_shock_state(m1: float, gamma: float = 1.4) -> NormalShockState:
    """Build the full :class:`NormalShockState`."""
    return NormalShockState(
        m1=m1,
        gamma=gamma,
        m2=shock_m2(m1, gamma),
        p_ratio=shock_p_ratio(m1, gamma),
        rho_ratio=shock_rho_ratio(m1, gamma),
        t_ratio=shock_t_ratio(m1, gamma),
        p0_ratio=shock_p0_ratio(m1, gamma),
    )


# --- Prandtl-Meyer expansion ----------------------------------------------


def prandtl_meyer(mach: float, gamma: float = 1.4) -> float:
    """Prandtl-Meyer function ν(M) [rad], defined for M ≥ 1.

    ν = √((γ+1)/(γ-1)) · atan(√((γ-1)/(γ+1)·(M²-1))) − atan(√(M²-1))

    It is the total angle through which a sonic flow must turn to reach M.
    """
    if mach < 1.0:
        raise ValueError(f"ν(M) n'est définie que pour M ≥ 1 (reçu {mach})")
    if mach == 1.0:
        return 0.0
    k = math.sqrt((gamma + 1.0) / (gamma - 1.0))
    s = math.sqrt(mach * mach - 1.0)
    return k * math.atan(s / k) - math.atan(s)


def nu_max(gamma: float = 1.4) -> float:
    """Maximum turning angle ν(M → ∞) [rad] — the vacuum expansion limit."""
    return 0.5 * math.pi * (math.sqrt((gamma + 1.0) / (gamma - 1.0)) - 1.0)


def mach_from_prandtl_meyer(nu: float, gamma: float = 1.4) -> float:
    """Invert ν → M by bisection."""
    limit = nu_max(gamma)
    if nu < 0.0:
        raise ValueError(f"ν doit être ≥ 0 (reçu {nu})")
    if nu >= limit:
        raise ValueError(
            f"ν = {math.degrees(nu):.3f}° ≥ ν_max = {math.degrees(limit):.3f}° : "
            "détente impossible pour ce γ"
        )
    if nu == 0.0:
        return 1.0
    high = 2.0
    while prandtl_meyer(high, gamma) < nu and high < 1e4:
        high *= 2.0
    return find_root(lambda m: prandtl_meyer(m, gamma) - nu, 1.0 + 1e-12, high)


# --- oblique shock --------------------------------------------------------


def theta_from_beta(m1: float, beta: float, gamma: float = 1.4) -> float:
    """θ-β-M relation: the deflection θ [rad] produced by a shock at angle β."""
    _check_supersonic(m1)
    s = math.sin(beta)
    numerator = 2.0 / math.tan(beta) * (m1 * m1 * s * s - 1.0)
    denominator = m1 * m1 * (gamma + math.cos(2.0 * beta)) + 2.0
    return math.atan2(numerator, denominator)


def theta_max_oblique(m1: float, gamma: float = 1.4) -> tuple[float, float]:
    """Detachment limit: ``(theta_max, beta_at_max)`` [rad].

    Beyond θ_max no attached oblique shock exists and the shock detaches into a
    bow shock — which quasi-1D theory cannot describe.
    """
    mu = mach_angle(m1)
    beta_max, theta_max = maximise(
        lambda b: theta_from_beta(m1, b, gamma), mu + 1e-6, 0.5 * math.pi - 1e-6
    )
    return theta_max, beta_max


def beta_from_theta(m1: float, theta: float, gamma: float = 1.4, *, weak: bool = True) -> float:
    """Invert θ → β [rad]. ``weak=True`` selects the physically usual root."""
    _check_supersonic(m1)
    if theta < 0.0:
        raise ValueError("θ doit être ≥ 0 — pour une déviation négative, voir prandtl_meyer()")
    if theta == 0.0:
        # Degenerate case: no deflection means no shock. The weak root is the
        # Mach wave itself, the strong one the normal shock. Solving for it
        # numerically would fail, the residual being zero at the bracket end.
        return mach_angle(m1) if weak else 0.5 * math.pi
    theta_max, beta_at_max = theta_max_oblique(m1, gamma)
    if theta > theta_max + 1e-12:
        raise ValueError(
            f"déviation {math.degrees(theta):.2f}° > θ_max = {math.degrees(theta_max):.2f}° "
            f"à M1 = {m1:.3f} : le choc est détaché"
        )

    def residual(beta: float) -> float:
        return theta_from_beta(m1, beta, gamma) - theta

    mu = mach_angle(m1)
    if weak:
        return find_root(residual, mu + 1e-9, beta_at_max)
    return find_root(residual, beta_at_max, 0.5 * math.pi - 1e-9)


@dataclass(frozen=True)
class ObliqueShockState:
    """An attached oblique shock, resolved from the deflection angle."""

    m1: float
    gamma: float
    theta_deg: float
    beta_deg: float
    mn1: float
    mn2: float
    m2: float
    p_ratio: float
    rho_ratio: float
    t_ratio: float
    p0_ratio: float
    weak: bool

    @property
    def solution_label(self) -> str:
        """French label of the selected root, for the report."""
        return "faible" if self.weak else "forte"


def oblique_shock(
    m1: float, theta: float, gamma: float = 1.4, *, weak: bool = True
) -> ObliqueShockState:
    """Solve an oblique shock from its deflection ``theta`` [rad].

    The jumps are those of a normal shock taken at the normal Mach component
    Mn1 = M1·sin β; only the tangential component survives untouched.
    """
    beta = beta_from_theta(m1, theta, gamma, weak=weak)
    mn1 = m1 * math.sin(beta)
    mn2 = shock_m2(mn1, gamma)
    return ObliqueShockState(
        m1=m1,
        gamma=gamma,
        theta_deg=math.degrees(theta),
        beta_deg=math.degrees(beta),
        mn1=mn1,
        mn2=mn2,
        m2=mn2 / math.sin(beta - theta),
        p_ratio=shock_p_ratio(mn1, gamma),
        rho_ratio=shock_rho_ratio(mn1, gamma),
        t_ratio=shock_t_ratio(mn1, gamma),
        p0_ratio=shock_p0_ratio(mn1, gamma),
        weak=weak,
    )


def pitot_p0_ratio(m1: float, gamma: float = 1.4) -> float:
    """Rayleigh pitot ratio p02/p1 — total pressure behind a bow shock over the
    upstream static pressure. Below M = 1 it degenerates to the isentropic
    p0/p, which is what a subsonic pitot reads.
    """
    if m1 < 1.0:
        return p0_over_p(m1, gamma)
    return p0_over_p(shock_m2(m1, gamma), gamma) * shock_p_ratio(m1, gamma)
