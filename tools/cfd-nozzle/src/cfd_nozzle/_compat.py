"""Petites compatibilités entre versions de Python.

cfd-nozzle doit s'installer tel quel sur les calculateurs isolés, où l'inter-
préteur disponible est souvent celui de la distribution — Python 3.9 sur les
bases RHEL 8 / Rocky 8 encore très répandues en CFD. Ce module regroupe les
rares endroits où la bibliothèque standard a changé depuis, pour que le reste
du code s'écrive une seule fois.

Même intention et même contenu que ``cfd_perf._compat`` : les paquets de
``tools/`` sont indépendants (chacun son ``pyproject.toml``), donc le shim est
dupliqué plutôt que partagé.
"""

from __future__ import annotations

import itertools
import sys
from collections.abc import Iterable, Iterator
from typing import Any, TypeVar, overload

__all__ = ["pairwise", "zip_strict"]


if sys.version_info >= (3, 10):
    pairwise = itertools.pairwise
else:  # pragma: no cover - dépend de l'interpréteur

    def pairwise(iterable: Iterable[Any]) -> Iterator[tuple[Any, Any]]:
        """``itertools.pairwise`` (Python 3.10+) : (a, b), (b, c), (c, d)…"""
        premier, second = itertools.tee(iterable)
        next(second, None)
        return zip(premier, second)


_T1 = TypeVar("_T1")
_T2 = TypeVar("_T2")
_T3 = TypeVar("_T3")
_T4 = TypeVar("_T4")
_T5 = TypeVar("_T5")


@overload
def zip_strict(i1: Iterable[_T1], i2: Iterable[_T2], /) -> Iterator[tuple[_T1, _T2]]: ...


@overload
def zip_strict(
    i1: Iterable[_T1], i2: Iterable[_T2], i3: Iterable[_T3], /
) -> Iterator[tuple[_T1, _T2, _T3]]: ...


@overload
def zip_strict(
    i1: Iterable[_T1], i2: Iterable[_T2], i3: Iterable[_T3], i4: Iterable[_T4], /
) -> Iterator[tuple[_T1, _T2, _T3, _T4]]: ...


@overload
def zip_strict(
    i1: Iterable[_T1],
    i2: Iterable[_T2],
    i3: Iterable[_T3],
    i4: Iterable[_T4],
    i5: Iterable[_T5],
    /,
) -> Iterator[tuple[_T1, _T2, _T3, _T4, _T5]]: ...


def zip_strict(*iterables: Iterable[Any]) -> Iterator[tuple[Any, ...]]:
    """``zip(..., strict=True)`` (Python 3.10+), sur toutes les versions.

    La longueur commune est une vraie vérification métier ici — un tableau de
    valeurs et sa liste d'en-têtes qui divergent est un bug, pas une troncature
    silencieuse à accepter. Comme le ``zip`` natif, l'erreur est levée pendant
    l'itération, au moment où le déséquilibre se voit.
    """
    if sys.version_info >= (3, 10):
        return zip(*iterables, strict=True)
    return _zip_strict(*iterables)  # pragma: no cover - dépend de l'interpréteur


def _zip_strict(*iterables: Iterable[Any]) -> Iterator[tuple[Any, ...]]:  # pragma: no cover
    manquant = object()
    for combo in itertools.zip_longest(*iterables, fillvalue=manquant):
        if any(valeur is manquant for valeur in combo):
            raise ValueError("zip_strict() : les itérables n'ont pas la même longueur")
        yield combo
