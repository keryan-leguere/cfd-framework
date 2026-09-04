"""Small compatibility shims between Python — and Matplotlib — versions.

cfd-plot has to install as-is on isolated clusters, where the available
interpreter is often the distribution's own — Python 3.9 on the RHEL 8 /
Rocky 8 bases still widespread in CFD. This module gathers the few places
where the standard library has moved on since, so the rest of the code is
written once.

The same happens one layer up: ``pyproject.toml`` asks for Matplotlib >= 3.8,
but a cluster commonly *provides* Matplotlib (a module, a container, a
site-wide install) and the package ends up next to whatever version is there.
The layout-engine API is where that bites — ``Figure.get_layout_engine`` /
``set_layout_engine`` only exist from 3.6 on, so a compare or folded figure
died with ``AttributeError: 'Figure' object has no attribute
'get_layout_engine'`` on an older one. The two helpers below speak whichever
API the installed Matplotlib has.

The Python part has the same intent and contents as ``cfd_perf._compat``: the
packages under ``tools/`` are independent (each with its own
``pyproject.toml``), so the shim is duplicated rather than shared.
"""

from __future__ import annotations

import itertools
import sys
from collections.abc import Iterable, Iterator
from typing import Any, TypeVar, overload

__all__ = ["figure_disable_layout", "figure_set_layout_pad", "zip_strict"]


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


# ---------------------------------------------------------------------------
# Matplotlib layout engine
# ---------------------------------------------------------------------------
#
# Matplotlib >= 3.6 exposes the active layout as an object
# (``fig.get_layout_engine()``); before that, "constrained" and "tight" were two
# independent booleans on the figure with their own pad setters. Both helpers
# probe for the modern method rather than testing a version string: a version
# string is a claim, an attribute is the fact.


def figure_set_layout_pad(fig: Any, *, h_pad: float) -> None:
    """Set the vertical padding of *fig*'s active automatic layout, if any.

    A figure laid out by hand (no engine, or both flags off) is left alone —
    there is nothing to pad, and forcing an engine on would move everything.
    """
    get_engine = getattr(fig, "get_layout_engine", None)
    if get_engine is not None:
        engine = get_engine()
        if engine is not None:
            engine.set(h_pad=h_pad)
        return

    # Matplotlib < 3.6.
    if getattr(fig, "get_constrained_layout", None) and fig.get_constrained_layout():
        fig.set_constrained_layout_pads(h_pad=h_pad)
    elif getattr(fig, "get_tight_layout", None) and fig.get_tight_layout():
        fig.set_tight_layout({"h_pad": h_pad})


def figure_disable_layout(fig: Any) -> None:
    """Turn off automatic layout on *fig* (the ``"none"`` engine).

    Used by the pages that place their artists in figure coordinates and by the
    animation writer once the first frame has fixed the geometry: an engine
    still running would fight them, or silently re-measure between frames.
    """
    set_engine = getattr(fig, "set_layout_engine", None)
    if set_engine is not None:
        set_engine("none")
        return

    # Matplotlib < 3.6.
    if getattr(fig, "set_constrained_layout", None):
        fig.set_constrained_layout(False)
    if getattr(fig, "set_tight_layout", None):
        fig.set_tight_layout(False)
