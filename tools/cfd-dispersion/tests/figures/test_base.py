"""Plomberie des figures : délégation à cfd-plot, couleurs, étiquetage sur courbe."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from matplotlib.axes import Axes
from matplotlib.text import Text

from cfd_dispersion.figures._base import (
    assombrir,
    boite_texte,
    couleur_de_serie,
    eclaircir,
    enregistrer,
    etiqueter_ligne,
    legende,
    lignes_reference,
    nouvelle_figure,
    remplir_entre,
    style,
    surtitre,
    titre,
    tracer_bande,
    tracer_ligne,
)
from cfd_dispersion.report._plotting_lib import get_plotting


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


class TestEclaircir:
    def test_eclaircit_vers_le_blanc(self) -> None:
        assert eclaircir("#808080", 0.5) == pytest.approx((0.75, 0.75, 0.75), abs=0.01)

    def test_facteur_nul_ne_change_rien(self) -> None:
        assert eclaircir("#4C72B0", 0.0) == pytest.approx((0.298, 0.447, 0.690), abs=0.01)

    def test_facteur_un_donne_du_blanc(self) -> None:
        assert eclaircir("#4C72B0", 1.0) == pytest.approx((1.0, 1.0, 1.0))

    def test_la_couleur_reste_reconnaissable(self) -> None:
        """Éclaircir doit rattacher, pas dépayser : les teintes gardent leur ordre."""
        r, v, b = eclaircir("#4C72B0", 0.35)
        assert b > v > r

    @pytest.mark.parametrize("facteur", [-0.1, 1.5])
    def test_un_facteur_hors_bornes_est_refuse(self, facteur: float) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            eclaircir("C0", facteur)


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

    def test_l_etiquette_n_a_pas_de_cartouche(self, axes: Axes) -> None:
        """Un fond percerait une tache claire dans le faisceau qu'on regarde."""
        x = np.linspace(0, 10, 20)
        assert etiqueter_ligne(axes, x, x, "a").get_bbox_patch() is None

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

    def test_remplir_entre_rend_aussi_ses_bords(self, axes: Axes) -> None:
        """Un bord de la teinte exacte du remplissage ne se verrait pas."""
        polygone, bords = remplir_entre(
            axes,
            [0, 1, 2],
            [0, 0, 0],
            [1, 1, 1],
            lignes=True,
            options_lignes={"color": "k", "linewidth": 2.0},
        )
        assert polygone is not None
        assert len(bords) == 2
        assert all(ligne.get_linewidth() == 2.0 for ligne in bords)

    def test_boite_texte_ancre_dans_les_axes(self, axes: Axes) -> None:
        texte = boite_texte(axes, "bonjour", loc="lower right")
        assert texte.get_text() == "bonjour"

    def test_legende_sans_courbe_ne_plante_pas(self, axes: Axes) -> None:
        legende(axes)


class TestLignesReference:
    def test_trace_une_verticale_par_position(self, axes: Axes) -> None:
        artistes = lignes_reference(axes, verticales=[0.25, 0.75])
        assert len(artistes) == 2
        assert [ligne.get_xdata()[0] for ligne in artistes] == [0.25, 0.75]

    def test_trace_aussi_des_horizontales(self, axes: Axes) -> None:
        (ligne,) = lignes_reference(axes, horizontales=[1.5])
        assert ligne.get_ydata()[0] == 1.5

    def test_sans_position_ne_trace_rien(self, axes: Axes) -> None:
        assert lignes_reference(axes) == []


class TestFondDesEtiquettes:
    def test_un_cartouche_se_redemande(self, axes: Axes) -> None:
        """Il n'y en a plus par défaut, mais il reste à portée de main."""
        cartouche = etiqueter_ligne(axes, [0, 1], [0, 1], "±1σ", fond_alpha=0.6).get_bbox_patch()
        assert cartouche is not None
        opacite = cartouche.get_alpha()
        assert opacite is not None and 0.0 < opacite < 1.0

    def test_il_se_rend_opaque(self, axes: Axes) -> None:
        cartouche = etiqueter_ligne(axes, [0, 1], [0, 1], "±1σ", fond_alpha=1.0).get_bbox_patch()
        assert cartouche is not None
        assert cartouche.get_alpha() == 1.0


class TestToutPasseParCfdPlot:
    """Le format des figures vient de cfd-plot, pas de Matplotlib nu.

    Ces primitives sont le seul chemin de tracé du paquet. Si l'une d'elles
    cessait de déléguer, ses figures sortiraient hors gabarit sans qu'aucune
    autre assertion ne bronche : c'est un défaut de *format*, et aucune
    vérification de contenu ne l'attrape.
    """

    @pytest.fixture
    def espion(self, monkeypatch: pytest.MonkeyPatch) -> list[str]:
        """Un faux cfd_plot qui note les fonctions demandées."""
        import cfd_dispersion.figures._base as base

        appels: list[str] = []
        vrai = get_plotting()

        class Espion:
            def __getattr__(self, nom: str) -> Any:
                appels.append(nom)
                return getattr(vrai, nom)

        monkeypatch.setattr(base, "get_plotting", Espion)
        return appels

    def test_les_primitives_deleguent_toutes(self, espion: list[str]) -> None:
        import matplotlib.pyplot as plt

        figure, ax = nouvelle_figure()
        tracer_ligne(ax, [0, 1], [0, 1], label="a", color="C0")
        tracer_bande(ax, [0, 1], [0, 1], y_bas=[-1, 0], y_haut=[1, 2])
        remplir_entre(ax, [0, 1], [0, 0], [1, 1])
        lignes_reference(ax, verticales=[0.5])
        boite_texte(ax, "x", loc="upper left")
        legende(ax)
        titre(ax, "titre")
        surtitre(figure, "surtitre")
        plt.close(figure)

        assert espion == [
            "new_figure",
            "plot_line",
            "plot_with_band",
            "fill_between_curves",
            "add_reference_lines",
            "add_textbox",
            "make_legend",
            "set_title",
            "set_suptitle",
        ]

    def test_le_style_passe_par_style_context(self, espion: list[str]) -> None:
        with style("paper"):
            pass
        # ``use_style`` modifierait les rcParams globaux de l'appelant.
        assert espion == ["style_context"]

    def test_enregistrer_ecrit_par_save_figure(self, espion: list[str], tmp_path: Path) -> None:
        import matplotlib.pyplot as plt

        figure, ax = nouvelle_figure()
        tracer_ligne(ax, [0, 1], [0, 1])
        ecrits = enregistrer(figure, tmp_path / "essai", formats=("png",))
        plt.close(figure)

        assert "save_figure" in espion
        assert ecrits and ecrits[0].is_file()
        assert ecrits[0].suffix == ".png"

    def test_un_point_dans_le_nom_ne_tronque_pas_le_fichier(self, tmp_path: Path) -> None:
        """« CN_Mach0.85 » doit rester « CN_Mach0.85.png ».

        ``save_figure`` compose son fichier par ``Path.with_suffix``, qui
        remplace tout ce qui suit le dernier point. Sans garde-fou, une série
        de points de vol s'écrase entière dans un seul fichier, sans erreur —
        et c'est le nom de figure le plus courant du framework.
        """
        import matplotlib.pyplot as plt

        ecrits = []
        for mach in (0.70, 0.85):
            figure, ax = nouvelle_figure()
            tracer_ligne(ax, [0, 1], [0, 1])
            ecrits += enregistrer(figure, tmp_path / f"CN_Mach{mach:g}", formats=("png", "svg"))
            plt.close(figure)

        noms = sorted(chemin.name for chemin in ecrits)
        assert noms == [
            "CN_Mach0.7.png",
            "CN_Mach0.7.svg",
            "CN_Mach0.85.png",
            "CN_Mach0.85.svg",
        ]
        assert all(chemin.is_file() for chemin in ecrits)

    def test_une_extension_deja_presente_n_est_pas_doublee(self, tmp_path: Path) -> None:
        import matplotlib.pyplot as plt

        figure, ax = nouvelle_figure()
        tracer_ligne(ax, [0, 1], [0, 1])
        (chemin,) = enregistrer(figure, tmp_path / "essai.png", formats=("png",))
        plt.close(figure)
        assert chemin.name == "essai.png"


class TestCfdPlotManquant:
    """Sans cfd-plot, l'échec doit nommer la commande à taper."""

    def test_get_plotting_leve_un_import_error_explicite(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cfd_dispersion.report import _plotting_lib

        monkeypatch.setattr(_plotting_lib, "_importer", lambda: None)
        with pytest.raises(ImportError, match="pip install -e tools/cfd-plot"):
            _plotting_lib.get_plotting()

    def test_cfd_plot_disponible_ne_leve_pas(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from cfd_dispersion.report import _plotting_lib

        monkeypatch.setattr(_plotting_lib, "_importer", lambda: None)
        assert _plotting_lib.cfd_plot_disponible() is False
