#!/usr/bin/env python3
"""Fabrique les CSV de REFERENCE/ comme s'ils venaient d'un autre environnement.

    cd ../../PYTHON && FFLAGS="-O3 -ffast-math -march=native" bash construire.sh aerolib_autre
    cd ../VALIDATION/04_INTEGRATION
    python generer_reference.py --module aerolib_autre

Dans la vraie vie, ce script n'existe pas : les CSV arrivent d'ailleurs (une
autre machine, un autre compilateur, l'ancienne chaîne de calcul), avec leurs
propres noms de colonnes. Ici on les fabrique pour l'exemple, avec le même code
compilé autrement (``-O3 -ffast-math``), et on les écrit avec des en-têtes
« étrangers » que ``04_integration.py`` doit ramener aux noms du modèle :

- campagne A : outil d'export n° 1, unités entre parenthèses (``Alpha (deg)``) ;
- campagnes B et C : outil n° 2, en majuscules, unités entre crochets
  (``ALPHA [deg]``), propulsion en ``ON``/``OFF``.

Les flottants sont écrits au plus court qui redonne la même valeur : la
relecture est exacte, un écart vu par le test vient du code, pas du CSV.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent))  # VALIDATION/ : tables_modele

from tables_modele import DEFAUTS, PYTHON, charger_modele  # noqa: E402

#: Constantes d'init de l'autre environnement : celles de la validation.
# biaicx 0.005 : la valeur des CSV livrés dans REFERENCE/ (le défaut du modèle est 0)
INIT = {**{k: DEFAUTS[k] for k in ("xref", "yref", "zref", "lref")}, "biaicx": 0.005}
ENTREES = ["mach", "alpha", "beta", "xg", "yg", "zg", "ipropu", "dm", "dn", "xref", "yref", "zref", "lref", "biaicx"]
SORTIES = ["cx", "cy", "cz", "cl", "cm", "cn", "ierr"]

#: Noms d'en-tête de chaque outil d'export, pour chaque colonne du modèle.
OUTIL_1 = {
    "mach": "Mach", "alpha": "Alpha (deg)", "beta": "Beta (deg)", "xg": "Xg (m)", "yg": "Yg (m)", "zg": "Zg (m)",
    "ipropu": "Propulsion", "dm": "DM (deg)", "dn": "DN (deg)", "xref": "Xref (m)", "yref": "Yref (m)",
    "zref": "Zref (m)", "lref": "Lref (m)", "biaicx": "Biais CX",
    "cx": "CX", "cy": "CY", "cz": "CZ", "cl": "Cl", "cm": "Cm", "cn": "Cn", "ierr": "IERR",
}
OUTIL_2 = {
    "mach": "MACH", "alpha": "ALPHA [deg]", "beta": "BETA [deg]", "xg": "XG [m]", "yg": "YG [m]", "zg": "ZG [m]",
    "ipropu": "PROPULSION", "dm": "DELTA_M [deg]", "dn": "DELTA_N [deg]", "xref": "XREF [m]", "yref": "YREF [m]",
    "zref": "ZREF [m]", "lref": "LREF [m]", "biaicx": "BIAIS_CX",
    "cx": "CX", "cy": "CY", "cz": "CZ", "cl": "CL", "cm": "CM", "cn": "CN", "ierr": "IERR",
}


def _plan(**axes: list[float]) -> pd.DataFrame:
    """Produit croisé des axes, le reste à sa valeur de validation."""
    df = pd.DataFrame(list(itertools.product(*axes.values())), columns=list(axes))
    for nom, valeur in {**INIT, **{k: DEFAUTS[k] for k in ("beta", "xg", "yg", "zg", "ipropu", "dm", "dn")}}.items():
        if nom not in df:
            df[nom] = valeur
    df["ipropu"] = df["ipropu"].astype("int64")
    return df


def pas(de: float, a: float, h: float) -> list[float]:
    """De ``de`` à ``a`` compris, par pas de ``h``, sans les 0.30000000000000004 de l'arithmétique."""
    return [round(float(v), 10) for v in np.arange(de, a + h / 2, h)]


def campagnes() -> dict[str, tuple[pd.DataFrame, dict[str, str]]]:
    """Les trois fichiers : leur plan et l'outil qui les a écrits."""
    return {
        # incidence et dérapage, Mach jusqu'au-delà des grilles (saturation, IERR 2)
        "campagne_A_incidence.csv": (_plan(
            mach=[0.2, 0.3, 0.6, 0.8, 0.95, 1.1, 1.5, 2.0, 2.3], alpha=pas(-24, 24, 3), beta=[-4.0, 0.0, 4.0],
            zg=[0.01]), OUTIL_1),
        # propulsion allumée ou non, deux centrages
        "campagne_B_propulsion.csv": (_plan(
            mach=pas(0.3, 2.1, 0.1), ipropu=[0, 1], alpha=[0.0, 5.0], xg=[1.0, 1.4]), OUTIL_2),
        # gouvernes
        "campagne_C_gouvernes.csv": (_plan(
            mach=[0.8, 1.0, 1.2], alpha=[-10.0, 0.0, 10.0], beta=[-5.0, 0.0, 5.0], dm=pas(-20, 20, 10),
            dn=[-10.0, 0.0, 10.0]), OUTIL_2),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--module", default="aerolib_autre", help="module de l'« autre environnement »")
    p.add_argument("--dossier", type=Path, default=PYTHON, help="où chercher le module")
    p.add_argument("--sortie", type=Path, default=ICI / "REFERENCE", help="dossier des CSV")
    args = p.parse_args()

    modele = charger_modele(args.module, args.dossier)
    if modele is None:
        return 1
    args.sortie.mkdir(parents=True, exist_ok=True)
    for nom, (plan, outil) in campagnes().items():
        res = modele.calcul_aero_elementaire(plan)
        res = res[[*ENTREES, *SORTIES]]
        if outil is OUTIL_2:
            res["ipropu"] = np.where(res["ipropu"] == 1, "ON", "OFF")
        res.rename(columns=outil).to_csv(args.sortie / nom, index=False)
        print(f"{nom} : {len(res)} lignes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
