"""Command-line behaviour: exit codes, refusals, and what lands on screen.

Exit code 2 is not a failure — it means the calculation ran but at least one
extrapolation outside the measured domain was reported. A script that budgets
drag can treat it as "look at the warnings"; `|| true` would hide exactly the
thing worth seeing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cfd_aq.cli.main import CODE_ERREUR_ENTREE, CODE_HORS_DOMAINE, CODE_OK, main
from cfd_aq.core.atmosphere import HAS_CFD_ATM
from cfd_aq.paths import EXEMPLE_DIR

CAS = str(EXEMPLE_DIR / "CAS_VOILURE.yaml")


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as sortie:
        main(["--version"])
    assert sortie.value.code == 0
    assert "cfd-aq" in capsys.readouterr().out


def test_ratio(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ratio", "--h-plus", "500", "--mach", "0.8"]) == CODE_OK
    sortie = capsys.readouterr().out
    assert "Marche montante" in sortie
    assert "Arête" in sortie


def test_ratio_hors_domaine_sort_en_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ratio", "--h-plus", "50000", "--mach", "0.8"]) == CODE_HORS_DOMAINE
    assert "Hors du domaine" in capsys.readouterr().out


def test_ratio_affiche_la_table_dediee_a_t_egal_2h(capsys: pytest.CaptureFixture[str]) -> None:
    main(["ratio", "--h-plus", "500", "--mach", "0.8", "--t-sur-h", "2"])
    assert "table dédiée" in capsys.readouterr().out


def test_marche(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1.5e-3",
            "--envergure",
            "2.4",
            "--altitude",
            "11000",
            "--mach",
            "0.82",
            "--x",
            "10",
            "--surface-reference",
            "122.6",
        ]
    )
    assert code == CODE_OK
    sortie = capsys.readouterr().out
    assert "ΔD" in sortie
    assert "ΔCx" in sortie
    assert "h⁺" in sortie


def test_marche_avec_conditions_statiques(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "marche",
            "--type",
            "arete",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--temperature",
            "220",
            "--pression",
            "25000",
            "--mach",
            "0.7",
            "--cf",
            "0.0016",
        ]
    )
    assert code == CODE_OK
    assert "t/h" in capsys.readouterr().out


def test_marche_par_cisaillement(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "marche",
            "--type",
            "descendante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--altitude",
            "0",
            "--mach",
            "0.3",
            "--tau",
            "20.0",
        ]
    )
    assert code == CODE_OK
    assert "τ_w" in capsys.readouterr().out


def test_marche_sans_couche_limite_refusee(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--altitude",
            "11000",
            "--mach",
            "0.82",
        ]
    )
    assert code == CODE_ERREUR_ENTREE
    assert "exactement une description" in capsys.readouterr().out


def test_marche_avec_deux_couches_limites_refusee(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--altitude",
            "11000",
            "--mach",
            "0.82",
            "--x",
            "10",
            "--cf",
            "0.0016",
        ]
    )
    assert code == CODE_ERREUR_ENTREE
    assert "exactement une description" in capsys.readouterr().out


def test_marche_sans_conditions_refusee(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--mach",
            "0.82",
            "--x",
            "10",
        ]
    )
    assert code == CODE_ERREUR_ENTREE
    assert "Conditions locales manquantes" in capsys.readouterr().out


def test_marche_altitude_et_statiques_refusees(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--altitude",
            "11000",
            "--temperature",
            "220",
            "--mach",
            "0.82",
            "--x",
            "10",
        ]
    )
    assert code == CODE_ERREUR_ENTREE
    assert "pas les deux" in capsys.readouterr().out


def test_marche_geometrie_invalide_refusee(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--altitude",
            "11000",
            "--mach",
            "0.82",
            "--x",
            "10",
            "--rayon-sur-h",
            "0.3",
            "--chanfrein",
            "45",
        ]
    )
    assert code == CODE_ERREUR_ENTREE
    assert "arrondie" in capsys.readouterr().out


@pytest.mark.skipif(not HAS_CFD_ATM, reason="cfd-atm n'est pas installé")
def test_marche_par_vitesse_conventionnelle(capsys: pytest.CaptureFixture[str]) -> None:
    """Vc rather than Mach — the conversion goes through cfd-atm."""
    code = main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--altitude",
            "11000",
            "--vc",
            "140.437",
            "--x",
            "10",
        ]
    )
    assert code == CODE_OK
    assert "M = 0.8200" in capsys.readouterr().out


@pytest.mark.skipif(not HAS_CFD_ATM, reason="cfd-atm n'est pas installé")
def test_marche_journee_chaude(capsys: pytest.CaptureFixture[str]) -> None:
    """ISA + 20 K raises the static temperature by exactly 20 K."""
    main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--altitude",
            "11000",
            "--mach",
            "0.82",
            "--delta-isa",
            "20",
            "--x",
            "10",
        ]
    )
    assert "T = 236.77 K" in capsys.readouterr().out


@pytest.mark.skipif(not HAS_CFD_ATM, reason="cfd-atm n'est pas installé")
def test_marche_altitude_pression(capsys: pytest.CaptureFixture[str]) -> None:
    main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--altitude",
            "11000",
            "--type-altitude",
            "pression",
            "--mach",
            "0.82",
            "--x",
            "10",
        ]
    )
    assert "p = 22632.0 Pa" in capsys.readouterr().out


def test_marche_sans_vitesse_refusee(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--altitude",
            "11000",
            "--x",
            "10",
        ]
    )
    assert code == CODE_ERREUR_ENTREE
    assert "exactement une vitesse" in capsys.readouterr().out


def test_marche_deux_vitesses_refusees(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--altitude",
            "11000",
            "--mach",
            "0.8",
            "--vc",
            "140",
            "--x",
            "10",
        ]
    )
    assert code == CODE_ERREUR_ENTREE
    assert "exactement une vitesse" in capsys.readouterr().out


def test_delta_isa_sans_altitude_refuse(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--temperature",
            "220",
            "--pression",
            "25000",
            "--mach",
            "0.8",
            "--delta-isa",
            "10",
            "--cf",
            "0.0016",
        ]
    )
    assert code == CODE_ERREUR_ENTREE
    assert "n'ont de sens qu'avec --altitude" in capsys.readouterr().out


def test_le_rapport_nomme_les_paquets_freres(capsys: pytest.CaptureFixture[str]) -> None:
    main(
        [
            "marche",
            "--type",
            "montante",
            "--hauteur",
            "1e-3",
            "--envergure",
            "1.0",
            "--altitude",
            "11000",
            "--mach",
            "0.82",
            "--x",
            "10",
        ]
    )
    sortie = capsys.readouterr().out
    assert "atmosphère" in sortie
    assert "figures" in sortie


def test_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["check", CAS]) == CODE_OK
    assert "Cas valide" in capsys.readouterr().out


def test_check_fichier_absent(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    assert main(["check", str(tmp_path / "rien.yaml")]) == CODE_ERREUR_ENTREE
    assert "impossible de lire" in capsys.readouterr().out


def test_run(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["run", CAS])
    assert code in (CODE_OK, CODE_HORS_DOMAINE)
    sortie = capsys.readouterr().out
    assert "Bilan" in sortie
    assert "Total" in sortie
    assert "Couvre-joint" in sortie


def test_run_avec_figures(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    repertoire = tmp_path / "figures"
    main(["run", CAS, "--figures", str(repertoire)])
    ecrits = sorted(p.name for p in repertoire.iterdir())
    assert ecrits == [
        "01_geometries.png",
        "02_rapports_h_plus.png",
        "03_effet_mach.png",
        "04_corrections.png",
    ]
    assert all((repertoire / nom).stat().st_size > 10_000 for nom in ecrits)
    assert "Figures écrites" in capsys.readouterr().out


def test_figures(tmp_path: Path) -> None:
    assert main(["figures", str(tmp_path / "f")]) == CODE_OK
    assert len(list((tmp_path / "f").iterdir())) == 4


def test_exemple(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    destination = tmp_path / "exemple"
    assert main(["exemple", str(destination)]) == CODE_OK
    fichiers = {p.name for p in destination.iterdir()}
    assert "CAS_VOILURE.yaml" in fichiers
    assert "RUN_EXEMPLE.sh" in fichiers
    assert "Exemple copié" in capsys.readouterr().out


def test_exemple_refuse_un_repertoire_non_vide(tmp_path: Path) -> None:
    destination = tmp_path / "plein"
    destination.mkdir()
    (destination / "fichier.txt").write_text("", encoding="utf-8")
    assert main(["exemple", str(destination)]) == CODE_ERREUR_ENTREE


def test_sous_commande_obligatoire() -> None:
    with pytest.raises(SystemExit) as sortie:
        main([])
    assert sortie.value.code != 0
