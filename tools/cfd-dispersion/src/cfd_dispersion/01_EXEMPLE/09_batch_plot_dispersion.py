#!/usr/bin/env python3
"""Le lot de polaires de ``batch_plot``, dispersé par un hook.

    python 09_batch_plot_dispersion.py [--sortie SORTIE] [-n 120]

C'est la jonction entre les deux moitiés du framework : ``cfd_plot.batch_plot``
produit les polaires d'une étude — une figure par (coefficient × point de vol)
— et ``cfd_dispersion`` y ajoute la dispersion, sans qu'aucune des deux ne
sache quoi que ce soit de l'autre.

Le partage est simple, et c'est tout l'intérêt :

    configuration_dict={"CFD": {"df": df_reference}}   ->  les COURBES
    on_before_save=hook_dispersion_tableau(df_disperse) ->  la DISPERSION

Le tableau de référence est le modèle tourné **une fois** avec un tirage neutre
(biais 0, FE 1) : c'est le nominal, donc les courbes. Le tableau dispersé est
le même modèle tourné **n fois** : c'est le faisceau, l'enveloppe et les σ.
Aucun des deux n'est mis en forme à la main — le hook découpe lui-même le
tableau dispersé point de vol par point de vol, du même filtre que
``batch_plot`` a employé pour la référence.

Ce que le script montre, dans l'ordre :

  1. les deux tableaux, tels que le modèle les rend ;
  2. les quatre dictionnaires de ``batch_plot``, écrits au complet ;
  3. le lot ordinaire, une ligne de code pour la dispersion ;
  4. les options d'affichage, sur un second lot ;
  5. la bande théorique en plus du nuage obtenu (``lois=``) ;
  6. la figure de comparaison, où le hook est appelé une fois par panneau ;
  7. la vérification de ce qui a été écrit.

Nécessite cfd-plot :  pip install -e tools/cfd-plot
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import matplotlib

# Agg : on écrit des fichiers, pas des fenêtres.
matplotlib.use("Agg")

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

from cfd_dispersion import JeuDeLois, charger_lois_yaml, tirage_neutre
from cfd_dispersion.batch import hook_dispersion_tableau

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

from modele import appeler_modele_polaire  # noqa: E402

#: Le balayage en incidence, commun à tous les points de vol.
ALPHA = np.linspace(-2.0, 18.0, 21)

#: Les points de vol de l'étude. `batch_plot` en fait une figure chacun.
POINTS_DE_VOL: tuple[dict[str, float], ...] = (
    {"Mach": 0.70, "Altitude_m": 5000.0},
    {"Mach": 0.80, "Altitude_m": 8000.0},
    {"Mach": 0.85, "Altitude_m": 10000.0},
)

SYMBOLES = {"CN": r"$C_N$", "CA": r"$C_A$", "Cm_alpha": r"$C_{m_\alpha}$"}
NOMS = {
    "CN": "Coefficient normal",
    "CA": "Coefficient axial",
    "Cm_alpha": "Gradient de moment de tangage",
}


# ---------------------------------------------------------------------------
# 1. les deux tableaux
# ---------------------------------------------------------------------------


def tourner_le_modele(lois: JeuDeLois, n: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Les deux appels du modèle : n tirages, puis un tirage neutre.

    Les deux tableaux ont **exactement la même forme** — mêmes colonnes, mêmes
    points de vol, même balayage — et c'est ce qui fait tenir tout le reste :
    le hook filtre le dispersé comme ``batch_plot`` filtre la référence.

    ============================ ==========================================
    ``Mach``, ``Altitude_m``      les clés de point de vol
    ``alpha``                     le balayage, l'abscisse des figures
    ``CN``, ``CA``, ``Cm_alpha``  les coefficients — dispersés ou nominaux
    ``tirage``                    le numéro du tirage (0 pour la référence)
    ============================ ==========================================
    """
    disperses: list[pd.DataFrame] = []
    references: list[pd.DataFrame] = []
    for indice, point in enumerate(POINTS_DE_VOL):
        mach = float(point["Mach"])
        # `riche=True` : décrochage, polaire de traînée, cassure de Cm_alpha.
        # Une enveloppe qui garde la même largeur d'un bout à l'autre du
        # balayage ne met rien à l'épreuve.
        #
        # Une graine par point de vol : une graine unique rejouerait le MÊME
        # lot partout, et les trois panneaux de la figure de comparaison se
        # ressembleraient sans que cela veuille rien dire.
        disperse = appeler_modele_polaire(
            lois, ALPHA, n=n, mach=mach, riche=True, graine=7 + indice
        )
        # Le tirage neutre — biais 0, FE 1 — donne le nominal. C'est la seule
        # façon honnête de l'obtenir : le MÊME modèle, sans dispersion.
        reference = appeler_modele_polaire(
            lois, ALPHA, mach=mach, riche=True, tirages=[tirage_neutre(lois)]
        )
        # Le modèle ne connaît que le Mach ; l'altitude est une clé de point de
        # vol qu'on ajoute ici. Les deux tableaux doivent la porter : c'est sur
        # elle aussi que le découpage se fera.
        for tableau, morceaux in ((disperse, disperses), (reference, references)):
            tableau["Altitude_m"] = point["Altitude_m"]
            morceaux.append(tableau)

    return (
        pd.concat(disperses, ignore_index=True),
        pd.concat(references, ignore_index=True),
    )


# ---------------------------------------------------------------------------
# 2. les quatre dictionnaires de batch_plot
# ---------------------------------------------------------------------------


def dictionnaires(df_reference: pd.DataFrame, coefficients: list[str]) -> dict[str, Any]:
    """Les quatre dictionnaires, écrits clé par clé.

    C'est le morceau qu'on vient copier. Rien n'y parle de dispersion : le
    lot se décrit comme n'importe quel lot de polaires, et la dispersion
    s'ajoute par le seul `on_before_save`.
    """
    return {
        # Une entrée par SOURCE de données. `df` est le tableau nominal — ici
        # une seule source ; on en mettrait une par maillage, par version du
        # solveur, par campagne d'essai. Le reste part en mots-clés de style.
        "configuration_dict": {
            "CFD": {"name": "CFD", "label": "CFD", "df": df_reference, "color": "C0", "marker": ""},
        },
        # Une FIGURE par entrée : les grandeurs à tracer.
        "y_axis_dict": {
            coefficient: {
                "col_name": coefficient,
                "literal_name": NOMS[coefficient],
                "symbol": SYMBOLES[coefficient],
                "unit": "-",
                "y_save_name": coefficient,
            }
            for coefficient in coefficients
        },
        # Les variables qui peuvent aller en ABSCISSE.
        "sweep_dict": {
            "alpha": {
                "col_name": "alpha",
                "literal_name": "Incidence",
                "symbol": r"$\alpha$",
                "unit": "°",
                "x_save_name": "alpha",
                "polar_prefix": "ALPHA_POLAR",
                "label": r"$\alpha$",
                "save_name": "ALPHA",
            },
        },
        # Les paramètres qui définissent un POINT DE VOL : un sous-répertoire
        # par valeur, et une figure par combinaison.
        "flight_point_dict": {
            "Mach": {
                "values": [p["Mach"] for p in POINTS_DE_VOL],
                "label": "M",
                "save_name": "M",
                "unit": "-",
            },
            "Altitude_m": {
                "values": [p["Altitude_m"] for p in POINTS_DE_VOL],
                "label": "Z",
                "save_name": "Z",
                "unit": "m",
            },
        },
    }


def inventaire(console: Console, titre: str, chemins: list[Path], racine: Path) -> None:
    """Ce qui a été écrit, avec la taille — une figure vide se voit là."""
    table = Table(title=titre, title_style="bold")
    table.add_column("fichier")
    table.add_column("ko", justify="right")
    for chemin in chemins:
        table.add_row(str(chemin.relative_to(racine)), f"{chemin.stat().st_size / 1024:.0f}")
    console.print(table)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lois", type=Path, default=ICI / "LOIS.yaml")
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE" / "BATCH_PLOT")
    parser.add_argument("-n", type=int, default=120, help="tirages par point de vol")
    parser.add_argument("--jobs", type=int, default=2, help="processus de rendu")
    args = parser.parse_args()

    try:
        from cfd_plot import batch_compare_flight_points, batch_plot
    except ImportError:
        print(
            "cfd-plot n'est pas installé ; cet exemple en a besoin.\n"
            "    pip install -e tools/cfd-plot",
            file=sys.stderr,
        )
        return 1

    console = Console()
    lois = charger_lois_yaml(args.lois)
    coefficients = list(lois)

    # --- 1. les deux tableaux -------------------------------------------
    console.print(
        f"[bold]Appel du modèle[/] : {args.n} tirages × {len(POINTS_DE_VOL)} points de vol…"
    )
    df_disperse, df_reference = tourner_le_modele(lois, args.n)
    console.print(
        f"  dispersé  : {len(df_disperse):>6} lignes  "
        f"({args.n} tirages × {len(ALPHA)} incidences × {len(POINTS_DE_VOL)} points)"
    )
    console.print(f"  référence : {len(df_reference):>6} lignes  (1 tirage neutre)")

    dicts = dictionnaires(df_reference, coefficients)

    # --- 3. le lot ordinaire --------------------------------------------
    #
    # UNE ligne pour la dispersion. Le hook reçoit le tableau dispersé entier
    # et se débrouille : pour chaque figure, il lit sur le `context` le point
    # de vol et la grandeur, découpe le tableau à l'identique de ce que
    # `batch_plot` a fait de la référence, regroupe en une courbe par tirage,
    # et superpose.
    #
    # `serie=` est facultatif quand il n'y a qu'une source : le hook prend la
    # seule courbe des axes. On l'écrit ici parce qu'un vrai lot en a
    # plusieurs, et qu'il faut alors dire laquelle porte le nominal.
    hook = hook_dispersion_tableau(df_disperse, serie="CFD")

    ecrits = batch_plot(
        **dicts,
        output_base=args.sortie / "ORDINAIRE",
        style_profile="paper",
        formats=("png",),
        report=False,
        # `n_jobs > 1` n'est possible que parce que le hook est sérialisable :
        # `HookDispersionTableau` est une classe de niveau module portant des
        # données simples. Une fermeture sur le DataFrame coûterait tous les
        # cœurs, avec pour seul signe un UserWarning noyé dans la sortie.
        n_jobs=args.jobs,
        on_before_save=hook,
    )
    inventaire(console, "1. le lot ordinaire", ecrits, args.sortie / "ORDINAIRE")

    # --- 4. les options d'affichage --------------------------------------
    #
    # Tout ce que `superposer_dispersion` accepte se passe au hook et vaut
    # pour tout le lot. Ici la lecture la plus sobre, celle qui tient dans un
    # dossier : ni faisceau ni σ, la seule enveloppe min/max et son cerne.
    #
    # `bordures` n'est pas à régler : sans σ il se met à True tout seul — il
    # faut bien que quelque chose délimite l'enveloppe — et à False dès qu'on
    # demande des σ, qui la longent déjà.
    sobre = hook_dispersion_tableau(
        df_disperse,
        serie="CFD",
        montrer_tirages=False,
        sigmas=(),
        boite_parametres=False,
    )
    ecrits_sobres = batch_plot(
        **dicts,
        output_base=args.sortie / "SOBRE",
        style_profile="paper",
        formats=("png",),
        report=False,
        n_jobs=args.jobs,
        on_before_save=sobre,
    )
    inventaire(console, "2. l'enveloppe seule", ecrits_sobres, args.sortie / "SOBRE")

    # --- 5. la bande théorique en plus -----------------------------------
    #
    # `lois=` ajoute au nuage obtenu la bande que les lois PRESCRIVAIENT. Les
    # deux devraient se recouvrir ; l'écart, s'il y en a un, est la vraie
    # information — un modèle qui disperse plus que demandé se lit là.
    prescrit = hook_dispersion_tableau(
        df_disperse,
        serie="CFD",
        lois=lois,
        n=4000,
        graine=1,
        sigmas=(1, 2, 3),
    )
    ecrits_prescrits = batch_plot(
        **dicts,
        output_base=args.sortie / "PRESCRIT",
        style_profile="paper",
        formats=("png",),
        report=False,
        n_jobs=args.jobs,
        on_before_save=prescrit,
    )
    inventaire(console, "3. prescrit contre obtenu", ecrits_prescrits, args.sortie / "PRESCRIT")

    # --- 6. la figure de comparaison -------------------------------------
    #
    # `batch_compare_flight_points` met les points de vol côte à côte sur une
    # même planche. Le hook y est appelé UNE FOIS PAR PANNEAU, avec le point
    # de vol de ce panneau : chacun reçoit donc ses propres tirages, sans
    # qu'on ait rien à faire. `panneaux=` permettrait de n'en décorer que
    # certains.
    ecrits_compare = batch_compare_flight_points(
        configuration_dict=dicts["configuration_dict"],
        y_axis_dict=dicts["y_axis_dict"],
        sweep_dict=dicts["sweep_dict"],
        flight_point_dict=dicts["flight_point_dict"],
        compare_flight_points={
            f"M{p['Mach']:.2f}": {"Mach": p["Mach"], "Altitude_m": p["Altitude_m"]}
            for p in POINTS_DE_VOL
        },
        output_base=args.sortie / "COMPARAISON",
        style_profile="paper",
        formats=("png",),
        report=False,
        on_before_save=hook_dispersion_tableau(df_disperse, serie="CFD", boite_parametres=False),
    )
    inventaire(
        console, "4. les points de vol côte à côte", ecrits_compare, args.sortie / "COMPARAISON"
    )

    # --- 7. le point de vol manquant -------------------------------------
    #
    # Les deux tableaux doivent couvrir les mêmes points de vol. S'ils ne le
    # font pas, le hook le dit DÈS LA PREMIÈRE FIGURE plutôt que de laisser
    # sortir un lot entier de figures nues, qui se lisent comme un modèle sans
    # dispersion. `absent="ignorer"` est là pour l'étude volontairement
    # partielle.
    console.print("\n[bold]Un point de vol absent du tableau dispersé[/]")
    ampute = df_disperse[df_disperse["Mach"] != 0.85]
    try:
        batch_plot(
            **dicts,
            output_base=args.sortie / "AMPUTE",
            formats=("png",),
            report=False,
            on_before_save=hook_dispersion_tableau(ampute, serie="CFD"),
        )
    except ValueError as erreur:
        console.print(f"  [red]{erreur}[/]")

    console.print(
        "\n[green]À regarder[/] : "
        f"{ecrits[0]}\n"
        "  la courbe nominale au premier plan, le faisceau des tirages derrière,\n"
        "  l'enveloppe min/max dans sa teinte, les ±kσ étiquetés, et la légende\n"
        "  qui porte l'effectif et la dispersion sur l'entrée de la série."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
