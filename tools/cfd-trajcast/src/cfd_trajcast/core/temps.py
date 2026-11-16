"""Temps vidéo → temps de vol : vitesse de lecture constante ou ralentis.

La vitesse de lecture ``v`` est le nombre de secondes de vol montrées par seconde
de vidéo (1 = temps réel, 0,25 = ralenti ×4). Un **ralenti** fixe ``v`` sur un
intervalle de **vol** ``[de ; a]`` ; ailleurs vaut la vitesse de base. Les
changements de vitesse se font en rampe linéaire sur ``transition`` secondes de
vol, pour que l'image ne saute pas d'une cadence à l'autre.

Le temps de vol est intégré image par image (``t_{k+1} = t_k + v(t_k) / ips``) :
il est strictement croissant et s'arrête exactement sur la fin demandée.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

__all__ = ["Ralenti", "instants_de_vol", "vitesse_de_lecture"]

Tableau = NDArray[np.float64]

#: Garde-fou : une vidéo ne dépasse pas ce nombre d'images.
IMAGES_MAX = 2_000_000


@dataclass(frozen=True)
class Ralenti:
    """Vitesse ``vitesse`` sur l'intervalle de vol ``[de ; a]`` (s)."""

    de: float
    a: float
    vitesse: float

    def __post_init__(self) -> None:
        if not self.de < self.a:
            raise ValueError(f"ralenti [{self.de:g} ; {self.a:g}] : il faut de < a")
        if not self.vitesse > 0:
            raise ValueError("ralenti : vitesse positive (secondes de vol par seconde de vidéo)")


def vitesse_de_lecture(t: Tableau | float, base: float, ralentis: Sequence[Ralenti],
                       transition: float = 0.5) -> Tableau:
    """Vitesse de lecture à l'instant de vol ``t`` (rampes linéaires aux bords)."""
    tt = np.atleast_1d(np.asarray(t, dtype=float))
    v = np.full_like(tt, float(base))
    for r in ralentis:
        if transition > 0:
            # Poids 0 → 1 sur [de − transition ; de], 1 sur le ralenti, 1 → 0 sur [a ; a + transition].
            poids = np.clip(np.minimum((tt - (r.de - transition)) / transition,
                                       ((r.a + transition) - tt) / transition), 0.0, 1.0)
        else:
            poids = ((tt >= r.de) & (tt <= r.a)).astype(float)
        v = v + poids * (r.vitesse - v)
    return v


def instants_de_vol(t0: float, t1: float, ips: float, base: float,
                    ralentis: Sequence[Ralenti] = (), transition: float = 0.5) -> Tableau:
    """Instant de vol de chaque image, de ``t0`` à ``t1`` inclus (dernière image recalée)."""
    if not ralentis:
        n = max(1, round((t1 - t0) / base * ips))
        return np.asarray(np.minimum(t0 + np.arange(n) / ips * base, t1), dtype=float)
    instants = [t0]
    t = t0
    while t < t1:
        t = t + float(vitesse_de_lecture(t, base, ralentis, transition)[0]) / ips
        instants.append(min(t, t1))
        if len(instants) > IMAGES_MAX:
            raise ValueError("ralentis : plus de deux millions d'images, vitesse trop faible ?")
    if len(instants) > 1 and instants[-1] - instants[-2] < 1e-9:
        instants.pop()
    return np.asarray(instants, dtype=float)
