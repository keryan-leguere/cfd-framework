"""Small compatibility shims between Python versions.

cfd-plot has to install as-is on isolated clusters, where the available
interpreter is often the distribution's own — Python 3.9 on the RHEL 8 /
Rocky 8 bases still widespread in CFD. This module gathers the few places
where the standard library has moved on since, so the rest of the code is
written once.

Same intent and same contents as ``cfd_perf._compat``: the packages under
``tools/`` are independent (each with its own ``pyproject.toml``), so the shim
is duplicated rather than shared.
"""

from __future__ import annotations

import itertools
import sys
from collections.abc import Iterable, Iterator
from typing import Any, TypeVar, overload

__all__ = ["zip_strict"]


_T1 = TypeVar("_T1")
_T2 = TypeVar("_T2")
_T3 = TypeVar("_T3")
_T4 = TypeVar("_T4")
_T5 = TypeVar("_T5")


@overload
def zip_strict(i1: Iterable[_T1], i2: Iterable[_T2], /) -> Iterator[tuple[_T1, _T2]]: ...


@overload
def zip_strict(i1: Iterable[_T1], i2: Iterable[_T2], i3: Iterable[_T3], /) -> Iterator[tuple[_T1, _T2, _T3]]: ...


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
    """``zip(..., strict=True)`` (Python 3.10+), on every version.

    The common length is a real check here — a set of axes and the labels meant
    for them drifting apart is a bug, not a truncation to swallow silently. Like
    the built-in ``zip``, the error is raised during iteration, at the point
    where the mismatch shows.
    """
    if sys.version_info >= (3, 10):
        return zip(*iterables, strict=True)
    return _zip_strict(*iterables)  # pragma: no cover - interpreter dependent


def _zip_strict(*iterables: Iterable[Any]) -> Iterator[tuple[Any, ...]]:  # pragma: no cover
    missing = object()
    for combo in itertools.zip_longest(*iterables, fillvalue=missing):
        if any(value is missing for value in combo):
            raise ValueError("zip_strict(): iterables have different lengths")
        yield combo
