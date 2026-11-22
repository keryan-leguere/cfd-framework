"""Entre les nœuds d'une table : points dans les mailles, abscisses d'une polaire.

Une **maille** d'un axe est l'intervalle ``[g[i], g[i+1]]`` entre deux nœuds
consécutifs. Un point y est placé par sa **fraction** ``t`` :
``x = (1 − t)·g[i] + t·g[i+1]``, la forme même de l'interpolation linéaire, si
bien que ``t = 0`` et ``t = 1`` retombent exactement sur les nœuds.

Une **polaire** parcourt un axe de part en part, au-delà de ses bornes : les
nœuds, ``subdivisions − 1`` points dans chaque maille, et un prolongement de
``ecart × étendue`` de chaque côté (rien d'un côté marqué inatteignable).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

__all__ = ["abscisses_polaire", "points_mailles", "verifier_fractions"]


def verifier_fractions(fractions: Sequence[float]) -> tuple[float, ...]:
    """Les fractions, triées et sans doublon ; chacune strictement dans ]0, 1[."""
    vues = sorted({float(f) for f in fractions})
    if not vues:
        raise ValueError("aucune fraction : il en faut au moins une dans ]0, 1[")
    hors = [f for f in vues if not 0.0 < f < 1.0]
    if hors:
        raise ValueError(f"fraction(s) {hors} : chacune doit être strictement entre 0 et 1 (0 et 1 sont des nœuds)")
    return tuple(vues)


def points_mailles(
    grille: NDArray[np.float64], fractions: Sequence[float]
) -> tuple[NDArray[np.float64], NDArray[np.int64], NDArray[np.float64]]:
    """``(x, i, t)`` : chaque fraction dans chaque maille, maille après maille.

    ``i`` est l'indice (base 0) du nœud bas de la maille, ``t`` la fraction.
    """
    g = np.asarray(grille, dtype=np.float64)
    if len(g) < 2:
        raise ValueError("un axe d'un seul nœud n'a pas de maille")
    f = np.asarray(verifier_fractions(fractions))
    i = np.repeat(np.arange(len(g) - 1), len(f))
    t = np.tile(f, len(g) - 1)
    x = (1.0 - t) * g[i] + t * g[i + 1]
    return x, i.astype(np.int64), t


def abscisses_polaire(
    grille: NDArray[np.float64],
    *,
    subdivisions: int = 8,
    ecart_min: float = 0.10,
    ecart_max: float = 0.10,
    points_hors: int = 8,
) -> NDArray[np.float64]:
    """Les abscisses d'une polaire : nœuds, mailles subdivisées, prolongements.

    ``ecart_min`` / ``ecart_max`` : prolongement de chaque côté en fraction de
    l'étendue (0 : aucun, pour un côté inatteignable) ; ``points_hors`` points
    régulièrement espacés dans chaque prolongement, la borne exclue.
    """
    g = np.asarray(grille, dtype=np.float64)
    if len(g) < 2:
        raise ValueError("un axe d'un seul nœud n'a pas de polaire")
    if subdivisions < 1 or points_hors < 1:
        raise ValueError("subdivisions et points_hors : au moins 1")
    if ecart_min < 0 or ecart_max < 0:
        raise ValueError("un prolongement ne peut pas être négatif")
    etendue = float(g[-1] - g[0])
    morceaux = [g]
    if subdivisions > 1:
        t = np.arange(1, subdivisions) / subdivisions
        morceaux.append(((1.0 - t)[None, :] * g[:-1, None] + t[None, :] * g[1:, None]).ravel())
    pas = np.arange(1, points_hors + 1) / points_hors
    if ecart_min > 0:
        morceaux.append(g[0] - pas * ecart_min * etendue)
    if ecart_max > 0:
        morceaux.append(g[-1] + pas * ecart_max * etendue)
    return np.unique(np.concatenate(morceaux))
