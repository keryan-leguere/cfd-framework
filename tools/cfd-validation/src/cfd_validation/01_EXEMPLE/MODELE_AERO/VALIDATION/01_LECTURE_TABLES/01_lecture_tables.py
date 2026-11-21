#!/usr/bin/env python3
"""Test de lecture de table du modèle aéro : chaque nœud de chaque table, relu par le code.

    cd ../../PYTHON && bash construire.sh     # une fois : le module instrumenté (sondes /PROBE/)
    cd ../VALIDATION/01_LECTURE_TABLES
    python 01_lecture_tables.py                # les 8 tables, entrées libres aux défauts
    python 01_lecture_tables.py --combinaisons # + invariance : toutes les combinaisons des autres entrées
    python 01_lecture_tables.py --defaut       # une valeur de CM faussée côté référence : NON CONFORME

Ce qui se déclare, table par table — c'est le bloc à recopier pour un autre code :

- la table et ses grilles, **lues dans le COMMON** que remplit le BLOCK DATA
  (``modele.lire("aertab.tcx")``), axes dans l'ordre des indices Fortran ;
- la sonde : la variable de ``COMMON /PROBE/`` que le code remplit juste après
  avoir lu cette table (``VALID_TAB_CX``, en minuscules pour f2py) ;
- le passage des colonnes de la table aux entrées du modèle, quand elles
  diffèrent (``vers_entrees``) ;
- les entrées à fixer pour que la table soit lue (``ipropu = 1`` pour la
  propulsion), et la tolérance si l'identité bit pour bit n'est pas atteignable.

Code de retour : 0 conforme, 2 non conforme.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from cfd_validation import TableReference, valider_lecture_tables

ICI = Path(__file__).resolve().parent
PYTHON = ICI.parent.parent / "PYTHON"  # MODELE_AERO/PYTHON : l'encapsulation f2py
sys.path.insert(0, str(PYTHON))

from modele_aero import ModeleAero  # noqa: E402

#: Valeur de chaque entrée du modèle quand la table ne la fixe pas.
DEFAUTS = {
    "mach": 0.8, "alpha": 0.0, "beta": 0.0,
    "xg": 1.2, "yg": 0.0, "zg": 0.0,          # CDG au point de référence : rien à transporter
    "ipropu": 0, "dm": 0.0, "dn": 0.0,
}

#: --combinaisons : chaque nœud rejoué pour toutes les combinaisons de ces valeurs
#: (entrées que la table ne pilote pas). La lecture d'une table n'en dépend pas.
COMBINAISONS: dict[str, list[float]] = {
    "alpha": [-5.0, 0.0, 5.0],
    "beta": [-5.0, 0.0, 5.0],
    "xg": [1.0, 1.4],
    "ipropu": [0.0, 1.0],   # entier côté Fortran : converti à l'appel, 0.5 serait refusé
    "dm": [-10.0, 0.0, 10.0],
}


def polaire_vers_cartesien(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """(alphat, phia) → (alpha, beta), l'inverse de ce que fait AERCAL.

    Le code calcule cos(alphaT) = cos(alpha)·cos(beta) et
    phiA = atan2(sin(beta), sin(alpha)·cos(beta)) ; d'où
    tan(alpha) = tan(alphaT)·cos(phiA) et sin(beta) = sin(alphaT)·sin(phiA).

    Variante simple, quand une table est en (mach, alphat) sans azimut :
    ``vers_entrees=lambda df: {"alpha": df["alphat"], "beta": 0.0}``.
    """
    at = np.radians(df["alphat"].to_numpy())
    phi = np.radians(df["phia"].to_numpy())
    return {
        "alpha": np.degrees(np.arctan(np.tan(at) * np.cos(phi))),
        "beta": np.degrees(np.arcsin(np.sin(at) * np.sin(phi))),
    }


def declarer_tables(modele: ModeleAero, *, faussee: bool = False) -> list[TableReference]:
    lire = modele.lire
    mach_alpha = {"mach": lire("aertab.tmach"), "alpha": lire("aertab.talpha")}
    mach_beta = {"mach": lire("aertab.tmach"), "beta": lire("aertab.tbeta")}

    tcm = lire("aertab.tcm")
    if faussee:  # scénario --defaut : la référence ne correspond plus au code en un nœud
        tcm[3, 4] += 1e-3

    tables = [
        TableReference("CX", lire("aertab.tcx"), mach_alpha, sonde="valid_tab_cx",
                       description="force axiale au point de référence"),
        TableReference("CZ", lire("aertab.tcz"), mach_alpha, sonde="valid_tab_cz",
                       description="force normale au point de référence"),
        TableReference("CM", tcm, mach_alpha, sonde="valid_tab_cm",
                       description="moment de tangage au point de référence, avant gouvernes et transport"),
        TableReference("CY", lire("aertab.tcy"), mach_beta, sonde="valid_tab_cy",
                       description="force latérale"),
        TableReference("CL", lire("aertab.tcl"), mach_beta, sonde="valid_tab_cl",
                       description="moment de roulis au point de référence"),
        TableReference("CN", lire("aertab.tcn"), mach_beta, sonde="valid_tab_cn",
                       description="moment de lacet au point de référence"),
        # Lue seulement propulsion allumée : sans « fixes », la sonde resterait NaN.
        TableReference("DCXP", lire("aertab.tdcxp"), {"mach": lire("aertab.tmachp")}, sonde="valid_tab_dcxp",
                       fixes={"ipropu": 1}, description="incrément de CX de la propulsion"),
        # 5D, en angles polaires : alphat et phia ne sont pas des entrées du modèle.
        TableReference(
            "DCMG", lire("aertb5.tdcmg"),
            {"mach": lire("aertb5.tmachg"), "alphat": lire("aertb5.talft"), "phia": lire("aertb5.tphia"),
             "dm": lire("aertb5.tdmg"), "dn": lire("aertb5.tdng")},
            sonde="valid_tab_dcmg",
            vers_entrees=polaire_vers_cartesien,
            rtol=1e-12, atol=1e-15,
            justification=(
                "(alphaT, phiA) → (alpha, beta) → (alphaT, phiA) ne retombe pas au bit près sur le "
                "nœud (acos, atan2) : l'écart d'arrondi, quelques 1e-15 deg, multiplié par la pente "
                "de la table, reste sous 1e-15 ; 1e-12 relatif laisse un facteur 1000."
            ),
            description="incrément de Cm des gouvernes, tabulé en (Mach, alphaT, phiA, DM, DN)",
        ),
    ]
    return tables


def _sha256(chemin: str | None) -> str:
    return hashlib.sha256(Path(chemin).read_bytes()).hexdigest() if chemin else "?"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--combinaisons", action="store_true", help="rejouer chaque nœud pour toutes les combinaisons des autres entrées")
    p.add_argument("--defaut", action="store_true", help="fausser une valeur de CM côté référence (verdict NON CONFORME)")
    p.add_argument("--module", default="aerolib", help="module f2py à tester (défaut aerolib)")
    p.add_argument("--dossier", type=Path, default=PYTHON, help="où chercher le module")
    p.add_argument("--sortie", type=Path, default=None, help="dossier des pièces (défaut SORTIE/<scénario>)")
    p.add_argument("--sans-figures", action="store_true", help="ne pas tracer la figure de synthèse")
    args = p.parse_args()

    try:
        modele = ModeleAero(args.module, dossier=args.dossier)
    except ModuleNotFoundError as erreur:
        print(f"{erreur}\n  → cd {PYTHON} && bash construire.sh", file=sys.stderr)
        return 1

    scenario = "defaut" if args.defaut else "combinaisons" if args.combinaisons else "nominal"
    res = valider_lecture_tables(
        declarer_tables(modele, faussee=args.defaut),
        evaluer=modele.calculer_df,
        defauts=DEFAUTS,
        combinaisons=COMBINAISONS if args.combinaisons else None,
        identifiant="VAL-TAB-01",
        metadonnees={
            "code": "modele_aero (exemple cfd-validation)",
            "module": f"{modele.bibliotheque.__name__} — sha256 {_sha256(modele.bibliotheque.__file__)[:16]}…",
            "constantes": ", ".join(f"{k}={getattr(modele, k)}" for k in modele.arguments_init),
            "scénario": scenario,
        },
        sortie=args.sortie or ICI / "SORTIE" / scenario,
        figures=not args.sans_figures,
        nettoyer=True,
    )
    return 0 if res.conforme else 2


if __name__ == "__main__":
    sys.exit(main())
