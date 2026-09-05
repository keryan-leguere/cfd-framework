"""Comparaison loi prescrite / loi réalisée, et le pilote par point de vol."""

from __future__ import annotations

from collections.abc import Iterator

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from cfd_dispersion.core.lois import JeuDeLois, charger_lois
from cfd_dispersion.core.tirage import tirer_tableau
from cfd_dispersion.figures._base import nouvelle_figure
from cfd_dispersion.figures.monte_carlo import figure_comparaison, figures_par_pdv
from tests.conftest import textes_de


@pytest.fixture(autouse=True)
def _fermer_les_figures() -> Iterator[None]:
    yield
    plt.close("all")


@pytest.fixture
def sortie(lois: JeuDeLois) -> pd.DataFrame:
    """Une sortie de modèle conforme, sur deux points de vol."""
    morceaux = []
    for i, (mach, altitude) in enumerate([(0.7, 5000.0), (0.85, 10000.0)]):
        lot = tirer_tableau(lois, 400, graine=50 + i)
        lot["Mach"] = mach
        lot["Altitude_m"] = altitude
        morceaux.append(lot)
    return pd.concat(morceaux, ignore_index=True)


def _echantillons(df: pd.DataFrame, coefficient: str) -> dict[str, np.ndarray]:
    return {
        "Biais": df[f"{coefficient}_Biais"].to_numpy(),
        "FE": df[f"{coefficient}_FE"].to_numpy(),
    }


class TestFigureComparaison:
    def test_rend_trois_panneaux(self, lois: JeuDeLois, sortie: pd.DataFrame) -> None:
        _, axes = figure_comparaison(_echantillons(sortie, "Cm_alpha"), lois["Cm_alpha"])
        assert axes.shape == (3,)

    def test_superpose_la_loi_prescrite_et_l_histogramme_realise(
        self, lois: JeuDeLois, sortie: pd.DataFrame
    ) -> None:
        _, axes = figure_comparaison(_echantillons(sortie, "Cm_alpha"), lois["Cm_alpha"])
        assert axes[0].get_lines()  # la densité théorique
        assert axes[0].patches  # l'histogramme empirique

    def test_la_boite_dit_valide_quand_le_tirage_est_conforme(
        self, lois: JeuDeLois, sortie: pd.DataFrame
    ) -> None:
        figure, _ = figure_comparaison(_echantillons(sortie, "Cm_alpha"), lois["Cm_alpha"])
        textes = textes_de(figure)
        assert any("VALIDÉ" in texte for texte in textes)

    def test_la_boite_dit_rejete_et_le_motif_quand_la_loi_est_fausse(
        self, lois: JeuDeLois, table: dict[str, dict[str, float]]
    ) -> None:
        """Un ET doublé doit ressortir dans la boîte, motif compris."""
        faux = {c: dict(s) for c, s in table.items()}
        faux["Cm_alpha"]["FE_ET"] = 0.20
        lot = tirer_tableau(charger_lois(faux), 800, graine=1)

        figure, _ = figure_comparaison(_echantillons(lot, "Cm_alpha"), lois["Cm_alpha"])
        textes = textes_de(figure)
        assert any("REJETÉ" in texte for texte in textes)

    def test_le_mode_qq_remplace_la_densite(self, lois: JeuDeLois, sortie: pd.DataFrame) -> None:
        _, axes = figure_comparaison(_echantillons(sortie, "Cm_alpha"), lois["Cm_alpha"], qq=True)
        assert axes[0].collections  # le nuage de quantiles
        assert not axes[0].patches  # plus d'histogramme

    def test_le_qq_trace_la_droite_d_accord_parfait(
        self, lois: JeuDeLois, sortie: pd.DataFrame
    ) -> None:
        _, axes = figure_comparaison(_echantillons(sortie, "Cm_alpha"), lois["Cm_alpha"], qq=True)
        assert any(t.get_linestyle() == "--" for t in axes[0].get_lines())

    def test_un_echantillon_constant_ne_plante_pas(self, lois: JeuDeLois) -> None:
        """Ni histogramme ni lissage à noyau n'ont de sens sur une constante."""
        constantes = {"Biais": np.full(200, 0.001), "FE": np.full(200, 1.0)}
        _, axes = figure_comparaison(constantes, lois["CA"])
        assert axes[0].get_lines()

    def test_un_nominal_scalaire_donne_la_distribution_reconstruite(
        self, lois: JeuDeLois, sortie: pd.DataFrame
    ) -> None:
        _, axes = figure_comparaison(
            _echantillons(sortie, "Cm_alpha"), lois["Cm_alpha"], nominal=-2.5
        )
        assert axes[2].patches

    def test_un_nominal_balaye_donne_une_bande(self, lois: JeuDeLois, sortie: pd.DataFrame) -> None:
        x = np.linspace(0, 10, 15)
        _, axes = figure_comparaison(
            _echantillons(sortie, "Cm_alpha"), lois["Cm_alpha"], nominal=0.1 * x, x=x
        )
        assert axes[2].collections  # le remplissage de la bande

    def test_le_nominal_reste_visible_sous_la_moyenne(
        self, lois: JeuDeLois, sortie: pd.DataFrame
    ) -> None:
        """Quand la dispersion est centrée les deux coïncident : il faut le voir."""
        _, axes = figure_comparaison(
            _echantillons(sortie, "Cm_alpha"), lois["Cm_alpha"], nominal=-2.5
        )
        nominal = [t for t in axes[2].get_lines() if t.get_label() == "nominal"]
        moyenne = [t for t in axes[2].get_lines() if "moyenne" in str(t.get_label())]
        assert nominal and moyenne
        assert nominal[0].get_zorder() > moyenne[0].get_zorder()

    def test_dessine_dans_des_axes_fournis(self, lois: JeuDeLois, sortie: pd.DataFrame) -> None:
        figure, grille = nouvelle_figure(1, 3)
        rendue, _ = figure_comparaison(
            _echantillons(sortie, "Cm_alpha"), lois["Cm_alpha"], axes=list(np.ravel(grille))
        )
        assert rendue is figure

    def test_un_echantillon_manquant_est_nomme(self, lois: JeuDeLois) -> None:
        with pytest.raises(ValueError, match="FE"):
            figure_comparaison({"Biais": np.zeros(10)}, lois["Cm_alpha"])

    def test_le_point_de_vol_apparait_dans_le_titre(
        self, lois: JeuDeLois, sortie: pd.DataFrame
    ) -> None:
        figure, _ = figure_comparaison(
            _echantillons(sortie, "Cm_alpha"), lois["Cm_alpha"], pdv_label="M=0.85"
        )
        textes = textes_de(figure)
        assert any("M=0.85" in texte for texte in textes)


class TestFiguresParPdv:
    def test_une_figure_par_point_de_vol_et_coefficient(
        self, lois: JeuDeLois, sortie: pd.DataFrame
    ) -> None:
        produites = list(figures_par_pdv(sortie, lois, par=("Mach", "Altitude_m")))
        assert len(produites) == 2 * len(lois)

    def test_rend_les_cles_du_point_de_vol(self, lois: JeuDeLois, sortie: pd.DataFrame) -> None:
        cles, coefficient, _ = next(iter(figures_par_pdv(sortie, lois, par=("Mach",))))
        assert set(cles) == {"Mach"}
        assert coefficient in lois

    def test_c_est_un_generateur(self, lois: JeuDeLois, sortie: pd.DataFrame) -> None:
        """Mille figures ne doivent jamais être toutes en mémoire à la fois."""
        produites = figures_par_pdv(sortie, lois, par=("Mach",))
        assert next(iter(produites)) is not None

    def test_restreindre_aux_coefficients_voulus(
        self, lois: JeuDeLois, sortie: pd.DataFrame
    ) -> None:
        produites = list(figures_par_pdv(sortie, lois, par=("Mach",), coefficients=["Cm_alpha"]))
        assert {coefficient for _, coefficient, _ in produites} == {"Cm_alpha"}

    def test_seulement_restreint_aux_points_de_vol_donnes(
        self, lois: JeuDeLois, sortie: pd.DataFrame
    ) -> None:
        """C'est ainsi qu'on ne trace que les points de vol rejetés."""
        produites = list(figures_par_pdv(sortie, lois, par=("Mach",), seulement=[{"Mach": 0.85}]))
        assert {cles["Mach"] for cles, _, _ in produites} == {0.85}

    def test_un_coefficient_inconnu_est_refuse(self, lois: JeuDeLois, sortie: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="absent"):
            list(figures_par_pdv(sortie, lois, par=("Mach",), coefficients=["CL"]))

    def test_une_colonne_absente_est_nommee(self, lois: JeuDeLois, sortie: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="Cm_alpha_FE"):
            list(figures_par_pdv(sortie.drop(columns=["Cm_alpha_FE"]), lois, par=("Mach",)))

    def test_une_colonne_de_groupement_absente_est_nommee(
        self, lois: JeuDeLois, sortie: pd.DataFrame
    ) -> None:
        with pytest.raises(ValueError, match="Regime"):
            list(figures_par_pdv(sortie, lois, par=("Regime",)))
