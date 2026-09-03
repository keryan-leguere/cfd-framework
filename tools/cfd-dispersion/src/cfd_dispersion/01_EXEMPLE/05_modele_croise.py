#!/usr/bin/env python3
"""La chaîne complète sur un vrai modèle : listes croisées, tableau large.

    python 05_modele_croise.py [--sortie SORTIE] [-n 200]

C'est l'exemple à copier quand votre modèle ressemble à ceci :

  * il reçoit des **listes d'axes** — ``L_MACH``, ``L_ALTITUDE``, ``L_ALPHA`` —
    et les croise lui-même ;
  * il initialise une bibliothèque Fortran, tire les dispersions, puis boucle ;
  * il rend **un seul tableau**, une ligne par (tirage × point croisé), portant
    le point de vol, les coefficients, ses métadonnées, et les deux
    dictionnaires : ``DICT_LAW_DISPERSION`` et ``DICT_TIRAGE``.

Le paquet lit ce tableau tel quel :

    resultats, lois = lire_sortie_modele(df)

Un point mérite l'attention, et il est traité ici : un appel croisé applique
**le même tirage à tous les points du balayage**. Le valider tel quel
multiplierait l'effectif par la longueur du balayage et rejetterait des tirages
corrects — d'où ``unique_par=("tirage",)``. L'oubli n'est pas silencieux : la
validation refuse le tableau en nommant le remède.

Sorties, dans SORTIE/ :

    sortie_modele.csv        le tableau du modèle, dictionnaires compris
    verdicts.csv             un verdict par (point de vol × composante)
    synthese.png             le damier
    mc_<pdv>_<coeff>.png     les points de vol rejetés
    POLAIRES/…               les polaires dispersées, une par Mach
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from rich.console import Console

from cfd_dispersion import (
    JeuDeLois,
    charger_lois_yaml,
    courbes_par_tirage,
    enregistrer,
    figure_synthese,
    figures_par_pdv,
    lire_sortie_modele,
    pdv_rejetes,
    table_rich,
    valider_lot,
)
from cfd_dispersion.batch import hook_dispersion

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

from modele import appeler_modele_croise, coefficients_nominaux  # noqa: E402

#: Les axes de l'étude, tels qu'on les écrit en tête de script.
L_MACH = [0.70, 0.85]
L_ALTITUDE = [8000.0]
L_ALPHA = [0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0]

#: Les colonnes qui définissent un point de vol. `alpha` n'en est pas : c'est
#: le balayage, l'abscisse des polaires.
PAR = ("Mach", "Altitude_m")

SYMBOLES = {"CN": r"$C_N$", "CA": r"$C_A$", "Cm_alpha": r"$C_{m_\alpha}$"}
NOMS = {
    "CN": "Coefficient normal",
    "CA": "Coefficient axial",
    "Cm_alpha": "Gradient de moment de tangage",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lois", type=Path, default=ICI / "LOIS.yaml")
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE" / "CROISE")
    parser.add_argument("-n", type=int, default=200, help="appels du modèle")
    args = parser.parse_args()

    console = Console()
    args.sortie.mkdir(parents=True, exist_ok=True)
    lois = charger_lois_yaml(args.lois)

    # --- 1. l'appel du modèle -------------------------------------------
    console.print(
        f"Modèle : {args.n} appels × {len(L_MACH)}×{len(L_ALTITUDE)}×{len(L_ALPHA)} points croisés…"
    )
    df = appeler_modele_croise(
        lois, L_MACH=L_MACH, L_ALTITUDE=L_ALTITUDE, L_ALPHA=L_ALPHA, n=args.n
    )
    df.to_csv(args.sortie / "sortie_modele.csv", index=False)
    console.print(f"  tableau : {len(df)} lignes × {len(df.columns)} colonnes")
    console.print(f"  colonnes : {list(df.columns)}\n")

    # --- 2. la traduction, en une ligne ---------------------------------
    #
    # Aplatit DICT_TIRAGE en colonnes <coeff>_Biais / <coeff>_FE, numérote les
    # tirages distincts, et relit DICT_LAW_DISPERSION. Les métadonnées du
    # solveur voyagent intactes : le paquet ne lit que les colonnes qu'il nomme.
    resultats, lois_relues = lire_sortie_modele(df)
    console.print(
        f"  aplati : {[c for c in resultats.columns if c not in df.columns]}\n"
        f"  lois relues depuis le tableau : {list(lois_relues)}\n"
        f"  {resultats['tirage'].nunique()} tirages distincts "
        f"pour {len(resultats)} lignes\n"
    )

    # --- 3. la validation, dédoublonnée ---------------------------------
    #
    # Sans `unique_par`, chaque tirage compterait sept fois — une par incidence.
    verdicts = valider_lot(resultats, lois_relues, par=PAR, unique_par=("tirage",))
    verdicts.to_csv(args.sortie / "verdicts.csv", index=False)
    console.print(table_rich(verdicts))

    figure, _ = figure_synthese(verdicts)
    (chemin,) = enregistrer(figure, args.sortie / "synthese", formats=("png",))
    plt.close(figure)
    console.print(f"[green]écrit :[/] {chemin}")

    rejetes = pdv_rejetes(verdicts)
    console.print(
        f"[red]{len(rejetes)} point(s) de vol rejeté(s)[/] : {rejetes}"
        if rejetes
        else "[green]Tous les points de vol sont validés.[/]"
    )

    for cles, coefficient, figure in figures_par_pdv(
        resultats,
        lois_relues,
        par=PAR,
        unique_par=("tirage",),
        nominaux=coefficients_nominaux(0.85),
        seulement=rejetes or None,
    ):
        etiquette = "_".join(f"{cle}{valeur:g}" for cle, valeur in cles.items())
        (chemin,) = enregistrer(
            figure, args.sortie / f"mc_{etiquette}_{coefficient}", formats=("png",)
        )
        plt.close(figure)
        console.print(f"[green]écrit :[/] {chemin}")

    # --- 4. les polaires dispersées, une par point de vol ---------------
    _polaires(resultats, lois_relues, args.sortie, console)
    return 0


def _polaires(resultats: pd.DataFrame, lois: JeuDeLois, sortie: Path, console: Console) -> int:
    """Une polaire dispersée par point de vol, via batch_plot."""
    try:
        from cfd_plot import batch_plot
    except ImportError:
        console.print("cfd-plot absent : polaires ignorées.")
        return 0

    # La polaire nominale : la moyenne des tirages en chaque point. Sur un
    # tableau réel, ce serait plutôt le calcul non dispersé.
    nominal = (
        resultats.groupby(["Mach", "Altitude_m", "alpha"], as_index=False)[list(SYMBOLES)]
        .mean()
        .sort_values(["Mach", "Altitude_m", "alpha"])
    )

    # Les courbes obtenues, une par tirage — à point de vol figé, car un
    # balayage se lit à Mach constant.
    tirages = {}
    for coefficient in SYMBOLES:
        for mach in L_MACH:
            bloc = resultats.loc[resultats["Mach"] == mach]
            _, courbes = courbes_par_tirage(bloc, x="alpha", y=coefficient, par=["tirage"])
            tirages[(coefficient, "alpha", mach)] = courbes

    ecrits = batch_plot(
        configuration_dict={
            "CFD": {"name": "CFD", "label": "CFD", "df": nominal, "color": "C0", "marker": "o"}
        },
        y_axis_dict={
            coefficient: {
                "col_name": coefficient,
                "literal_name": NOMS[coefficient],
                "symbol": SYMBOLES[coefficient],
                "unit": "-",
                "y_save_name": coefficient,
            }
            for coefficient in SYMBOLES
        },
        sweep_dict={
            "alpha": {
                "col_name": "alpha",
                "literal_name": "Incidence",
                "symbol": r"$\alpha$",
                "unit": "°",
                "x_save_name": "alpha",
                "polar_prefix": "ALPHA_POLAR",
                "label": r"$\alpha$",
                "save_name": "ALPHA",
            }
        },
        flight_point_dict={
            "Mach": {"values": L_MACH, "label": "M", "save_name": "M", "unit": "-"},
            "Altitude_m": {"values": L_ALTITUDE, "label": "Z", "save_name": "Z", "unit": "m"},
        },
        output_base=sortie / "POLAIRES",
        style_profile="paper",
        formats=("png",),
        report=False,
        # La dispersion change de point de vol en point de vol : la clé par
        # défaut (grandeur, balayage) ne suffit pas, d'où `cle=cle_par_pdv` —
        # une fonction de niveau module, pour rester sérialisable.
        on_before_save=hook_dispersion(
            lois, serie="CFD", tirages=tirages, cle=cle_par_pdv, n=6000, graine=1, max_tirages=120
        ),
    )
    for chemin in ecrits:
        console.print(f"[green]écrit :[/] {chemin}")
    return 0


def cle_par_pdv(context: object) -> tuple[object, ...]:
    """La clé des tirages : (grandeur, balayage, Mach).

    De niveau module, et non une fermeture ni une lambda : ``batch_plot``
    sérialise son hook pour ses processus de travail, et retombe silencieusement
    sur un seul cœur quand il n'y parvient pas.
    """
    return (
        context.y_key,  # type: ignore[attr-defined]
        context.sweep_key,  # type: ignore[attr-defined]
        context.flight_point["Mach"],  # type: ignore[attr-defined]
    )


if __name__ == "__main__":
    raise SystemExit(main())
