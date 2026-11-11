"""Plans d'expériences sur un pavé normalisé, sans rien savoir de l'aérodynamique.

Deux familles (00_DOC/02_REMPLISSAGE.md) :

- plans **structurés**, sur ``[-1, 1]^k`` : composite centré, Box-Behnken,
  grille creuse de Smolyak. Tous sont symétriques par changement de signe de
  chaque facteur : une symétrie de l'engin envoie un point du plan sur un autre ;
- plans à **remplissage d'espace**, sur ``[0, 1]^k`` : hypercube latin
  (optimisé maximin), suites de Halton et de Sobol.

Un point est un tuple de flottants ; l'appelant met à l'échelle.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from itertools import product

import numpy as np

__all__ = [
    "box_behnken",
    "composite_centre",
    "grille_creuse",
    "halton",
    "hypercube_latin",
    "sobol",
    "sous_ensemble_maximin",
]

Point = tuple[float, ...]

#: Les premiers nombres premiers, bases de la suite de Halton.
_PREMIERS = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53)


def composite_centre(k: int, fraction: int = 0) -> list[Point]:
    """Plan composite centré à faces centrées : sommets, points axiaux, centre.

    ``fraction = 0`` : les ``2^k`` sommets ; ``fraction = 1`` : la demi-fraction
    ``2^(k-1)`` où le dernier facteur est le produit des autres (résolution V
    dès ``k = 5`` : effets principaux et interactions doubles non confondus).
    """
    if k < 2:
        raise ValueError("un plan composite centré demande au moins 2 facteurs")
    if fraction not in (0, 1):
        raise ValueError("fraction : 0 (complet) ou 1 (demi-fraction)")
    sommets: list[Point] = list(product((-1.0, 1.0), repeat=k - fraction))
    if fraction == 1:
        sommets = [(*s, float(np.prod(s))) for s in sommets]
    axiaux = [tuple(s if i == j else 0.0 for j in range(k)) for i in range(k) for s in (-1.0, 1.0)]
    return [*sommets, *axiaux, tuple([0.0] * k)]


def box_behnken(k: int) -> list[Point]:
    """Box-Behnken « toutes les paires » : ±1 sur deux facteurs, 0 ailleurs, plus le centre.

    Aucun sommet du pavé : jamais tous les facteurs à l'extrême ensemble.
    """
    if k < 3:
        raise ValueError("un plan de Box-Behnken demande au moins 3 facteurs")
    points: list[Point] = [tuple([0.0] * k)]
    for i in range(k):
        for j in range(i + 1, k):
            for a, b in product((-1.0, 1.0), repeat=2):
                p = [0.0] * k
                p[i], p[j] = a, b
                points.append(tuple(p))
    return points


def grille_creuse(k: int, niveau: int) -> list[Point]:
    """Grille creuse de Smolyak, points de Clenshaw-Curtis emboîtés (1, 3, 5, 9… par axe).

    Le niveau 1 est l'étoile ``2k + 1`` ; le niveau 2 lui ajoute les
    croisements deux à deux (``2k² + 2k + 1`` points).
    """
    if k < 1 or niveau < 0:
        raise ValueError("grille creuse : k ≥ 1 et niveau ≥ 0")

    def axe(i: int) -> list[float]:
        if i == 0:
            return [0.0]
        m = 2**i + 1
        return [round(-math.cos(math.pi * j / (m - 1)), 12) + 0.0 for j in range(m)]

    points: set[Point] = set()
    for indices in product(range(niveau + 1), repeat=k):
        if sum(indices) <= niveau:
            points.update(product(*(axe(i) for i in indices)))
    return sorted(points)


def hypercube_latin(n: int, k: int, graine: int = 0, essais: int = 100) -> list[Point]:
    """Hypercube latin de ``n`` points en dimension ``k``, le meilleur de ``essais`` (maximin).

    Chaque axe est découpé en ``n`` tranches, chacune visitée une fois, le
    point tiré au hasard dans sa tranche. Parmi ``essais`` tirages, on garde
    celui dont la plus petite distance entre deux points est la plus grande.
    """
    if n < 1 or k < 1:
        return []
    rng = np.random.default_rng(graine)
    meilleur: np.ndarray | None = None
    distance = -1.0
    for _ in range(max(1, essais if n > 1 else 1)):
        plan = np.column_stack([(rng.permutation(n) + rng.random(n)) / n for _ in range(k)])
        d = _distance_minimale(plan)
        if d > distance:
            meilleur, distance = plan, d
    assert meilleur is not None
    return [tuple(float(x) for x in ligne) for ligne in meilleur]


def _distance_minimale(plan: np.ndarray) -> float:
    if len(plan) < 2:
        return math.inf
    ecarts = plan[:, None, :] - plan[None, :, :]
    carres = (ecarts**2).sum(-1)
    return float(np.sqrt(carres[np.triu_indices(len(plan), 1)].min()))


def halton(n: int, k: int, depart: int = 1) -> list[Point]:
    """Les ``n`` points de la suite de Halton en dimension ``k``, à partir du rang ``depart``.

    Déterministe et **extensible** : les ``n`` premiers points d'une suite plus
    longue sont déjà bien répartis ; ``depart`` permet de continuer une suite,
    ou d'en décaler une d'un Mach à l'autre.
    """
    if k > len(_PREMIERS):
        raise ValueError(f"suite de Halton : au plus {len(_PREMIERS)} facteurs")

    def radical(i: int, base: int) -> float:
        valeur, facteur = 0.0, 1.0 / base
        while i > 0:
            valeur += facteur * (i % base)
            i //= base
            facteur /= base
        return valeur

    return [tuple(radical(i, _PREMIERS[j]) for j in range(k)) for i in range(depart, depart + n)]


#: Nombres directeurs de Sobol (Joe et Kuo, new-joe-kuo-6.21201), dimensions 2 à 16 :
#: (degré s du polynôme primitif, ses coefficients a, les m_i initiaux).
_SOBOL: tuple[tuple[int, int, tuple[int, ...]], ...] = (
    (1, 0, (1,)),
    (2, 1, (1, 3)),
    (3, 1, (1, 3, 1)),
    (3, 2, (1, 1, 1)),
    (4, 1, (1, 1, 3, 3)),
    (4, 4, (1, 3, 5, 13)),
    (5, 2, (1, 1, 5, 5, 17)),
    (5, 4, (1, 1, 5, 5, 5)),
    (5, 7, (1, 1, 7, 11, 19)),
    (5, 11, (1, 1, 5, 1, 1)),
    (5, 13, (1, 1, 1, 3, 11)),
    (5, 14, (1, 3, 5, 5, 31)),
    (6, 1, (1, 3, 3, 9, 7, 49)),
    (6, 13, (1, 1, 1, 15, 21, 21)),
    (6, 16, (1, 3, 1, 13, 27, 49)),
)
_BITS = 32


def _directions(dimension: int) -> list[int]:
    """Les ``_BITS`` nombres directeurs d'une dimension (0 : la première, m_i = 1)."""
    if dimension == 0:
        return [1 << (_BITS - i) for i in range(1, _BITS + 1)]
    s, a, m = _SOBOL[dimension - 1]
    v = [m[i] << (_BITS - 1 - i) for i in range(s)]
    for i in range(s, _BITS):
        suivant = v[i - s] ^ (v[i - s] >> s)
        for k in range(1, s):
            if (a >> (s - 1 - k)) & 1:
                suivant ^= v[i - k]
        v.append(suivant)
    return v


def sobol(n: int, k: int, graine: int | None = 0, depart: int = 0) -> list[Point]:
    """Les ``n`` points de la suite de Sobol en dimension ``k``, à partir du rang ``depart``.

    Ordre de Gray (Antonov-Saleev), comme les implémentations de référence.
    Chaque bloc de ``2^m`` points consécutifs alignés stratifie chaque axe en
    ``2^m`` tranches égales : préférer des effectifs puissances de 2.
    ``graine`` applique un **décalage digital** aléatoire (XOR par axe), qui
    conserve cette propriété et retire le point (0, …, 0) ; ``None`` : suite brute.
    """
    if k > len(_SOBOL) + 1:
        raise ValueError(f"suite de Sobol : au plus {len(_SOBOL) + 1} facteurs")
    if n <= 0 or k <= 0:
        return []
    directions = [_directions(j) for j in range(k)]
    decalage = (
        [0] * k
        if graine is None
        else [int(x) for x in np.random.default_rng(graine).integers(0, 1 << _BITS, size=k)]
    )
    echelle = 1.0 / (1 << _BITS)
    points: list[Point] = []
    for i in range(depart, depart + n):
        gray = i ^ (i >> 1)
        point = []
        for j in range(k):
            x, bit = decalage[j], 0
            g = gray
            while g:
                if g & 1:
                    x ^= directions[j][bit]
                g >>= 1
                bit += 1
            point.append(x * echelle)
        points.append(tuple(point))
    return points


def sous_ensemble_maximin(points: Sequence[Sequence[float]], n: int) -> list[int]:
    """Indices de ``n`` points bien répartis parmi ``points`` (glouton, maximin).

    Sert à extraire d'un plan basse fidélité le sous-plan haute fidélité
    emboîté. Part du point le plus central, puis ajoute à chaque pas le point le
    plus éloigné de ceux déjà choisis.
    """
    if n >= len(points):
        return list(range(len(points)))
    if n <= 0:
        return []
    tableau = np.asarray(points, dtype=float)
    etendue = np.ptp(tableau, axis=0)
    tableau = (tableau - tableau.min(axis=0)) / np.where(etendue > 0, etendue, 1.0)
    choisis = [int(np.argmin(((tableau - tableau.mean(axis=0)) ** 2).sum(-1)))]
    distances = ((tableau - tableau[choisis[0]]) ** 2).sum(-1)
    while len(choisis) < n:
        suivant = int(np.argmax(distances))
        choisis.append(suivant)
        distances = np.minimum(distances, ((tableau - tableau[suivant]) ** 2).sum(-1))
    return choisis
