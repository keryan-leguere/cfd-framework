#!/usr/bin/env python3
"""Appeler le modèle aéro depuis Python : un point, puis un DataFrame.

    bash construire.sh          # une fois : produit aerolib*.so dans ce dossier
    python exemple_appel.py
"""

from __future__ import annotations

import itertools

import pandas as pd
from modele_aero import ModeleAero


def plan_de_calcul() -> pd.DataFrame:
    """Les colonnes portent le nom des arguments de aercal, en minuscules."""
    mach = [0.3, 0.7, 0.9, 1.2, 1.6, 2.4]
    alpha = [-15.0, -2.0, 0.0, 5.0, 15.0]
    beta = [-6.0, 0.0, 4.0]
    lignes = [
        {"cas": f"C{i:03d}", "mach": m, "alpha": a, "beta": b,
         "xg": 1.05, "yg": 0.0, "zg": -0.008, "ipropu": p, "dm": 5.0, "dn": 0.0}
        for i, (m, a, b, p) in enumerate(itertools.product(mach, alpha, beta, (0, 1)))
    ]
    return pd.DataFrame(lignes)


def main() -> None:
    modele = ModeleAero()
    print(modele.decrire())
    print("\nColonnes d'entrée reconnues :", ", ".join(modele.colonnes_entree))

    print("\n== Un point")
    print(modele.calculer(mach=0.8, alpha=5.0, beta=2.0, xg=1.0, yg=0.0, zg=0.0, ipropu=1, dm=5.0, dn=0.0))

    print("\n== Un DataFrame")
    df = plan_de_calcul()
    sortie = modele.calculer_df(df)
    with pd.option_context("display.width", 140, "display.max_columns", 20):
        print(sortie.drop(columns=list(modele.sondes)).head(8).to_string(index=False))
    print(f"\n{len(sortie)} cas ; IERR :", sortie["ierr"].value_counts().sort_index().to_dict())

    print("\n== Une constante d'init qui varie d'une ligne à l'autre (réinit à chaque changement)")
    point = df.iloc[[40]].drop(columns="cas")
    balayage = pd.concat([point] * 3, ignore_index=True).assign(lref=[0.1, 0.2, 0.4])
    print(modele.calculer_df(balayage)[["lref", "cx", "cm", "cn"]].to_string(index=False))
    print(f"\nAprès le balayage, l'objet garde ses constantes : {modele!r}")


if __name__ == "__main__":
    main()
