"""Figures du tirage : les trois panneaux d'un coefficient."""

from __future__ import annotations

from collections.abc import Iterator

import matplotlib.pyplot as plt
import numpy as np
import pytest

from cfd_dispersion.core.loi import LoiDispersion
from cfd_dispersion.core.lois import JeuDeLois
from cfd_dispersion.core.tirage import Tirage, tirer
from cfd_dispersion.figures._base import nouvelle_figure
from cfd_dispersion.figures.tirage import figure_tirage, figure_tirage_matrice, tracer_loi
from tests.conftest import textes_de


@pytest.fixture
def tirage(lois: JeuDeLois) -> Tirage:
    return tirer(lois, graine=42)


@pytest.fixture(autouse=True)
def _fermer_les_figures() -> Iterator[None]:
    yield
    plt.close("all")


class TestTracerLoi:
    def test_trace_la_densite_d_une_loi_continue(self) -> None:
        _, ax = nouvelle_figure()
        tracer_loi(ax, LoiDispersion(4, 0.0, 0.2), label="loi")
        assert ax.get_lines()

    def test_marque_la_valeur_tiree(self) -> None:
        _, ax = nouvelle_figure()
        tracer_loi(ax, LoiDispersion(4, 0.0, 0.2), valeur=0.03)
        positions = [
            ligne.get_xdata()[0] for ligne in ax.get_lines() if ligne.get_linestyle() == "--"
        ]
        assert pytest.approx(0.03) in positions

    def test_marque_les_bornes_du_support_d_une_loi_bornee(self) -> None:
        """Ce qui distingue à l'œil une tronquée d'une gaussienne pleine."""
        _, borne = nouvelle_figure()
        tracer_loi(borne, LoiDispersion(6, 0.0, 0.10))
        pointilles = [t for t in borne.get_lines() if t.get_linestyle() == ":"]
        assert len(pointilles) == 2

    def test_une_gaussienne_pleine_n_a_pas_de_bornes_tracees(self) -> None:
        _, ax = nouvelle_figure()
        tracer_loi(ax, LoiDispersion(4, 0.0, 0.10))
        assert not [t for t in ax.get_lines() if t.get_linestyle() == ":"]

    def test_une_loi_degeneree_borne_quand_meme_son_axe(self) -> None:
        """``axvline`` seul laisserait Matplotlib retomber sur (0, 1)."""
        _, ax = nouvelle_figure()
        tracer_loi(ax, LoiDispersion(2, 0.001))
        bas, haut = ax.get_xlim()
        assert bas < 0.001 < haut
        assert haut - bas < 1.0


class TestFigureTirage:
    def test_rend_trois_panneaux(self, lois: JeuDeLois, tirage: Tirage) -> None:
        _, axes = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5)
        assert axes.shape == (3,)

    def test_les_panneaux_sont_titres_par_composante(self, lois: JeuDeLois, tirage: Tirage) -> None:
        _, axes = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5)
        titres = [ax.get_title() for ax in axes]
        assert "Biais" in titres[0] and "FE" in titres[1] and "reconstruction" in titres[2]

    def test_un_nominal_scalaire_donne_des_barres(self, lois: JeuDeLois, tirage: Tirage) -> None:
        _, axes = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5)
        assert axes[2].patches

    def test_un_nominal_negatif_laisse_la_place_aux_etiquettes(
        self, lois: JeuDeLois, tirage: Tirage
    ) -> None:
        """Sinon le chiffre qu'on vient lire sort des axes et se fait rogner."""
        _, axes = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5)
        bas, _ = axes[2].get_ylim()
        assert bas < -2.5

    def test_un_nominal_balaye_donne_deux_courbes(self, lois: JeuDeLois, tirage: Tirage) -> None:
        x = np.linspace(0, 10, 20)
        _, axes = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5 + 0.05 * x, x=x)
        assert len(axes[2].get_lines()) >= 2

    def test_dessine_dans_des_axes_fournis(self, lois: JeuDeLois, tirage: Tirage) -> None:
        figure, grille = nouvelle_figure(1, 3)
        rendue, _ = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5, axes=list(np.ravel(grille))
        )
        assert rendue is figure

    def test_il_faut_exactement_trois_axes(self, lois: JeuDeLois, tirage: Tirage) -> None:
        _, grille = nouvelle_figure(1, 2)
        with pytest.raises(ValueError, match="3 axes"):
            figure_tirage(
                "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5, axes=list(np.ravel(grille))
            )

    def test_un_coefficient_absent_du_tirage_est_refuse(
        self, lois: JeuDeLois, tirage: Tirage
    ) -> None:
        with pytest.raises(ValueError, match="absent du tirage"):
            figure_tirage("CL", lois["Cm_alpha"], tirage, nominal=1.0)

    def test_la_convention_du_tirage_est_reprise_par_defaut(self, lois: JeuDeLois) -> None:
        t = tirer(lois, graine=1, convention_="pourcentage")
        figure, _ = figure_tirage("Cm_alpha", lois["Cm_alpha"], t, nominal=-2.5)
        textes = textes_de(figure)
        assert any("FE/100" in texte for texte in textes)

    def test_la_convention_peut_etre_imposee(self, lois: JeuDeLois, tirage: Tirage) -> None:
        figure, _ = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5, convention_="relatif"
        )
        textes = textes_de(figure)
        assert any("(1 + FE) · c" in texte for texte in textes)


class TestFigureTirageMatrice:
    def test_une_ligne_de_trois_panneaux_par_coefficient(
        self, lois: JeuDeLois, tirage: Tirage
    ) -> None:
        _, grille = figure_tirage_matrice(
            lois, tirage, nominaux={"Cm_alpha": -2.5, "Cn_beta": 0.1, "CA": 0.3}
        )
        assert grille.shape == (3, 3)

    def test_l_ordre_des_coefficients_est_respecte(self, lois: JeuDeLois, tirage: Tirage) -> None:
        _, grille = figure_tirage_matrice(
            lois,
            tirage,
            nominaux={"Cm_alpha": -2.5, "CA": 0.3},
            coefficients=["CA", "Cm_alpha"],
        )
        assert "CA" in grille[0, 0].get_title()

    def test_un_coefficient_inconnu_est_refuse(self, lois: JeuDeLois, tirage: Tirage) -> None:
        with pytest.raises(ValueError, match="absent"):
            figure_tirage_matrice(lois, tirage, nominaux={}, coefficients=["CL"])

    def test_une_liste_vide_est_refusee(self, lois: JeuDeLois, tirage: Tirage) -> None:
        with pytest.raises(ValueError, match="aucun coefficient"):
            figure_tirage_matrice(lois, tirage, nominaux={}, coefficients=[])
