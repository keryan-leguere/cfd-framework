"""Écarts entre une valeur de référence et une valeur testée, point par point.

Quatre mesures, parce qu'aucune ne suffit seule :

- ``ecart = t − r`` (signé) : son **biais** (moyenne) trahit un décalage
  systématique (une constante, une convention), là où le bruit d'arrondi est
  centré ;
- ``ecart_rel = |t − r| / |r|`` : lisible, mais infini dès que ``r = 0`` ;
- ``ulp`` : nombre de flottants représentables entre ``r`` et ``t``. C'est
  l'unité naturelle d'un test d'intégration : 1 à 10 ULP, c'est l'arrondi d'un
  autre compilateur ; 10⁶ ULP, c'est autre chose ;
- ``marge = (t − r) / (atol + rtol·|r|)`` : l'écart **en unités de
  tolérance**, signé. ``|marge| ≤ 1`` est le critère d'acceptation ; c'est la
  grandeur qu'on trace, puisqu'elle met toutes les sorties sur une même échelle.
  Elle vaut ``+inf`` pour un côté non fini : aucun seuil ne l'admet.

Deux NaN, ou deux infinis de même signe, sont **identiques** : un code qui
renvoyait NaN et le renvoie encore n'a pas changé de comportement. Un NaN
contre un nombre est ``NON_FINI``, jamais « dans la tolérance ».
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cfd_validation.core.statuts import ECART, IDENTIQUE, NON_FINI, TOLERE
from cfd_validation.core.tolerance import Tolerance

__all__ = ["Ecarts", "comparer_exact", "comparer_numerique", "distance_ulp"]

_SIGNE = np.uint64(0x8000_0000_0000_0000)
_MAGNITUDE = np.uint64(0x7FFF_FFFF_FFFF_FFFF)


@dataclass(frozen=True)
class Ecarts:
    """Les mesures d'écart d'une sortie, alignées sur les lignes comparées.

    Les mesures numériques valent NaN là où elles n'ont pas de sens (côté non
    fini, sortie non numérique).
    """

    statut: NDArray[np.int8]
    ecart: NDArray[np.float64]
    ecart_rel: NDArray[np.float64]
    ulp: NDArray[np.float64]
    marge: NDArray[np.float64]


def _cle_ordonnee(x: NDArray[np.float64]) -> NDArray[np.uint64]:
    """Entier non signé croissant avec le flottant : ``2⁶³ ± magnitude IEEE 754``.

    Deux flottants voisins ont des clés consécutives, et ``−0`` et ``+0`` la
    même — sans quoi traverser zéro compterait un ULP de trop.
    """
    u = np.ascontiguousarray(x, dtype=np.float64).view(np.uint64)
    magnitude = u & _MAGNITUDE
    return np.where(u & _SIGNE, _SIGNE - magnitude, _SIGNE + magnitude)


def distance_ulp(a: NDArray[np.float64], b: NDArray[np.float64]) -> NDArray[np.float64]:
    """Nombre de flottants double précision séparant ``a`` de ``b`` (NaN si l'un est NaN).

    ``+0`` et ``−0`` sont à distance nulle (ils sont égaux).
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ka, kb = _cle_ordonnee(a), _cle_ordonnee(b)
    d = np.where(ka >= kb, ka - kb, kb - ka).astype(np.float64)
    d[a == b] = 0.0
    d[np.isnan(a) | np.isnan(b)] = np.nan
    return d


def comparer_numerique(
    reference: NDArray[Any], test: NDArray[Any], tolerance: Tolerance
) -> Ecarts:
    """Compare deux colonnes numériques de même longueur selon ``tolerance``."""
    r = np.asarray(reference, dtype=np.float64)
    t = np.asarray(test, dtype=np.float64)
    if r.shape != t.shape:
        raise ValueError(f"longueurs différentes : {r.shape} contre {t.shape}")

    egal = (r == t) | (np.isnan(r) & np.isnan(t))
    fini = np.isfinite(r) & np.isfinite(t)
    seuil = tolerance.seuil(np.where(fini, r, 0.0))

    with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        ecart = np.where(fini, t - r, np.nan)
        ecart_abs = np.abs(ecart)
        ecart_rel = np.where(fini, ecart_abs / np.abs(r), np.nan)
        marge = np.where(fini, ecart / seuil, np.nan)
    # 0/0 : valeurs égales sur une référence nulle.
    ecart[egal] = 0.0
    ecart_rel[egal] = 0.0
    marge[egal] = 0.0

    statut = np.full(r.shape, ECART, dtype=np.int8)
    statut[fini & (ecart_abs <= seuil)] = TOLERE
    statut[~egal & ~fini] = NON_FINI
    statut[egal] = IDENTIQUE
    # Un NaN contre un nombre est infiniment hors tolérance : aucun seuil ne l'admet.
    marge[statut == NON_FINI] = np.inf

    return Ecarts(
        statut=statut,
        ecart=ecart,
        ecart_rel=ecart_rel,
        ulp=distance_ulp(r, t),
        marge=marge,
    )


def _manquant(x: Any) -> bool:
    try:
        return bool(x != x)  # NaN, pd.NA renvoie NA → TypeError géré plus bas
    except TypeError:
        return True


def comparer_exact(reference: NDArray[Any], test: NDArray[Any]) -> Ecarts:
    """Compare deux colonnes non numériques (texte, booléens) : égalité stricte.

    Deux manquants sont identiques ; un manquant contre une valeur est un écart.
    """
    r = np.asarray(reference, dtype=object)
    t = np.asarray(test, dtype=object)
    if r.shape != t.shape:
        raise ValueError(f"longueurs différentes : {r.shape} contre {t.shape}")
    statut = np.empty(r.shape, dtype=np.int8)
    for i, (a, b) in enumerate(zip(r, t)):
        ma, mb = _manquant(a), _manquant(b)
        if ma or mb:
            statut[i] = IDENTIQUE if (ma and mb) else ECART
        else:
            statut[i] = IDENTIQUE if a == b else ECART
    vide = np.full(r.shape, np.nan)
    return Ecarts(statut=statut, ecart=vide, ecart_rel=vide.copy(), ulp=vide.copy(), marge=vide.copy())
