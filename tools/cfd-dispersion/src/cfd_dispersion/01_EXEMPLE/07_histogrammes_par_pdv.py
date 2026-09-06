#!/usr/bin/env python3
"""L'ensemble des tirages d'un point de vol, en histogrammes.

    python 07_histogrammes_par_pdv.py [--sortie SORTIE] [-n 100]

Même tableau de départ qu'au script 06 — `sortie_modele.py`, 4 points de vol ×
100 tirages — et même dictionnaire de points de vol. Ce qui change est la
question posée :

    06  « qu'est-ce qu'UN tirage fait à mon coefficient ? »
        -> une figure par tirage, 15 tirages par point de vol

    07  « qu'est-ce que les CENT tirages ont donné ? »
        -> une figure par point de vol et par coefficient, tous les tirages

Les trois panneaux sont les mêmes, mais remplis autrement : l'histogramme de ce
qui a été **obtenu**, superposé à la loi qui le **prescrivait**.

  1. le biais obtenu sur les n tirages, contre sa loi ;
  2. le facteur d'échelle, de même ;
  3. le coefficient tel que le modèle l'a rendu, contre la loi combinée.

Ce que le script montre :

  1. le parcours ordinaire, sur les quatre points de vol ;
  2. le cas où lois et sorties ne parlent pas des mêmes coefficients — et il se
     comporte autrement qu'au script 06, c'est tout l'intérêt ;
  3. le refus d'un tableau croisé, où l'histogramme n'aurait pas de sens.

Sorties, dans SORTIE/HISTOGRAMMES/ :

    M_0.7/Z_0/CN.svg          les trois histogrammes d'un coefficient
    M_0.7/Z_0/matrice.svg     les trois coefficients empilés
    …
    SORTIE/INVENTAIRE_HISTOGRAMMES.csv   ce qui a été écrit
    SORTIE/HISTOGRAMMES_DECALES/…        lois sur CX0, sortie sur CA

Chez vous
---------
Les deux mêmes lignes qu'au script 06 :

    df = sortie_modele(args.n)             -> votre tableau de sortie
    reference = sortie_modele_reference()  -> le même modèle, tirage neutre
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import matplotlib
import pandas as pd
from rich.console import Console

# Agg : on dessine dans des fichiers, pas dans des fenêtres.
matplotlib.use("Agg")

from cfd_dispersion import figures_histogramme_par_pdv

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

# Le dict de points de vol du script 06, repris tel quel : les deux parcours
# lisent la même chose et écrivent la même arborescence, seule la figure
# change. `import_module` plutôt qu'un `import` ordinaire : un nom de module
# qui commence par un chiffre n'est pas un identifiant Python valide.
from importlib import import_module  # noqa: E402

from sortie_modele import (  # noqa: E402
    POINTS_DE_VOL,
    sortie_modele,
    sortie_modele_reference,
)

_TIRAGES = import_module("06_tirages_par_pdv")
POINTS_DE_VOL_DICT = _TIRAGES.POINTS_DE_VOL_DICT
renommer_dans_les_dicts = _TIRAGES.renommer_dans_les_dicts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE")
    parser.add_argument("-n", type=int, default=100, help="tirages par point de vol")
    parser.add_argument("--jobs", type=int, default=-1, help="processus (-1 = tous les cœurs)")
    args = parser.parse_args()

    console = Console()
    args.sortie.mkdir(parents=True, exist_ok=True)

    # --- 1. le parcours -------------------------------------------------
    #
    # Le même tableau et la même référence qu'au script 06.
    df = sortie_modele(args.n)
    reference = sortie_modele_reference()

    console.print(
        f"[bold]Sortie du modèle[/] : {len(df)} lignes "
        f"({len(POINTS_DE_VOL)} points de vol × {args.n} tirages)"
    )

    # `figures_histogramme_par_pdv` a la même signature que son jumeau du
    # script 06, à deux choses près :
    #
    #   * pas de `max_tirages` : l'histogramme les prend TOUS, c'est son objet ;
    #   * il écrit une figure par (point de vol × coefficient), soit ici
    #     4 × 3 = 12, plus 4 matrices — contre 240 au script 06.
    #
    # Le reste est identique : le dict de points de vol, la référence d'où
    # viennent les nominaux, l'arborescence, l'inventaire rendu.
    racine = args.sortie / "HISTOGRAMMES"
    depart = time.time()
    inventaire = figures_histogramme_par_pdv(
        df,
        points_de_vol=POINTS_DE_VOL_DICT,
        racine=racine,
        reference=reference,
        nettoyer=True,
        n_jobs=args.jobs,
    )
    duree = time.time() - depart

    console.print(
        f"\n[bold]Parcours[/] : {len(inventaire)} fichiers en {duree:.0f} s "
        f"({inventaire['tirages'].iloc[0]} tirages par point de vol)"
    )
    console.print(
        "  "
        + inventaire.groupby(["Mach", "Altitude_m"])
        .size()
        .rename("fichiers")
        .to_string()
        .replace("\n", "\n  ")
    )

    chemin = args.sortie / "INVENTAIRE_HISTOGRAMMES.csv"
    inventaire.to_csv(chemin, index=False)
    console.print(f"\n[green]écrit :[/] {chemin}")
    console.print(f"  à regarder : {inventaire.iloc[0]['fichier']}")
    console.print(
        "  le troisième panneau confronte l'histogramme obtenu à la loi combinée\n"
        "  prescrite : si le modèle disperse plus que demandé, cela se voit là."
    )

    # --- 2. lois et sorties décalées -------------------------------------
    #
    # Le même cas qu'au script 06 — les lois parlent de CX0, la sortie de CA —
    # mais l'histogramme s'en tire mieux, et c'est la raison d'être de cette
    # figure :
    #
    #   CX0  a des lois mais aucune colonne : ses deux premiers panneaux sont
    #        pleins (le biais et le FE ont bien été tirés cent fois), et le
    #        troisième dit que le modèle ne rend pas ce coefficient ;
    #   CA   a une colonne mais aucune loi : ses deux premiers panneaux le
    #        disent, et le TROISIÈME EST TRACÉ QUAND MÊME — on a bien cent
    #        valeurs obtenues, et leur histogramme est déjà la moitié de la
    #        réponse. Le script 06, lui, ne pouvait montrer de CA que le
    #        nominal et une valeur.
    #
    # Il faut nommer CA explicitement : par défaut, le parcours ne trace que
    # les coefficients que les lois décrivent.
    console.print("\n[bold]Lois et sorties décalées[/] : lois sur CX0, sortie sur CA")
    df_decale = renommer_dans_les_dicts(df, "CA", "CX0")
    reference_decale = renommer_dans_les_dicts(reference, "CA", "CX0")

    inventaire_decale = figures_histogramme_par_pdv(
        df_decale,
        points_de_vol={
            "Mach": {"values": [0.85], "label": "M", "save_name": "M"},
            "Altitude_m": {"values": [10_000.0], "label": "Z", "save_name": "Z", "unit": " m"},
        },
        racine=args.sortie / "HISTOGRAMMES_DECALES",
        reference=reference_decale,
        coefficients=["CN", "CX0", "CA"],
        nettoyer=True,
        n_jobs=1,
    )
    console.print(f"  {len(inventaire_decale)} fichiers : {list(inventaire_decale['figure'])}")
    console.print(
        "  CN  : les trois panneaux — lois et sortie\n"
        "  CX0 : biais et FE obtenus ; pas de colonne, donc pas de troisième panneau\n"
        "  CA  : pas de loi, mais l'histogramme obtenu est bien là"
    )

    # --- 3. ce que l'histogramme refuse ----------------------------------
    #
    # Un histogramme suppose UNE LIGNE PAR TIRAGE. Si le modèle a été appelé en
    # croisé — le même tirage rejoué à sept incidences — chaque valeur apparaît
    # sept fois et l'histogramme du coefficient mélange le balayage et la
    # dispersion. Un histogramme faux se lit comme un vrai : le parcours le
    # refuse, en nommant la colonne à ajouter au point de vol.
    console.print("\n[bold]Un tableau croisé[/] : ce que l'histogramme refuse")
    croise = pd.concat([df.assign(alpha=alpha) for alpha in (0.0, 5.0, 10.0)], ignore_index=True)
    try:
        figures_histogramme_par_pdv(
            croise,
            points_de_vol=POINTS_DE_VOL_DICT,
            racine=args.sortie / "CROISE",
            reference=reference,
        )
    except ValueError as erreur:
        console.print(f"  [red]{erreur}[/]")
    console.print(
        "  le remède : ajouter alpha aux points de vol — un histogramme par\n"
        "  incidence — ou ne garder qu'une ligne par tirage."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
