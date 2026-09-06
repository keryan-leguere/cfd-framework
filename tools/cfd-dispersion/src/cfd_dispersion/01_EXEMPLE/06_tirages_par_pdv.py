#!/usr/bin/env python3
"""Parcourir les points de vol d'une sortie de modèle, et tracer ses tirages.

    python 06_tirages_par_pdv.py [--sortie SORTIE] [-n 100] [--max-tirages 15]

Le tableau de départ est celui de ``sortie_modele.py`` — un exemple **écrit en
dur** de ce qu'un modèle rend :

    4 points de vol × 100 tirages = 400 lignes

Le lot est tiré une fois et rejoué à chaque point de vol : le tirage numéro 7
est le même partout, et porte le même numéro partout.

Ce que le script montre :

  1. la sortie du modèle : ses colonnes, ses deux dictionnaires ;
  2. la **base de référence** : le même modèle, un tirage neutre, d'où viennent
     les valeurs nominales ;
  3. le parcours — un dict de points de vol, comme le ``flight_point_dict`` de
     ``batch_plot``, et une figure par (point de vol × tirage × coefficient) ;
  4. l'inventaire, et l'**accord** entre ce que le modèle a rendu et ce que le
     paquet recalcule ;
  5. à quoi ressemble un désaccord.

Quatre cents tirages font quatre cents figures par coefficient, que personne ne
regardera : ``max_tirages`` en garde quinze par point de vol — soit ici
4 × 15 = 60 tirages tracés, et 60 × (3 coefficients + 1 matrice) = 240 fichiers.

Sorties, dans SORTIE/TIRAGES/ :

    M_0.7/Z_0/tirage_000/CN.svg          les trois panneaux d'un coefficient
    M_0.7/Z_0/tirage_000/matrice.svg     les trois coefficients empilés
    …
    SORTIE/INVENTAIRE_TIRAGES.csv        ce qui a été écrit, ligne par ligne
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import matplotlib
from rich.console import Console

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cfd_dispersion import charger_lois, figure_tirage, tirage_depuis_ligne
from cfd_dispersion.figures.par_pdv import figures_tirage_par_pdv

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

from sortie_modele import (  # noqa: E402
    POINTS_DE_VOL,
    sortie_modele,
    sortie_modele_reference,
)

#: Le dictionnaire de points de vol, dans la forme du ``flight_point_dict`` de
#: ``cfd_plot.batch_plot`` : des valeurs, un libellé pour les titres, un nom
#: court pour les dossiers, et une unité.
POINTS_DE_VOL_DICT = {
    "Mach": {
        "values": sorted({point["Mach"] for point in POINTS_DE_VOL}),
        "label": "M",
        "save_name": "M",
    },
    "Altitude_m": {
        "values": sorted({point["Altitude_m"] for point in POINTS_DE_VOL}),
        "label": "Z",
        "save_name": "Z",
        "unit": " m",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE")
    parser.add_argument("-n", type=int, default=100, help="tirages par point de vol")
    parser.add_argument("--max-tirages", type=int, default=15, help="tirages tracés par PDV")
    parser.add_argument("--jobs", type=int, default=-1, help="processus (-1 = tous les cœurs)")
    args = parser.parse_args()

    console = Console()
    args.sortie.mkdir(parents=True, exist_ok=True)

    # --- 1. la sortie du modèle ----------------------------------------
    #
    # Écrite en dur dans sortie_modele.py : c'est la forme à comparer à la
    # vôtre, pas un modèle.
    df = sortie_modele(args.n)
    console.print(
        f"[bold]Sortie du modèle[/] : {len(df)} lignes "
        f"({len(POINTS_DE_VOL)} points de vol × {args.n} tirages)"
    )
    console.print(f"  colonnes : {list(df.columns)}")
    console.print(
        "  les dictionnaires voyagent dans le tableau : "
        "DICT_LAW_DISPERSION (les lois), DICT_TIRAGE (le tirage de la ligne)"
    )
    console.print(
        "  le tirage 0 est le même aux quatre points de vol : "
        f"{df.loc[df['tirage'] == 0, 'DICT_TIRAGE'].astype(str).nunique()} tirage, "
        f"{df.loc[df['tirage'] == 0, 'CN'].nunique()} coefficients dispersés"
    )

    # --- 2. la base de référence ---------------------------------------
    #
    # Le même modèle, tourné une fois avec un tirage neutre : les coefficients
    # non dispersés, un par point de vol. C'est de là que viennent les valeurs
    # nominales des figures.
    reference = sortie_modele_reference()
    neutre = dict(reference.iloc[0])["DICT_TIRAGE"]["CN"]
    console.print(f"\n[bold]Référence[/] : {len(reference)} lignes, tirage neutre {neutre}")
    console.print(
        "  "
        + reference.loc[:, ["Mach", "Altitude_m", "CN"]]
        .to_string(index=False)
        .replace("\n", "\n  ")
    )

    # --- 3. le parcours -------------------------------------------------
    #
    # Un dict de points de vol, et la fonction boucle : elle isole chaque
    # point de vol, prend ses premiers tirages, et écrit pour chacun une
    # figure par coefficient plus la matrice qui les empile.
    #
    # La colonne <coeff> du tableau principal n'est pas un nominal : c'est ce
    # que le modèle a rendu. Les figures le confrontent à leur propre calcul.
    racine = args.sortie / "TIRAGES"
    console.print(
        f"\n[bold]Parcours[/] : {len(POINTS_DE_VOL)} points de vol × "
        f"{args.max_tirages} tirages tracés"
    )

    depart = time.time()
    inventaire = figures_tirage_par_pdv(
        df,
        points_de_vol=POINTS_DE_VOL_DICT,
        racine=racine,
        reference=reference,
        max_tirages=args.max_tirages,
        nettoyer=True,
        n_jobs=args.jobs,
    )
    duree = time.time() - depart

    # --- 4. l'inventaire, et l'accord -----------------------------------
    console.print(
        f"  {len(inventaire)} fichiers en {duree:.0f} s "
        f"({inventaire['tirage'].nunique()} tirages × "
        f"{inventaire['figure'].nunique()} figures × "
        f"{len(inventaire.groupby(['Mach', 'Altitude_m']))} points de vol)"
    )
    par_pdv = inventaire.groupby(["Mach", "Altitude_m"]).size().rename("fichiers")
    console.print(par_pdv.to_string())

    # Le paquet recalcule convention(nominal, biais, FE) et le compare à la
    # colonne du modèle. Les deux doivent tomber sur le même nombre.
    verdicts = inventaire["accord"].dropna()
    console.print(
        f"  accord modèle / calcul : {int(verdicts.sum())}/{len(verdicts)} coefficients"
        + ("" if verdicts.all() else "  [red]— voir les figures en rouge[/]")
    )

    chemin = args.sortie / "INVENTAIRE_TIRAGES.csv"
    inventaire.to_csv(chemin, index=False)
    console.print(f"\n[green]écrit :[/] {chemin}")
    console.print(f"[green]figures :[/] {racine}")

    exemple = inventaire.iloc[0]["fichier"]
    console.print(f"  à regarder : {exemple}")

    # --- 5. à quoi ressemble un désaccord --------------------------------
    #
    # Une figure de plus, avec une valeur de modèle volontairement fausse de
    # 1 % : la boîte de paramètres passe au rouge et chiffre l'écart. C'est ce
    # qu'on verrait si le modèle et le paquet n'appliquaient pas la même
    # convention — l'erreur que rien d'autre ne trahit.
    premiere = dict(df.iloc[0])
    faux = figure_tirage(
        "CN",
        charger_lois(premiere["DICT_LAW_DISPERSION"])["CN"],
        tirage_depuis_ligne(premiere, ["CN"], numero=int(premiere["tirage"])),
        nominal=float(dict(reference.iloc[0])["CN"]),
        disperse_modele=float(premiere["CN"]) * 1.01,
        chemin=args.sortie / "tirage_desaccord",
    )
    plt.close(faux.figure)
    assert faux.accord is not None
    console.print(f"\n[bold]Désaccord volontaire[/] : {faux.accord.resume}")
    console.print(f"[green]écrit :[/] {faux.fichiers[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
