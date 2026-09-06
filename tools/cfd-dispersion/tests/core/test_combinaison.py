"""La loi du coefficient dispersé : voie exacte, voie lissée, et leur accord."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_dispersion.core.combinaison import (
    TOLERANCE_ACCORD,
    LoiCombinee,
    comparer_au_modele,
    decomposition_affine,
    loi_combinee,
)
from cfd_dispersion.core.convention import CONVENTIONS, Convention, convention
from cfd_dispersion.core.loi import LoiDispersion
from cfd_dispersion.core.lois import LoiCoefficient, charger_lois


def _coefficient(biais: LoiDispersion, fe: LoiDispersion, nom: str = "CN") -> LoiCoefficient:
    return LoiCoefficient(nom=nom, biais=biais, fe=fe)


#: Un coefficient représentatif : biais tronqué ±3σ, FE tronqué ±2σ.
CN = _coefficient(LoiDispersion(5, 0.0, 0.02), LoiDispersion(6, 1.0, 0.08))


def carre_du_fe(c: object, biais: object, fe: object) -> np.ndarray:
    """Une relation non affine — fonction de module, donc sérialisable."""
    valeurs = np.asarray(biais, dtype=float) + np.asarray(fe, dtype=float) ** 2 * np.asarray(
        c, dtype=float
    )
    return np.asarray(valeurs, dtype=float)


TORDUE = Convention(nom="tordue", formule="biais + FE² · c", appliquer=carre_du_fe)


class TestDecompositionAffine:
    @pytest.mark.parametrize(
        ("nom", "attendu"),
        [
            ("lineaire", (1.0, 0.85, 0.0)),
            ("pourcentage", (1.0, 0.0085, 0.85)),
            ("relatif", (1.0, 0.85, 0.85)),
        ],
    )
    def test_les_trois_conventions_livrees_sont_affines(
        self, nom: str, attendu: tuple[float, float, float]
    ) -> None:
        poids = decomposition_affine(CONVENTIONS[nom], 0.85)
        assert poids is not None
        assert poids == pytest.approx(attendu)

    def test_une_relation_maison_affine_est_reconnue(self) -> None:
        """``biais + f(c)·FE`` est affine en (biais, FE), si tordu que soit f."""
        maison = Convention(
            nom="maison",
            formule="biais + FE · c · (1 + 0.1·c)",
            appliquer=lambda c, biais, fe: biais + fe * c * (1.0 + 0.1 * c),
        )
        poids = decomposition_affine(maison, 2.0)
        assert poids is not None
        assert poids == pytest.approx((1.0, 2.4, 0.0))

    def test_une_relation_non_affine_est_detectee(self) -> None:
        """Sans ce contrôle, la loi « exacte » serait exactement fausse."""
        assert decomposition_affine(TORDUE, 0.85) is None


class TestVoieExacte:
    def test_les_conventions_livrees_passent_par_la_voie_exacte(self) -> None:
        combinee = loi_combinee(CN, 0.85)
        assert combinee.exacte
        assert combinee.n_lissage == 0
        assert "exacte" in combinee.methode

    def test_la_moyenne_et_l_ecart_type_sont_ceux_de_la_combinaison(self) -> None:
        """Contrôle contre un gros tirage : la loi exacte doit le retrouver."""
        combinee = loi_combinee(CN, 0.85)
        biais = CN.biais.tirer(200_000, graine=7)
        fe = CN.fe.tirer(200_000, graine=8)
        reference = biais + fe * 0.85
        assert combinee.M_theorique == pytest.approx(float(reference.mean()), abs=1e-3)
        assert combinee.ET_theorique == pytest.approx(float(reference.std()), rel=0.02)

    def test_la_convention_pourcentage_ne_donne_pas_la_meme_loi(self) -> None:
        """Deux conventions à un facteur 100 près : elles doivent se distinguer."""
        lineaire = loi_combinee(CN, 0.85, convention_="lineaire")
        pourcent = loi_combinee(CN, 0.85, convention_="pourcentage")
        assert pourcent.ET_theorique < lineaire.ET_theorique / 2.0

    def test_le_support_borne_est_rendu(self) -> None:
        bornes = loi_combinee(CN, 0.85).bornes()
        assert bornes is not None
        bas, haut = bornes
        assert bas == pytest.approx(0.85 * (1.0 - 0.08) - 0.03)
        assert haut == pytest.approx(0.85 * (1.0 + 0.08) + 0.03)

    def test_une_gaussienne_pleine_n_a_pas_de_bornes(self) -> None:
        coefficient = _coefficient(LoiDispersion(4, 0.0, 0.02), LoiDispersion(6, 1.0, 0.08))
        assert loi_combinee(coefficient, 0.85).bornes() is None

    def test_deux_composantes_degenerees_donnent_une_masse(self) -> None:
        coefficient = _coefficient(LoiDispersion(2, 0.001), LoiDispersion(2, 1.0))
        combinee = loi_combinee(coefficient, 0.85)
        assert combinee.est_degeneree
        assert combinee.M_theorique == pytest.approx(0.851)
        assert combinee.ET_theorique == 0.0

    def test_une_composante_degeneree_ne_gene_pas_l_autre(self) -> None:
        """La masse est repliée dans la constante, pas passée comme Dirac."""
        coefficient = _coefficient(LoiDispersion(2, 0.001), LoiDispersion(3, 1.0, 0.05))
        combinee = loi_combinee(coefficient, 0.85)
        assert combinee.exacte
        assert combinee.M_theorique == pytest.approx(0.851)
        assert combinee.ET_theorique > 0.0

    def test_un_nominal_nul_annule_la_contribution_du_facteur_d_echelle(self) -> None:
        """Poids nul : la composante sort de la combinaison, sans la casser."""
        combinee = loi_combinee(CN, 0.0)
        assert combinee.exacte
        assert combinee.ET_theorique == pytest.approx(CN.biais.ET_theorique)


class TestVoieLissee:
    def test_une_relation_non_affine_passe_par_le_lissage(self) -> None:
        combinee = loi_combinee(CN, 0.85, convention_=TORDUE, n=5_000)
        assert not combinee.exacte
        assert combinee.n_lissage == 5_000
        assert "lissée" in combinee.methode

    def test_le_lissage_retrouve_les_moments_de_la_combinaison(self) -> None:
        """« On n'y verra que du feu » : encore faut-il que ce soit vrai."""
        combinee = loi_combinee(CN, 0.85, convention_=TORDUE)
        biais = CN.biais.tirer(200_000, graine=11)
        fe = CN.fe.tirer(200_000, graine=12)
        reference = biais + fe**2 * 0.85
        assert combinee.M_theorique == pytest.approx(float(reference.mean()), abs=2e-3)
        assert combinee.ET_theorique == pytest.approx(float(reference.std()), rel=0.05)

    def test_la_densite_lissee_integre_a_un(self) -> None:
        combinee = loi_combinee(CN, 0.85, convention_=TORDUE)
        grille = np.linspace(*combinee.plage_utile(k=8.0), 2000)
        pas = float(grille[1] - grille[0])
        assert float(np.sum(combinee.pdf(grille)) * pas) == pytest.approx(1.0, abs=0.02)

    def test_le_lissage_est_reproductible(self) -> None:
        """Une figure redessinée doit être la même figure."""
        premier = loi_combinee(CN, 0.85, convention_=TORDUE, n=4_000)
        second = loi_combinee(CN, 0.85, convention_=TORDUE, n=4_000)
        assert premier.ET_theorique == second.ET_theorique

    def test_une_relation_non_affine_mais_constante_donne_une_masse(self) -> None:
        figee = Convention(nom="figee", formule="0", appliquer=lambda c, biais, fe: 0.0 * fe)
        combinee = loi_combinee(CN, 0.85, convention_=figee, n=500)
        assert combinee.est_degeneree


class TestInterface:
    def test_la_densite_a_la_meme_forme_que_les_abscisses(self) -> None:
        combinee = loi_combinee(CN, 0.85)
        assert combinee.pdf(np.linspace(0.8, 0.9, 17)).shape == (17,)

    def test_la_repartition_va_de_zero_a_un(self) -> None:
        combinee = loi_combinee(CN, 0.85)
        bas, haut = combinee.bornes()  # type: ignore[misc]
        assert combinee.cdf([bas, haut]) == pytest.approx([0.0, 1.0], abs=1e-6)

    def test_les_quantiles_encadrent_la_mediane(self) -> None:
        combinee = loi_combinee(CN, 0.85)
        q10, q50, q90 = combinee.quantile([0.1, 0.5, 0.9])
        assert q10 < q50 < q90
        assert q50 == pytest.approx(0.85, abs=1e-3)

    def test_une_probabilite_hors_bornes_est_refusee(self) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            loi_combinee(CN, 0.85).quantile([1.5])

    def test_la_plage_utile_encadre_la_moyenne(self) -> None:
        combinee = loi_combinee(CN, 0.85)
        bas, haut = combinee.plage_utile()
        assert bas < combinee.M_theorique < haut

    def test_la_plage_utile_d_une_masse_n_est_pas_de_largeur_nulle(self) -> None:
        coefficient = _coefficient(LoiDispersion(1), LoiDispersion(1))
        bas, haut = loi_combinee(coefficient, 0.85).plage_utile()
        assert haut > bas

    def test_le_pourcentage_est_relatif_au_nominal(self) -> None:
        combinee = loi_combinee(CN, 0.80)
        assert combinee.pourcent(0.84) == pytest.approx(5.0)

    def test_le_pourcentage_est_indefini_sur_un_nominal_nul(self) -> None:
        """Muet plutôt que faux : rien à diviser par zéro."""
        assert loi_combinee(CN, 0.0).pourcent(0.02) is None

    def test_l_ecart_au_nominal_est_rendu(self) -> None:
        coefficient = _coefficient(LoiDispersion(2, 0.01), LoiDispersion(2, 1.0))
        assert loi_combinee(coefficient, 0.85).ecart == pytest.approx(0.01)

    def test_un_nominal_non_fini_est_refuse(self) -> None:
        with pytest.raises(ValueError, match="finie"):
            loi_combinee(CN, float("nan"))

    def test_la_convention_employee_est_conservee(self) -> None:
        combinee = loi_combinee(CN, 0.85, convention_="relatif")
        assert combinee.convention is convention("relatif")

    def test_elle_se_construit_depuis_un_jeu_de_lois(self) -> None:
        lois = charger_lois(
            {
                "CN": {
                    "Biais_Type": 5,
                    "Biais_M": 0.0,
                    "Biais_ET": 0.02,
                    "FE_Type": 6,
                    "FE_M": 1.0,
                    "FE_ET": 0.08,
                }
            }
        )
        combinee = loi_combinee(lois["CN"], 0.85)
        assert isinstance(combinee, LoiCombinee)
        assert combinee.coefficient == "CN"


class TestAccordAvecLeModele:
    """Le coefficient recalculé contre celui que le modèle a rendu."""

    def test_deux_valeurs_identiques_concordent(self) -> None:
        accord = comparer_au_modele(0.8325, 0.8325, nominal=0.85)
        assert accord.accord
        assert accord.ecart == 0.0
        assert accord.resume == "modèle = calcul"

    def test_un_ecart_est_chiffre_en_absolu_et_en_relatif(self) -> None:
        accord = comparer_au_modele(0.80, 0.84, nominal=0.80)
        assert not accord.accord
        assert accord.ecart == pytest.approx(0.04)
        assert accord.ecart_relatif == pytest.approx(5.0)
        assert "≠" in accord.resume

    def test_l_echelle_vient_du_nominal(self) -> None:
        """Un écart de 0.01 sur un CA de 0.03 n'est pas celui d'un CN de 0.85."""
        petit = comparer_au_modele(0.03, 0.031, nominal=0.03)
        grand = comparer_au_modele(0.85, 0.851, nominal=0.85)
        assert abs(petit.ecart_relatif) > 10 * abs(grand.ecart_relatif)

    def test_sans_nominal_l_echelle_vient_des_valeurs(self) -> None:
        assert comparer_au_modele(1.0, 1.5).ecart_relatif == pytest.approx(100.0 * 0.5 / 1.5)

    def test_deux_zeros_ne_divisent_pas_par_zero(self) -> None:
        accord = comparer_au_modele(0.0, 0.0, nominal=0.0)
        assert accord.accord
        assert accord.ecart_relatif == 0.0

    def test_la_tolerance_est_relative(self) -> None:
        assert comparer_au_modele(0.85, 0.85 + 1e-9, nominal=0.85).accord
        assert not comparer_au_modele(0.85, 0.85 + 1e-3, nominal=0.85).accord

    def test_elle_se_regle(self) -> None:
        assert comparer_au_modele(0.85, 0.851, nominal=0.85, tolerance=0.01).accord

    def test_la_tolerance_par_defaut_est_serree(self) -> None:
        """Les deux doivent être le même nombre, pas deux nombres voisins."""
        assert TOLERANCE_ACCORD == 1e-6

    def test_le_verdict_tient_en_deux_lignes_courtes(self) -> None:
        """La boîte de figure partage sa largeur avec la légende."""
        assert comparer_au_modele(0.85, 0.85).lignes == ("modèle = calcul",)
        assert len(comparer_au_modele(0.85, 0.90).lignes) == 2
