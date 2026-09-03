#!/usr/bin/env python3
"""Cas d'usage 2.1 et 2.2 : le modèle a-t-il tiré ce qu'on lui demandait ?

    python 02_monte_carlo.py [--sortie SORTIE]

Appelle le modèle 800 fois sur quatre points de vol, puis :

  2.1  compare, par point de vol et par coefficient, la loi prescrite à la
       loi réalisée — trois panneaux, plus un verdict ;
  2.2  synthétise en un damier, donne le taux de validation par composante,
       et **ne trace que les points de vol rejetés**.

Le modèle jouet fausse volontairement une composante à M = 0.85 (voir
``modele.py``). Un exemple où tout passe ne prouverait rien.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rich.console import Console

from cfd_dispersion import charger_lois_yaml, valider_lot
from cfd_dispersion.figures.monte_carlo import figures_par_pdv
from cfd_dispersion.figures.synthese import figure_synthese, pdv_rejetes, table_rich

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

from modele import POINTS_DE_VOL, appeler_modele, coefficients_nominaux  # noqa: E402

PAR = ("Mach", "Altitude_m")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lois", type=Path, default=ICI / "LOIS.yaml")
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE")
    parser.add_argument("-n", type=int, default=800)
    parser.add_argument(
        "--tout-tracer",
        action="store_true",
        help="tracer tous les points de vol, pas seulement les rejetés",
    )
    args = parser.parse_args()

    console = Console()
    args.sortie.mkdir(parents=True, exist_ok=True)

    lois = charger_lois_yaml(args.lois)
    console.print(f"Appel du modèle : {args.n} tirages × {len(POINTS_DE_VOL)} points de vol…")
    resultats = appeler_modele(lois, n=args.n)
    resultats.to_csv(args.sortie / "resultats_modele.csv", index=False)

    # --- 2.2 : la synthèse d'abord, pour savoir où regarder ------------
    #
    # `alpha` porte sur l'ensemble du tableau, pas sur chaque test : sans
    # cette correction, 4 points de vol × 6 composantes donneraient une ou
    # deux cases rouges par pur hasard.
    verdicts = valider_lot(resultats, lois, par=PAR)
    verdicts.to_csv(args.sortie / "verdicts.csv", index=False)

    console.print(table_rich(verdicts))

    figure, _ = figure_synthese(verdicts)
    figure.savefig(args.sortie / "synthese.png", dpi=130, bbox_inches="tight")
    plt.close(figure)
    console.print(f"[green]écrit :[/] {args.sortie / 'synthese.png'}")

    rejetes = pdv_rejetes(verdicts)
    if rejetes:
        console.print(f"[red]{len(rejetes)} point(s) de vol rejeté(s)[/] : {rejetes}")
    else:
        console.print("[green]Tous les points de vol sont validés.[/]")

    # --- 2.1 : les figures, seulement là où c'est utile ----------------
    seulement = None if args.tout_tracer else (rejetes or None)
    nominaux = {coefficient: valeur for coefficient, valeur in coefficients_nominaux(0.85).items()}

    compte = 0
    for cles, coefficient, figure in figures_par_pdv(
        resultats, lois, par=PAR, nominaux=nominaux, seulement=seulement
    ):
        etiquette = "_".join(f"{cle}{valeur:g}" for cle, valeur in cles.items())
        chemin = args.sortie / f"mc_{etiquette}_{coefficient}.png"
        figure.savefig(chemin, dpi=120, bbox_inches="tight")
        plt.close(figure)
        compte += 1
    console.print(
        f"[green]{compte} figure(s) écrite(s)[/] "
        f"({'tous les points de vol' if seulement is None else 'points de vol rejetés'})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
