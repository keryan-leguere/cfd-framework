"""Déclaration d'une table de référence pour le test de lecture de table.

Une table, c'est :

- ses **valeurs**, un tableau à N dimensions tel que le code le voit (pour un
  code encapsulé par f2py, la variable du COMMON rempli par le BLOCK DATA) ;
- ses **axes**, dans l'ordre des indices Fortran, chacun avec sa grille ;
- la **sonde**, la colonne que l'évaluateur rend avec la valeur lue par le code ;
- le passage des colonnes de la table aux **entrées du modèle** : direct quand
  une colonne porte le nom d'une entrée, sinon par ``vers_entrees`` (la relation
  inverse : (alphaT, phiA) → (alpha, beta)) ;
- les entrées **fixées** pour cette table (``ipropu = 1`` pour qu'une table de
  propulsion soit seulement lue) ;
- la tolérance et sa justification — par défaut l'identité bit pour bit, ce que
  doit rendre une interpolation dont les poids valent 0 ou 1 sur un nœud.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from cfd_validation.core.noeuds import (
    coordonnees_noeuds,
    decrire_forme,
    verifier_forme,
    verifier_grille,
)
from cfd_validation.core.tolerance import ORIGINE_DECLAREE, ORIGINE_DEFAUT, Tolerance
from cfd_validation.data.specification import ErreurSpecification

__all__ = ["JUSTIFICATION_NOEUD", "ErreurTable", "Inversion", "TableReference"]

#: Justification de la tolérance par défaut (identité bit pour bit).
JUSTIFICATION_NOEUD = (
    "Sur un nœud, les poids d'interpolation valent exactement 0 ou 1 : "
    "le code doit rendre la valeur de la table au bit près."
)

#: ``vers_entrees(df_axes) -> {entrée: valeurs}`` : colonnes de la table → entrées du modèle.
Inversion = Callable[[pd.DataFrame], Mapping[str, Any]]


class ErreurTable(ErreurSpecification):
    """Une table mal déclarée (forme, axes, sonde, entrées)."""


@dataclass(frozen=True)
class TableReference:
    """Une table à relire sur ses nœuds.

    Parameters
    ----------
    nom
        Nom de la table dans le rapport et les fichiers (``CX``, ``DCMG``).
    valeurs
        Tableau à N dimensions, axes dans l'ordre des indices Fortran.
    axes
        ``{colonne: grille}``, dans l'ordre des indices. Une colonne qui porte le
        nom d'une entrée du modèle y est injectée telle quelle.
    sonde
        Colonne rendue par l'évaluateur avec la valeur lue par le code.
    vers_entrees
        ``f(df) -> {entrée: valeurs}``, ``df`` ayant une colonne par axe et une
        ligne par nœud : reconstruit les entrées du modèle quand les colonnes de
        la table n'en sont pas (``alphat`` → ``alpha``, ``beta``).
    fixes
        Entrées imposées pour cette table, par-dessus les défauts.
    rtol, atol, justification
        Tolérance ; par défaut identité bit pour bit (``JUSTIFICATION_NOEUD``).
    description
        Ce que la table représente, repris dans le rapport.
    """

    nom: str
    valeurs: Any
    axes: Mapping[str, Any]
    sonde: str
    vers_entrees: Inversion | None = None
    fixes: Mapping[str, Any] = field(default_factory=dict)
    rtol: float | None = None
    atol: float | None = None
    justification: str | None = None
    description: str = ""

    def __post_init__(self) -> None:
        if not self.nom or not str(self.nom).strip():
            raise ErreurTable("une table sans nom")
        if not self.sonde:
            raise ErreurTable(f"table {self.nom} : sonde non déclarée")
        if not self.axes:
            raise ErreurTable(f"table {self.nom} : aucun axe déclaré")
        try:
            valeurs = np.array(self.valeurs, dtype=np.float64, copy=True)
            grilles = {str(a): np.array(g, dtype=np.float64, copy=True).ravel() for a, g in self.axes.items()}
            for a, g in grilles.items():
                verifier_grille(f"{a} (table {self.nom})", g)
            verifier_forme(self.nom, valeurs.shape, {a: len(g) for a, g in grilles.items()})
        except (TypeError, ValueError) as erreur:
            raise ErreurTable(str(erreur)) from None
        if len(grilles) != len(self.axes):
            raise ErreurTable(f"table {self.nom} : noms d'axes en double")
        object.__setattr__(self, "valeurs", valeurs)
        object.__setattr__(self, "axes", grilles)
        object.__setattr__(self, "fixes", dict(self.fixes))
        try:
            self.tolerance  # noqa: B018 — valide rtol/atol dès la déclaration
        except (TypeError, ValueError) as erreur:
            raise ErreurTable(f"table {self.nom} : {erreur}") from None

    @property
    def grilles(self) -> tuple[NDArray[np.float64], ...]:
        return tuple(self.axes.values())

    @property
    def noms_axes(self) -> tuple[str, ...]:
        return tuple(self.axes)

    @property
    def forme(self) -> tuple[int, ...]:
        return tuple(len(g) for g in self.grilles)

    @property
    def n_noeuds(self) -> int:
        return int(np.prod(self.forme))

    @property
    def decrire_forme(self) -> str:
        return decrire_forme(self.forme)

    @property
    def tolerance(self) -> Tolerance:
        if self.rtol is None and self.atol is None:
            return Tolerance(0.0, 0.0, self.justification or JUSTIFICATION_NOEUD, ORIGINE_DEFAUT)
        return Tolerance(
            float(self.rtol or 0.0), float(self.atol or 0.0), self.justification, ORIGINE_DECLAREE
        )

    def table_plate(self) -> pd.DataFrame:
        """Une ligne par nœud, ordre de lecture Fortran : colonnes des axes, puis ``valeur``."""
        _, coords = coordonnees_noeuds(self.grilles)
        df = pd.DataFrame(coords, columns=list(self.noms_axes))
        df["valeur"] = np.asarray(self.valeurs).ravel(order="F")
        return df
