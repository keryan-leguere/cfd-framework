"""Les histogrammes par point de vol : obtenu contre prescrit, et les décalages."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from cfd_dispersion.core.lois import JeuDeLois, charger_lois
from cfd_dispersion.core.tirage import tirage_neutre, tirer_lot
from cfd_dispersion.figures.histogramme import (
    MESSAGE_SANS_SORTIE,
    figure_histogramme,
    figure_histogramme_matrice,
    figures_histogramme_par_pdv,
)
from cfd_dispersion.figures.tirage import MESSAGE_SANS_LOI
from tests.conftest import textes_de

TABLE = {
    "CN": {
        "Biais_Type": 5,
        "Biais_M": 0.0,
        "Biais_ET": 0.02,
        "FE_Type": 6,
        "FE_M": 1.0,
        "FE_ET": 0.08,
    },
    "CX0": {
        "Biais_Type": 3,
        "Biais_M": 0.0,
        "Biais_ET": 0.0015,
        "FE_Type": 4,
        "FE_M": 1.0,
        "FE_ET": 0.06,
    },
}

#: Les nominaux du point de vol unique de ces tests.
NOMINAUX = {"CN": 0.85, "CA": 0.032}


@pytest.fixture(autouse=True)
def _fermer_les_figures() -> Iterator[None]:
    yield
    plt.close("all")


@pytest.fixture(scope="module")
def lois_deux() -> JeuDeLois:
    return charger_lois(TABLE)


@pytest.fixture(scope="module")
def tableau(lois_deux: JeuDeLois) -> pd.DataFrame:
    """Un point de vol, 60 tirages. Les lois portent CX0, la sortie porte CA.

    C'est le cas décalé : le modèle *consomme* un CX0 dispersé et *rend* un CA
    qu'aucune loi ne décrit.
    """
    lot = tirer_lot(lois_deux, 60, graine=3)
    lignes: list[dict[str, Any]] = []
    for tirage in lot:
        disperses = tirage.appliquer({"CN": NOMINAUX["CN"]})
        lignes.append(
            {
                "Mach": 0.85,
                "CN": float(disperses["CN"]),
                # CA n'a pas de loi : il est rendu tel quel, avec sa propre
                # dispersion interne au modèle.
                "CA": NOMINAUX["CA"] * (1.0 + 0.02 * float(tirage["CX0"]["FE"] - 1.0)),
                "DICT_LAW_DISPERSION": TABLE,
                "DICT_TIRAGE": tirage.vers_dict(),
                "tirage": tirage.numero,
            }
        )
    return pd.DataFrame(lignes)


@pytest.fixture(scope="module")
def reference(lois_deux: JeuDeLois) -> pd.DataFrame:
    """Le modèle tourné une fois sans dispersion : ses coefficients sont les nominaux."""
    neutre = tirage_neutre(lois_deux)
    coefficients = neutre.appliquer({"CN": NOMINAUX["CN"]})
    return pd.DataFrame(
        [
            {
                "Mach": 0.85,
                "CN": float(coefficients["CN"]),
                "CA": NOMINAUX["CA"],
                "DICT_TIRAGE": neutre.vers_dict(),
                "tirage": 0,
            }
        ]
    )


class TestFigureHistogramme:
    def test_les_trois_panneaux(self, lois_deux: JeuDeLois) -> None:
        rendue = figure_histogramme(
            "CN",
            lois_deux["CN"],
            biais=np.random.default_rng(0).normal(0, 0.01, 200),
            fe=np.random.default_rng(1).normal(1, 0.03, 200),
            valeurs=np.random.default_rng(2).normal(0.85, 0.03, 200),
            nominal=0.85,
        )
        assert rendue.axes.shape == (3,)
        titres = [ax.get_title() for ax in rendue.axes]
        assert "Biais" in titres[0]
        assert "FE" in titres[1]
        assert "coefficient obtenu" in titres[2]

    def test_l_histogramme_compte_les_tirages(self, lois_deux: JeuDeLois) -> None:
        rendue = figure_histogramme(
            "CN",
            lois_deux["CN"],
            biais=np.zeros(50) + np.linspace(-0.01, 0.01, 50),
            fe=np.linspace(0.95, 1.05, 50),
            valeurs=np.linspace(0.8, 0.9, 50),
            nominal=0.85,
        )
        # Un histogramme = des rectangles ; la loi prescrite = des courbes.
        assert rendue.axes[0].patches
        assert any("n=50" in str(ligne) for ligne in textes_de(rendue.figure))

    def test_la_loi_prescrite_du_coefficient_est_superposee(self, lois_deux: JeuDeLois) -> None:
        rendue = figure_histogramme(
            "CN",
            lois_deux["CN"],
            biais=np.linspace(-0.01, 0.01, 40),
            fe=np.linspace(0.96, 1.04, 40),
            valeurs=np.linspace(0.80, 0.90, 40),
            nominal=0.85,
        )
        libelles = {str(ligne.get_label()) for ligne in rendue.axes[2].get_lines()}
        assert "prescrite (combinée)" in libelles

    def test_le_titre_situe_la_figure(self, lois_deux: JeuDeLois) -> None:
        rendue = figure_histogramme(
            "CN",
            lois_deux["CN"],
            biais=np.linspace(-0.01, 0.01, 10),
            fe=np.linspace(0.96, 1.04, 10),
            valeurs=np.linspace(0.80, 0.90, 10),
            nominal=0.85,
            etiquette="M = 0.85",
        )
        assert any("M = 0.85" in texte for texte in textes_de(rendue.figure))

    def test_elle_s_ecrit_d_un_appel(self, lois_deux: JeuDeLois, tmp_path: Path) -> None:
        rendue = figure_histogramme(
            "CN",
            lois_deux["CN"],
            biais=np.linspace(-0.01, 0.01, 10),
            fe=np.linspace(0.96, 1.04, 10),
            valeurs=np.linspace(0.80, 0.90, 10),
            nominal=0.85,
            chemin=tmp_path / "CN",
        )
        assert [chemin.name for chemin in rendue.fichiers] == ["CN.svg"]


class TestDecalages:
    """Les deux directions, traitées différemment."""

    def test_sans_sortie_le_troisieme_panneau_le_dit(self, lois_deux: JeuDeLois) -> None:
        """Dispersé mais jamais rendu : les deux premiers panneaux valent."""
        rendue = figure_histogramme(
            "CX0",
            lois_deux["CX0"],
            biais=np.linspace(-0.001, 0.001, 30),
            fe=np.linspace(0.97, 1.03, 30),
        )
        assert rendue.axes[0].patches  # l'histogramme du biais est bien là
        assert not rendue.axes[2].patches
        assert MESSAGE_SANS_SORTIE.format(coefficient="CX0") in textes_de(rendue.figure)

    def test_sans_loi_l_histogramme_reste_trace(self) -> None:
        """C'est ce que la figure de tirage ne peut pas faire."""
        rendue = figure_histogramme(
            "CA",
            None,
            valeurs=np.linspace(0.030, 0.034, 40),
            nominal=0.032,
        )
        assert rendue.axes[2].patches
        assert MESSAGE_SANS_LOI.format(coefficient="CA") in textes_de(rendue.figure)

    def test_sans_loi_ni_nominal_l_histogramme_reste_trace(self) -> None:
        rendue = figure_histogramme("CA", None, valeurs=np.linspace(0.03, 0.034, 20))
        assert rendue.axes[2].patches
        # Pas de nominal : pas d'axe en pourcentage.
        assert not rendue.axes[2].child_axes

    def test_ni_loi_ni_valeurs_ne_trace_rien(self) -> None:
        rendue = figure_histogramme("CA", None)
        assert not rendue.axes[2].patches
        assert not rendue.axes[2].get_lines()


class TestMatrice:
    def test_une_ligne_par_coefficient(self, lois_deux: JeuDeLois) -> None:
        (page,) = figure_histogramme_matrice(
            lois_deux,
            obtenues={
                "CN": {
                    "Biais": np.linspace(-0.01, 0.01, 20),
                    "FE": np.linspace(0.96, 1.04, 20),
                    "valeurs": np.linspace(0.8, 0.9, 20),
                },
                "CX0": {
                    "Biais": np.linspace(-0.001, 0.001, 20),
                    "FE": np.linspace(0.97, 1.03, 20),
                },
            },
            nominaux={"CN": 0.85},
        )
        assert page.axes.shape == (2, 3)

    def test_un_coefficient_sans_loi_est_admis(self, lois_deux: JeuDeLois) -> None:
        (page,) = figure_histogramme_matrice(
            lois_deux,
            obtenues={"CA": {"valeurs": np.linspace(0.03, 0.034, 20)}},
            coefficients=["CA"],
            nominaux={"CA": 0.032},
        )
        assert page.axes.shape == (1, 3)
        assert page.axes[0, 2].patches

    def test_une_liste_vide_est_refusee(self, lois_deux: JeuDeLois) -> None:
        with pytest.raises(ValueError, match="aucun coefficient"):
            figure_histogramme_matrice(lois_deux, obtenues={}, coefficients=[])


class TestParcours:
    def test_une_figure_par_coefficient_et_par_point_de_vol(
        self, tableau: pd.DataFrame, reference: pd.DataFrame, tmp_path: Path
    ) -> None:
        inventaire = figures_histogramme_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            reference=reference,
            coefficients=["CN", "CX0", "CA"],
        )
        assert sorted(inventaire["figure"]) == ["CA", "CN", "CX0", "matrice"]
        assert (tmp_path / "CN.svg").is_file()

    def test_l_inventaire_compte_les_tirages(
        self, tableau: pd.DataFrame, reference: pd.DataFrame, tmp_path: Path
    ) -> None:
        inventaire = figures_histogramme_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            reference=reference,
            par_coefficient=False,
        )
        assert list(inventaire.columns) == ["Mach", "tirages", "figure", "fichier"]
        assert inventaire["tirages"].tolist() == [60]

    def test_un_coefficient_de_sortie_sans_loi_est_admis(
        self, tableau: pd.DataFrame, reference: pd.DataFrame, tmp_path: Path
    ) -> None:
        """La différence avec le parcours des tirages, qui le refuse."""
        inventaire = figures_histogramme_par_pdv(
            tableau,
            points_de_vol={"Mach": [0.85]},
            racine=tmp_path,
            reference=reference,
            coefficients=["CA"],
            matrice=False,
        )
        assert list(inventaire["figure"]) == ["CA"]

    def test_un_coefficient_inconnu_partout_est_refuse(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="ni loi ni colonne"):
            figures_histogramme_par_pdv(
                tableau,
                points_de_vol={"Mach": [0.85]},
                racine=tmp_path,
                coefficients=["CL"],
            )

    def test_un_appel_croise_est_refuse(
        self, tableau: pd.DataFrame, reference: pd.DataFrame, tmp_path: Path
    ) -> None:
        """Sept lignes par tirage : l'histogramme mélangerait balayage et dispersion."""
        croise = pd.concat(
            [tableau.assign(alpha=alpha) for alpha in (0.0, 5.0, 10.0)], ignore_index=True
        )
        with pytest.raises(ValueError, match="3 lignes par tirage"):
            figures_histogramme_par_pdv(
                croise,
                points_de_vol={"Mach": [0.85]},
                racine=tmp_path,
                reference=reference,
            )

    def test_le_message_nomme_la_colonne_de_balayage(
        self, tableau: pd.DataFrame, tmp_path: Path
    ) -> None:
        croise = pd.concat([tableau.assign(alpha=alpha) for alpha in (0.0, 5.0)], ignore_index=True)
        with pytest.raises(ValueError, match="alpha"):
            figures_histogramme_par_pdv(croise, points_de_vol={"Mach": [0.85]}, racine=tmp_path)

    def test_un_points_de_vol_vide_est_refuse(self, tableau: pd.DataFrame) -> None:
        with pytest.raises(ValueError, match="points_de_vol est vide"):
            figures_histogramme_par_pdv(tableau, points_de_vol={}, racine="/tmp/x")

    def test_deux_processus_donnent_le_meme_inventaire(
        self, tableau: pd.DataFrame, reference: pd.DataFrame, tmp_path: Path
    ) -> None:
        commun: dict[str, Any] = {
            "points_de_vol": {"Mach": [0.85]},
            "reference": reference,
            "par_coefficient": False,
        }
        seul = figures_histogramme_par_pdv(tableau, racine=tmp_path / "a", **commun)
        deux = figures_histogramme_par_pdv(tableau, racine=tmp_path / "b", n_jobs=2, **commun)
        assert list(seul["figure"]) == list(deux["figure"])
