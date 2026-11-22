"""Quelles polaires tracer pour une table : abscisses, nœuds retenus, superposition.

Une **polaire** d'une table est la courbe du code le long d'un axe (l'abscisse),
les autres axes fixés sur un de leurs nœuds (une **condition**), de
``ecart × étendue`` avant la première borne à autant après la dernière. Les
nœuds de la table y sont posés par-dessus : la courbe passe-t-elle par eux
(lecture), est-elle droite entre eux (interpolation), que fait-elle au-delà
(bornes) ?

Par défaut, une polaire par axe et par condition — tous les nœuds des autres
axes. C'est raisonnable en 2D (7 × 7 : 14 courbes) et déraisonnable en 5D
(5⁵ : 3 125) ; ``noeuds`` restreint alors les conditions, ``abscisses`` les
axes tracés.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from cfd_validation.data.tables import ErreurTable, TableReference

__all__ = ["COURBES_MAX", "Polaires"]

#: Courbes au-delà desquelles une table doit restreindre ses polaires.
COURBES_MAX = 200


@dataclass(frozen=True)
class Polaires:
    """Les polaires d'une table.

    Parameters
    ----------
    abscisses
        Axes tracés en abscisse ; ``None`` : tous.
    noeuds
        ``{axe: [valeurs]}`` : les seuls nœuds retenus pour cet axe quand il est
        une condition (jamais quand il est l'abscisse, toujours parcourue de
        part en part). Chaque valeur doit être un nœud de la grille.
    superposer
        Axe dont les conditions sont superposées sur une même figure
        (``fold`` « overlay » de ``batch_plot``). ``None`` : le premier axe,
        dans l'ordre de déclaration, qui prend plusieurs valeurs. Sans objet
        pour la polaire dont il est l'abscisse.
    subdivisions
        Points par maille sur la courbe du code (8 : 7 points entre deux nœuds).
    """

    abscisses: Sequence[str] | None = None
    noeuds: Mapping[str, Sequence[float]] = field(default_factory=dict)
    superposer: str | None = None
    subdivisions: int = 8

    def __post_init__(self) -> None:
        if self.abscisses is not None:
            object.__setattr__(self, "abscisses", tuple(str(a) for a in self.abscisses))
        object.__setattr__(self, "noeuds", {str(k): tuple(float(x) for x in v) for k, v in dict(self.noeuds).items()})
        if not isinstance(self.subdivisions, int) or self.subdivisions < 1:
            raise ErreurTable(f"polaires : subdivisions {self.subdivisions!r}, un entier ≥ 1 est attendu")

    def verifier(self, table: TableReference) -> None:
        """Noms d'axes et nœuds connus de la table ; sinon refusés et nommés."""
        axes = table.noms_axes
        inconnus = [a for a in (*(self.abscisses or ()), *self.noeuds, *([self.superposer] if self.superposer else []))
                    if a not in axes]
        if inconnus:
            raise ErreurTable(f"polaires de {table.nom} : {', '.join(inconnus)} n'est pas un axe ({', '.join(axes)})")
        if self.abscisses is not None and not self.abscisses:
            raise ErreurTable(f"polaires de {table.nom} : aucune abscisse")
        for a, valeurs in self.noeuds.items():
            grille = table.axes[a]
            absents = [v for v in valeurs if not np.any(grille == v)]
            if absents:
                raise ErreurTable(
                    f"polaires de {table.nom} : {a} = {', '.join(f'{v:g}' for v in absents)} n'est pas un nœud "
                    f"({', '.join(f'{g:g}' for g in grille)})"
                )
            if not valeurs:
                raise ErreurTable(f"polaires de {table.nom} : aucun nœud retenu pour {a}")

    def axes_abscisses(self, table: TableReference) -> tuple[str, ...]:
        return tuple(self.abscisses) if self.abscisses is not None else table.noms_axes

    def noeuds_condition(self, table: TableReference, axe: str) -> Any:
        """Les nœuds retenus pour ``axe`` quand il est une condition."""
        if axe in self.noeuds:
            return np.asarray(self.noeuds[axe], dtype=np.float64)
        return table.axes[axe]
