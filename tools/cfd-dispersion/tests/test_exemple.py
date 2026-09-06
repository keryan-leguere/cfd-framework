"""L'exemple livré doit tourner tel quel."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from cfd_dispersion.core.lois import JeuDeLois
from cfd_dispersion.paths import EXEMPLE_DIR

FICHIERS = (
    "README.md",
    "LOIS.yaml",
    "modele.py",
    "01_tirage.py",
    "02_monte_carlo.py",
    "03_polaire_batch_plot.py",
    "04_bande_et_correlation.py",
    "05_modele_croise.py",
    "RUN_EXEMPLE.sh",
)


class TestContenu:
    @pytest.mark.parametrize("nom", FICHIERS)
    def test_le_fichier_est_livre_avec_le_paquet(self, nom: str) -> None:
        """Package data : ``pip install cfd-dispersion`` doit suffire."""
        assert (EXEMPLE_DIR / nom).is_file()

    def test_les_lois_de_l_exemple_se_chargent(self) -> None:
        from cfd_dispersion import charger_lois_yaml

        lois = charger_lois_yaml(EXEMPLE_DIR / "LOIS.yaml")
        assert list(lois) == ["CN", "CA", "Cm_alpha"]


class TestModele:
    def test_le_modele_rend_une_ligne_par_point_de_vol_et_tirage(self) -> None:
        modele = _modele()
        lois = _lois()
        resultats = modele.appeler_modele(lois, n=50)
        assert len(resultats) == 50 * len(modele.POINTS_DE_VOL)
        assert {"Mach", "Altitude_m", "CN", "CN_Biais", "CN_FE"} <= set(resultats.columns)

    def test_le_defaut_volontaire_est_bien_la(self) -> None:
        """Un exemple où tout passe ne prouverait rien."""
        from cfd_dispersion import valider_lot

        modele = _modele()
        lois = _lois()
        verdicts = valider_lot(modele.appeler_modele(lois, n=600), lois, par=("Mach", "Altitude_m"))
        rejets = verdicts.loc[~verdicts["valide"]]
        assert len(rejets) == 1
        coefficient, composante = modele.COMPOSANTE_FAUTIVE
        assert rejets.iloc[0]["coefficient"] == coefficient
        assert rejets.iloc[0]["composante"] == composante
        assert rejets.iloc[0]["Mach"] == modele.PDV_FAUTIF

    def test_sans_le_defaut_tout_est_valide(self) -> None:
        from cfd_dispersion import valider_lot

        modele = _modele()
        lois = _lois()
        verdicts = valider_lot(
            modele.appeler_modele(lois, n=600, fausser=False),
            lois,
            par=("Mach", "Altitude_m"),
        )
        assert verdicts["valide"].all()

    def test_le_modele_polaire_rend_un_balayage_par_tirage(self) -> None:
        import numpy as np

        modele = _modele()
        alpha = np.linspace(0.0, 12.0, 15)
        a_plat = modele.appeler_modele_polaire(_lois(), alpha, n=20)
        assert len(a_plat) == 20 * alpha.size

        from cfd_dispersion.figures.polaire import courbes_par_tirage

        _, courbes = courbes_par_tirage(a_plat, x="alpha", y="CN", par=["tirage"])
        assert courbes.shape == (20, alpha.size)


class TestExecution:
    """Les scripts tournent réellement, dans un répertoire temporaire."""

    def _lancer(self, script: str, tmp_path: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(EXEMPLE_DIR / script), "--sortie", str(tmp_path), *extra],
            capture_output=True,
            text=True,
            check=False,
            cwd=str(EXEMPLE_DIR),
        )

    def test_01_tirage(self, tmp_path: Path) -> None:
        resultat = self._lancer("01_tirage.py", tmp_path, "-n", "50")
        assert resultat.returncode == 0, resultat.stderr
        assert (tmp_path / "lot.csv").is_file()
        # Trois coefficients, celui sans valeur nominale, la matrice qui les
        # empile, et ses deux pages forcées : sept SVG, écrits par les figures
        # elles-mêmes.
        assert len(list(tmp_path.glob("tirage_*.svg"))) == 7
        assert (tmp_path / "tirage_sans_nominal.svg").is_file()
        assert (tmp_path / "tirage_pagine_02.svg").is_file()
        assert len(pd.read_csv(tmp_path / "lot.csv")) == 50

    def test_02_monte_carlo(self, tmp_path: Path) -> None:
        resultat = self._lancer("02_monte_carlo.py", tmp_path, "-n", "300")
        assert resultat.returncode == 0, resultat.stderr
        assert (tmp_path / "synthese.png").is_file()
        assert (tmp_path / "verdicts.csv").is_file()
        assert (tmp_path / "synthese.csv").is_file()
        # Le défaut volontaire doit ressortir, et déclencher des figures.
        assert "rejeté" in resultat.stdout
        assert list(tmp_path.glob("mc_*.png"))
        assert list(tmp_path.glob("qq_*.png"))

    def test_02_ne_perd_pas_de_figure_dans_un_nom_pointe(self, tmp_path: Path) -> None:
        """Un point de vol s'appelle « Mach0.85 », et le point compte.

        ``save_figure`` compose son fichier par ``with_suffix`` : sans
        précaution, ``mc_Mach0.85_..._CN`` devient ``mc_Mach0.png`` et les
        trois coefficients s'écrasent dans un seul fichier, sans rien dire.
        """
        resultat = self._lancer("02_monte_carlo.py", tmp_path, "-n", "300")
        assert resultat.returncode == 0, resultat.stderr
        figures = sorted(p.name for p in tmp_path.glob("mc_*.png"))
        assert len(figures) == 3, figures
        assert all("0.85" in nom for nom in figures), figures

    def test_03_polaire_batch_plot(self, tmp_path: Path) -> None:
        pytest.importorskip("cfd_plot", reason="cet exemple exige cfd-plot")
        resultat = self._lancer("03_polaire_batch_plot.py", tmp_path, "-n", "40")
        assert resultat.returncode == 0, resultat.stderr
        assert list(tmp_path.rglob("*_vs_alpha.png"))
        # La voie directe, sans batch_plot, doit sortir elle aussi.
        assert (tmp_path / "polaire_directe_CN.png").is_file()

    def test_05_modele_croise(self, tmp_path: Path) -> None:
        pytest.importorskip("cfd_plot", reason="les polaires exigent cfd-plot")
        resultat = self._lancer("05_modele_croise.py", tmp_path, "-n", "60")
        assert resultat.returncode == 0, resultat.stderr
        assert (tmp_path / "sortie_modele.csv").is_file()
        assert (tmp_path / "verdicts.csv").is_file()
        assert (tmp_path / "synthese.png").is_file()
        # Une polaire par point de vol, et la cle par PDV du hook.
        assert len(list(tmp_path.rglob("*_vs_alpha.png"))) == 6

    def test_06_tirages_par_pdv(self, tmp_path: Path) -> None:
        """Le parcours des points de vol, en tout petit : chaque figure coûte."""
        resultat = self._lancer(
            "06_tirages_par_pdv.py", tmp_path, "-n", "6", "--max-tirages", "1", "--jobs", "1"
        )
        assert resultat.returncode == 0, resultat.stderr
        assert (tmp_path / "INVENTAIRE_TIRAGES.csv").is_file()

        inventaire = pd.read_csv(tmp_path / "INVENTAIRE_TIRAGES.csv")
        # 4 points de vol × 1 tirage × (3 coefficients + 1 matrice).
        assert len(inventaire) == 16
        assert set(inventaire["figure"]) == {"CN", "CA", "Cm_alpha", "matrice"}
        assert (tmp_path / "TIRAGES" / "M_0.7" / "Z_0" / "tirage_000" / "matrice.svg").is_file()

    def test_la_sortie_de_modele_ecrite_en_dur(self, tmp_path: Path) -> None:
        """L'exemple de tableau : 4 PDV × n tirages, le même lot partout."""
        resultat = self._lancer("sortie_modele.py", tmp_path, "-n", "10")
        assert resultat.returncode == 0, resultat.stderr

        table = pd.read_csv(tmp_path / "SORTIE_MODELE.csv")
        assert len(table) == 4 * 10
        assert {"DICT_LAW_DISPERSION", "DICT_TIRAGE", "tirage", "CN_nominal"} <= set(table.columns)
        # Le tirage 3 est le même aux quatre points de vol.
        assert table.loc[table["tirage"] == 3, "DICT_TIRAGE"].nunique() == 1

    def test_04_bande_et_correlation(self, tmp_path: Path) -> None:
        resultat = self._lancer("04_bande_et_correlation.py", tmp_path, "-n", "400")
        assert resultat.returncode == 0, resultat.stderr
        for nom in (
            "correle_vs_independant.png",
            "remplissages.png",
            "correlation_coefficients.png",
        ):
            assert (tmp_path / nom).is_file(), nom


class TestModeleCroise:
    """La forme d'un vrai modèle : listes croisées, colonnes dictionnaires."""

    def test_le_tableau_porte_les_deux_dictionnaires(self) -> None:
        modele = _modele()
        df = modele.appeler_modele_croise(
            _lois(), L_MACH=[0.7, 0.85], L_ALTITUDE=[8000.0], L_ALPHA=[0.0, 4.0], n=10
        )
        assert len(df) == 10 * 2 * 1 * 2
        assert {"DICT_LAW_DISPERSION", "DICT_TIRAGE"} <= set(df.columns)
        # Les métadonnées du solveur voyagent avec.
        assert {"version_solveur", "table_aero", "convergence"} <= set(df.columns)

    def test_le_meme_tirage_sert_a_tout_le_balayage(self) -> None:
        """C'est le cas physique — et ce qui impose de dédoublonner."""
        from cfd_dispersion import lire_sortie_modele

        modele = _modele()
        df = modele.appeler_modele_croise(
            _lois(), L_MACH=[0.7], L_ALTITUDE=[8000.0], L_ALPHA=[0.0, 4.0, 8.0], n=12
        )
        resultats, _ = lire_sortie_modele(df)
        assert len(resultats) == 12 * 3
        assert resultats["tirage"].nunique() == 12

    def test_les_lois_se_relisent_depuis_le_tableau(self) -> None:
        from cfd_dispersion import lire_sortie_modele

        modele = _modele()
        df = modele.appeler_modele_croise(
            _lois(), L_MACH=[0.7], L_ALTITUDE=[8000.0], L_ALPHA=[0.0, 4.0], n=5
        )
        _, relues = lire_sortie_modele(df)
        assert list(relues) == list(_lois())
        assert relues["CN"].biais.ET == pytest.approx(_lois()["CN"].biais.ET)

    def test_le_defaut_volontaire_ressort_apres_dedoublonnage(self) -> None:
        from cfd_dispersion import lire_sortie_modele, valider_lot

        modele = _modele()
        df = modele.appeler_modele_croise(
            _lois(),
            L_MACH=[0.70, 0.85],
            L_ALTITUDE=[8000.0],
            L_ALPHA=[0.0, 4.0, 8.0],
            n=600,
        )
        resultats, lois = lire_sortie_modele(df)
        verdicts = valider_lot(resultats, lois, par=("Mach", "Altitude_m"), unique_par=("tirage",))
        assert set(verdicts["n"]) == {600}
        rejets = verdicts.loc[~verdicts["valide"]]
        assert len(rejets) == 1
        coefficient, composante = modele.COMPOSANTE_FAUTIVE
        assert rejets.iloc[0]["coefficient"] == coefficient
        assert rejets.iloc[0]["composante"] == composante
        assert rejets.iloc[0]["Mach"] == modele.PDV_FAUTIF


def _modele() -> Any:
    """Importe le modèle jouet livré avec l'exemple."""
    import importlib.util

    specification = importlib.util.spec_from_file_location(
        "_modele_exemple", EXEMPLE_DIR / "modele.py"
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _lois() -> JeuDeLois:
    from cfd_dispersion import charger_lois_yaml

    return charger_lois_yaml(EXEMPLE_DIR / "LOIS.yaml")
