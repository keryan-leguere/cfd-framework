"""Le tirage réalisé suit-il vraiment la loi demandée ?

C'est l'indicateur derrière les cas d'usage 2.1 et 2.2 : on appelle un modèle
mille fois, on récupère ses tirages, et on veut savoir — par point de vol et
par coefficient — si ce qui a été tiré correspond à ce qui a été prescrit.

Trois contrôles, dans cet ordre, parce qu'ils échouent pour des raisons
différentes et que le motif doit dire laquelle :

1. **Support** — un seul point hors des bornes de la loi est rédhibitoire.
   C'est le contrôle qui attrape une loi tronquée tirée comme une gaussienne
   pleine, et aucun test de distance ne le ferait de façon fiable : sur mille
   points, la queue fautive en compte une poignée. Mesuré : un échantillon de
   loi tronquée additionné de deux points hors bornes passe le test de
   Kolmogorov–Smirnov avec p = 0.85.

2. **Moments** — moyenne et écart-type contre les valeurs **exactes**
   d'OpenTURNS, pas contre les paramètres. Une gaussienne tronquée est plus
   resserrée que la gaussienne dont elle sort (×0.88 au type 6) : comparer à
   ``ET/2`` rejetterait des tirages parfaitement corrects.

3. **Kolmogorov–Smirnov** — ``ot.FittingTest.Kolmogorov`` contre la fonction de
   répartition exacte, et non contre un histogramme.

Les tolérances et le bruit d'échantillonnage
--------------------------------------------
Les écarts de moments sont exprimés en grandeurs *pratiques* — un décalage de
moyenne en unités de σ, une erreur d'écart-type en relatif — et non en
p-valeurs. Un test de significativité seul se comporte mal aux deux bouts :
sur 100 tirages il ne détecte rien, sur 100 000 il rejette un écart de 1 %
sans importance.

Mais une tolérance pratique fixe se ferait piéger dans l'autre sens sur les
petits effectifs, où le bruit d'échantillonnage dépasse la tolérance. Le seuil
effectivement appliqué est donc ``max(tolérance, marge de bruit)``, la marge
valant quatre erreurs-types : ``4/√n`` pour la moyenne (en unités de σ) et
``4/√(2n)`` pour l'écart-type (en relatif). Un tirage correct passe alors quel
que soit *n*, et une erreur de facteur 2 sur ``ET`` — la confusion
demi-étendue / écart-type — échoue quel que soit *n*.

Le piège de la multiplicité
---------------------------
Le test de Kolmogorov–Smirnov rejette à tort dans α des cas : c'est sa
définition. Sur **un** tirage, 5 % est acceptable. Sur un tableau de synthèse
de cinquante points de vol et quatre composantes, cela fait deux cents tests et
donc une dizaine de cases rouges qui ne sont que du bruit — dans un livrable
dont tout l'intérêt est justement qu'on ne regarde que les cases rouges.

:func:`valider_lot` sait combien de tests il lance, et corrige donc le seuil
pour tenir *α sur l'ensemble du tableau* (correction de Šidák par défaut :
``α_test = 1 − (1 − α)^(1/m)``). Un tableau entièrement conforme sort alors
tout vert dans 95 % des cas, au lieu de presque jamais. La correction ne coûte
rien en détection réelle : une loi tirée de travers donne une p-valeur si
petite qu'aucun seuil raisonnable ne la sauve.

:func:`valider` seul ne corrige rien — il ne sait pas combien d'autres tests
l'accompagnent. Passer ``correction=None`` à :func:`valider_lot` retrouve ce
comportement, test par test.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import openturns as ot
import pandas as pd

from .loi import LoiDispersion
from .lois import COMPOSANTES, JeuDeLois

__all__ = [
    "ALPHA_DEFAUT",
    "CORRECTIONS",
    "N_MIN_DEFAUT",
    "TOL_ET_DEFAUT",
    "TOL_M_DEFAUT",
    "Verdict",
    "alpha_corrige",
    "valider",
    "valider_lot",
]

#: Risque de première espèce du test de Kolmogorov–Smirnov.
ALPHA_DEFAUT = 0.05

#: Décalage de moyenne toléré, en unités de l'écart-type de la loi.
TOL_M_DEFAUT = 0.10

#: Erreur relative tolérée sur l'écart-type.
TOL_ET_DEFAUT = 0.10

#: En deçà, l'échantillon est jugé trop court pour conclure.
N_MIN_DEFAUT = 20

#: Nombre d'erreurs-types absorbées par la marge de bruit.
_MARGE_BRUIT = 4.0

#: Corrections de multiplicité disponibles pour :func:`valider_lot`.
CORRECTIONS: tuple[str, ...] = ("sidak", "bonferroni")

#: Motifs de rejet, dans l'ordre où ils sont testés.
MOTIFS: tuple[str, ...] = ("effectif", "support", "moyenne", "écart-type", "forme")


@dataclass(frozen=True)
class Verdict:
    """Le résultat d'une validation, pour une composante d'un coefficient.

    Attributes
    ----------
    coefficient, composante:
        Ce qui a été validé (``"Cm_alpha"``, ``"Biais"``).
    n:
        Effectif de l'échantillon.
    ks_D, ks_p:
        Statistique et p-valeur de Kolmogorov–Smirnov. ``nan`` pour une loi
        dégénérée, où le test n'est pas défini.
    M_empirique, ET_empirique:
        Moments mesurés sur l'échantillon.
    M_theorique, ET_theorique:
        Moments exacts de la loi, calculés par OpenTURNS.
    ecart_M:
        ``|M_empirique − M_theorique| / ET_theorique`` — un décalage de moyenne
        en unités de l'écart-type de la loi.
    ecart_ET:
        ``|ET_empirique − ET_theorique| / ET_theorique`` — une erreur relative.
    hors_support:
        Nombre de points hors des bornes de la loi.
    valide:
        Le verdict.
    motif:
        Vide si valide ; sinon le contrôle qui a échoué (voir :data:`MOTIFS`).
    """

    coefficient: str
    composante: str
    n: int
    ks_D: float
    ks_p: float
    M_empirique: float
    ET_empirique: float
    M_theorique: float
    ET_theorique: float
    ecart_M: float
    ecart_ET: float
    hors_support: int
    valide: bool
    motif: str

    def vers_dict(self) -> dict[str, Any]:
        """Le verdict en dictionnaire, pour construire un tableau."""
        return asdict(self)

    @property
    def resume(self) -> str:
        """Une ligne lisible, pour une boîte de texte ou un journal."""
        etat = "VALIDÉ" if self.valide else f"REJETÉ ({self.motif})"
        return (
            f"{self.coefficient} {self.composante} : {etat} · n={self.n} · "
            f"M {self.M_empirique:.4g}/{self.M_theorique:.4g} · "
            f"ET {self.ET_empirique:.4g}/{self.ET_theorique:.4g}"
        )


def alpha_corrige(alpha: float, m: int, correction: str | None = "sidak") -> float:
    """Le seuil par test qui tient *alpha* sur une famille de *m* tests.

    Parameters
    ----------
    alpha:
        Le risque voulu sur l'ensemble du tableau.
    m:
        Le nombre de tests de la famille.
    correction:
        ``"sidak"`` (défaut, exacte sous indépendance), ``"bonferroni"``
        (légèrement plus sévère), ou None pour ne rien corriger.

    Returns
    -------
    float
        Le seuil à appliquer à chaque p-valeur.
    """
    if correction is None:
        return alpha
    if correction not in CORRECTIONS:
        raise ValueError(
            f"correction inconnue : {correction!r} ; attendu l'une de {list(CORRECTIONS)} ou None"
        )
    if m <= 1:
        return alpha
    if correction == "bonferroni":
        return alpha / m
    return float(1.0 - (1.0 - alpha) ** (1.0 / m))


def valider(
    echantillon: object,
    loi: LoiDispersion,
    *,
    coefficient: str = "",
    composante: str = "",
    alpha: float = ALPHA_DEFAUT,
    tol_M: float = TOL_M_DEFAUT,
    tol_ET: float = TOL_ET_DEFAUT,
    n_min: int = N_MIN_DEFAUT,
) -> Verdict:
    """Confronte un échantillon à la loi qu'il est censé réaliser.

    Parameters
    ----------
    echantillon:
        Les valeurs tirées, 1-D.
    loi:
        La loi prescrite.
    coefficient, composante:
        Étiquettes reportées dans le verdict ; sans effet sur le calcul.
    alpha:
        Risque du test de Kolmogorov–Smirnov.
    tol_M:
        Décalage de moyenne toléré, en unités de l'écart-type de la loi.
    tol_ET:
        Erreur relative tolérée sur l'écart-type.
    n_min:
        En deçà, l'échantillon est déclaré trop court plutôt que jugé.

    Returns
    -------
    Verdict

    Examples
    --------
    >>> loi = LoiDispersion(6, 0.0, 0.10)
    >>> verdict = valider(loi.tirer(1000, graine=1), loi)   # doctest: +SKIP
    >>> verdict.valide                                       # doctest: +SKIP
    True
    """
    valeurs = np.asarray(echantillon, dtype=float).ravel()
    n = int(valeurs.size)

    M_th = loi.M_theorique
    ET_th = loi.ET_theorique

    if n < n_min:
        return _verdict_court(coefficient, composante, n, valeurs, M_th, ET_th)

    M_emp = float(np.mean(valeurs))
    ET_emp = float(np.std(valeurs))

    bas, haut = loi.support()
    hors_support = int(np.count_nonzero((valeurs < bas - 1e-9) | (valeurs > haut + 1e-9)))

    if loi.est_degeneree:
        return _verdict_degenere(
            coefficient, composante, n, valeurs, M_emp, ET_emp, M_th, ET_th, hors_support
        )

    ecart_M = abs(M_emp - M_th) / ET_th
    ecart_ET = abs(ET_emp - ET_th) / ET_th

    ks_D, ks_p = _kolmogorov(valeurs, loi)

    # Les seuils absorbent le bruit d'échantillonnage : sur un petit effectif,
    # une tolérance pratique fixe rejetterait des tirages corrects.
    seuil_M = max(tol_M, _MARGE_BRUIT / math.sqrt(n))
    seuil_ET = max(tol_ET, _MARGE_BRUIT / math.sqrt(2.0 * n))

    motif = ""
    if hors_support:
        motif = "support"
    elif ecart_M > seuil_M:
        motif = "moyenne"
    elif ecart_ET > seuil_ET:
        motif = "écart-type"
    elif ks_p < alpha:
        motif = "forme"

    return Verdict(
        coefficient=coefficient,
        composante=composante,
        n=n,
        ks_D=ks_D,
        ks_p=ks_p,
        M_empirique=M_emp,
        ET_empirique=ET_emp,
        M_theorique=M_th,
        ET_theorique=ET_th,
        ecart_M=ecart_M,
        ecart_ET=ecart_ET,
        hors_support=hors_support,
        valide=not motif,
        motif=motif,
    )


def _kolmogorov(valeurs: np.ndarray, loi: LoiDispersion) -> tuple[float, float]:
    """Statistique et p-valeur de Kolmogorov–Smirnov contre la loi exacte."""
    echantillon = ot.Sample(valeurs.reshape(-1, 1))
    resultat = ot.FittingTest.Kolmogorov(echantillon, loi.distribution)
    return float(resultat.getStatistic()), float(resultat.getPValue())


def _verdict_court(
    coefficient: str,
    composante: str,
    n: int,
    valeurs: np.ndarray,
    M_th: float,
    ET_th: float,
) -> Verdict:
    """Un échantillon trop court n'est pas rejeté sur le fond, mais pas validé."""
    return Verdict(
        coefficient=coefficient,
        composante=composante,
        n=n,
        ks_D=math.nan,
        ks_p=math.nan,
        M_empirique=float(np.mean(valeurs)) if n else math.nan,
        ET_empirique=float(np.std(valeurs)) if n else math.nan,
        M_theorique=M_th,
        ET_theorique=ET_th,
        ecart_M=math.nan,
        ecart_ET=math.nan,
        hors_support=0,
        valide=False,
        motif="effectif",
    )


def _verdict_degenere(
    coefficient: str,
    composante: str,
    n: int,
    valeurs: np.ndarray,
    M_emp: float,
    ET_emp: float,
    M_th: float,
    ET_th: float,
    hors_support: int,
) -> Verdict:
    """Une loi dégénérée se vérifie à l'égalité, pas par un test de distance.

    Kolmogorov–Smirnov n'est défini que pour des lois continues ; une masse de
    Dirac exige simplement que toutes les valeurs soient la bonne.
    """
    exact = bool(np.allclose(valeurs, M_th, rtol=0.0, atol=1e-12))
    return Verdict(
        coefficient=coefficient,
        composante=composante,
        n=n,
        ks_D=math.nan,
        ks_p=math.nan,
        M_empirique=M_emp,
        ET_empirique=ET_emp,
        M_theorique=M_th,
        ET_theorique=ET_th,
        ecart_M=abs(M_emp - M_th),
        ecart_ET=abs(ET_emp - ET_th),
        hors_support=hors_support,
        valide=exact,
        motif="" if exact else "support",
    )


def valider_lot(
    df: pd.DataFrame,
    lois: JeuDeLois,
    *,
    par: Sequence[str] = (),
    colonnes: Mapping[tuple[str, str], str] | None = None,
    alpha: float = ALPHA_DEFAUT,
    tol_M: float = TOL_M_DEFAUT,
    tol_ET: float = TOL_ET_DEFAUT,
    n_min: int = N_MIN_DEFAUT,
    correction: str | None = "sidak",
) -> pd.DataFrame:
    """Valide toute une sortie de modèle, groupée par point de vol.

    C'est le pilote du cas d'usage 2.2 : mille appels du modèle sur plusieurs
    points de vol donnent un ``DataFrame`` ; celui-ci le regroupe et rend un
    verdict par (point de vol × coefficient × composante).

    Parameters
    ----------
    df:
        La sortie du modèle. Doit porter une colonne par composante — par
        défaut ``"<coefficient>_<composante>"`` — et les colonnes de *par*.
    lois:
        Les lois prescrites.
    par:
        Les colonnes définissant un point de vol (``("Mach", "Altitude_m")``).
        Vide : tout le tableau est validé d'un bloc.
    colonnes:
        Correspondance ``{(coefficient, composante): nom de colonne}`` quand la
        convention de nommage par défaut ne s'applique pas.
    alpha, tol_M, tol_ET, n_min:
        Passés à :func:`valider`. *alpha* porte ici sur **l'ensemble** du
        tableau, pas sur chaque test pris isolément.
    correction:
        Correction de multiplicité : ``"sidak"`` (défaut), ``"bonferroni"``,
        ou None pour appliquer *alpha* test par test. Sans elle, un tableau
        entièrement conforme ressort presque toujours avec quelques cases
        rouges dues au seul hasard (voir la docstring du module).

    Returns
    -------
    pandas.DataFrame
        Une ligne par (point de vol, coefficient, composante), portant les
        colonnes de *par* puis tous les champs de :class:`Verdict`.

    Raises
    ------
    ValueError
        Si une colonne attendue manque ; le message la nomme.
    """
    correspondance = _correspondance_colonnes(lois, colonnes)
    manquantes = sorted({c for c in correspondance.values() if c not in df.columns})
    if manquantes:
        raise ValueError(
            f"colonne(s) absente(s) du tableau : {manquantes} ; il porte {sorted(df.columns)}"
        )

    par = tuple(par)
    absentes = [cle for cle in par if cle not in df.columns]
    if absentes:
        raise ValueError(f"colonne(s) de groupement absente(s) : {absentes}")

    groupes = _grouper(df, par)
    # Le seuil est corrigé du nombre total de tests du tableau : c'est la
    # seule information que `valider` seul ne peut pas avoir.
    n_tests = len(groupes) * len(lois.composantes())
    alpha_test = alpha_corrige(alpha, n_tests, correction)

    lignes: list[dict[str, Any]] = []
    for cles, groupe in groupes:
        for coeff, composante, loi in lois.composantes():
            verdict = valider(
                groupe[correspondance[(coeff, composante)]].to_numpy(),
                loi,
                coefficient=coeff,
                composante=composante,
                alpha=alpha_test,
                tol_M=tol_M,
                tol_ET=tol_ET,
                n_min=n_min,
            )
            lignes.append({**cles, **verdict.vers_dict()})

    return pd.DataFrame(lignes)


def _correspondance_colonnes(
    lois: JeuDeLois, colonnes: Mapping[tuple[str, str], str] | None
) -> dict[tuple[str, str], str]:
    """Associe chaque (coefficient, composante) à sa colonne."""
    defaut = {
        (coeff, composante): f"{coeff}_{composante}" for coeff in lois for composante in COMPOSANTES
    }
    if colonnes:
        defaut.update(colonnes)
    return defaut


def _grouper(df: pd.DataFrame, par: tuple[str, ...]) -> list[tuple[dict[str, Any], pd.DataFrame]]:
    """Groupe *df* par *par*, en rendant les clés sous forme de dictionnaire."""
    if not par:
        return [({}, df)]

    groupes: list[tuple[dict[str, Any], pd.DataFrame]] = []
    for valeurs, groupe in df.groupby(list(par), sort=False):
        if not isinstance(valeurs, tuple):
            valeurs = (valeurs,)
        groupes.append((dict(zip(par, valeurs)), groupe))
    return groupes
