"""La ligne de commande.

Deux exigences de fond :

* **aucune trace d'appels** ne remonte à l'utilisateur. Le public est un
  ingénieur qui a écrit le Fortran, pas un développeur Python qui déboguerait
  cet outil ;
* les codes de retour distinguent l'erreur d'entrée (1) du résultat qui exige
  une action (2). Un script d'intégration continue en dépend.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cfd_validation.cli.main import build_parser, main
from cfd_validation.paths import EXEMPLE_DIR


@pytest.fixture
def tables(tmp_path: Path) -> Path:
    """Le fichier de tables de l'exemple, recopié là où le test travaille."""
    chemin = tmp_path / "TABLES.yaml"
    chemin.write_text((EXEMPLE_DIR / "TABLES.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    return chemin


@pytest.fixture
def atelier(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tables: Path) -> Path:
    """Un répertoire de travail portant le module et le modèle de l'exemple."""
    for nom in ("aero_factice.py", "mon_modele.py"):
        (tmp_path / nom).write_text(
            (EXEMPLE_DIR / nom).read_text(encoding="utf-8"), encoding="utf-8"
        )
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestAnalyseur:
    def test_l_analyseur_se_construit_seul(self) -> None:
        """Il est testable sans lancer une commande."""
        assert build_parser().prog == "cfd-validation"

    def test_une_commande_est_obligatoire(self) -> None:
        with pytest.raises(SystemExit):
            main([])

    def test_la_version_sort_en_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit) as capture:
            main(["--version"])
        assert capture.value.code == 0
        assert "cfd-validation" in capsys.readouterr().out


class TestCheck:
    def test_un_fichier_valide_sort_en_zero(
        self, tables: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert main(["check", "--tables", str(tables)]) == 0
        assert "sans erreur" in capsys.readouterr().out

    def test_un_fichier_fautif_sort_en_un_sans_trace(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        chemin = tmp_path / "TABLES.yaml"
        chemin.write_text("CN:\n  colonnes: [x, CN]\n", encoding="utf-8")
        with pytest.raises(SystemExit) as capture:
            main(["check", "--tables", str(chemin)])
        assert capture.value.code == 1
        sortie = capsys.readouterr()
        assert "Traceback" not in sortie.err
        assert "bloc" in sortie.err

    def test_un_fichier_absent_sort_en_un(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as capture:
            main(["check", "--tables", str(tmp_path / "rien.yaml")])
        assert capture.value.code == 1


class TestInspecter:
    def test_les_blocs_sont_listes(self, atelier: Path, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["inspecter", "--module", "aero_factice"]) == 0
        assert "tab_cn" in capsys.readouterr().out

    def test_un_module_introuvable_sort_en_un_sans_trace(
        self, atelier: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as capture:
            main(["inspecter", "--module", "module_qui_n_existe_pas"])
        assert capture.value.code == 1
        assert "Traceback" not in capsys.readouterr().err


class TestValider:
    def test_un_modele_juste_sort_en_zero(
        self, atelier: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(
            [
                "valider",
                "--tables",
                "TABLES.yaml",
                "--module",
                "aero_factice",
                "--modele",
                "mon_modele:appeler",
            ]
        )
        assert code == 0
        assert "relues correctement" in capsys.readouterr().out

    def test_un_modele_fautif_sort_en_deux(
        self, atelier: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """2 et non 1 : la commande a abouti, c'est son résultat qui exige une action."""
        (atelier / "casse.py").write_text(
            "from cfd_validation.wrap.factice import ModeleFactice, module_factice\n"
            "appeler = ModeleFactice(module_factice(), bug='echelle')\n",
            encoding="utf-8",
        )
        code = main(
            [
                "valider",
                "--tables",
                "TABLES.yaml",
                "--module",
                "aero_factice",
                "--modele",
                "casse:appeler",
            ]
        )
        assert code == 2
        sortie = capsys.readouterr().out
        assert "des écarts subsistent" in sortie
        # Le rapport remplace les soulignés par des espaces, et la console de
        # test fait 80 colonnes : on cherche le mot, pas la mise en page.
        assert "facteur" in sortie

    def test_un_modele_non_appelable_sort_en_un(
        self, atelier: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (atelier / "pas_une_fonction.py").write_text("appeler = 42\n", encoding="utf-8")
        with pytest.raises(SystemExit) as capture:
            main(
                [
                    "valider",
                    "--tables",
                    "TABLES.yaml",
                    "--module",
                    "aero_factice",
                    "--modele",
                    "pas_une_fonction:appeler",
                ]
            )
        assert capture.value.code == 1
        assert "appelable" in capsys.readouterr().err

    def test_un_attribut_absent_liste_ce_que_le_module_porte(
        self, atelier: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as capture:
            main(
                [
                    "valider",
                    "--tables",
                    "TABLES.yaml",
                    "--module",
                    "aero_factice",
                    "--modele",
                    "mon_modele:inexistante",
                ]
            )
        assert capture.value.code == 1
        assert "appeler" in capsys.readouterr().err

    def test_le_trace_a_blanc_n_ecrit_rien(
        self, atelier: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        pytest.importorskip("cfd_plot")
        code = main(
            [
                "valider",
                "--tables",
                "TABLES.yaml",
                "--module",
                "aero_factice",
                "--modele",
                "mon_modele:appeler",
                "--figures",
                "FIGURE",
                "--a-blanc",
                "--max-valeurs",
                "2",
            ]
        )
        assert code == 0
        assert not list((atelier / "FIGURE").rglob("*.png"))
        assert "seraient écrites" in capsys.readouterr().out

    def test_max_valeurs_zero_vaut_toutes_les_valeurs(self, atelier: Path) -> None:
        """argparse ne sait pas dire None sur la ligne de commande."""
        args = build_parser().parse_args(
            ["valider", "--tables", "T", "--module", "m", "--modele", "a:b", "--max-valeurs", "0"]
        )
        assert args.max_valeurs == 0  # avant traduction
        # `main` traduit 0 en None avant d'appeler la sous-commande.


class TestToolchain:
    def test_la_commande_rapporte_l_etat_sans_lever(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(["toolchain"])
        assert code in {0, 2}
        assert "moteur f2py" in capsys.readouterr().out


class TestConstruire:
    def test_une_source_absente_sort_en_un_sans_trace(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with pytest.raises(SystemExit) as capture:
            main(["construire", str(tmp_path / "rien.f")])
        assert capture.value.code == 1
        sortie = capsys.readouterr()
        assert "Traceback" not in sortie.err
        assert "toolchain" in sortie.err  # l'indice dit où regarder


class TestExemple:
    def test_l_exemple_se_recopie(self, tmp_path: Path) -> None:
        destination = tmp_path / "essai"
        assert main(["exemple", str(destination)]) == 0
        assert (destination / "RUN_EXEMPLE.sh").exists()
        assert (destination / "TABLES.yaml").exists()
        assert (destination / "MODELE_FORTRAN" / "aero.f").exists()

    def test_un_repertoire_non_vide_est_refuse(self, tmp_path: Path) -> None:
        """Recopier par-dessus écraserait le travail de quelqu'un."""
        destination = tmp_path / "occupe"
        destination.mkdir()
        (destination / "deja.txt").write_text("là", encoding="utf-8")
        with pytest.raises(SystemExit) as capture:
            main(["exemple", str(destination)])
        assert capture.value.code == 1

    def test_les_artefacts_ne_sont_pas_recopies(self, tmp_path: Path) -> None:
        destination = tmp_path / "propre"
        main(["exemple", str(destination)])
        assert not list(destination.rglob("__pycache__"))
        assert not list(destination.rglob("*.so"))
