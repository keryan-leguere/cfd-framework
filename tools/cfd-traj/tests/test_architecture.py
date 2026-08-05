"""La règle de couche, vérifiée mécaniquement.

    cli/      →  report, synth, engine, data, core
    report/   →          synth, engine, data, core
    synth/    →                         data, core
    engine/   →                         data, core
    data/     →                               core
    core/     →  numpy, scipy, cfd_atm.core seulement

La règle n'est pas décorative. C'est elle qui garantit que ``core`` reste du
calcul pur sur tableaux typés — ce qui est la seule raison pour laquelle mypy
strict est tenable en présence de pandas — et que rien ne décide dans la couche
qui affiche.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
SOURCE = RACINE / "src" / "cfd_traj"

LAYERS = ("core", "data", "engine", "synth", "report", "cli")

#: Couches que chaque couche a le droit d'importer.
ALLOWED: dict[str, frozenset[str]] = {
    "core": frozenset(),
    "data": frozenset({"core"}),
    "engine": frozenset({"core", "data"}),
    "synth": frozenset({"core", "data"}),
    "report": frozenset({"core", "data", "engine", "synth"}),
    "cli": frozenset({"core", "data", "engine", "synth", "report"}),
}

#: Bibliothèques externes interdites à ``core`` : entrées-sorties, tableaux
#: étiquetés, rendu. Tout cela appartient aux couches supérieures.
BANNED_IN_CORE = ("pandas", "yaml", "rich", "matplotlib")

#: Interdites aussi aux couches qui décident : elles ne formatent rien.
BANNED_IN_ENGINE = ("rich", "matplotlib")


def _modules() -> list[Path]:
    """Tous les modules du paquet."""
    return sorted(p for p in SOURCE.rglob("*.py") if "__pycache__" not in p.parts)


def _layer_of(path: Path) -> str | None:
    """La couche à laquelle appartient un module."""
    relative = path.relative_to(SOURCE)
    return relative.parts[0] if len(relative.parts) > 1 else None


def _imports(path: Path) -> list[str]:
    """Les modules importés par un fichier, sous forme de chemins pointés."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append(node.module)
    return out


class TestLayering:
    @pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.name))
    def test_a_module_only_imports_the_layers_below_it(self, path):
        layer = _layer_of(path)
        if layer is None:
            return
        allowed = ALLOWED[layer] | {layer}

        offenders = [
            name
            for name in _imports(path)
            if name.startswith("cfd_traj.")
            and (parts := name.split("."))[1] in LAYERS
            and parts[1] not in allowed
        ]

        assert not offenders, f"{path.relative_to(RACINE)} importe {offenders}"

    def test_the_maths_layer_touches_no_io_no_frames_no_rendering(self):
        offenders: list[str] = []

        for path in _modules():
            if _layer_of(path) != "core":
                continue
            for name in _imports(path):
                root = name.split(".")[0]
                if root in BANNED_IN_CORE:
                    offenders.append(f"{path.relative_to(RACINE)} importe {name}")

        assert not offenders, "\n".join(offenders)

    @pytest.mark.parametrize("layer", ["data", "engine", "synth"])
    def test_the_deciding_layers_never_render(self, layer):
        offenders: list[str] = []

        for path in _modules():
            if _layer_of(path) != layer:
                continue
            for name in _imports(path):
                if name.split(".")[0] in BANNED_IN_ENGINE:
                    offenders.append(f"{path.relative_to(RACINE)} importe {name}")

        assert not offenders, "\n".join(offenders)

    def test_the_maths_layer_depends_only_on_the_atmosphere_package(self):
        allowed_third_party = {"numpy", "scipy", "cfd_atm", "cfd_traj"}
        offenders: list[str] = []

        for path in _modules():
            if _layer_of(path) != "core":
                continue
            for name in _imports(path):
                root = name.split(".")[0]
                if root in allowed_third_party:
                    continue
                # Standard library is fine; anything else is not.
                spec = importlib.util.find_spec(root)
                if spec is not None and spec.origin and "site-packages" in spec.origin:
                    offenders.append(f"{path.relative_to(RACINE)} importe {name}")

        assert not offenders, "\n".join(offenders)


class TestConventions:
    @pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.name))
    def test_every_module_postpones_annotation_evaluation(self, path):
        text = path.read_text(encoding="utf-8")
        if not text.strip() or (path.name == "__init__.py" and len(text.splitlines()) <= 2):
            return

        assert "from __future__ import annotations" in text, path.relative_to(RACINE)

    @pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.name))
    def test_every_module_has_a_docstring(self, path):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        assert ast.get_docstring(tree), path.relative_to(RACINE)


class TestImportGraph:
    def test_every_module_imports_cleanly(self):
        for path in _modules():
            relative = path.relative_to(SOURCE).with_suffix("")
            parts = [p for p in relative.parts if p != "__init__"]
            if not parts or parts[-1] == "__main__":
                continue

            importlib.import_module("cfd_traj." + ".".join(parts))

    def test_the_public_api_is_importable(self):
        import cfd_traj

        assert cfd_traj.__version__
        assert cfd_traj.__all__ == sorted(cfd_traj.__all__)
        for name in cfd_traj.__all__:
            assert hasattr(cfd_traj, name), name
