"""La règle de couches et le confinement des bibliothèques lourdes, vérifiés sur les imports (AST).

cli/     →  report, engine, data, core
report/  →          engine, data, core
engine/  →                  data, core
data/    →                        core
core/    →  math et numpy seulement

Chaque bibliothèque lourde ou optionnelle n'est importée que par un module : le
jour où elle manque ou change d'API, on sait où regarder.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "src" / "cfd_trajcast"

AUTORISE: dict[str, frozenset[str]] = {
    "core": frozenset(),
    "data": frozenset({"core"}),
    "engine": frozenset({"core", "data"}),
    "report": frozenset({"core", "data", "engine"}),
    "cli": frozenset({"core", "data", "engine", "report"}),
}
#: core ne connaît que NumPy.
PERMISES_DANS_CORE = {"numpy", "math", "dataclasses", "__future__", "collections", "typing", "functools"}
#: Bibliothèque → seuls modules (relatifs à SOURCE) autorisés à l'importer.
CONFINEES = {
    "pyvista": {"engine/rendu/pyvista_.py"},
    "vtk": {"engine/rendu/pyvista_.py"},
    "vtkmodules": {"engine/rendu/pyvista_.py"},
    "bpy": {"engine/rendu/blender.py"},
    "mathutils": {"engine/rendu/blender.py"},
    "matplotlib": {"engine/telemetrie.py"},
    "cascadio": {"data/maquette.py"},
    "trimesh": {"data/maquette.py"},
    "rocketpy": {"data/rocketpy_.py"},
    "rich": {"report/theme.py", "report/console.py", "report/rendu.py", "cli/main.py"},
    "imageio_ffmpeg": {"engine/encodage.py", "engine/diagnostic.py"},
    "PIL": {"engine/encodage.py", "engine/montage.py", "engine/effets.py"},
}


def _modules() -> list[Path]:
    return sorted(
        p for p in SOURCE.rglob("*.py") if "__pycache__" not in p.parts and "01_EXEMPLE" not in p.parts
    )


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


@pytest.mark.parametrize("chemin", _modules(), ids=lambda p: str(p.relative_to(SOURCE)))
def test_couches(chemin: Path) -> None:
    couche = _couche(chemin)
    if couche is None:
        return
    permises = AUTORISE[couche] | {couche}
    fautifs = [
        n for n in _imports(chemin)
        if n.startswith("cfd_trajcast.") and n.split(".")[1] in AUTORISE and n.split(".")[1] not in permises
    ]
    assert not fautifs, f"{chemin.name} ({couche}) importe {fautifs}"


@pytest.mark.parametrize("chemin", _modules(), ids=lambda p: str(p.relative_to(SOURCE)))
def test_core_numpy_seulement(chemin: Path) -> None:
    if _couche(chemin) != "core":
        return
    fautifs = [
        n for n in _imports(chemin)
        if n.split(".")[0] not in PERMISES_DANS_CORE and not n.startswith("cfd_trajcast.core")
    ]
    assert not fautifs, f"{chemin.name} importe {fautifs}"


@pytest.mark.parametrize("chemin", _modules(), ids=lambda p: str(p.relative_to(SOURCE)))
def test_bibliotheques_confinees(chemin: Path) -> None:
    relatif = chemin.relative_to(SOURCE).as_posix()
    fautifs = [
        n for n in _imports(chemin)
        if n.split(".")[0] in CONFINEES and relatif not in CONFINEES[n.split(".")[0]]
    ]
    assert not fautifs, f"{relatif} importe {fautifs}"


@pytest.mark.parametrize("chemin", _modules(), ids=lambda p: str(p.relative_to(SOURCE)))
def test_docstring_et_annotations_reportees(chemin: Path) -> None:
    """Chaque module a une docstring ; s'il contient du code, il reporte ses annotations.

    Le report (``from __future__ import annotations``) permet d'écrire ``X | None``
    en restant compatible Python 3.9.
    """
    contenu = chemin.read_text(encoding="utf-8")
    arbre = ast.parse(contenu)
    assert ast.get_docstring(arbre), chemin.name
    if len(arbre.body) > 1:
        assert "from __future__ import annotations" in contenu, chemin.name
