"""Du cadre de données aux détecteurs de motifs.

Un pont mince, et c'est voulu : les détecteurs de
:mod:`cfd_validation.core.motifs` travaillent sur des tableaux NumPy et ne
doivent rien savoir de pandas. Ici on extrait la géométrie de la table — les
colonnes indépendantes, dans l'ordre déclaré — et on la leur passe.
"""

from __future__ import annotations

import pandas as pd

from cfd_validation.core.ecart import Ecart
from cfd_validation.core.motifs import Contexte, Motif, detecter
from cfd_validation.data.spec import SpecTable

__all__ = ["contexte_de", "diagnostiquer"]


def contexte_de(table: pd.DataFrame, spec: SpecTable, ecart: Ecart) -> Contexte:
    """Le contexte que voient les détecteurs, pour une table et un écart."""
    noeuds = table.loc[:, list(spec.independantes)].to_numpy(dtype=float)
    return Contexte(noeuds=noeuds, ecart=ecart, noms=spec.independantes)


def diagnostiquer(table: pd.DataFrame, spec: SpecTable, ecart: Ecart) -> tuple[Motif, ...]:
    """Les motifs qui expliquent les points fautifs, du plus explicatif au moins.

    Vide quand tout est conforme : il n'y a rien à diagnostiquer.
    """
    if ecart.conforme:
        return ()
    return detecter(contexte_de(table, spec, ecart))
