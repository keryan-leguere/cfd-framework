"""Convergent-divergent (de Laval) nozzle: operating regimes and performance.

A nozzle of fixed area ratio ε has exactly one supersonic design point. Away
from it, the flow adapts through one of five regimes, delimited by three
critical pressure ratios NPR = p0/pa (see :class:`CriticalRatios`). This module
identifies the regime, resolves the exit state, and derives the propulsive
performance.

Performance follows the Sutton decomposition, which keeps the three efficiency
knobs independent and mutually consistent:

    c*   = η_c* · √(R·T0) / Γ(γ)        characteristic velocity [m/s]
    ṁ    = p0 · At / c*                 so that ṁ · c* = p0 · At exactly
    Cf   = λ · Cf_mom + (pe − pa)/p0 · ε
    F    = Cf · p0 · At
    Isp  = F / (ṁ · g0) = Cf · c* / g0

Lowering η_c* therefore raises the mass flow needed to hold p0 and lowers Isp,
while λ (divergence loss) only degrades the momentum term. See
``00_DOC/03_REGIMES_ET_PERFORMANCES.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from numpy.typing import NDArray

from cfd_nozzle.core.gas import G0, GasModel
from cfd_nozzle.core.isentropic import (
    Branch,
    area_ratio,
    mach_from_area_ratio,
    mach_from_p0_over_p,
    p0_over_p,
    t0_over_t,
)
from cfd_nozzle.core.numerics import find_root
from cfd_nozzle.core.shocks import shock_p0_ratio, shock_p_ratio

__all__ = [
    "SEPARATION_RATIO",
    "CriticalRatios",
    "FlowField",
    "Nozzle",
    "NozzleState",
    "Regime",
]

#: Summerfield criterion: below this pe/pa the boundary layer is expected to
#: separate inside the divergent, and the quasi-1D result stops being physical.
SEPARATION_RATIO = 0.35


class Regime(Enum):
    """The five operating regimes of a de Laval nozzle."""

    VENTURI = "venturi"
    SHOCK_IN_DIVERGENT = "choc_interne"
    OVEREXPANDED = "sur_detendue"
    ADAPTED = "adaptee"
    UNDEREXPANDED = "sous_detendue"

    @property
    def label(self) -> str:
        """One-line French description used by the reports."""
        return _REGIME_LABELS[self]

    @property
    def is_choked(self) -> bool:
        """True when the throat is sonic."""
        return self is not Regime.VENTURI


_REGIME_LABELS: dict[Regime, str] = {
    Regime.VENTURI: "Subsonique partout — tuyère NON amorcée (venturi)",
    Regime.SHOCK_IN_DIVERGENT: "Amorcée — choc droit dans le divergent",
    Regime.OVEREXPANDED: "Amorcée — sur-détendue (pe < pa, chocs obliques en sortie)",
    Regime.ADAPTED: "Amorcée — adaptée (pe = pa, poussée optimale)",
    Regime.UNDEREXPANDED: "Amorcée — sous-détendue (pe > pa, faisceau de détente en sortie)",
}


@dataclass(frozen=True)
class CriticalRatios:
    """The three NPR = p0/pa that delimit the regimes, for a given ε.

    Attributes:
        npr_choked: first critical ratio — the throat just reaches M = 1 while
            the exit stays subsonic.
        npr_shock_at_exit: second critical ratio — a normal shock sits exactly
            in the exit plane. Below it the shock has moved inside.
        npr_design: third critical ratio — full supersonic expansion with
            pe = pa. This is the design point.
        mach_exit_sub: subsonic root of A/A* = ε.
        mach_exit_sup: supersonic root of A/A* = ε.
    """

    npr_choked: float
    npr_shock_at_exit: float
    npr_design: float
    mach_exit_sub: float
    mach_exit_sup: float


@dataclass(frozen=True)
class NozzleState:
    """Complete operating point of a nozzle for one triplet (p0, T0, pa)."""

    regime: Regime
    p0: float
    t0: float
    pa: float
    npr: float
    mach_exit: float
    p_exit: float
    t_exit: float
    rho_exit: float
    v_exit: float
    mdot: float
    thrust: float
    cf: float
    isp: float
    c_star: float
    v_effective: float
    area_ratio_opt: float
    mach_shock: float | None = None
    area_ratio_shock: float | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def choked(self) -> bool:
        """True when the throat is sonic."""
        return self.regime.is_choked

    @property
    def pressure_ratio_exit(self) -> float:
        """pe/pa — the over/under-expansion indicator."""
        return self.p_exit / self.pa


@dataclass(frozen=True)
class FlowField:
    """Quasi-1D distribution of the flow along the nozzle axis.

    All arrays share the shape of ``x``. ``x_shock`` is the abscissa of the
    internal normal shock when one exists.
    """

    x: NDArray[np.float64]
    area: NDArray[np.float64]
    mach: NDArray[np.float64]
    p: NDArray[np.float64]
    t: NDArray[np.float64]
    rho: NDArray[np.float64]
    v: NDArray[np.float64]
    state: NozzleState
    x_shock: float | None = None


class Nozzle:
    """A convergent-divergent nozzle under quasi-1D theory.

    Args:
        throat_area: throat area At [m²].
        area_ratio: ε = Ae/At [-], ≥ 1.
        gas: the working gas.
        eta_cstar: combustion efficiency η_c* = c*_réel / c*_idéal, ≤ 1.
        lambda_div: divergence loss coefficient; 1.0 is ideal, a cone of
            half-angle α gives (1 + cos α)/2.
    """

    def __init__(
        self,
        throat_area: float,
        area_ratio: float,
        gas: GasModel | None = None,
        *,
        eta_cstar: float = 1.0,
        lambda_div: float = 1.0,
    ) -> None:
        if not throat_area > 0.0:
            raise ValueError(f"l'aire au col doit être > 0 (reçue {throat_area})")
        if area_ratio < 1.0:
            raise ValueError(f"ε = Ae/At doit être ≥ 1 (reçu {area_ratio})")
        if not 0.0 < eta_cstar <= 1.0:
            raise ValueError(f"η_c* doit être dans ]0, 1] (reçu {eta_cstar})")
        if not 0.0 < lambda_div <= 1.0:
            raise ValueError(f"λ doit être dans ]0, 1] (reçu {lambda_div})")
        self.throat_area = float(throat_area)
        self.eps = float(area_ratio)
        self.gas = gas if gas is not None else GasModel()
        self.eta_cstar = float(eta_cstar)
        self.lambda_div = float(lambda_div)

    @classmethod
    def from_diameters(cls, throat_diameter: float, exit_diameter: float, **kwargs: object) -> Nozzle:
        """Build from circular throat and exit diameters [m]."""
        at = 0.25 * math.pi * throat_diameter**2
        ae = 0.25 * math.pi * exit_diameter**2
        return cls(at, ae / at, **kwargs)  # type: ignore[arg-type]

    def __repr__(self) -> str:
        return (
            f"Nozzle(At={self.throat_area:.6g} m², ε={self.eps:.4g}, "
            f"gas={self.gas.name!r}, η_c*={self.eta_cstar:.4g}, λ={self.lambda_div:.4g})"
        )

    # --- geometry ---------------------------------------------------------
    @property
    def exit_area(self) -> float:
        """Exit area Ae [m²]."""
        return self.throat_area * self.eps

    @property
    def throat_diameter(self) -> float:
        """Equivalent circular throat diameter [m]."""
        return 2.0 * math.sqrt(self.throat_area / math.pi)

    @property
    def exit_diameter(self) -> float:
        """Equivalent circular exit diameter [m]."""
        return 2.0 * math.sqrt(self.exit_area / math.pi)

    # --- limiting isentropic solutions ------------------------------------
    def mach_exit(self, branch: Branch = "sup") -> float:
        """Exit Mach number of one of the two isentropic solutions."""
        return mach_from_area_ratio(self.eps, self.gas.gamma, branch)

    def critical_ratios(self) -> CriticalRatios:
        """Compute the three critical NPR delimiting the regimes."""
        gamma = self.gas.gamma
        mach_sub = self.mach_exit("sub")
        mach_sup = self.mach_exit("sup")
        npr_design = p0_over_p(mach_sup, gamma)
        return CriticalRatios(
            npr_choked=p0_over_p(mach_sub, gamma),
            # A shock sitting in the exit plane raises the static pressure by
            # p2/p1, so the same p0 balances a back pressure that much higher.
            npr_shock_at_exit=npr_design / shock_p_ratio(mach_sup, gamma),
            npr_design=npr_design,
            mach_exit_sub=mach_sub,
            mach_exit_sup=mach_sup,
        )

    # --- mass flow and characteristic velocity ----------------------------
    def c_star(self, t0: float) -> float:
        """Characteristic velocity c* = η_c* · √(R·T0)/Γ [m/s]."""
        return self.eta_cstar * math.sqrt(self.gas.r * t0) / self.gas.vandenkerckhove

    def mdot_choked(self, p0: float, t0: float) -> float:
        """Mass flow with a sonic throat, ṁ = p0·At/c* [kg/s].

        With η_c* = 1 this is the textbook ṁ = Γ·p0·At/√(R·T0); a degraded
        combustion (η_c* < 1) needs *more* mass flow to hold the same chamber
        pressure, which is what the definition c* ≡ p0·At/ṁ expresses.
        """
        return p0 * self.throat_area / self.c_star(t0)

    def mdot_subsonic(self, p0: float, t0: float, pa: float) -> float:
        """Mass flow of an entirely subsonic (unchoked) nozzle [kg/s]."""
        gamma = self.gas.gamma
        mach = mach_from_p0_over_p(p0 / pa, gamma)
        t = t0 / t0_over_t(mach, gamma)
        return self.gas.density(pa, t) * self.exit_area * self.gas.velocity(mach, t)

    # --- thrust coefficient ------------------------------------------------
    def momentum_cf(self, p0: float, p_exit: float) -> float:
        """Ideal momentum thrust coefficient (no λ, no pressure term)."""
        gamma = self.gas.gamma
        return math.sqrt(
            (2.0 * gamma * gamma / (gamma - 1.0))
            * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
            * (1.0 - (p_exit / p0) ** ((gamma - 1.0) / gamma))
        )

    def thrust_coefficient(
        self, p0: float, pa: float, *, p_exit: float | None = None
    ) -> float:
        """Thrust coefficient Cf = F/(p0·At) [-] of the supersonic solution."""
        if p_exit is None:
            p_exit = p0 / p0_over_p(self.mach_exit("sup"), self.gas.gamma)
        return self.lambda_div * self.momentum_cf(p0, p_exit) + (p_exit - pa) / p0 * self.eps

    def optimal_area_ratio(self, p0: float, pa: float) -> float:
        """ε that would make this (p0, pa) adapted (pe = pa)."""
        if pa <= 0.0:
            return math.inf
        if p0 / pa <= 1.0:
            return 1.0
        mach = mach_from_p0_over_p(p0 / pa, self.gas.gamma)
        return area_ratio(mach, self.gas.gamma) if mach >= 1.0 else 1.0

    # --- internal shock location -------------------------------------------
    def shock_in_divergent(self, p0: float, pa: float) -> tuple[float, float]:
        """Locate the normal shock in the divergent.

        Returns ``(mach_shock, area_ratio_shock)``: the Mach number just
        upstream of the shock and the A/At at which it stands.

        The shock position is the one for which the subsonic recompression
        downstream leaves the nozzle exactly at pa. Downstream of the shock the
        sonic reference area grows to A2* = At/(p02/p01), so the exit sees an
        effective area ratio ε·(p02/p01).
        """
        gamma = self.gas.gamma

        def residual(mach_shock: float) -> float:
            p0_ratio = shock_p0_ratio(mach_shock, gamma)
            effective_eps = max(self.eps * p0_ratio, 1.0)
            mach_e = mach_from_area_ratio(effective_eps, gamma, "sub")
            return p0 * p0_ratio / p0_over_p(mach_e, gamma) - pa

        mach = find_root(residual, 1.0 + 1e-9, self.mach_exit("sup"))
        return mach, area_ratio(mach, gamma)

    # --- full analysis -----------------------------------------------------
    def solve(self, p0: float, t0: float, pa: float) -> NozzleState:
        """Identify the regime and compute the complete performance."""
        if not p0 > 0.0:
            raise ValueError(f"p0 doit être > 0 (reçu {p0})")
        if not t0 > 0.0:
            raise ValueError(f"T0 doit être > 0 (reçu {t0})")
        if pa < 0.0:
            raise ValueError(f"pa doit être ≥ 0 (reçu {pa})")
        if pa >= p0:
            raise ValueError(
                f"pa = {pa:g} Pa doit être < p0 = {p0:g} Pa : sans différence de pression "
                "il n'y a pas d'écoulement, et pour pa > p0 il s'inverserait — "
                "situation hors du modèle"
            )

        gamma = self.gas.gamma
        crit = self.critical_ratios()
        npr = p0 / pa if pa > 0.0 else math.inf
        warnings: list[str] = []
        mach_shock: float | None = None
        area_ratio_shock: float | None = None

        if npr < crit.npr_choked:
            regime = Regime.VENTURI
            mach_e = mach_from_p0_over_p(npr, gamma)
            p_e = pa
            mdot = self.mdot_subsonic(p0, t0, pa)
            warnings.append(
                "Le col n'est pas sonique : le divergent se comporte en diffuseur "
                "et la tuyère ne délivre pas de poussée utile."
            )
        elif npr < crit.npr_shock_at_exit - 1e-12:
            regime = Regime.SHOCK_IN_DIVERGENT
            mach_shock, area_ratio_shock = self.shock_in_divergent(p0, pa)
            p0_ratio = shock_p0_ratio(mach_shock, gamma)
            mach_e = mach_from_area_ratio(max(self.eps * p0_ratio, 1.0), gamma, "sub")
            p_e = pa
            mdot = self.mdot_choked(p0, t0)
            warnings.append(
                "Recompression interne : forte perte de pression d'arrêt et, dans la "
                "réalité, décollement quasi certain de la couche limite (Summerfield)."
            )
        elif npr < crit.npr_design - 1e-9:
            regime = Regime.OVEREXPANDED
            mach_e = crit.mach_exit_sup
            p_e = p0 / p0_over_p(mach_e, gamma)
            mdot = self.mdot_choked(p0, t0)
            warnings.append(
                "Le système de chocs obliques est extérieur : la tuyère est trop "
                "longue pour cette altitude."
            )
            if p_e / pa < SEPARATION_RATIO:
                warnings.append(
                    f"pe/pa = {p_e / pa:.3f} < {SEPARATION_RATIO} : risque sérieux de "
                    "décollement dans le divergent (critère de Summerfield)."
                )
        elif math.isfinite(npr) and abs(npr - crit.npr_design) <= max(1e-9, 1e-6 * npr):
            regime = Regime.ADAPTED
            mach_e = crit.mach_exit_sup
            p_e = pa
            mdot = self.mdot_choked(p0, t0)
        else:
            regime = Regime.UNDEREXPANDED
            mach_e = crit.mach_exit_sup
            p_e = p0 / p0_over_p(mach_e, gamma)
            mdot = self.mdot_choked(p0, t0)
            warnings.append(
                "La détente se poursuit à l'extérieur : un divergent plus long "
                "augmenterait la poussée."
            )

        t_e = t0 / t0_over_t(mach_e, gamma)
        rho_e = self.gas.density(p_e, t_e)
        v_e = self.gas.velocity(mach_e, t_e)

        if regime in (Regime.OVEREXPANDED, Regime.ADAPTED, Regime.UNDEREXPANDED):
            # Supersonic exit: go through Cf, so that λ degrades the momentum
            # term only and Isp = Cf·c*/g0 holds exactly.
            cf = self.thrust_coefficient(p0, pa, p_exit=p_e)
            thrust = cf * p0 * self.throat_area
        else:
            # Subsonic exit: the Cf correlation does not apply — integrate the
            # momentum balance directly. pe = pa here, so the pressure term is
            # zero, but it is kept explicit for clarity.
            thrust = mdot * v_e + (p_e - pa) * self.exit_area
            cf = thrust / (p0 * self.throat_area)

        isp = thrust / (mdot * G0) if mdot > 0.0 else 0.0

        return NozzleState(
            regime=regime,
            p0=p0,
            t0=t0,
            pa=pa,
            npr=npr,
            mach_exit=mach_e,
            p_exit=p_e,
            t_exit=t_e,
            rho_exit=rho_e,
            v_exit=v_e,
            mdot=mdot,
            thrust=thrust,
            cf=cf,
            isp=isp,
            c_star=self.c_star(t0),
            v_effective=thrust / mdot if mdot > 0.0 else 0.0,
            area_ratio_opt=self.optimal_area_ratio(p0, pa),
            mach_shock=mach_shock,
            area_ratio_shock=area_ratio_shock,
            warnings=warnings,
        )

    # --- axial distribution -------------------------------------------------
    def flow_field(
        self,
        x: NDArray[np.float64],
        area: NDArray[np.float64],
        p0: float,
        t0: float,
        pa: float,
        *,
        x_throat: float | None = None,
    ) -> FlowField:
        """Quasi-1D distribution of M, p, T, ρ and V along the nozzle.

        Args:
            x: axial abscissa [m].
            area: cross-sectional area at each ``x`` [m²].
            p0, t0, pa: the operating point.
            x_throat: abscissa of the throat; defaults to the minimum of
                ``area``.

        The distribution is the pure gas-dynamic one: η_c* and λ affect the
        integral performance in :meth:`solve`, not the local field.
        """
        gamma = self.gas.gamma
        x_arr = np.asarray(x, dtype=np.float64)
        area_arr = np.asarray(area, dtype=np.float64)
        if x_arr.shape != area_arr.shape:
            raise ValueError("x et area doivent avoir la même forme")
        if x_arr.size < 2:
            raise ValueError("il faut au moins deux points pour un champ")

        throat_index = (
            int(np.argmin(area_arr))
            if x_throat is None
            else int(np.argmin(np.abs(x_arr - x_throat)))
        )
        at_local = float(area_arr[throat_index])
        state = self.solve(p0, t0, pa)

        mach = np.zeros_like(x_arr)
        p = np.zeros_like(x_arr)
        x_shock: float | None = None

        if not state.choked:
            # Entirely subsonic: A* is fictitious, deduced from the exit Mach.
            a_star = self.exit_area / area_ratio(state.mach_exit, gamma)
            for i, a_i in enumerate(area_arr):
                mach[i] = mach_from_area_ratio(max(a_i / a_star, 1.0), gamma, "sub")
                p[i] = p0 / p0_over_p(mach[i], gamma)
        else:
            shock_index: int | None = None
            a_star_after = at_local
            p0_after = p0
            if state.mach_shock is not None and state.area_ratio_shock is not None:
                a_shock = at_local * state.area_ratio_shock
                downstream = [
                    i for i in range(throat_index, area_arr.size) if area_arr[i] >= a_shock
                ]
                shock_index = downstream[0] if downstream else area_arr.size - 1
                x_shock = float(x_arr[shock_index])
                p0_ratio = shock_p0_ratio(state.mach_shock, gamma)
                a_star_after = at_local / p0_ratio
                p0_after = p0 * p0_ratio

            for i, a_i in enumerate(area_arr):
                if i <= throat_index:  # convergent, subsonic
                    mach[i] = mach_from_area_ratio(max(a_i / at_local, 1.0), gamma, "sub")
                    p[i] = p0 / p0_over_p(mach[i], gamma)
                elif shock_index is None or i < shock_index:  # supersonic divergent
                    mach[i] = mach_from_area_ratio(max(a_i / at_local, 1.0), gamma, "sup")
                    p[i] = p0 / p0_over_p(mach[i], gamma)
                else:  # subsonic recompression downstream of the shock
                    mach[i] = mach_from_area_ratio(max(a_i / a_star_after, 1.0), gamma, "sub")
                    p[i] = p0_after / p0_over_p(mach[i], gamma)

        t = t0 / np.array([t0_over_t(float(m), gamma) for m in mach])
        rho = p / (self.gas.r * t)
        v = mach * np.sqrt(gamma * self.gas.r * t)
        return FlowField(
            x=x_arr,
            area=area_arr,
            mach=mach,
            p=p,
            t=t,
            rho=rho,
            v=v,
            state=state,
            x_shock=x_shock,
        )
