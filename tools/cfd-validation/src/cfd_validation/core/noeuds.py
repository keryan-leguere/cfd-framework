"""Les nœuds d'une table à N dimensions : forme, orientation, ordre de lecture.

**Orientation.** Une table se déclare avec ses axes dans l'ordre des indices du
Fortran : ``TCX(NM, NA)`` a pour premier axe le Mach, pour second l'incidence.
f2py rend un tableau de même forme, ``[i, j]`` valant ``TCX(I+1, J+1)``. La
seule vérification possible est la forme — chaque axe a la taille de sa grille
— et elle ne suffit pas sur une table **carrée** : déclarer (alpha, mach) au
lieu de (mach, alpha) sur un 7 × 7 passe la vérification et lit la table
transposée. C'est le test lui-même qui le révèle (les valeurs ne collent pas),
pas la forme ; d'où l'ordre de déclaration comme seule convention.

**Ordre de lecture.** Les nœuds sont parcourus dans l'ordre mémoire du Fortran,
premier indice le plus rapide — celui des instructions ``DATA`` : la k-ième
valeur listée dans le source est le k-ième point des figures et des CSV.
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence

import numpy as np
from numpy.typing import NDArray

__all__ = ["coordonnees_noeuds", "decrire_forme", "verifier_forme", "verifier_grille"]


def decrire_forme(forme: Sequence[int]) -> str:
    """``2D 7×7``, ``5D 5×5×5×5×5``, ``1D 7``."""
    return f"{len(forme)}D " + "×".join(str(n) for n in forme)


def verifier_grille(nom: str, grille: NDArray[np.float64]) -> None:
    """Une grille est un vecteur fini, non vide, strictement croissant."""
    if grille.ndim != 1 or grille.size == 0:
        raise ValueError(f"grille {nom} : un vecteur non vide est attendu, forme {grille.shape}")
    if not np.all(np.isfinite(grille)):
        raise ValueError(f"grille {nom} : valeur non finie")
    if grille.size > 1 and not np.all(np.diff(grille) > 0):
        raise ValueError(f"grille {nom} : pas strictement croissante ({grille.tolist()})")


def verifier_forme(nom: str, forme: Sequence[int], tailles: Mapping[str, int]) -> None:
    """La table ``nom`` a-t-elle une forme compatible avec ses axes, dans l'ordre déclaré ?

    En cas d'écart, le message donne un ordre d'axes qui irait, s'il en existe un.
    """
    attendue = tuple(tailles.values())
    forme = tuple(int(n) for n in forme)
    if forme == attendue:
        return
    declares = ", ".join(f"{a} ({n})" for a, n in tailles.items())
    message = f"table {nom} : forme {decrire_forme(forme)}, axes déclarés {declares}"
    if len(forme) != len(attendue):
        raise ValueError(f"{message} — {len(forme)} dimensions contre {len(attendue)} axes")
    for ordre in itertools.permutations(tailles):
        if tuple(tailles[a] for a in ordre) == forme:
            raise ValueError(
                f"{message} — axes à déclarer dans l'ordre des indices Fortran ? essayer ({', '.join(ordre)})"
            )
    raise ValueError(f"{message} — aucun ordre des axes ne correspond")


def coordonnees_noeuds(grilles: Sequence[NDArray[np.float64]]) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    """Indices ``(n, d)`` et coordonnées ``(n, d)`` des nœuds, premier axe le plus rapide.

    ``valeurs.ravel(order="F")`` donne les valeurs de la table dans le même ordre.
    """
    forme = tuple(len(g) for g in grilles)
    n = int(np.prod(forme)) if forme else 0
    indices = np.stack(np.unravel_index(np.arange(n), forme, order="F"), axis=1).astype(np.int64)
    coords = np.empty(indices.shape, dtype=np.float64)
    for d, g in enumerate(grilles):
        coords[:, d] = np.asarray(g, dtype=np.float64)[indices[:, d]]
    return indices, coords
