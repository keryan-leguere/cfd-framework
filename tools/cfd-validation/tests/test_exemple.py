"""L'exemple livré : il doit tourner, et dire ce qu'il prétend dire.

Un exemple faux est pire qu'aucun exemple : c'est la première chose que le
lecteur copie. Les scripts sont donc exécutés pour de vrai, en sous-processus,
depuis une copie neuve — exactement ce que produit ``cfd-validation exemple``.

Le script Fortran (``05``) est lancé lui aussi : il est écrit pour s'arrêter
proprement en code 0 quand la chaîne de compilation est incomplète, et c'est
précisément ce comportement qu'on veut voir tenu.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from cfd_validation.paths import EXEMPLE_DIR, FORTRAN_DIR


@pytest.fixture(scope="module")
def copie(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Une copie neuve de l'exemple, comme la CLI la produit."""
    destination = tmp_path_factory.mktemp("exemple")
    shutil.copytree(
        EXEMPLE_DIR,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "SORTIE", "*.pyc", "*.so", "*.mod"),
    )
    return destination


def _lancer(copie: Path, script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, script, *arguments],
        cwd=copie,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


class TestFichiers:
    def test_l_exemple_porte_tout_ce_qu_il_annonce(self) -> None:
        for nom in (
            "README.md",
            "RUN_EXEMPLE.sh",
            "TABLES.yaml",
            "aero_factice.py",
            "mon_modele.py",
            "01_lire_table.py",
            "02_valider.py",
            "03_diagnostics.py",
            "04_figures_batch_plot.py",
            "05_fortran_reel.py",
        ):
            assert (EXEMPLE_DIR / nom).exists(), nom

    def test_le_jumeau_fortran_est_livre(self) -> None:
        assert (FORTRAN_DIR / "aero.f").exists()

    def test_le_source_fortran_est_en_ascii_pur(self) -> None:
        """f2py lit le Fortran en ASCII et échoue sur le premier octet accentué.

        Le message qu'il produit alors parle de codec, jamais du fichier.
        """
        octets = (FORTRAN_DIR / "aero.f").read_bytes()
        assert all(octet < 128 for octet in octets)

    def test_le_lanceur_n_appelle_pas_le_script_console(self) -> None:
        """pip grave ``sys.executable`` dans son shebang, et ce chemin peut être faux."""
        contenu = (EXEMPLE_DIR / "RUN_EXEMPLE.sh").read_text(encoding="utf-8")
        assert "CFD_VALIDATION_PYTHON" in contenu
        assert "python3" in contenu


class TestExecution:
    def test_01_lit_les_tables(self, copie: Path) -> None:
        acheve = _lancer(copie, "01_lire_table.py")
        assert acheve.returncode == 0, acheve.stderr
        assert "294" in acheve.stdout  # les lignes réellement renseignées
        assert "320" in acheve.stdout  # et la capacité du tableau

    def test_02_sort_vert_sur_un_modele_juste(self, copie: Path) -> None:
        """Le cœur de la promesse : un code juste ne déclenche rien."""
        acheve = _lancer(copie, "02_valider.py")
        assert acheve.returncode == 0, acheve.stderr
        assert "relues correctement" in acheve.stdout

    def test_03_retrouve_chaque_motif(self, copie: Path) -> None:
        acheve = _lancer(copie, "03_diagnostics.py")
        assert acheve.returncode == 0, acheve.stderr
        assert "✗" not in acheve.stdout, "un motif n'a pas été retrouvé"
        assert acheve.stdout.count("✓") >= 8

    def test_04_annonce_puis_ecrit_les_memes_planches(self, copie: Path) -> None:
        pytest.importorskip("cfd_plot")
        a_blanc = _lancer(copie, "04_figures_batch_plot.py", "--a-blanc")
        assert a_blanc.returncode == 0, a_blanc.stderr
        assert "seraient écrits" in a_blanc.stdout
        assert not list((copie / "SORTIE").rglob("*.png"))

        reel = _lancer(copie, "04_figures_batch_plot.py")
        assert reel.returncode == 0, reel.stderr
        assert len(list((copie / "SORTIE").rglob("*.png"))) == 85

    def test_05_s_arrete_proprement_sans_chaine_de_compilation(self, copie: Path) -> None:
        """Il doit sortir en 0 et le dire, pas échouer : le reste n'en dépend pas."""
        acheve = _lancer(copie, "05_fortran_reel.py")
        assert acheve.returncode == 0, acheve.stderr
        assert "Chaîne de compilation" in acheve.stdout


class TestDocumentation:
    def test_le_readme_de_l_exemple_cite_chaque_script(self) -> None:
        contenu = (EXEMPLE_DIR / "README.md").read_text(encoding="utf-8")
        for script in (
            "01_lire_table.py",
            "02_valider.py",
            "03_diagnostics.py",
            "04_figures_batch_plot.py",
            "05_fortran_reel.py",
        ):
            assert script in contenu, script
