"""Repères : référentiel local (ENU/NED), repère corps (FRD/FLU), axes de la CAO.

Conventions internes, fixées une fois pour toutes :

* **référence** : ENU local — x Est, y Nord, z Haut — origine à la rampe, en mètres ;
* **corps** : FRD — x vers le nez, y à droite, z vers le bas (norme aérospatiale).

Toute donnée d'entrée est ramenée à ces deux repères dès la lecture.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_trajcast.core import rotations as rot

__all__ = [
    "CORPS",
    "REPERES",
    "matrice_cao_vers_corps",
    "matrice_vers_enu",
    "positions_vers_enu",
    "quaternion_corps_vers_frd",
    "quaternion_vers_enu",
    "vecteur_axe",
]

Tableau = NDArray[np.float64]

#: Référentiels locaux acceptés en entrée.
REPERES = ("ENU", "NED")
#: Repères corps acceptés en entrée.
CORPS = ("FRD", "FLU")

_VERS_ENU: dict[str, Tableau] = {
    "ENU": np.eye(3),
    # (n, e, d) → (e, n, -d) : rotation propre (déterminant +1), demi-tour autour de (1, 1, 0).
    "NED": np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]]),
}

# Quaternion q_{FRD→corps d'entrée} : FLU = FRD retourné d'un demi-tour autour de x.
_FRD_VERS: dict[str, Tableau] = {
    "FRD": np.array([1.0, 0.0, 0.0, 0.0]),
    "FLU": np.array([0.0, 1.0, 0.0, 0.0]),
}


def _verifier(nom: str, valeur: str, permis: tuple[str, ...]) -> str:
    if valeur not in permis:
        raise ValueError(f"{nom} {valeur!r} inconnu ; valeurs permises : {', '.join(permis)}")
    return valeur


def matrice_vers_enu(repere: str) -> Tableau:
    """Matrice ``M`` telle que ``p_ENU = M @ p_repere``."""
    return _VERS_ENU[_verifier("repère", repere, REPERES)].copy()


def positions_vers_enu(positions: ArrayLike, repere: str) -> Tableau:
    """Positions ``(N, 3)`` exprimées dans ``repere`` → ENU."""
    return np.asarray(positions, dtype=float) @ matrice_vers_enu(repere).T


def quaternion_vers_enu(q_vers_repere: ArrayLike, repere: str) -> Tableau:
    """``q_{corps→repere}`` → ``q_{corps→ENU}``."""
    q_repere_enu = rot.depuis_matrice(matrice_vers_enu(repere))
    return rot.produit(q_repere_enu, q_vers_repere)


def quaternion_corps_vers_frd(q_corps: ArrayLike, corps: str) -> Tableau:
    """``q_{corps→ref}`` pour le corps déclaré → ``q_{FRD→ref}``."""
    return rot.produit(q_corps, _FRD_VERS[_verifier("repère corps", corps, CORPS)])


def vecteur_axe(axe: str) -> Tableau:
    """``"+X"``, ``"-z"``… → vecteur unitaire."""
    texte = axe.strip().upper()
    if len(texte) == 1:
        texte = "+" + texte
    if len(texte) != 2 or texte[0] not in "+-" or texte[1] not in "XYZ":
        raise ValueError(f"axe {axe!r} invalide : attendu +X, -X, +Y, -Y, +Z ou -Z")
    v = np.zeros(3)
    v["XYZ".index(texte[1])] = 1.0 if texte[0] == "+" else -1.0
    return v


def matrice_cao_vers_corps(axe_nez: str, axe_haut: str) -> Tableau:
    """Matrice ``R`` telle que ``v_FRD = R @ v_CAO``.

    ``axe_nez`` est l'axe de la CAO qui pointe vers le nez (→ x corps) ;
    ``axe_haut`` celui qui pointe vers le haut quand la fusée est à roulis nul
    (→ -z corps, puisque z corps pointe vers le bas).
    """
    x = vecteur_axe(axe_nez)
    haut = vecteur_axe(axe_haut)
    if abs(float(x @ haut)) > 0.5:
        raise ValueError(
            f"axe_haut {axe_haut!r} doit être perpendiculaire à axe_nez {axe_nez!r}"
        )
    z = -haut
    y = np.cross(z, x)
    return np.stack([x, y, z])
