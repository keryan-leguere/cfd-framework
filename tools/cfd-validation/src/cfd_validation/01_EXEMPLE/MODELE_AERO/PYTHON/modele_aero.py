"""Le modèle aéro vu de Python : la seule partie propre à ce code.

    from modele_aero import ModeleAero

    modele = ModeleAero()                    # aerini(xref, yref, zref, lref) appelé ici
    modele = ModeleAero(lref=0.25)           # une constante changée, sans toucher au Fortran
    modele.calculer(mach=0.8, alpha=5.0, beta=0.0, xg=1.1, yg=0.0, zg=0.0, ipropu=1, dm=0.0, dn=0.0)
    df_sortie = modele.calculer_df(df)       # colonnes mach … dn → + cx … cn, ierr, sondes
    modele.lire("aertab.tcx")                # une table, telle que le code la voit

Tout le mécanisme est dans ``modele_f2py.py`` ; les noms d'arguments viennent
de la docstring f2py (``aerolib.aercal.__doc__``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from modele_f2py import ModeleF2py

# Codes IERR de AERCAL (SOURCES/aero_modele.f)
IERR_NOMINAL = 0
IERR_NON_INITIALISE = 1
IERR_HORS_DOMAINE = 2
IERR_IPROPU = 3


class ModeleAero(ModeleF2py):
    """AERINI puis AERCAL ; constantes par défaut : point de référence et LREF des tables."""

    BIBLIOTHEQUE: ClassVar[str] = "aerolib"
    DOSSIER: ClassVar[str | Path | None] = Path(__file__).resolve().parent
    PHASES_INIT: ClassVar[tuple[str, ...]] = ("aerini",)
    PHASE_CALCUL: ClassVar[str] = "aercal"
    CONSTANTES: ClassVar[dict[str, Any]] = {"xref": 1.2, "yref": 0.0, "zref": 0.0, "lref": 0.2}
    # COMMON /PROBE/ (SOURCES/aero_probe.inc) : valid_tab_cx … valid_tab_dcmg
    SONDES: ClassVar[tuple[str, ...]] = ("probe",)
