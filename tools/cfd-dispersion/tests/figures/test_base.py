"""Plomberie des figures : couleurs, étiquetage sur courbe, repli Matplotlib."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest
from matplotlib.axes import Axes
from matplotlib.text import Text

from cfd_dispersion.figures._base import (
    assombrir,
    boite_texte,
    couleur_de_serie,
    etiqueter_ligne,
    legende,
    nouvelle_figure,
    remplir_entre,
    tracer_bande,
    tracer_ligne,
)


@pytest.fixture
def axes() -> Iterator[Axes]:
    figure, ax = nouvelle_figure()
    yield ax
    import matplotlib.pyplot as plt

    plt.close(figure)


class TestAssombrir:
    def test_assombrit_vers_le_noir(self) -> None:
        assert assombrir("#808080", 0.5) == pytest.approx((0.25, 0.25, 0.25), abs=0.01)

    def test_facteur_nul_ne_change_rien(self) -> None:
        assert assombrir("#4C72B0", 0.0) == pytest.approx((0.298, 0.447, 0.690), abs=0.01)

    def test_facteur_un_donne_du_noir(self) -> None:
        assert assombrir("#4C72B0", 1.0) == (0.0, 0.0, 0.0)

    def test_la_couleur_reste_reconnaissable(self) -> None:
        """Assombrir doit rattacher, pas dépayser : les teintes gardent leur ordre."""
        r, v, b = assombrir("#4C72B0", 0.25)
        assert b > v > r

    @pytest.mark.parametrize("facteur", [-0.1, 1.5])
    def test_un_facteur_hors_bornes_est_refuse(self, facteur: float) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            assombrir("C0", facteur)


class TestCouleurDeSerie:
    def test_retrouve_la_couleur_par_le_libelle(self, axes: Axes) -> None:
        tracer_ligne(axes, [0, 1], [0, 1], label="KW", color="C0")
        tracer_ligne(axes, [0, 1], [1, 2], label="SA", color="C1")
        assert couleur_de_serie(axes, "SA") == "C1"

    def test_une_serie_absente_liste_celles_presentes(self, axes: Axes) -> None:
        tracer_ligne(axes, [0, 1], [0, 1], label="KW", color="C0")
        with pytest.raises(ValueError, match="KW"):
            couleur_de_serie(axes, "EXP")

    def test_des_axes_vides_le_disent(self, axes: Axes) -> None:
        with pytest.raises(ValueError, match="aucun"):
            couleur_de_serie(axes, "KW")


def _angle(texte: Text) -> float:
    """L'inclinaison ramenée dans [-180, 180].

    ``Text.get_rotation`` normalise dans [0, 360) : une pente descendante de
    -56° est relue 304°, ce qui est le même rendu mais complique l'assertion.
    """
    return float(((texte.get_rotation() + 180.0) % 360.0) - 180.0)


class TestEtiqueterLigne:
    def test_pose_le_texte_sur_la_courbe(self, axes: Axes) -> None:
        x = np.linspace(0, 10, 50)
        texte = etiqueter_ligne(axes, x, 2.0 * x, "+2σ")
        assert texte.get_text() == "+2σ"
        assert texte.get_position()[0] == pytest.approx(x[round(0.85 * 49)])

    def test_l_inclinaison_suit_la_pente_affichee(self, axes: Axes) -> None:
        """Une courbe montante donne un angle positif, une descendante négatif."""
        x = np.linspace(0, 10, 50)
        assert _angle(etiqueter_ligne(axes, x, 2.0 * x, "a")) > 0.0
        assert _angle(etiqueter_ligne(axes, x, -2.0 * x, "b")) < 0.0

    def test_une_courbe_horizontale_donne_un_texte_horizontal(self, axes: Axes) -> None:
        x = np.linspace(0, 10, 50)
        assert _angle(etiqueter_ligne(axes, x, np.zeros_like(x), "0")) == pytest.approx(
            0.0, abs=1e-6
        )

    def test_l_angle_est_calcule_en_coordonnees_d_affichage(self, axes: Axes) -> None:
        """Une même pente en données donne des angles différents selon l'échelle.

        C'est tout l'intérêt : l'étiquette suit la pente réellement tracée, pas
        celle des données.
        """
        x = np.linspace(0, 10, 50)
        y = 2.0 * x
        axes.set_ylim(0, 20)
        raide = _angle(etiqueter_ligne(axes, x, y, "a"))
        axes.set_ylim(0, 200)
        plat = _angle(etiqueter_ligne(axes, x, y, "b"))
        assert raide > plat

    def test_le_texte_ne_se_lit_jamais_a_l_envers(self, axes: Axes) -> None:
        x = np.linspace(0, 10, 50)
        for pente in (-50.0, -5.0, 5.0, 50.0):
            assert -90.0 <= _angle(etiqueter_ligne(axes, x, pente * x, "s")) <= 90.0

    def test_la_fraction_choisit_la_position(self, axes: Axes) -> None:
        x = np.linspace(0, 10, 101)
        debut = etiqueter_ligne(axes, x, x, "a", fraction=0.0).get_position()[0]
        fin = etiqueter_ligne(axes, x, x, "b", fraction=1.0).get_position()[0]
        assert debut == pytest.approx(0.0)
        assert fin == pytest.approx(10.0)

    def test_l_etiquette_porte_un_cartouche(self, axes: Axes) -> None:
        """Le fond interrompt la courbe au lieu de la laisser traverser le texte."""
        x = np.linspace(0, 10, 20)
        assert etiqueter_ligne(axes, x, x, "a").get_bbox_patch() is not None

    def test_les_formes_doivent_correspondre(self, axes: Axes) -> None:
        with pytest.raises(ValueError, match="même forme"):
            etiqueter_ligne(axes, np.arange(5.0), np.arange(3.0), "a")

    def test_il_faut_au_moins_deux_points(self, axes: Axes) -> None:
        with pytest.raises(ValueError, match="deux points"):
            etiqueter_ligne(axes, [1.0], [1.0], "a")

    @pytest.mark.parametrize("fraction", [-0.2, 1.5])
    def test_une_fraction_hors_bornes_est_refusee(self, axes: Axes, fraction: float) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            etiqueter_ligne(axes, np.arange(5.0), np.arange(5.0), "a", fraction=fraction)


class TestPrimitives:
    def test_tracer_ligne_rend_une_ligne(self, axes: Axes) -> None:
        assert tracer_ligne(axes, [0, 1], [0, 1], label="a") in axes.get_lines()

    def test_tracer_bande_rend_ligne_et_polygone(self, axes: Axes) -> None:
        ligne, polygone = tracer_bande(
            axes, [0, 1, 2], [0, 1, 2], y_bas=[-1, 0, 1], y_haut=[1, 2, 3]
        )
        assert ligne is not None
        assert polygone is not None

    def test_remplir_entre_rend_un_polygone(self, axes: Axes) -> None:
        assert remplir_entre(axes, [0, 1, 2], [0, 0, 0], [1, 1, 1]) is not None

    def test_boite_texte_ancre_dans_les_axes(self, axes: Axes) -> None:
        texte = boite_texte(axes, "bonjour", loc="lower right")
        assert texte.get_text() == "bonjour"

    def test_legende_sans_courbe_ne_plante_pas(self, axes: Axes) -> None:
        legende(axes)


class TestSansCfdPlot:
    """Le paquet doit tracer la même chose sans cfd-plot installé."""

    @pytest.fixture
    def sans_plotting(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        import cfd_dispersion.figures._base as base

        monkeypatch.setattr(base, "get_plotting", lambda: None)
        return base

    def test_nouvelle_figure_fonctionne(self, sans_plotting: Any) -> None:
        import matplotlib.pyplot as plt

        figure, ax = sans_plotting.nouvelle_figure(1, 2)
        assert len(np.ravel(ax)) == 2
        plt.close(figure)

    def test_les_primitives_fonctionnent(self, sans_plotting: Any) -> None:
        import matplotlib.pyplot as plt

        figure, ax = sans_plotting.nouvelle_figure()
        sans_plotting.tracer_ligne(ax, [0, 1], [0, 1], label="a", color="C0")
        sans_plotting.tracer_bande(ax, [0, 1], [0, 1], y_bas=[-1, 0], y_haut=[1, 2])
        sans_plotting.remplir_entre(ax, [0, 1], [0, 0], [1, 1])
        sans_plotting.boite_texte(ax, "x", loc="upper left")
        sans_plotting.legende(ax)
        sans_plotting.titre(ax, "titre")
        assert ax.get_title() == "titre"
        plt.close(figure)

    def test_une_position_de_boite_inconnue_est_refusee(self, sans_plotting: Any) -> None:
        import matplotlib.pyplot as plt

        figure, ax = sans_plotting.nouvelle_figure()
        with pytest.raises(ValueError, match="position inconnue"):
            sans_plotting.boite_texte(ax, "x", loc="nowhere")
        plt.close(figure)
