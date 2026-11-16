"""La référence 00_DOC/02_CONFIGURATION.md cite toutes les clés que le lecteur accepte."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from cfd_trajcast.data import configuration as c

RACINE = Path(__file__).resolve().parents[1]
DOC = (RACINE / "00_DOC" / "02_CONFIGURATION.md").read_text(encoding="utf-8")
#: Les mots écrits en code (entre accents graves) : une clé doit en faire partie.
MOTS_CODE = {mot for bloc in re.findall(r"`([^`]+)`", DOC) for mot in re.findall(r"\w+", bloc)}


def _cles_du_lecteur() -> set[str]:
    """Toutes les chaînes des ensembles passés à ``_cles(…)`` et des tables de clés du module."""
    source = Path(c.__file__).read_text(encoding="utf-8")
    cles: set[str] = set()
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, ast.Call) and getattr(noeud.func, "id", "") == "_cles" and len(noeud.args) >= 3:
            ensemble = noeud.args[2]
            if isinstance(ensemble, ast.Set):
                cles |= {e.value for e in ensemble.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
    for valeurs in c._CLES_VUE.values():
        cles |= valeurs
    cles |= {"principale", "incrustations", "cases", "telemetrie"}  # dispositions (dict local)
    return cles


@pytest.mark.parametrize("cle", sorted(_cles_du_lecteur()))
def test_cle_documentee(cle: str) -> None:
    assert cle in MOTS_CODE, f"clé `{cle}` absente de 02_CONFIGURATION.md"


@pytest.mark.parametrize("valeur", [*c.PRESETS_STYLE, *c.JETS, *c.MODES_VUE, *c.SOLS, *c.RESOLUTIONS,
                                    *c.MOTEURS, *c.RENDUS_BLENDER, *c.TRANSITIONS, *c.POSITIONS_TITRE])
def test_valeur_documentee(valeur: str) -> None:
    assert f"`{valeur}`" in DOC, f"valeur `{valeur}` absente de 02_CONFIGURATION.md"
