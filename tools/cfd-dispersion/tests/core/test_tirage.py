"""Tirage d'une réalisation et d'un lot — le premier cas d'usage."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cfd_dispersion.core.convention import Convention, convention
from cfd_dispersion.core.lois import JeuDeLois
from cfd_dispersion.core.tirage import Tirage, tirer, tirer_lot


class TestTirageUnique:
    def test_rend_un_biais_et_un_fe_par_coefficient(self, lois: JeuDeLois) -> None:
        t = tirer(lois, graine=42)
        assert set(t) == set(lois)
        assert set(t["Cm_alpha"]) == {"Biais", "FE"}

    def test_s_utilise_comme_le_dict_attendu_par_un_modele(self, lois: JeuDeLois) -> None:
        """C'est le ``DICT_DISP_DRAWN`` que le modèle reçoit."""
        t = tirer(lois, graine=42)
        assert isinstance(t["Cm_alpha"]["Biais"], float)
        assert len(t) == len(lois)
        assert dict(t) == t.vers_dict()

    def test_meme_graine_meme_tirage(self, lois: JeuDeLois) -> None:
        assert tirer(lois, graine=7).vers_dict() == tirer(lois, graine=7).vers_dict()

    def test_graines_differentes_tirages_differents(self, lois: JeuDeLois) -> None:
        assert tirer(lois, graine=7).vers_dict() != tirer(lois, graine=8).vers_dict()

    def test_les_valeurs_respectent_le_support_de_leur_loi(self, lois: JeuDeLois) -> None:
        t = tirer(lois, graine=11)
        for coeff, loi_coeff in lois.items():
            for nom, loi in loi_coeff:
                bas, haut = loi.support()
                assert bas - 1e-12 <= t[coeff][nom] <= haut + 1e-12

    def test_une_composante_degeneree_rend_toujours_sa_valeur(self, lois: JeuDeLois) -> None:
        assert tirer(lois, graine=1)["CA"]["Biais"] == pytest.approx(0.001)

    def test_le_tirage_porte_sa_convention_sa_graine_et_son_plan(self, lois: JeuDeLois) -> None:
        t = tirer(lois, graine=5, convention_="pourcentage", methode="lhs")
        assert t.convention.nom == "pourcentage"
        assert t.graine == 5
        assert t.methode == "lhs"
        assert "pourcentage" not in t.resume  # le résumé porte la formule
        assert "biais + (1 + FE/100) · c" in t.resume
        assert "lhs" in t.resume and "5" in t.resume

    def test_un_coefficient_inconnu_liste_ceux_du_tirage(self, lois: JeuDeLois) -> None:
        with pytest.raises(KeyError, match="Cm_alpha"):
            tirer(lois, graine=1)["CL"]

    def test_vers_serie_met_le_tirage_a_plat(self, lois: JeuDeLois) -> None:
        serie = tirer(lois, graine=1).vers_serie()
        assert isinstance(serie, pd.Series)
        assert "Cm_alpha_Biais" in serie.index
        assert len(serie) == 6


class TestApplication:
    def _tirage(self) -> Tirage:
        return Tirage(
            valeurs={"CN": {"Biais": 0.1, "FE": 1.5}},
            convention=convention("lineaire"),
        )

    def test_applique_la_relation_a_un_scalaire(self) -> None:
        assert self._tirage().appliquer({"CN": 2.0})["CN"] == pytest.approx(3.1)

    def test_applique_le_meme_tirage_a_tout_un_balayage(self) -> None:
        """Le cas corrélé : une erreur de recalage décale la courbe entière."""
        resultat = self._tirage().appliquer({"CN": np.array([0.0, 1.0, 2.0])})["CN"]
        assert resultat == pytest.approx([0.1, 1.6, 3.1])

    def test_une_autre_convention_peut_etre_imposee(self) -> None:
        resultat = self._tirage().appliquer({"CN": 2.0}, convention_="relatif")["CN"]
        assert resultat == pytest.approx(0.1 + 2.5 * 2.0)

    def test_une_convention_maison_s_applique(self) -> None:
        maison = Convention(
            nom="carre", formule="biais + FE·c²", appliquer=lambda c, b, f: b + f * c**2
        )
        resultat = self._tirage().appliquer({"CN": 2.0}, convention_=maison)["CN"]
        assert resultat == pytest.approx(0.1 + 1.5 * 4.0)

    def test_un_coefficient_non_tire_est_refuse(self) -> None:
        with pytest.raises(ValueError, match="absent"):
            self._tirage().appliquer({"CA": 1.0})

    def test_appliquer_ne_traite_que_les_coefficients_demandes(self, lois: JeuDeLois) -> None:
        t = tirer(lois, graine=1)
        assert set(t.appliquer({"CA": 0.3})) == {"CA"}


class TestTirageEnLot:
    def test_une_ligne_par_tirage_une_colonne_par_composante(self, lois: JeuDeLois) -> None:
        lot = tirer_lot(lois, 50, graine=1)
        assert lot.shape == (50, 6)
        assert list(lot.columns) == list(lois.colonnes)

    def test_meme_graine_meme_lot(self, lois: JeuDeLois) -> None:
        pd.testing.assert_frame_equal(tirer_lot(lois, 20, graine=3), tirer_lot(lois, 20, graine=3))

    @pytest.mark.parametrize("methode", ["mc", "lhs", "sobol"])
    def test_les_trois_plans_respectent_les_supports(self, lois: JeuDeLois, methode: str) -> None:
        lot = tirer_lot(lois, 500, graine=2, methode=methode)
        for coeff, loi_coeff in lois.items():
            for nom, loi in loi_coeff:
                bas, haut = loi.support()
                colonne = lot[f"{coeff}_{nom}"]
                assert colonne.min() >= bas - 1e-9
                assert colonne.max() <= haut + 1e-9

    def test_une_colonne_degeneree_est_constante(self, lois: JeuDeLois) -> None:
        assert tirer_lot(lois, 100, graine=1)["CA_Biais"].nunique() == 1

    def test_les_moments_du_lot_suivent_les_lois(self, lois: JeuDeLois) -> None:
        lot = tirer_lot(lois, 20_000, graine=4)
        for coeff, loi_coeff in lois.items():
            for nom, loi in loi_coeff:
                colonne = lot[f"{coeff}_{nom}"]
                assert colonne.mean() == pytest.approx(
                    loi.M_theorique, abs=0.05 * max(loi.ET, 1e-6) + 1e-9
                )
                assert colonne.std() == pytest.approx(loi.ET_theorique, rel=0.06, abs=1e-9)

    def test_le_lot_honore_une_correlation_declaree(
        self, table: dict[str, dict[str, float]]
    ) -> None:
        from cfd_dispersion.core.lois import charger_lois

        jeu = charger_lois(table, correlation={("Cm_alpha", "Cn_beta"): 0.7})
        lot = tirer_lot(jeu, 20_000, graine=6)
        rho = lot["Cm_alpha_Biais"].corr(lot["Cn_beta_Biais"])
        assert rho == pytest.approx(0.7, abs=0.06)

    def test_lhs_couvre_mieux_que_le_monte_carlo(self, lois: JeuDeLois) -> None:
        """La raison de tirer la loi jointe plutôt que chaque loi séparément."""
        trous = {
            m: np.diff(np.sort(tirer_lot(lois, 400, graine=9, methode=m)["Cn_beta_Biais"])).max()
            for m in ("mc", "lhs")
        }
        assert trous["lhs"] < trous["mc"]

    @pytest.mark.parametrize("n", [0, -3])
    def test_un_effectif_non_positif_est_refuse(self, lois: JeuDeLois, n: int) -> None:
        with pytest.raises(ValueError, match="strictement positif"):
            tirer_lot(lois, n)

    def test_une_methode_inconnue_est_refusee(self, lois: JeuDeLois) -> None:
        with pytest.raises(ValueError, match="méthode inconnue"):
            tirer_lot(lois, 5, methode="bogosort")

    def test_le_lot_ne_pollue_pas_le_flux_global(self, lois: JeuDeLois) -> None:
        import openturns as ot

        ot.RandomGenerator.SetSeed(77)
        avant = np.asarray(ot.Normal().getSample(3)).ravel()
        ot.RandomGenerator.SetSeed(77)
        tirer_lot(lois, 100, graine=1234)
        apres = np.asarray(ot.Normal().getSample(3)).ravel()
        assert np.allclose(avant, apres)
