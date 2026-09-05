#!/usr/bin/env python3
"""Les trois réglages qui décident de ce qu'une enveloppe veut dire.

    python 04_bande_et_correlation.py [--sortie SORTIE]

Trois questions, une figure chacune :

  1. **corrélé ou indépendant** — une même erreur sur toute la courbe, ou un
     bruit tiré point par point ? L'enveloppe sort presque identique ; ce qu'il
     y a dedans, non. Seule la version corrélée se lit « la vraie courbe est
     là-dedans » ;
  2. **quel remplissage** — min/max, percentile ou ±kσ ne recouvrent pas la
     même chose, et le troisième suppose une forme que des lois uniformes ou
     tronquées n'ont pas ;
  3. **coefficients corrélés entre eux** — deux coefficients issus du même
     recalage partagent une erreur ; le déclarer change le nuage tiré.

Sorties, dans SORTIE/ :

    correle_vs_independant.png
    remplissages.png
    correlation_coefficients.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rich.console import Console

from cfd_dispersion import (
    bande_depuis_loi,
    bande_depuis_points,
    charger_lois_yaml,
    enregistrer,
    nouvelle_figure,
    style,
    superposer_dispersion,
    tirer_tableau,
    tracer_ligne,
)

ICI = Path(__file__).resolve().parent

ALPHA = np.linspace(0.0, 12.0, 60)


def polaire(alpha: np.ndarray) -> np.ndarray:
    """Une polaire nominale quelconque, pour porter la dispersion."""
    return 0.11 * alpha + 0.0045 * alpha**2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lois", type=Path, default=ICI / "LOIS.yaml")
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE")
    parser.add_argument("-n", type=int, default=4000)
    args = parser.parse_args()

    console = Console()
    args.sortie.mkdir(parents=True, exist_ok=True)

    lois = charger_lois_yaml(args.lois)
    nominal = polaire(ALPHA)

    # --- 1. corrélé ou indépendant --------------------------------------
    with style("notebook"):
        figure, axes = nouvelle_figure(1, 2, figsize=(11.0, 4.2))
        for ax, correle in zip(np.ravel(axes), (True, False)):
            bande = bande_depuis_loi(
                ALPHA, nominal, loi=lois["CN"], n=args.n, correle=correle, graine=3
            )
            for realisation in bande.echantillons[:40]:
                tracer_ligne(ax, ALPHA, realisation, color="C0", alpha=0.15, lw=0.6, marker="")
            tracer_ligne(ax, ALPHA, bande.bas, color="C0", lw=1.0, ls="--", marker="")
            tracer_ligne(ax, ALPHA, bande.haut, color="C0", lw=1.0, ls="--", marker="")
            tracer_ligne(ax, ALPHA, nominal, color="0.2", lw=1.4, marker="", label="nominal")
            ax.set_title(
                "corrélé — une erreur par courbe" if correle else "indépendant — un bruit par point"
            )
            ax.set_xlabel(r"$\alpha$ [°]")
            ax.set_ylabel(r"$C_N$ [-]")
            console.print(
                f"  {'corrélé   ' if correle else 'indépendant'} : "
                f"demi-largeur moyenne {bande.demi_largeur.mean():.4f}"
            )
        (chemin,) = enregistrer(figure, args.sortie / "correle_vs_independant", formats=("png",))
        plt.close(figure)
    console.print(f"[green]écrit :[/] {chemin}")

    # --- 2. les trois remplissages ---------------------------------------
    with style("notebook"):
        figure, axes = nouvelle_figure(1, 3, figsize=(14.0, 4.2))
        # 95 % pour le percentile, ±2σ pour la version gaussienne : les deux se
        # comparent alors sur la même intention. `minmax` n'a pas de niveau du
        # tout — et le lui en passer un est refusé, plutôt qu'ignoré en silence.
        for ax, remplissage in zip(np.ravel(axes), ("minmax", "percentile", "sigma")):
            tracer_ligne(ax, ALPHA, nominal, label="CFD", color="C0", marker="")
            superposer_dispersion(
                ax,
                ALPHA,
                nominal,
                loi=lois["CN"],
                serie="CFD",
                remplissage=remplissage,
                sigmas=(),
                boite_parametres=False,
                n=args.n,
                graine=3,
                couverture=0.95 if remplissage == "percentile" else None,
                k=2.0 if remplissage == "sigma" else None,
            )
            ax.set_title(f"remplissage = {remplissage!r}")
            ax.set_xlabel(r"$\alpha$ [°]")
            ax.set_ylabel(r"$C_N$ [-]")
        (chemin,) = enregistrer(figure, args.sortie / "remplissages", formats=("png",))
        plt.close(figure)
    console.print(f"[green]écrit :[/] {chemin}")

    # --- 3. deux coefficients issus du même recalage ---------------------
    #
    # Nommer deux COEFFICIENTS corrèle leurs composantes de même nature :
    # biais avec biais, FE avec FE. Appliquer un même ρ aux quatre croisements
    # donnerait une matrice non définie positive.
    liees = charger_lois_yaml(args.lois, correlation={("CN", "Cm_alpha"): 0.85})
    console.print(f"  indépendantes : {lois.independantes} → {liees.independantes}")

    with style("notebook"):
        figure, axes = nouvelle_figure(1, 2, figsize=(11.0, 4.6))
        for ax, jeu, nom in zip(np.ravel(axes), (lois, liees), ("indépendants", "ρ = 0.85")):
            lot = tirer_tableau(jeu, 1500, graine=5, methode="lhs")
            ax.scatter(lot["CN_Biais"], lot["Cm_alpha_Biais"], s=4, alpha=0.35, color="C0")
            correlation = float(np.corrcoef(lot["CN_Biais"], lot["Cm_alpha_Biais"])[0, 1])
            ax.set_title(f"{nom} — corrélation mesurée {correlation:+.2f}")
            ax.set_xlabel("biais de CN")
            ax.set_ylabel("biais de Cm_alpha")
            console.print(f"  {nom:<14} corrélation mesurée {correlation:+.3f}")
        (chemin,) = enregistrer(figure, args.sortie / "correlation_coefficients", formats=("png",))
        plt.close(figure)
    console.print(f"[green]écrit :[/] {chemin}")

    # --- 4. une dispersion propre à chaque point --------------------------
    #
    # `bande_depuis_points` prend une loi PAR point du balayage : le cas d'une
    # incertitude qui s'ouvre avec l'incidence, par exemple.
    par_point = [lois["CN"] if a < 6.0 else lois["Cm_alpha"] for a in ALPHA]
    bande = bande_depuis_points(ALPHA, nominal, par_point, n=args.n, graine=3)
    console.print(
        "  bande_depuis_points : demi-largeur "
        f"{bande.demi_largeur[0]:.4f} au début, {bande.demi_largeur[-1]:.4f} à la fin"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
