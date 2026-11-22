"""Des colonnes d'une table aux entrées du modèle : le point qu'on injecte.

Partagé par les tests de lecture et de bornes de table. Pour chaque point (une
ligne de ``axes_df``, une colonne par axe de la table), dans cet ordre :

1. les ``defauts`` — leurs clés sont la liste des entrées du modèle ;
2. les ``fixes`` de la table ;
3. les colonnes de la table : directement quand une colonne porte le nom d'une
   entrée, sinon par ``vers_entrees`` (la relation inverse de celle du code).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from cfd_validation.data.tables import ErreurTable, TableReference

__all__ = ["Appel", "appeler", "piloter", "verifier_defauts"]


def _colonne(valeurs: Any, n: int, quoi: str) -> np.ndarray:
    a = np.asarray(valeurs)
    if a.ndim == 0:
        return np.full(n, a.item())
    a = a.ravel()
    if a.size != n:
        raise ErreurTable(f"{quoi} : {a.size} valeurs pour {n} points")
    return a


def verifier_defauts(table: TableReference, defauts: Mapping[str, Any]) -> None:
    """Colonnes sans entrée ni inversion, entrées fixées inconnues : refusées et nommées."""
    non_entrees = [a for a in table.noms_axes if a not in defauts]
    if non_entrees and table.vers_entrees is None:
        raise ErreurTable(
            f"table {table.nom} : {', '.join(non_entrees)} n'est pas une entrée du modèle "
            f"({', '.join(defauts)}) — déclarer vers_entrees pour reconstruire les entrées"
        )
    inconnues = sorted(set(table.fixes) - set(defauts))
    if inconnues:
        raise ErreurTable(f"table {table.nom} : fixes inconnues du vecteur de défauts : {', '.join(inconnues)}")


def piloter(
    table: TableReference, defauts: Mapping[str, Any], axes_df: pd.DataFrame
) -> tuple[dict[str, np.ndarray], tuple[str, ...]]:
    """``({entrée: valeurs}, entrées pilotées)`` pour les points de ``axes_df``.

    Seules les entrées pilotées par la table figurent dans le dictionnaire ; les
    autres prennent leur valeur fixée ou par défaut.
    """
    verifier_defauts(table, defauts)
    n = len(axes_df)
    pilote: dict[str, np.ndarray] = {a: axes_df[a].to_numpy() for a in table.noms_axes if a in defauts}
    if table.vers_entrees is not None:
        rendu = table.vers_entrees(axes_df.copy())
        if not isinstance(rendu, (Mapping, pd.DataFrame)):
            raise ErreurTable(f"table {table.nom} : vers_entrees doit rendre un dict {{entrée: valeurs}}")
        cles = list(rendu.keys())
        hors = sorted(str(k) for k in cles if k not in defauts)
        if hors:
            raise ErreurTable(
                f"table {table.nom} : vers_entrees rend {', '.join(hors)}, pas des entrées du modèle "
                f"({', '.join(defauts)})"
            )
        for k in cles:
            pilote[str(k)] = _colonne(rendu[k], n, f"table {table.nom}, vers_entrees[{k}]")
    pilotees = tuple(k for k in defauts if k in pilote)
    conflit = sorted(set(pilotees) & set(table.fixes))
    if conflit:
        raise ErreurTable(f"table {table.nom} : {', '.join(conflit)} à la fois fixée et pilotée par la table")
    return pilote, pilotees



@dataclass(frozen=True)
class Appel:
    """Un appel de l'évaluateur pour une table : ce qu'on a injecté, ce que la sonde rend."""

    entrees: pd.DataFrame
    code: np.ndarray
    pilotees: tuple[str, ...]


def appeler(
    table: TableReference,
    evaluer: Callable[[pd.DataFrame], pd.DataFrame],
    defauts: Mapping[str, Any],
    axes_df: pd.DataFrame,
) -> Appel:
    """Injecte les points de ``axes_df`` (une colonne par axe), un seul appel, et lit la sonde."""
    pilote, pilotees = piloter(table, defauts, axes_df)
    base = {**defauts, **table.fixes}
    n = len(axes_df)
    entrees = pd.DataFrame({k: (pilote[k] if k in pilote else np.full(n, base[k])) for k in defauts})
    sortie = evaluer(entrees.copy())
    if not isinstance(sortie, pd.DataFrame):
        raise ErreurTable(f"table {table.nom} : l'évaluateur doit rendre un DataFrame, reçu {type(sortie).__name__}")
    if len(sortie) != n:
        raise ErreurTable(f"table {table.nom} : l'évaluateur rend {len(sortie)} lignes pour {n} points")
    if table.sonde not in sortie.columns:
        colonnes = ", ".join(map(str, list(sortie.columns)[:30]))
        raise ErreurTable(f"table {table.nom} : sonde « {table.sonde} » absente de la sortie de l'évaluateur ({colonnes})")
    code = pd.to_numeric(sortie[table.sonde], errors="coerce").to_numpy(dtype=np.float64)
    return Appel(entrees=entrees, code=code, pilotees=pilotees)
