"""Fixtures partagées par la suite."""

from __future__ import annotations

import matplotlib
import pytest
from matplotlib.figure import Figure
from matplotlib.text import Text

from cfd_dispersion.core.lois import JeuDeLois

# Aucune figure ne doit ouvrir de fenêtre pendant les tests.
matplotlib.use("Agg")

from cfd_dispersion.core.lois import charger_lois

#: Une table de lois couvrant les cas intéressants : une tronquée, une
#: uniforme, une gaussienne pleine, et une composante dégénérée.
TABLE_EXEMPLE: dict[str, dict[str, float]] = {
    "Cm_alpha": {
        "Biais_Type": 5,
        "Biais_M": 0.0,
        "Biais_ET": 0.015,
        "FE_Type": 6,
        "FE_M": 0.0,
        "FE_ET": 0.10,
    },
    "Cn_beta": {
        "Biais_Type": 3,
        "Biais_M": 0.0,
        "Biais_ET": 0.02,
        "FE_Type": 4,
        "FE_M": 0.0,
        "FE_ET": 0.08,
    },
    "CA": {
        "Biais_Type": 2,
        "Biais_M": 0.001,
        "Biais_ET": 0.0,
        "FE_Type": 3,
        "FE_M": 0.0,
        "FE_ET": 0.05,
    },
}


def textes_de(figure: Figure) -> set[str]:
    """Tous les textes portés par une figure.

    Passe par un prédicat plutôt que par une classe : ``findobj(match=...)``
    est typé ``Callable[[Artist], bool]``, et les stubs Matplotlib n'exportent
    pas ``pyplot.Text``.
    """
    return {
        artiste.get_text()
        for artiste in figure.findobj(match=lambda a: isinstance(a, Text))
        if isinstance(artiste, Text)
    }


@pytest.fixture
def table() -> dict[str, dict[str, float]]:
    """La table de lois brute, telle qu'un utilisateur l'écrit."""
    return {coeff: dict(spec) for coeff, spec in TABLE_EXEMPLE.items()}


@pytest.fixture
def lois(table: dict[str, dict[str, float]]) -> JeuDeLois:
    """Le jeu de lois chargé."""
    return charger_lois(table)
