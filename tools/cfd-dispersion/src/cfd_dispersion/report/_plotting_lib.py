"""Accès à la bibliothèque de figures maison :mod:`cfd_plot`.

**Toutes** les figures de cfd-dispersion passent par ``cfd_plot``. C'est une
exigence, pas une préférence : le format des livrables — police, tailles,
marges, épaisseurs, palette, gabarit d'export — est défini là et nulle part
ailleurs. Une figure tracée en Matplotlib nu sortirait juste, et ne
ressemblerait à aucune autre figure du dossier.

``cfd-plot`` est un paquet frère de ce dépôt, pas une publication PyPI : il ne
peut donc pas être déclaré comme dépendance ordinaire dans ``pyproject.toml``.
Il s'installe à côté de cfd-dispersion ::

    pip install -e tools/cfd-plot

Le reste du paquet — lois, tirage, validation, synthèse chiffrée, ligne de
commande hors figures — n'en a aucun besoin : c'est du calcul, et il tourne
sans lui.

Appeler :func:`get_plotting` pour obtenir le module ; il lève un ``ImportError``
nommant la commande d'installation quand il manque. :func:`cfd_plot_disponible`
répond à la même question sans lever, pour les diagnostics.
"""

from __future__ import annotations

from functools import lru_cache
from types import ModuleType
from typing import cast

_MESSAGE = (
    "cfd-dispersion trace ses figures avec cfd-plot, qui n'est pas installé.\n"
    "cfd-plot est un paquet frère de ce dépôt, pas une publication PyPI :\n"
    "    pip install -e tools/cfd-plot\n"
    "Le calcul (lois, tirage, validation, synthèse) fonctionne sans lui ; "
    "les figures, non."
)


@lru_cache(maxsize=1)
def _importer() -> ModuleType | None:
    try:
        import cfd_plot
    except ImportError:  # pragma: no cover - dépend de l'environnement
        return None
    # cfd-plot ne livre pas de marqueur py.typed : mypy voit le module en Any.
    return cast(ModuleType, cfd_plot)


def get_plotting() -> ModuleType:
    """Retourne le module :mod:`cfd_plot`.

    Raises
    ------
    ImportError
        Si cfd-plot n'est pas installé — avec la commande à taper.
    """
    module = _importer()
    if module is None:  # pragma: no cover - dépend de l'environnement
        raise ImportError(_MESSAGE)
    return module


def cfd_plot_disponible() -> bool:
    """Dit si cfd-plot est installé, sans rien lever."""
    return _importer() is not None


#: Vrai quand cfd-plot est installé. Sert aux diagnostics, pas au tracé.
HAS_PLOTTING: bool = cfd_plot_disponible()

__all__ = ["HAS_PLOTTING", "cfd_plot_disponible", "get_plotting"]
