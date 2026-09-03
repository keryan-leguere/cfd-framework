"""Les six lois de dispersion, adossées à OpenTURNS.

Une loi est décrite par trois nombres — ceux que porte votre table de lois :

    type_loi   entier 1..6, la famille
    M          moyenne / centre
    ET         **demi-étendue**, et non écart-type

La convention ``ET`` est la source d'erreur numéro un de ce modèle, donc elle
est répétée partout : pour les familles gaussiennes, ``σ = ET/2``. ``ET`` est
donc une demi-largeur à 2σ, *pas* un écart-type. Une table écrite en écarts-
types et lue ici donne des dispersions deux fois trop larges, ce qui reste
parfaitement plausible à l'œil — d'où :mod:`cfd_dispersion.core.validation`,
qui le détecte.

Correspondance avec OpenTURNS
-----------------------------
======  =================  ==========================================  =================
type    libellé            distribution                                support
======  =================  ==========================================  =================
1       Nulle              ``Dirac(0)``                                {0}
2       Constante          ``Dirac(M)``                                {M}
3       Uniforme           ``Uniform(M-ET, M+ET)``                     M ± ET
4       Gaussienne         ``Normal(M, ET/2)``                         ℝ
5       Gaussienne ±3σ     ``TruncatedNormal(M, ET/2, M±1.5·ET)``      M ± 1.5·ET
6       Gaussienne ±2σ     ``TruncatedNormal(M, ET/2, M±1.0·ET)``      M ± 1.0·ET
======  =================  ==========================================  =================

Les bornes des types 5 et 6 sont bien ``M ± 3σ`` et ``M ± 2σ`` avec ``σ = ET/2``,
soit ``M ± 1.5·ET`` et ``M ± 1.0·ET``.

Deux pièges d'OpenTURNS, vérifiés et traités ici
------------------------------------------------
``Normal(M, σ).getRange()`` rend un intervalle **fini** (environ ``M ± 7.65 σ``) :
c'est une plage numérique, pas le support mathématique. :meth:`LoiDispersion.support`
rend donc ``(-inf, +inf)`` pour le type 4, sans quoi une queue lointaine mais
légitime serait comptée « hors support ». Pour tracer, utiliser
:meth:`LoiDispersion.plage_utile`.

``Normal(M, 0)`` est **accepté** par OpenTURNS (loi dégénérée silencieuse) alors
que ``Uniform(M, M)`` et ``TruncatedNormal(σ=0)`` sont refusés. Plutôt que de
dépendre de ces refus, ``ET = 0`` est ramené explicitement à ``Dirac(M)`` pour
les types 3 à 6 : une seule règle, le même comportement pour les quatre.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Union

import numpy as np
import openturns as ot

from .alea import graine_temporaire, vers_numpy

__all__ = [
    "LIBELLES_TYPE",
    "TYPES_VALIDES",
    "LoiDispersion",
    "libelle_type",
]

#: Libellé lisible de chaque type de loi.
LIBELLES_TYPE: dict[int, str] = {
    1: "Nulle",
    2: "Constante",
    3: "Uniforme",
    4: "Gaussienne",
    5: "Gaussienne ±3σ",
    6: "Gaussienne ±2σ",
}

#: Les types acceptés.
TYPES_VALIDES: frozenset[int] = frozenset(LIBELLES_TYPE)

#: Familles gaussiennes : celles où ``σ = ET/2``.
_TYPES_GAUSSIENS: frozenset[int] = frozenset({4, 5, 6})

#: Multiple de σ auquel les types tronqués sont coupés.
_TRONCATURE: dict[int, float] = {5: 3.0, 6: 2.0}

#: Méthodes d'échantillonnage acceptées par :meth:`LoiDispersion.tirer`.
METHODES: tuple[str, ...] = ("mc", "lhs", "sobol")

Reel = Union[float, int]


def libelle_type(type_loi: int) -> str:
    """Retourne le libellé lisible d'un type de loi.

    Raises
    ------
    ValueError
        Si *type_loi* n'est pas l'un des six types connus.
    """
    if type_loi not in TYPES_VALIDES:
        raise ValueError(
            f"type de loi inconnu : {type_loi!r} ; attendu l'un de {sorted(TYPES_VALIDES)}"
        )
    return LIBELLES_TYPE[type_loi]


@lru_cache(maxsize=512)
def _construire(type_loi: int, M: float, ET: float) -> ot.Distribution:
    """Construit la distribution OpenTURNS d'un triplet (type, M, ET).

    Mise en cache : une étude rejoue les mêmes quelques lois des milliers de
    fois, et les distributions OpenTURNS n'ont pas d'état propre — le tirage
    passe par le générateur global — donc les partager est sans effet de bord.
    """
    if type_loi == 1:
        return ot.Dirac(0.0)
    if type_loi == 2:
        return ot.Dirac(M)

    # ET nul : les quatre familles restantes se réduisent à une masse en M.
    if ET == 0.0:
        return ot.Dirac(M)

    if type_loi == 3:
        return ot.Uniform(M - ET, M + ET)

    sigma = 0.5 * ET
    if type_loi == 4:
        return ot.Normal(M, sigma)

    k = _TRONCATURE[type_loi]
    return ot.TruncatedNormal(M, sigma, M - k * sigma, M + k * sigma)


@dataclass(frozen=True)
class LoiDispersion:
    """Une composante de dispersion : un biais, ou un facteur d'échelle.

    Parameters
    ----------
    type_loi:
        Entier 1 à 6 choisissant la famille (voir le tableau du module).
    M:
        Moyenne / centre de la loi.
    ET:
        Demi-étendue. Pour les familles gaussiennes, ``σ = ET/2`` — ce n'est
        **pas** un écart-type.

    Examples
    --------
    >>> loi = LoiDispersion(type_loi=6, M=0.0, ET=0.10)
    >>> loi.label
    'Gaussienne ±2σ'
    >>> loi.support()
    (-0.1, 0.1)
    >>> round(loi.sigma_nominal, 4)
    0.05
    """

    type_loi: int
    M: float = 0.0
    ET: float = 0.0

    def __post_init__(self) -> None:
        if self.type_loi not in TYPES_VALIDES:
            raise ValueError(
                f"type de loi inconnu : {self.type_loi!r} ; attendu l'un de {sorted(TYPES_VALIDES)}"
            )
        if not math.isfinite(self.M):
            raise ValueError(f"M doit être fini, reçu {self.M!r}")
        if not math.isfinite(self.ET):
            raise ValueError(f"ET doit être fini, reçu {self.ET!r}")
        if self.ET < 0.0:
            raise ValueError(
                f"ET est une demi-étendue et ne peut pas être négatif, reçu {self.ET!r}"
            )
        # Normalise en flottants : le cache de _construire est sensible au type
        # (1 et 1.0 sont des clés distinctes), et les comparaisons de lois le
        # seraient aussi.
        object.__setattr__(self, "type_loi", int(self.type_loi))
        object.__setattr__(self, "M", float(self.M))
        object.__setattr__(self, "ET", float(self.ET))

    # ------------------------------------------------------------------
    # La distribution OpenTURNS
    # ------------------------------------------------------------------

    @property
    def distribution(self) -> ot.Distribution:
        """La distribution OpenTURNS correspondante."""
        return _construire(self.type_loi, self.M, self.ET)

    # ------------------------------------------------------------------
    # Description
    # ------------------------------------------------------------------

    @property
    def label(self) -> str:
        """Libellé lisible du type."""
        return LIBELLES_TYPE[self.type_loi]

    @property
    def est_degeneree(self) -> bool:
        """Vrai si la loi est une masse de Dirac (aucune dispersion).

        C'est le cas des types 1 et 2, et de tout type dont ``ET`` est nul.
        Les lois dégénérées sont exclues du test de Kolmogorov–Smirnov, qui
        n'est défini que pour des lois continues.
        """
        return self.type_loi in (1, 2) or self.ET == 0.0

    @property
    def est_bornee(self) -> bool:
        """Vrai si le support est borné — soit tout sauf la gaussienne pleine."""
        return not (self.type_loi == 4 and self.ET > 0.0)

    @property
    def sigma_nominal(self) -> float:
        """``ET/2`` pour les familles gaussiennes, 0 sinon.

        C'est le **paramètre** σ passé à OpenTURNS, à ne pas confondre avec
        :attr:`ET_theorique`, l'écart-type réellement obtenu : une gaussienne
        tronquée est plus resserrée que la gaussienne dont elle est issue.
        """
        if self.type_loi in _TYPES_GAUSSIENS:
            return 0.5 * self.ET
        return 0.0

    @property
    def M_theorique(self) -> float:
        """Moyenne exacte de la loi, calculée par OpenTURNS."""
        return float(self.distribution.getMean()[0])

    @property
    def ET_theorique(self) -> float:
        """Écart-type exact de la loi, calculé par OpenTURNS.

        Pour les types 5 et 6, il est strictement inférieur à
        :attr:`sigma_nominal` — la troncature resserre la loi (environ ×0.987
        pour le type 5, ×0.880 pour le type 6). Comparer un échantillon à
        ``ET/2`` plutôt qu'à cette valeur rejetterait des tirages corrects.
        """
        return float(self.distribution.getStandardDeviation()[0])

    def support(self) -> tuple[float, float]:
        """Bornes **mathématiques** du support, ``(bas, haut)``.

        Rend ``(-inf, +inf)`` pour une gaussienne non tronquée. On ne peut pas
        se reposer sur ``getRange()`` d'OpenTURNS ici : il rend une plage
        numérique finie (≈ ``M ± 7.65 σ``) même pour une loi non bornée, ce qui
        ferait passer une queue légitime pour un point hors support.
        """
        if self.type_loi == 4 and self.ET > 0.0:
            return (-math.inf, math.inf)
        plage = self.distribution.getRange()
        return (float(plage.getLowerBound()[0]), float(plage.getUpperBound()[0]))

    def plage_utile(self, *, k: float = 4.0, marge: float = 0.05) -> tuple[float, float]:
        """Bornes **finies** utilisables pour tracer la loi.

        Le support pour les lois bornées, élargi de *marge* ; ``M ± k·σ`` pour
        la gaussienne pleine, dont le support est infini. Une loi dégénérée
        rend un petit intervalle autour de sa masse, pour qu'un axe construit
        dessus ne soit pas de largeur nulle.
        """
        if self.est_degeneree:
            demi = max(abs(self.M), 1.0) * 0.1
            return (self.M - demi, self.M + demi)

        bas, haut = self.support()
        if not (math.isfinite(bas) and math.isfinite(haut)):
            demi = k * self.sigma_nominal
            bas, haut = self.M - demi, self.M + demi

        largeur = haut - bas
        return (bas - marge * largeur, haut + marge * largeur)

    # ------------------------------------------------------------------
    # Densité, répartition, quantiles
    # ------------------------------------------------------------------

    def pdf(self, x: object) -> np.ndarray:
        """Densité de probabilité aux abscisses *x*, forme ``(n,)``.

        Pour une loi dégénérée, OpenTURNS rend la **masse** de probabilité (1
        au point, 0 ailleurs) et non une densité : la grandeur n'est pas
        comparable à celle d'une loi continue, et les figures la tracent en
        conséquence.
        """
        points = np.atleast_1d(np.asarray(x, dtype=float))
        valeurs = self.distribution.computePDF([[float(v)] for v in points])
        return vers_numpy(valeurs)

    def cdf(self, x: object) -> np.ndarray:
        """Fonction de répartition aux abscisses *x*, forme ``(n,)``."""
        points = np.atleast_1d(np.asarray(x, dtype=float))
        valeurs = self.distribution.computeCDF([[float(v)] for v in points])
        return vers_numpy(valeurs)

    def quantile(self, p: object) -> np.ndarray:
        """Quantiles aux probabilités *p*, forme ``(n,)``.

        Utilisé pour les diagrammes quantile-quantile, qui lisent l'accord des
        queues bien mieux qu'un histogramme — là où une loi tronquée dérape.
        """
        probas = np.atleast_1d(np.asarray(p, dtype=float))
        if np.any((probas < 0.0) | (probas > 1.0)):
            raise ValueError("les probabilités doivent être dans [0, 1]")
        return np.array([float(self.distribution.computeQuantile(float(v))[0]) for v in probas])

    # ------------------------------------------------------------------
    # Tirage
    # ------------------------------------------------------------------

    def tirer(
        self,
        n: int,
        *,
        graine: int | None = None,
        methode: str = "mc",
    ) -> np.ndarray:
        """Tire *n* réalisations indépendantes, forme ``(n,)``.

        Parameters
        ----------
        n:
            Nombre de tirages, strictement positif.
        graine:
            Graine posée le temps du tirage, l'état du générateur global étant
            restauré ensuite (voir :func:`cfd_dispersion.core.alea.graine_temporaire`).
        methode:
            ``"mc"`` (Monte-Carlo brut, défaut), ``"lhs"`` (hypercube latin) ou
            ``"sobol"`` (suite à faible discrépance). Sur une composante seule
            la différence est modeste ; elle devient nette en dimension
            supérieure, d'où :func:`cfd_dispersion.core.tirage.tirer_lot`.

        Returns
        -------
        np.ndarray, forme ``(n,)``
        """
        if n <= 0:
            raise ValueError(f"n doit être strictement positif, reçu {n!r}")
        if methode not in METHODES:
            raise ValueError(f"méthode inconnue : {methode!r} ; attendu l'une de {list(METHODES)}")

        dist = self.distribution
        with graine_temporaire(graine):
            if methode == "mc":
                return vers_numpy(dist.getSample(n))
            plan = _plan_experience(dist, n, methode)
            return vers_numpy(plan.generate())


def _plan_experience(dist: ot.Distribution, n: int, methode: str) -> ot.WeightedExperiment:
    """Construit le plan d'expérience LHS ou Sobol pour *dist*."""
    if methode == "lhs":
        return ot.LHSExperiment(dist, n)
    return ot.LowDiscrepancyExperiment(ot.SobolSequence(), dist, n)
