"""La règle de couche, vérifiée mécaniquement.

    cli/      →  report, engine, wrap, data, core
    report/   →          engine, wrap, data, core
    engine/   →                wrap, data, core
    wrap/     →                      data, core
    data/     →                            core
    core/     →  numpy seulement

La règle n'est pas décorative. C'est elle qui garantit que ``core`` reste du
calcul pur sur tableaux — seule raison pour laquelle les détecteurs de motifs
se testent sur de petites grilles écrites à la main plutôt qu'à travers tout le
paquet — et que rien ne décide dans la couche qui affiche.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parents[1]
SOURCE = RACINE / "src" / "cfd_validation"

COUCHES = ("core", "data", "wrap", "engine", "report", "cli")

#: Couches que chaque couche a le droit d'importer.
AUTORISE: dict[str, frozenset[str]] = {
    "core": frozenset(),
    "data": frozenset({"core"}),
    "wrap": frozenset({"core", "data"}),
    "engine": frozenset({"core", "data", "wrap"}),
    "report": frozenset({"core", "data", "wrap", "engine"}),
    "cli": frozenset({"core", "data", "wrap", "engine", "report"}),
}

#: Interdites à ``core`` : tableaux étiquetés, entrées-sorties, rendu.
#: Tout cela appartient aux couches supérieures.
BANNIES_DANS_CORE = ("pandas", "yaml", "rich", "matplotlib", "cfd_plot")

#: Interdites aux couches qui décident : elles ne formatent rien.
BANNIES_DANS_ENGINE = ("rich", "matplotlib", "cfd_plot")


def _modules() -> list[Path]:
    """Tous les modules du paquet, l'exemple excepté."""
    return sorted(
        chemin
        for chemin in SOURCE.rglob("*.py")
        if "__pycache__" not in chemin.parts and "01_EXEMPLE" not in chemin.parts
    )


def _couche(chemin: Path) -> str | None:
    """La couche à laquelle appartient un module."""
    relatif = chemin.relative_to(SOURCE)
    return relatif.parts[0] if len(relatif.parts) > 1 else None


def _imports(chemin: Path) -> list[str]:
    """Les modules importés par un fichier, sous forme de chemins pointés."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
    noms: list[str] = []
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Import):
            noms.extend(alias.name for alias in noeud.names)
        elif isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.level == 0:
            noms.append(noeud.module)
    return noms


class TestCouches:
    @pytest.mark.parametrize("chemin", _modules(), ids=lambda p: str(p.name))
    def test_un_module_n_importe_que_les_couches_sous_lui(self, chemin: Path) -> None:
        couche = _couche(chemin)
        if couche is None:
            return
        autorisees = AUTORISE[couche] | {couche}

        fautifs = [
            nom
            for nom in _imports(chemin)
            if nom.startswith("cfd_validation.")
            and (morceaux := nom.split("."))
            and len(morceaux) > 1
            and morceaux[1] in COUCHES
            and morceaux[1] not in autorisees
        ]
        assert not fautifs, f"{chemin.name} ({couche}) importe {fautifs}"

    @pytest.mark.parametrize(
        "chemin",
        [p for p in _modules() if _couche(p) == "core"],
        ids=lambda p: str(p.name),
    )
    def test_le_coeur_ne_connait_ni_pandas_ni_le_rendu(self, chemin: Path) -> None:
        fautifs = [
            nom
            for nom in _imports(chemin)
            if any(nom == banni or nom.startswith(f"{banni}.") for banni in BANNIES_DANS_CORE)
        ]
        assert not fautifs, f"{chemin.name} importe {fautifs}"

    @pytest.mark.parametrize(
        "chemin",
        [p for p in _modules() if _couche(p) in {"engine", "data", "wrap"}],
        ids=lambda p: str(p.name),
    )
    def test_les_couches_qui_decident_ne_formatent_rien(self, chemin: Path) -> None:
        fautifs = [
            nom
            for nom in _imports(chemin)
            if any(nom == banni or nom.startswith(f"{banni}.") for banni in BANNIES_DANS_ENGINE)
        ]
        assert not fautifs, f"{chemin.name} importe {fautifs}"


class TestConventions:
    @pytest.mark.parametrize("chemin", _modules(), ids=lambda p: str(p.name))
    def test_chaque_module_reporte_ses_annotations(self, chemin: Path) -> None:
        """``from __future__ import annotations`` : la compatibilité 3.9 en dépend."""
        if chemin.name == "__init__.py" and chemin.read_text(encoding="utf-8").strip() == "":
            return
        contenu = chemin.read_text(encoding="utf-8")
        assert "from __future__ import annotations" in contenu, chemin.name

    @pytest.mark.parametrize("chemin", _modules(), ids=lambda p: str(p.name))
    def test_chaque_module_porte_une_docstring(self, chemin: Path) -> None:
        contenu = chemin.read_text(encoding="utf-8")
        if chemin.name == "__init__.py" and contenu.strip() == "":
            return
        arbre = ast.parse(contenu, filename=str(chemin))
        assert ast.get_docstring(arbre), chemin.name

    def test_cfd_plot_n_est_atteint_que_par_le_sas_prevu(self) -> None:
        """Un import direct rendrait le paquet inutilisable sans cfd-plot.

        Le contrôle doit tourner sur un calculateur isolé où seules les
        dépendances déclarées sont présentes.
        """
        fautifs = [
            chemin.name
            for chemin in _modules()
            if chemin.name != "_plotting_lib.py"
            and any(nom.startswith("cfd_plot") for nom in _imports(chemin))
        ]
        assert not fautifs
