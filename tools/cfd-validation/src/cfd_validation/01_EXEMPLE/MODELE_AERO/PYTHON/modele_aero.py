"""Le modèle aéro vu de Python : la surcouche propre à ce code.

    from modele_aero import ModeleAero

    modele = ModeleAero()                          # charge aerolib, rien d'autre
    sortie = modele.calcul_aero(df)                # paramètres standard → sorties + colonnes en plus
    modele.calcul_aero(df, csv="resultats.csv")    # idem, et écrit en CSV
    brut = modele.calcul_aero_elementaire(df_f)    # arguments Fortran tels quels → sorties + sondes
    modele.lire("aertab.tcx")                      # une table, telle que le code la voit

Deux niveaux :

- ``calcul_aero_elementaire(df)`` : une colonne par argument de AERINI, AERCFG
  et AERCAL, dans les unités et conventions du Fortran (CDG en m en axes corps
  FRD, ``ipropu`` 0/1, ``xref`` … ``lref``, ``biaicx``). Rien entre le code et l'appelant :
  c'est par là que passe la validation. Les arguments des phases d'init
  (``xref`` … ``lref``, ``biaicx``) sont facultatifs : absents, ou vides sur une
  ligne, ils prennent ``DEFAUTS`` ; ceux de AERCAL restent obligatoires.
- ``calcul_aero(df)`` : les paramètres tels qu'on les donne d'habitude
  (``PARAMETRES``), convertis en arguments élémentaires par
  ``vers_elementaire``, puis les sorties complétées par ``completer_sorties``
  (nom et version du modèle, état lisible de IERR…). C'est là qu'on ajoute
  toute grandeur à retrouver dans le vecteur de sortie.

Pour un autre code : garder la forme, réécrire ``vers_elementaire`` et
``completer_sorties``.
"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar

import pandas as pd
from modele_f2py import ErreurModele, ModeleF2py, ecrire_csv

# Codes IERR de AERCAL (SOURCES/aero_modele.f)
IERR_NOMINAL = 0
IERR_NON_INITIALISE = 1
IERR_HORS_DOMAINE = 2
IERR_IPROPU = 3
ETATS = {
    IERR_NOMINAL: "nominal",
    IERR_NON_INITIALISE: "non initialisé (AERINI absente ou refusée)",
    IERR_HORS_DOMAINE: "hors grille (saturé ou extrapolé)",
    IERR_IPROPU: "ipropu invalide",
}


class ModeleAero(ModeleF2py):
    """AERINI, AERCFG puis AERCAL, et la surcouche ``calcul_aero``."""

    BIBLIOTHEQUE: ClassVar[str] = "aerolib"
    DOSSIER: ClassVar[str | Path | None] = Path(__file__).resolve().parent
    PHASES_INIT: ClassVar[tuple[str, ...]] = ("aerini", "aercfg")  # constantes, puis configuration
    PHASE_CALCUL: ClassVar[str] = "aercal"
    # COMMON /PROBE/ (SOURCES/aero_probe.inc) : valid_tab_cx … valid_tab_dcmg
    SONDES: ClassVar[tuple[str, ...]] = ("probe",)

    NOM: ClassVar[str] = "MODELE_AERO"
    VERSION: ClassVar[str] = "1.0"

    #: Paramètres de ``calcul_aero`` et leur sens.
    PARAMETRES: ClassVar[dict[str, str]] = {
        "mach": "nombre de Mach",
        "alpha": "incidence (deg)",
        "beta": "dérapage (deg)",
        "xg_mm": "CDG, axes corps FLU : x vers l'avant (mm)",
        "yg_mm": "CDG, axes corps FLU : y vers la gauche (mm)",
        "zg_mm": "CDG, axes corps FLU : z vers le haut (mm)",
        "propulsion": "propulsion allumée (booléen)",
        "dm": "braquage de profondeur (deg)",
        "dn": "braquage de direction (deg)",
    }
    #: Phases d'init (AERINI, AERCFG) : valeurs prises par les deux calculs quand la
    #: colonne est absente — le point de référence des moments des tables (m, FRD),
    #: leur longueur de référence (m), et le biais de configuration sur CX.
    DEFAUTS: ClassVar[dict[str, Any]] = {"xref": 1.2, "yref": 0.0, "zref": 0.0, "lref": 0.2, "biaicx": 0.0}
    #: Phase de calcul (AERCAL) : **jamais utilisées pour calculer** (un point de vol
    #: s'écrit en entier). C'est le point où une table ne pilote pas l'argument, repris
    #: tel quel par la validation (VALIDATION/tables_modele.py) : CDG au point de
    #: référence, donc rien à transporter ; propulsion éteinte, gouvernes au neutre.
    DEFAUTS_CALCUL: ClassVar[dict[str, Any]] = {
        "mach": 0.8, "alpha": 0.0, "beta": 0.0,
        "xg": 1.2, "yg": 0.0, "zg": 0.0,
        "ipropu": 0, "dm": 0.0, "dn": 0.0,
    }

    def __init__(
        self,
        bibliotheque: ModuleType | str | None = None,
        dossier: str | Path | None = None,
        *,
        sondes: bool | None = None,
    ) -> None:
        # Sans argument : aerolib, à côté de ce fichier. Les deux premiers ne servent
        # qu'à charger une autre compilation (aerolib_o3…) ; l'init Fortran est faite par le calcul.
        # sondes : None = COMMON /PROBE/ s'il existe, True = exigé, False = ignoré (ModeleF2py).
        super().__init__(bibliotheque, dossier, sondes=sondes)

    # -- niveau élémentaire : le Fortran tel quel ----------------------------

    def calcul_aero_elementaire(self, entrees: pd.DataFrame, *, csv: str | Path | None = None) -> pd.DataFrame:
        """Colonnes mach … dn (xref … lref, biaicx : ``DEFAUTS`` si absentes) → l'entrée + cx … cn, ierr, sondes.

        ``csv`` : aussi en fichier.
        """
        return self.calcul_elementaire(self.completer_init(entrees), csv=csv)

    # -- niveau standard : conversions, puis sorties en plus -----------------

    def vers_elementaire(self, entrees: pd.DataFrame) -> pd.DataFrame:
        """Paramètres standard → arguments de AERINI / AERCAL (les autres colonnes suivent)."""
        melange = sorted({"xg", "yg", "zg", "ipropu"} & set(entrees.columns))
        if melange:
            raise ErreurModele(
                f"{', '.join(melange)} : argument(s) Fortran dans les paramètres standard — "
                f"donner {', '.join(self.PARAMETRES)} ou passer par calcul_aero_elementaire"
            )
        manquants = [p for p in self.PARAMETRES if p not in entrees.columns]
        if manquants:
            raise ErreurModele(f"paramètre(s) absent(s) : {', '.join(manquants)}")
        df = self.completer_init(entrees)  # xref … lref, biaicx : le défaut s'ils manquent
        # FLU (mm) → FRD (m) : y et z changent de signe
        df["xg"] = df["xg_mm"] / 1000.0
        df["yg"] = 0.0 - df["yg_mm"] / 1000.0  # 0.0 − x et non −x : pas de −0 dans le CSV
        df["zg"] = 0.0 - df["zg_mm"] / 1000.0
        df["ipropu"] = df["propulsion"].astype(bool).astype("int64")
        return df

    def completer_sorties(self, sortie: pd.DataFrame) -> pd.DataFrame:
        """Ce qu'on veut retrouver en plus des sorties du code et des sondes."""
        sortie = sortie.copy()
        sortie["etat"] = sortie["ierr"].map(ETATS).fillna("code inconnu")
        sortie["modele"] = self.NOM
        sortie["version"] = self.VERSION
        sortie["bibliotheque"] = self.bibliotheque.__name__
        return sortie

    def calcul_aero(self, entrees: pd.DataFrame, *, csv: str | Path | None = None) -> pd.DataFrame:
        """Paramètres standard (``PARAMETRES``, ``DEFAUTS`` facultatifs) → sorties complètes (``csv`` : aussi en fichier)."""
        sortie = self.completer_sorties(self.calcul_aero_elementaire(self.vers_elementaire(entrees)))
        if csv is not None:
            ecrire_csv(sortie, csv)
        return sortie
