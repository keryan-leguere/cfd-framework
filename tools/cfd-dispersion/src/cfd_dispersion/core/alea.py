"""Maîtrise du générateur aléatoire d'OpenTURNS.

OpenTURNS n'expose pas de générateur par appel : il n'y a qu'un **état
global**, piloté par ``ot.RandomGenerator.SetSeed / GetState / SetState``.
C'est la différence la plus visible avec ``numpy.random.Generator``, et elle a
une conséquence désagréable si on la laisse telle quelle : tirer une loi au
milieu d'un script décale la suite du flux aléatoire de l'appelant.

D'où :func:`graine_temporaire`, qui pose une graine puis **restitue l'état
d'origine** en sortant. Toutes les fonctions de tirage du paquet passent par
elle, si bien qu'un ``graine=`` reproductible ne coûte jamais la reproductibilité
de quelqu'un d'autre.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import numpy as np
import openturns as ot

__all__ = ["graine_temporaire", "vers_numpy"]


@contextmanager
def graine_temporaire(graine: int | None) -> Iterator[None]:
    """Pose *graine* le temps du bloc, puis restaure l'état antérieur.

    ``graine=None`` ne touche à rien : le flux global continue, ce qui est le
    comportement voulu quand l'appelant gère lui-même sa reproductibilité.

    Parameters
    ----------
    graine:
        Graine à poser, ou None pour laisser le générateur tel quel.

    Examples
    --------
    >>> with graine_temporaire(42):
    ...     x = ot.Normal().getSample(3)
    """
    if graine is None:
        yield
        return

    etat = ot.RandomGenerator.GetState()
    try:
        ot.RandomGenerator.SetSeed(int(graine))
        yield
    finally:
        ot.RandomGenerator.SetState(etat)


def vers_numpy(echantillon: object) -> np.ndarray:
    """Convertit un ``ot.Sample`` 1-D en tableau numpy de forme ``(n,)``.

    Deux corrections, toutes deux nécessaires :

    ``Distribution.getSample(n)`` rend un ``Sample`` de forme ``(n, 1)``, pas
    ``(n,)`` : un point par ligne, même en dimension 1. Sans l'aplatissement,
    ce ``(n, 1)`` se diffuse contre un balayage ``(npts,)`` et produit un
    ``(n, npts)`` d'apparence plausible et faux.

    Et la conversion **copie** au lieu de partager la mémoire d'OpenTURNS :
    une vue sur le tampon du ``Sample`` arrive en lecture seule, si bien qu'un
    ``echantillon[0] = …`` parfaitement ordinaire échoue chez l'appelant. Un
    tableau rendu par ce paquet se manipule comme n'importe quel tableau numpy.
    """
    return np.array(echantillon, dtype=float).ravel()
