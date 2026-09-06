"""Superposition d'une dispersion sur une polaire."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from matplotlib.axes import Axes

from cfd_dispersion.core.lois import JeuDeLois
from cfd_dispersion.figures._base import assombrir, nouvelle_figure, tracer_ligne
from cfd_dispersion.figures.polaire import (
    courbes_par_tirage,
    nominal_depuis_tableau,
    superposer_depuis_tableau,
    superposer_dispersion,
)


@pytest.fixture(autouse=True)
def _fermer_les_figures() -> Iterator[None]:
    yield
    plt.close("all")


@pytest.fixture
def polaire() -> tuple[Axes, np.ndarray, np.ndarray]:
    """Des axes portant deux séries nominales, comme batch_plot en produit."""
    alpha = np.linspace(0.0, 12.0, 25)
    CN = 0.09 * alpha + 0.004 * alpha**2
    _, ax = nouvelle_figure()
    tracer_ligne(ax, alpha, CN, label="KW", color="C0")
    tracer_ligne(ax, alpha, 0.97 * CN, label="SA", color="C1")
    return ax, alpha, CN


@pytest.fixture
def nuage(lois: JeuDeLois, polaire: tuple[Axes, np.ndarray, np.ndarray]) -> np.ndarray:
    """400 courbes, comme un modèle appelé 400 fois en rendrait."""
    from cfd_dispersion.core.tirage import tirer_tableau

    _, _, CN = polaire
    lot = tirer_tableau(lois, 400, graine=7)
    return np.array([b + f * CN for b, f in zip(lot["Cn_beta_Biais"], lot["Cn_beta_FE"])])


class TestSuperposerDispersion:
    def test_rend_les_artistes_crees(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(ax, alpha, CN, loi=lois["Cn_beta"], n=500, graine=1)
        assert artistes["bande"] is not None
        assert artistes["moyenne"] is not None
        assert artistes["objet_bande"] is not None
        assert len(artistes["sigmas"]) == 6  # trois sigmas, deux branches
        assert len(artistes["etiquettes"]) == 6

    def test_la_bande_theorique_vient_de_la_loi(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(ax, alpha, CN, loi=lois["Cn_beta"], n=800, graine=1)
        assert artistes["objet_bande"].n_tirages == 800

    def test_les_tirages_du_modele_sont_traces(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois, nuage: np.ndarray
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(
            ax, alpha, CN, tirages=nuage, couleur="C2", max_tirages=None
        )
        assert len(artistes["tirages"]) == 400

    def test_les_tirages_sont_plafonnes(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], nuage: np.ndarray
    ) -> None:
        """Mille courbes opaques ne montrent rien de plus que deux cents."""
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(ax, alpha, CN, tirages=nuage, couleur="C2", max_tirages=50)
        assert len(artistes["tirages"]) <= 50

    def test_loi_et_tirages_cohabitent(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois, nuage: np.ndarray
    ) -> None:
        """Les voir se superposer est précisément l'intérêt."""
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(
            ax, alpha, CN, loi=lois["Cn_beta"], tirages=nuage, n=500, graine=1
        )
        assert artistes["tirages"] and artistes["objet_bande"] is not None


class TestRattachementALaSerie:
    def test_serie_reprend_la_couleur_de_la_courbe(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(
            ax, alpha, CN, loi=lois["Cn_beta"], serie="SA", n=300, graine=1
        )
        assert artistes["couleur"] == "C1"

    def test_la_moyenne_est_plus_sombre_que_la_serie(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        """C'est ce qui rattache la dispersion à sa série sans légende."""
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(
            ax, alpha, CN, loi=lois["Cn_beta"], serie="KW", n=300, graine=1
        )
        import matplotlib.colors as mcolors

        moyenne = mcolors.to_rgb(artistes["moyenne"].get_color())
        assert moyenne == pytest.approx(assombrir("C0", 0.25), abs=1e-6)
        assert sum(moyenne) < sum(mcolors.to_rgb("C0"))

    def test_couleur_explicite_pour_un_faisceau_autonome(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(
            ax, alpha, CN, loi=lois["Cn_beta"], couleur="C3", n=300, graine=1
        )
        assert artistes["couleur"] == "C3"

    def test_serie_et_couleur_s_excluent(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        with pytest.raises(ValueError, match="pas les deux"):
            superposer_dispersion(
                ax, alpha, CN, loi=lois["Cn_beta"], serie="KW", couleur="C3", n=100
            )

    def test_une_serie_absente_liste_celles_presentes(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        with pytest.raises(ValueError, match="KW"):
            superposer_dispersion(ax, alpha, CN, loi=lois["Cn_beta"], serie="EXP", n=100)


class TestRemplissageEtSigmas:
    @pytest.mark.parametrize("remplissage", ["minmax", "percentile", "sigma"])
    def test_les_trois_remplissages(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois, remplissage: str
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(
            ax, alpha, CN, loi=lois["Cn_beta"], n=400, graine=1, remplissage=remplissage
        )
        assert artistes["bande"] is not None
        assert artistes["objet_bande"].intervalle == remplissage

    def test_aucun_remplissage(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(
            ax, alpha, CN, loi=lois["Cn_beta"], n=300, graine=1, remplissage=None
        )
        assert artistes["bande"] is None

    def test_le_nombre_de_sigmas_est_reglable(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(
            ax, alpha, CN, loi=lois["Cn_beta"], n=300, graine=1, sigmas=(2,)
        )
        assert len(artistes["sigmas"]) == 2
        assert len(artistes["etiquettes"]) == 2

    def test_aucun_sigma(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(
            ax, alpha, CN, loi=lois["Cn_beta"], n=300, graine=1, sigmas=()
        )
        assert artistes["sigmas"] == []

    def test_les_etiquettes_peuvent_etre_coupees(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(
            ax, alpha, CN, loi=lois["Cn_beta"], n=300, graine=1, etiquettes_sigma=False
        )
        assert artistes["sigmas"] and artistes["etiquettes"] == []

    def test_les_etiquettes_nomment_chaque_sigma(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(ax, alpha, CN, loi=lois["Cn_beta"], n=300, graine=1)
        textes = {e.get_text() for e in artistes["etiquettes"]}
        assert textes == {"+1σ", "−1σ", "+2σ", "−2σ", "+3σ", "−3σ"}

    def test_les_deux_branches_sont_decalees_le_long_de_la_courbe(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        """Sinon +kσ et −kσ se chevauchent dès que la bande est étroite."""
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(ax, alpha, CN, loi=lois["Cn_beta"], n=300, graine=1)
        positions = {e.get_text(): e.get_position()[0] for e in artistes["etiquettes"]}
        assert positions["+1σ"] != positions["−1σ"]

    def test_les_etiquettes_sont_posees_apres_tout_le_reste(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        """Leur inclinaison lit la transformation des axes : elle doit être finale."""
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(ax, alpha, CN, loi=lois["Cn_beta"], n=300, graine=1)
        etiquette = artistes["etiquettes"][0]
        assert etiquette.get_rotation() != 0.0


class TestBoiteDeParametres:
    def test_la_boite_nomme_la_loi_et_la_convention(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(ax, alpha, CN, loi=lois["Cn_beta"], n=300, graine=1)
        texte = artistes["boite"].get_text()
        assert "Uniforme" in texte  # le biais de Cn_beta
        assert "biais + FE · c" in texte
        assert "n = 300" in texte

    def test_la_boite_dit_si_le_tirage_est_correle(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        correle = superposer_dispersion(ax, alpha, CN, loi=lois["Cn_beta"], n=300, graine=1)
        assert "corrélé" in correle["boite"].get_text()

    def test_la_boite_compte_les_tirages_du_modele(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois, nuage: np.ndarray
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(
            ax, alpha, CN, loi=lois["Cn_beta"], tirages=nuage, n=300, graine=1
        )
        assert "400 tirages du modèle" in artistes["boite"].get_text()

    def test_la_boite_peut_etre_coupee(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        artistes = superposer_dispersion(
            ax, alpha, CN, loi=lois["Cn_beta"], n=300, graine=1, boite_parametres=False
        )
        assert artistes["boite"] is None


class TestValidationDesEntrees:
    def test_il_faut_une_loi_ou_des_tirages(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray]
    ) -> None:
        ax, alpha, CN = polaire
        with pytest.raises(ValueError, match="passer au moins"):
            superposer_dispersion(ax, alpha, CN)

    def test_x_doit_etre_1d(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, _, _ = polaire
        with pytest.raises(ValueError, match="1-D"):
            superposer_dispersion(ax, np.zeros((2, 2)), np.zeros((2, 2)), loi=lois["Cn_beta"])

    def test_nominal_doit_suivre_x(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, _ = polaire
        with pytest.raises(ValueError, match="doivent correspondre"):
            superposer_dispersion(ax, alpha, np.zeros(3), loi=lois["Cn_beta"])

    def test_les_tirages_doivent_suivre_x(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        with pytest.raises(ValueError, match="doivent correspondre"):
            superposer_dispersion(ax, alpha, CN, tirages=np.zeros((10, 3)))


class TestCourbesParTirage:
    def _plat(self, n_tirages: int = 5, npts: int = 25) -> pd.DataFrame:
        alpha = np.linspace(0.0, 12.0, npts)
        return pd.DataFrame(
            {
                "alpha": np.tile(alpha, n_tirages),
                "CN": np.repeat(np.arange(n_tirages, dtype=float), npts)
                + np.tile(alpha, n_tirages),
                "tirage": np.repeat(np.arange(n_tirages), npts),
            }
        )

    def test_regroupe_en_une_courbe_par_tirage(self) -> None:
        x, courbes = courbes_par_tirage(self._plat(), x="alpha", y="CN", par=["tirage"])
        assert x.shape == (25,)
        assert courbes.shape == (5, 25)

    def test_les_courbes_sont_triees_par_abscisse(self) -> None:
        melange = self._plat().sample(frac=1.0, random_state=0)
        x, _ = courbes_par_tirage(melange, x="alpha", y="CN", par=["tirage"])
        assert np.all(np.diff(x) > 0)

    def test_le_resultat_se_passe_a_superposer_dispersion(
        self, polaire: tuple[Axes, np.ndarray, np.ndarray], lois: JeuDeLois
    ) -> None:
        ax, alpha, CN = polaire
        plat = self._plat(npts=alpha.size)
        plat["alpha"] = np.tile(alpha, 5)
        _, courbes = courbes_par_tirage(plat, x="alpha", y="CN", par=["tirage"])
        artistes = superposer_dispersion(ax, alpha, CN, tirages=courbes, couleur="C2")
        assert len(artistes["tirages"]) == 5

    def test_grouper_sur_les_colonnes_du_tirage(self, lois: JeuDeLois) -> None:
        """Le cas réel : la clé est le tirage lui-même, pas un numéro."""
        from cfd_dispersion.core.tirage import tirer_tableau

        alpha = np.linspace(0.0, 10.0, 11)
        lot = tirer_tableau(lois, 6, graine=3)
        lignes = []
        for _, tirage in lot.iterrows():
            morceau = pd.DataFrame({"alpha": alpha, "CN": tirage["Cn_beta_Biais"] + alpha})
            morceau["Cn_beta_Biais"] = tirage["Cn_beta_Biais"]
            morceau["Cn_beta_FE"] = tirage["Cn_beta_FE"]
            lignes.append(morceau)
        plat = pd.concat(lignes, ignore_index=True)

        _, courbes = courbes_par_tirage(
            plat, x="alpha", y="CN", par=["Cn_beta_Biais", "Cn_beta_FE"]
        )
        assert courbes.shape == (6, 11)

    def test_des_abscisses_differentes_sont_refusees(self) -> None:
        """Les empiler donnerait un tableau dont les colonnes ne veulent rien dire."""
        plat = self._plat(n_tirages=2, npts=5)
        plat.loc[plat["tirage"] == 1, "alpha"] += 0.5
        with pytest.raises(ValueError, match="même abscisse"):
            courbes_par_tirage(plat, x="alpha", y="CN", par=["tirage"])

    def test_une_colonne_absente_est_nommee(self) -> None:
        with pytest.raises(ValueError, match="CL"):
            courbes_par_tirage(self._plat(), x="alpha", y="CL", par=["tirage"])

    def test_par_ne_peut_pas_etre_vide(self) -> None:
        with pytest.raises(ValueError, match="au moins une colonne"):
            courbes_par_tirage(self._plat(), x="alpha", y="CN", par=[])

    def test_un_tableau_vide_est_refuse(self) -> None:
        vide = self._plat().iloc[0:0]
        with pytest.raises(ValueError, match="vide"):
            courbes_par_tirage(vide, x="alpha", y="CN", par=["tirage"])


class TestSuperposerDepuisTableau:
    """L'entrée table : celle qu'on a sous la main après le modèle."""

    @pytest.fixture
    def tableau(self) -> pd.DataFrame:
        """Une polaire dispersée à plat : 20 tirages × 5 incidences."""
        alpha = np.linspace(0.0, 12.0, 5)
        lignes = []
        for numero in range(20):
            facteur = 1.0 + 0.01 * (numero - 10)
            for x, y in zip(alpha, 0.1 * alpha * facteur):
                lignes.append({"alpha": x, "CN": y, "tirage": numero, "Mach": 0.8})
        return pd.DataFrame(lignes)

    @pytest.fixture
    def reference_polaire(self) -> pd.DataFrame:
        alpha = np.linspace(0.0, 12.0, 5)
        return pd.DataFrame({"alpha": alpha, "CN": 0.1 * alpha, "Mach": 0.8})

    def test_elle_trace_a_partir_du_tableau(
        self, tableau: pd.DataFrame, reference_polaire: pd.DataFrame
    ) -> None:
        _, ax = nouvelle_figure()
        artistes = superposer_depuis_tableau(
            ax, tableau, x="alpha", y="CN", reference=reference_polaire
        )
        assert artistes["bande"] is not None
        assert len(artistes["tirages"]) == 20

    def test_la_reference_peut_etre_un_tableau_de_valeurs(self, tableau: pd.DataFrame) -> None:
        _, ax = nouvelle_figure()
        artistes = superposer_depuis_tableau(ax, tableau, x="alpha", y="CN", reference=np.zeros(5))
        assert artistes["objet_bande"] is not None
        assert artistes["objet_bande"].nominal == pytest.approx(np.zeros(5))

    def test_sans_reference_la_moyenne_des_tirages_sert_de_nominal(
        self, tableau: pd.DataFrame
    ) -> None:
        """Correct si les lois sont centrées ; le biais devient invisible sinon."""
        _, ax = nouvelle_figure()
        artistes = superposer_depuis_tableau(ax, tableau, x="alpha", y="CN")
        bande = artistes["objet_bande"]
        assert bande.nominal == pytest.approx(bande.moyenne)

    def test_une_reference_mal_alignee_est_refusee(self, tableau: pd.DataFrame) -> None:
        """Sinon la bande se poserait à côté de sa courbe."""
        decalee = pd.DataFrame({"alpha": np.linspace(0.0, 12.0, 7), "CN": np.zeros(7)})
        _, ax = nouvelle_figure()
        with pytest.raises(ValueError, match="ne sont pas celles des tirages"):
            superposer_depuis_tableau(ax, tableau, x="alpha", y="CN", reference=decalee)

    def test_les_options_passent(
        self, tableau: pd.DataFrame, reference_polaire: pd.DataFrame
    ) -> None:
        _, ax = nouvelle_figure()
        artistes = superposer_depuis_tableau(
            ax,
            tableau,
            x="alpha",
            y="CN",
            reference=reference_polaire,
            remplissage="sigma",
            k=1.0,
            max_tirages=0,
        )
        assert artistes["tirages"] == []
        assert artistes["objet_bande"].label == "±1σ"

    def test_une_colonne_absente_est_refusee(self, tableau: pd.DataFrame) -> None:
        _, ax = nouvelle_figure()
        with pytest.raises(ValueError, match="CL"):
            superposer_depuis_tableau(ax, tableau, x="alpha", y="CL")


class TestNominalDepuisTableau:
    def test_il_lit_la_courbe_dans_l_ordre_des_abscisses(self) -> None:
        melange = pd.DataFrame({"alpha": [2.0, 0.0, 1.0], "CN": [0.2, 0.0, 0.1]})
        assert nominal_depuis_tableau(melange, x="alpha", y="CN") == pytest.approx([0.0, 0.1, 0.2])

    def test_une_abscisse_repetee_est_refusee(self) -> None:
        """Une référence porte une ligne par point : deux, c'est un tableau de tirages."""
        double = pd.DataFrame({"alpha": [0.0, 0.0], "CN": [0.1, 0.2]})
        with pytest.raises(ValueError, match="plusieurs lignes"):
            nominal_depuis_tableau(double, x="alpha", y="CN")

    def test_une_colonne_absente_est_refusee(self) -> None:
        with pytest.raises(ValueError, match="absente"):
            nominal_depuis_tableau(pd.DataFrame({"alpha": [0.0]}), x="alpha", y="CN")


class TestChiffresDeLaDispersion:
    """Les nombres, en légende et dans la boîte."""

    @pytest.fixture
    def axes_traces(self) -> Any:
        x = np.linspace(0.0, 10.0, 11)
        nominal = np.full_like(x, 2.0)
        courbes = np.vstack([nominal - 0.05 * x, nominal, nominal + 0.05 * x])
        _, ax = nouvelle_figure()
        return ax, x, nominal, courbes

    def test_la_legende_porte_le_chiffre_de_tete(self, axes_traces: Any) -> None:
        ax, x, nominal, courbes = axes_traces
        artistes = superposer_dispersion(ax, x, nominal, tirages=courbes)
        assert "50.0 % max" in str(artistes["bande"].get_label())

    def test_il_se_coupe(self, axes_traces: Any) -> None:
        ax, x, nominal, courbes = axes_traces
        artistes = superposer_dispersion(ax, x, nominal, tirages=courbes, chiffres_legende=False)
        assert "%" not in str(artistes["bande"].get_label())

    def test_la_boite_chiffre_l_enveloppe(self, axes_traces: Any) -> None:
        ax, x, nominal, courbes = axes_traces
        artistes = superposer_dispersion(ax, x, nominal, tirages=courbes)
        texte = artistes["boite"].get_text()
        assert "enveloppe max" in texte
        assert "σ max" in texte
        assert "écart moyen/nominal" in texte
