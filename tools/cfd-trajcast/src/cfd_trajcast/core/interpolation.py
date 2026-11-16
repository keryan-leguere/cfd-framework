"""Rééchantillonnage d'une trajectoire aux instants de la vidéo, en NumPy pur.

* positions : interpolant cubique monotone par morceaux (PCHIP, Fritsch–Carlson,
  mêmes pentes que ``scipy.interpolate.PchipInterpolator``) — pas de dépassement,
  donc pas d'apogée inventée ni de fusée qui passe sous le sol entre deux points ;
* attitude : SLERP entre échantillons voisins (rotation à vitesse constante) ;
* dérivées des données brutes : différences finies d'ordre 2 sur pas non uniforme.

On n'extrapole jamais : un instant hors des données est une erreur.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_trajcast.core import rotations as rot

__all__ = ["Pchip", "deriver", "slerp_serie"]

Tableau = NDArray[np.float64]

#: Tolérance relative sur les bornes (arrondis de temps).
_TOLERANCE_BORNES = 1e-9


def _verifier_abscisses(x: Tableau) -> None:
    if x.ndim != 1 or len(x) < 2:
        raise ValueError("au moins deux instants sont nécessaires")
    if not np.all(np.isfinite(x)):
        raise ValueError("instants non finis")
    if np.any(np.diff(x) <= 0):
        raise ValueError("les instants doivent être strictement croissants")


def _localiser(x: Tableau, xn: Tableau) -> tuple[NDArray[np.intp], Tableau]:
    """Intervalle de chaque ``xn`` et position relative ``u ∈ [0, 1]`` dedans."""
    marge = _TOLERANCE_BORNES * max(1.0, float(x[-1] - x[0]))
    if np.any(xn < x[0] - marge) or np.any(xn > x[-1] + marge):
        raise ValueError(
            f"instant hors des données [{x[0]:g} ; {x[-1]:g}] : pas d'extrapolation"
        )
    xn = np.clip(xn, x[0], x[-1])
    k = np.clip(np.searchsorted(x, xn, side="right") - 1, 0, len(x) - 2)
    return k, (xn - x[k]) / (x[k + 1] - x[k])


def _pente_bord(h0: float, h1: float, d0: Tableau, d1: Tableau) -> Tableau:
    pente = ((2 * h0 + h1) * d0 - h0 * d1) / (h0 + h1)
    pente = np.where(np.sign(pente) != np.sign(d0), 0.0, pente)
    trop = (np.sign(d0) != np.sign(d1)) & (np.abs(pente) > 3 * np.abs(d0))
    return np.where(trop, 3 * d0, pente)


class Pchip:
    """Interpolant cubique monotone de ``y`` (``(N,)`` ou ``(N, k)``) en fonction de ``x``."""

    def __init__(self, x: ArrayLike, y: ArrayLike) -> None:
        self.x = np.asarray(x, dtype=float)
        _verifier_abscisses(self.x)
        y_arr = np.asarray(y, dtype=float)
        self._vecteur = y_arr.ndim == 1
        self.y = y_arr[:, None] if self._vecteur else y_arr
        if len(self.y) != len(self.x):
            raise ValueError("x et y n'ont pas le même nombre de points")
        self.d = self._pentes()

    def _pentes(self) -> Tableau:
        h = np.diff(self.x)[:, None]
        delta = np.diff(self.y, axis=0) / h
        n = len(self.x)
        d = np.zeros_like(self.y)
        if n == 2:
            d[:] = delta[0]
            return d
        w1 = 2 * h[1:] + h[:-1]
        w2 = h[1:] + 2 * h[:-1]
        meme_signe = (np.sign(delta[:-1]) * np.sign(delta[1:])) > 0
        with np.errstate(divide="ignore", invalid="ignore"):
            harmonique = (w1 + w2) / (w1 / delta[:-1] + w2 / delta[1:])
        d[1:-1] = np.where(meme_signe, harmonique, 0.0)
        d[0] = _pente_bord(float(h[0, 0]), float(h[1, 0]), delta[0], delta[1])
        d[-1] = _pente_bord(float(h[-1, 0]), float(h[-2, 0]), delta[-1], delta[-2])
        return d

    def __call__(self, xn: ArrayLike, derivee: int = 0) -> Tableau:
        """Valeur (``derivee=0``), dérivée première ou seconde aux instants ``xn``."""
        if derivee not in (0, 1, 2):
            raise ValueError("derivee vaut 0, 1 ou 2")
        x_n = np.atleast_1d(np.asarray(xn, dtype=float))
        k, u = _localiser(self.x, x_n)
        h = (self.x[k + 1] - self.x[k])[:, None]
        t = u[:, None]
        y0, y1 = self.y[k], self.y[k + 1]
        m0, m1 = self.d[k] * h, self.d[k + 1] * h
        if derivee == 0:
            b = (2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2)
            echelle = 1.0
        elif derivee == 1:
            b = (6 * t**2 - 6 * t, 3 * t**2 - 4 * t + 1, -6 * t**2 + 6 * t, 3 * t**2 - 2 * t)
            echelle = 1 / h
        else:
            b = (12 * t - 6, 6 * t - 4, -12 * t + 6, 6 * t - 2)
            echelle = 1 / h**2
        valeur = (b[0] * y0 + b[1] * m0 + b[2] * y1 + b[3] * m1) * echelle
        resultat: Tableau = valeur[:, 0] if self._vecteur else valeur
        return resultat


def slerp_serie(x: ArrayLike, q: ArrayLike, xn: ArrayLike) -> Tableau:
    """Attitude aux instants ``xn`` par SLERP entre les deux échantillons qui l'encadrent."""
    xa = np.asarray(x, dtype=float)
    _verifier_abscisses(xa)
    quat, _ = rot.continuite_hemisphere(rot.normaliser(q))
    k, u = _localiser(xa, np.atleast_1d(np.asarray(xn, dtype=float)))
    return rot.slerp(quat[k], quat[k + 1], u)


def deriver(x: ArrayLike, y: ArrayLike) -> Tableau:
    """Dérivée de données échantillonnées (ordre 2, pas non uniforme, bords compris)."""
    xa = np.asarray(x, dtype=float)
    _verifier_abscisses(xa)
    ya = np.asarray(y, dtype=float)
    ordre: Literal[1, 2] = 2 if len(xa) >= 3 else 1
    return np.asarray(np.gradient(ya, xa, axis=0, edge_order=ordre), dtype=float)
