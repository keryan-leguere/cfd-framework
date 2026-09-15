"""Ce que **vous** écrivez : la fonction qui appelle votre modèle.

C'est la seule pièce que cfd-validation ne peut pas fournir, parce qu'elle
dépend de la signature de vos routines. Le contrat tient en trois lignes :

* elle reçoit un ``DataFrame`` portant les colonnes indépendantes de la table
  et les constantes déclarées ;
* elle rend un ``DataFrame`` de **même longueur**, **dans le même ordre**,
  portant les QOI ;
* elle ne trie rien et ne regroupe rien — un réordonnancement comparerait
  chaque point à son voisin, et sortirait rouge sur un modèle juste.

Ici l'« appel au modèle » est une recherche dans la table du module, parce que
c'est ce que fait un code juste : une interpolation vaut exactement la valeur
tabulée à ses nœuds. Avec un vrai module f2py, la même fonction s'écrit ::

    rendu["CN"] = aero.eval_cn(df["mach"].to_numpy(),
                               df["alpha"].to_numpy(),
                               df["delta"].to_numpy())

Voir 00_DOC/03_BRANCHER_SON_MODELE.md.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import aero_factice


def _table(bloc: object, tableau: str, compteur: str) -> np.ndarray:
    """Les lignes réellement renseignées d'un tableau du module."""
    brut = np.asarray(getattr(bloc, tableau), dtype=float)
    remplies = int(np.asarray(getattr(bloc, compteur)).reshape(-1)[0])
    return brut[:remplies]


def _chercher(lignes: np.ndarray, point: np.ndarray) -> float:
    """La valeur tabulée au nœud *point*, ou 0 si le nœud n'est pas dans la table."""
    axes = lignes[:, : point.size]
    trouve = np.flatnonzero(np.all(np.isclose(axes, point, rtol=0.0, atol=1e-9), axis=1))
    return float(lignes[trouve[0], point.size]) if trouve.size else 0.0


def appeler(entrees: pd.DataFrame) -> pd.DataFrame:
    """Le modèle, appelé sur un cadre de points. Rend le même cadre plus la QOI."""
    rendu = entrees.copy()

    if "delta" in entrees.columns:
        lignes = _table(aero_factice.tab_cn, "tab_cn", "npt_cn")
        points = entrees.loc[:, ["mach", "alpha", "delta"]].to_numpy(dtype=float)
        rendu["CN"] = [_chercher(lignes, point) for point in points]
    else:
        lignes = _table(aero_factice.tab_ca, "tab_ca", "npt_ca")
        points = entrees.loc[:, ["mach", "alpha"]].to_numpy(dtype=float)
        rendu["CA"] = [_chercher(lignes, point) for point in points]

    return rendu
