"""Fixtures partagées par la suite.

Le double de test est le faux module livré avec le paquet
(:mod:`cfd_validation.wrap.factice`), et non un objet monté pour l'occasion :
c'est le même que celui de l'exemple et de la documentation, si bien qu'un test
qui passe atteste de ce que le lecteur va taper.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import matplotlib
import numpy as np
import pandas as pd
import pytest

# Aucune figure ne doit ouvrir de fenêtre pendant les tests.
matplotlib.use("Agg")

from cfd_validation.core.ecart import comparer
from cfd_validation.core.motifs import Contexte
from cfd_validation.data.spec import SpecTable, charger_tables
from cfd_validation.wrap.factice import (
    TABLES,
    ModeleFactice,
    ModuleFactice,
    module_factice,
)


@pytest.fixture
def module() -> ModuleFactice:
    """Le faux module f2py, tables remplies."""
    return module_factice()


@pytest.fixture
def declarations() -> dict[str, dict[str, Any]]:
    """La déclaration brute, telle qu'un utilisateur l'écrit."""
    return {nom: dict(contenu) for nom, contenu in TABLES.items()}


@pytest.fixture
def specs(declarations: dict[str, dict[str, Any]]) -> dict[str, SpecTable]:
    """La déclaration validée."""
    return charger_tables(declarations)


@pytest.fixture
def spec_cn(specs: dict[str, SpecTable]) -> SpecTable:
    """La spec de la table à trois axes, celle qui porte tous les pièges."""
    return specs["CN"]


@pytest.fixture
def modele(module: ModuleFactice) -> ModeleFactice:
    """Un modèle qui relit exactement ses tables."""
    return ModeleFactice(module)


def contexte_de_tableaux(
    noeuds: Any,
    reference: Any,
    obtenu: Any,
    *,
    noms: tuple[str, ...] = ("x", "y"),
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> Contexte:
    """Un contexte de détection bâti à la main, pour éprouver un motif isolé."""
    return Contexte(
        noeuds=np.asarray(noeuds, dtype=float),
        ecart=comparer(reference, obtenu, rtol=rtol, atol=atol),
        noms=noms,
    )


def grille(*axes: Any) -> np.ndarray:
    """Le produit cartésien d'axes, en tableau de nœuds (une ligne par point)."""
    maillage = np.meshgrid(*[np.asarray(axe, dtype=float) for axe in axes], indexing="ij")
    return np.stack([bloc.ravel() for bloc in maillage], axis=1)


def textes_de(figure: Any) -> set[str]:
    """Tous les textes portés par une figure, pour vérifier une annotation."""
    from matplotlib.text import Text

    return {
        artiste.get_text()
        for artiste in figure.findobj(match=lambda a: isinstance(a, Text))
        if isinstance(artiste, Text)
    }


@dataclass(frozen=True)
class FauxContexte:
    """Ce que ``batch_plot`` passe à un hook ``on_before_save``.

    Reproduit les seuls champs de ``BatchPlotContext`` que le hook regarde. On
    le construit à la main plutôt que d'appeler ``batch_plot`` : le hook doit
    se tester sans écrire une seule figure.
    """

    y_key: str = "CN"
    sweep_key: str = "mach"
    y_spec: Mapping[str, Any] = field(default_factory=lambda: {"col_name": "CN"})
    x_spec: Mapping[str, Any] = field(default_factory=lambda: {"col_name": "mach"})
    flight_point: Mapping[str, float] = field(default_factory=dict)
    fixed_sweeps: Mapping[str, float] = field(default_factory=dict)
    fold_kind: str | None = None
    fold_layout: str | None = None


def cadre(**colonnes: Any) -> pd.DataFrame:
    """Un cadre de données court, écrit en une ligne."""
    return pd.DataFrame(colonnes)
