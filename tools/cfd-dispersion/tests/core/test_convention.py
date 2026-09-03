"""Les relations de reconstruction biais / FE / coefficient."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_dispersion.core.convention import (
    CONVENTION_PAR_DEFAUT,
    CONVENTIONS,
    Convention,
    convention,
)


class TestRelationsLivrees:
    def test_lineaire(self) -> None:
        assert convention("lineaire")(2.0, 0.1, 1.5) == pytest.approx(3.1)

    def test_pourcentage(self) -> None:
        """5 % d'échelle sur 2.0, plus 0.1 de biais."""
        assert convention("pourcentage")(2.0, 0.1, 5.0) == pytest.approx(2.2)

    def test_relatif(self) -> None:
        assert convention("relatif")(2.0, 0.1, 0.05) == pytest.approx(2.2)

    def test_pourcentage_et_relatif_different_d_un_facteur_cent(self) -> None:
        """Les deux conventions qu'on peut confondre sans que rien ne le montre."""
        assert convention("pourcentage")(2.0, 0.0, 5.0) == convention("relatif")(2.0, 0.0, 0.05)

    @pytest.mark.parametrize("nom", sorted(CONVENTIONS))
    def test_un_tirage_nul_laisse_le_coefficient_intact(self, nom: str) -> None:
        """Biais nul et FE neutre doivent rendre le nominal, dans les trois cas."""
        neutre = {"lineaire": 1.0, "pourcentage": 0.0, "relatif": 0.0}[nom]
        assert convention(nom)(3.7, 0.0, neutre) == pytest.approx(3.7)

    @pytest.mark.parametrize("nom", sorted(CONVENTIONS))
    def test_chaque_relation_porte_sa_formule(self, nom: str) -> None:
        formule = CONVENTIONS[nom].formule
        assert "biais" in formule and "FE" in formule

    @pytest.mark.parametrize("nom", sorted(CONVENTIONS))
    def test_chaque_relation_se_diffuse(self, nom: str) -> None:
        resultat = convention(nom)(np.array([1.0, 2.0, 3.0]), 0.1, 0.5)
        assert resultat.shape == (3,)


class TestResolution:
    def test_none_donne_la_convention_par_defaut(self) -> None:
        assert convention(None).nom == CONVENTION_PAR_DEFAUT

    def test_un_objet_convention_passe_tel_quel(self) -> None:
        maison = Convention(nom="maison", formule="c", appliquer=lambda c, b, f: c)
        assert convention(maison) is maison

    def test_un_nom_inconnu_est_refuse_en_listant_les_noms(self) -> None:
        with pytest.raises(ValueError, match="convention inconnue"):
            convention("bogosort")

    def test_le_message_enumere_les_conventions_disponibles(self) -> None:
        with pytest.raises(ValueError, match="lineaire"):
            convention("bogosort")


class TestRelationMaison:
    def test_une_relation_maison_s_applique(self) -> None:
        maison = Convention(
            nom="tabulee",
            formule="biais + FE · c · (1 + c²)",
            appliquer=lambda c, biais, fe: biais + fe * c * (1 + c**2),
        )
        assert maison(2.0, 0.0, 1.0) == pytest.approx(10.0)

    def test_une_relation_maison_est_vectorisee_comme_les_autres(self) -> None:
        maison = Convention(nom="double", formule="2·c", appliquer=lambda c, b, f: 2 * c)
        assert maison(np.arange(4.0), 0.0, 0.0) == pytest.approx([0.0, 2.0, 4.0, 6.0])
