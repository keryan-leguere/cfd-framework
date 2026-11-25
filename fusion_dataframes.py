"""Fusion de plusieurs DataFrames sur une grille de temps commune.

Chaque DataFrame porte une colonne ``t`` et ses propres colonnes (``colA1``,
``colB1`` pour le premier, ``colA2``, ``colB2`` pour le second...). La sortie
est un seul DataFrame dont la grille ``t`` est l'union de tous les ``t`` ; chaque
colonne y est interpolée linéairement à partir de son DataFrame d'origine.

Exemple : df1 a ``t=2, m=10`` et ``t=4, m=20`` ; df2 a un point à ``t=3`` ;
la sortie contient ``t=3, m=15``.

En dehors de l'intervalle de temps couvert par un DataFrame, ses colonnes valent
NaN : on interpole, on n'extrapole pas.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd


def fusionner_sur_t(dfs: Sequence[pd.DataFrame], col_t: str = "t") -> pd.DataFrame:
    """Rassemble les colonnes de ``dfs`` sur la grille union de leurs ``col_t``.

    Lève ``ValueError`` si un DataFrame n'a pas de colonne ``col_t``, si deux
    DataFrames partagent un nom de colonne, si une colonne n'est pas numérique
    ou si un même ``t`` apparaît deux fois dans un DataFrame.
    """
    if not dfs:
        raise ValueError("La liste de DataFrames est vide.")

    vues = set()
    for i, df in enumerate(dfs):
        if col_t not in df.columns:
            raise ValueError(f"DataFrame n°{i} : pas de colonne '{col_t}'.")
        if df[col_t].duplicated().any():
            doublons = df.loc[df[col_t].duplicated(), col_t].unique()
            raise ValueError(f"DataFrame n°{i} : '{col_t}' en double : {list(doublons)}.")
        for col in df.columns.drop(col_t):
            if col in vues:
                raise ValueError(f"Colonne '{col}' présente dans plusieurs DataFrames.")
            if not pd.api.types.is_numeric_dtype(df[col]):
                raise ValueError(f"DataFrame n°{i} : colonne '{col}' non numérique.")
            vues.add(col)

    grille = np.unique(np.concatenate([df[col_t].to_numpy(dtype=float) for df in dfs]))
    sortie = pd.DataFrame({col_t: grille})

    for df in dfs:
        df = df.sort_values(col_t)
        t = df[col_t].to_numpy(dtype=float)
        for col in df.columns.drop(col_t):
            y = df[col].to_numpy(dtype=float)
            ok = ~np.isnan(y)  # un trou dans une colonne n'efface pas ses voisins
            if ok.sum() == 0:
                sortie[col] = np.nan
                continue
            sortie[col] = np.interp(grille, t[ok], y[ok], left=np.nan, right=np.nan)

    return sortie


if __name__ == "__main__":
    df1 = pd.DataFrame({"t": [2.0, 4.0], "masse": [10.0, 20.0]})
    df2 = pd.DataFrame({"t": [1.0, 3.0, 5.0], "poussee": [100.0, 80.0, 60.0]})
    print(fusionner_sur_t([df1, df2]))
