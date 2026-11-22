#!/usr/bin/env python3
"""Appeler le modèle aéro depuis Python : paramètres standard, puis arguments Fortran.

    bash construire.sh          # une fois : produit aerolib*.so dans ce dossier
    python exemple_appel.py
"""

from __future__ import annotations

import itertools

import pandas as pd
from modele_aero import ModeleAero


def plan_standard() -> pd.DataFrame:
    """Les paramètres de calcul_aero (ModeleAero.PARAMETRES) ; xref … lref pris par défaut."""
    mach = [0.3, 0.7, 0.9, 1.2, 1.6, 2.4]
    alpha = [-15.0, -2.0, 0.0, 5.0, 15.0]
    beta = [-6.0, 0.0, 4.0]
    lignes = [
        {"cas": f"C{i:03d}", "mach": m, "alpha": a, "beta": b,
         "xg_mm": 1050.0, "yg_mm": 0.0, "zg_mm": 8.0, "propulsion": p, "dm": 5.0, "dn": 0.0}
        for i, (m, a, b, p) in enumerate(itertools.product(mach, alpha, beta, (False, True)))
    ]
    return pd.DataFrame(lignes)


def main() -> None:
    modele = ModeleAero()
    print(modele.decrire())

    print("\n== calcul_aero : paramètres standard")
    for nom, sens in modele.PARAMETRES.items():
        print(f"  {nom:<11s} {sens}")
    sortie = modele.calcul_aero(plan_standard())
    colonnes = ["cas", "mach", "alpha", "propulsion", "zg_mm", "zg", "ipropu", "cx", "cm", "etat", "modele"]
    with pd.option_context("display.width", 140, "display.max_columns", 20):
        print(sortie[colonnes].head(6).to_string(index=False))
    print(f"\n{len(sortie)} cas ; état :", sortie["etat"].value_counts().to_dict())

    print("\n== calcul_aero_elementaire : les arguments Fortran tels quels")
    print("  colonnes :", ", ".join(modele.colonnes_entree))
    point = pd.DataFrame([{"xref": 1.2, "yref": 0.0, "zref": 0.0, "lref": 0.2, "biaicx": 0.0, "mach": 0.8, "alpha": 5.0,
                           "beta": 2.0, "xg": 1.0, "yg": 0.0, "zg": 0.0, "ipropu": 1, "dm": 5.0, "dn": 0.0}])
    brut = modele.calcul_aero_elementaire(point)
    print(brut[list(modele.colonnes_sortie[:7])].to_string(index=False))

    print("\n== lref qui varie d'une ligne à l'autre : AERINI rappelée à chaque changement")
    balayage = pd.concat([point] * 3, ignore_index=True).assign(lref=[0.1, 0.2, 0.4])
    print(modele.calcul_aero_elementaire(balayage)[["lref", "cx", "cm", "cn"]].to_string(index=False))

    print("\n== biaicx (AERCFG) : CX décalé, la sonde de la table ne bouge pas")
    biais = pd.concat([point] * 2, ignore_index=True).assign(biaicx=[0.0, 0.01])
    print(modele.calcul_aero_elementaire(biais)[["biaicx", "cx", "valid_tab_cx", "cm"]].to_string(index=False))


if __name__ == "__main__":
    main()
