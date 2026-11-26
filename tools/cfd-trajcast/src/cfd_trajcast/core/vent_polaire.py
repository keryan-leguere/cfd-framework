"""Le vent sur une rose Nord/Est : azimut, module horizontal, vent vertical.

Conventions (``00_DOC/10_FIGURES_VENT.md``) :

* le vent entre ici en **ENU** (m/s), vitesse de l'air — ce que rend
  :func:`cfd_trajcast.data.vent.vent_enu`, quelle que soit la déclaration du fichier ;
* l'**azimut** se compte depuis le Nord, dans le sens des aiguilles d'une montre
  (0 = Nord, π/2 = Est), comme un cap ;
* ``sens="vers"`` : la flèche montre où va l'air ; ``sens="depuis"`` : d'où il vient
  (convention météo), soit l'azimut opposé — le module ne change pas ;
* entre deux instants, on interpole les **composantes**, jamais l'angle : un vent qui
  passe de 359° à 1° ne fait pas le tour du cadran.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike, NDArray

__all__ = ["SENS_POLAIRE", "azimut_module", "rayon_polaire", "vent_a"]

Tableau = NDArray[np.float64]

SENS_POLAIRE = ("vers", "depuis")


def azimut_module(vent_enu: ArrayLike, sens: str = "vers") -> tuple[Tableau, Tableau, Tableau]:
    """``(azimut (rad, dans [0, 2π[), module horizontal (m/s), vertical (m/s, > 0 vers le haut))``.

    ``vent_enu`` : ``(3,)`` ou ``(n, 3)``. Un vent horizontal nul a l'azimut 0 (sans objet).
    """
    if sens not in SENS_POLAIRE:
        raise ValueError(f"sens : {' ou '.join(SENS_POLAIRE)} (reçu : {sens!r})")
    v = np.atleast_2d(np.asarray(vent_enu, dtype=float))
    if v.shape[-1] != 3:
        raise ValueError("vent : trois composantes (Est, Nord, Haut)")
    est, nord, haut = v[:, 0], v[:, 1], v[:, 2]
    azimut = np.arctan2(est, nord)
    if sens == "depuis":
        azimut = azimut + np.pi
    azimut = np.mod(azimut, 2 * np.pi)
    # mod peut rendre 2π tout juste (arrondi d'un −0) : on le ramène à 0.
    azimut = np.where(azimut >= 2 * np.pi, 0.0, azimut)
    return azimut, np.hypot(est, nord), haut.copy()


def vent_a(t: float | ArrayLike, instants: ArrayLike, vent_enu: ArrayLike) -> Tableau:
    """Le vent ENU à ``t`` (scalaire → ``(3,)``, tableau → ``(n, 3)``), interpolé par composante.

    Borné au vol : avant le premier instant, le premier vent ; après le dernier, le dernier.
    """
    ti = np.asarray(instants, dtype=float)
    v = np.asarray(vent_enu, dtype=float)
    tt = np.asarray(t, dtype=float)
    sortie = np.stack([np.interp(tt, ti, v[:, k]) for k in range(3)], axis=-1)
    return np.asarray(sortie, dtype=float)


def rayon_polaire(module_h: ArrayLike) -> float:
    """Limite radiale commune : le plus fort vent horizontal du vol, arrondi vers le haut à
    un pas lisible (1, 2, 2,5 ou 5 × 10ⁿ) ; 1 m/s au moins pour un vent nul."""
    m = np.asarray(module_h, dtype=float)
    m = m[np.isfinite(m)]
    vmax = float(m.max()) if m.size else 0.0
    if vmax <= 0:
        return 1.0
    puissance = 10.0 ** math.floor(math.log10(vmax))
    for pas in (1.0, 2.0, 2.5, 5.0, 10.0):
        if vmax <= pas * puissance * (1 + 1e-12):
            # Une marge de 5 % : la pointe de la flèche ne touche pas le cercle extérieur.
            limite = pas * puissance
            return limite if vmax < 0.95 * limite else _suivant(limite)
    return 10.0 * puissance  # pragma: no cover - la boucle s'arrête toujours à 10


def _suivant(limite: float) -> float:
    puissance = 10.0 ** math.floor(math.log10(limite) + 1e-12)
    for pas in (1.0, 2.0, 2.5, 5.0, 10.0):
        if pas * puissance > limite * (1 + 1e-12):
            return pas * puissance
    return 10.0 * puissance  # pragma: no cover
