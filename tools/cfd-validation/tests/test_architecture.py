"""La règle de couches, vérifiée sur les imports (AST).

cli/     →  report, engine, data, core
report/  →          engine, data, core
engine/  →                  data, core
data/    →                        core
core/    →  math et numpy seulement

Hors couches : ``integration.py`` (la façade, qui enchaîne calcul, rendu et
pièces) et 01_EXEMPLE/ (des scripts qu'on recopie et qu'on adapte).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "src" / "cfd_validation"

AUTORISE: dict[str, frozenset[str]] = {
    "core": frozenset(),
    "data": frozenset({"core"}),
    "engine": frozenset({"core", "data"}),
    "report": frozenset({"core", "data", "engine"}),
    "cli": frozenset({"core", "data", "engine", "report"}),
}
BANNIES_DANS_CORE = ("yaml", "rich", "pandas", "matplotlib")
BANNIES_HORS_RENDU = ("rich", "matplotlib")


def _modules() -> list[Path]:
    return sorted(p for p in SOURCE.rglob("*.py") if "__pycache__" not in p.parts)


def _couche(chemin: Path) -> str | None:
    parts = chemin.relative_to(SOURCE).parts
    return parts[0] if len(parts) > 1 and parts[0] in AUTORISE else None


def _imports(chemin: Path) -> list[str]:
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    noms: list[str] = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            noms += [a.name for a in noeud.names]
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            noms.append(noeud.module)
    return noms


@pytest.mark.parametrize("chemin", _modules(), ids=lambda p: p.name)
def test_couches(chemin: Path) -> None:
    couche = _couche(chemin)
    if couche is None:
        return
    permises = AUTORISE[couche] | {couche}
    fautifs = [
        n
        for n in _imports(chemin)
        if n.startswith("cfd_validation.")
        and n.split(".")[1] in AUTORISE
        and n.split(".")[1] not in permises
    ]
    assert not fautifs, f"{chemin.name} ({couche}) importe {fautifs}"


@pytest.mark.parametrize("chemin", _modules(), ids=lambda p: p.name)
def test_bibliotheques_bannies(chemin: Path) -> None:
    couche = _couche(chemin)
    bannies = (
        BANNIES_DANS_CORE
        if couche == "core"
        else BANNIES_HORS_RENDU
        if couche in {"data", "engine"}
        else ()
    )
    fautifs = [n for n in _imports(chemin) if n.split(".")[0] in bannies]
    assert not fautifs, f"{chemin.name} importe {fautifs}"


@pytest.mark.parametrize("chemin", _modules(), ids=lambda p: p.name)
def test_docstring_et_annotations_reportees(chemin: Path) -> None:
    """Chaque module a une docstring ; s'il contient du code, il reporte ses annotations.

    Le report (``from __future__ import annotations``) est ce qui permet
    d'écrire ``X | None`` en restant compatible Python 3.9.
    """
    contenu = chemin.read_text(encoding="utf-8")
    arbre = ast.parse(contenu)
    assert ast.get_docstring(arbre), chemin.name
    if len(arbre.body) > 1:
        assert "from __future__ import annotations" in contenu, chemin.name

