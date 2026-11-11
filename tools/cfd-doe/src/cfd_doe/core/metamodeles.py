"""Métamodèles des plans non tabulés : krigeage et polynômes (00_DOC/02_REMPLISSAGE.md §5–8).

NumPy seul, sur des entrées déjà normalisées par l'appelant :

- :class:`Krigeage` : krigeage ordinaire (processus gaussien, noyau de Matérn
  5/2 anisotrope), portées estimées par maximum de vraisemblance ; il
  interpole les calculs et donne une variance de prédiction ;
- :class:`Polynome` : moindres carrés sur une base de Legendre, de degré total
  donné (plans composites, Box-Behnken) ou de l'espace d'une grille creuse de
  Smolyak (:func:`indices_smolyak`) ;
- :func:`plan_variance_maximale` : le plan d'expériences *du* krigeage, qui
  place chaque point là où la variance a priori est la plus forte, images par
  symétrie comprises.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import product

import numpy as np

__all__ = [
    "Krigeage",
    "Polynome",
    "indices_degre_total",
    "indices_smolyak",
    "matern52",
    "plan_variance_maximale",
]

#: Pépites relatives essayées dans l'ordre : la plus petite qui factorise gagne. Petite,
#: le krigeage interpole les calculs ; elle ne grossit que si la matrice est mal conditionnée
#: (points très proches, portées longues).
PEPITES = (1e-10, 1e-9, 1e-8, 1e-7, 1e-6)
#: Bornes des portées, dans l'espace normalisé [0, 1].
PORTEE_MIN, PORTEE_MAX = 0.03, 20.0


def matern52(x: np.ndarray, y: np.ndarray, portees: np.ndarray) -> np.ndarray:
    """Corrélation de Matérn 5/2 entre les lignes de ``x`` (n, k) et de ``y`` (m, k)."""
    xa, ya = x / portees, y / portees
    # ‖a − b‖² = ‖a‖² + ‖b‖² − 2 a·b : pas de tableau (n, m, k) en mémoire.
    d2 = (xa * xa).sum(1)[:, None] + (ya * ya).sum(1)[None, :] - 2.0 * xa @ ya.T
    r = np.sqrt(np.maximum(d2, 0.0)) * math.sqrt(5.0)
    return np.asarray((1.0 + r + r * r / 3.0) * np.exp(-r))


@dataclass
class Krigeage:
    """Krigeage ordinaire, à une ou plusieurs sorties.

    Plusieurs sorties (``y`` de forme (n, m)) partagent les portées, chacune
    gardant sa moyenne et sa variance : une seule factorisation sert tous les
    coefficients d'un même calcul. ``portees`` : ``None`` pour les estimer
    (maximum de vraisemblance concentrée, recherche par coordonnées en
    échelle log), ou fixées.
    """

    portees: np.ndarray | None = None
    pepite: float = PEPITES[0]
    x: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    moyenne: np.ndarray = field(default_factory=lambda: np.zeros(0))
    variance: np.ndarray = field(default_factory=lambda: np.zeros(0))
    _chol: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    _alpha: np.ndarray = field(default_factory=lambda: np.zeros((0, 0)))
    _r1: np.ndarray = field(default_factory=lambda: np.zeros(0))
    _s: float = 1.0
    _scalaire: bool = False

    # --- ajustement --------------------------------------------------------

    def _decomposer(self, x: np.ndarray, y: np.ndarray, portees: np.ndarray) -> float:
        """Factorise ; renvoie la log-vraisemblance concentrée des sorties non constantes."""
        n = len(x)
        noyau = matern52(x, x, portees)
        for pepite in PEPITES:
            try:
                chol = np.linalg.cholesky(noyau + pepite * np.eye(n))
                break
            except np.linalg.LinAlgError:
                continue
        else:
            raise np.linalg.LinAlgError("krigeage : matrice de corrélation non factorisable")
        self.pepite = pepite
        seconds = np.column_stack([np.ones(n), y])
        resolu = np.linalg.solve(chol.T, np.linalg.solve(chol, seconds))
        r1, ry = resolu[:, 0], resolu[:, 1:]
        s = float(r1.sum())
        mu = ry.sum(0) / s
        residu = y - mu
        alpha = ry - np.outer(r1, mu)
        sigma2 = np.maximum((residu * alpha).sum(0) / n, 0.0)
        self._chol, self._alpha, self._r1, self._s = chol, alpha, r1, s
        self.moyenne, self.variance = mu, sigma2
        actives = sigma2 > 1e-24 * np.maximum(1.0, mu * mu)
        if not actives.any():
            return 0.0
        log_det = 2.0 * float(np.log(np.diag(chol)).sum())
        return float(-0.5 * (n * np.log(sigma2[actives]).sum() + actives.sum() * log_det))

    def _vraisemblance(self, x: np.ndarray, y: np.ndarray, log_portees: np.ndarray) -> float:
        try:
            return self._decomposer(x, y, np.exp(log_portees))
        except np.linalg.LinAlgError:
            return -math.inf

    def ajuster(self, x: np.ndarray, y: np.ndarray) -> Krigeage:
        """Ajuste sur ``x`` (n, k), dans [0, 1]^k, et ``y`` (n,) ou (n, m)."""
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        self._scalaire = y.ndim == 1
        y = y.reshape(len(y), -1)
        if x.ndim != 2 or len(x) != len(y) or len(x) == 0:
            raise ValueError("krigeage : x (n, k) et y (n,) ou (n, m) attendus, n ≥ 1")
        self.x = x
        k = x.shape[1]
        echelle = np.where(np.ptp(y, axis=0) > 0, np.ptp(y, axis=0), 1.0)
        if self.portees is None:
            # Sorties réduites : chacune pèse autant dans la vraisemblance commune.
            z = y / echelle
            bornes = (math.log(PORTEE_MIN), math.log(PORTEE_MAX))
            candidats = np.linspace(math.log(0.08), math.log(3.0), 9)
            scores = [self._vraisemblance(x, z, np.full(k, c)) for c in candidats]
            log_p = np.full(k, candidats[int(np.argmax(scores))])
            meilleur = max(scores)
            pas = 1.0
            for _ in range(4):
                for j in range(k):
                    for sens in (1.0, -1.0):
                        essai = log_p.copy()
                        essai[j] = float(np.clip(essai[j] + sens * pas, *bornes))
                        score = self._vraisemblance(x, z, essai)
                        if score > meilleur + 1e-9:
                            meilleur, log_p = score, essai
                            break
                pas /= 2.0
            self.portees = np.exp(log_p)
        self._decomposer(x, y, np.asarray(self.portees, dtype=float))
        return self

    # --- prédiction --------------------------------------------------------

    def predire(
        self, xs: np.ndarray, ecart_type: bool = False
    ) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
        """Moyenne de prédiction (et écart-type si demandé) aux lignes de ``xs``.

        Forme (n,) pour une sortie scalaire, (n, m) sinon.
        """
        assert self.portees is not None
        xs = np.asarray(xs, dtype=float)
        m = len(self.moyenne)
        moyennes, ecarts = [np.zeros((0, m))], [np.zeros((0, m))]
        for debut in range(0, len(xs), 4096):
            bloc = xs[debut : debut + 4096]
            r = matern52(bloc, self.x, self.portees)
            moyennes.append(self.moyenne + r @ self._alpha)
            if ecart_type:
                v = np.linalg.solve(self._chol, r.T)
                u = 1.0 - r @ self._r1
                facteur = np.maximum(1.0 - (v * v).sum(0) + u * u / self._s, 0.0)
                ecarts.append(np.sqrt(np.outer(facteur, self.variance)))
        moyenne, ecart = np.vstack(moyennes), np.vstack(ecarts)
        if self._scalaire:
            moyenne, ecart = moyenne[:, 0], ecart[:, 0]
        return (moyenne, ecart) if ecart_type else moyenne


# ---------------------------------------------------------------------------
# Polynômes
# ---------------------------------------------------------------------------


def indices_degre_total(k: int, degre: int) -> list[tuple[int, ...]]:
    """Multi-indices de degré total ≤ ``degre`` (base d'un polynôme complet)."""
    return [a for a in product(range(degre + 1), repeat=k) if sum(a) <= degre]


def indices_smolyak(k: int, niveau: int) -> list[tuple[int, ...]]:
    """Multi-indices de l'espace exact de la grille creuse de Clenshaw-Curtis (core.plans).

    Le niveau d'axe ``i`` porte ``1, 3, 5, 9…`` points, donc les degrés
    ``0, 2, 4, 8…`` ; l'espace est l'union des produits tensoriels sur
    ``|i| ≤ niveau``. Sa dimension est le nombre de points de la grille.
    """

    def degre(i: int) -> int:
        return 0 if i == 0 else 2**i

    indices: set[tuple[int, ...]] = set()
    for niveaux in product(range(niveau + 1), repeat=k):
        if sum(niveaux) <= niveau:
            indices.update(product(*(range(degre(i) + 1) for i in niveaux)))
    return sorted(indices)


def _legendre(x: np.ndarray, degre: int) -> np.ndarray:
    """P_0 … P_degre aux points ``x`` (dans [-1, 1]) : tableau (degre + 1, n)."""
    p = np.ones((degre + 1, len(x)))
    if degre >= 1:
        p[1] = x
    for n in range(1, degre):
        p[n + 1] = ((2 * n + 1) * x * p[n] - n * p[n - 1]) / (n + 1)
    return p


@dataclass
class Polynome:
    """Polynôme en base de Legendre, ajusté aux moindres carrés sur [-1, 1]^k."""

    indices: Sequence[tuple[int, ...]]
    coefficients: np.ndarray = field(default_factory=lambda: np.zeros(0))
    rang: int = 0

    def _base(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=float)
        degre = max((max(a) for a in self.indices if a), default=0)
        tables = [_legendre(x[:, j], degre) for j in range(x.shape[1])]
        base = np.ones((len(x), len(self.indices)))
        for colonne, a in enumerate(self.indices):
            for j, d in enumerate(a):
                if d:
                    base[:, colonne] *= tables[j][d]
        return base

    def ajuster(self, x: np.ndarray, y: np.ndarray) -> Polynome:
        """Moindres carrés (norme minimale si la base est sous-déterminée)."""
        base = self._base(x)
        self.coefficients, _, self.rang, _ = np.linalg.lstsq(base, np.asarray(y, float), rcond=None)
        return self

    def predire(self, xs: np.ndarray) -> np.ndarray:
        """Valeur du polynôme aux lignes de ``xs``."""
        return np.asarray(self._base(xs) @ self.coefficients)


# ---------------------------------------------------------------------------
# Plan du krigeage
# ---------------------------------------------------------------------------


def plan_variance_maximale(
    orbites: Sequence[np.ndarray],
    n: int,
    portees: np.ndarray | float,
    connus: np.ndarray | None = None,
) -> list[int]:
    """Choisit ``n`` candidats, un à un, là où la variance a priori est maximale.

    ``orbites[i]`` (m_i, k) : le candidat ``i`` (première ligne) et ses images
    par les symétries, dans [0, 1]^k. Un point choisi informe le krigeage en
    toutes ses images : sur un plan de symétrie elles se confondent avec lui,
    et le point y apporte moins — le critère en tient compte de lui-même.

    Variance de krigeage simple à portées fixées : elle ne dépend que de
    l'emplacement des points, pas des résultats, d'où un plan constructible
    avant tout calcul. Mise à jour de rang 1 (Cholesky incrémental) sur le
    réservoir des orbites. ``connus`` (m, k) : points déjà calculés, images
    comprises (enrichissement d'un plan existant).
    """
    if n <= 0 or not orbites:
        return []
    k = orbites[0].shape[1]
    portees = np.broadcast_to(np.asarray(portees, dtype=float), (k,))
    connus = np.zeros((0, k)) if connus is None else np.asarray(connus, dtype=float)
    # Réservoir : les orbites des candidats, puis les points déjà calculés.
    reservoir = np.vstack([*orbites, connus])
    debuts = np.cumsum([0, *(len(o) for o in orbites)])
    tetes = debuts[:-1]
    variance = np.ones(len(reservoir))
    facteurs: list[np.ndarray] = []

    def conditionner(indice: int) -> None:
        """Ajoute le point ``reservoir[indice]`` aux données (mise à jour de rang 1)."""
        nonlocal variance
        covariance = matern52(reservoir, reservoir[indice : indice + 1], portees)[:, 0]
        for u in facteurs:
            covariance -= u * u[indice]
        pivot = covariance[indice]
        if pivot <= 1e-10:
            return  # point confondu avec un point déjà vu
        u = covariance / math.sqrt(pivot)
        facteurs.append(u)
        variance = np.maximum(variance - u * u, 0.0)

    for indice in range(int(debuts[-1]), len(reservoir)):
        conditionner(indice)
    choisis: list[int] = []
    disponibles = np.ones(len(orbites), dtype=bool)
    for _ in range(min(n, len(orbites))):
        scores = np.where(disponibles, variance[tetes], -1.0)
        i = int(np.argmax(scores))
        if scores[i] <= 1e-12:
            break
        choisis.append(i)
        disponibles[i] = False
        for indice in range(int(debuts[i]), int(debuts[i + 1])):
            conditionner(indice)
    return choisis
