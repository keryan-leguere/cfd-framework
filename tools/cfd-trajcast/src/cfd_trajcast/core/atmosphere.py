"""Atmosphère standard (ISA / US 1976, 0–86 km) réduite à ce qu'exige la télémétrie.

La température donne la célérité du son (Mach) ; pression et masse volumique
donnent la pression dynamique du vol de référence.
Le paquet frère ``cfd-atm`` fait bien plus (ΔT, profils, vitesses aéro) ; celle-ci
existe pour que ``cfd-trajcast`` reste installable seul.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

__all__ = [
    "G0",
    "GAMMA",
    "RAYON_TERRE",
    "R_AIR",
    "celerite_son",
    "mach",
    "masse_volumique",
    "pression",
    "temperature",
]

#: Rapport des chaleurs spécifiques de l'air.
GAMMA = 1.4
#: Constante spécifique de l'air (J/kg/K).
R_AIR = 287.05287
#: Pesanteur de référence de l'atmosphère standard (m/s²).
G0 = 9.80665
#: Pression au niveau de la mer (Pa).
P0 = 101_325.0
#: Rayon terrestre de la conversion géométrique ↔ géopotentielle (m).
RAYON_TERRE = 6_356_766.0

# Bases géopotentielles (m) et gradients (K/m) des couches US 1976.
_BASES = np.array([0.0, 11_000.0, 20_000.0, 32_000.0, 47_000.0, 51_000.0, 71_000.0, 84_852.0])
_GRADIENTS = np.array([-6.5e-3, 0.0, 1.0e-3, 2.8e-3, 0.0, -2.8e-3, -2.0e-3])
_T0 = 288.15


def _temperatures_bases() -> NDArray[np.float64]:
    t = [_T0]
    for i, g in enumerate(_GRADIENTS):
        t.append(t[-1] + g * (_BASES[i + 1] - _BASES[i]))
    return np.array(t)


_T_BASES = _temperatures_bases()


def _pression_couche(p_b: float, t_b: float, gradient: float, dh: NDArray[np.float64] | float) -> NDArray[np.float64]:
    if gradient == 0:
        return np.asarray(p_b * np.exp(-G0 * np.asarray(dh) / (R_AIR * t_b)))
    return np.asarray(p_b * ((t_b + gradient * np.asarray(dh)) / t_b) ** (-G0 / (gradient * R_AIR)))


def _pressions_bases() -> NDArray[np.float64]:
    p = [P0]
    for i, g in enumerate(_GRADIENTS):
        p.append(float(_pression_couche(p[-1], _T_BASES[i], g, _BASES[i + 1] - _BASES[i])))
    return np.array(p)


_P_BASES = _pressions_bases()


def _geopotentielle(altitude: ArrayLike) -> NDArray[np.float64]:
    z = np.asarray(altitude, dtype=float)
    return np.asarray(np.minimum(RAYON_TERRE * z / (RAYON_TERRE + z), _BASES[-1]))


def temperature(altitude: ArrayLike) -> NDArray[np.float64]:
    """Température (K) à une altitude **géométrique** (m).

    Sous 0 m, le gradient de la troposphère est prolongé ; au-dessus de 86 km,
    la température est figée à sa valeur de 86 km (le Mach n'y a plus guère de sens).
    """
    z = np.asarray(altitude, dtype=float)
    h = RAYON_TERRE * z / (RAYON_TERRE + z)
    h = np.minimum(h, _BASES[-1])
    couche = np.clip(np.searchsorted(_BASES, h, side="right") - 1, 0, len(_GRADIENTS) - 1)
    return np.asarray(_T_BASES[couche] + _GRADIENTS[couche] * (h - _BASES[couche]))


def celerite_son(altitude: ArrayLike) -> NDArray[np.float64]:
    """Célérité du son (m/s) à une altitude géométrique (m)."""
    return np.asarray(np.sqrt(GAMMA * R_AIR * temperature(altitude)))


def mach(vitesse: ArrayLike, altitude: ArrayLike) -> NDArray[np.float64]:
    """Mach d'une vitesse (m/s, norme) à une altitude (m) ; vent nul supposé."""
    return np.asarray(np.asarray(vitesse, dtype=float) / celerite_son(altitude))


def pression(altitude: ArrayLike) -> NDArray[np.float64]:
    """Pression statique (Pa) à une altitude géométrique (m), 0–86 km."""
    h = _geopotentielle(altitude)
    couche = np.clip(np.searchsorted(_BASES, h, side="right") - 1, 0, len(_GRADIENTS) - 1)
    out = np.empty_like(h)
    for c in np.unique(couche):
        m = couche == c
        out[m] = _pression_couche(_P_BASES[c], _T_BASES[c], _GRADIENTS[c], h[m] - _BASES[c])
    return out


def masse_volumique(altitude: ArrayLike) -> NDArray[np.float64]:
    """Masse volumique (kg/m³) à une altitude géométrique (m)."""
    return np.asarray(pression(altitude) / (R_AIR * temperature(altitude)))
