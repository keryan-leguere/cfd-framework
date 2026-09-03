"""La commande ``cfd-dispersion``."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from cfd_dispersion.cli.main import build_parser, main
from cfd_dispersion.core.lois import JeuDeLois
from cfd_dispersion.core.tirage import tirer_lot
from cfd_dispersion.paths import EXEMPLE_DIR

LOIS_EXEMPLE = EXEMPLE_DIR / "LOIS.yaml"


class TestAnalyseur:
    def test_les_quatre_sous_commandes_existent(self) -> None:
        parser = build_parser()
        for commande in ("check", "tirage", "valider", "exemple"):
            assert parser.parse_args([commande, *_arguments_minimaux(commande)])

    def test_une_sous_commande_est_obligatoire(self) -> None:
        with pytest.raises(SystemExit):
            build_parser().parse_args([])

    def test_version(self) -> None:
        with pytest.raises(SystemExit) as sortie:
            main(["--version"])
        assert sortie.value.code == 0


def _arguments_minimaux(commande: str) -> list[str]:
    if commande in ("check", "tirage"):
        return ["--lois", str(LOIS_EXEMPLE)]
    if commande == "valider":
        return ["--lois", str(LOIS_EXEMPLE), "--donnees", "x.csv"]
    return []


class TestCheck:
    def test_valide_le_fichier_livre(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["check", "--lois", str(LOIS_EXEMPLE)]) == 0
        assert "sans erreur" in capsys.readouterr().out

    def test_un_fichier_absent_sort_en_erreur(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit) as sortie:
            main(["check", "--lois", str(tmp_path / "absent.yaml")])
        assert sortie.value.code == 1

    def test_un_fichier_fautif_sort_en_erreur_sans_trace(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Le public est un ingénieur, pas un développeur qui débogue l'outil."""
        mauvais = tmp_path / "LOIS.yaml"
        mauvais.write_text("CN:\n  Biais_Type: 4\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            main(["check", "--lois", str(mauvais)])
        assert "Traceback" not in capsys.readouterr().err


class TestTirage:
    def test_un_tirage_unique(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert main(["tirage", "--lois", str(LOIS_EXEMPLE), "--graine", "1"]) == 0
        assert "Tirage" in capsys.readouterr().out

    def test_un_lot_ecrit_en_csv(self, tmp_path: Path) -> None:
        sortie = tmp_path / "lot.csv"
        assert (
            main(["tirage", "--lois", str(LOIS_EXEMPLE), "-n", "50", "--sortie", str(sortie)]) == 0
        )
        assert len(pd.read_csv(sortie)) == 50

    @pytest.mark.parametrize("methode", ["mc", "lhs", "sobol"])
    def test_les_trois_plans(self, tmp_path: Path, methode: str) -> None:
        sortie = tmp_path / "lot.csv"
        assert (
            main(
                [
                    "tirage",
                    "--lois",
                    str(LOIS_EXEMPLE),
                    "-n",
                    "40",
                    "--methode",
                    methode,
                    "--sortie",
                    str(sortie),
                ]
            )
            == 0
        )
        assert len(pd.read_csv(sortie)) == 40

    def test_les_figures_sont_ecrites(self, tmp_path: Path) -> None:
        assert (
            main(
                ["tirage", "--lois", str(LOIS_EXEMPLE), "--graine", "1", "--figures", str(tmp_path)]
            )
            == 0
        )
        assert sorted(p.name for p in tmp_path.glob("*.png")) == [
            "tirage_CA.png",
            "tirage_CN.png",
            "tirage_Cm_alpha.png",
        ]


class TestValider:
    @pytest.fixture
    def donnees(self, tmp_path: Path, lois_exemple: JeuDeLois) -> Path:
        # Graine fixée et vérifiée conforme : ces tests portent sur la
        # plomberie de la commande, pas sur la statistique — dont la
        # calibration est éprouvée dans tests/core/test_validation.py.
        morceaux = []
        for indice, mach in enumerate([0.7, 0.85]):
            lot = tirer_lot(lois_exemple, 400, graine=indice)
            lot["Mach"] = mach
            morceaux.append(lot)
        chemin = tmp_path / "resultats.csv"
        pd.concat(morceaux, ignore_index=True).to_csv(chemin, index=False)
        return chemin

    @pytest.fixture
    def lois_exemple(self) -> JeuDeLois:
        from cfd_dispersion import charger_lois_yaml

        return charger_lois_yaml(LOIS_EXEMPLE)

    def test_un_tirage_conforme_est_valide(
        self, donnees: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        code = main(
            ["valider", "--lois", str(LOIS_EXEMPLE), "--donnees", str(donnees), "--par", "Mach"]
        )
        assert code == 0
        assert "Tous les points de vol sont validés" in capsys.readouterr().out

    def test_les_verdicts_sont_ecrits(self, donnees: Path, tmp_path: Path) -> None:
        sortie = tmp_path / "verdicts.csv"
        main(
            [
                "valider",
                "--lois",
                str(LOIS_EXEMPLE),
                "--donnees",
                str(donnees),
                "--par",
                "Mach",
                "--sortie",
                str(sortie),
            ]
        )
        verdicts = pd.read_csv(sortie)
        assert {"coefficient", "composante", "valide", "motif"} <= set(verdicts.columns)

    def test_la_figure_de_synthese_est_ecrite(self, donnees: Path, tmp_path: Path) -> None:
        figures = tmp_path / "FIG"
        main(
            [
                "valider",
                "--lois",
                str(LOIS_EXEMPLE),
                "--donnees",
                str(donnees),
                "--par",
                "Mach",
                "--figures",
                str(figures),
            ]
        )
        assert (figures / "synthese.png").is_file()

    def test_un_fichier_de_donnees_absent_sort_en_erreur(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit):
            main(
                ["valider", "--lois", str(LOIS_EXEMPLE), "--donnees", str(tmp_path / "absent.csv")]
            )

    def test_une_colonne_de_groupement_absente_sort_en_erreur(self, donnees: Path) -> None:
        with pytest.raises(SystemExit):
            main(
                [
                    "valider",
                    "--lois",
                    str(LOIS_EXEMPLE),
                    "--donnees",
                    str(donnees),
                    "--par",
                    "Regime",
                ]
            )

    def test_correction_aucune_est_acceptee(self, donnees: Path) -> None:
        assert (
            main(
                [
                    "valider",
                    "--lois",
                    str(LOIS_EXEMPLE),
                    "--donnees",
                    str(donnees),
                    "--par",
                    "Mach",
                    "--correction",
                    "aucune",
                ]
            )
            == 0
        )

    def test_strict_sort_en_un_quand_un_point_de_vol_est_rejete(
        self, tmp_path: Path, lois_exemple: JeuDeLois
    ) -> None:
        from cfd_dispersion import charger_lois

        faux = charger_lois(
            {
                "CN": {
                    "Biais_Type": 5,
                    "Biais_M": 0.0,
                    "Biais_ET": 0.08,
                    "FE_Type": 6,
                    "FE_M": 1.0,
                    "FE_ET": 0.32,
                },
                "CA": {
                    "Biais_Type": 2,
                    "Biais_M": 0.001,
                    "Biais_ET": 0.0,
                    "FE_Type": 3,
                    "FE_M": 1.0,
                    "FE_ET": 0.05,
                },
                "Cm_alpha": {
                    "Biais_Type": 5,
                    "Biais_M": 0.0,
                    "Biais_ET": 0.015,
                    "FE_Type": 4,
                    "FE_M": 1.0,
                    "FE_ET": 0.10,
                },
            }
        )
        lot = tirer_lot(faux, 500, graine=3)
        lot["Mach"] = 0.8
        chemin = tmp_path / "faux.csv"
        lot.to_csv(chemin, index=False)

        code = main(
            [
                "valider",
                "--lois",
                str(LOIS_EXEMPLE),
                "--donnees",
                str(chemin),
                "--par",
                "Mach",
                "--strict",
            ]
        )
        assert code == 1


class TestExemple:
    def test_copie_l_exemple(self, tmp_path: Path) -> None:
        destination = tmp_path / "ex"
        assert main(["exemple", str(destination)]) == 0
        assert (destination / "LOIS.yaml").is_file()
        assert (destination / "RUN_EXEMPLE.sh").is_file()
        assert (destination / "01_tirage.py").is_file()

    def test_refuse_un_repertoire_non_vide(self, tmp_path: Path) -> None:
        destination = tmp_path / "ex"
        destination.mkdir()
        (destination / "quelque_chose").write_text("x", encoding="utf-8")
        with pytest.raises(SystemExit):
            main(["exemple", str(destination)])


class TestCommandeInstallee:
    def test_python_m_cfd_dispersion_fonctionne(self) -> None:
        """Le script console de pip fige le chemin de l'interpréteur ; pas ``-m``."""
        resultat = subprocess.run(
            [sys.executable, "-m", "cfd_dispersion.cli.main", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert resultat.returncode == 0
        assert "cfd-dispersion" in resultat.stdout
