"""Interface en ligne de commande."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from cfd_doe.cli.main import main
from cfd_doe.paths import EXEMPLE_DIR

EXEMPLE = str(EXEMPLE_DIR / "ETUDE_FUSEE.yaml")


def test_domaine_sur_l_exemple(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["domaine", EXEMPLE]) == 0
    sortie = capsys.readouterr().out
    assert "Sous-domaines à calculer (8)" in sortie
    assert "divisé par 8" in sortie


def test_options_seules(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "domaine",
            "--traj",
            "3DOF_TANGAGE",
            "--sym",
            "double_symetrie",
            "--alpha",
            "-20",
            "20",
            "--dm",
            "-20",
            "20",
        ]
    )
    assert code == 0
    assert "Sous-domaines à calculer (2)" in capsys.readouterr().out


def test_option_prime_sur_le_fichier(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["domaine", EXEMPLE, "--repere", "cartesien"]) == 0
    sortie = capsys.readouterr().out
    assert "cartésien" in sortie
    assert "non exploitées" in sortie


@pytest.mark.parametrize("suffixe", [".yaml", ".json"])
def test_export(tmp_path: Path, suffixe: str) -> None:
    chemin = tmp_path / f"sd{suffixe}"
    assert main(["domaine", EXEMPLE, "--export", str(chemin)]) == 0
    texte = chemin.read_text(encoding="utf-8")
    donnees = json.loads(texte) if suffixe == ".json" else yaml.safe_load(texte)
    assert donnees["repere"] == "polaire"
    assert len(donnees["sous_domaines"]) == 8


def test_erreur_d_entree_code_1(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as sortie:
        main(["domaine", "--traj", "6DOF"])
    assert sortie.value.code == 1
    assert "erreur" in capsys.readouterr().err


def test_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", EXEMPLE]) == 0
    assert "✓" in capsys.readouterr().out


def test_exemple(tmp_path: Path) -> None:
    destination = tmp_path / "ex"
    assert main(["exemple", str(destination)]) == 0
    assert (destination / "ETUDE_FUSEE.yaml").is_file()
    with pytest.raises(SystemExit):
        main(["exemple", str(destination)])


def test_verbose_ajoute_la_demarche(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["domaine", EXEMPLE, "--verbose"]) == 0
    sortie = capsys.readouterr().out
    assert "Démarche" in sortie
    assert "4. Découpage en domaine fondamental" in sortie
    assert "→ #8" in sortie
    assert "Sous-domaines à calculer (8)" in sortie
    assert main(["domaine", EXEMPLE, "-v"]) == 0
    assert "Démarche" in capsys.readouterr().out


def test_sans_verbose_pas_de_demarche(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["domaine", EXEMPLE]) == 0
    assert "Démarche" not in capsys.readouterr().out
