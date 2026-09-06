"""La loi du coefficient dispersé — biais et facteur d'échelle **combinés**.

Le tirage rend deux nombres par coefficient, et les lois de ces deux nombres
sont connues. Mais la question posée n'est pas « comment se répartit le
biais » : c'est **comment se répartit le coefficient**, une fois la relation
de reconstruction appliquée ::

    c_dispersé = biais + FE · c        (convention linéaire)

C'est ce que calcule ce module : la loi de ``c_dispersé`` à valeur nominale
fixée, rendue comme une densité continue et non comme un histogramme.

Deux chemins, dans cet ordre
----------------------------
1. **Exact.** À nominal fixé, les conventions livrées — et la plupart des
   conventions maison — sont *affines* en (biais, FE) : ``c_disp = a·biais +
   b·FE + cst``. La loi de cette combinaison est alors calculée exactement par
   OpenTURNS (``LinearCombinationDistribution``, inversion de la fonction
   caractéristique), quelles que soient les familles des deux composantes —
   uniforme plus gaussienne tronquée comprise. L'affinité n'est pas supposée :
   elle est **mesurée**, en évaluant la relation en quelques points et en
   vérifiant qu'elle s'y superpose à sa propre forme affine.

2. **Lissé.** Sinon (relation maison non affine), un gros tirage LHS —
   20 000 points par défaut — passe dans la relation, et sa densité est
   estimée par noyau (``ot.KernelSmoothing``). À cet effectif la courbe est
   indiscernable de la densité exacte, et la figure dit laquelle des deux
   elle montre.

Dans les deux cas la loi rendue expose la même interface — ``pdf``,
``quantile``, ``M_theorique``, ``ET_theorique``, ``plage_utile`` — que
:class:`cfd_dispersion.core.loi.LoiDispersion`, de sorte que les figures ne
distinguent pas les deux cas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import openturns as ot

from .alea import graine_temporaire, vers_numpy
from .convention import Convention, ConventionArg, convention
from .lois import LoiCoefficient

__all__ = [
    "GRAINE_LISSAGE",
    "N_LISSAGE",
    "TOLERANCE_ACCORD",
    "AccordModele",
    "LoiCombinee",
    "comparer_au_modele",
    "decomposition_affine",
    "loi_combinee",
]

#: Effectif du tirage de secours, quand la relation n'est pas affine.
N_LISSAGE: int = 20_000

#: Graine de ce tirage. Fixée, pour qu'une même figure redessinée soit
#: identique : la courbe montrée est une propriété de la loi, pas un aléa
#: supplémentaire que l'appelant aurait à subir.
GRAINE_LISSAGE: int = 20_240_101

#: Tolérance relative du contrôle d'affinité.
_TOL_AFFINE: float = 1e-9

#: Tolérance relative de l'accord entre le coefficient calculé et celui rendu
#: par le modèle. Serrée : les deux doivent être *le même nombre*, à l'erreur
#: d'écriture près. Un écart plus grand n'est pas du bruit, c'est un désaccord.
TOLERANCE_ACCORD: float = 1e-6


def decomposition_affine(
    relation: Convention,
    nominal: float,
) -> tuple[float, float, float] | None:
    """Décompose ``relation(c, biais, FE)`` en ``a·biais + b·FE + cst``.

    À valeur nominale *fixée*, une relation de reconstruction est presque
    toujours affine en ses deux composantes — c'est le cas des trois
    conventions livrées, et de toute relation de la forme
    ``biais + f(c)·FE``, si tordue que soit ``f``.

    La décomposition est **mesurée** en trois évaluations, puis **vérifiée**
    en trois autres : une relation non affine est donc détectée, pas
    supposée absente.

    Returns
    -------
    (a, b, cst), ou None si la relation n'est pas affine en (biais, FE).
    """
    c = float(nominal)

    def evaluer(biais: float, fe: float) -> float:
        return float(np.asarray(relation(c, biais, fe), dtype=float).reshape(-1)[0])

    cst = evaluer(0.0, 0.0)
    a = evaluer(1.0, 0.0) - cst
    b = evaluer(0.0, 1.0) - cst

    if not all(math.isfinite(v) for v in (cst, a, b)):
        return None

    echelle = 1.0 + abs(cst) + abs(a) + abs(b)
    for biais, fe in ((1.0, 1.0), (2.0, -3.0), (-0.5, 0.25)):
        attendu = cst + a * biais + b * fe
        obtenu = evaluer(biais, fe)
        if abs(obtenu - attendu) > _TOL_AFFINE * echelle * (1.0 + abs(biais) + abs(fe)):
            return None

    return a, b, cst


@dataclass(frozen=True)
class LoiCombinee:
    """La loi du coefficient dispersé, à valeur nominale fixée.

    Attributes
    ----------
    coefficient:
        Le nom du coefficient, pour les titres.
    nominal:
        La valeur nominale à laquelle la loi est calculée. Une loi combinée
        n'a de sens qu'en un point : ``FE`` multiplie le nominal, donc la
        dispersion absolue du coefficient varie le long d'un balayage.
    convention:
        La relation employée.
    distribution:
        La distribution OpenTURNS, exacte ou lissée.
    exacte:
        Vrai si la loi est calculée exactement, faux si elle est estimée par
        noyau sur un tirage.
    poids:
        ``(a, b, cst)`` de la décomposition affine, ou None.
    n_lissage:
        Effectif du tirage de secours ; 0 quand la loi est exacte.
    """

    coefficient: str
    nominal: float
    convention: Convention
    distribution: Any
    exacte: bool
    poids: tuple[float, float, float] | None = None
    n_lissage: int = 0

    # ------------------------------------------------------------------
    # Description
    # ------------------------------------------------------------------

    @property
    def M_theorique(self) -> float:
        """Moyenne du coefficient dispersé."""
        return float(self.distribution.getMean()[0])

    @property
    def ET_theorique(self) -> float:
        """Écart-type du coefficient dispersé — un vrai σ, celui-là."""
        return float(self.distribution.getStandardDeviation()[0])

    @property
    def est_degeneree(self) -> bool:
        """Vrai si le coefficient dispersé est en fait déterministe."""
        return self.ET_theorique == 0.0

    @property
    def methode(self) -> str:
        """Comment la loi a été obtenue, en clair, pour la boîte de paramètres."""
        if self.exacte:
            return "loi exacte (combinaison linéaire)"
        return f"densité lissée (LHS n={self.n_lissage:,})".replace(",", " ")

    @property
    def methode_courte(self) -> str:
        """La même chose en trois mots, pour une boîte de figure.

        La boîte du panneau partage sa largeur avec la légende : une ligne de
        trop la fait passer dessous.
        """
        if self.exacte:
            return "loi exacte"
        return f"loi lissée (LHS {self.n_lissage:,})".replace(",", " ")

    @property
    def ecart(self) -> float:
        """Écart moyen au nominal, en valeur absolue."""
        return self.M_theorique - self.nominal

    def pourcent(self, valeur: float) -> float | None:
        """*valeur* rapportée au nominal, en pourcentage d'écart.

        Rend None quand le nominal est nul : le pourcentage n'y a pas de sens,
        et une figure vaut mieux muette que fausse.
        """
        if self.nominal == 0.0:
            return None
        return 100.0 * (float(valeur) - self.nominal) / abs(self.nominal)

    # ------------------------------------------------------------------
    # Densité, quantiles, bornes
    # ------------------------------------------------------------------

    def pdf(self, x: object) -> np.ndarray:
        """Densité de probabilité aux abscisses *x*, forme ``(n,)``."""
        points = np.atleast_1d(np.asarray(x, dtype=float))
        return vers_numpy(self.distribution.computePDF([[float(v)] for v in points]))

    def cdf(self, x: object) -> np.ndarray:
        """Fonction de répartition aux abscisses *x*, forme ``(n,)``."""
        points = np.atleast_1d(np.asarray(x, dtype=float))
        return vers_numpy(self.distribution.computeCDF([[float(v)] for v in points]))

    def quantile(self, p: object) -> np.ndarray:
        """Quantiles aux probabilités *p*, forme ``(n,)``."""
        probas = np.atleast_1d(np.asarray(p, dtype=float))
        if np.any((probas < 0.0) | (probas > 1.0)):
            raise ValueError("les probabilités doivent être dans [0, 1]")
        return np.array([float(self.distribution.computeQuantile(float(v))[0]) for v in probas])

    def bornes(self) -> tuple[float, float] | None:
        """Les bornes du support, ou None s'il n'est pas borné ou pas exact.

        Une densité lissée n'a pas de bornes à montrer : celles de son
        échantillon ne sont pas celles de la loi.
        """
        if not self.exacte:
            return None
        plage = self.distribution.getRange()
        bas = float(plage.getLowerBound()[0])
        haut = float(plage.getUpperBound()[0])
        fini = plage.getFiniteLowerBound()[0] and plage.getFiniteUpperBound()[0]
        return (bas, haut) if fini else None

    def plage_utile(self, *, k: float = 4.0, marge: float = 0.05) -> tuple[float, float]:
        """Bornes finies utilisables pour tracer la loi."""
        moyenne, sigma = self.M_theorique, self.ET_theorique
        if sigma == 0.0:
            demi = max(abs(moyenne), 1.0) * 0.1
            return (moyenne - demi, moyenne + demi)

        plage = self.distribution.getRange()
        bas = max(float(plage.getLowerBound()[0]), moyenne - k * sigma)
        haut = min(float(plage.getUpperBound()[0]), moyenne + k * sigma)
        largeur = haut - bas
        return (bas - marge * largeur, haut + marge * largeur)


def loi_combinee(
    loi: LoiCoefficient,
    nominal: float,
    *,
    convention_: ConventionArg = None,
    n: int = N_LISSAGE,
    graine: int = GRAINE_LISSAGE,
) -> LoiCombinee:
    """Construit la loi du coefficient dispersé en une valeur nominale.

    Parameters
    ----------
    loi:
        Les deux lois du coefficient (biais, facteur d'échelle).
    nominal:
        La valeur nominale du coefficient, un scalaire.
    convention_:
        La relation de reconstruction. Défaut : ``"lineaire"``.
    n:
        Effectif du tirage de secours, employé seulement si la relation n'est
        pas affine.
    graine:
        Graine de ce tirage. Fixe par défaut, pour que la même figure
        redessinée donne la même courbe.

    Returns
    -------
    LoiCombinee

    Examples
    --------
    >>> from cfd_dispersion import charger_lois, loi_combinee
    >>> lois = charger_lois({"CN": {"Biais_Type": 5, "Biais_M": 0.0,
    ...                            "Biais_ET": 0.02, "FE_Type": 6,
    ...                            "FE_M": 1.0, "FE_ET": 0.08}})
    >>> combinee = loi_combinee(lois["CN"], 0.85)
    >>> combinee.exacte
    True
    >>> round(combinee.M_theorique, 4)
    0.85
    """
    nominal_ = float(np.asarray(nominal, dtype=float).reshape(-1)[0])
    if not math.isfinite(nominal_):
        raise ValueError(f"la valeur nominale doit être finie, reçu {nominal!r}")

    relation = convention(convention_)
    poids = decomposition_affine(relation, nominal_)

    if poids is not None:
        distribution = _combinaison_exacte(loi, poids)
        if distribution is not None:
            return LoiCombinee(
                coefficient=loi.nom,
                nominal=nominal_,
                convention=relation,
                distribution=distribution,
                exacte=True,
                poids=poids,
            )

    return LoiCombinee(
        coefficient=loi.nom,
        nominal=nominal_,
        convention=relation,
        distribution=_combinaison_lissee(loi, nominal_, relation, n=n, graine=graine),
        exacte=False,
        poids=poids,
        n_lissage=n,
    )


def _combinaison_exacte(loi: LoiCoefficient, poids: tuple[float, float, float]) -> Any:
    """``a·biais + b·FE + cst`` par OpenTURNS, ou None si la voie exacte échoue.

    Les composantes dégénérées — et celles de poids nul — sont repliées dans
    la constante plutôt que passées comme masses de Dirac : c'est exactement
    la même loi, sans faire reposer le calcul sur le traitement d'un cas
    limite.
    """
    a, b, cst = poids
    lois_continues: list[Any] = []
    facteurs: list[float] = []

    for facteur, composante in ((a, loi.biais), (b, loi.fe)):
        if facteur == 0.0 or composante.est_degeneree:
            cst += facteur * composante.M_theorique
        else:
            lois_continues.append(composante.distribution)
            facteurs.append(facteur)

    if not lois_continues:
        return ot.Dirac(cst)

    try:
        return ot.LinearCombinationDistribution(lois_continues, facteurs, cst)
    except AttributeError:  # pragma: no cover - OpenTURNS < 1.26
        return ot.RandomMixture(lois_continues, facteurs, cst)
    except Exception:  # pragma: no cover - repli sur le lissage
        return None


def _combinaison_lissee(
    loi: LoiCoefficient,
    nominal: float,
    relation: Convention,
    *,
    n: int,
    graine: int,
) -> Any:
    """La densité du coefficient dispersé, estimée par noyau sur un LHS.

    Le plan LHS et non Monte-Carlo brut : à effectif égal il remplit mieux le
    plan (biais, FE), donc la densité estimée est plus lisse — et c'est bien
    la seule chose qu'on lui demande.
    """
    jointe = ot.JointDistribution([loi.biais.distribution, loi.fe.distribution])
    with graine_temporaire(graine):
        plan = np.asarray(ot.LHSExperiment(jointe, int(n)).generate(), dtype=float)

    valeurs = np.asarray(relation(nominal, plan[:, 0], plan[:, 1]), dtype=float).ravel()
    etendue = float(np.ptp(valeurs))
    if etendue == 0.0:
        return ot.Dirac(float(valeurs[0]))

    echantillon = ot.Sample(valeurs.reshape(-1, 1))
    noyau = ot.KernelSmoothing()
    # Les lois tronquées donnent une combinaison à support borné : sans
    # correction de bord, le noyau déborde des bornes et rabote le sommet.
    noyau.setBoundaryCorrection(True)
    return noyau.build(echantillon)


@dataclass(frozen=True)
class AccordModele:
    """Le coefficient calculé, celui rendu par le modèle, et leur écart.

    Le modèle applique le tirage lui-même ; le paquet le réapplique à la valeur
    nominale. Les deux doivent tomber sur le même nombre. Quand ils n'y tombent
    pas, ce n'est pas du bruit numérique : c'est une convention différente de
    part et d'autre (le facteur 100 de ``pourcentage``), une valeur nominale de
    référence qui n'est pas celle qu'a vue le modèle, ou un modèle qui
    n'applique pas la dispersion là où on croit.

    C'est le seul contrôle du paquet qui porte sur le **modèle** et non sur le
    tirage — et il ne coûte rien, puisque les deux nombres sont là.

    Attributes
    ----------
    calcul:
        ``convention(nominal, biais, FE)``, ce que le paquet obtient.
    modele:
        Ce que le modèle a rendu pour ce tirage.
    ecart:
        ``modele - calcul``.
    ecart_relatif:
        L'écart rapporté à l'échelle du coefficient, en pourcentage.
    accord:
        Vrai si l'écart tient dans la tolérance.
    tolerance:
        La tolérance **relative** employée.
    """

    calcul: float
    modele: float
    ecart: float
    ecart_relatif: float
    accord: bool
    tolerance: float = TOLERANCE_ACCORD

    @property
    def resume(self) -> str:
        """Le verdict en une ligne, pour un terminal ou un inventaire."""
        if self.accord:
            return "modèle = calcul"
        return f"modèle ≠ calcul : {self.ecart:+.4g} ({self.ecart_relatif:+.3g} %)"

    @property
    def lignes(self) -> tuple[str, ...]:
        """Le même verdict en lignes courtes, pour une boîte de figure.

        Le chiffre passe à la ligne : la boîte partage sa largeur avec la
        légende, et une ligne trop longue passe dessous.
        """
        if self.accord:
            return ("modèle = calcul",)
        return ("modèle ≠ calcul", f"{self.ecart:+.4g} ({self.ecart_relatif:+.3g} %)")


def comparer_au_modele(
    calcul: float,
    modele: float,
    *,
    nominal: float | None = None,
    tolerance: float = TOLERANCE_ACCORD,
) -> AccordModele:
    """Compare le coefficient recalculé à celui que le modèle a rendu.

    Parameters
    ----------
    calcul:
        Le coefficient reconstruit ici, ``convention(nominal, biais, FE)``.
    modele:
        Le coefficient rendu par le modèle pour ce même tirage.
    nominal:
        La valeur nominale, qui donne son échelle à l'écart relatif. À défaut,
        l'échelle est celle des deux valeurs comparées.
    tolerance:
        Tolérance **relative** à cette échelle.

    Returns
    -------
    AccordModele

    Examples
    --------
    >>> comparer_au_modele(0.8325, 0.8325).accord
    True
    >>> comparer_au_modele(0.8325, 0.8400, nominal=0.85).accord
    False
    """
    calcule = float(calcul)
    rendu = float(modele)
    ecart = rendu - calcule

    # L'échelle est celle du coefficient — son nominal — comme partout ailleurs
    # dans le paquet : un écart de 0.001 n'a pas le même sens sur un CA de 0.03
    # et sur un CN de 0.85. Sans nominal, celle des deux valeurs comparées.
    echelle = abs(float(nominal)) if nominal is not None else 0.0
    if echelle == 0.0:
        echelle = max(abs(calcule), abs(rendu)) or 1.0

    return AccordModele(
        calcul=calcule,
        modele=rendu,
        ecart=ecart,
        ecart_relatif=100.0 * ecart / echelle,
        accord=abs(ecart) <= tolerance * echelle,
        tolerance=tolerance,
    )
