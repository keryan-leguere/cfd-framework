#!/usr/bin/env python3
"""Cas d'usage 1 : tirer les lois, et regarder ce qui a été tiré.

    python 01_tirage.py [--sortie SORTIE] [-n 1000]

Ce que le script montre, dans l'ordre :

  1. charger une table de lois — depuis un dict Python, puis depuis LOIS.yaml ;
  2. tirer une réalisation : c'est le ``DICT_DISP_DRAWN`` du modèle ;
  3. reconstruire le coefficient dispersé sous les quatre conventions ;
  4. la loi du coefficient dispersé, biais et FE combinés ;
  5. les figures, qui s'écrivent d'elles-mêmes ;
  6. tirer un lot de mille : la liste de tirages à donner au modèle ;
  7. le même lot à plat, et les trois plans d'échantillonnage compares.

Sorties, dans SORTIE/ :

    tirage_<coefficient>.svg   trois panneaux : biais, FE, coefficient dispersé
    tirage_sans_nominal.svg    le même, sans valeur nominale : deux panneaux sur trois
    tirage_matrice.svg         une ligne de trois par coefficient
    tirage_pagine_01.svg …     la même, paginée (deux coefficients par figure)
    lot.csv                    le lot à plat, une ligne par tirage

Les figures s'écrivent d'elles-mêmes : ``chemin=`` suffit, et le fichier sort
en SVG par le gabarit d'export de cfd-plot.
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
    MAX_COEFFICIENTS_PAR_FIGURE,
    Convention,
    charger_lois,
    charger_lois_yaml,
    figure_tirage,
    figure_tirage_matrice,
    loi_combinee,
    tableau_des_tirages,
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


def convention_saturee(c: Any, biais: Any, fe: Any) -> np.ndarray:
    """Une relation **non affine** en (biais, FE) : le FE y sature.

    C'est le cas où la loi du coefficient dispersé n'a pas de forme fermée —
    et où le paquet bascule sur un gros tirage LHS lissé par noyau.
    """
    fe = np.asarray(fe, dtype=float)
    return np.asarray(biais + fe * c / (1.0 + np.abs(fe)), dtype=float)


SATUREE = Convention(
    nom="saturee",
    formule="biais + FE · c / (1 + |FE|)",
    appliquer=convention_saturee,
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
    maisons = {MAISON.nom: MAISON, SATUREE.nom: SATUREE}
    for nom in (*CONVENTIONS, *maisons):
        relation = maisons.get(nom) or CONVENTIONS[nom]
        disperses = tirage.appliquer(NOMINAUX, convention_=relation)
        detail = "  ".join(
            f"{coefficient} {float(valeur):+.5g}" for coefficient, valeur in disperses.items()
        )
        console.print(f"  {nom:<12} {relation.formule:<28} {detail}")
    console.print(
        f"  {'nominal':<12} {'':<28} " + "  ".join(f"{k} {v:+.5g}" for k, v in NOMINAUX.items())
    )

    # --- 4. la loi du coefficient dispersé ------------------------------
    #
    # Le troisième panneau des figures ne montre pas un histogramme : la loi
    # du coefficient, biais et FE combinés, est calculée. Exactement quand la
    # relation est affine à nominal fixé — le cas des conventions livrées —
    # sinon lissée sur un gros tirage LHS.
    console.print("\n[bold]La loi du coefficient dispersé[/]")
    for coefficient, nominal in NOMINAUX.items():
        combinee = loi_combinee(lois[coefficient], nominal)
        relatif = combinee.pourcent(combinee.M_theorique + combinee.ET_theorique)
        console.print(
            f"  {coefficient:<10} nominal {nominal:+.5g}  "
            f"σ {combinee.ET_theorique:.5g} ({abs(relatif or 0.0):.2f} %)  "
            f"{combinee.methode}"
        )
    # Une relation maison reste affine en (biais, FE) tant que le FE n'y
    # apparaît qu'au premier degré : la voie exacte tient. Sinon, le paquet
    # bascule tout seul sur un tirage LHS lissé — et le dit.
    for relation in (MAISON, SATUREE):
        combinee = loi_combinee(lois["CN"], NOMINAUX["CN"], convention_=relation)
        console.print(f"  {relation.nom:<10} {relation.formule:<28} {combinee.methode}")

    # --- 5. les figures ------------------------------------------------
    #
    # Tracer et écrire ne font qu'un appel : `chemin=` suffit. Le fichier
    # passe par cfd_plot.save_figure — DPI, marges et fond viennent du profil
    # de style, comme pour toute figure du framework.
    for coefficient in lois:
        rendue = figure_tirage(
            coefficient,
            lois[coefficient],
            tirage,
            nominal=NOMINAUX[coefficient],
            chemin=args.sortie / f"tirage_{coefficient}",
        )
        plt.close(rendue.figure)
        console.print(f"[green]écrit :[/] {rendue.fichiers[0]}")

    # `nominal` est facultatif : sans lui, les deux panneaux de composantes
    # sont tracés comme d'habitude et le troisième reste vide en disant ce qui
    # lui manque — la loi du coefficient dispersé se calcule en un point.
    rendue = figure_tirage("CN", lois["CN"], tirage, chemin=args.sortie / "tirage_sans_nominal")
    plt.close(rendue.figure)
    console.print(f"[green]écrit :[/] {rendue.fichiers[0]}  (sans valeur nominale)")

    (page,) = figure_tirage_matrice(
        lois, tirage, nominaux=NOMINAUX, chemin=args.sortie / "tirage_matrice"
    )
    plt.close(page.figure)
    console.print(f"[green]écrit :[/] {page.fichiers[0]}")

    # Au-delà de MAX_COEFFICIENTS_PAR_FIGURE (quatre) coefficients, la matrice
    # passe à la figure suivante et numérote les fichiers d'elle-même. Forcé
    # ici à deux par page, faute d'assez de coefficients pour le montrer
    # autrement.
    console.print(f"  (défaut : {MAX_COEFFICIENTS_PAR_FIGURE} coefficients par figure)")
    for page in figure_tirage_matrice(
        lois,
        tirage,
        nominaux=NOMINAUX,
        chemin=args.sortie / "tirage_pagine",
        max_par_figure=2,
    ):
        plt.close(page.figure)
        console.print(f"[green]écrit :[/] {page.fichiers[0]}  {list(page.coefficients)}")

    # --- 6. le lot : n tirages, un par appel du modèle -------------------
    #
    # `tirer_lot` rend la LISTE des tirages, pas un tableau : chaque élément
    # est le dictionnaire que votre modèle attend. Aucun modèle n'est appelé
    # ici — seulement l'interface, pour montrer ce qu'on lui passerait.
    lot = tirer_lot(lois, args.n, graine=args.graine, methode="lhs")
    console.print(f"\n[bold]Le lot : {len(lot)} tirages[/]  (type : {type(lot).__name__})")

    for tirage_i in lot[:3]:
        # `tirage_i` EST le DICT_DISP_DRAWN : un Mapping {coeff: {Biais, FE}}.
        # C'est lui qu'on passerait au modèle, tel quel :
        #
        #     resultats.append(mon_modele(L_MACH, L_ALPHA, tirage_i))
        #
        console.print(
            f"  tirage {tirage_i.numero:<3} "
            f"CN {tirage_i['CN']['Biais']:+.5f} / {tirage_i['CN']['FE']:.5f}   "
            f"vu du modèle : {dict(tirage_i['CA'])}"
        )
    console.print(f"  … et {len(lot) - 3} autres, numérotés jusqu'à {lot[-1].numero}")

    # Chaque tirage porte de quoi se décrire : la convention, le plan, la
    # graine du lot et son propre rang. C'est ce que les figures impriment.
    console.print(f"  résumé du dernier : {lot[-1].resume}")

    # Deux façons d'obtenir les n tirages, et ce qui les sépare :
    #
    #   for i in range(n): tirer(lois, graine=graine + i)   -> n tirages MC
    #   tirer_lot(lois, n, graine=graine, methode="lhs")    -> un plan conjoint
    #
    # La boucle donne bien n tirages Monte-Carlo indépendants, mais aucun plan
    # ne peut y améliorer le remplissage : chaque tirage ignore les autres.
    boucle = [tirer(lois, graine=args.graine + i) for i in range(3)]
    console.print(
        "  en boucle sur la graine : " + "  ".join(f"CN_FE {t['CN']['FE']:.5f}" for t in boucle)
    )

    # --- 7. le lot à plat, et les trois plans ---------------------------
    #
    # Pour un CSV ou une statistique, `tableau_des_tirages` remet le lot à
    # plat ; `tirer_tableau` fait les deux d'un coup.
    console.print("\n[bold]Les trois plans d'échantillonnage[/]")
    for methode in ("mc", "lhs", "sobol"):
        table = tableau_des_tirages(tirer_lot(lois, args.n, graine=args.graine, methode=methode))
        # Le plus gros trou laissé dans le support d'une composante : c'est
        # ce que LHS et Sobol améliorent, à effectif égal.
        rangs = np.sort(table["CN_FE"].to_numpy())
        trou = float(np.max(np.diff(rangs)))
        console.print(
            f"  {methode:<6} moyenne {table['CN_FE'].mean():+.5f}  "
            f"écart-type {table['CN_FE'].std(ddof=1):.5f}  plus grand trou {trou:.5f}"
        )
        if methode == "lhs":
            chemin = args.sortie / "lot.csv"
            table.to_csv(chemin, index=False)
            console.print(f"  [green]écrit :[/] {chemin}  ({len(table)} tirages, plan LHS)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
