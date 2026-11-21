"""Repères locaux au CDG de l'engin : corps FRD, NED local, aérodynamique, trajectoire.

Chaque trièdre est rendu comme une matrice ``(…, 3, 3)`` dont les **colonnes** sont
ses axes x, y, z exprimés en ENU (la convention interne) : ``axes[..., :, 0]`` est
l'axe x. Tous sont orthonormés directs, ce que les tests vérifient.

* **Corps FRD** — les colonnes de la matrice d'attitude (avant, droite, bas).
* **NED local** — Nord, Est, Bas, translatés au CDG (la référence de l'attitude).
* **Aérodynamique** — depuis la vitesse **air** ``v_air = v_sol − vent`` vue dans le
  corps, ``(u, v, w)`` : incidence ``α = atan2(w, u)``, dérapage ``β = asin(v/V)``.
  Les axes sont ceux de la mécanique du vol (repère « vent ») : ``x_a`` le long de la
  vitesse air, obtenus du corps par β puis α. Sous :data:`V_AIR_MIN` le repère n'est
  pas défini (NaN) : une direction de vitesse nulle ne se dessine pas.
* **Trajectoire** (cinématique) — ``x_k`` le long de la vitesse **sol**, ``y_k``
  horizontal vers la droite de la route, ``z_k`` complète vers le bas. En vol
  vertical la route n'existe pas : ``y_k`` est alors pris vers l'Est.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_trajcast.core import rotations as rot

__all__ = [
    "REPERES_LOCAUX",
    "V_AIR_MIN",
    "angles_aero",
    "axes_aero",
    "axes_corps",
    "axes_ned_local",
    "axes_trajectoire",
]

Tableau = NDArray[np.float64]

#: Les repères dessinables au CDG, dans l'ordre des menus.
REPERES_LOCAUX = ("corps", "ned", "aero", "trajectoire")
#: Vitesse (m/s) en dessous de laquelle les repères aérodynamique et trajectoire ne sont pas définis.
V_AIR_MIN = 0.5

_NED_EN_ENU = np.array([[0.0, 1.0, 0.0],   # colonnes : Nord, Est, Bas exprimés en ENU
                        [1.0, 0.0, 0.0],
                        [0.0, 0.0, -1.0]])


def axes_corps(q: ArrayLike) -> Tableau:
    """Axes FRD en ENU, ``(n, 3, 3)`` (colonnes x avant, y droite, z bas)."""
    return np.asarray(rot.vers_matrice(np.atleast_2d(np.asarray(q, dtype=float))), dtype=float)


def axes_ned_local(n: int = 1) -> Tableau:
    """Axes Nord, Est, Bas en ENU, ``(n, 3, 3)`` — les mêmes partout, translatés au CDG."""
    return np.repeat(_NED_EN_ENU[None, :, :], n, axis=0)


def angles_aero(q: ArrayLike, v_air_enu: ArrayLike) -> tuple[Tableau, Tableau, Tableau]:
    """Incidence α, dérapage β (rad) et vitesse air V (m/s), ``(n,)`` chacun ; NaN sous :data:`V_AIR_MIN`."""
    r = axes_corps(q)
    v = np.atleast_2d(np.asarray(v_air_enu, dtype=float))
    uvw = np.einsum("nji,nj->ni", r, v)  # Rᵀ v : la vitesse air dans le corps
    norme = np.linalg.norm(uvw, axis=1)
    ok = norme > V_AIR_MIN
    with np.errstate(invalid="ignore", divide="ignore"):
        alpha = np.where(ok, np.arctan2(uvw[:, 2], uvw[:, 0]), np.nan)
        beta = np.where(ok, np.arcsin(np.clip(uvw[:, 1] / norme, -1.0, 1.0)), np.nan)
    return alpha, beta, norme


def axes_aero(q: ArrayLike, v_air_enu: ArrayLike) -> Tableau:
    """Axes aérodynamiques en ENU, ``(n, 3, 3)`` ; NaN où la vitesse air est trop faible."""
    alpha, beta, _ = angles_aero(q, v_air_enu)
    ca, sa, cb, sb = np.cos(alpha), np.sin(alpha), np.cos(beta), np.sin(beta)
    # Axes du repère aérodynamique exprimés dans le corps (mécanique du vol, β puis α).
    dans_corps = np.empty((len(alpha), 3, 3))
    dans_corps[:, :, 0] = np.column_stack([ca * cb, sb, sa * cb])
    dans_corps[:, :, 1] = np.column_stack([-ca * sb, cb, -sa * sb])
    dans_corps[:, :, 2] = np.column_stack([-sa, np.zeros_like(sa), ca])
    return np.asarray(np.einsum("nij,njk->nik", axes_corps(q), dans_corps), dtype=float)


def axes_trajectoire(v_sol_enu: ArrayLike) -> Tableau:
    """Axes cinématiques en ENU, ``(n, 3, 3)`` ; NaN où la vitesse sol est trop faible."""
    v = np.atleast_2d(np.asarray(v_sol_enu, dtype=float))
    norme = np.linalg.norm(v, axis=1)
    x = v / np.where(norme > V_AIR_MIN, norme, np.nan)[:, None]
    horizontal = np.hypot(v[:, 0], v[:, 1])
    # Droite de la route : (cos χ, −sin χ, 0) en ENU pour un cap χ ; vers l'Est en vol vertical.
    with np.errstate(invalid="ignore", divide="ignore"):
        y = np.where((horizontal > 1e-9)[:, None],
                     np.column_stack([v[:, 1], -v[:, 0], np.zeros(len(v))]) / horizontal[:, None],
                     np.array([1.0, 0.0, 0.0]))
    z = np.cross(x, y)
    axes = np.stack([x, y, z], axis=2)
    axes[norme <= V_AIR_MIN] = np.nan
    return axes
