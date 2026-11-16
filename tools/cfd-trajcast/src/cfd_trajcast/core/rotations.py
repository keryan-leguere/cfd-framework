"""Quaternions et angles d'Euler, en NumPy pur.

Convention unique du paquet : quaternion de **Hamilton**, scalaire **en tête**
``(w, x, y, z)``, rotation **active** du repère corps vers le repère de référence :
``v_ref = q ⊗ v_corps ⊗ q*``. Tous les tableaux ont les composantes sur le dernier
axe, ce qui vectorise tout sur une série temporelle ``(N, 4)``.

Angles d'Euler : la séquence s'écrit comme dans SciPy — trois lettres **majuscules**
pour une rotation intrinsèque (axes mobiles, ``"ZYX"`` = lacet-tangage-roulis de la
mécanique du vol), **minuscules** pour une rotation extrinsèque (axes fixes). Les
douze séquences (Tait-Bryan et Euler propres) sont acceptées. Angles nuls : le
repère corps coïncide avec le repère de référence.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

__all__ = [
    "SEQUENCES",
    "angle_entre",
    "conjugue",
    "continuite_hemisphere",
    "depuis_euler",
    "depuis_matrice",
    "elementaire",
    "normaliser",
    "produit",
    "slerp",
    "tourner",
    "valider_sequence",
    "vers_euler",
    "vers_matrice",
]

Tableau = NDArray[np.float64]

_AXES = "xyz"

#: Les douze séquences, en intrinsèque (majuscules) ; les minuscules sont extrinsèques.
SEQUENCES: tuple[str, ...] = tuple(
    a + b + c
    for a in "XYZ"
    for b in "XYZ"
    for c in "XYZ"
    if a != b and b != c
)


def _q(q: ArrayLike) -> Tableau:
    tableau = np.asarray(q, dtype=float)
    if tableau.shape[-1:] != (4,):
        raise ValueError(f"un quaternion a 4 composantes, reçu la forme {tableau.shape}")
    return tableau


def normaliser(q: ArrayLike) -> Tableau:
    """Ramène chaque quaternion à la norme 1."""
    tableau = _q(q)
    norme = np.linalg.norm(tableau, axis=-1, keepdims=True)
    if np.any(norme == 0):
        raise ValueError("quaternion nul : aucune rotation ne lui correspond")
    return tableau / norme


def conjugue(q: ArrayLike) -> Tableau:
    """Conjugué, c'est-à-dire la rotation inverse pour un quaternion unitaire."""
    tableau = _q(q).copy()
    tableau[..., 1:] *= -1
    return tableau


def produit(p: ArrayLike, q: ArrayLike) -> Tableau:
    """Produit de Hamilton ``p ⊗ q`` (appliquer ``q`` puis ``p``)."""
    a, b = _q(p), _q(q)
    pw, px, py, pz = np.moveaxis(a, -1, 0)
    qw, qx, qy, qz = np.moveaxis(b, -1, 0)
    return np.stack(
        [
            pw * qw - px * qx - py * qy - pz * qz,
            pw * qx + px * qw + py * qz - pz * qy,
            pw * qy - px * qz + py * qw + pz * qx,
            pw * qz + px * qy - py * qx + pz * qw,
        ],
        axis=-1,
    )


def vers_matrice(q: ArrayLike) -> Tableau:
    """Matrice de rotation ``R`` telle que ``v_ref = R @ v_corps``."""
    w, x, y, z = np.moveaxis(normaliser(q), -1, 0)
    return np.stack(
        [
            np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)], -1),
            np.stack([2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)], -1),
            np.stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)], -1),
        ],
        axis=-2,
    )


def depuis_matrice(r: ArrayLike) -> Tableau:
    """Quaternion d'une matrice de rotation (méthode de Shepperd, stable partout)."""
    m = np.asarray(r, dtype=float)
    if m.shape[-2:] != (3, 3):
        raise ValueError(f"une matrice de rotation est 3×3, reçu la forme {m.shape}")
    forme = m.shape[:-2]
    m = m.reshape(-1, 3, 3)
    diag = np.stack([m[:, 0, 0], m[:, 1, 1], m[:, 2, 2], m[:, 0, 0] + m[:, 1, 1] + m[:, 2, 2]], 1)
    choix = np.argmax(diag, axis=1)
    q = np.empty((len(m), 4))
    # Plus grande composante : le scalaire.
    s = choix == 3
    q[s, 0] = 1 + diag[s, 3]
    q[s, 1] = m[s, 2, 1] - m[s, 1, 2]
    q[s, 2] = m[s, 0, 2] - m[s, 2, 0]
    q[s, 3] = m[s, 1, 0] - m[s, 0, 1]
    # Plus grande composante : un axe i, avec j, k les suivants.
    for i in range(3):
        s = choix == i
        j, k = (i + 1) % 3, (i + 2) % 3
        q[s, 1 + i] = 1 - diag[s, 3] + 2 * m[s, i, i]
        q[s, 1 + j] = m[s, j, i] + m[s, i, j]
        q[s, 1 + k] = m[s, k, i] + m[s, i, k]
        q[s, 0] = m[s, k, j] - m[s, j, k]
    return normaliser(q).reshape(*forme, 4)


def elementaire(axe: str, angle: ArrayLike) -> Tableau:
    """Rotation d'``angle`` (rad) autour d'un axe ``"x"``, ``"y"`` ou ``"z"``."""
    a = np.asarray(angle, dtype=float)
    q = np.zeros((*a.shape, 4))
    q[..., 0] = np.cos(a / 2)
    q[..., 1 + _AXES.index(axe.lower())] = np.sin(a / 2)
    return q


def valider_sequence(sequence: str) -> str:
    """Vérifie une séquence d'Euler et la renvoie ; lève ``ValueError`` sinon."""
    if (
        len(sequence) != 3
        or not (sequence.isupper() or sequence.islower())
        or sequence.upper() not in SEQUENCES
    ):
        raise ValueError(
            f"séquence d'Euler {sequence!r} invalide : trois axes parmi x, y, z, deux "
            "consécutifs différents, tout en majuscules (intrinsèque, ex. 'ZYX') ou tout "
            "en minuscules (extrinsèque, ex. 'xyz')"
        )
    return sequence


def depuis_euler(angles: ArrayLike, sequence: str) -> Tableau:
    """Quaternion corps → référence depuis trois angles (rad), dans l'ordre de ``sequence``."""
    valider_sequence(sequence)
    a = np.asarray(angles, dtype=float)
    if a.shape[-1:] != (3,):
        raise ValueError(f"trois angles attendus, reçu la forme {a.shape}")
    q1, q2, q3 = (elementaire(sequence[i], a[..., i]) for i in range(3))
    if sequence.isupper():  # axes mobiles : R = R1 R2 R3
        return produit(produit(q1, q2), q3)
    return produit(produit(q3, q2), q1)  # axes fixes : R = R3 R2 R1


def vers_euler(q: ArrayLike, sequence: str) -> Tableau:
    """Angles (rad) d'une séquence, inverse de :func:`depuis_euler`.

    Méthode directe de Bernardes & Viollet (2022), la même que SciPy. Le deuxième
    angle est dans ``[-π/2, π/2]`` (Tait-Bryan) ou ``[0, π]`` (Euler propre) ; en
    blocage de cardan, le troisième angle est mis à zéro et le premier porte tout.
    Les angles rendus reconstruisent toujours la rotation.
    """
    valider_sequence(sequence)
    quat = normaliser(q)
    forme = quat.shape[:-1]
    quat = quat.reshape(-1, 4)
    extrinseque = sequence.islower()
    seq = sequence.lower() if extrinseque else sequence.lower()[::-1]
    i, j, k = (_AXES.index(c) for c in seq)
    propre = i == k
    if propre:
        k = 3 - i - j
    signe = (i - j) * (j - k) * (k - i) // 2
    w = quat[:, 0]
    v = quat[:, 1:]
    if propre:
        a, b, c, d = w, v[:, i], v[:, j], v[:, k] * signe
    else:
        a = w - v[:, j]
        b = v[:, i] + v[:, k] * signe
        c = v[:, j] + w
        d = v[:, k] * signe - v[:, i]
    angles = np.empty((len(quat), 3))
    angles[:, 1] = 2 * np.arctan2(np.hypot(c, d), np.hypot(a, b))
    eps = 1e-7
    cas1 = np.abs(angles[:, 1]) <= eps
    cas2 = np.abs(angles[:, 1] - np.pi) <= eps
    demi_somme = np.arctan2(b, a)
    demi_diff = np.arctan2(d, c)
    angles[:, 0] = demi_somme - demi_diff
    angles[:, 2] = demi_somme + demi_diff
    degenere = cas1 | cas2
    if not propre:
        angles[:, 2] *= signe
        angles[:, 1] -= np.pi / 2
    if not extrinseque:
        angles = angles[:, ::-1].copy()
    if np.any(degenere):
        # Blocage de cardan : seule une combinaison des angles 1 et 3 est définie. On fixe
        # le troisième à zéro ; il reste q = q1 ⊗ q2 (intrinsèque) ou q2 ⊗ q1 (extrinsèque),
        # donc q1 se lit en retirant q2, connu.
        q2 = elementaire(sequence[1], angles[degenere, 1])
        qd = quat[degenere]
        q1 = produit(conjugue(q2), qd) if extrinseque else produit(qd, conjugue(q2))
        axe = _AXES.index(sequence[0].lower())
        angles[degenere, 0] = 2 * np.arctan2(q1[:, 1 + axe], q1[:, 0])
        angles[degenere, 2] = 0.0
    angles = (angles + np.pi) % (2 * np.pi) - np.pi
    return angles.reshape(*forme, 3)


def tourner(q: ArrayLike, v: ArrayLike) -> Tableau:
    """Applique la rotation ``q`` à des vecteurs ``v`` (corps → référence)."""
    return np.asarray(np.einsum("...ij,...j->...i", vers_matrice(q), np.asarray(v, dtype=float)), dtype=float)


def angle_entre(p: ArrayLike, q: ArrayLike) -> Tableau:
    """Angle (rad, dans ``[0, π]``) de la rotation qui mène de ``p`` à ``q``."""
    # atan2 plutôt qu'arccos du produit scalaire : précis aussi pour les petits angles.
    r = produit(conjugue(normaliser(p)), normaliser(q))
    return np.asarray(2 * np.arctan2(np.linalg.norm(r[..., 1:], axis=-1), np.abs(r[..., 0])), dtype=float)


def continuite_hemisphere(q: ArrayLike) -> tuple[Tableau, int]:
    """Choisit le signe de chaque quaternion d'une série pour qu'elle soit continue.

    ``q`` et ``-q`` sont la même rotation ; une série qui saute de l'un à l'autre
    fait tourner l'interpolation par le grand arc. Renvoie la série corrigée et le
    nombre de retournements trouvés.
    """
    quat = _q(q)
    if quat.ndim != 2 or len(quat) < 2:
        return quat.copy(), 0
    produits = np.sum(quat[1:] * quat[:-1], axis=1)
    sauts = produits < 0
    signes = np.concatenate([[1.0], np.cumprod(np.where(sauts, -1.0, 1.0))])
    return quat * signes[:, None], int(np.count_nonzero(sauts))


def slerp(p: ArrayLike, q: ArrayLike, u: ArrayLike) -> Tableau:
    """Interpolation sphérique de ``p`` (u = 0) à ``q`` (u = 1), par le petit arc."""
    a, b = normaliser(p), normaliser(q)
    t = np.asarray(u, dtype=float)[..., None]
    d = np.sum(a * b, axis=-1, keepdims=True)
    b = np.where(d < 0, -b, b)
    d = np.abs(d)
    proche = d > 0.9995
    theta = np.arccos(np.clip(d, -1.0, 1.0))
    sin_theta = np.where(proche, 1.0, np.sin(theta))
    wa = np.where(proche, 1 - t, np.sin((1 - t) * theta) / sin_theta)
    wb = np.where(proche, t, np.sin(t * theta) / sin_theta)
    return normaliser(wa * a + wb * b)
