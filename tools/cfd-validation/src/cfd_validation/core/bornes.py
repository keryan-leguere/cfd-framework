"""Hors des bornes d'une table : consignes, points d'appel, valeur attendue.

Une **consigne** dit, pour chaque axe et chaque côté, ce que le code doit faire
d'un point au-delà de la grille :

- ``sature`` : la valeur au bord de la grille, comme si le point y était ;
- ``extrapole`` : le prolongement linéaire de la dernière maille ;
- ``inatteignable`` : aucune entrée du modèle ne produit un tel point (alphaT
  sous 0, qu'un ``acos`` ne rend jamais ; phiA hors de [−180, 180]) — le côté
  n'est pas testé, et le rapport le dit.

**Oracle.** L'interpolation multilinéaire ``Σ Π (1 − tₖ | tₖ) · V`` sur les
2ᵈ coins de la maille, où, pour chaque axe, ``(i, t)`` vient de la position du
point dans sa grille : dans la grille ``t ∈ [0, 1]`` ; au-delà, ``t`` est borné à
0 ou 1 (saturation) ou laissé hors de [0, 1] (extrapolation). Sur un nœud,
``t`` vaut exactement 0 ou 1, et la valeur de la table revient au bit près.

**Distance.** Le point hors bornes est à ``ecart × (max − min)`` au-delà de la
borne : une fraction de l'étendue de l'axe, qui a un sens quel que soit le
signe des bornes (« 10 % de la borne » n'en a pas pour alpha ∈ [−20, 20]).
"""

from __future__ import annotations

import itertools
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

__all__ = [
    "CONSIGNES",
    "COTES",
    "EXTRAPOLE",
    "INATTEIGNABLE",
    "SATURE",
    "interpoler",
    "point_hors_bornes",
]

SATURE = "sature"
EXTRAPOLE = "extrapole"
INATTEIGNABLE = "inatteignable"
CONSIGNES = (SATURE, EXTRAPOLE, INATTEIGNABLE)
COTES = ("min", "max")


def point_hors_bornes(grille: NDArray[np.float64], cote: str, ecart: float) -> float:
    """La coordonnée à ``ecart × étendue`` au-delà de la borne ``cote`` de ``grille``."""
    if cote not in COTES:
        raise ValueError(f"côté {cote!r} : attendu min ou max")
    if not ecart > 0:
        raise ValueError(f"écart {ecart!r} : un nombre strictement positif est attendu")
    etendue = float(grille[-1] - grille[0])
    if etendue <= 0:
        raise ValueError("grille d'un seul point : pas d'étendue, pas de point hors bornes")
    return float(grille[0] - ecart * etendue) if cote == "min" else float(grille[-1] + ecart * etendue)


def _poids(grille: NDArray[np.float64], x: NDArray[np.float64], regles: tuple[str, str]) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    """Maille ``i`` et poids ``t`` de chaque ``x`` : ``x = (1 − t)·g[i] + t·g[i+1]``."""
    n = len(grille)
    i = np.clip(np.searchsorted(grille, x, side="right") - 1, 0, n - 2)
    i[x >= grille[-1]] = n - 2  # le dernier nœud : t = 1 dans la dernière maille, comme le code
    t = (x - grille[i]) / (grille[i + 1] - grille[i])
    t[x == grille[-1]] = 1.0
    t[x == grille[i]] = 0.0
    dessous, dessus = x < grille[0], x > grille[-1]
    if regles[0] == SATURE:
        t[dessous] = 0.0
    if regles[1] == SATURE:
        t[dessus] = 1.0
    return i.astype(np.int64), t


def interpoler(
    valeurs: NDArray[np.float64],
    grilles: Sequence[NDArray[np.float64]],
    points: NDArray[np.float64],
    regles: Sequence[tuple[str, str]],
) -> NDArray[np.float64]:
    """Valeur multilinéaire de la table en chaque point ``(n, d)``, avec la règle de bord de chaque axe.

    ``regles[k] = (côté min, côté max)``, chacun ``sature`` ou ``extrapole``.
    """
    points = np.atleast_2d(np.asarray(points, dtype=np.float64))
    d = len(grilles)
    if points.shape[1] != d or len(regles) != d:
        raise ValueError(f"{points.shape[1]} coordonnées et {len(regles)} règles pour {d} axes")
    if any(len(g) < 2 for g in grilles):
        raise ValueError("chaque axe doit avoir au moins deux nœuds")
    mailles = [_poids(np.asarray(g, dtype=np.float64), points[:, k], tuple(regles[k]))  # type: ignore[arg-type]
               for k, g in enumerate(grilles)]
    somme = np.zeros(len(points))
    for coin in itertools.product((0, 1), repeat=d):
        poids = np.ones(len(points))
        indices = []
        for (i, t), b in zip(mailles, coin):
            poids = poids * (t if b else (1.0 - t))
            indices.append(i + b)
        somme = somme + poids * valeurs[tuple(indices)]
    return somme
