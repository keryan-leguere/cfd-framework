"""Figures du tirage : les trois panneaux, les lignes σ, la pagination."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

from cfd_dispersion.core.combinaison import loi_combinee
from cfd_dispersion.core.convention import Convention
from cfd_dispersion.core.loi import LoiDispersion
from cfd_dispersion.core.lois import JeuDeLois, LoiCoefficient
from cfd_dispersion.core.tirage import Tirage, tirer
from cfd_dispersion.figures._base import nouvelle_figure
from cfd_dispersion.figures.tirage import (
    MAX_COEFFICIENTS_PAR_FIGURE,
    MESSAGE_SANS_NOMINAL,
    figure_tirage,
    figure_tirage_matrice,
    tracer_loi,
    tracer_loi_combinee,
    tracer_sigmas,
)
from tests.conftest import textes_de

#: Les nominaux de la table de test, pour les appels de figure.
NOMINAUX = {"Cm_alpha": -2.5, "Cn_beta": 0.1, "CA": 0.3}


@pytest.fixture
def tirage(lois: JeuDeLois) -> Tirage:
    return tirer(lois, graine=42)


@pytest.fixture(autouse=True)
def _fermer_les_figures() -> Iterator[None]:
    yield
    plt.close("all")


def _tirets_points(ax: Axes) -> list[Line2D]:
    """Les lignes ±kσ : ce sont les seules en trait mixte."""
    return [ligne for ligne in ax.get_lines() if ligne.get_linestyle() == "-."]


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

    def test_une_valeur_hors_plage_reste_visible(self) -> None:
        """Sinon le panneau cache précisément ce qu'il existe pour montrer."""
        _, ax = nouvelle_figure()
        tracer_loi(ax, LoiDispersion(4, 0.0, 0.02), valeur=0.15)
        bas, haut = ax.get_xlim()
        assert bas < 0.15 < haut

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

    def test_la_densite_laisse_de_la_place_aux_boites(self) -> None:
        """Sinon la légende et la boîte de paramètres se posent sur la bosse."""
        loi = LoiDispersion(4, 0.0, 0.2)
        _, ax = nouvelle_figure()
        tracer_loi(ax, loi)
        sommet = float(np.max(loi.pdf(np.linspace(*loi.plage_utile(), 400))))
        assert ax.get_ylim()[1] > 1.3 * sommet


class TestLignesSigma:
    def test_pose_une_ligne_par_multiple_et_par_cote(self) -> None:
        _, ax = nouvelle_figure()
        tracer_loi(ax, LoiDispersion(4, 0.0, 0.2))
        assert len(_tirets_points(ax)) == 6

    def test_les_lignes_tombent_a_kilo_sigma(self) -> None:
        loi = LoiDispersion(4, 0.0, 0.2)
        _, ax = nouvelle_figure()
        tracer_loi(ax, loi)
        positions = sorted(
            float(np.asarray(ligne.get_xdata(), dtype=float)[0]) for ligne in _tirets_points(ax)
        )
        attendues = sorted(k * loi.ET_theorique for k in (-3, -2, -1, 1, 2, 3))
        assert positions == pytest.approx(attendues)

    def test_une_ligne_hors_champ_n_est_pas_tracee(self) -> None:
        """Une tronquée ±2σ n'a pas de 3σ : la tracer élargirait l'axe pour rien."""
        _, ax = nouvelle_figure()
        tracer_loi(ax, LoiDispersion(6, 0.0, 0.10))
        assert len(_tirets_points(ax)) == 4

    def test_les_lignes_sont_etiquetees(self) -> None:
        figure, ax = nouvelle_figure()
        tracer_loi(ax, LoiDispersion(4, 0.0, 0.2))
        assert {"+1σ", "-2σ", "+3σ"} <= textes_de(figure)

    def test_elles_se_taisent_sur_demande(self) -> None:
        _, ax = nouvelle_figure()
        tracer_loi(ax, LoiDispersion(4, 0.0, 0.2), sigmas=None)
        assert not _tirets_points(ax)

    def test_une_loi_sans_dispersion_n_a_pas_de_sigma(self) -> None:
        _, ax = nouvelle_figure()
        assert tracer_sigmas(ax, 1.0, 0.0) == []


class TestTracerLoiCombinee:
    @pytest.fixture
    def coefficient(self) -> LoiCoefficient:
        return LoiCoefficient(
            nom="CN",
            biais=LoiDispersion(5, 0.0, 0.02),
            fe=LoiDispersion(6, 1.0, 0.08),
        )

    def test_trace_la_densite_du_coefficient(self, coefficient: LoiCoefficient) -> None:
        _, ax = nouvelle_figure()
        tracer_loi_combinee(ax, loi_combinee(coefficient, 0.85))
        assert ax.get_lines()
        assert ax.get_xlabel() == "CN"

    def test_repere_le_nominal_et_la_valeur_tiree(self, coefficient: LoiCoefficient) -> None:
        _, ax = nouvelle_figure()
        tracer_loi_combinee(ax, loi_combinee(coefficient, 0.85), valeur=0.87)
        libelles = {str(ligne.get_label()) for ligne in ax.get_lines()}
        assert any(libelle.startswith("nominal : 0.85") for libelle in libelles)
        assert any(libelle.startswith("dispersé : 0.87") for libelle in libelles)

    def test_la_valeur_tiree_est_chiffree_en_pourcentage(self, coefficient: LoiCoefficient) -> None:
        """Le pourcentage d'écart est ce qui se lit, pas la valeur absolue."""
        _, ax = nouvelle_figure()
        tracer_loi_combinee(ax, loi_combinee(coefficient, 0.80), valeur=0.84)
        libelles = [str(ligne.get_label()) for ligne in ax.get_lines()]
        assert any("+5.00 %" in libelle for libelle in libelles)

    def test_un_axe_superieur_donne_l_ecart_en_pourcentage(
        self, coefficient: LoiCoefficient
    ) -> None:
        _, ax = nouvelle_figure()
        tracer_loi_combinee(ax, loi_combinee(coefficient, 0.85))
        assert any("%" in enfant.get_xlabel() for enfant in ax.child_axes)

    def test_pas_d_axe_en_pourcentage_sur_un_nominal_nul(self, coefficient: LoiCoefficient) -> None:
        """Un écart relatif à zéro n'existe pas : muet plutôt que faux."""
        _, ax = nouvelle_figure()
        tracer_loi_combinee(ax, loi_combinee(coefficient, 0.0))
        assert not ax.child_axes

    def test_les_bornes_du_support_sont_marquees(self, coefficient: LoiCoefficient) -> None:
        _, ax = nouvelle_figure()
        tracer_loi_combinee(ax, loi_combinee(coefficient, 0.85))
        assert len([t for t in ax.get_lines() if t.get_linestyle() == ":"]) == 2

    def test_un_coefficient_sans_dispersion_est_une_masse(self) -> None:
        fige = LoiCoefficient(nom="CA", biais=LoiDispersion(2, 0.001), fe=LoiDispersion(2, 1.0))
        _, ax = nouvelle_figure()
        tracer_loi_combinee(ax, loi_combinee(fige, 0.3))
        assert not _tirets_points(ax)


class TestFigureTirage:
    def test_rend_trois_panneaux(self, lois: JeuDeLois, tirage: Tirage) -> None:
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5)
        assert rendue.axes.shape == (3,)
        assert rendue.coefficients == ("Cm_alpha",)

    def test_les_panneaux_sont_titres(self, lois: JeuDeLois, tirage: Tirage) -> None:
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5)
        titres = [ax.get_title() for ax in rendue.axes]
        assert "Biais" in titres[0]
        assert "FE" in titres[1]
        assert "coefficient dispersé" in titres[2]

    def test_le_troisieme_panneau_porte_la_loi_du_coefficient(
        self, lois: JeuDeLois, tirage: Tirage
    ) -> None:
        """Une densité, et non un histogramme : aucune barre sur le panneau."""
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5)
        assert not rendue.axes[2].patches
        assert any(
            str(ligne.get_label()) == "loi du coefficient" for ligne in rendue.axes[2].get_lines()
        )

    def test_un_nominal_balaye_se_ramene_a_un_point(self, lois: JeuDeLois, tirage: Tirage) -> None:
        """La loi combinée n'existe qu'en un point : la figure dit lequel."""
        x = np.linspace(0.0, 10.0, 21)
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5 + 0.05 * x, x=x)
        assert any("à x = 5" in texte for texte in textes_de(rendue.figure))

    def test_le_point_de_reference_se_choisit(self, lois: JeuDeLois, tirage: Tirage) -> None:
        x = np.linspace(0.0, 10.0, 21)
        rendue = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5 + 0.05 * x, x=x, reference=8.0
        )
        assert any("à x = 8" in texte for texte in textes_de(rendue.figure))

    def test_un_balayage_sans_abscisse_est_repere_par_son_indice(
        self, lois: JeuDeLois, tirage: Tirage
    ) -> None:
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=np.full(9, -2.5))
        assert any("point 5/9" in texte for texte in textes_de(rendue.figure))

    def test_un_x_de_longueur_differente_est_refuse(self, lois: JeuDeLois, tirage: Tirage) -> None:
        with pytest.raises(ValueError, match="même longueur"):
            figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=np.zeros(5), x=np.zeros(4))

    def test_dessine_dans_des_axes_fournis(self, lois: JeuDeLois, tirage: Tirage) -> None:
        figure, grille = nouvelle_figure(1, 3)
        rendue = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5, axes=list(np.ravel(grille))
        )
        assert rendue.figure is figure

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
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], t, nominal=-2.5)
        assert any("FE/100" in texte for texte in textes_de(rendue.figure))

    def test_la_convention_peut_etre_imposee(self, lois: JeuDeLois, tirage: Tirage) -> None:
        rendue = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5, convention_="relatif"
        )
        assert any("(1 + FE) · c" in texte for texte in textes_de(rendue.figure))

    def test_une_convention_non_affine_passe_par_le_lissage(
        self, lois: JeuDeLois, tirage: Tirage
    ) -> None:
        tordue = Convention(
            nom="tordue", formule="biais + FE² · c", appliquer=lambda c, b, f: b + f**2 * c
        )
        rendue = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5, convention_=tordue
        )
        assert any("lissée" in texte for texte in textes_de(rendue.figure))


class TestSansNominal:
    """Sans valeur nominale, les deux premiers panneaux valent toujours."""

    def test_les_deux_premiers_panneaux_sont_traces(self, lois: JeuDeLois, tirage: Tirage) -> None:
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage)
        assert rendue.axes.shape == (3,)
        assert rendue.axes[0].get_lines()
        assert rendue.axes[1].get_lines()

    def test_le_troisieme_reste_vide(self, lois: JeuDeLois, tirage: Tirage) -> None:
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage)
        assert not rendue.axes[2].get_lines()
        assert not rendue.axes[2].patches

    def test_il_explique_ce_qui_lui_manque(self, lois: JeuDeLois, tirage: Tirage) -> None:
        """Un panneau blanc muet se lirait comme un bogue."""
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage)
        textes = textes_de(rendue.figure)
        assert MESSAGE_SANS_NOMINAL.format(coefficient="Cm_alpha") in textes
        assert any("Cm_alpha — coefficient dispersé" == texte for texte in textes)

    def test_ses_axes_sont_eteints(self, lois: JeuDeLois, tirage: Tirage) -> None:
        """Une graduation sous un message d'absence ferait croire à un tracé."""
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage)
        assert not rendue.axes[2].axison

    def test_la_figure_s_ecrit_quand_meme(
        self, lois: JeuDeLois, tirage: Tirage, tmp_path: Path
    ) -> None:
        rendue = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, chemin=tmp_path / "sans_nominal"
        )
        assert rendue.fichiers[0].is_file()

    def test_la_matrice_se_passe_de_nominaux(self, lois: JeuDeLois, tirage: Tirage) -> None:
        (page,) = figure_tirage_matrice(lois, tirage)
        assert page.axes.shape == (3, 3)
        assert all(not page.axes[ligne, 2].get_lines() for ligne in range(3))

    def test_la_matrice_accepte_des_nominaux_incomplets(
        self, lois: JeuDeLois, tirage: Tirage
    ) -> None:
        """Le coefficient renseigné garde son panneau ; l'autre s'explique."""
        (page,) = figure_tirage_matrice(
            lois, tirage, nominaux={"CA": 0.3}, coefficients=["CA", "Cm_alpha"]
        )
        assert page.axes[0, 2].get_lines()
        assert not page.axes[1, 2].get_lines()
        assert MESSAGE_SANS_NOMINAL.format(coefficient="Cm_alpha") in textes_de(page.figure)


class TestAccordAvecLeModele:
    """La valeur que le modèle a rendue, confrontée à celle qu'on recalcule."""

    def _calcul(self, lois: JeuDeLois, tirage: Tirage) -> float:
        return float(tirage.appliquer({"Cm_alpha": -2.5})["Cm_alpha"])

    def test_la_valeur_du_modele_est_reperee(self, lois: JeuDeLois, tirage: Tirage) -> None:
        rendue = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5, disperse_modele=-2.6
        )
        libelles = {str(ligne.get_label()) for ligne in rendue.axes[2].get_lines()}
        assert any(libelle.startswith("modèle : -2.6") for libelle in libelles)

    def test_l_accord_est_rendu(self, lois: JeuDeLois, tirage: Tirage) -> None:
        calcul = self._calcul(lois, tirage)
        rendue = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5, disperse_modele=calcul
        )
        assert rendue.accord is not None
        assert rendue.accord.accord
        assert any("modèle = calcul" in texte for texte in textes_de(rendue.figure))

    def test_un_desaccord_est_chiffre(self, lois: JeuDeLois, tirage: Tirage) -> None:
        """Une convention différente de part et d'autre, et rien ne le dirait."""
        calcul = self._calcul(lois, tirage)
        rendue = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5, disperse_modele=calcul * 1.05
        )
        assert rendue.accord is not None
        assert not rendue.accord.accord
        assert any("modèle ≠ calcul" in texte for texte in textes_de(rendue.figure))

    def test_sans_valeur_de_modele_il_n_y_a_pas_de_verdict(
        self, lois: JeuDeLois, tirage: Tirage
    ) -> None:
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5)
        assert rendue.accord is None
        assert not any("modèle" in texte for texte in textes_de(rendue.figure))

    def test_sans_nominal_il_n_y_a_rien_a_comparer(self, lois: JeuDeLois, tirage: Tirage) -> None:
        """Pas de calcul possible, donc pas de confrontation."""
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, disperse_modele=-2.6)
        assert rendue.accord is None

    def test_la_tolerance_se_regle(self, lois: JeuDeLois, tirage: Tirage) -> None:
        calcul = self._calcul(lois, tirage)
        rendue = figure_tirage(
            "Cm_alpha",
            lois["Cm_alpha"],
            tirage,
            nominal=-2.5,
            disperse_modele=calcul * 1.001,
            tolerance=0.01,
        )
        assert rendue.accord is not None and rendue.accord.accord

    def test_la_matrice_confronte_chaque_ligne(self, lois: JeuDeLois, tirage: Tirage) -> None:
        disperses = tirage.appliquer(NOMINAUX)
        (page,) = figure_tirage_matrice(
            lois,
            tirage,
            nominaux=NOMINAUX,
            disperses_modele={nom: float(valeur) for nom, valeur in disperses.items()},
        )
        textes = textes_de(page.figure)
        assert sum("modèle = calcul" in texte for texte in textes) == 3


class TestEcriture:
    def test_sans_chemin_rien_n_est_ecrit(self, lois: JeuDeLois, tirage: Tirage) -> None:
        rendue = figure_tirage("Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5)
        assert rendue.fichiers == ()

    def test_le_chemin_donne_ecrit_un_svg(
        self, lois: JeuDeLois, tirage: Tirage, tmp_path: Path
    ) -> None:
        """Tracer et enregistrer ne font qu'un appel, et le format est vectoriel."""
        rendue = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5, chemin=tmp_path / "CN"
        )
        assert [chemin.name for chemin in rendue.fichiers] == ["CN.svg"]
        assert rendue.fichiers[0].is_file()

    def test_les_formats_se_choisissent(
        self, lois: JeuDeLois, tirage: Tirage, tmp_path: Path
    ) -> None:
        rendue = figure_tirage(
            "Cm_alpha",
            lois["Cm_alpha"],
            tirage,
            nominal=-2.5,
            chemin=tmp_path / "CN",
            formats=("png", "svg"),
        )
        assert [chemin.suffix for chemin in rendue.fichiers] == [".png", ".svg"]

    def test_un_point_dans_le_nom_survit(
        self, lois: JeuDeLois, tirage: Tirage, tmp_path: Path
    ) -> None:
        """``Path.with_suffix`` mangerait le ``.85`` — d'où ``enregistrer``."""
        rendue = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5, chemin=tmp_path / "CN_Mach0.85"
        )
        assert rendue.fichiers[0].name == "CN_Mach0.85.svg"

    def test_le_dossier_est_cree(self, lois: JeuDeLois, tirage: Tirage, tmp_path: Path) -> None:
        rendue = figure_tirage(
            "Cm_alpha", lois["Cm_alpha"], tirage, nominal=-2.5, chemin=tmp_path / "SORTIE" / "CN"
        )
        assert rendue.fichiers[0].is_file()


class TestFigureTirageMatrice:
    def test_une_ligne_de_trois_panneaux_par_coefficient(
        self, lois: JeuDeLois, tirage: Tirage
    ) -> None:
        (page,) = figure_tirage_matrice(lois, tirage, nominaux=NOMINAUX)
        assert page.axes.shape == (3, 3)

    def test_l_ordre_des_coefficients_est_respecte(self, lois: JeuDeLois, tirage: Tirage) -> None:
        (page,) = figure_tirage_matrice(
            lois,
            tirage,
            nominaux=NOMINAUX,
            coefficients=["CA", "Cm_alpha"],
        )
        assert "CA" in page.axes[0, 0].get_title()
        assert page.coefficients == ("CA", "Cm_alpha")

    def test_au_dela_de_quatre_coefficients_une_seconde_figure(
        self, lois: JeuDeLois, tirage: Tirage
    ) -> None:
        """Cinq lignes sur une page : les panneaux deviennent des timbres."""
        noms = ["Cm_alpha", "Cn_beta", "CA", "Cm_alpha", "Cn_beta"]
        pages = figure_tirage_matrice(lois, tirage, nominaux=NOMINAUX, coefficients=noms)
        assert [page.axes.shape for page in pages] == [(4, 3), (1, 3)]
        assert MAX_COEFFICIENTS_PAR_FIGURE == 4

    def test_la_pagination_se_regle(self, lois: JeuDeLois, tirage: Tirage) -> None:
        pages = figure_tirage_matrice(lois, tirage, nominaux=NOMINAUX, max_par_figure=1)
        assert len(pages) == 3

    def test_les_fichiers_sont_numerotes_quand_il_y_a_plusieurs_pages(
        self, lois: JeuDeLois, tirage: Tirage, tmp_path: Path
    ) -> None:
        pages = figure_tirage_matrice(
            lois, tirage, nominaux=NOMINAUX, chemin=tmp_path / "tirage", max_par_figure=2
        )
        ecrits = [chemin.name for page in pages for chemin in page.fichiers]
        assert ecrits == ["tirage_01.svg", "tirage_02.svg"]

    def test_une_page_unique_garde_le_nom_tel_quel(
        self, lois: JeuDeLois, tirage: Tirage, tmp_path: Path
    ) -> None:
        (page,) = figure_tirage_matrice(lois, tirage, nominaux=NOMINAUX, chemin=tmp_path / "tirage")
        assert [chemin.name for chemin in page.fichiers] == ["tirage.svg"]

    def test_le_numero_de_page_est_affiche(self, lois: JeuDeLois, tirage: Tirage) -> None:
        pages = figure_tirage_matrice(lois, tirage, nominaux=NOMINAUX, max_par_figure=2)
        assert any("(2/2)" in texte for texte in textes_de(pages[1].figure))

    def test_un_coefficient_inconnu_est_refuse(self, lois: JeuDeLois, tirage: Tirage) -> None:
        with pytest.raises(ValueError, match="absent"):
            figure_tirage_matrice(lois, tirage, nominaux={}, coefficients=["CL"])

    def test_une_liste_vide_est_refusee(self, lois: JeuDeLois, tirage: Tirage) -> None:
        with pytest.raises(ValueError, match="aucun coefficient"):
            figure_tirage_matrice(lois, tirage, nominaux={}, coefficients=[])

    def test_une_pagination_nulle_est_refusee(self, lois: JeuDeLois, tirage: Tirage) -> None:
        with pytest.raises(ValueError, match="strictement positif"):
            figure_tirage_matrice(lois, tirage, nominaux=NOMINAUX, max_par_figure=0)
