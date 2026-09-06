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

Chez vous
---------
Deux lignes à remplacer, et deux seulement :

    df = sortie_modele(args.n)             -> votre tableau de sortie
    reference = sortie_modele_reference()  -> le même modèle, tirage neutre

Tout le reste — le dict de points de vol, l'appel au parcours, l'inventaire —
s'écrit pareil. Le paquet ne demande à votre tableau que quatre choses : les
colonnes de point de vol, une colonne par coefficient, le tirage de chaque
ligne (``DICT_TIRAGE``, ou les colonnes ``<coeff>_Biais`` / ``<coeff>_FE``) et
les lois (``DICT_LAW_DISPERSION``, ou un ``lois=`` passé à la main).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import matplotlib
from rich.console import Console

# Agg = « dessine dans un fichier, n'ouvre pas de fenêtre ». À poser AVANT
# d'importer pyplot, sinon Matplotlib a déjà choisi son afficheur — et sur une
# machine de calcul sans écran, il échoue.
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cfd_dispersion import charger_lois, figure_tirage, tirage_depuis_ligne
from cfd_dispersion.figures.par_pdv import figures_tirage_par_pdv

ICI = Path(__file__).resolve().parent

# `sortie_modele.py` est le fichier d'à côté, pas un paquet installé : sans
# cette ligne, Python ne le trouverait qu'en lançant le script depuis son
# propre dossier. Chez vous, c'est votre modèle qu'on importe ici — ou rien du
# tout, si vous relisez un CSV déjà écrit.
sys.path.insert(0, str(ICI))

from sortie_modele import (  # noqa: E402
    POINTS_DE_VOL,
    sortie_modele,
    sortie_modele_reference,
)

#: Le dictionnaire de points de vol : **quelles colonnes du tableau font un
#: point de vol, et quelles valeurs y retenir**. C'est la forme du
#: ``flight_point_dict`` de ``cfd_plot.batch_plot``, à l'identique.
#:
#: Une entrée par colonne. Chacune porte :
#:
#:   values     les valeurs à parcourir. Omises, ce sont toutes celles que
#:              porte le tableau. En donner moins est la façon de ne tracer
#:              qu'une partie de l'étude.
#:   label      le nom court dans les TITRES de figure : « M = 0.85 ».
#:   save_name  le nom court dans les DOSSIERS : « M_0.85/ ».
#:   unit       l'unité, accolée à la valeur dans les titres : « Z = 10000 m ».
#:
#: Le produit des valeurs donne les points de vol : 2 Mach × 2 altitudes = 4.
#: Une clé à valeur unique ne crée pas de dossier — elle n'apprendrait rien.
POINTS_DE_VOL_DICT = {
    "Mach": {
        # `{point["Mach"] for point in POINTS_DE_VOL}` est un *ensemble* : il
        # dédoublonne les Mach de la liste des points de vol. Trié, cela donne
        # [0.70, 0.85]. Écrire la liste en dur marcherait tout aussi bien.
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
    # vôtre, pas un modèle. Une ligne par (point de vol × tirage), donc
    # 4 × 100 = 400 lignes, portant :
    #
    #   Mach, Altitude_m ........ le point de vol
    #   cas, maillage, solveur .. vos métadonnées, que le paquet ne lit pas
    #                             mais ne perd pas
    #   CN, CA, Cm_alpha ........ les coefficients DISPERSÉS, ce que le modèle
    #                             a calculé avec le tirage de la ligne
    #   DICT_LAW_DISPERSION ..... la table de lois, recopiée sur chaque ligne
    #   DICT_TIRAGE ............. le tirage appliqué à cette ligne
    #   tirage .................. son numéro
    #
    # Chez vous : `df = pd.read_csv("SORTIE_MODELE.csv")` fait aussi bien.
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
    # Vérification de ce qui vient d'être dit : sur les quatre lignes qui
    # portent le tirage n° 0 — une par point de vol — il n'y a qu'UN tirage
    # distinct, mais QUATRE coefficients différents, puisque le nominal change
    # d'un point de vol à l'autre.
    #
    #   df.loc[condition, "colonne"]  la colonne, restreinte aux lignes qui
    #                                 vérifient la condition
    #   .nunique()                    combien de valeurs distinctes
    #   .astype(str)                  un dict ne se compare pas tel quel : on
    #                                 le compare par son écriture
    console.print(
        "  le tirage 0 est le même aux quatre points de vol : "
        f"{df.loc[df['tirage'] == 0, 'DICT_TIRAGE'].astype(str).nunique()} tirage, "
        f"{df.loc[df['tirage'] == 0, 'CN'].nunique()} coefficients dispersés"
    )

    # --- 2. la base de référence ---------------------------------------
    #
    # Le même modèle, tourné une fois avec un tirage NEUTRE — biais 0 et FE 1
    # pour la convention linéaire — donc sans dispersion : ses coefficients
    # sont les valeurs nominales, une ligne par point de vol.
    #
    # C'est le seul endroit d'où les figures peuvent tirer un nominal : la
    # colonne CN du tableau principal, elle, change à chaque tirage — c'est la
    # sortie dispersée, pas une référence.
    #
    # Chez vous : lancez votre modèle une fois avec `tirage_neutre(lois)` et
    # gardez le tableau. Le facteur neutre dépend de la convention (1 en
    # linéaire, 0 en pourcentage), d'où cette fonction plutôt qu'un 1 écrit à
    # la main.
    reference = sortie_modele_reference()

    # `reference.iloc[0]` = la première ligne ; `dict(...)` la transforme en
    # dictionnaire ordinaire, pour lire une colonne qui contient elle-même un
    # dictionnaire sans que pandas s'en mêle.
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
    # LA fonction du script. Pour chaque point de vol du dict, elle :
    #
    #   1. isole les lignes du tableau qui le concernent (ici 100) ;
    #   2. y prend les `max_tirages` premiers tirages (ici 15) ;
    #   3. lit la valeur nominale de chaque coefficient dans `reference` ;
    #   4. écrit, pour chacun de ces tirages, une figure par coefficient
    #      (CN.svg, CA.svg, Cm_alpha.svg) plus la matrice qui les empile
    #      (matrice.svg), dans TIRAGES/M_0.85/Z_10000/tirage_003/ ;
    #   5. referme chaque figure aussitôt écrite — il y en a des centaines.
    #
    # Les arguments qui comptent :
    #
    #   points_de_vol  le dict ci-dessus : que parcourir
    #   racine         où écrire ; l'arborescence se déploie dessous
    #   reference      d'où viennent les valeurs nominales
    #   max_tirages    combien de tirages tracer par point de vol (None = tous)
    #   nettoyer       vider l'arborescence avant d'écrire, pour ne pas
    #                  mélanger deux exécutions
    #   n_jobs         -1 = tous les cœurs. Une figure coûte une demi-seconde à
    #                  écrire, et il y en a 240 : une minute au lieu de quatre.
    #
    # Ce qu'elle rend n'est pas une figure mais un INVENTAIRE : un tableau
    # d'une ligne par fichier écrit, dont on se sert juste après.
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
    #
    # L'inventaire ressemble à ceci, une ligne par fichier :
    #
    #   Mach  Altitude_m  tirage  figure   fichier        calcul  modele  ecart  accord
    #   0.85     10000.0       0  CN       …/CN.svg       0.8325  0.8325    0.0    True
    #   0.85     10000.0       0  matrice  …/matrice.svg     NaN     NaN    NaN     NaN
    #
    # `calcul` / `modele` / `ecart` / `accord` ne sont remplis que sur les
    # lignes de coefficient : une matrice en empile trois, elle n'a pas un
    # verdict mais trois.
    console.print(
        f"  {len(inventaire)} fichiers en {duree:.0f} s "
        f"({inventaire['tirage'].nunique()} tirages × "
        f"{inventaire['figure'].nunique()} figures × "
        f"{len(inventaire.groupby(['Mach', 'Altitude_m']))} points de vol)"
    )
    # `groupby([...]).size()` = combien de lignes par point de vol.
    par_pdv = inventaire.groupby(["Mach", "Altitude_m"]).size().rename("fichiers")
    console.print(par_pdv.to_string())

    # Le contrôle qui porte sur le MODÈLE et non sur le tirage : le paquet
    # recalcule convention(nominal, biais, FE) et le compare à la colonne du
    # modèle. Les deux doivent tomber sur le même nombre ; sinon c'est une
    # convention différente de part et d'autre, une référence que le modèle n'a
    # jamais vue, ou une dispersion appliquée ailleurs qu'on ne croit.
    #
    #   .dropna()  écarte les lignes de matrice, qui n'ont pas de verdict
    #   .sum()     sur des booléens, compte les True
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
    # Une figure de plus, hors parcours, avec une valeur de modèle
    # volontairement fausse de 1 % : la boîte de paramètres passe au rouge et
    # chiffre l'écart. C'est ce qu'on verrait si le modèle et le paquet
    # n'appliquaient pas la même convention — l'erreur que rien d'autre ne
    # trahit.
    #
    # C'est aussi l'occasion de voir ce que le parcours fait en boucle,
    # déplié sur une seule ligne du tableau. Une figure de tirage demande
    # quatre choses :
    #
    #   1. le nom du coefficient ;
    #   2. ses deux lois — relues du tableau, personne ne redonne le YAML ;
    #   3. le tirage de la ligne, reconstruit par `tirage_depuis_ligne` ;
    #   4. la valeur nominale, prise dans la référence.
    #
    # `disperse_modele` est ce que le modèle a rendu ; ici on le fausse.
    premiere = dict(df.iloc[0])
    faux = figure_tirage(
        "CN",
        charger_lois(premiere["DICT_LAW_DISPERSION"])["CN"],
        tirage_depuis_ligne(premiere, ["CN"], numero=int(premiere["tirage"])),
        nominal=float(dict(reference.iloc[0])["CN"]),
        disperse_modele=float(premiere["CN"]) * 1.01,
        chemin=args.sortie / "tirage_desaccord",
    )
    # La figure s'est écrite toute seule (`chemin=`) ; il reste à la fermer,
    # et à lire le verdict qu'elle porte.
    plt.close(faux.figure)
    assert faux.accord is not None
    console.print(f"\n[bold]Désaccord volontaire[/] : {faux.accord.resume}")
    console.print(f"[green]écrit :[/] {faux.fichiers[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
