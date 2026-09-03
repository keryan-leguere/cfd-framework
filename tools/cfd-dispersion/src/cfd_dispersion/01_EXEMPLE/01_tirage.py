#!/usr/bin/env python3
"""Cas d'usage 1 : tirer les lois, et regarder ce qui a été tiré.

    python 01_tirage.py [--sortie SORTIE]

Produit, dans SORTIE/ :

    tirage_<coefficient>.png   trois panneaux par coefficient :
                               la loi du biais, celle du FE, et la
                               reconstruction du coefficient
    lot.csv                    1000 tirages, prêts à alimenter un modèle
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rich.console import Console

from cfd_dispersion import charger_lois_yaml, tirer, tirer_lot
from cfd_dispersion.figures.tirage import figure_tirage
from cfd_dispersion.report.console import table_lois, table_tirage

ICI = Path(__file__).resolve().parent

#: Valeurs nominales des coefficients, telles qu'un modèle les fournirait.
NOMINAUX = {"CN": 0.85, "CA": 0.032, "Cm_alpha": -2.5}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lois", type=Path, default=ICI / "LOIS.yaml")
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE")
    parser.add_argument("--graine", type=int, default=42)
    parser.add_argument("-n", type=int, default=1000)
    args = parser.parse_args()

    console = Console()
    args.sortie.mkdir(parents=True, exist_ok=True)

    lois = charger_lois_yaml(args.lois)
    console.print(table_lois(lois))

    # --- un tirage, et sa figure ---------------------------------------
    tirage = tirer(lois, graine=args.graine)
    console.print(table_tirage(tirage))

    disperses = tirage.appliquer(NOMINAUX)
    for nom, valeur in disperses.items():
        console.print(f"  {nom} : {NOMINAUX[nom]:+.5g} → {float(valeur):+.5g}")

    for coefficient in lois:
        figure, _ = figure_tirage(
            coefficient, lois[coefficient], tirage, nominal=NOMINAUX[coefficient]
        )
        chemin = args.sortie / f"tirage_{coefficient}.png"
        figure.savefig(chemin, dpi=130, bbox_inches="tight")
        plt.close(figure)
        console.print(f"[green]écrit :[/] {chemin}")

    # --- un lot, pour alimenter le modèle ------------------------------
    # Le plan LHS remplit mieux l'espace des six composantes que le
    # Monte-Carlo brut, à effectif égal.
    lot = tirer_lot(lois, args.n, graine=args.graine, methode="lhs")
    chemin = args.sortie / "lot.csv"
    lot.to_csv(chemin, index=False)
    console.print(f"[green]écrit :[/] {chemin}  ({len(lot)} tirages, plan LHS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
