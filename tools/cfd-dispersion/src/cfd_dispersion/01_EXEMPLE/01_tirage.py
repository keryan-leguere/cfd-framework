#!/usr/bin/env python3
"""Cas d'usage 1 : tirer les lois, et regarder ce qui a été tiré.

    python 01_tirage.py [--sortie SORTIE] [-n 1000]

Ce que le script montre, dans l'ordre :

  1. charger une table de lois — depuis un dict Python, puis depuis LOIS.yaml ;
  2. tirer une réalisation : c'est le ``DICT_DISP_DRAWN`` du modèle ;
  3. reconstruire le coefficient dispersé sous les quatre conventions ;
  4. la figure en trois panneaux, par coefficient puis en matrice ;
  5. tirer un lot de mille, et comparer les trois plans d'échantillonnage.

Sorties, dans SORTIE/ :

    tirage_<coefficient>.png   trois panneaux : biais, FE, reconstruction
    tirage_matrice.png         une ligne de trois par coefficient
    lot.csv                    le lot, prêt à alimenter un modèle
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from rich.console import Console

from cfd_dispersion import (
    CONVENTIONS,
    Convention,
    charger_lois,
    charger_lois_yaml,
    enregistrer,
    figure_tirage,
    figure_tirage_matrice,
    tirer,
    tirer_lot,
)
from cfd_dispersion.report.console import table_lois, table_tirage

ICI = Path(__file__).resolve().parent

#: Valeurs nominales des coefficients, telles qu'un modèle les fournirait.
NOMINAUX = {"CN": 0.85, "CA": 0.032, "Cm_alpha": -2.5}

#: La même table qu'en YAML, écrite en Python. C'est le format d'entrée du
#: paquet : une entrée par coefficient, six clés chacune.
DICT_DISP_LAWS = {
    "CN": {
        "Biais_Type": 5,  # Gaussienne ±3σ
        "Biais_M": 0.0,
        "Biais_ET": 0.02,  # DEMI-ÉTENDUE : σ = 0.01
        "FE_Type": 6,  # Gaussienne ±2σ
        "FE_M": 1.0,  # facteur neutre pour la convention `lineaire`
        "FE_ET": 0.08,
    },
}


def convention_maison(c: Any, biais: Any, fe: Any) -> np.ndarray:
    """Une relation à soi — fonction de niveau module, donc sérialisable.

    Une ``lambda`` marcherait ici, mais ne passerait pas le hook de
    ``batch_plot``, qui sérialise tout ce qu'on lui donne.
    """
    return np.asarray(biais + fe * c * (1.0 + 0.1 * c), dtype=float)


MAISON = Convention(
    nom="maison",
    formule="biais + FE · c · (1 + 0.1·c)",
    appliquer=convention_maison,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lois", type=Path, default=ICI / "LOIS.yaml")
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE")
    parser.add_argument("--graine", type=int, default=42)
    parser.add_argument("-n", type=int, default=1000)
    args = parser.parse_args()

    console = Console()
    args.sortie.mkdir(parents=True, exist_ok=True)

    # --- 1. charger ----------------------------------------------------
    #
    # Les deux chemins donnent le même objet ; le YAML se relit à six mois.
    depuis_dict = charger_lois(DICT_DISP_LAWS)
    console.print(f"depuis un dict Python : {depuis_dict['CN'].resume}")

    lois = charger_lois_yaml(args.lois)
    console.print(table_lois(lois))
    console.print(f"composantes : {list(lois.colonnes)}\nindépendantes : {lois.independantes}\n")

    # --- 2. tirer ------------------------------------------------------
    #
    # `Tirage` EST un Mapping : il se passe tel quel au modèle qui attend
    # {coeff: {"Biais": …, "FE": …}}. Rien à convertir.
    tirage = tirer(lois, graine=args.graine)
    console.print(table_tirage(tirage))
    console.print(f"vu du modèle : {tirage['CN']}")

    # --- 3. reconstruire -----------------------------------------------
    #
    # Rien dans une figure ne trahit qu'on s'est trompé de convention : la
    # courbe reste lisse et l'ordre de grandeur reste crédible.
    console.print("\n[bold]Le coefficient dispersé, convention par convention[/]")
    for nom in (*CONVENTIONS, MAISON.nom):
        relation = MAISON if nom == MAISON.nom else CONVENTIONS[nom]
        disperses = tirage.appliquer(NOMINAUX, convention_=relation)
        detail = "  ".join(
            f"{coefficient} {float(valeur):+.5g}" for coefficient, valeur in disperses.items()
        )
        console.print(f"  {nom:<12} {relation.formule:<28} {detail}")
    console.print(
        f"  {'nominal':<12} {'':<28} " + "  ".join(f"{k} {v:+.5g}" for k, v in NOMINAUX.items())
    )

    # --- 4. les figures ------------------------------------------------
    for coefficient in lois:
        figure, _ = figure_tirage(
            coefficient, lois[coefficient], tirage, nominal=NOMINAUX[coefficient]
        )
        # `enregistrer` passe par cfd_plot.save_figure : DPI, marges et fond
        # viennent du profil de style, comme pour toute figure du framework.
        (chemin,) = enregistrer(figure, args.sortie / f"tirage_{coefficient}", formats=("png",))
        plt.close(figure)
        console.print(f"[green]écrit :[/] {chemin}")

    figure, _ = figure_tirage_matrice(lois, tirage, nominaux=NOMINAUX)
    (chemin,) = enregistrer(figure, args.sortie / "tirage_matrice", formats=("png",))
    plt.close(figure)
    console.print(f"[green]écrit :[/] {chemin}")

    # --- 5. le lot, et les trois plans ---------------------------------
    console.print("\n[bold]Les trois plans d'échantillonnage[/]")
    for methode in ("mc", "lhs", "sobol"):
        lot = tirer_lot(lois, args.n, graine=args.graine, methode=methode)
        # Le plus gros trou laissé dans le support d'une composante : c'est
        # ce que LHS et Sobol améliorent, à effectif égal.
        rangs = np.sort(lot["CN_FE"].to_numpy())
        trou = float(np.max(np.diff(rangs)))
        console.print(
            f"  {methode:<6} moyenne {lot['CN_FE'].mean():+.5f}  "
            f"écart-type {lot['CN_FE'].std(ddof=1):.5f}  plus grand trou {trou:.5f}"
        )
        if methode == "lhs":
            chemin = args.sortie / "lot.csv"
            lot.to_csv(chemin, index=False)
            console.print(f"  [green]écrit :[/] {chemin}  ({len(lot)} tirages, plan LHS)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
