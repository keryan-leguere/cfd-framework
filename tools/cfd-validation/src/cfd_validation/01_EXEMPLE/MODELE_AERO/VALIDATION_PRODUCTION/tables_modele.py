"""Les tables du modèle aéro, déclarées une fois pour tous les tests de validation — version de production.

Copie de ``VALIDATION/tables_modele.py`` sans ce qui sert à fausser un test pour
la démonstration (``declarer_tables`` ne prend que le modèle) : ce qui est
déclaré ici est exactement ce qui est vérifié.

C'est le fichier à réécrire pour un autre code : chaque table avec ses valeurs
et ses grilles **lues dans le COMMON** que remplit le BLOCK DATA, sa sonde, le
passage de ses colonnes aux entrées du modèle, et sa **consigne hors bornes**,
axe par axe — celle que le code doit appliquer, pas celle qu'il applique : c'est
au test de dire s'ils coïncident. S'y ajoutent les **polaires** à tracer et le
libellé de chaque axe sur les figures.

Consignes du modèle (SOURCES/aero_modele.f) :

| Axe                 | Consigne                                              |
|---------------------|-------------------------------------------------------|
| Mach (toutes)       | sature                                                |
| alpha, beta         | extrapole                                             |
| alphaT (5D)         | inatteignable sous 0 (acos ≥ 0), extrapole au-delà     |
| phiA (5D)           | inatteignable (atan2 reste dans [−180, 180])          |
| DM, DN (5D)         | sature                                                |
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cfd_validation import Polaires, TableReference

ICI = Path(__file__).resolve().parent
PYTHON = ICI.parent / "PYTHON"  # MODELE_AERO/PYTHON : l'encapsulation f2py
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from modele_aero import ModeleAero  # noqa: E402

__all__ = ["DEFAUTS", "LIBELLES", "POLAIRES", "PYTHON", "ModeleAero", "analyseur", "charger_modele", "declarer_tables",
           "metadonnees", "polaire_vers_cartesien"]

#: Valeur de chaque argument Fortran (AERINI puis AERCAL) quand la table ne le pilote pas.
#: Les tests passent par ModeleAero.calcul_aero_elementaire : tous les arguments sont là,
#: constantes d'init comprises.
DEFAUTS: dict[str, Any] = {
    "xref": 1.2, "yref": 0.0, "zref": 0.0, "lref": 0.2,  # AERINI : point de référence des moments, longueur
    "biaicx": 0.005,                                      # AERCFG : biais sur CX, constant ; appliqué après
                                                          # les sondes, il ne change aucune lecture de table
    "mach": 0.8, "alpha": 0.0, "beta": 0.0,
    "xg": 1.2, "yg": 0.0, "zg": 0.0,          # CDG au point de référence : rien à transporter
    "ipropu": 0, "dm": 0.0, "dn": 0.0,
}

#: Libellé (mathtext) et unité de chaque axe et de chaque table sur les figures.
LIBELLES: dict[str, str | tuple[str, str]] = {
    "mach": "Mach", "alpha": (r"$\alpha$", "°"), "beta": (r"$\beta$", "°"),
    "alphat": (r"$\alpha_T$", "°"), "phia": (r"$\varphi_A$", "°"),
    "dm": (r"$\delta_m$", "°"), "dn": (r"$\delta_n$", "°"),
    "CX": "$C_X$", "CY": "$C_Y$", "CZ": "$C_Z$", "CL": "$C_l$", "CM": "$C_m$", "CN": "$C_n$",
    "DCXP": r"$\Delta C_{X,\mathrm{prop}}$", "DCMG": r"$\Delta C_{m,\mathrm{gouv}}$",
}

#: Polaires : toutes par défaut (2D : une courbe par nœud de l'autre axe, dans les deux sens).
#: La 5D en aurait 3 125 : on retient Mach 1, trois incidences, deux azimuts, DN nul.
POLAIRES: dict[str, Polaires] = {
    "DCMG": Polaires(
        abscisses=("alphat", "phia", "dm"),
        noeuds={"mach": [1.0], "alphat": [0.0, 10.0, 20.0], "phia": [0.0, 90.0], "dn": [0.0]},
        superposer="dm",
    ),
}

MACH_ALPHA = {"mach": "sature", "alpha": "extrapole"}
MACH_BETA = {"mach": "sature", "beta": "extrapole"}


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


def declarer_tables(modele: ModeleAero) -> list[TableReference]:
    """Les 8 tables du modèle, valeurs et grilles telles que le code les a en mémoire."""
    lire = modele.lire
    mach_alpha = {"mach": lire("aertab.tmach"), "alpha": lire("aertab.talpha")}
    mach_beta = {"mach": lire("aertab.tmach"), "beta": lire("aertab.tbeta")}

    return [
        TableReference("CX", lire("aertab.tcx"), mach_alpha, sonde="valid_tab_cx", bornes=MACH_ALPHA,
                       description="force axiale au point de référence"),
        TableReference("CZ", lire("aertab.tcz"), mach_alpha, sonde="valid_tab_cz", bornes=MACH_ALPHA,
                       description="force normale au point de référence"),
        TableReference("CM", lire("aertab.tcm"), mach_alpha, sonde="valid_tab_cm", bornes=MACH_ALPHA,
                       description="moment de tangage au point de référence, avant gouvernes et transport"),
        TableReference("CY", lire("aertab.tcy"), mach_beta, sonde="valid_tab_cy", bornes=MACH_BETA,
                       description="force latérale"),
        TableReference("CL", lire("aertab.tcl"), mach_beta, sonde="valid_tab_cl", bornes=MACH_BETA,
                       description="moment de roulis au point de référence"),
        TableReference("CN", lire("aertab.tcn"), mach_beta, sonde="valid_tab_cn", bornes=MACH_BETA,
                       description="moment de lacet au point de référence"),
        # Lue seulement propulsion allumée : sans « fixes », la sonde resterait NaN.
        TableReference("DCXP", lire("aertab.tdcxp"), {"mach": lire("aertab.tmachp")}, sonde="valid_tab_dcxp",
                       fixes={"ipropu": 1}, bornes={"mach": "sature"},
                       description="incrément de CX de la propulsion"),
        # 5D, en angles polaires : alphat et phia ne sont pas des entrées du modèle.
        TableReference(
            "DCMG", lire("aertb5.tdcmg"),
            {"mach": lire("aertb5.tmachg"), "alphat": lire("aertb5.talft"), "phia": lire("aertb5.tphia"),
             "dm": lire("aertb5.tdmg"), "dn": lire("aertb5.tdng")},
            sonde="valid_tab_dcmg",
            vers_entrees=polaire_vers_cartesien,
            bornes={"mach": "sature", "alphat": ("inatteignable", "extrapole"), "phia": "inatteignable",
                    "dm": "sature", "dn": "sature"},
            rtol=1e-12, atol=1e-15,
            justification=(
                "(alphaT, phiA) → (alpha, beta) → (alphaT, phiA) ne retombe pas au bit près sur le "
                "nœud (acos, atan2) : l'écart d'arrondi, quelques 1e-15 deg, multiplié par la pente "
                "de la table, reste sous 1e-15 ; 1e-12 relatif laisse un facteur 1000."
            ),
            description="incrément de Cm des gouvernes, tabulé en (Mach, alphaT, phiA, DM, DN)",
        ),
    ]


class _Analyseur(argparse.ArgumentParser):
    """Une option inconnue (celles de la démonstration comprises) sort en 1, pas en 2.

    2 veut dire « non conforme » pour RUN_VALIDATION.sh : une erreur d'appel ne
    doit pas pouvoir passer pour un verdict.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        print(f"{self.prog} : erreur : {message}", file=sys.stderr)
        sys.exit(1)


def analyseur(description: str) -> argparse.ArgumentParser:
    """L'analyseur de ligne de commande des scripts de test."""
    return _Analyseur(description=description)


def charger_modele(module: str, dossier: Path) -> ModeleAero | None:
    """Le modèle, ou ``None`` après avoir dit comment construire le module."""
    try:
        return ModeleAero(module, dossier=dossier, sondes=True)  # les tests de tables lisent les sondes
    except ModuleNotFoundError as erreur:
        print(f"{erreur}\n  → cd {PYTHON} && bash construire.sh", file=sys.stderr)
        return None


def metadonnees(modele: ModeleAero, scenario: str) -> dict[str, str]:
    """Ce qui identifie le code testé, repris en tête du rapport."""
    chemin = modele.bibliotheque.__file__
    sha = hashlib.sha256(Path(chemin).read_bytes()).hexdigest()[:16] if chemin else "?"
    return {
        "code": "modele_aero (exemple cfd-validation)",
        "module": f"{modele.bibliotheque.__name__} — sha256 {sha}…",
        "constantes": ", ".join(f"{k}={DEFAUTS[k]}" for k in modele.arguments_init),
        "scénario": scenario,
    }
