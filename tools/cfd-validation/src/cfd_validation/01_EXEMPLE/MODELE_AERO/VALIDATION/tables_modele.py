"""Les tables du modèle aéro, déclarées une fois pour tous les tests de validation.

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
| alpha_rad (DCZR)    | extrapole (comme alpha : c'est le même angle)         |
| abeta (DCXB)        | inatteignable sous 0 (valeur absolue), extrapole au-delà |

Deux tables à lecture **indirecte**, les cas pratiques de construction
(``DOC/01_SOURCES.md`` §4.4) :

- **DCZR** est tabulée en alpha **en radians**, alors que AERCAL reçoit des
  degrés. L'axe porte donc son propre nom (``alpha_rad``, pas ``alpha`` : une
  colonne nommée comme une entrée y serait injectée telle quelle, en radians
  dans une entrée en degrés) et ``vers_entrees`` fait la conversion inverse de
  celle du code : ``alpha = degrees(alpha_rad)``. L'aller-retour degrés →
  radians ne retombe pas toujours au bit près sur le nœud, d'où une tolérance
  déclarée et justifiée. Cas inverse (table en degrés, code en radians) :
  ``{"alpha_rad": np.radians(df["alpha"])}``.
- **DCXB** est tabulée en ``|beta|`` : le code lit ``ABS(BETA)``. Une seule
  déclaration ne verrait que la moitié du domaine ; on la déclare **deux fois**,
  mêmes valeurs et même sonde, ``beta = +|beta|`` puis ``beta = −|beta|``
  (``DCXB_NEG``) : c'est la seconde qui prouve que le code prend bien la valeur
  absolue, y compris au-delà de la borne (|beta| > 10 par β < −10). Côté min,
  ``|beta| < 0`` n'existe pas : ``inatteignable``.
"""

from __future__ import annotations

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
from modele_f2py import ErreurModele  # noqa: E402

__all__ = [
    "DEFAUTS",
    "LIBELLES",
    "POLAIRES",
    "PYTHON",
    "ModeleAero",
    "beta_negatif",
    "beta_positif",
    "charger_modele",
    "declarer_tables",
    "metadonnees",
    "polaire_vers_cartesien",
    "radians_vers_degres",
]

#: Valeur de chaque argument Fortran quand la table ne le pilote pas : **celles du
#: modèle**, rien à réécrire ici — ModeleAero.DEFAUTS pour les phases d'init (AERINI,
#: AERCFG), ModeleAero.DEFAUTS_CALCUL pour AERCAL (PYTHON/modele_aero.py).
#: charger_modele refuse un modèle qui n'en donne pas une par argument.
#: Pour une valeur propre à la validation : {**ModeleAero.defauts_complets(), "biaicx": 0.005}.
DEFAUTS: dict[str, Any] = ModeleAero.defauts_complets()

#: Libellé (mathtext) et unité de chaque axe et de chaque table sur les figures.
LIBELLES: dict[str, str | tuple[str, str]] = {
    "mach": "Mach", "alpha": (r"$\alpha$", "°"), "beta": (r"$\beta$", "°"),
    "alphat": (r"$\alpha_T$", "°"), "phia": (r"$\varphi_A$", "°"),
    "dm": (r"$\delta_m$", "°"), "dn": (r"$\delta_n$", "°"),
    "CX": "$C_X$", "CY": "$C_Y$", "CZ": "$C_Z$", "CL": "$C_l$", "CM": "$C_m$", "CN": "$C_n$",
    "DCXP": r"$\Delta C_{X,\mathrm{prop}}$", "DCMG": r"$\Delta C_{m,\mathrm{gouv}}$",
    "alpha_rad": (r"$\alpha$", "rad"), "abeta": (r"$|\beta|$", "°"),
    "DCZR": r"$\Delta C_{Z,\mathrm{voil}}$", "DCXB": r"$\Delta C_{X,\beta}$",
    "DCXB_NEG": r"$\Delta C_{X,\beta}\ (\beta < 0)$",
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


def radians_vers_degres(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """DCZR : la table est en radians, AERCAL reçoit des degrés — l'inverse de ``ALPHA / DEG``."""
    return {"alpha": np.degrees(df["alpha_rad"].to_numpy())}


def beta_positif(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """DCXB : |beta| → beta, côté positif."""
    return {"beta": df["abeta"].to_numpy()}


def beta_negatif(df: pd.DataFrame) -> dict[str, np.ndarray]:
    """DCXB_NEG : |beta| → beta, côté négatif (0.0 − x : pas de −0)."""
    return {"beta": 0.0 - df["abeta"].to_numpy()}


def declarer_tables(
    modele: ModeleAero, *, cm_faussee: bool = False, consigne_cx_alpha: str | None = None
) -> list[TableReference]:
    """Les 11 déclarations (10 tables, DCXB des deux côtés) du modèle.

    ``cm_faussee`` : une valeur de CM modifiée côté référence (test 1, ``--defaut``) ;
    ``consigne_cx_alpha`` : remplace la consigne d'alpha de CX (test 2, ``--defaut``).
    """
    lire = modele.lire
    mach_alpha = {"mach": lire("aertab.tmach"), "alpha": lire("aertab.talpha")}
    mach_beta = {"mach": lire("aertab.tmach"), "beta": lire("aertab.tbeta")}

    tcm = lire("aertab.tcm")
    if cm_faussee:
        tcm[3, 4] += 1e-3
    bornes_cx = {**MACH_ALPHA, "alpha": consigne_cx_alpha} if consigne_cx_alpha else MACH_ALPHA

    return [
        TableReference("CX", lire("aertab.tcx"), mach_alpha, sonde="valid_tab_cx", bornes=bornes_cx,
                       description="force axiale au point de référence"),
        TableReference("CZ", lire("aertab.tcz"), mach_alpha, sonde="valid_tab_cz", bornes=MACH_ALPHA,
                       description="force normale au point de référence"),
        TableReference("CM", tcm, mach_alpha, sonde="valid_tab_cm", bornes=MACH_ALPHA,
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
        # Table en radians, entrée en degrés : l'axe garde son nom, vers_entrees convertit.
        TableReference("DCZR", lire("aertab.tdczr"), {"mach": lire("aertab.tmach"), "alpha_rad": lire("aertab.talfr")},
                       sonde="valid_tab_dczr", vers_entrees=radians_vers_degres,
                       bornes={"mach": "sature", "alpha_rad": "extrapole"},
                       rtol=1e-12, atol=1e-15,
                       justification=(
                           "alpha_rad → degrés (numpy) → radians (ALPHA / DEG dans le code) ne retombe pas "
                           "toujours au bit près : ~9 % des angles de [-0.35, 0.35] ratent d'1 ULP (les 7 nœuds "
                           "passent, par chance ; bornes et interpolation montrent 1 à 2 ULP sur la valeur). "
                           "1 ULP d'angle fois la pente reste sous 1e-15 ; 1e-12 relatif laisse un facteur 1000."
                       ),
                       description="incrément de CZ de la voilure, tabulé en alpha en radians"),
        # Table en |beta| : déclarée des deux côtés, même table, même sonde.
        *(TableReference(nom, lire("aertab.tdcxb"), {"mach": lire("aertab.tmach"), "abeta": lire("aertab.tabeta")},
                         sonde="valid_tab_dcxb", vers_entrees=vers_beta,
                         bornes={"mach": "sature", "abeta": ("inatteignable", "extrapole")},
                         description=f"incrément de CX en dérapage, tabulé en |beta| — lu par beta {signe} 0")
          for nom, vers_beta, signe in (("DCXB", beta_positif, ">"), ("DCXB_NEG", beta_negatif, "<"))),
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


def charger_modele(module: str, dossier: Path) -> ModeleAero | None:
    """Le modèle, ou ``None`` après avoir dit comment construire le module."""
    try:
        modele = ModeleAero(module, dossier=dossier, sondes=True)  # les tests de tables lisent les sondes
    except ModuleNotFoundError as erreur:
        print(f"{erreur}\n  → cd {PYTHON} && bash construire.sh", file=sys.stderr)
        return None
    except ErreurModele as erreur:
        print(f"erreur : {erreur}", file=sys.stderr)
        return None
    manquants = [n for n in modele.colonnes_obligatoires if n not in DEFAUTS]
    if manquants:  # chaque test pilote les arguments que ses tables ne pilotent pas
        print(f"erreur : pas de valeur par défaut pour {', '.join(manquants)} — à déclarer dans "
              "ModeleAero.DEFAUTS (init) ou ModeleAero.DEFAUTS_CALCUL (calcul), PYTHON/modele_aero.py",
              file=sys.stderr)
        return None
    return modele


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
