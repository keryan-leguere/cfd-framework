#!/usr/bin/env python3
"""Cas d'usage 2.3 : la dispersion superposée sur les polaires de batch_plot.

    python 03_polaire_batch_plot.py [--sortie SORTIE] [-n 300]

Fait tourner ``cfd_plot.batch_plot`` — le générateur de polaires du framework —
avec le hook de dispersion greffé dessus. Chaque figure reçoit alors :

  * la bande théorique issue de la loi du coefficient ;
  * les courbes réellement obtenues, une par tirage du modèle ;
  * le remplissage min/max, dans la teinte de la série ;
  * les lignes ±1σ, ±2σ, ±3σ, étiquetées sur la courbe ;
  * la boîte disant quelle loi a produit tout cela.

Les quatre dictionnaires de ``batch_plot`` sont écrits ici au complet, clé par
clé : c'est le morceau qu'on vient copier. Voir aussi
``00_DOC/05_BRANCHER_SON_MODELE.md`` §5.6.

Le script montre aussi la voie directe — ``superposer_dispersion`` sur des axes
à soi, sans ``batch_plot`` — pour les figures qui ne relèvent pas d'un lot.

Nécessite cfd-plot :  pip install -e tools/cfd-plot
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from rich.console import Console

from cfd_dispersion import (
    charger_lois_yaml,
    courbes_par_tirage,
    enregistrer,
    nouvelle_figure,
    style,
    superposer_dispersion,
    tracer_ligne,
)
from cfd_dispersion.batch import hook_dispersion

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

from modele import appeler_modele_polaire, polaire_nominale  # noqa: E402

ALPHA = np.linspace(0.0, 12.0, 25)
MACH = 0.80
ALTITUDE = 8000.0

SYMBOLES = {"CN": r"$C_N$", "CA": r"$C_A$", "Cm_alpha": r"$C_{m_\alpha}$"}
NOMS = {
    "CN": "Coefficient normal",
    "CA": "Coefficient axial",
    "Cm_alpha": "Gradient de moment de tangage",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lois", type=Path, default=ICI / "LOIS.yaml")
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE" / "POLAIRES")
    parser.add_argument("-n", type=int, default=300, help="tirages du modèle")
    parser.add_argument("--n-jobs", type=int, default=2, help="processus de rendu")
    args = parser.parse_args()

    try:
        from cfd_plot import batch_plot
    except ImportError:
        print(
            "cfd-plot n'est pas installé ; cet exemple en a besoin.\n"
            "    pip install -e tools/cfd-plot",
            file=sys.stderr,
        )
        return 1

    console = Console()
    lois = charger_lois_yaml(args.lois)

    # --- 1. la polaire nominale, telle que batch_plot l'attend ----------
    #
    # Un DataFrame par source de données : une colonne par grandeur, une
    # colonne par variable de balayage, une colonne par clé de point de vol.
    nominal = polaire_nominale(ALPHA, mach=MACH)
    donnees = pd.DataFrame(
        {"alpha": ALPHA, "beta": 0.0, "Mach": MACH, "Altitude_m": ALTITUDE, **nominal}
    )

    # --- 2. les courbes réellement obtenues, une par tirage -------------
    #
    # Le modèle rend un tableau à plat : une ligne par (tirage × point du
    # balayage). `courbes_par_tirage` le remet en matrice (n_tirages, npts).
    console.print(f"Appel du modèle : {args.n} tirages sur le balayage…")
    a_plat = appeler_modele_polaire(lois, ALPHA, n=args.n, mach=MACH)

    tirages = {}
    for coefficient in lois:
        _, courbes = courbes_par_tirage(a_plat, x="alpha", y=coefficient, par=["tirage"])
        # La clé est celle que rend `cle_par_defaut` : (grandeur, balayage).
        tirages[(coefficient, "alpha")] = courbes
        console.print(f"  {coefficient} : {courbes.shape[0]} courbes × {courbes.shape[1]} points")

    # --- 3. les quatre dictionnaires de batch_plot ---------------------
    configuration_dict = {
        # Une entrée par source de données. `df` est le tableau chargé ; tout
        # le reste part en mots-clés de style vers plot_line.
        "CFD": {
            "name": "CFD",
            "label": "CFD",
            "df": donnees,
            "color": "C0",
            "marker": "o",
        },
    }

    y_axis_dict = {
        # Une figure par entrée : les grandeurs tracées.
        coefficient: {
            "col_name": coefficient,
            "literal_name": NOMS[coefficient],
            "symbol": SYMBOLES[coefficient],
            "unit": "-",
            "y_save_name": coefficient,
        }
        for coefficient in lois
    }

    sweep_dict = {
        # Les variables qui peuvent aller en abscisse.
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
    }

    flight_point_dict = {
        # Les paramètres qui définissent un point de vol.
        "Mach": {"values": [MACH], "label": "M", "save_name": "M", "unit": "-"},
        "Altitude_m": {"values": [ALTITUDE], "label": "Z", "save_name": "Z", "unit": "m"},
    }

    # --- 4. le hook, et le lot ------------------------------------------
    #
    # `serie="CFD"` : le hook lit sur les axes la courbe portant ce libellé,
    # en reprend la couleur, et disperse SES données. La courbe nominale n'a
    # donc pas à être redonnée, et ne peut pas diverger de ce qui est tracé.
    hook = hook_dispersion(
        lois,
        serie="CFD",
        tirages=tirages,
        n=6000,
        graine=1,
        max_tirages=150,
    )

    ecrits = batch_plot(
        configuration_dict=configuration_dict,
        y_axis_dict=y_axis_dict,
        sweep_dict=sweep_dict,
        flight_point_dict=flight_point_dict,
        output_base=args.sortie,
        style_profile="paper",
        formats=("png",),
        report=True,
        # `n_jobs > 1` n'est possible que parce que le hook est sérialisable :
        # `HookDispersion` est une classe de niveau module, et non une
        # fermeture. Sinon batch_plot retomberait à 1 sans le dire vraiment.
        n_jobs=args.n_jobs,
        on_before_save=hook,
    )

    for chemin in ecrits:
        console.print(f"[green]écrit :[/] {chemin}")

    # --- 5. la même chose sans batch_plot -------------------------------
    #
    # Pour une figure isolée, `superposer_dispersion` s'appelle directement
    # sur des axes à soi. C'est la même fonction que celle du hook.
    with style("paper"):
        figure, ax = nouvelle_figure()
        tracer_ligne(ax, ALPHA, nominal["CN"], label="CFD", color="C0", marker="o")
        superposer_dispersion(
            ax,
            ALPHA,
            nominal["CN"],
            loi=lois["CN"],
            tirages=tirages[("CN", "alpha")],
            serie="CFD",  # reprendre la teinte de la courbe ci-dessus
            remplissage="minmax",
            sigmas=(1, 2, 3),
            n=6000,
            graine=1,
            label="CN",
        )
        ax.set_xlabel(r"Incidence $\alpha$ [°]")
        ax.set_ylabel(r"$C_N$ [-]")
        (chemin,) = enregistrer(figure, args.sortie / "polaire_directe_CN", formats=("png",))
        plt.close(figure)
    console.print(f"[green]écrit :[/] {chemin}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
