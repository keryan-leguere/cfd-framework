"""La comparaison point à point, et ses cas limites.

Ces cas-là sont la raison d'être du module : une référence nulle, un infini des
deux côtés, un ``NaN``. Chacun a une réponse défendable et une seule, et c'est
ici qu'elle est fixée.
"""

from __future__ import annotations

import numpy as np
import pytest

from cfd_validation.core.ecart import ATOL_DEFAUT, RTOL_DEFAUT, comparer


class TestConformite:
    def test_deux_tableaux_identiques_sont_conformes(self) -> None:
        ecart = comparer([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        assert ecart.conforme
        assert ecart.n_fautifs == 0
        assert ecart.indice_pire is None

    def test_la_tolerance_relative_porte_sur_la_reference(self) -> None:
        ecart = comparer([100.0], [100.0 + 1e-8], rtol=1e-9, atol=0.0)
        assert ecart.conforme  # 1e-8 <= 1e-9 * 100

        serre = comparer([100.0], [100.0 + 1e-6], rtol=1e-9, atol=0.0)
        assert not serre.conforme

    def test_atol_gouverne_au_voisinage_de_zero(self) -> None:
        """Avec une référence nulle, rtol ne peut rien : seul atol décide."""
        assert comparer([0.0], [1e-13], rtol=1.0, atol=1e-12).conforme
        assert not comparer([0.0], [1e-11], rtol=1.0, atol=1e-12).conforme

    def test_les_valeurs_par_defaut_sont_serrees(self) -> None:
        """Une table relue juste l'est au bit près ; le défaut le suppose."""
        assert RTOL_DEFAUT <= 1e-9
        assert ATOL_DEFAUT <= 1e-12


class TestCasLimites:
    def test_un_infini_est_conforme_a_lui_meme(self) -> None:
        """L'égalité stricte passe d'abord, sans quoi |inf − inf| = NaN rejette."""
        ecart = comparer([np.inf, -np.inf], [np.inf, -np.inf])
        assert ecart.conforme

    def test_un_nan_n_est_conforme_a_rien_pas_meme_a_lui_meme(self) -> None:
        """Une table qui porte un NaN est cassée, et le contrôle est là pour le dire."""
        ecart = comparer([np.nan, 1.0], [np.nan, 1.0])
        assert not ecart.conforme
        assert ecart.indices_fautifs.tolist() == [0]

    def test_un_nan_rendu_par_le_modele_est_le_pire_point(self) -> None:
        ecart = comparer([1.0, 2.0, 3.0], [1.0, np.nan, 3.1])
        assert ecart.indice_pire == 1

    def test_une_reference_nulle_donne_un_ecart_relatif_infini(self) -> None:
        """Et non une division silencieuse par zéro."""
        ecart = comparer([0.0, 0.0], [0.0, 1.0])
        assert ecart.relatif[0] == 0.0
        assert np.isinf(ecart.relatif[1])

    def test_un_tableau_vide_se_compare_sans_lever(self) -> None:
        ecart = comparer([], [])
        assert ecart.n == 0
        assert ecart.conforme
        assert np.isnan(ecart.absolu_max)


class TestRefus:
    def test_des_longueurs_differentes_sont_refusees(self) -> None:
        with pytest.raises(ValueError, match="pas la même longueur"):
            comparer([1.0, 2.0], [1.0])

    def test_une_tolerance_negative_est_refusee(self) -> None:
        with pytest.raises(ValueError, match="positives"):
            comparer([1.0], [1.0], rtol=-1.0)


class TestLecture:
    def test_le_pire_point_se_classe_sur_l_ecart_relatif(self) -> None:
        """Un gros écart sur une grande valeur pèse moins qu'un petit sur une petite."""
        ecart = comparer([1000.0, 0.001], [1001.0, 0.002], rtol=1e-9, atol=0.0)
        assert ecart.indice_pire == 1

    def test_les_quantiles_ignorent_les_valeurs_infinies(self) -> None:
        ecart = comparer([1.0, 0.0], [2.0, 1.0])
        quantiles = ecart.quantiles()
        assert np.isfinite(quantiles[1.0])

    def test_les_indices_fautifs_suivent_l_ordre_d_origine(self) -> None:
        ecart = comparer([1.0, 2.0, 3.0, 4.0], [1.0, 9.0, 3.0, 9.0])
        assert ecart.indices_fautifs.tolist() == [1, 3]
