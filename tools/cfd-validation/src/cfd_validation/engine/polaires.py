"""Les polaires des tables : la courbe du code le long d'un axe, et les nœuds de la table.

Pour chaque table et chaque abscisse retenue (:class:`~cfd_validation.data.polaires.Polaires`),
un seul appel de l'évaluateur : pour chaque condition (un nœud de chacun des
autres axes), les abscisses de :func:`~cfd_validation.core.mailles.abscisses_polaire`
— nœuds, mailles subdivisées, prolongement de ``ecart × étendue`` de chaque côté,
rien d'un côté que la table déclare inatteignable.

Les polaires ne rendent **pas** de verdict : elles montrent, d'un coup d'œil, ce
que les trois tests vérifient point par point — la courbe passe par les nœuds
(lecture), elle est droite entre eux (interpolation), elle sature ou se
prolonge au-delà des bornes selon la consigne (bornes).
"""

from __future__ import annotations

import itertools
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from cfd_validation.core.bornes import INATTEIGNABLE
from cfd_validation.core.mailles import abscisses_polaire
from cfd_validation.data.polaires import COURBES_MAX, Polaires
from cfd_validation.data.tables import ErreurTable, TableReference
from cfd_validation.engine.injection import appeler
from cfd_validation.engine.lecture_tables import Evaluateur

__all__ = ["COLONNE_VALEUR", "Polaire", "calculer_polaires"]

#: Colonne de la grandeur dans les tableaux d'une polaire.
COLONNE_VALEUR = "valeur"


@dataclass(frozen=True)
class Polaire:
    """Les polaires d'une table le long d'un axe, toutes conditions comprises.

    ``code`` et ``noeuds`` ont une colonne par axe de la table et ``valeur`` :
    la courbe du code (dense, prolongée) et les nœuds de la table, pour les
    mêmes conditions.
    """

    table: TableReference
    axe: str
    conditions: tuple[str, ...]
    superpose: str | None
    code: pd.DataFrame
    noeuds: pd.DataFrame
    bornes: tuple[float, float]
    consignes: tuple[str | None, str | None]
    prolongements: tuple[float, float]

    @property
    def nom(self) -> str:
        return self.table.nom

    @property
    def n_courbes(self) -> int:
        return len(self.noeuds) // len(self.table.axes[self.axe])

    @property
    def n_appels(self) -> int:
        return len(self.code)


def _conditions(table: TableReference, spec: Polaires, axe: str) -> tuple[list[str], pd.DataFrame]:
    """Les autres axes et leurs combinaisons de nœuds retenus (premier axe le plus rapide)."""
    autres = [a for a in table.noms_axes if a != axe]
    if not autres:
        return [], pd.DataFrame(index=range(1))
    grilles = [spec.noeuds_condition(table, a) for a in autres]
    lignes = [tuple(reversed(p)) for p in itertools.product(*reversed(grilles))]
    return autres, pd.DataFrame(lignes, columns=autres)


def _croiser(conditions: pd.DataFrame, axe: str, x: np.ndarray, colonnes: Sequence[str]) -> pd.DataFrame:
    """Chaque condition × chaque abscisse, colonnes dans l'ordre de la table."""
    n_c, n_x = len(conditions), len(x)
    df = conditions.loc[conditions.index.repeat(n_x)].reset_index(drop=True)
    df[axe] = np.tile(x, n_c)
    return df[list(colonnes)]


def _superpose(spec: Polaires, autres: Sequence[str], conditions: pd.DataFrame) -> str | None:
    varient = [a for a in autres if conditions[a].nunique() > 1]
    if spec.superposer is not None and spec.superposer in varient:
        return spec.superposer
    return varient[0] if varient else None


def _polaire(
    table: TableReference, evaluer: Evaluateur, defauts: Mapping[str, Any], spec: Polaires,
    axe: str, ecart: float,
) -> Polaire:
    grille = table.axes[axe]
    consignes = table.bornes.get(axe)
    c_min, c_max = consignes if consignes else (None, None)
    prolongements = (0.0 if c_min == INATTEIGNABLE else ecart, 0.0 if c_max == INATTEIGNABLE else ecart)
    x = abscisses_polaire(grille, subdivisions=spec.subdivisions,
                          ecart_min=prolongements[0], ecart_max=prolongements[1])
    autres, conditions = _conditions(table, spec, axe)
    colonnes = table.noms_axes
    points = _croiser(conditions, axe, x, colonnes)
    appel = appeler(table, evaluer, defauts, points)
    code = points.copy()
    code[COLONNE_VALEUR] = appel.code

    noeuds = _croiser(conditions, axe, grille, colonnes)
    indices = [np.searchsorted(table.axes[a], noeuds[a].to_numpy()) for a in colonnes]
    noeuds[COLONNE_VALEUR] = table.valeurs[tuple(indices)]
    return Polaire(
        table=table, axe=axe, conditions=tuple(autres), superpose=_superpose(spec, autres, conditions),
        code=code, noeuds=noeuds, bornes=(float(grille[0]), float(grille[-1])),
        consignes=(c_min, c_max), prolongements=prolongements,
    )


def calculer_polaires(
    tables: Sequence[TableReference],
    evaluer: Evaluateur,
    defauts: Mapping[str, Any],
    polaires: Mapping[str, Polaires] | None = None,
    *,
    ecart: float = 0.10,
    courbes_max: int = COURBES_MAX,
) -> tuple[Polaire, ...]:
    """Les polaires de chaque table (``polaires[nom]``, sinon toutes les abscisses, tous les nœuds).

    Une table dont les polaires dépasseraient ``courbes_max`` courbes est
    refusée : c'est le cas d'une table 5D laissée à ses défauts, qu'il faut
    restreindre par ``Polaires(noeuds=…)``.
    """
    if not (ecart >= 0):
        raise ErreurTable(f"écart {ecart!r} : une fraction positive de l'étendue est attendue")
    specs = dict(polaires or {})
    noms = {t.nom for t in tables}
    inconnues = sorted(set(specs) - noms)
    if inconnues:
        raise ErreurTable(f"polaires déclarées pour {', '.join(inconnues)}, qui n'est pas une table testée")
    rendu: list[Polaire] = []
    for table in tables:
        spec = specs.get(table.nom, Polaires())
        spec.verifier(table)
        abscisses = spec.axes_abscisses(table)
        n_courbes = sum(len(_conditions(table, spec, a)[1]) for a in abscisses)
        if n_courbes > courbes_max:
            raise ErreurTable(
                f"polaires de {table.nom} : {n_courbes} courbes (plus de {courbes_max}) — restreindre les "
                f"conditions, par exemple Polaires(noeuds={{\"{table.noms_axes[-1]}\": [...]}}), ou les abscisses"
            )
        rendu += [_polaire(table, evaluer, defauts, spec, a, ecart) for a in abscisses]
    return tuple(rendu)
