"""Optional access to the in-house :mod:`cfd_plot` figure library.

cfd-perf renders its figures with ``cfd_plot`` when that package is installed,
and falls back to plain Matplotlib when it is not: cfd-perf must stay usable
when it is deployed on its own, without the rest of the framework
(see ``00_DOC/06_INSTALLATION_AIR_GAP.md``).

``cfd-plot`` is a sibling package in this repository, not a PyPI release, so it
cannot be declared as a normal dependency. Install it alongside cfd-perf with::

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
    # cfd-plot ships no py.typed marker, so mypy sees the module as Any.
    return cast(ModuleType, cfd_plot)


HAS_PLOTTING: bool = get_plotting() is not None
