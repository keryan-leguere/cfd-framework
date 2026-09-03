#!/usr/bin/env python3
"""Cas d'usage 2.1 et 2.2 : le modèle a-t-il tiré ce qu'on lui demandait ?

    python 02_monte_carlo.py [--sortie SORTIE] [-n 800] [--tout-tracer]

Appelle le modèle 800 fois sur quatre points de vol, puis :

  2.1  compare, par point de vol et par coefficient, la loi prescrite à la
       loi réalisée — trois panneaux, plus un verdict ;
  2.2  synthétise en un damier, donne le taux de validation par composante,
       et **ne trace que les points de vol rejetés**.

Le modèle jouet fausse volontairement une composante à M = 0.85 (voir
``modele.py``) : la demi-étendue y est prise pour un écart-type, donc doublée.
Un exemple où tout passe ne prouverait rien.

Sorties, dans SORTIE/ :

    resultats_modele.csv   la sortie du modèle, au format attendu (§5.4 des docs)
    verdicts.csv           un verdict par (point de vol × coefficient × composante)
    synthese.csv           le taux de validation par composante
    synthese.png           le damier
    mc_<pdv>_<coeff>.png   les trois panneaux, pour les points de vol rejetés
    qq_<pdv>_<coeff>.png   les mêmes en quantile-quantile, plus net dans les queues
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rich.console import Console

from cfd_dispersion import (
    charger_lois_yaml,
    enregistrer,
    figure_synthese,
    figures_par_pdv,
    pdv_rejetes,
    synthese,
    table_rich,
    valider_lot,
)

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

from modele import POINTS_DE_VOL, appeler_modele, coefficients_nominaux  # noqa: E402

#: Les colonnes qui définissent un point de vol dans la sortie du modèle.
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

    # Le contrat de colonnes, celui que votre modèle doit honorer.
    console.print(f"colonnes rendues : {sorted(resultats.columns)}\n")

    # --- 2.2 : la synthèse d'abord, pour savoir où regarder ------------
    #
    # `alpha` porte sur l'ensemble du tableau, pas sur chaque test : sans
    # cette correction, 4 points de vol × 6 composantes donneraient une ou
    # deux cases rouges par pur hasard.
    verdicts = valider_lot(resultats, lois, par=PAR)
    verdicts.to_csv(args.sortie / "verdicts.csv", index=False)

    console.print(table_rich(verdicts))

    resume = synthese(verdicts)
    resume.to_csv(args.sortie / "synthese.csv", index=False)
    console.print("\n[bold]Taux de validation, par composante[/]")
    # Colonne par colonne, et non `itertuples` : les stubs pandas typent les
    # champs d'un NamedTuple en Any/bytes, et le formatage passe alors en
    # `b'CN'` sans que rien ne le signale.
    for ligne in resume.to_dict("records"):
        motifs = str(ligne["motifs"])
        detail = f"  ({motifs})" if motifs else ""
        nom = f"{ligne['coefficient']}_{ligne['composante']}"
        console.print(
            f"  {nom:<16} {float(ligne['taux_validation']):5.1f} % validés "
            f"sur {int(ligne['n_pdv'])} PDV{detail}"
        )

    figure, _ = figure_synthese(verdicts)
    (chemin,) = enregistrer(figure, args.sortie / "synthese", formats=("png",))
    plt.close(figure)
    console.print(f"[green]écrit :[/] {chemin}")

    rejetes = pdv_rejetes(verdicts)
    if rejetes:
        console.print(f"[red]{len(rejetes)} point(s) de vol rejeté(s)[/] : {rejetes}")
    else:
        console.print("[green]Tous les points de vol sont validés.[/]")

    # --- 2.1 : les figures, seulement là où c'est utile ----------------
    #
    # `seulement=` prend exactement ce que rend `pdv_rejetes` : sur cinquante
    # points de vol et six composantes, on ne regarde pas trois cents figures.
    seulement = None if args.tout_tracer else (rejetes or None)
    nominaux = coefficients_nominaux(0.85)

    compte = 0
    for qq, prefixe in ((False, "mc"), (True, "qq")):
        for cles, coefficient, figure in figures_par_pdv(
            resultats, lois, par=PAR, nominaux=nominaux, seulement=seulement, qq=qq
        ):
            etiquette = "_".join(f"{cle}{valeur:g}" for cle, valeur in cles.items())
            (chemin,) = enregistrer(
                figure, args.sortie / f"{prefixe}_{etiquette}_{coefficient}", formats=("png",)
            )
            plt.close(figure)
            compte += 1

    console.print(
        f"[green]{compte} figure(s) écrite(s)[/] "
        f"({'tous les points de vol' if seulement is None else 'points de vol rejetés'}, "
        f"densité et quantile-quantile)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
