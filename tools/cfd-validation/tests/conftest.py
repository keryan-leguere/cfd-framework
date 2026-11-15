"""Tables de test partagées : petites, déterministes, aux échecs connus d'avance."""

from __future__ import annotations

import importlib.util
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from types import ModuleType

import numpy as np
import pandas as pd
import pytest

from cfd_validation.paths import EXEMPLE_DIR


def table_reference() -> pd.DataFrame:
    """4 Mach × 5 alpha × 2 configurations = 40 cas, deux sorties numériques et une textuelle."""
    grille = pd.MultiIndex.from_product(
        [[0.5, 0.8, 1.2, 2.0], [-2.0, 0.0, 2.0, 4.0, 6.0], ["A", "B"]], names=["Mach", "alpha", "conf"]
    ).to_frame(index=False)
    a = np.radians(grille["alpha"].to_numpy())
    grille["CN"] = (2.0 + grille["Mach"].to_numpy()) * np.sin(a)
    grille["Cm"] = -0.3 * grille["CN"] + 0.01
    grille["regime"] = np.where(grille["Mach"] < 1.0, "sub", "super")
    return grille


@pytest.fixture
def reference() -> pd.DataFrame:
    return table_reference()


def _importer(nom: str) -> ModuleType:
    chemin = EXEMPLE_DIR / nom
    spec = importlib.util.spec_from_file_location(chemin.stem, chemin)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def exemple() -> ModuleType:
    """Le script d'exemple livré, importé comme module (ses scénarios servent de jeu de test)."""
    return _importer("01_test_integration.py")


@pytest.fixture
def exemple_grand() -> ModuleType:
    """L'exemple 10 entrées × 15 sorties."""
    return _importer("02_grande_table.py")


@contextmanager
def glyphes_manquants_en_erreur() -> Iterator[None]:
    """Fait échouer un test de figure sur tout ``UserWarning`` : un glyphe manquant est une figure fausse.

    Les avertissements de dépréciation sont exclus, même quand ils héritent *aussi* de
    ``UserWarning`` : c'est le cas de ``PyparsingDeprecationWarning`` (pyparsing ≥ 3.3), que
    matplotlib 3.9 — la dernière version installable sous Python 3.9 — déclenche à chaque
    rendu mathtext. Il ne dit rien des figures produites.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        warnings.filterwarnings("ignore", category=DeprecationWarning)  # ajouté après : prioritaire
        yield
