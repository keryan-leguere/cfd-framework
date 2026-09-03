#!/usr/bin/env python3
"""Cas d'usage 2.3 : la dispersion superposée sur les polaires de batch_plot.

    python 03_polaire_batch_plot.py [--sortie SORTIE]

Fait tourner ``cfd_plot.batch_plot`` — le générateur de polaires du framework —
avec le hook de dispersion greffé dessus. Chaque figure reçoit alors :

  * la bande théorique issue de la loi du coefficient ;
  * les courbes réellement obtenues, une par tirage du modèle ;
  * le remplissage min/max, dans la teinte de la série ;
  * les lignes ±1σ, ±2σ, ±3σ, étiquetées sur la courbe ;
  * la boîte disant quelle loi a produit tout cela.

Nécessite cfd-plot :  pip install -e tools/cfd-plot
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import numpy as np
import pandas as pd
from rich.console import Console

from cfd_dispersion import charger_lois_yaml
from cfd_dispersion.batch import hook_dispersion
from cfd_dispersion.figures.polaire import courbes_par_tirage

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI))

from modele import appeler_modele_polaire, polaire_nominale  # noqa: E402

ALPHA = np.linspace(0.0, 12.0, 25)
MACH = 0.80
ALTITUDE = 8000.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lois", type=Path, default=ICI / "LOIS.yaml")
    parser.add_argument("--sortie", type=Path, default=ICI / "SORTIE" / "POLAIRES")
    parser.add_argument("-n", type=int, default=300, help="tirages du modèle")
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

    # --- la polaire nominale, telle que batch_plot l'attend -------------
    nominal = polaire_nominale(ALPHA, mach=MACH)
    donnees = pd.DataFrame(
        {
            "alpha": ALPHA,
            "beta": 0.0,
            "Mach": MACH,
            "Altitude_m": ALTITUDE,
            **nominal,
        }
    )

    # --- les courbes réellement obtenues, une par tirage ----------------
    console.print(f"Appel du modèle : {args.n} tirages sur le balayage…")
    a_plat = appeler_modele_polaire(lois, ALPHA, n=args.n, mach=MACH)

    tirages = {}
    for coefficient in lois:
        _, courbes = courbes_par_tirage(a_plat, x="alpha", y=coefficient, par=["tirage"])
        # La clé est celle que rend `cle_par_defaut` : (grandeur, balayage).
        tirages[(coefficient, "alpha")] = courbes

    # --- batch_plot, avec la dispersion greffée -------------------------
    hook = hook_dispersion(
        lois,
        serie="CFD",
        tirages=tirages,
        n=6000,
        graine=1,
        max_tirages=150,
    )

    ecrits = batch_plot(
        configuration_dict={"CFD": {"df": donnees, "label": "CFD", "color": "C0"}},
        y_axis_dict={
            coefficient: {
                "col_name": coefficient,
                "symbol": _symbole(coefficient),
                "unit": "-",
                "y_save_name": coefficient,
            }
            for coefficient in lois
        },
        sweep_dict={
            "alpha": {
                "col_name": "alpha",
                "literal_name": "Incidence",
                "symbol": r"$\alpha$",
                "unit": "°",
                "x_save_name": "alpha",
            }
        },
        flight_point_dict={
            "Mach": {"values": [MACH], "label": "M", "save_name": "M", "unit": "-"},
            "Altitude_m": {"values": [ALTITUDE], "label": "Z", "save_name": "Z", "unit": "m"},
        },
        output_base=args.sortie,
        style_profile="paper",
        formats=("png",),
        report=False,
        on_before_save=hook,
    )

    for chemin in ecrits:
        console.print(f"[green]écrit :[/] {chemin}")
    return 0


def _symbole(coefficient: str) -> str:
    return {
        "CN": r"$C_N$",
        "CA": r"$C_A$",
        "Cm_alpha": r"$C_{m_\alpha}$",
    }.get(coefficient, coefficient)


if __name__ == "__main__":
    raise SystemExit(main())
