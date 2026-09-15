"""Accès à la bibliothèque de figures maison :mod:`cfd_plot`.

cfd-validation trace ses planches avec ``cfd_plot``, qui est un paquet **frère
de ce dépôt** et non une publication PyPI : il ne peut donc pas figurer dans
les dépendances, et il peut légitimement manquer de l'environnement.

Le partage est net : le contrôle (lecture des tables, comparaison, diagnostic,
rapport terminal) tourne sans ``cfd_plot`` ; les figures, non. C'est ce qui
permet de déployer le paquet seul sur un calculateur isolé et d'y valider un
modèle, quitte à rapatrier les cadres de données pour tracer ailleurs.
"""

from __future__ import annotations

from functools import lru_cache
from types import ModuleType
from typing import cast

__all__ = ["HAS_PLOTTING", "cfd_plot_disponible", "get_plotting"]

_MESSAGE = (
    "cfd-validation trace ses figures avec cfd-plot, qui n'est pas installé.\n"
    "cfd-plot est un paquet frère de ce dépôt, pas une publication PyPI :\n"
    "    pip install -e tools/cfd-plot\n"
    "Le contrôle (lecture, comparaison, diagnostic, rapport) fonctionne sans lui ; "
    "les figures, non."
)


@lru_cache(maxsize=1)
def _importer() -> ModuleType | None:
    try:
        import cfd_plot
    except ImportError:  # pragma: no cover - dépend de l'installation
        return None
    # cfd-plot ne livre pas de marqueur py.typed : mypy voit le module en Any.
    return cast(ModuleType, cfd_plot)


def get_plotting() -> ModuleType:
    """Le module ``cfd_plot``, ou une :class:`ImportError` qui dit quoi taper."""
    module = _importer()
    if module is None:
        raise ImportError(_MESSAGE)
    return module


def cfd_plot_disponible() -> bool:
    """Vrai si ``cfd_plot`` est importable. Ne lève jamais."""
    return _importer() is not None


HAS_PLOTTING: bool = cfd_plot_disponible()
