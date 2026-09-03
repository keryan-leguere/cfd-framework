"""Propagation d'une dispersion le long d'un balayage."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from cfd_dispersion.core.bande import (
    INTERVALLES,
    BandeDispersion,
    bande_depuis_loi,
    bande_depuis_points,
)
from cfd_dispersion.core.loi import LoiDispersion
from cfd_dispersion.core.lois import LoiCoefficient


@pytest.fixture
def balayage() -> tuple[np.ndarray, np.ndarray]:
    x = np.linspace(0.0, 10.0, 21)
    return x, 0.1 * x


@pytest.fixture
def loi_cn() -> LoiCoefficient:
    return LoiCoefficient(
        nom="CN",
        biais=LoiDispersion(5, 0.0, 0.02),
        fe=LoiDispersion(6, 1.0, 0.10),
    )


class TestFormeEtContenu:
    def test_les_formes_suivent_le_balayage(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=500, graine=1)

        assert bande.x.shape == x.shape
        assert bande.nominal.shape == x.shape
        assert bande.moyenne.shape == x.shape
        assert bande.bas.shape == x.shape
        assert bande.haut.shape == x.shape
        assert bande.echantillons.shape == (500, x.size)
        assert bande.n_tirages == 500

    def test_l_enveloppe_encadre_la_moyenne(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=1000, graine=1)
        assert np.all(bande.bas <= bande.moyenne)
        assert np.all(bande.moyenne <= bande.haut)

    def test_le_nominal_est_conserve_tel_quel(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=100, graine=1)
        assert bande.nominal == pytest.approx(nominal)

    def test_demi_largeur_et_ecart_type(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=500, graine=1)
        assert bande.demi_largeur == pytest.approx(0.5 * (bande.haut - bande.bas))
        assert bande.ecart_type.shape == x.shape

    def test_biais_et_fe_separes_donnent_le_meme_resultat_que_loi(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        a = bande_depuis_loi(x, nominal, loi=loi_cn, n=200, graine=3)
        b = bande_depuis_loi(x, nominal, biais=loi_cn.biais, fe=loi_cn.fe, n=200, graine=3)
        assert a.echantillons == pytest.approx(b.echantillons)


class TestModeleDeDispersion:
    def test_un_biais_pur_decale_tous_les_points_pareil(
        self, balayage: tuple[np.ndarray, np.ndarray]
    ) -> None:
        """Une constante additive : l'écart au nominal est le même partout."""
        x, nominal = balayage
        loi = LoiCoefficient("CN", LoiDispersion(2, 0.05), LoiDispersion(2, 1.0))
        bande = bande_depuis_loi(x, nominal, loi=loi, n=10, graine=1)
        assert bande.echantillons[0] - nominal == pytest.approx(np.full(x.size, 0.05))

    def test_un_facteur_pur_croit_avec_le_nominal(
        self, balayage: tuple[np.ndarray, np.ndarray]
    ) -> None:
        x, nominal = balayage
        loi = LoiCoefficient("CN", LoiDispersion(1), LoiDispersion(2, 1.10))
        bande = bande_depuis_loi(x, nominal, loi=loi, n=10, graine=1)
        assert bande.echantillons[0] == pytest.approx(1.10 * nominal)

    def test_la_convention_est_respectee(self, balayage: tuple[np.ndarray, np.ndarray]) -> None:
        x, nominal = balayage
        loi = LoiCoefficient("CN", LoiDispersion(2, 0.0), LoiDispersion(2, 5.0))
        bande = bande_depuis_loi(x, nominal, loi=loi, n=5, graine=1, convention_="pourcentage")
        assert bande.echantillons[0] == pytest.approx(1.05 * nominal)
        assert bande.convention.nom == "pourcentage"

    def test_la_moyenne_s_ecarte_du_nominal_quand_la_loi_est_decentree(
        self, balayage: tuple[np.ndarray, np.ndarray]
    ) -> None:
        """C'est cet écart-là que l'analyse est censée révéler."""
        x, nominal = balayage
        loi = LoiCoefficient("CN", LoiDispersion(4, 0.20, 0.02), LoiDispersion(2, 1.0))
        bande = bande_depuis_loi(x, nominal, loi=loi, n=5000, graine=1)
        assert np.mean(bande.moyenne - bande.nominal) == pytest.approx(0.20, abs=0.01)


class TestCorrelation:
    def test_les_realisations_correlees_sont_lisses(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        """Un tirage partagé incline la courbe entière ; il ne la hache pas."""
        x, nominal = balayage
        correle = bande_depuis_loi(x, nominal, loi=loi_cn, n=200, graine=1, correle=True)
        independant = bande_depuis_loi(x, nominal, loi=loi_cn, n=200, graine=1, correle=False)

        def rugosite(echantillons: np.ndarray) -> float:
            return float(np.abs(np.diff(echantillons[0], n=2)).mean())

        assert rugosite(correle.echantillons) < rugosite(independant.echantillons)

    def test_le_drapeau_correle_est_reporte(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        assert bande_depuis_loi(x, nominal, loi=loi_cn, n=50, graine=1).correle is True
        assert (
            bande_depuis_loi(x, nominal, loi=loi_cn, n=50, graine=1, correle=False).correle is False
        )

    def test_les_points_correles_le_sont_reellement(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=2000, graine=1)
        rho = np.corrcoef(bande.echantillons[:, 5], bande.echantillons[:, 15])[0, 1]
        assert rho > 0.9

    def test_les_points_independants_ne_le_sont_pas(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=2000, graine=1, correle=False)
        rho = np.corrcoef(bande.echantillons[:, 5], bande.echantillons[:, 15])[0, 1]
        assert abs(rho) < 0.15


class TestIntervalles:
    def test_les_trois_reductions_existent(self) -> None:
        assert set(INTERVALLES) == {"percentile", "sigma", "minmax"}

    def test_minmax_est_l_enveloppe_extreme(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=500, graine=1, intervalle="minmax")
        assert bande.bas == pytest.approx(bande.echantillons.min(axis=0))
        assert bande.haut == pytest.approx(bande.echantillons.max(axis=0))
        assert bande.label == "min/max"

    def test_minmax_contient_toute_autre_enveloppe(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        base = bande_depuis_loi(x, nominal, loi=loi_cn, n=500, graine=1, intervalle="minmax")
        etroite = base.reduire(intervalle="percentile", niveau=0.95)
        assert np.all(base.bas <= etroite.bas)
        assert np.all(etroite.haut <= base.haut)

    def test_percentile_couvre_la_fraction_demandee(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=5000, graine=1, couverture=0.90)
        colonne = bande.echantillons[:, 10]
        dedans = np.mean((colonne >= bande.bas[10]) & (colonne <= bande.haut[10]))
        assert dedans == pytest.approx(0.90, abs=0.02)

    def test_sigma_vaut_moyenne_plus_ou_moins_k_sigma(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(
            x, nominal, loi=loi_cn, n=1000, graine=1, intervalle="sigma", k=2.0
        )
        assert bande.haut - bande.moyenne == pytest.approx(2.0 * bande.ecart_type)

    def test_enveloppe_sigma_donne_les_lignes_a_k_sigma(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=1000, graine=1)
        bas, haut = bande.enveloppe_sigma(3.0)
        assert haut - bas == pytest.approx(6.0 * bande.ecart_type)

    def test_enveloppe_sigma_refuse_un_k_nul(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=50, graine=1)
        with pytest.raises(ValueError, match="strictement positif"):
            bande.enveloppe_sigma(0.0)

    @pytest.mark.parametrize(
        ("kwargs", "motif"),
        [
            ({"intervalle": "minmax", "couverture": 0.9}, "n'a pas de niveau"),
            ({"intervalle": "minmax", "k": 2.0}, "n'a pas de niveau"),
            ({"intervalle": "percentile", "k": 2.0}, "sigma"),
            ({"intervalle": "sigma", "couverture": 0.9}, "percentile"),
            ({"intervalle": "zzz"}, "intervalle inconnu"),
        ],
    )
    def test_les_reglages_incompatibles_sont_refuses(
        self,
        balayage: tuple[np.ndarray, np.ndarray],
        loi_cn: LoiCoefficient,
        kwargs: dict[str, Any],
        motif: str,
    ) -> None:
        x, nominal = balayage
        with pytest.raises(ValueError, match=motif):
            bande_depuis_loi(x, nominal, loi=loi_cn, n=20, **kwargs)

    def test_une_couverture_hors_bornes_est_refusee(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        with pytest.raises(ValueError, match=r"\(0, 1\)"):
            bande_depuis_loi(x, nominal, loi=loi_cn, n=20, couverture=1.5)


class TestLabel:
    @pytest.mark.parametrize(
        ("intervalle", "niveau", "attendu"),
        [
            ("percentile", 0.95, "95 %"),
            ("sigma", 2.0, "±2σ"),
            ("sigma", 1.5, "±1.5σ"),
            ("minmax", 1.0, "min/max"),
        ],
    )
    def test_label(
        self,
        balayage: tuple[np.ndarray, np.ndarray],
        loi_cn: LoiCoefficient,
        intervalle: str,
        niveau: float,
        attendu: str,
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=50, graine=1)
        assert bande.reduire(intervalle=intervalle, niveau=niveau).label == attendu


class TestReduire:
    def test_reduire_ne_retire_pas(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=500, graine=1)
        autre = bande.reduire(intervalle="sigma", niveau=1.0)
        assert autre.echantillons is bande.echantillons
        assert autre.moyenne is bande.moyenne

    def test_reduire_conserve_les_metadonnees(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=100, graine=1, convention_="relatif")
        autre = bande.reduire(intervalle="minmax")
        assert autre.correle == bande.correle
        assert autre.convention.nom == "relatif"

    def test_reduire_sans_argument_ne_change_rien(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=100, graine=1)
        assert bande.reduire().bas == pytest.approx(bande.bas)

    def test_changer_d_intervalle_prend_le_niveau_par_defaut(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=100, graine=1)
        assert bande.reduire(intervalle="sigma").niveau == 2.0


class TestDepuisPoints:
    def test_une_loi_par_point(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_points(x, nominal, [loi_cn] * x.size, n=200, graine=1)
        assert bande.echantillons.shape == (200, x.size)
        assert bande.correle is False

    def test_une_dispersion_croissante_elargit_la_bande(
        self, balayage: tuple[np.ndarray, np.ndarray]
    ) -> None:
        """Le cas qui motive la fonction : l'incertitude qui croît après décrochage."""
        x, nominal = balayage
        lois = [
            LoiCoefficient("CN", LoiDispersion(4, 0.0, 0.002 * (i + 1)), LoiDispersion(2, 1.0))
            for i in range(x.size)
        ]
        bande = bande_depuis_points(x, nominal, lois, n=2000, graine=1)
        largeur = bande.haut - bande.bas
        assert largeur[-1] > 3.0 * largeur[0]

    def test_le_nombre_de_lois_doit_suivre_le_balayage(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        with pytest.raises(ValueError, match="doivent correspondre"):
            bande_depuis_points(x, nominal, [loi_cn] * 3, n=10)


class TestReproductibilite:
    def test_meme_graine_meme_bande(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        a = bande_depuis_loi(x, nominal, loi=loi_cn, n=200, graine=5)
        b = bande_depuis_loi(x, nominal, loi=loi_cn, n=200, graine=5)
        assert a.echantillons == pytest.approx(b.echantillons)

    def test_graines_differentes_bandes_differentes(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        a = bande_depuis_loi(x, nominal, loi=loi_cn, n=200, graine=5)
        b = bande_depuis_loi(x, nominal, loi=loi_cn, n=200, graine=6)
        assert not np.allclose(a.echantillons, b.echantillons)


class TestValidationDesEntrees:
    def test_x_doit_etre_1d(self, loi_cn: LoiCoefficient) -> None:
        with pytest.raises(ValueError, match="1-D"):
            bande_depuis_loi(np.zeros((2, 2)), np.zeros((2, 2)), loi=loi_cn, n=10)

    def test_x_et_nominal_doivent_correspondre(self, loi_cn: LoiCoefficient) -> None:
        with pytest.raises(ValueError, match="doivent correspondre"):
            bande_depuis_loi(np.arange(5.0), np.arange(3.0), loi=loi_cn, n=10)

    def test_il_faut_une_loi_ou_deux_composantes(
        self, balayage: tuple[np.ndarray, np.ndarray]
    ) -> None:
        x, nominal = balayage
        with pytest.raises(ValueError, match="soit loi="):
            bande_depuis_loi(x, nominal, n=10)

    def test_loi_et_composantes_s_excluent(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        with pytest.raises(ValueError, match="pas les deux"):
            bande_depuis_loi(x, nominal, loi=loi_cn, biais=loi_cn.biais, fe=loi_cn.fe, n=10)


class TestDataclass:
    def test_la_bande_est_gelee(
        self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient
    ) -> None:
        x, nominal = balayage
        bande = bande_depuis_loi(x, nominal, loi=loi_cn, n=20, graine=1)
        with pytest.raises(Exception):  # noqa: B017 - FrozenInstanceError
            bande.moyenne = np.zeros(3)  # type: ignore[misc]

    def test_type(self, balayage: tuple[np.ndarray, np.ndarray], loi_cn: LoiCoefficient) -> None:
        x, nominal = balayage
        assert isinstance(bande_depuis_loi(x, nominal, loi=loi_cn, n=20, graine=1), BandeDispersion)
