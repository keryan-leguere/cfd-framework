"""Apparier les lignes de la référence et du test.

Deux modes :

- **sur les entrées** (défaut) : une ligne de test correspond à la ligne de
  référence qui a les mêmes valeurs d'entrée. L'ordre peut différer (un
  workflow parallèle termine ses cas dans le désordre), des cas peuvent
  manquer (plantage) ou être en trop. Si une combinaison d'entrées revient
  plusieurs fois, ses occurrences sont appariées dans leur ordre d'apparition,
  et le rapport le signale : c'est le signe qu'une entrée n'a pas été déclarée ;
- **par position** : la i-ème ligne contre la i-ème ligne. Les entrées sont
  alors *vérifiées* : une paire dont les entrées diffèrent n'est pas comparée
  (ses sorties ne répondent pas à la même question), elle est déclarée
  « entrées divergentes ».

Les entrées numériques sont comparées en double précision (un entier ``2``
apparie un flottant ``2.0``), ``-0.0`` égale ``0.0`` ; ``chiffres_cle``
arrondit d'abord à ce nombre de chiffres significatifs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from cfd_validation.data.specification import ALIGNEMENT_ENTREES, ALIGNEMENT_POSITION

__all__ = ["Appariement", "apparier", "cles_entrees"]

_RANG = "__rang__"
_POS_REF = "__ligne_ref__"
_POS_TEST = "__ligne_test__"


@dataclass(frozen=True)
class Appariement:
    """Positions (0, 1, … dans chaque table) des lignes appariées, absentes et en trop."""

    #: Positions dans la référence des paires, triées.
    ref: NDArray[np.int64]
    #: Positions dans le test correspondantes.
    test: NDArray[np.int64]
    #: Paires dont les entrées diffèrent (mode position seulement).
    divergentes: NDArray[np.bool_]
    #: Lignes de référence sans correspondant.
    absentes: NDArray[np.int64]
    #: Lignes de test sans correspondant.
    en_trop: NDArray[np.int64]
    #: Lignes de référence dont la combinaison d'entrées a déjà été vue.
    n_cles_dupliquees: int
    #: Vrai si chaque ligne de test est à la même position que sa référence.
    meme_ordre: bool
    #: Entrées converties en texte pour être appariées (types incompatibles des deux côtés).
    entrees_en_texte: tuple[str, ...]


def _arrondir(x: NDArray[np.float64], chiffres: int) -> NDArray[np.float64]:
    with np.errstate(divide="ignore", invalid="ignore"):
        ordre = np.floor(np.log10(np.abs(x)))
    ordre = np.where(np.isfinite(ordre), ordre, 0.0)
    echelle = 10.0 ** (chiffres - 1 - ordre)
    with np.errstate(invalid="ignore", over="ignore"):
        arrondi = np.round(x * echelle) / echelle
    return np.where(np.isfinite(arrondi), arrondi, x)


def cles_entrees(
    ref: pd.DataFrame, test: pd.DataFrame, entrees: Sequence[str], chiffres_cle: int | None
) -> tuple[pd.DataFrame, pd.DataFrame, tuple[str, ...]]:
    """Les colonnes d'entrée des deux tables, normalisées pour être comparées terme à terme."""
    cle_ref = pd.DataFrame(index=pd.RangeIndex(len(ref)))
    cle_test = pd.DataFrame(index=pd.RangeIndex(len(test)))
    en_texte = []
    for nom in entrees:
        a, b = ref[nom], test[nom]
        num_a = pd.api.types.is_numeric_dtype(a) and not pd.api.types.is_bool_dtype(a)
        num_b = pd.api.types.is_numeric_dtype(b) and not pd.api.types.is_bool_dtype(b)
        if num_a and num_b:
            va = a.to_numpy(dtype=np.float64, na_value=np.nan) + 0.0  # -0.0 → 0.0
            vb = b.to_numpy(dtype=np.float64, na_value=np.nan) + 0.0
            if chiffres_cle is not None:
                va, vb = _arrondir(va, chiffres_cle), _arrondir(vb, chiffres_cle)
            cle_ref[nom], cle_test[nom] = va, vb
        else:
            if num_a != num_b:
                en_texte.append(nom)
            cle_ref[nom] = a.astype(str).to_numpy()
            cle_test[nom] = b.astype(str).to_numpy()
    return cle_ref, cle_test, tuple(en_texte)


def _egales(a: pd.DataFrame, b: pd.DataFrame) -> NDArray[np.bool_]:
    """Ligne à ligne : toutes les entrées égales (deux NaN sont égaux)."""
    egal = np.ones(len(a), dtype=bool)
    for nom in a.columns:
        x, y = a[nom].to_numpy(), b[nom].to_numpy()
        if x.dtype.kind == "f":
            egal &= (x == y) | (np.isnan(x) & np.isnan(y))
        else:
            egal &= x == y
    return egal


def apparier(
    ref: pd.DataFrame,
    test: pd.DataFrame,
    entrees: Sequence[str],
    *,
    alignement: str = ALIGNEMENT_ENTREES,
    chiffres_cle: int | None = None,
) -> Appariement:
    """Apparie les lignes de ``ref`` et ``test`` (voir le module)."""
    cle_ref, cle_test, en_texte = cles_entrees(ref, test, entrees, chiffres_cle)
    cols = list(entrees)
    rang_ref = cle_ref.groupby(cols, dropna=False, sort=False).cumcount().to_numpy()
    n_dup = int((rang_ref > 0).sum())

    if alignement == ALIGNEMENT_POSITION:
        n = min(len(ref), len(test))
        pos = np.arange(n, dtype=np.int64)
        divergentes = ~_egales(cle_ref.iloc[:n], cle_test.iloc[:n])
        return Appariement(
            ref=pos,
            test=pos.copy(),
            divergentes=divergentes,
            absentes=np.arange(n, len(ref), dtype=np.int64),
            en_trop=np.arange(n, len(test), dtype=np.int64),
            n_cles_dupliquees=n_dup,
            meme_ordre=True,
            entrees_en_texte=en_texte,
        )
    if alignement != ALIGNEMENT_ENTREES:
        raise ValueError(f"alignement inconnu : {alignement!r}")

    gauche = cle_ref.assign(**{_RANG: rang_ref, _POS_REF: np.arange(len(ref))})
    droite = cle_test.assign(
        **{
            _RANG: cle_test.groupby(cols, dropna=False, sort=False).cumcount().to_numpy(),
            _POS_TEST: np.arange(len(test)),
        }
    )
    fusion = gauche.merge(droite, on=[*cols, _RANG], how="outer", indicator=True, sort=False)
    paires = fusion[fusion["_merge"] == "both"].sort_values(_POS_REF)
    p_ref = paires[_POS_REF].to_numpy(dtype=np.int64)
    p_test = paires[_POS_TEST].to_numpy(dtype=np.int64)
    absentes = np.sort(fusion.loc[fusion["_merge"] == "left_only", _POS_REF].to_numpy(dtype=np.int64))
    en_trop = np.sort(fusion.loc[fusion["_merge"] == "right_only", _POS_TEST].to_numpy(dtype=np.int64))
    return Appariement(
        ref=p_ref,
        test=p_test,
        divergentes=np.zeros(p_ref.size, dtype=bool),
        absentes=absentes,
        en_trop=en_trop,
        n_cles_dupliquees=n_dup,
        meme_ordre=bool(np.array_equal(p_ref, p_test)),
        entrees_en_texte=en_texte,
    )
