#!/usr/bin/env python3
"""
================================================================================
 NOZZLE TOOLBOX - Boite a outils pour le calcul des tuyeres (theorie quasi-1D)
================================================================================

Auteur   : genere avec Claude
Licence  : usage libre (pedagogique / ingenierie preliminaire)
Dependances : numpy (obligatoire), matplotlib (optionnel, pour les traces)

--------------------------------------------------------------------------------
CONTENU
--------------------------------------------------------------------------------
  1. Modele de gaz calorifiquement parfait                    -> class GasModel
  2. Relations isentropiques + inversions robustes            -> section ISENTROPIQUE
  3. Choc droit, choc oblique, detente de Prandtl-Meyer       -> section CHOCS
  4. Regimes de fonctionnement d'une tuyere de Laval          -> class Nozzle
  5. Performances propulsives (mdot, F, Cf, Isp, c*, eps_opt) -> class Nozzle
  6. Geometries : conique, galbe parabolique (Rao), MOC 2D    -> section GEOMETRIE
  7. Champ quasi-1D le long de la tuyere (choc interne inclus)-> Nozzle.flow_field
  8. Traces matplotlib + interface en ligne de commande       -> section CLI

--------------------------------------------------------------------------------
HYPOTHESES DE LA THEORIE QUASI-1D
--------------------------------------------------------------------------------
  * Ecoulement stationnaire, adiabatique, non visqueux (sauf a travers les chocs)
  * Gaz parfait, gamma et R constants (pas de chimie, pas de figeage)
  * Grandeurs uniformes sur chaque section droite -> A = A(x) uniquement
  * Variation de section "lente" (dA/dx petit) : pas de composante radiale
  * Les chocs internes sont traites comme des chocs droits localises

--------------------------------------------------------------------------------
UTILISATION RAPIDE
--------------------------------------------------------------------------------
  $ python nozzle_toolbox.py demo
  $ python nozzle_toolbox.py iso --mach 2.5
  $ python nozzle_toolbox.py iso --area-ratio 4.0 --branch sup
  $ python nozzle_toolbox.py shock --mach 3.0
  $ python nozzle_toolbox.py oblique --mach 3.0 --theta 20
  $ python nozzle_toolbox.py nozzle --p0 50e5 --t0 3200 --pa 1.013e5 \
        --dt 0.10 --eps 8 --gamma 1.20 --rgas 320 --plot
  $ python nozzle_toolbox.py moc --me 2.4 --n 25 --rt 0.05 --plot
  $ python nozzle_toolbox.py geom --rt 0.05 --eps 16 --type bell --plot

En import :
  >>> from nozzle_toolbox import GasModel, Nozzle
  >>> gas = GasModel(gamma=1.22, R=345.0)
  >>> noz = Nozzle(A_throat=7.85e-3, area_ratio=25.0, gas=gas)
  >>> noz.report(p0=70e5, T0=3400.0, pa=1.013e5)
"""

from __future__ import annotations

import argparse
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

# matplotlib est optionnel : la toolbox reste utilisable sans lui.
try:
    import matplotlib.pyplot as plt
    _HAS_MPL = True
except Exception:                                        # pragma: no cover
    plt = None
    _HAS_MPL = False


G0 = 9.80665          # acceleration standard de la pesanteur [m/s2]
R_UNIVERSAL = 8314.46  # constante universelle des gaz [J/(kmol.K)]


# ==============================================================================
#  0. OUTILS NUMERIQUES
# ==============================================================================

def _bisect(f: Callable[[float], float], a: float, b: float,
            tol: float = 1e-12, maxiter: int = 200) -> float:
    """Recherche de zero par dichotomie + secante (robuste, sans scipy).

    f doit changer de signe sur [a, b]. On combine bissection (garantie de
    convergence) et interpolation lineaire (vitesse) facon methode de Dekker
    simplifiee.
    """
    fa, fb = f(a), f(b)
    if fa == 0.0:
        return a
    if fb == 0.0:
        return b
    if fa * fb > 0.0:
        raise ValueError(
            f"Pas de changement de signe sur [{a:g}, {b:g}] : "
            f"f(a)={fa:g}, f(b)={fb:g}. Solution hors bornes ?"
        )
    for _ in range(maxiter):
        xm = 0.5 * (a + b)
        # candidat secante, accepte seulement s'il tombe dans les 80 % centraux
        # du crochet : sinon la convergence peut stagner sur les fonctions
        # tres raides (ex. A/A* quand M -> 0).
        lo, hi = min(a, b), max(a, b)
        span = hi - lo
        if fb != fa:
            xs = b - fb * (b - a) / (fb - fa)
            x = xs if (lo + 0.1 * span) <= xs <= (hi - 0.1 * span) else xm
        else:
            x = xm
        fx = f(x)
        if fx == 0.0 or abs(b - a) < tol * max(1.0, abs(x)):
            return x
        if fa * fx < 0.0:
            b, fb = x, fx
        else:
            a, fa = x, fx
    return 0.5 * (a + b)


def _maximize(f: Callable[[float], float], a: float, b: float,
              n: int = 200, refine: int = 60) -> tuple[float, float]:
    """Maximum d'une fonction unimodale sur [a, b] : balayage + section doree."""
    xs = np.linspace(a, b, n)
    ys = np.array([f(x) for x in xs])
    k = int(np.argmax(ys))
    lo = xs[max(k - 1, 0)]
    hi = xs[min(k + 1, n - 1)]
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    c, d = hi - phi * (hi - lo), lo + phi * (hi - lo)
    for _ in range(refine):
        if f(c) > f(d):
            hi, d = d, c
            c = hi - phi * (hi - lo)
        else:
            lo, c = c, d
            d = lo + phi * (hi - lo)
    xm = 0.5 * (lo + hi)
    return xm, f(xm)


# ==============================================================================
#  1. MODELE DE GAZ
# ==============================================================================

@dataclass(frozen=True)
class GasModel:
    """Gaz calorifiquement parfait.

    Parameters
    ----------
    gamma : rapport des chaleurs specifiques cp/cv [-]
    R     : constante specifique du gaz [J/(kg.K)]
    name  : etiquette libre
    """
    gamma: float = 1.4
    R: float = 287.05
    name: str = "air"

    def __post_init__(self):
        if self.gamma <= 1.0:
            raise ValueError("gamma doit etre > 1")
        if self.R <= 0.0:
            raise ValueError("R doit etre > 0")

    # --- proprietes derivees -------------------------------------------------
    @property
    def cp(self) -> float:
        """Chaleur specifique a pression constante [J/(kg.K)]."""
        return self.gamma * self.R / (self.gamma - 1.0)

    @property
    def cv(self) -> float:
        """Chaleur specifique a volume constant [J/(kg.K)]."""
        return self.R / (self.gamma - 1.0)

    @property
    def Gamma(self) -> float:
        """Fonction de Vandenkerckhove Gamma(gamma) = sqrt(g)*(2/(g+1))^((g+1)/(2(g-1)))."""
        g = self.gamma
        return math.sqrt(g) * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0)))

    # --- grandeurs locales ---------------------------------------------------
    def sound_speed(self, T: float) -> float:
        """Vitesse du son a [m/s]."""
        return math.sqrt(self.gamma * self.R * T)

    def velocity(self, M: float, T: float) -> float:
        """Vitesse V = M * a [m/s]."""
        return M * self.sound_speed(T)

    def density(self, p: float, T: float) -> float:
        """Masse volumique via p = rho.R.T [kg/m3]."""
        return p / (self.R * T)

    def v_limit(self, T0: float) -> float:
        """Vitesse limite (detente vers le vide, M -> inf) [m/s]."""
        return math.sqrt(2.0 * self.cp * T0)

    @classmethod
    def from_molar_mass(cls, gamma: float, M_molar: float,
                        name: str = "gaz") -> GasModel:
        """Construit le modele a partir de la masse molaire [kg/kmol]."""
        return cls(gamma=gamma, R=R_UNIVERSAL / M_molar, name=name)


# Quelques gaz usuels ----------------------------------------------------------
GAS_LIBRARY: dict[str, GasModel] = {
    "air":       GasModel(1.400, 287.05, "air"),
    "air_hot":   GasModel(1.330, 287.05, "air chaud (~1000 K)"),
    "n2":        GasModel(1.400, 296.80, "azote"),
    "co2":       GasModel(1.289, 188.92, "dioxyde de carbone"),
    "he":        GasModel(1.667, 2077.0, "helium"),
    "steam":     GasModel(1.330, 461.50, "vapeur d'eau"),
    "lox_lh2":   GasModel(1.200, 692.0,  "LOX/LH2 (ordre de grandeur)"),
    "lox_rp1":   GasModel(1.220, 345.0,  "LOX/RP-1 (ordre de grandeur)"),
    "n2o4_mmh":  GasModel(1.230, 322.0,  "N2O4/MMH (ordre de grandeur)"),
    "apcp":      GasModel(1.180, 300.0,  "propergol solide APCP (ordre de grandeur)"),
}


# ==============================================================================
#  2. RELATIONS ISENTROPIQUES
# ==============================================================================

def t0_over_t(M: float, g: float = 1.4) -> float:
    """Rapport de temperature d'arret T0/T."""
    return 1.0 + 0.5 * (g - 1.0) * M * M


def p0_over_p(M: float, g: float = 1.4) -> float:
    """Rapport de pression d'arret p0/p."""
    return t0_over_t(M, g) ** (g / (g - 1.0))


def rho0_over_rho(M: float, g: float = 1.4) -> float:
    """Rapport de masse volumique d'arret rho0/rho."""
    return t0_over_t(M, g) ** (1.0 / (g - 1.0))


def area_ratio(M: float, g: float = 1.4) -> float:
    """Rapport de section A/A* (relation de Hugoniot integree).

        A/A* = (1/M) * [ (2/(g+1)) * (1 + (g-1)/2 M^2) ] ^ ((g+1)/(2(g-1)))
    """
    if M <= 0.0:
        raise ValueError("M doit etre > 0")
    e = (g + 1.0) / (2.0 * (g - 1.0))
    return (1.0 / M) * ((2.0 / (g + 1.0)) * t0_over_t(M, g)) ** e


def mach_angle(M: float) -> float:
    """Angle de Mach mu = asin(1/M) [rad], defini pour M >= 1."""
    if M < 1.0:
        raise ValueError("angle de Mach defini seulement pour M >= 1")
    return math.asin(min(1.0, 1.0 / M))


def mach_star(M: float, g: float = 1.4) -> float:
    """Nombre de Mach critique M* = V/a* [-]."""
    return math.sqrt(((g + 1.0) * M * M) / (2.0 + (g - 1.0) * M * M))


# --- Inversions ---------------------------------------------------------------

def mach_from_area_ratio(ar: float, g: float = 1.4,
                         branch: str = "sub") -> float:
    """Inverse la relation A/A* -> M.

    branch : "sub" (branche subsonique, M<1) ou "sup" (supersonique, M>1).
    """
    if ar < 1.0 - 1e-12:
        raise ValueError("A/A* doit etre >= 1 (col sonique)")
    if abs(ar - 1.0) < 1e-12:
        return 1.0
    f = lambda M: area_ratio(M, g) - ar
    if branch.lower().startswith("sub"):
        return _bisect(f, 1e-6, 1.0 - 1e-12)
    elif branch.lower().startswith("sup"):
        hi = 2.0
        while area_ratio(hi, g) < ar and hi < 1e4:
            hi *= 2.0
        return _bisect(f, 1.0 + 1e-12, hi)
    raise ValueError("branch doit valoir 'sub' ou 'sup'")


def mach_from_p0_over_p(ratio: float, g: float = 1.4) -> float:
    """Inverse p0/p -> M (relation monotone, solution unique)."""
    if ratio < 1.0:
        raise ValueError("p0/p doit etre >= 1")
    return math.sqrt(2.0 / (g - 1.0) * (ratio ** ((g - 1.0) / g) - 1.0))


def mach_from_t0_over_t(ratio: float, g: float = 1.4) -> float:
    """Inverse T0/T -> M."""
    if ratio < 1.0:
        raise ValueError("T0/T doit etre >= 1")
    return math.sqrt(2.0 / (g - 1.0) * (ratio - 1.0))


def isentropic_table(M: float, g: float = 1.4) -> dict[str, float]:
    """Toutes les grandeurs isentropiques pour un Mach donne."""
    out = {
        "M": M,
        "T/T0": 1.0 / t0_over_t(M, g),
        "p/p0": 1.0 / p0_over_p(M, g),
        "rho/rho0": 1.0 / rho0_over_rho(M, g),
        "T0/T": t0_over_t(M, g),
        "p0/p": p0_over_p(M, g),
        "rho0/rho": rho0_over_rho(M, g),
        "A/A*": area_ratio(M, g),
        "M* = V/a*": mach_star(M, g),
    }
    if M >= 1.0:
        out["mu [deg]"] = math.degrees(mach_angle(M))
        out["nu [deg]"] = math.degrees(prandtl_meyer(M, g))
    return out


# ==============================================================================
#  3. CHOCS ET DETENTES
# ==============================================================================

def shock_M2(M1: float, g: float = 1.4) -> float:
    """Mach aval d'un choc droit."""
    _check_supersonic(M1)
    num = 1.0 + 0.5 * (g - 1.0) * M1 * M1
    den = g * M1 * M1 - 0.5 * (g - 1.0)
    return math.sqrt(num / den)


def shock_p2_p1(M1: float, g: float = 1.4) -> float:
    """Saut de pression statique a travers un choc droit."""
    _check_supersonic(M1)
    return (2.0 * g * M1 * M1 - (g - 1.0)) / (g + 1.0)


def shock_rho2_rho1(M1: float, g: float = 1.4) -> float:
    """Saut de masse volumique a travers un choc droit."""
    _check_supersonic(M1)
    return ((g + 1.0) * M1 * M1) / ((g - 1.0) * M1 * M1 + 2.0)


def shock_T2_T1(M1: float, g: float = 1.4) -> float:
    """Saut de temperature statique (T0 est conserve)."""
    return shock_p2_p1(M1, g) / shock_rho2_rho1(M1, g)


def shock_p02_p01(M1: float, g: float = 1.4) -> float:
    """Perte de pression d'arret a travers un choc droit (< 1)."""
    _check_supersonic(M1)
    a = ((g + 1.0) * M1 * M1 / ((g - 1.0) * M1 * M1 + 2.0)) ** (g / (g - 1.0))
    b = ((g + 1.0) / (2.0 * g * M1 * M1 - (g - 1.0))) ** (1.0 / (g - 1.0))
    return a * b


def shock_entropy_rise(M1: float, gas: GasModel) -> float:
    """Creation d'entropie a travers le choc, ds = -R ln(p02/p01) [J/(kg.K)]."""
    return -gas.R * math.log(shock_p02_p01(M1, gas.gamma))


def mach_from_shock_p02_p01(ratio: float, g: float = 1.4) -> float:
    """Inverse p02/p01 -> M1 (utile pour localiser un choc interne)."""
    if not (0.0 < ratio <= 1.0):
        raise ValueError("p02/p01 doit etre dans ]0, 1]")
    if abs(ratio - 1.0) < 1e-14:
        return 1.0
    f = lambda M: shock_p02_p01(M, g) - ratio
    hi = 2.0
    while shock_p02_p01(hi, g) > ratio and hi < 1e3:
        hi *= 2.0
    return _bisect(f, 1.0 + 1e-12, hi)


def normal_shock_table(M1: float, g: float = 1.4) -> dict[str, float]:
    """Tableau complet du choc droit."""
    return {
        "M1": M1,
        "M2": shock_M2(M1, g),
        "p2/p1": shock_p2_p1(M1, g),
        "rho2/rho1": shock_rho2_rho1(M1, g),
        "T2/T1": shock_T2_T1(M1, g),
        "p02/p01": shock_p02_p01(M1, g),
        "p1/p02": 1.0 / (p0_over_p(M1, g) * shock_p02_p01(M1, g)),
    }


def _check_supersonic(M1: float) -> None:
    if M1 < 1.0:
        raise ValueError("un choc n'existe que pour M1 >= 1")


# --- Prandtl-Meyer ------------------------------------------------------------

def prandtl_meyer(M: float, g: float = 1.4) -> float:
    """Fonction de Prandtl-Meyer nu(M) [rad], definie pour M >= 1.

        nu = sqrt((g+1)/(g-1)) * atan( sqrt((g-1)/(g+1)(M^2-1)) ) - atan(sqrt(M^2-1))
    """
    if M < 1.0:
        raise ValueError("nu(M) definie seulement pour M >= 1")
    if M == 1.0:
        return 0.0
    k = math.sqrt((g + 1.0) / (g - 1.0))
    s = math.sqrt(M * M - 1.0)
    return k * math.atan(s / k) - math.atan(s)


def nu_max(g: float = 1.4) -> float:
    """Angle de detente maximal (M -> infini) [rad]."""
    return 0.5 * math.pi * (math.sqrt((g + 1.0) / (g - 1.0)) - 1.0)


def mach_from_prandtl_meyer(nu: float, g: float = 1.4) -> float:
    """Inverse nu -> M par dichotomie."""
    nmax = nu_max(g)
    if nu < 0.0:
        raise ValueError("nu doit etre >= 0")
    if nu >= nmax:
        raise ValueError(f"nu = {math.degrees(nu):.3f} deg >= nu_max = "
                         f"{math.degrees(nmax):.3f} deg (detente impossible)")
    if nu == 0.0:
        return 1.0
    f = lambda M: prandtl_meyer(M, g) - nu
    hi = 2.0
    while prandtl_meyer(hi, g) < nu and hi < 1e4:
        hi *= 2.0
    return _bisect(f, 1.0 + 1e-12, hi)


# --- Choc oblique -------------------------------------------------------------

def theta_from_beta(M1: float, beta: float, g: float = 1.4) -> float:
    """Relation theta-beta-M : deviation theta [rad] pour un angle de choc beta."""
    _check_supersonic(M1)
    s = math.sin(beta)
    num = 2.0 / math.tan(beta) * (M1 * M1 * s * s - 1.0)
    den = M1 * M1 * (g + math.cos(2.0 * beta)) + 2.0
    return math.atan2(num, den)


def theta_max_oblique(M1: float, g: float = 1.4) -> tuple[float, float]:
    """Deviation maximale et angle de choc associe : (theta_max, beta_at_max) [rad]."""
    mu = mach_angle(M1)
    beta_m, th_m = _maximize(lambda b: theta_from_beta(M1, b, g),
                             mu + 1e-6, 0.5 * math.pi - 1e-6)
    return th_m, beta_m


def beta_from_theta(M1: float, theta: float, g: float = 1.4,
                    weak: bool = True) -> float:
    """Inverse theta -> beta [rad]. weak=True : solution faible (physique usuelle)."""
    _check_supersonic(M1)
    th_max, beta_at_max = theta_max_oblique(M1, g)
    if theta > th_max + 1e-12:
        raise ValueError(
            f"Deviation {math.degrees(theta):.2f} deg > theta_max = "
            f"{math.degrees(th_max):.2f} deg a M1={M1:.3f} : choc detache."
        )
    if theta < 0.0:
        raise ValueError("theta doit etre >= 0 (utiliser Prandtl-Meyer si detente)")
    f = lambda b: theta_from_beta(M1, b, g) - theta
    mu = mach_angle(M1)
    if weak:
        return _bisect(f, mu + 1e-9, beta_at_max)
    return _bisect(f, beta_at_max, 0.5 * math.pi - 1e-9)


def oblique_shock(M1: float, theta: float, g: float = 1.4,
                  weak: bool = True) -> dict[str, float]:
    """Choc oblique complet a partir de la deviation theta [rad]."""
    beta = beta_from_theta(M1, theta, g, weak)
    Mn1 = M1 * math.sin(beta)
    Mn2 = shock_M2(Mn1, g)
    M2 = Mn2 / math.sin(beta - theta)
    return {
        "M1": M1,
        "theta [deg]": math.degrees(theta),
        "beta [deg]": math.degrees(beta),
        "Mn1": Mn1,
        "Mn2": Mn2,
        "M2": M2,
        "p2/p1": shock_p2_p1(Mn1, g),
        "rho2/rho1": shock_rho2_rho1(Mn1, g),
        "T2/T1": shock_T2_T1(Mn1, g),
        "p02/p01": shock_p02_p01(Mn1, g),
        "solution": "faible" if weak else "forte",
    }


# ==============================================================================
#  4-5. TUYERE : REGIMES ET PERFORMANCES
# ==============================================================================

@dataclass
class NozzleState:
    """Etat de fonctionnement complet d'une tuyere pour un triplet (p0, T0, pa)."""
    regime: str
    p0: float
    T0: float
    pa: float
    npr: float                      # p0/pa
    choked: bool
    M_exit: float
    p_exit: float
    T_exit: float
    rho_exit: float
    V_exit: float
    mdot: float
    thrust: float
    cf: float
    isp: float
    c_star: float
    area_ratio_opt: float           # eps donnant l'adaptation pour ce (p0, pa)
    M_shock: float | None = None       # Mach juste avant le choc interne
    area_ratio_shock: float | None = None  # A_choc / A_col
    notes: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        L = []
        A = L.append
        A("-" * 74)
        A(f"  REGIME : {self.regime}")
        A("-" * 74)
        A(f"  NPR = p0/pa           : {self.npr:12.4f}")
        A(f"  Amorcage (col sonique): {'OUI' if self.choked else 'NON'}")
        if self.M_shock is not None:
            A(f"  Choc droit interne    : M_choc = {self.M_shock:.4f} "
              f"a A/At = {self.area_ratio_shock:.4f}")
        A("")
        A(f"  Mach en sortie   Me   : {self.M_exit:12.4f}")
        A(f"  Pression sortie  pe   : {self.p_exit:12.1f} Pa   "
          f"(pe/pa = {self.p_exit / self.pa:.4f})")
        A(f"  Temperature      Te   : {self.T_exit:12.2f} K")
        A(f"  Masse volumique  rhoe : {self.rho_exit:12.5f} kg/m3")
        A(f"  Vitesse sortie   Ve   : {self.V_exit:12.2f} m/s")
        A("")
        A(f"  Debit massique   mdot : {self.mdot:12.5f} kg/s")
        A(f"  Poussee          F    : {self.thrust:12.2f} N")
        A(f"  Coeff. poussee   Cf   : {self.cf:12.4f}")
        A(f"  Impulsion spec.  Isp  : {self.isp:12.2f} s")
        A(f"  Vitesse caract.  c*   : {self.c_star:12.2f} m/s")
        A(f"  eps optimal pour pa   : {self.area_ratio_opt:12.4f}")
        for n in self.notes:
            A(f"  ! {n}")
        A("-" * 74)
        return "\n".join(L)


class Nozzle:
    """Tuyere convergente-divergente (de Laval) en theorie quasi-1D.

    Parameters
    ----------
    A_throat    : aire au col [m2]
    area_ratio  : eps = A_sortie / A_col [-]
    gas         : modele de gaz
    eta_cstar   : rendement de combustion (c* reel / c* theorique)
    lambda_div  : coefficient de perte par divergence (1.0 = ideal ;
                  cone de demi-angle alpha -> (1+cos alpha)/2)
    """

    def __init__(self, A_throat: float, area_ratio: float,
                 gas: GasModel = GasModel(),
                 eta_cstar: float = 1.0, lambda_div: float = 1.0):
        if A_throat <= 0.0:
            raise ValueError("A_throat doit etre > 0")
        if area_ratio < 1.0:
            raise ValueError("area_ratio doit etre >= 1")
        self.At = float(A_throat)
        self.eps = float(area_ratio)
        self.gas = gas
        self.eta_cstar = float(eta_cstar)
        self.lam = float(lambda_div)

    # --- geometrie ------------------------------------------------------------
    @property
    def Ae(self) -> float:
        """Aire de sortie [m2]."""
        return self.At * self.eps

    @property
    def Dt(self) -> float:
        """Diametre au col [m] (section circulaire)."""
        return 2.0 * math.sqrt(self.At / math.pi)

    @property
    def De(self) -> float:
        """Diametre de sortie [m]."""
        return 2.0 * math.sqrt(self.Ae / math.pi)

    @classmethod
    def from_diameters(cls, D_throat: float, D_exit: float, **kw) -> Nozzle:
        At = 0.25 * math.pi * D_throat ** 2
        Ae = 0.25 * math.pi * D_exit ** 2
        return cls(At, Ae / At, **kw)

    # --- solutions isentropiques limites -------------------------------------
    @property
    def M_exit_sub(self) -> float:
        """Mach de sortie de la solution subsonique (col juste sonique)."""
        return mach_from_area_ratio(self.eps, self.gas.gamma, "sub")

    @property
    def M_exit_sup(self) -> float:
        """Mach de sortie de la solution supersonique (tuyere adaptee)."""
        return mach_from_area_ratio(self.eps, self.gas.gamma, "sup")

    def critical_pressure_ratios(self) -> dict[str, float]:
        """Les trois NPR critiques qui delimitent les regimes.

        NPR1 : amorcage du col, sortie subsonique (1er critique)
        NPR2 : choc droit pile en sortie          (2e critique)
        NPR3 : adaptation, pe = pa                (3e critique / design)
        """
        g = self.gas.gamma
        Me_sub = self.M_exit_sub
        Me_sup = self.M_exit_sup
        npr1 = p0_over_p(Me_sub, g)
        npr3 = p0_over_p(Me_sup, g)
        npr2 = npr3 / shock_p2_p1(Me_sup, g)
        return {"NPR1_amorcage": npr1, "NPR2_choc_sortie": npr2,
                "NPR3_adapte": npr3, "Me_sub": Me_sub, "Me_sup": Me_sup}

    # --- debit ----------------------------------------------------------------
    def mdot_choked(self, p0: float, T0: float) -> float:
        """Debit massique en regime amorce (col sonique) [kg/s].

            mdot = Gamma(g) * p0 * At / sqrt(R T0)
        """
        return (self.gas.Gamma * p0 * self.At / math.sqrt(self.gas.R * T0)
                * self.eta_cstar)

    def mdot_subsonic(self, p0: float, T0: float, pa: float) -> float:
        """Debit massique en regime non amorce (tuyere entierement subsonique)."""
        g = self.gas.gamma
        Me = mach_from_p0_over_p(p0 / pa, g)      # sortie a la pression ambiante
        Te = T0 / t0_over_t(Me, g)
        rhoe = self.gas.density(pa, Te)
        Ve = self.gas.velocity(Me, Te)
        return rhoe * self.Ae * Ve

    def c_star(self, T0: float) -> float:
        """Vitesse caracteristique c* = p0.At/mdot [m/s]."""
        return self.eta_cstar * math.sqrt(self.gas.R * T0) / self.gas.Gamma

    # --- coefficient de poussee ----------------------------------------------
    def thrust_coefficient(self, p0: float, pa: float,
                           pe: float | None = None,
                           Me: float | None = None) -> float:
        """Coefficient de poussee Cf = F / (p0 . At) [-]."""
        g = self.gas.gamma
        if pe is None:
            Me = self.M_exit_sup if Me is None else Me
            pe = p0 / p0_over_p(Me, g)
        cf_mom = math.sqrt(
            (2.0 * g * g / (g - 1.0))
            * (2.0 / (g + 1.0)) ** ((g + 1.0) / (g - 1.0))
            * (1.0 - (pe / p0) ** ((g - 1.0) / g))
        )
        return self.lam * cf_mom + (pe - pa) / p0 * self.eps

    def optimal_area_ratio(self, p0: float, pa: float) -> float:
        """eps donnant l'adaptation (pe = pa) pour le rapport p0/pa donne."""
        g = self.gas.gamma
        if pa <= 0.0:
            return float("inf")
        if p0 / pa <= 1.0:
            return 1.0
        Me = mach_from_p0_over_p(p0 / pa, g)
        if Me < 1.0:
            return 1.0
        return area_ratio(Me, g)

    # --- localisation d'un choc interne --------------------------------------
    def shock_in_divergent(self, p0: float, pa: float) -> tuple[float, float]:
        """Position du choc droit dans le divergent.

        Retourne (M_choc, A_choc/A_col). Resolution : on cherche le Mach amont
        du choc tel que la detente subsonique aval debouche exactement a pa.
        """
        g = self.gas.gamma
        Me_sup = self.M_exit_sup

        def residual(Ms: float) -> float:
            pr0 = shock_p02_p01(Ms, g)          # perte de pression d'arret
            # A* augmente en aval du choc : A2* = At / (p02/p01)
            ar2 = self.eps * pr0                # Ae / A2*
            Me = mach_from_area_ratio(max(ar2, 1.0), g, "sub")
            pe = p0 * pr0 / p0_over_p(Me, g)
            return pe - pa

        Ms = _bisect(residual, 1.0 + 1e-9, Me_sup)
        return Ms, area_ratio(Ms, g)

    # --- analyse complete -----------------------------------------------------
    def solve(self, p0: float, T0: float, pa: float) -> NozzleState:
        """Determine le regime et calcule toutes les performances."""
        g = self.gas.gamma
        gas = self.gas
        crit = self.critical_pressure_ratios()
        npr = p0 / pa if pa > 0.0 else float("inf")
        notes: list[str] = []
        M_shock = ars = None

        # ---- 1) non amorcee -------------------------------------------------
        if npr < crit["NPR1_amorcage"]:
            regime = "Subsonique partout - tuyere NON amorcee (venturi)"
            Me = mach_from_p0_over_p(npr, g)
            pe = pa
            mdot = self.mdot_subsonic(p0, T0, pa)
            choked = False
            notes.append("Le col n'est pas sonique : le divergent agit en diffuseur.")

        # ---- 2) choc droit dans le divergent --------------------------------
        elif npr < crit["NPR2_choc_sortie"] - 1e-12:
            regime = "Amorcee - CHOC DROIT dans le divergent"
            M_shock, ars = self.shock_in_divergent(p0, pa)
            pr0 = shock_p02_p01(M_shock, g)
            Me = mach_from_area_ratio(self.eps * pr0, g, "sub")
            pe = pa
            mdot = self.mdot_choked(p0, T0)
            choked = True
            notes.append("Recompression interne : forte perte de pression d'arret, "
                         "decollement probable dans la realite (critere de Summerfield).")

        # ---- 3) sur-detendue -------------------------------------------------
        elif npr < crit["NPR3_adapte"] - 1e-9:
            regime = "Amorcee - SUR-DETENDUE (pe < pa, chocs obliques en sortie)"
            Me = crit["Me_sup"]
            pe = p0 / p0_over_p(Me, g)
            mdot = self.mdot_choked(p0, T0)
            choked = True
            notes.append("Le systeme de chocs obliques est exterieur ; "
                         "la tuyere est trop longue pour cette altitude.")
            if pe / pa < 0.35:
                notes.append("pe/pa < 0.35 : risque serieux de decollement de la "
                             "couche limite dans le divergent.")

        # ---- 4) adaptee ------------------------------------------------------
        elif abs(npr - crit["NPR3_adapte"]) <= max(1e-9, 1e-6 * npr):
            regime = "Amorcee - ADAPTEE (pe = pa, poussee optimale)"
            Me = crit["Me_sup"]
            pe = pa
            mdot = self.mdot_choked(p0, T0)
            choked = True

        # ---- 5) sous-detendue ------------------------------------------------
        else:
            regime = "Amorcee - SOUS-DETENDUE (pe > pa, faisceau de detente en sortie)"
            Me = crit["Me_sup"]
            pe = p0 / p0_over_p(Me, g)
            mdot = self.mdot_choked(p0, T0)
            choked = True
            notes.append("La detente se poursuit a l'exterieur : "
                         "un divergent plus long augmenterait la poussee.")

        # ---- grandeurs de sortie --------------------------------------------
        Te = T0 / t0_over_t(Me, g)
        rhoe = gas.density(pe, Te)
        Ve = self.lam * gas.velocity(Me, Te)
        F = mdot * Ve + (pe - pa) * self.Ae
        cf = F / (p0 * self.At)
        isp = F / (mdot * G0) if mdot > 0 else 0.0

        return NozzleState(
            regime=regime, p0=p0, T0=T0, pa=pa, npr=npr, choked=choked,
            M_exit=Me, p_exit=pe, T_exit=Te, rho_exit=rhoe, V_exit=Ve,
            mdot=mdot, thrust=F, cf=cf, isp=isp, c_star=self.c_star(T0),
            area_ratio_opt=self.optimal_area_ratio(p0, pa),
            M_shock=M_shock, area_ratio_shock=ars, notes=notes,
        )

    # --- champ quasi-1D le long de l'axe -------------------------------------
    def flow_field(self, x: np.ndarray, A: np.ndarray,
                   p0: float, T0: float, pa: float,
                   x_throat: float | None = None) -> dict[str, np.ndarray]:
        """Distribution des grandeurs le long de la tuyere.

        Parameters
        ----------
        x, A       : abscisse [m] et aire de la section [m2] (A minimal = col)
        x_throat   : abscisse du col ; par defaut celle du minimum de A

        Returns
        -------
        dict avec 'x', 'A', 'M', 'p', 'T', 'rho', 'V', et 'x_shock' (ou None)
        """
        g = self.gas.gamma
        x = np.asarray(x, dtype=float)
        A = np.asarray(A, dtype=float)
        it = int(np.argmin(A)) if x_throat is None else int(np.argmin(np.abs(x - x_throat)))
        At = A[it]
        st = self.solve(p0, T0, pa)

        M = np.zeros_like(x)
        p = np.zeros_like(x)
        x_shock = None

        if not st.choked:
            # tout subsonique : A* fictif deduit du Mach de sortie
            Astar = self.Ae / area_ratio(st.M_exit, g)
            for i, Ai in enumerate(A):
                M[i] = mach_from_area_ratio(max(Ai / Astar, 1.0), g, "sub")
                p[i] = p0 / p0_over_p(M[i], g)
        else:
            i_shock = None
            if st.M_shock is not None:
                A_shock = At * st.area_ratio_shock
                # premiere section du divergent dont l'aire depasse A_shock
                cand = [i for i in range(it, len(A)) if A[i] >= A_shock]
                i_shock = cand[0] if cand else len(A) - 1
                x_shock = float(x[i_shock])
                pr0 = shock_p02_p01(st.M_shock, g)
                Astar2 = At / pr0
                p02 = p0 * pr0

            for i, Ai in enumerate(A):
                if i <= it:                                  # convergent
                    M[i] = mach_from_area_ratio(max(Ai / At, 1.0), g, "sub")
                    p[i] = p0 / p0_over_p(M[i], g)
                elif i_shock is None or i < i_shock:         # divergent supersonique
                    M[i] = mach_from_area_ratio(max(Ai / At, 1.0), g, "sup")
                    p[i] = p0 / p0_over_p(M[i], g)
                else:                                        # apres le choc
                    M[i] = mach_from_area_ratio(max(Ai / Astar2, 1.0), g, "sub")
                    p[i] = p02 / p0_over_p(M[i], g)

        T = T0 / np.array([t0_over_t(m, g) for m in M])
        rho = p / (self.gas.R * T)
        V = M * np.sqrt(g * self.gas.R * T)
        return {"x": x, "A": A, "M": M, "p": p, "T": T, "rho": rho,
                "V": V, "x_shock": x_shock, "state": st}

    # --- rapport texte --------------------------------------------------------
    def report(self, p0: float, T0: float, pa: float) -> NozzleState:
        """Affiche un rapport complet et renvoie l'etat calcule."""
        crit = self.critical_pressure_ratios()
        print("=" * 74)
        print("  TUYERE CONVERGENTE-DIVERGENTE - ANALYSE QUASI-1D")
        print("=" * 74)
        print(f"  Gaz            : {self.gas.name}  "
              f"(gamma = {self.gas.gamma:.4f}, R = {self.gas.R:.2f} J/kg/K)")
        print(f"  A_col          : {self.At:.6e} m2   (D_col = {self.Dt * 1e3:.2f} mm)")
        print(f"  A_sortie       : {self.Ae:.6e} m2   (D_e   = {self.De * 1e3:.2f} mm)")
        print(f"  eps = Ae/At    : {self.eps:.4f}")
        print(f"  eta_c*         : {self.eta_cstar:.4f}     lambda_div : {self.lam:.4f}")
        print("-" * 74)
        print(f"  p0 = {p0:.4e} Pa | T0 = {T0:.2f} K | pa = {pa:.4e} Pa")
        print("-" * 74)
        print("  NPR critiques (p0/pa) :")
        print(f"    NPR1 (amorcage, sortie subsonique) : {crit['NPR1_amorcage']:10.4f}"
              f"   -> Me_sub = {crit['Me_sub']:.4f}")
        print(f"    NPR2 (choc droit en sortie)        : {crit['NPR2_choc_sortie']:10.4f}")
        print(f"    NPR3 (adaptation, pe = pa)         : {crit['NPR3_adapte']:10.4f}"
              f"   -> Me_sup = {crit['Me_sup']:.4f}")
        st = self.solve(p0, T0, pa)
        print(st)
        return st


# ==============================================================================
#  6. GEOMETRIES
# ==============================================================================

def conical_nozzle(R_throat: float, area_ratio: float,
                   half_angle_deg: float = 15.0,
                   conv_half_angle_deg: float = 30.0,
                   R_chamber_ratio: float = 2.5,
                   Rc_up_ratio: float = 1.5, Rc_down_ratio: float = 0.4,
                   n: int = 400) -> dict[str, np.ndarray]:
    """Contour d'une tuyere conique (col a x = 0).

    Convergent : conique + raccord circulaire de rayon Rc_up_ratio * Rt
    Divergent  : raccord circulaire Rc_down_ratio * Rt puis cone.

    Returns dict {'x', 'r', 'A', 'x_throat', 'lambda_div', 'L_div'}
    """
    Rt = float(R_throat)
    Re = Rt * math.sqrt(area_ratio)
    a = math.radians(half_angle_deg)
    ac = math.radians(conv_half_angle_deg)
    Rup, Rdn = Rc_up_ratio * Rt, Rc_down_ratio * Rt

    # --- amont : arc de raccord ------------------------------------------------
    th = np.linspace(-ac, 0.0, max(n // 5, 20))
    x_arc_up = Rup * np.sin(th)
    r_arc_up = Rt + Rup * (1.0 - np.cos(th))
    # cone convergent jusqu'a la chambre
    Rch = R_chamber_ratio * Rt
    x0, r0 = x_arc_up[0], r_arc_up[0]
    L_conv = (Rch - r0) / math.tan(ac)
    x_conv = np.linspace(x0 - L_conv, x0, max(n // 5, 20))
    r_conv = r0 + (x0 - x_conv) * math.tan(ac)

    # --- aval : arc puis cone --------------------------------------------------
    th2 = np.linspace(0.0, a, max(n // 5, 20))
    x_arc_dn = Rdn * np.sin(th2)
    r_arc_dn = Rt + Rdn * (1.0 - np.cos(th2))
    x1, r1 = x_arc_dn[-1], r_arc_dn[-1]
    L_cone = (Re - r1) / math.tan(a)
    x_cone = np.linspace(x1, x1 + L_cone, max(n // 2, 40))
    r_cone = r1 + (x_cone - x1) * math.tan(a)

    x = np.concatenate([x_conv[:-1], x_arc_up[:-1], x_arc_dn[:-1], x_cone])
    r = np.concatenate([r_conv[:-1], r_arc_up[:-1], r_arc_dn[:-1], r_cone])
    return {
        "x": x, "r": r, "A": math.pi * r ** 2, "x_throat": 0.0,
        "lambda_div": 0.5 * (1.0 + math.cos(a)),
        "L_div": float(x[-1]),
        "type": f"conique {half_angle_deg:.1f} deg",
    }


# Abaques de Rao (approximation lissee) : angles initial/final du galbe
_RAO_EPS = np.array([4.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 40.0, 50.0, 100.0])
_RAO_THN_80 = np.array([19.5, 20.5, 22.5, 23.3, 24.0, 24.6, 25.0, 25.5, 26.0, 27.4])
_RAO_THE_80 = np.array([16.0, 14.2, 11.4, 10.2, 9.5, 9.0, 8.6, 8.1, 7.7, 6.5])


def rao_angles(area_ratio: float, pct_length: float = 80.0) -> tuple[float, float]:
    """Angles de Rao (theta_n en sortie de col, theta_e en sortie) [deg].

    Approximation des abaques classiques ; correction empirique lineaire pour
    les longueurs differentes de 80 %. A verifier pour un design final.
    """
    thn = float(np.interp(area_ratio, _RAO_EPS, _RAO_THN_80))
    the = float(np.interp(area_ratio, _RAO_EPS, _RAO_THE_80))
    k = (pct_length - 80.0) / 80.0
    thn *= (1.0 - 0.55 * k)      # galbe plus court -> col plus ouvert
    the *= (1.0 + 1.10 * k)      # galbe plus court -> sortie moins alignee
    return thn, the


def bell_nozzle(R_throat: float, area_ratio: float, pct_length: float = 80.0,
                theta_n_deg: float | None = None,
                theta_e_deg: float | None = None,
                conv_half_angle_deg: float = 30.0,
                R_chamber_ratio: float = 2.5,
                n: int = 400) -> dict[str, np.ndarray]:
    """Tuyere galbee type Rao : arc de col + parabole (Bezier quadratique).

    La longueur est un pourcentage de celle d'un cone a 15 deg de meme eps.
    """
    Rt = float(R_throat)
    Re = Rt * math.sqrt(area_ratio)
    if theta_n_deg is None or theta_e_deg is None:
        tn, te = rao_angles(area_ratio, pct_length)
        theta_n_deg = tn if theta_n_deg is None else theta_n_deg
        theta_e_deg = te if theta_e_deg is None else theta_e_deg
    thn, the = math.radians(theta_n_deg), math.radians(theta_e_deg)

    L15 = (Re - Rt) / math.tan(math.radians(15.0))
    L = pct_length / 100.0 * L15

    # arc aval du col : rayon 0.382 Rt, de 0 a theta_n
    Rdn = 0.382 * Rt
    t2 = np.linspace(0.0, thn, max(n // 6, 20))
    xN = Rdn * np.sin(t2)
    rN = Rt + Rdn * (1.0 - np.cos(t2))
    Nx, Ny = xN[-1], rN[-1]
    Ex, Ey = L, Re
    if Ex <= Nx:
        raise ValueError("Longueur de galbe trop faible pour cet eps.")

    # point de controle = intersection des deux tangentes
    m1, m2 = math.tan(thn), math.tan(the)
    if abs(m1 - m2) < 1e-9:
        raise ValueError("theta_n et theta_e trop proches.")
    Qx = ((Ey - m2 * Ex) - (Ny - m1 * Nx)) / (m1 - m2)
    Qy = Ny + m1 * (Qx - Nx)

    t = np.linspace(0.0, 1.0, max(n // 2, 60))
    xB = (1 - t) ** 2 * Nx + 2 * t * (1 - t) * Qx + t ** 2 * Ex
    rB = (1 - t) ** 2 * Ny + 2 * t * (1 - t) * Qy + t ** 2 * Ey

    # convergent (identique au conique)
    ac = math.radians(conv_half_angle_deg)
    Rup = 1.5 * Rt
    th = np.linspace(-ac, 0.0, max(n // 6, 20))
    x_arc_up = Rup * np.sin(th)
    r_arc_up = Rt + Rup * (1.0 - np.cos(th))
    Rch = R_chamber_ratio * Rt
    x0, r0 = x_arc_up[0], r_arc_up[0]
    L_conv = (Rch - r0) / math.tan(ac)
    x_conv = np.linspace(x0 - L_conv, x0, max(n // 6, 20))
    r_conv = r0 + (x0 - x_conv) * math.tan(ac)

    x = np.concatenate([x_conv[:-1], x_arc_up[:-1], xN[:-1], xB])
    r = np.concatenate([r_conv[:-1], r_arc_up[:-1], rN[:-1], rB])
    return {
        "x": x, "r": r, "A": math.pi * r ** 2, "x_throat": 0.0,
        "lambda_div": 0.5 * (1.0 + math.cos(the)),
        "L_div": float(L), "theta_n": theta_n_deg, "theta_e": theta_e_deg,
        "type": f"galbee Rao {pct_length:.0f}%",
    }


# ------------------------------------------------------------------------------
#  Methode des caracteristiques (MOC) - tuyeres planes ET axisymetriques
# ------------------------------------------------------------------------------
#
#  EQUATIONS DE COMPATIBILITE (ecoulement permanent, isentropique, irrotationnel)
#  -----------------------------------------------------------------------------
#  Avec delta = 0 (plan) ou delta = 1 (axisymetrique), y etant la distance a
#  l'axe, on montre a partir de l'equation du potentiel que :
#
#     le long de C- , de pente dy/dx = tan(theta - mu) :
#         d(theta + nu) = + delta * sin(mu) sin(theta) / sin(theta - mu) * dy/y
#
#     le long de C+ , de pente dy/dx = tan(theta + mu) :
#         d(theta - nu) = - delta * sin(mu) sin(theta) / sin(theta + mu) * dy/y
#
#  En plan (delta = 0) on retrouve les invariants de Riemann K- = theta + nu et
#  K+ = theta - nu constants. En axisymetrique ils ne le sont PLUS : c'est le
#  terme source qui distingue les deux geometries.
#
#  Verification : ces relations sont satisfaites exactement par l'ecoulement
#  source spherique (solution exacte des equations axisymetriques), ou
#  theta = phi, A/A* = (r/r*)^2 ; le test est reproduit dans `check_axisymmetric
#  _compatibility()` ci-dessous.
#
#  CONSEQUENCE SUR LE TRACE DE PAROI
#  ---------------------------------
#  En plan, la region comprise entre la derniere caracteristique du col et la
#  paroi est une onde simple : l'etat est constant le long de chaque C+, ce qui
#  donne directement les points de paroi. En axisymetrique cette propriete
#  DISPARAIT, et une paroi n'apporte qu'UNE condition aux limites (l'angle) pour
#  DEUX inconnues (theta, nu) : le probleme de conception est mal pose tel quel.
#
#  On utilise donc la methode inverse classique :
#    1. NOYAU : detente centree sur le coin du col, calcule avec les processus
#       unitaires "point interieur" et "point sur l'axe" (aucune paroi requise).
#       L'angle theta_max est ajuste par dichotomie pour que le dernier point
#       axial atteigne exactement M_sortie (en plan on retrouve theta_max=nu_e/2).
#    2. CARACTERISTIQUE DE SORTIE : issue de ce point axial, elle porte un
#       ecoulement uniforme (theta = 0, M = M_e) ; c'est bien une solution, car
#       le terme source s'annule identiquement quand theta = 0.
#    3. REGION DE REDRESSEMENT : probleme de Goursat pose sur ces deux
#       caracteristiques secantes -> entierement determine sans connaitre la
#       paroi.
#    4. PAROI = LIGNE DE COURANT issue du coin du col, tracee dans ce champ
#       jusqu'a la caracteristique de sortie.
#
#  LIMITES : col a coin vif (detente centree) et ligne sonique droite au col.
#  L'ecoulement transsonique reel au col est courbe (correction de Sauer) ; pour
#  un dimensionnement definitif il faut partir d'une ligne initiale transsonique
#  et d'un arc de raccord au col.
# ------------------------------------------------------------------------------

@dataclass
class MOCPoint:
    x: float
    y: float
    theta: float     # angle de l'ecoulement [rad]
    nu: float        # fonction de Prandtl-Meyer [rad]
    M: float
    mu: float        # angle de Mach [rad]
    kind: str        # 'axis' | 'internal' | 'wall' | 'corner' | 'exit'


_AXIS_TOL = 1e-12


def _nu_inv_fast(nu: float, g: float, guess: float = 0.0) -> float:
    """Inverse nu -> M par Newton (repli sur dichotomie). Utilise en boucle MOC."""
    if nu <= 0.0:
        return 1.0
    if nu >= nu_max(g):
        raise ValueError(f"nu = {math.degrees(nu):.3f} deg depasse nu_max = "
                         f"{math.degrees(nu_max(g)):.3f} deg")
    M = guess if guess > 1.0000001 else 1.0 + math.sqrt(max(nu, 1e-9))
    for _ in range(60):
        f = prandtl_meyer(M, g) - nu
        if abs(f) < 1e-13:
            return M
        # dnu/dM = sqrt(M^2-1) / (M (1 + (g-1)/2 M^2))
        d = math.sqrt(M * M - 1.0) / (M * (1.0 + 0.5 * (g - 1.0) * M * M))
        if d <= 1e-14:
            break
        Mn = M - f / d
        if Mn <= 1.0 or not math.isfinite(Mn):
            break
        if abs(Mn - M) < 1e-14:
            return Mn
        M = Mn
    return mach_from_prandtl_meyer(nu, g)          # repli robuste


def _mk_point(x: float, y: float, theta: float, nu: float, g: float,
              kind: str, guess: float = 0.0) -> MOCPoint:
    M = _nu_inv_fast(nu, g, guess)
    return MOCPoint(x, y, theta, nu, M, mach_angle(M), kind)


def _src_minus(p: MOCPoint, delta: float) -> float:
    """Coefficient du terme source le long de C- : d(theta+nu) = S- . dy."""
    if delta == 0.0 or p.y <= _AXIS_TOL:
        return 0.0
    return delta * math.sin(p.mu) * math.sin(p.theta) / (p.y * math.sin(p.theta - p.mu))


def _src_plus(p: MOCPoint, delta: float) -> float:
    """Coefficient du terme source le long de C+ : d(theta-nu) = S+ . dy."""
    if delta == 0.0 or p.y <= _AXIS_TOL:
        return 0.0
    return -delta * math.sin(p.mu) * math.sin(p.theta) / (p.y * math.sin(p.theta + p.mu))


def _avg_src(sa: float, ya: float, sb: float, yb: float) -> float:
    """Moyenne des coefficients source ; sur l'axe le terme est indetermine
    (0/0) et on retient alors la seule valeur hors axe (schema decentre)."""
    if ya <= _AXIS_TOL:
        return sb
    if yb <= _AXIS_TOL:
        return sa
    return 0.5 * (sa + sb)


def _line_intersect(x1, y1, s1, x2, y2, s2):
    """Intersection de deux droites definies par (point, pente)."""
    if abs(s1 - s2) < 1e-14 or not (math.isfinite(s1) and math.isfinite(s2)):
        raise ValueError("caracteristiques quasi paralleles : maillage degenere")
    x = ((y2 - s2 * x2) - (y1 - s1 * x1)) / (s1 - s2)
    return x, y1 + s1 * (x - x1)


# --- processus unitaires ------------------------------------------------------

def _moc_interior(p_plus: MOCPoint, p_minus: MOCPoint, g: float, delta: float,
                  iters: int = 4) -> MOCPoint:
    """Point interieur : p_plus est amont sur C+, p_minus amont sur C-.

    Schema predicteur-correcteur : pentes et termes sources evalues en moyenne
    entre les deux extremites de chaque arc de caracteristique.
    """
    theta = 0.5 * (p_plus.theta + p_minus.theta)
    nu = 0.5 * (p_plus.nu + p_minus.nu)
    M = _nu_inv_fast(nu, g, 0.5 * (p_plus.M + p_minus.M))
    mu = mach_angle(M)
    x = y = 0.0
    for _ in range(iters):
        s_m = math.tan(0.5 * ((p_minus.theta - p_minus.mu) + (theta - mu)))
        s_p = math.tan(0.5 * ((p_plus.theta + p_plus.mu) + (theta + mu)))
        x, y = _line_intersect(p_minus.x, p_minus.y, s_m, p_plus.x, p_plus.y, s_p)
        cur = MOCPoint(x, y, theta, nu, M, mu, "tmp")
        Sm = _avg_src(_src_minus(p_minus, delta), p_minus.y,
                      _src_minus(cur, delta), y)
        Sp = _avg_src(_src_plus(p_plus, delta), p_plus.y,
                      _src_plus(cur, delta), y)
        Km = (p_minus.theta + p_minus.nu) + Sm * (y - p_minus.y)
        Kp = (p_plus.theta - p_plus.nu) + Sp * (y - p_plus.y)
        theta, nu = 0.5 * (Km + Kp), max(0.5 * (Km - Kp), 1e-10)
        M = _nu_inv_fast(nu, g, M)
        mu = mach_angle(M)
    return MOCPoint(x, y, theta, nu, M, mu, "internal")


def _moc_axis(p_minus: MOCPoint, g: float, delta: float,
              iters: int = 4) -> MOCPoint:
    """Point sur l'axe (theta = 0 par symetrie), atteint par la C- issue de p_minus."""
    theta = 0.0
    nu = p_minus.theta + p_minus.nu
    M = _nu_inv_fast(nu, g, p_minus.M)
    mu = mach_angle(M)
    x = 0.0
    Sm = _src_minus(p_minus, delta)          # indetermine sur l'axe -> decentre
    for _ in range(iters):
        s_m = math.tan(0.5 * ((p_minus.theta - p_minus.mu) + (theta - mu)))
        x = p_minus.x + (0.0 - p_minus.y) / s_m
        nu = max((p_minus.theta + p_minus.nu) + Sm * (0.0 - p_minus.y), 1e-10)
        M = _nu_inv_fast(nu, g, M)
        mu = mach_angle(M)
    return MOCPoint(x, 0.0, 0.0, nu, M, mu, "axis")


# --- noyau : detente centree sur le coin du col -------------------------------

def _moc_kernel(theta_max: float, n: int, y_t: float, g: float, delta: float):
    """Champ du noyau. Renvoie (grille pts[i][j], liste des angles du faisceau).

    pts[i][j] : j-ieme point de la i-eme C- (j = 1 sur l'axe, j = i le plus haut).
    """
    thetas = [theta_max * i / n for i in range(1, n + 1)]
    pts: list[list[MOCPoint | None]] = [[None] * (n + 2) for _ in range(n + 2)]
    for i in range(1, n + 1):
        th_i = thetas[i - 1]
        corner = _mk_point(0.0, y_t, th_i, th_i, g, "corner")
        for j in range(i, 0, -1):
            p_minus = corner if j == i else pts[i][j + 1]
            if j == 1:
                pts[i][1] = _moc_axis(p_minus, g, delta)
            else:
                pts[i][j] = _moc_interior(pts[i - 1][j - 1], p_minus, g, delta)
    return pts, thetas


def moc_nozzle(M_exit: float, n_char: int = 30, y_throat: float = 1.0,
               gamma: float = 1.4, axisymmetric: bool = True,
               max_lines: int = 4000) -> dict[str, object]:
    """Contour de tuyere a longueur minimale par la methode des caracteristiques.

    Parameters
    ----------
    M_exit       : Mach de sortie vise (uniforme et axial en sortie)
    n_char       : nombre de caracteristiques du faisceau de detente
    y_throat     : rayon au col (axisymetrique) ou demi-hauteur (plan)
    gamma        : rapport des chaleurs specifiques
    axisymmetric : True -> tuyere de revolution (delta = 1)
                   False -> tuyere plane (delta = 0)

    Returns
    -------
    dict contenant 'wall_x', 'wall_y' (contour du divergent, col en x = 0),
    'theta_max', 'area_ratio' (= (re/rt)^2 ou he/ht), 'area_ratio_theo',
    'length', ainsi que les maillages 'kernel' et 'transition' pour le trace.
    """
    if M_exit <= 1.0:
        raise ValueError("M_exit doit etre > 1")
    if n_char < 3:
        raise ValueError("n_char >= 3")
    g = gamma
    delta = 1.0 if axisymmetric else 0.0
    nu_e = prandtl_meyer(M_exit, g)

    # ---- 1) noyau : theta_max ajuste pour atteindre M_exit sur l'axe ---------
    def axis_nu(th_max: float) -> float:
        pts, _ = _moc_kernel(th_max, n_char, y_throat, g, delta)
        return pts[n_char][1].nu

    if delta == 0.0:
        theta_max = 0.5 * nu_e                      # resultat exact en plan
    else:
        lo, hi = 0.30 * nu_e, 0.5 * nu_e
        f_lo = axis_nu(lo) - nu_e
        f_hi = axis_nu(hi) - nu_e
        k = 0
        while f_lo * f_hi > 0.0 and k < 30:
            k += 1
            if f_hi < 0.0:                          # il faut ouvrir davantage
                lo, f_lo = hi, f_hi
                hi = min(hi * 1.25, 0.98 * nu_max(g))
                f_hi = axis_nu(hi) - nu_e
            else:
                hi, f_hi = lo, f_lo
                lo *= 0.75
                f_lo = axis_nu(lo) - nu_e
        if f_lo * f_hi > 0.0:
            raise ValueError("impossible d'encadrer theta_max : reduire M_exit "
                             "ou augmenter n_char")
        theta_max = _bisect(lambda t: axis_nu(t) - nu_e, lo, hi, tol=1e-12)

    pts, thetas = _moc_kernel(theta_max, n_char, y_throat, g, delta)
    e = pts[n_char][1]                              # point axial de sortie du noyau

    # ---- 2) caracteristique de sortie : ecoulement uniforme (theta = 0) ------
    mu_e = mach_angle(M_exit)
    n = n_char
    # derniere C- du noyau, ordonnee de l'axe vers le coin du col
    A: list[MOCPoint] = [pts[n][k] for k in range(1, n + 1)]
    A.append(_mk_point(0.0, y_throat, theta_max, theta_max, g, "corner"))
    m = len(A)                                      # = n + 1
    ds = float(np.mean([math.hypot(A[k].x - A[k - 1].x, A[k].y - A[k - 1].y)
                        for k in range(1, m)]))

    # ---- 3) region de redressement : probleme de Goursat ---------------------
    # Q[k][j] : C+ numero k (issue de A[k]) x C- numero j (semee sur la
    # caracteristique de sortie). k = 0 correspond a la caracteristique de sortie.
    Q: list[list[MOCPoint]] = [[A[k]] for k in range(m)]

    # ---- 4) paroi = ligne de courant issue du coin du col --------------------
    wall: list[MOCPoint] = [A[m - 1]]                # le coin lui-meme
    s_exit = math.tan(mu_e)

    def _below_exit_char(x: float, y: float) -> bool:
        return y <= e.y + s_exit * (x - e.x) + 1e-12

    j = 0
    finished = False
    while not finished and j < max_lines:
        j += 1
        # germe sur la caracteristique de sortie (etat uniforme M_exit, theta = 0)
        Q[0].append(MOCPoint(e.x + j * ds * math.cos(mu_e),
                             e.y + j * ds * math.sin(mu_e),
                             0.0, nu_e, M_exit, mu_e, "exit"))
        for k in range(1, m):
            Q[k].append(_moc_interior(Q[k][j - 1], Q[k - 1][j], g, delta))

        # intersection de la ligne de courant avec la C- numero j
        W = wall[-1]
        hit = None
        for k in range(m - 1, 0, -1):
            P, Pn = Q[k][j], Q[k - 1][j]            # segment de la C- (haut -> bas)
            th_w = W.theta
            for _ in range(3):
                sw = math.tan(th_w)
                dx, dy = Pn.x - P.x, Pn.y - P.y
                den = dy - sw * dx
                if abs(den) < 1e-14:
                    t = None
                    break
                t = (sw * (P.x - W.x) - (P.y - W.y)) / den
                if not (-1e-9 <= t <= 1.0 + 1e-9):
                    break
                th_w = 0.5 * (W.theta + (P.theta + t * (Pn.theta - P.theta)))
            if t is None or not (-1e-9 <= t <= 1.0 + 1e-9):
                continue
            t = min(max(t, 0.0), 1.0)
            xw, yw = P.x + t * dx, P.y + t * dy
            if xw < W.x - 1e-12:
                continue
            nu_w = P.nu + t * (Pn.nu - P.nu)
            th_new = P.theta + t * (Pn.theta - P.theta)
            hit = _mk_point(xw, yw, th_new, max(nu_w, 1e-10), g, "wall")
            break

        # la ligne de courant a-t-elle rejoint la caracteristique de sortie ?
        # (soit le point trouve est sous elle, soit plus aucune C- ne la coupe)
        if hit is None or _below_exit_char(hit.x, hit.y):
            th_end = W.theta if hit is None else hit.theta
            sw = math.tan(0.5 * (W.theta + th_end))
            xw, yw = _line_intersect(W.x, W.y, sw, e.x, e.y, s_exit)
            if xw < W.x - 1e-9:
                raise RuntimeError("tracage de la ligne de courant divergent")
            wall.append(_mk_point(xw, yw, 0.0, nu_e, g, "wall"))
            finished = True
        else:
            wall.append(hit)

    if not finished:
        raise RuntimeError("la ligne de courant n'a pas rejoint la "
                           "caracteristique de sortie (augmenter max_lines)")

    wall_x = np.array([w.x for w in wall])
    wall_y = np.array([w.y for w in wall])
    ar_geo = (wall_y[-1] / y_throat) ** (2.0 if axisymmetric else 1.0)
    flat = [p for row in pts for p in row if p is not None]
    flat += [p for col in Q for p in col]
    return {
        "wall_x": wall_x, "wall_y": wall_y, "wall_points": wall,
        "points": flat, "kernel": pts, "transition": Q, "thetas": thetas,
        "axisymmetric": axisymmetric,
        "theta_max": math.degrees(theta_max), "M_exit": M_exit,
        "length": float(wall_x[-1]), "y_exit": float(wall_y[-1]),
        "area_ratio": float(ar_geo),
        "area_ratio_theo": area_ratio(M_exit, g),
        "n_transition": j,
        "gamma": g, "n_char": n_char, "y_throat": y_throat,
        # compatibilite ascendante
        "area_ratio_2d": float(wall_y[-1] / y_throat),
    }


def moc_min_length_2d(M_exit: float, n_char: int = 25, y_throat: float = 1.0,
                      gamma: float = 1.4) -> dict[str, object]:
    """Alias historique : tuyere PLANE (delta = 0). Voir `moc_nozzle`."""
    return moc_nozzle(M_exit, n_char, y_throat, gamma, axisymmetric=False)


def check_axisymmetric_compatibility(M: float = 2.0, phi_deg: float = 12.0,
                                     gamma: float = 1.4) -> dict[str, float]:
    """Verifie les relations de compatibilite sur l'ecoulement source spherique.

    Dans un ecoulement source, theta = phi (angle polaire), A/A* = (r/r*)^2, d'ou
    dnu = 2 tan(mu) dr/r et, le long de C+/-, r dphi/dr = +/- tan(mu). Les
    residus renvoyes doivent etre nuls a la precision machine.
    """
    g, phi = gamma, math.radians(phi_deg)
    mu = mach_angle(M)
    tm = math.tan(mu)
    res = {}
    for eps, name in ((-1.0, "C-"), (+1.0, "C+")):
        # variations relatives pour dr/r = 1
        dtheta = eps * tm
        dnu = 2.0 * tm
        lhs = dtheta - eps * dnu                     # d(theta - eps*nu)
        dy_over_y = 1.0 + (1.0 / math.tan(phi)) * dtheta
        rhs = -eps * math.sin(mu) * math.sin(phi) / math.sin(phi + eps * mu) * dy_over_y
        res[f"residu {name}"] = lhs - rhs
    return res


# ==============================================================================
#  7. TRACES
# ==============================================================================

def _require_mpl() -> None:
    if not _HAS_MPL:
        raise RuntimeError("matplotlib n'est pas installe : "
                           "faire `pip install matplotlib`.")


def plot_nozzle_flow(geom: dict[str, np.ndarray], field: dict[str, np.ndarray],
                     title: str = "Tuyere - champ quasi-1D",
                     savefig: str | None = None):
    """4 panneaux : contour, Mach, pression, temperature."""
    _require_mpl()
    x, r = geom["x"], geom["r"]
    fig, ax = plt.subplots(4, 1, figsize=(9, 11), sharex=True)

    ax[0].plot(x * 1e3, r * 1e3, "k-", lw=2)
    ax[0].plot(x * 1e3, -r * 1e3, "k-", lw=2)
    ax[0].fill_between(x * 1e3, -r * 1e3, r * 1e3, color="0.90")
    ax[0].axhline(0, color="0.6", ls=":", lw=0.8)
    ax[0].set_ylabel("r [mm]")
    ax[0].set_title(title)
    ax[0].set_aspect("equal", adjustable="datalim")

    ax[1].plot(x * 1e3, field["M"], "b-", lw=1.8)
    ax[1].axhline(1.0, color="r", ls="--", lw=0.9, label="M = 1")
    ax[1].set_ylabel("Mach [-]")
    ax[1].legend(loc="best", fontsize=8)

    ax[2].plot(x * 1e3, field["p"] * 1e-5, "g-", lw=1.8)
    ax[2].axhline(field["state"].pa * 1e-5, color="0.4", ls="--", lw=0.9,
                  label="p ambiante")
    ax[2].set_ylabel("p [bar]")
    ax[2].legend(loc="best", fontsize=8)

    ax[3].plot(x * 1e3, field["T"], "r-", lw=1.8)
    ax[3].set_ylabel("T [K]")
    ax[3].set_xlabel("x [mm]  (col a x = 0)")

    if field.get("x_shock") is not None:
        for a in ax:
            a.axvline(field["x_shock"] * 1e3, color="m", ls="-.", lw=1.2)
        ax[1].annotate("choc droit", (field["x_shock"] * 1e3, 1.5),
                       color="m", fontsize=9, rotation=90, va="bottom")

    for a in ax:
        a.grid(alpha=0.3)
    fig.tight_layout()
    if savefig:
        fig.savefig(savefig, dpi=150)
        print(f"[ok] figure enregistree : {savefig}")
    else:
        plt.show()
    return fig


def plot_moc(res: dict[str, object], show_mesh: bool = True,
             savefig: str | None = None):
    """Trace le maillage des caracteristiques et le contour obtenu."""
    _require_mpl()
    fig, ax = plt.subplots(figsize=(10, 5))
    if show_mesh:
        grid = res["grid"]                            # type: ignore
        n = int(res["n_char"])                        # type: ignore
        yt = float(res["y_throat"])                   # type: ignore
        wall_pts: list[MOCPoint] = res["wall_points"]  # type: ignore
        # reseau C- : du coin du col vers l'axe
        for i in range(1, n + 1):
            xs = [0.0] + [grid[i][j].x for j in range(i, 0, -1)]
            ys = [yt] + [grid[i][j].y for j in range(i, 0, -1)]
            ax.plot(xs, ys, color="tab:blue", lw=0.5, alpha=0.55, zorder=1)
        # reseau C- : point axial -> ... -> paroi (segment d'annulation inclus)
        for k in range(1, n + 1):
            xs = [grid[k][1].x] + [grid[i][i - k + 1].x for i in range(k + 1, n + 1)]
            ys = [grid[k][1].y] + [grid[i][i - k + 1].y for i in range(k + 1, n + 1)]
            xs.append(wall_pts[k - 1].x)
            ys.append(wall_pts[k - 1].y)
            ax.plot(xs, ys, color="tab:red", lw=0.5, alpha=0.55, zorder=1)
        pts: list[MOCPoint] = res["points"]           # type: ignore
        sc = ax.scatter([p.x for p in pts], [p.y for p in pts],
                        s=7, c=[p.M for p in pts], cmap="viridis", zorder=3)
        cb = fig.colorbar(sc, ax=ax)
        cb.set_label("Mach local")
    ax.plot(res["wall_x"], res["wall_y"], "k-", lw=2.2, label="paroi (MOC)")
    ax.axhline(0.0, color="0.5", ls=":", lw=1.0)
    ax.set_xlabel("x / (unite de y_col)")
    ax.set_ylabel("y")
    ax.set_title(f"Tuyere plane a longueur minimale - MOC | "
                 f"Me = {res['M_exit']:.2f}, n = {res['n_char']}, "
                 f"theta_max = {res['theta_max']:.2f} deg")
    ax.legend()
    ax.grid(alpha=0.3)
    ax.set_aspect("equal", adjustable="datalim")
    fig.tight_layout()
    if savefig:
        fig.savefig(savefig, dpi=150)
        print(f"[ok] figure enregistree : {savefig}")
    else:
        plt.show()
    return fig


def plot_performance_map(noz: Nozzle, p0: float, T0: float,
                         pa_min: float, pa_max: float, n: int = 300,
                         savefig: str | None = None):
    """Poussee, Cf et Me en fonction de la pression ambiante."""
    _require_mpl()
    pas = np.linspace(pa_min, pa_max, n)
    F, cf, Me, pe = [], [], [], []
    for pa in pas:
        s = noz.solve(p0, T0, pa)
        F.append(s.thrust); cf.append(s.cf); Me.append(s.M_exit); pe.append(s.p_exit)
    crit = noz.critical_pressure_ratios()
    pa_design = p0 / crit["NPR3_adapte"]

    fig, ax = plt.subplots(3, 1, figsize=(8.5, 9), sharex=True)
    ax[0].plot(pas * 1e-5, np.array(F) * 1e-3, "b-", lw=1.8)
    ax[0].set_ylabel("Poussee [kN]")
    ax[1].plot(pas * 1e-5, cf, "g-", lw=1.8)
    ax[1].set_ylabel("Cf [-]")
    ax[2].plot(pas * 1e-5, Me, "r-", lw=1.8, label="Me")
    ax[2].set_ylabel("Mach sortie [-]")
    ax[2].set_xlabel("Pression ambiante [bar]")
    for a in ax:
        a.axvline(pa_design * 1e-5, color="m", ls="--", lw=1.0)
        a.grid(alpha=0.3)
    ax[0].annotate("adaptation", (pa_design * 1e-5, np.max(F) * 1e-3 * 0.6),
                   color="m", rotation=90, fontsize=9)
    ax[0].set_title(f"Carte de performance | p0 = {p0*1e-5:.1f} bar, eps = {noz.eps:.1f}")
    fig.tight_layout()
    if savefig:
        fig.savefig(savefig, dpi=150)
        print(f"[ok] figure enregistree : {savefig}")
    else:
        plt.show()
    return fig


# ==============================================================================
#  8. INTERFACE EN LIGNE DE COMMANDE
# ==============================================================================

def _print_table(d: dict[str, float], title: str = "") -> None:
    if title:
        print("=" * 56)
        print(f"  {title}")
        print("=" * 56)
    for k, v in d.items():
        if isinstance(v, float):
            print(f"  {k:<22s} : {v:>15.6f}")
        else:
            print(f"  {k:<22s} : {v!s:>15s}")
    print("=" * 56)


def _gas_from_args(args) -> GasModel:
    if getattr(args, "gas", None) and args.gas in GAS_LIBRARY:
        base = GAS_LIBRARY[args.gas]
        g = args.gamma if args.gamma is not None else base.gamma
        R = args.rgas if args.rgas is not None else base.R
        return GasModel(g, R, base.name)
    g = args.gamma if args.gamma is not None else 1.4
    R = args.rgas if args.rgas is not None else 287.05
    return GasModel(g, R, "personnalise")


def cmd_iso(args) -> None:
    gas = _gas_from_args(args)
    g = gas.gamma
    if args.mach is not None:
        M = args.mach
    elif args.area_ratio is not None:
        M = mach_from_area_ratio(args.area_ratio, g, args.branch)
    elif args.p0_p is not None:
        M = mach_from_p0_over_p(args.p0_p, g)
    else:
        raise SystemExit("Donner --mach, --area-ratio ou --p0-p")
    _print_table(isentropic_table(M, g),
                 f"RELATIONS ISENTROPIQUES (gamma = {g:.4f})")


def cmd_shock(args) -> None:
    gas = _gas_from_args(args)
    _print_table(normal_shock_table(args.mach, gas.gamma),
                 f"CHOC DROIT (gamma = {gas.gamma:.4f})")
    print(f"  Creation d'entropie ds = "
          f"{shock_entropy_rise(args.mach, gas):.3f} J/(kg.K)")


def cmd_oblique(args) -> None:
    gas = _gas_from_args(args)
    th_max, b_max = theta_max_oblique(args.mach, gas.gamma)
    print(f"  theta_max = {math.degrees(th_max):.3f} deg "
          f"(beta = {math.degrees(b_max):.3f} deg)")
    res = oblique_shock(args.mach, math.radians(args.theta),
                        gas.gamma, weak=not args.strong)
    _print_table(res, f"CHOC OBLIQUE (gamma = {gas.gamma:.4f})")


def cmd_pm(args) -> None:
    gas = _gas_from_args(args)
    g = gas.gamma
    if args.mach is not None:
        nu = prandtl_meyer(args.mach, g)
        M = args.mach
    else:
        nu = math.radians(args.nu)
        M = mach_from_prandtl_meyer(nu, g)
    _print_table({"M": M, "nu [deg]": math.degrees(nu),
                  "mu [deg]": math.degrees(mach_angle(M)),
                  "nu_max [deg]": math.degrees(nu_max(g))},
                 f"PRANDTL-MEYER (gamma = {g:.4f})")


def cmd_nozzle(args) -> None:
    gas = _gas_from_args(args)
    At = 0.25 * math.pi * args.dt ** 2 if args.dt else args.at
    if At is None:
        raise SystemExit("Donner --dt (diametre du col) ou --at (aire du col)")
    geom = (bell_nozzle(math.sqrt(At / math.pi), args.eps, args.pct)
            if args.type == "bell"
            else conical_nozzle(math.sqrt(At / math.pi), args.eps, args.alpha))
    noz = Nozzle(At, args.eps, gas, eta_cstar=args.eta,
                 lambda_div=geom["lambda_div"] if args.use_lambda else 1.0)
    noz.report(args.p0, args.t0, args.pa)
    print(f"  Geometrie : {geom['type']} | L_divergent = "
          f"{geom['L_div']*1e3:.1f} mm | lambda = {geom['lambda_div']:.4f}")
    if args.plot:
        field = noz.flow_field(geom["x"], geom["A"], args.p0, args.t0, args.pa)
        plot_nozzle_flow(geom, field, savefig=args.savefig)


def cmd_moc(args) -> None:
    res = moc_min_length_2d(args.me, args.n, args.rt, args.gamma or 1.4)
    print("=" * 66)
    print("  MOC - TUYERE PLANE A LONGUEUR MINIMALE")
    print("=" * 66)
    print(f"  Mach de sortie vise      : {res['M_exit']:.4f}")
    print(f"  theta_max (= nu_e / 2)   : {res['theta_max']:.4f} deg")
    print(f"  Nb de caracteristiques   : {res['n_char']}")
    print(f"  Demi-hauteur de sortie   : {res['wall_y'][-1]:.6f}")
    print(f"  Longueur du divergent    : {res['length']:.6f}")
    print(f"  Rapport h_e/h_col (2D)   : {res['area_ratio_2d']:.4f}")
    print(f"  Rapport A/A* theorique   : {res['area_ratio_theo']:.4f}  "
          f"(ecart {100*abs(res['area_ratio_2d']/res['area_ratio_theo']-1):.2f} %)")
    print("=" * 66)
    if args.export:
        np.savetxt(args.export, np.column_stack([res["wall_x"], res["wall_y"]]),
                   header="x  y  (contour paroi MOC 2D plan)", comments="# ")
        print(f"[ok] contour exporte : {args.export}")
    if args.plot:
        plot_moc(res, savefig=args.savefig)


def cmd_geom(args) -> None:
    Rt = args.rt
    geom = (bell_nozzle(Rt, args.eps, args.pct) if args.type == "bell"
            else conical_nozzle(Rt, args.eps, args.alpha))
    print(f"  Type              : {geom['type']}")
    print(f"  R_col             : {Rt*1e3:.3f} mm")
    print(f"  R_sortie          : {Rt*math.sqrt(args.eps)*1e3:.3f} mm")
    print(f"  L_divergent       : {geom['L_div']*1e3:.3f} mm")
    print(f"  lambda divergence : {geom['lambda_div']:.4f}")
    if "theta_n" in geom:
        print(f"  theta_n / theta_e : {geom['theta_n']:.2f} / {geom['theta_e']:.2f} deg")
    if args.export:
        np.savetxt(args.export, np.column_stack([geom["x"], geom["r"]]),
                   header="x [m]   r [m]", comments="# ")
        print(f"[ok] contour exporte : {args.export}")
    if args.plot:
        _require_mpl()
        fig, ax = plt.subplots(figsize=(9, 4))
        ax.plot(geom["x"] * 1e3, geom["r"] * 1e3, "k-", lw=2)
        ax.plot(geom["x"] * 1e3, -geom["r"] * 1e3, "k-", lw=2)
        ax.fill_between(geom["x"] * 1e3, -geom["r"] * 1e3, geom["r"] * 1e3,
                        color="0.9")
        ax.set_aspect("equal"); ax.grid(alpha=0.3)
        ax.set_xlabel("x [mm]"); ax.set_ylabel("r [mm]")
        ax.set_title(geom["type"])
        fig.tight_layout()
        plt.show() if not args.savefig else fig.savefig(args.savefig, dpi=150)


def cmd_demo(args) -> None:
    print("\n############ DEMO 1 : TABLES AIR, M = 2.5 ############")
    _print_table(isentropic_table(2.5, 1.4), "Isentropique")
    _print_table(normal_shock_table(2.5, 1.4), "Choc droit")

    print("\n############ DEMO 2 : TUYERE DE SOUFFLERIE ############")
    gas = GAS_LIBRARY["air"]
    noz = Nozzle.from_diameters(0.050, 0.100, gas=gas)   # eps = 4
    print(f"  eps = {noz.eps:.2f}  ->  Me_sup = {noz.M_exit_sup:.4f}")
    for pa_bar in (9.0, 6.0, 3.5, 1.013, 0.4):
        st = noz.solve(10e5, 300.0, pa_bar * 1e5)
        extra = (f" | choc a A/At = {st.area_ratio_shock:.3f}"
                 if st.area_ratio_shock else "")
        print(f"   pa = {pa_bar:6.3f} bar | NPR = {st.npr:7.3f} | "
              f"Me = {st.M_exit:5.3f} | F = {st.thrust:9.2f} N | {st.regime[:38]}{extra}")

    print("\n############ DEMO 3 : MOTEUR-FUSEE LOX/RP-1 ############")
    gas = GAS_LIBRARY["lox_rp1"]
    noz = Nozzle(A_throat=0.25 * math.pi * 0.20 ** 2, area_ratio=16.0,
                 gas=gas, eta_cstar=0.96, lambda_div=0.985)
    noz.report(p0=100e5, T0=3500.0, pa=1.013e5)
    st_vac = noz.solve(100e5, 3500.0, 1.0)
    print(f"  -> Sous vide : F = {st_vac.thrust*1e-3:.2f} kN, "
          f"Isp = {st_vac.isp:.1f} s")

    print("\n############ DEMO 4 : MOC 2D, Me = 2.4 ############")
    res = moc_min_length_2d(2.4, 20, 1.0, 1.4)
    print(f"  theta_max = {res['theta_max']:.3f} deg | "
          f"h_e/h_col = {res['area_ratio_2d']:.4f} | "
          f"theorique = {res['area_ratio_theo']:.4f}")
    print(f"  longueur = {res['length']:.4f} (en unites de demi-hauteur de col)")

    if args.plot:
        geomd = bell_nozzle(0.10, 16.0, 80.0)
        nozd = Nozzle(0.25 * math.pi * 0.20 ** 2, 16.0, GAS_LIBRARY["lox_rp1"])
        field = nozd.flow_field(geomd["x"], geomd["A"], 100e5, 3500.0, 1.013e5)
        plot_nozzle_flow(geomd, field, "Moteur LOX/RP-1 - eps = 16")
        plot_moc(res)
        plot_performance_map(nozd, 100e5, 3500.0, 1e3, 2.0e5)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nozzle_toolbox",
        description="Boite a outils quasi-1D pour le calcul des tuyeres.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemple : python nozzle_toolbox.py demo --plot",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_gas(sp):
        sp.add_argument("--gamma", type=float, default=None, help="rapport cp/cv")
        sp.add_argument("--rgas", type=float, default=None, help="R [J/kg/K]")
        sp.add_argument("--gas", type=str, default=None,
                        choices=sorted(GAS_LIBRARY), help="gaz predefini")

    s = sub.add_parser("iso", help="relations isentropiques")
    s.add_argument("--mach", type=float)
    s.add_argument("--area-ratio", type=float, dest="area_ratio")
    s.add_argument("--p0-p", type=float, dest="p0_p")
    s.add_argument("--branch", default="sub", choices=["sub", "sup"])
    add_gas(s); s.set_defaults(func=cmd_iso)

    s = sub.add_parser("shock", help="choc droit")
    s.add_argument("--mach", type=float, required=True)
    add_gas(s); s.set_defaults(func=cmd_shock)

    s = sub.add_parser("oblique", help="choc oblique (theta-beta-M)")
    s.add_argument("--mach", type=float, required=True)
    s.add_argument("--theta", type=float, required=True, help="deviation [deg]")
    s.add_argument("--strong", action="store_true", help="solution forte")
    add_gas(s); s.set_defaults(func=cmd_oblique)

    s = sub.add_parser("pm", help="fonction de Prandtl-Meyer")
    s.add_argument("--mach", type=float)
    s.add_argument("--nu", type=float, help="angle de detente [deg]")
    add_gas(s); s.set_defaults(func=cmd_pm)

    s = sub.add_parser("nozzle", help="analyse complete d'une tuyere")
    s.add_argument("--p0", type=float, required=True, help="pression totale [Pa]")
    s.add_argument("--t0", type=float, required=True, help="temperature totale [K]")
    s.add_argument("--pa", type=float, required=True, help="pression ambiante [Pa]")
    s.add_argument("--dt", type=float, help="diametre du col [m]")
    s.add_argument("--at", type=float, help="aire du col [m2]")
    s.add_argument("--eps", type=float, required=True, help="Ae/At")
    s.add_argument("--type", default="bell", choices=["bell", "conical"])
    s.add_argument("--alpha", type=float, default=15.0, help="demi-angle cone [deg]")
    s.add_argument("--pct", type=float, default=80.0, help="%% longueur galbe")
    s.add_argument("--eta", type=float, default=1.0, help="rendement c*")
    s.add_argument("--use-lambda", action="store_true", dest="use_lambda",
                   help="appliquer la perte par divergence")
    s.add_argument("--plot", action="store_true")
    s.add_argument("--savefig", type=str, default=None)
    add_gas(s); s.set_defaults(func=cmd_nozzle)

    s = sub.add_parser("moc", help="tuyere 2D plane a longueur minimale (MOC)")
    s.add_argument("--me", type=float, required=True, help="Mach de sortie")
    s.add_argument("--n", type=int, default=25, help="nb de caracteristiques")
    s.add_argument("--rt", type=float, default=1.0, help="demi-hauteur du col")
    s.add_argument("--gamma", type=float, default=1.4)
    s.add_argument("--export", type=str, default=None, help="fichier .dat du contour")
    s.add_argument("--plot", action="store_true")
    s.add_argument("--savefig", type=str, default=None)
    s.set_defaults(func=cmd_moc)

    s = sub.add_parser("geom", help="generation de contour")
    s.add_argument("--rt", type=float, required=True, help="rayon au col [m]")
    s.add_argument("--eps", type=float, required=True)
    s.add_argument("--type", default="bell", choices=["bell", "conical"])
    s.add_argument("--alpha", type=float, default=15.0)
    s.add_argument("--pct", type=float, default=80.0)
    s.add_argument("--export", type=str, default=None)
    s.add_argument("--plot", action="store_true")
    s.add_argument("--savefig", type=str, default=None)
    s.set_defaults(func=cmd_geom)

    s = sub.add_parser("demo", help="demonstration complete")
    s.add_argument("--plot", action="store_true")
    s.set_defaults(func=cmd_demo)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (ValueError, RuntimeError) as e:
        print(f"[ERREUR] {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
