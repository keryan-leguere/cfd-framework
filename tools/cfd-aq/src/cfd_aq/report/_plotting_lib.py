"""Optional access to the in-house :mod:`cfd_plot` figure library.

cfd-aq renders its figures with ``cfd_plot`` when that package is installed,
and falls back to plain Matplotlib when it is not: cfd-aq must stay usable
when deployed on its own, without the rest of the framework.

``cfd-plot`` is a sibling package in this repository, not a PyPI release, so
it cannot be declared as a normal dependency. Install it alongside cfd-aq
with::

    pip install -e tools/cfd-plot

Call :func:`get_plotting` for the module (or None) and check
:data:`HAS_PLOTTING`.
"""

from __future__ import annotations

from functools import lru_cache
from types import ModuleType
from typing import cast


@lru_cache(maxsize=1)
def get_plotting() -> ModuleType | None:
    """Return the :mod:`cfd_plot` module, or None when it is not installed."""
    try:
        import cfd_plot
    except ImportError:
        return None
    # cfd-plot ne livre pas de marqueur py.typed : mypy voit le module comme Any.
    return cast(ModuleType, cfd_plot)


HAS_PLOTTING: bool = get_plotting() is not None
