#!/usr/bin/env python3
"""Génère les figures illustrant 00_DOC/ dans 00_DOC/FIGURES/.

    python 00_DOC/generer_figures.py

Les figures sont volontairement autonomes du reste du package : elles servent
la documentation, pas le rapport terminal.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

from cfd_nozzle._compat import zip_strict

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from cfd_nozzle import (
    GAS_LIBRARY,
    Nozzle,
    area_ratio,
    bell_contour,
    conical_contour,
    moc_nozzle,
    p0_over_p,
    prandtl_meyer,
)
from cfd_nozzle.core.geometry import NozzleContour
from cfd_nozzle.core.isentropic import mach_from_area_ratio, t0_over_t
from cfd_nozzle.core.shocks import (
    nu_max,
    shock_m2,
    shock_p0_ratio,
    shock_p_ratio,
    shock_rho_ratio,
)
from cfd_nozzle.report.figures import plot_flow_field, plot_moc, plot_performance_map

FIGURES = Path(__file__).resolve().parent / "FIGURES"
GAMMA = 1.4


def _save(fig: plt.Figure, name: str) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    path = FIGURES / f"{name}.png"
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"[ok] {path}")


def figure_isentropique() -> None:
    """Rapports isentropiques et les deux racines de A/A*."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    mach = np.linspace(0.05, 4.0, 400)

    axes[0].plot(mach, [1.0 / t0_over_t(float(m), GAMMA) for m in mach], label="T/T₀")
    axes[0].plot(mach, [1.0 / p0_over_p(float(m), GAMMA) for m in mach], label="p/p₀")
    axes[0].plot(
        mach,
        [(1.0 / t0_over_t(float(m), GAMMA)) ** (1.0 / (GAMMA - 1.0)) for m in mach],
        label="ρ/ρ₀",
    )
    axes[0].axvline(1.0, color="0.5", ls=":", lw=1.0)
    axes[0].set_xlabel("Mach")
    axes[0].set_ylabel("rapport aux conditions d'arrêt")
    axes[0].set_title("Rapports isentropiques (γ = 1.4)")
    axes[0].legend()
    axes[0].grid(alpha=0.3)

    axes[1].plot(mach, [area_ratio(float(m), GAMMA) for m in mach], color="#1f77b4")
    axes[1].axvline(1.0, color="0.5", ls=":", lw=1.0)
    axes[1].axhline(1.0, color="0.5", ls=":", lw=1.0)
    eps = 4.0
    for branch, colour in (("sub", "#2ca02c"), ("sup", "#d62728")):
        m = mach_from_area_ratio(eps, GAMMA, branch)  # type: ignore[arg-type]
        axes[1].plot([m], [eps], "o", color=colour, ms=8)
        axes[1].annotate(
            f"branche {branch}\nM = {m:.3f}",
            (m, eps),
            textcoords="offset points",
            xytext=(10, 12),
            color=colour,
            fontsize=9,
        )
    axes[1].axhline(eps, color="0.7", ls="--", lw=0.9)
    axes[1].set_ylim(0.8, 12.0)
    axes[1].set_xlabel("Mach")
    axes[1].set_ylabel("A/A*")
    axes[1].set_title("A/A* : minimum à M = 1, donc deux racines pour tout ε > 1")
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    _save(fig, "01_relations_isentropiques")


def figure_chocs() -> None:
    """Sauts du choc droit et fonction de Prandtl-Meyer."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    m1 = np.linspace(1.0, 5.0, 300)

    axes[0].plot(m1, [shock_p_ratio(float(m), GAMMA) for m in m1], label="p₂/p₁")
    axes[0].plot(m1, [shock_rho_ratio(float(m), GAMMA) for m in m1], label="ρ₂/ρ₁")
    axes[0].plot(m1, [shock_m2(float(m), GAMMA) for m in m1], label="M₂")
    axes[0].plot(m1, [shock_p0_ratio(float(m), GAMMA) for m in m1], label="p₀₂/p₀₁")
    limit = (GAMMA + 1.0) / (GAMMA - 1.0)
    axes[0].axhline(limit, color="#d62728", ls="--", lw=0.9)
    axes[0].annotate(
        f"ρ₂/ρ₁ → (γ+1)/(γ−1) = {limit:.0f}",
        (3.0, limit),
        textcoords="offset points",
        xytext=(0, 6),
        color="#d62728",
        fontsize=9,
    )
    axes[0].axhline(1.0, color="0.5", ls=":", lw=0.9)
    axes[0].set_xlabel("M₁")
    axes[0].set_ylabel("rapport [-]")
    axes[0].set_title("Choc droit : M₂ < 1 toujours, p₀ toujours perdue")
    axes[0].legend(fontsize=9)
    axes[0].grid(alpha=0.3)

    for gamma, colour in ((1.4, "#1f77b4"), (1.22, "#ff7f0e")):
        machs = np.linspace(1.0, 8.0, 300)
        axes[1].plot(
            machs,
            [math.degrees(prandtl_meyer(float(m), gamma)) for m in machs],
            color=colour,
            label=f"ν(M), γ = {gamma}",
        )
        axes[1].axhline(math.degrees(nu_max(gamma)), color=colour, ls="--", lw=0.9)
        axes[1].annotate(
            f"ν_max = {math.degrees(nu_max(gamma)):.1f}°",
            (6.5, math.degrees(nu_max(gamma))),
            textcoords="offset points",
            xytext=(0, -14),
            color=colour,
            fontsize=9,
        )
    axes[1].set_xlabel("Mach")
    axes[1].set_ylabel("ν [°]")
    axes[1].set_title("Prandtl-Meyer : un γ plus faible tourne davantage")
    axes[1].legend(fontsize=9)
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    _save(fig, "02_chocs_detentes")


def figure_regimes() -> None:
    """Les cinq régimes le long de l'axe, et la carte de poussée."""
    gas = GAS_LIBRARY["air"]
    nozzle = Nozzle(0.01, 4.0, gas)
    contour = bell_contour(math.sqrt(0.01 / math.pi), 4.0)
    critical = nozzle.critical_ratios()
    p0, t0 = 10e5, 300.0

    cas = [
        (p0 / (1.0 + 0.5 * (critical.npr_choked - 1.0)), "venturi"),
        (p0 / (0.5 * (critical.npr_choked + critical.npr_shock_at_exit)), "choc interne"),
        (p0 / (0.5 * (critical.npr_shock_at_exit + critical.npr_design)), "sur-détendue"),
        (p0 / critical.npr_design, "adaptée"),
        (p0 / (3.0 * critical.npr_design), "sous-détendue"),
    ]

    fig, axes = plt.subplots(2, 1, figsize=(10, 8.5), sharex=False)
    # The three supersonic regimes share the same interior solution: once the
    # exit is supersonic, the back pressure cannot reach back inside. Drawing
    # them with decreasing widths keeps all three visible on top of each other,
    # which is the point rather than an artefact.
    styles = [
        ("#7f7f7f", "-", 1.8),
        ("#d62728", "-", 1.8),
        ("#ff7f0e", "-", 4.0),
        ("#2ca02c", "--", 2.6),
        ("#1f77b4", ":", 1.6),
    ]
    for (pa, label), (colour, dash, width) in zip_strict(cas, styles):
        field = nozzle.flow_field(contour.x, contour.area, p0, t0, pa)
        axes[0].plot(
            field.x * 1e3, field.p * 1e-5, color=colour, ls=dash, lw=width, label=label, alpha=0.9
        )
    axes[0].axvline(0.0, color="0.6", ls=":", lw=1.0)
    axes[0].annotate("col", (0.0, 9.2), fontsize=9, color="0.4")
    axes[0].annotate(
        "les 3 régimes supersoniques\nont le MÊME champ interne :\npa ne remonte pas dans la tuyère",
        (0.45, 0.42),
        xycoords="axes fraction",
        fontsize=8.5,
        color="0.35",
    )
    axes[0].set_ylabel("p [bar]")
    axes[0].set_xlabel("x [mm]   (col à x = 0)")
    axes[0].set_title("Les cinq régimes — pression le long de l'axe (air, ε = 4, p₀ = 10 bar)")
    axes[0].legend(fontsize=9)
    axes[0].grid(alpha=0.3)

    pressures = np.linspace(1e3, 0.98 * p0, 400)
    thrust = np.array([nozzle.solve(p0, t0, float(pa)).thrust for pa in pressures])
    axes[1].plot(pressures * 1e-5, thrust * 1e-3, color="#1f77b4", lw=1.8)
    for npr, name, colour in (
        (critical.npr_choked, "NPR₁", "#7f7f7f"),
        (critical.npr_shock_at_exit, "NPR₂", "#d62728"),
        (critical.npr_design, "NPR₃", "#2ca02c"),
    ):
        axes[1].axvline(p0 / npr * 1e-5, color=colour, ls="--", lw=1.1)
        axes[1].annotate(
            name,
            (p0 / npr * 1e-5, float(thrust.max()) * 1e-3 * 0.5),
            color=colour,
            rotation=90,
            fontsize=9,
            textcoords="offset points",
            xytext=(4, 0),
        )
    axes[1].set_xlabel("Pression ambiante [bar]")
    axes[1].set_ylabel("Poussée [kN]")
    axes[1].set_title("Poussée et NPR critiques")
    axes[1].grid(alpha=0.3)

    fig.tight_layout()
    _save(fig, "03_regimes_tuyere")


def figure_geometries() -> None:
    """Cône, galbe et MOC pour un même ε, plus la convergence du MOC."""
    # Le contour occupe sa propre rangée : à l'échelle (aspect égal), un
    # divergent est six fois plus long que haut et n'entre pas dans une demi-
    # largeur sans laisser l'essentiel de la case vide.
    fig, axes = plt.subplots(2, 1, figsize=(11, 8.0))

    # ε = 8 : assez grand pour que l'abaque de Rao donne θe < 15°, donc pour que
    # le galbe batte réellement le cône — ce qui n'est plus vrai vers ε = 4 —
    # et assez petit pour que le M_sortie visé (3.66) reste dans le domaine
    # validé du MOC axisymétrique.
    rt, eps = 1.0, 8.0
    cone = conical_contour(rt, eps, 15.0)
    bell = bell_contour(rt, eps, 80.0)
    moc = moc_nozzle(mach_from_area_ratio(eps, GAMMA, "sup"), 40, rt, GAMMA, axisymmetric=True)

    axes[0].plot(cone.x, cone.r, color="#7f7f7f", lw=2, label=f"cône 15° (λ = {cone.divergence_lambda:.3f})")
    axes[0].plot(bell.x, bell.r, color="#1f77b4", lw=2, label=f"galbe 80 % (λ = {bell.divergence_lambda:.3f})")
    axes[0].plot(moc.wall_x, moc.wall_y, color="#d62728", lw=2, label="MOC axisymétrique")
    axes[0].axhline(0.0, color="0.6", ls=":", lw=0.9)
    axes[0].set_xlabel("x / R_col")
    axes[0].set_ylabel("r / R_col")
    axes[0].set_title(f"Trois divergents pour ε = {eps:g}")
    axes[0].set_aspect("equal", adjustable="box")
    axes[0].set_ylim(0.0, 1.15 * max(cone.r.max(), bell.r.max(), moc.wall_y.max()))
    axes[0].legend(fontsize=9, loc="lower right")
    axes[0].grid(alpha=0.3)

    for axisymmetric, colour, label in ((False, "#1f77b4", "plane"), (True, "#d62728", "axisymétrique")):
        counts = [10, 15, 20, 30, 45, 60]
        errors = [
            100.0 * moc_nozzle(2.4, n, 1.0, GAMMA, axisymmetric=axisymmetric).area_ratio_error
            for n in counts
        ]
        axes[1].loglog(counts, errors, "o-", color=colour, label=label)
    axes[1].set_xlabel("n_char (nombre de caractéristiques du faisceau)")
    axes[1].set_ylabel("écart au ε théorique [%]")
    axes[1].set_title("Convergence du MOC (M_sortie = 2.4)")
    axes[1].legend(fontsize=9)
    axes[1].grid(alpha=0.3, which="both")

    fig.tight_layout()
    _save(fig, "04_geometries")


# --------------------------------------------------------------------------
#  Figures « résultat » : la sortie réelle des fonctions de report.figures,
#  telle qu'on l'obtient avec --figure. Elles illustrent le README.
# --------------------------------------------------------------------------


def _moteur_demo() -> tuple[Nozzle, NozzleContour]:
    """Le moteur LOX/RP-1 de 01_EXEMPLE/CAS_MOTEUR.yaml."""
    gas = GAS_LIBRARY["lox_rp1"]
    contour = bell_contour(0.10, 16.0, 80.0)
    nozzle = Nozzle(
        0.25 * math.pi * 0.20**2,
        16.0,
        gas,
        eta_cstar=0.96,
        lambda_div=contour.divergence_lambda,
    )
    return nozzle, contour


def figure_resultat_champ() -> None:
    """Sortie de `cfd-nozzle run … --figure` : le champ quasi-1D."""
    nozzle, contour = _moteur_demo()
    field = nozzle.flow_field(contour.x, contour.area, 100e5, 3500.0, 1.013e5)
    fig = plot_flow_field(contour, field, title="MOTEUR_DEMO_LOX_RP1 — champ quasi-1D")
    _save(fig, "05_resultat_champ")


def figure_resultat_choc() -> None:
    """Le même tracé quand un choc droit se tient dans le divergent."""
    nozzle = Nozzle(0.03, 4.0, GAS_LIBRARY["air"])
    contour = bell_contour(math.sqrt(0.03 / math.pi), 4.0)
    field = nozzle.flow_field(contour.x, contour.area, 10e5, 300.0, 6e5)
    fig = plot_flow_field(contour, field, title="Choc droit dans le divergent (air, ε = 4)")
    _save(fig, "06_resultat_choc_interne")


def figure_resultat_carte() -> None:
    """Sortie de `--figure` : la carte de performance en pression ambiante."""
    nozzle, _ = _moteur_demo()
    # Jusqu'à 20 bar : assez haut pour traverser NPR₂ et faire apparaître le
    # régime à choc interne sur le panneau du Mach de sortie.
    fig = plot_performance_map(nozzle, 100e5, 3500.0, 1e3, 20.0e5, n=300)
    _save(fig, "07_resultat_carte_performance")


def figure_resultat_moc() -> None:
    """Sortie de `cfd-nozzle moc … --figure` : maillage et paroi."""
    fig = plot_moc(moc_nozzle(2.4, 30, 1.0, GAMMA, axisymmetric=True))
    _save(fig, "08_resultat_moc")


def main() -> int:
    figure_isentropique()
    figure_chocs()
    figure_regimes()
    figure_geometries()
    figure_resultat_champ()
    figure_resultat_choc()
    figure_resultat_carte()
    figure_resultat_moc()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
