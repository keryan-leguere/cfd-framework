"""Attribuer les échecs aux entrées : sur quelle valeur d'entrée les écarts se concentrent-ils ?

Pour chaque entrée, on la **discrétise** en niveaux (ses valeurs distinctes
si elles sont peu nombreuses, des classes de quantiles sinon), puis on compte
les lignes en échec par niveau. Deux lectures :

- le **taux d'échec par niveau**, la pièce justificative : « 100 % des lignes
  à Mach 1.5 échouent, 0 % ailleurs » ;
- le **V de Cramér** entre le niveau et l'échec, un seul nombre dans [0, 1]
  pour classer les entrées : 0 si l'échec est indépendant de l'entrée, 1 s'il
  est entièrement déterminé par son niveau. Pour un tableau 2 × k,
  ``V = √(χ² / n)``.

Discrétiser est indispensable : une entrée continue dont chaque ligne a sa
propre valeur « explique » parfaitement n'importe quoi (k = n, V = 1). Le
plafond de niveaux tient ce biais en respect ; il reste sensible aux petits
effectifs (quelques dizaines de lignes), ce que le rapport rappelle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cfd_validation.core.format import formater

__all__ = [
    "MAX_NIVEAUX",
    "N_CLASSES",
    "Discretisation",
    "comptes_par_niveau",
    "discretiser",
    "v_cramer",
]

#: Au-delà de ce nombre de valeurs distinctes, une entrée numérique est découpée en classes.
MAX_NIVEAUX = 12
#: Nombre de classes de quantiles d'une entrée continue.
N_CLASSES = 8
_AUTRES = "autres"


@dataclass(frozen=True)
class Discretisation:
    """Niveau de chaque ligne (``codes``, indices dans ``libelles``)."""

    codes: NDArray[np.int64]
    libelles: tuple[str, ...]
    #: Vrai si les niveaux sont des classes (entrée continue), faux s'ils sont ses valeurs.
    en_classes: bool

    @property
    def n_niveaux(self) -> int:
        return len(self.libelles)


def _est_numerique(valeurs: NDArray[Any]) -> bool:
    return valeurs.dtype.kind in "iuf"


def discretiser(
    valeurs: NDArray[Any], *, max_niveaux: int = MAX_NIVEAUX, n_classes: int = N_CLASSES
) -> Discretisation:
    """Découpe une colonne d'entrée en niveaux.

    Numérique : ses valeurs distinctes s'il y en a au plus ``max_niveaux``,
    sinon ``n_classes`` classes de quantiles (bornes fusionnées si la
    distribution a des paliers). Autre : ses valeurs, les plus fréquentes
    d'abord, le reliquat regroupé sous « autres ». Les manquants forment leur
    propre niveau, ``NaN``.
    """
    if max_niveaux < 2 or n_classes < 2:
        raise ValueError("max_niveaux et n_classes doivent valoir au moins 2")
    v = np.asarray(valeurs)
    if _est_numerique(v):
        return _discretiser_numerique(v.astype(np.float64), max_niveaux, n_classes)
    return _discretiser_categories(v, max_niveaux)


def _discretiser_numerique(x: NDArray[np.float64], max_niveaux: int, n_classes: int) -> Discretisation:
    manquant = np.isnan(x)
    presentes = x[~manquant]
    codes = np.full(x.shape, -1, dtype=np.int64)
    distinctes = np.unique(presentes)
    if distinctes.size <= max_niveaux:
        codes[~manquant] = np.searchsorted(distinctes, x[~manquant])
        libelles = [formater(float(d), 6) for d in distinctes]
        en_classes = False
    else:
        bornes = np.unique(np.quantile(presentes, np.linspace(0.0, 1.0, n_classes + 1)))
        idx = np.searchsorted(bornes, x[~manquant], side="right") - 1
        codes[~manquant] = np.clip(idx, 0, bornes.size - 2)
        libelles = [
            f"[{formater(float(a), 4)} ; {formater(float(b), 4)}{']' if i == bornes.size - 2 else '['}"
            for i, (a, b) in enumerate(zip(bornes[:-1], bornes[1:]))
        ]
        en_classes = True
    if manquant.any():
        codes[manquant] = len(libelles)
        libelles.append("NaN")
    return Discretisation(codes=codes, libelles=tuple(libelles), en_classes=en_classes)


def _manquant(x: Any) -> bool:
    if x is None:
        return True
    try:
        return bool(x != x)
    except TypeError:  # pd.NA : sa comparaison n'a pas de valeur de vérité
        return True


def _discretiser_categories(v: NDArray[Any], max_niveaux: int) -> Discretisation:
    textes = np.array(["NaN" if _manquant(x) else str(x) for x in v], dtype=object)
    valeurs, comptes = np.unique(textes, return_counts=True)
    ordre = np.lexsort((valeurs, -comptes))  # plus fréquentes d'abord, puis alphabétique
    valeurs = valeurs[ordre]
    if valeurs.size > max_niveaux:
        gardees = list(valeurs[: max_niveaux - 1])
        libelles = (*gardees, _AUTRES)
    else:
        gardees = list(valeurs)
        libelles = tuple(gardees)
    rang = {nom: i for i, nom in enumerate(gardees)}
    codes = np.array([rang.get(t, len(gardees)) for t in textes], dtype=np.int64)
    return Discretisation(codes=codes, libelles=tuple(str(x) for x in libelles), en_classes=False)


def comptes_par_niveau(
    codes: NDArray[np.int64], echec: NDArray[np.bool_], n_niveaux: int
) -> tuple[NDArray[np.int64], NDArray[np.int64]]:
    """Effectif et nombre d'échecs de chaque niveau."""
    n = np.bincount(codes, minlength=n_niveaux).astype(np.int64)
    e = np.bincount(codes, weights=echec.astype(np.float64), minlength=n_niveaux)
    return n, np.rint(e).astype(np.int64)


def v_cramer(codes: NDArray[np.int64], echec: NDArray[np.bool_], n_niveaux: int) -> float:
    """V de Cramér du tableau (niveau × échec) ; NaN s'il est sans objet.

    Sans objet : moins de deux niveaux peuplés, ou aucune ligne (ou toutes) en
    échec — l'échec ne varie pas, il n'y a rien à attribuer.
    """
    n_niv, n_ech = comptes_par_niveau(codes, echec, n_niveaux)
    peuples = n_niv > 0
    n_niv, n_ech = n_niv[peuples], n_ech[peuples]
    total = int(n_niv.sum())
    total_echec = int(n_ech.sum())
    if n_niv.size < 2 or total_echec == 0 or total_echec == total:
        return math.nan
    observe = np.stack([n_ech, n_niv - n_ech]).astype(np.float64)
    attendu = np.outer([total_echec, total - total_echec], n_niv) / total
    chi2 = float(((observe - attendu) ** 2 / attendu).sum())
    return min(1.0, math.sqrt(chi2 / total))
