"""Accès optionnel à la bibliothèque de figures maison :mod:`cfd_plot`.

cfd-dispersion trace ses figures avec ``cfd_plot`` quand ce paquet est
installé, et retombe sur Matplotlib nu sinon : le paquet doit rester utilisable
déployé seul, sans le reste du framework.

``cfd-plot`` est un paquet frère de ce dépôt, pas une publication PyPI : il ne
peut donc pas être déclaré comme dépendance normale. On l'installe à côté de
cfd-dispersion avec ::

    pip install -e tools/cfd-plot

Appeler :func:`get_plotting` pour le module (ou None) et vérifier
:data:`HAS_PLOTTING`.

Une seule exception à cette souplesse : :mod:`cfd_dispersion.batch`, qui greffe
la dispersion sur ``cfd_plot.batch_plot``. Celui-là ne peut pas se dégrader —
sans cfd-plot il n'y a pas de figure à décorer — et l'importe donc directement.
"""

from __future__ import annotations

from functools import lru_cache
from types import ModuleType
from typing import cast


@lru_cache(maxsize=1)
def get_plotting() -> ModuleType | None:
    """Retourne le module :mod:`cfd_plot`, ou None s'il n'est pas installé."""
    try:
        import cfd_plot
    except ImportError:
        return None
    # cfd-plot ne livre pas de marqueur py.typed : mypy voit le module en Any.
    return cast(ModuleType, cfd_plot)


HAS_PLOTTING: bool = get_plotting() is not None

__all__ = ["HAS_PLOTTING", "get_plotting"]
