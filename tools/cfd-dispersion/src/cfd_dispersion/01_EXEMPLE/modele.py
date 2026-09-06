"""Un modèle jouet, à la place du vôtre — et le contrat qu'il honore.

Le vrai modèle est une fonction Python qui reçoit les points de vol, la table
de lois, les coefficients et un tirage, et rend un ``DataFrame``. Celui-ci en
a la forme exacte, en beaucoup plus simple : il applique la convention aux
coefficients nominaux et rend une ligne par (point de vol × tirage).

Le contrat de sortie
--------------------
C'est le seul point d'accroche du paquet, et il tient en quatre noms de
colonnes :

======================= ==================================================
``<coefficient>_Biais``  le biais tiré, tel qu'il a servi
``<coefficient>_FE``     le facteur d'échelle tiré
``<coefficient>``        le coefficient dispersé obtenu
``Mach``, ``Altitude_m`` les clés de point de vol, ce que ``par=`` nommera
======================= ==================================================

Les deux premières sont ce que ``valider_lot`` relit pour dire si le tirage
suit sa loi ; la troisième alimente le panneau de reconstruction. Un modèle qui
nomme ses colonnes autrement n'a pas à être renommé : voir l'argument
``colonnes=`` et ``00_DOC/05_BRANCHER_SON_MODELE.md`` §5.4.

Le défaut volontaire
--------------------
Un défaut est glissé exprès : au point de vol ``M = 0.85``, le facteur
d'échelle de ``Cm_alpha`` est tiré avec une demi-étendue **doublée** — la
confusion classique entre demi-étendue et écart-type. Rien ne le montre à
l'œil sur une courbe ; c'est exactement ce que la validation doit rattraper.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd

from cfd_dispersion import (
    JeuDeLois,
    Tirage,
    charger_lois,
    convention,
    plan_croise,
    tirer,
    tirer_lot,
    tirer_tableau,
)

#: Les points de vol de l'étude.
POINTS_DE_VOL: tuple[dict[str, float], ...] = (
    {"Mach": 0.70, "Altitude_m": 5000.0},
    {"Mach": 0.80, "Altitude_m": 8000.0},
    {"Mach": 0.85, "Altitude_m": 10000.0},
    {"Mach": 0.90, "Altitude_m": 12000.0},
)

#: Le point de vol où le tirage est volontairement faussé.
PDV_FAUTIF = 0.85

#: Le coefficient et la composante faussés.
COMPOSANTE_FAUTIVE = ("Cm_alpha", "FE")


def coefficients_nominaux(mach: float) -> dict[str, float]:
    """Les coefficients nominaux à un point de vol — une dépendance en Mach."""
    return {
        "CN": 0.85 + 0.6 * (mach - 0.7),
        "CA": 0.032 + 0.05 * (mach - 0.7) ** 2,
        "Cm_alpha": -2.5 - 1.2 * (mach - 0.7),
    }


def _lois_du_point(lois: JeuDeLois, mach: float, fausser: bool) -> JeuDeLois:
    """Les lois effectivement tirées à un point de vol."""
    if not fausser or mach != PDV_FAUTIF:
        return lois

    coefficient, composante = COMPOSANTE_FAUTIVE
    table: dict[str, dict[str, Any]] = {}
    for nom, loi in lois.items():
        table[nom] = {
            "Biais_Type": loi.biais.type_loi,
            "Biais_M": loi.biais.M,
            "Biais_ET": loi.biais.ET,
            "FE_Type": loi.fe.type_loi,
            "FE_M": loi.fe.M,
            "FE_ET": loi.fe.ET,
        }
    table[coefficient][f"{composante}_ET"] *= 2.0
    return charger_lois(table)


def appeler_modele(
    lois: JeuDeLois,
    *,
    n: int = 800,
    points_de_vol: Sequence[Mapping[str, float]] = POINTS_DE_VOL,
    convention_: str = "lineaire",
    graine: int = 2026,
    fausser: bool = True,
) -> pd.DataFrame:
    """Appelle le modèle *n* fois par point de vol.

    Returns
    -------
    pandas.DataFrame
        Une ligne par (point de vol × tirage). Porte les colonnes de point de
        vol, les composantes tirées (``"<coeff>_Biais"``, ``"<coeff>_FE"``) et
        les coefficients dispersés (``"<coeff>"``).
    """
    relation = convention(convention_)
    morceaux = []

    for indice, point in enumerate(points_de_vol):
        mach = float(point["Mach"])
        lot = tirer_tableau(_lois_du_point(lois, mach, fausser), n, graine=graine + indice)

        nominaux = coefficients_nominaux(mach)
        for coefficient, valeur in nominaux.items():
            lot[coefficient] = relation(
                valeur, lot[f"{coefficient}_Biais"], lot[f"{coefficient}_FE"]
            )
        for cle, valeur in point.items():
            lot[cle] = valeur
        lot["tirage"] = np.arange(n)
        morceaux.append(lot)

    return pd.concat(morceaux, ignore_index=True)


def appeler_modele_polaire(
    lois: JeuDeLois,
    alpha: np.ndarray,
    *,
    n: int = 300,
    mach: float = 0.80,
    convention_: str = "lineaire",
    graine: int = 7,
    tirages: Sequence[Tirage] | None = None,
    riche: bool = False,
) -> pd.DataFrame:
    """Appelle le modèle *n* fois sur un balayage en incidence.

    C'est la forme dont part le cas d'usage 2.3 : un tableau à plat, une ligne
    par (tirage × point du balayage), à regrouper en une courbe par tirage.

    *tirages* impose la liste des tirages au lieu d'en tirer *n*. C'est ainsi
    qu'on obtient la **polaire de référence** : un seul tirage, neutre.

        appeler_modele_polaire(lois, alpha, tirages=[tirage_neutre(lois)])

    *riche* emploie les formes de :func:`_forme_riche` — décrochage, polaire de
    traînée, cassure de Cm_alpha — au lieu des paraboles douces. C'est le jeu
    de données sur lequel on juge un rendu : une enveloppe qui garde la même
    largeur d'un bout à l'autre ne met rien à l'épreuve.
    """
    relation = convention(convention_)
    nominaux = coefficients_nominaux(mach)

    lignes = []
    # `tirer_lot` rend la liste des tirages : un modèle boucle dessus et reçoit
    # à chaque tour le dictionnaire {coeff: {"Biais": …, "FE": …}} qu'il attend.
    lot = list(tirages) if tirages is not None else tirer_lot(lois, n, graine=graine)
    for tirage in lot:
        colonnes: dict[str, Any] = {"alpha": alpha}
        for coefficient, valeur in nominaux.items():
            # Le coefficient nominal varie le long du balayage ; le tirage,
            # lui, est partagé sur toute la courbe — le cas corrélé.
            forme = _forme_riche if riche else _forme
            courbe = valeur * forme(coefficient, alpha)
            biais = tirage[coefficient]["Biais"]
            fe = tirage[coefficient]["FE"]
            colonnes[coefficient] = relation(courbe, biais, fe)
            colonnes[f"{coefficient}_Biais"] = biais
            colonnes[f"{coefficient}_FE"] = fe
        colonnes["tirage"] = 0 if tirage.numero is None else tirage.numero
        colonnes["Mach"] = mach
        lignes.append(pd.DataFrame(colonnes))

    return pd.concat(lignes, ignore_index=True)


def _forme(coefficient: str, alpha: np.ndarray) -> np.ndarray:
    """La dépendance en incidence de chaque coefficient, en unités du nominal."""
    if coefficient == "CN":
        return 0.11 * alpha + 0.0045 * alpha**2
    if coefficient == "CA":
        return 1.0 + 0.012 * alpha**2
    return 1.0 + 0.02 * alpha


def _forme_riche(coefficient: str, alpha: np.ndarray) -> np.ndarray:
    """La même chose, mais avec ce qui rend une polaire intéressante à tracer.

    Trois accidents, et ils ne sont pas décoratifs : ils font varier la largeur
    de l'enveloppe le long du balayage, ce qu'une polaire droite ne montre
    jamais.

    * **CN** part linéaire puis **s'aplatit** — un décrochage. La dispersion
      relative, elle, ne s'aplatit pas : l'enveloppe s'ouvre là où la pente
      tombe, et c'est exactement ce qu'un dossier doit voir.
    * **CA** suit une **polaire de traînée** : un creux vers zéro, puis une
      croissance en CN². Il change d'un facteur trois sur le balayage.
    * **Cm_alpha** **casse** après le décrochage : la marge statique s'effondre.

    Le balayage va aussi dans les incidences négatives, où CN passe par zéro —
    de quoi vérifier que rien ne divise par lui.
    """
    if coefficient == "CN":
        # a·tanh(b·α) : pente 0.11 à l'origine (a·b), saturation vers 1.45.
        return 1.45 * np.tanh(0.0759 * alpha)
    if coefficient == "CA":
        portance = 1.45 * np.tanh(0.0759 * alpha)
        return 1.0 + 0.9 * portance**2
    # Marge statique constante, puis effondrement au-delà de 14 degrés.
    return 1.0 + 0.02 * alpha - 0.06 * np.maximum(alpha - 14.0, 0.0)


#: Le Mach de divergence : au-delà, l'onde de choc s'installe et tout bouge.
MACH_DIVERGENCE = 0.78


def _forme_transsonique(coefficient: str, mach: np.ndarray) -> np.ndarray:
    """La dépendance en **Mach**, autour de la divergence de traînée.

    Un balayage en incidence donne des courbes lisses ; un balayage en Mach en
    donne une qui **casse**, et c'est un tout autre exercice pour une enveloppe.

    * **CA** double en dix centièmes de Mach : c'est la divergence de traînée.
      Une dispersion de 3 % y devient trois fois plus large en valeur absolue
      sans que la loi ait changé — le genre de chose qu'un dossier doit voir.
    * **CN** suit Prandtl–Glauert, puis **perd** au passage du choc.
    * **Cm_alpha** bascule : c'est le *tuck* transsonique.
    """
    montee = np.maximum(mach - MACH_DIVERGENCE, 0.0)
    if coefficient == "CA":
        return np.asarray(1.0 + 0.03 * mach + 22.0 * montee**2, dtype=float)
    if coefficient == "CN":
        # Prandtl–Glauert, borné avant la singularité, puis perte de portance.
        compressibilite = 1.0 / np.sqrt(np.maximum(1.0 - np.minimum(mach, 0.94) ** 2, 0.12))
        return np.asarray(0.55 * compressibilite - 3.0 * montee**2, dtype=float)
    return np.asarray(1.0 + 0.10 * mach - 6.0 * montee**2, dtype=float)


def appeler_modele_transsonique(
    lois: JeuDeLois,
    mach: np.ndarray,
    *,
    n: int = 100,
    alpha: float = 6.0,
    convention_: str = "lineaire",
    graine: int = 11,
    tirages: Sequence[Tirage] | None = None,
) -> pd.DataFrame:
    """Le même modèle, balayé en **Mach** à incidence fixée.

    Même contrat de sortie que :func:`appeler_modele_polaire` — une ligne par
    (tirage × point du balayage) — mais la colonne de balayage est ``Mach`` et
    les formes sont celles de :func:`_forme_transsonique`.
    """
    relation = convention(convention_)
    lignes = []
    lot = list(tirages) if tirages is not None else tirer_lot(lois, n, graine=graine)
    for tirage in lot:
        colonnes: dict[str, Any] = {"Mach": mach}
        for coefficient in ("CN", "CA", "Cm_alpha"):
            # Le nominal dépend du Mach par la forme, et de l'incidence par le
            # niveau : deux dépendances, une seule courbe.
            niveau = coefficients_nominaux(0.70)[coefficient]
            courbe = niveau * _forme_transsonique(coefficient, mach) * (1.0 + 0.02 * alpha)
            biais = tirage[coefficient]["Biais"]
            fe = tirage[coefficient]["FE"]
            colonnes[coefficient] = relation(courbe, biais, fe)
            colonnes[f"{coefficient}_Biais"] = biais
            colonnes[f"{coefficient}_FE"] = fe
        colonnes["alpha"] = alpha
        colonnes["tirage"] = 0 if tirage.numero is None else tirage.numero
        lignes.append(pd.DataFrame(colonnes))

    return pd.concat(lignes, ignore_index=True)


def polaire_nominale(
    alpha: np.ndarray, *, mach: float = 0.80, riche: bool = False
) -> dict[str, np.ndarray]:
    """Les polaires non dispersées, pour servir de référence sur les figures."""
    nominaux = coefficients_nominaux(mach)
    return {
        coefficient: valeur * _forme(coefficient, alpha) for coefficient, valeur in nominaux.items()
    }


# ---------------------------------------------------------------------------
# La forme d'un vrai modèle d'établissement : listes croisées, tableau large
# ---------------------------------------------------------------------------


def initialiser_bibliotheque() -> dict[str, Any]:
    """Là où s'initialise la bibliothèque Fortran, une fois pour l'étude.

    Ici, un simple dictionnaire de métadonnées. Dans le vrai modèle, c'est
    l'appel d'initialisation du solveur : il coûte cher, il se fait une fois,
    et ce qu'il rend (version, options, table de référence) a sa place dans le
    tableau de sortie — c'est ce qui rend un résultat relisable dans six mois.
    """
    return {"version_solveur": "FORTRAN v3.1", "table_aero": "REF_2026A", "options": "std"}


def appeler_modele_croise(
    lois: JeuDeLois,
    *,
    L_MACH: Sequence[float],
    L_ALTITUDE: Sequence[float],
    L_ALPHA: Sequence[float],
    n: int = 200,
    convention_: str = "lineaire",
    graine: int = 4242,
    fausser: bool = True,
) -> pd.DataFrame:
    """Croise les axes, tire, appelle le solveur, et rend UN tableau large.

    C'est la forme réelle d'un modèle d'établissement :

    * il reçoit des **listes d'axes** et les croise lui-même ;
    * il initialise sa bibliothèque une fois, puis boucle ;
    * il rend **une ligne par (tirage × point croisé)**, portant le point de
      vol, les coefficients, ses métadonnées, et les deux dictionnaires —
      la table de lois employée et le tirage appliqué.

    Le tirage est fait ici, une fois par appel du modèle, et **partagé par
    tous les points croisés** : c'est le cas physique — une erreur de recalage
    est la même sur toute la polaire. C'est aussi ce qui impose de dédoublonner
    avant de valider (``unique_par=("tirage",)``).

    Returns
    -------
    pandas.DataFrame
        Colonnes : ``Mach``, ``Altitude_m``, ``alpha``, un par coefficient,
        les métadonnées du solveur, ``DICT_LAW_DISPERSION`` et ``DICT_TIRAGE``.
    """
    relation = convention(convention_)
    contexte = initialiser_bibliotheque()
    table = _table_des_lois(lois)
    points = plan_croise(Mach=list(L_MACH), Altitude_m=list(L_ALTITUDE), alpha=list(L_ALPHA))

    lignes: list[dict[str, Any]] = []
    for indice in range(n):
        # Un tirage par appel du modèle, avec sa propre graine : une graine
        # constante donnerait n fois le même tirage, ce qui ne se voit qu'à la
        # validation.
        lignes.extend(
            _lignes_d_un_appel(lois, table, contexte, relation, points, indice, graine, fausser)
        )
    return pd.DataFrame(lignes)


def _lignes_d_un_appel(
    lois: JeuDeLois,
    table: dict[str, dict[str, Any]],
    contexte: Mapping[str, Any],
    relation: Any,
    points: Sequence[Mapping[str, float]],
    indice: int,
    graine: int,
    fausser: bool,
) -> list[dict[str, Any]]:
    """Les lignes rendues par un appel du modèle, sous un tirage donné."""
    lignes = []
    for point in points:
        mach = float(point["Mach"])
        # Le défaut volontaire se joue au tirage, point de vol par point de vol.
        tirage = tirer(_lois_du_point(lois, mach, fausser), graine=graine + indice)
        nominaux = coefficients_nominaux(mach)
        alpha = float(point["alpha"])

        ligne: dict[str, Any] = {**point, **contexte}
        for coefficient, valeur in nominaux.items():
            courbe = valeur * _forme(coefficient, np.array([alpha]))[0]
            ligne[coefficient] = float(
                relation(courbe, tirage[coefficient]["Biais"], tirage[coefficient]["FE"])
            )
        ligne["temps_calcul_s"] = 0.017
        ligne["convergence"] = True
        ligne["DICT_LAW_DISPERSION"] = table
        ligne["DICT_TIRAGE"] = dict(tirage)
        lignes.append(ligne)
    return lignes


def _table_des_lois(lois: JeuDeLois) -> dict[str, dict[str, Any]]:
    """Le ``DICT_LAW_DISPERSION`` tel qu'il voyage dans le tableau."""
    return {
        nom: {
            "Biais_Type": loi.biais.type_loi,
            "Biais_M": loi.biais.M,
            "Biais_ET": loi.biais.ET,
            "FE_Type": loi.fe.type_loi,
            "FE_M": loi.fe.M,
            "FE_ET": loi.fe.ET,
        }
        for nom, loi in lois.items()
    }
