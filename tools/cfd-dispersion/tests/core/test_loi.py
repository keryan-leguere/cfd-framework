"""Les six lois : correspondance OpenTURNS, supports, moments, tirage."""

from __future__ import annotations

import math

import numpy as np
import openturns as ot
import pytest

from cfd_dispersion.core.loi import (
    LIBELLES_TYPE,
    TYPES_VALIDES,
    LoiDispersion,
    libelle_type,
)

# ---------------------------------------------------------------------------
# Référence : l'implémentation SciPy que ce paquet remplace
# ---------------------------------------------------------------------------

#: Moments et supports mesurés sur 400 000 tirages de l'ancien
#: ``cfd_plot.dispersion.DispersionSpec`` (SciPy), avant sa suppression.
#:
#: C'est le garde-fou du portage : OpenTURNS et SciPy n'ont pas le même flux
#: aléatoire, donc les *valeurs* diffèrent à graine égale — mais les *lois*
#: doivent coïncider. Ces nombres sont figés ici précisément parce que le code
#: qui les a produits n'existe plus : sans eux, plus rien ne distinguerait
#: « porté » de « silencieusement modifié ».
#:
#: (type, M, ET) -> (moyenne, écart-type, min, max)
REFERENCE_SCIPY: dict[tuple[int, float, float], tuple[float, float, float, float]] = {
    (1, 0.0, 0.0): (0.0, 0.0, 0.0, 0.0),
    (2, 0.5, 0.0): (0.5, 0.0, 0.5, 0.5),
    (3, 0.5, 0.2): (0.5001346504, 0.1154611450, 0.3000008372, 0.6999992564),
    (4, 0.5, 0.2): (0.5001084934, 0.0999701612, 0.0504910255, 0.9649021190),
    (5, 0.5, 0.2): (0.5000609912, 0.0985331970, 0.2000470683, 0.7999581913),
    (6, 0.5, 0.2): (0.5000697581, 0.0878912944, 0.3000037003, 0.6999967135),
    (4, -1.5, 0.8): (-1.4995660265, 0.3998806447, -3.2980358982, 0.3596084761),
    (6, 0.0, 0.05): (0.0000174395, 0.0219728236, -0.0499990749, 0.0499991784),
    (3, -2.0, 1.0): (-1.9993267479, 0.5773057248, -2.9999958138, -1.0000037182),
    (5, 10.0, 4.0): (10.0012198239, 1.9706639391, 4.0009413655, 15.9991638269),
}


class TestPortageDepuisScipy:
    """Le portage ne doit pas avoir changé les lois."""

    @pytest.mark.parametrize("cle", sorted(REFERENCE_SCIPY))
    def test_les_moments_coincident_avec_l_ancienne_implementation(
        self, cle: tuple[int, float, float]
    ) -> None:
        type_loi, M, ET = cle
        moy_ref, et_ref, _, _ = REFERENCE_SCIPY[cle]
        loi = LoiDispersion(type_loi, M, ET)

        echantillon = loi.tirer(400_000, graine=20260902)

        assert echantillon.mean() == pytest.approx(moy_ref, abs=5e-3 * max(1.0, abs(moy_ref)))
        assert echantillon.std() == pytest.approx(et_ref, rel=5e-3, abs=1e-12)

    @pytest.mark.parametrize("cle", sorted(REFERENCE_SCIPY))
    def test_l_ecart_type_theorique_predit_l_ancien_tirage(
        self, cle: tuple[int, float, float]
    ) -> None:
        """La valeur exacte d'OpenTURNS retrouve l'écart-type empirique SciPy.

        C'est le contrôle le plus fin des deux : il compare une formule fermée
        à un tirage, sans passer par un tirage OpenTURNS.
        """
        type_loi, M, ET = cle
        _, et_ref, _, _ = REFERENCE_SCIPY[cle]

        assert LoiDispersion(type_loi, M, ET).ET_theorique == pytest.approx(
            et_ref, rel=5e-3, abs=1e-12
        )

    @pytest.mark.parametrize("cle", sorted(REFERENCE_SCIPY))
    def test_les_supports_coincident(self, cle: tuple[int, float, float]) -> None:
        type_loi, M, ET = cle
        _, _, mini_ref, maxi_ref = REFERENCE_SCIPY[cle]
        loi = LoiDispersion(type_loi, M, ET)

        bas, haut = loi.support()
        if loi.est_bornee:
            assert bas == pytest.approx(mini_ref, abs=1e-2 * max(1.0, abs(mini_ref)))
            assert haut == pytest.approx(maxi_ref, abs=1e-2 * max(1.0, abs(maxi_ref)))
        else:
            # La gaussienne pleine : l'ancien tirage était forcément borné,
            # le support ne l'est pas.
            assert math.isinf(bas) and math.isinf(haut)
            assert mini_ref > bas and maxi_ref < haut


# ---------------------------------------------------------------------------
# La correspondance avec OpenTURNS, type par type
# ---------------------------------------------------------------------------


class TestCorrespondanceOpenTurns:
    @pytest.mark.parametrize(
        ("type_loi", "attendu"),
        [
            (1, ot.Dirac),
            (2, ot.Dirac),
            (3, ot.Uniform),
            (4, ot.Normal),
            (5, ot.TruncatedNormal),
            (6, ot.TruncatedNormal),
        ],
    )
    def test_chaque_type_construit_la_bonne_distribution(
        self, type_loi: int, attendu: type
    ) -> None:
        loi = LoiDispersion(type_loi, M=0.5, ET=0.2)
        assert loi.distribution.getClassName() == attendu.__name__

    def test_le_type_1_est_centre_sur_zero_quel_que_soit_M(self) -> None:
        """La loi « Nulle » est nulle, pas « constante à M »."""
        assert LoiDispersion(1, M=7.0, ET=3.0).support() == (0.0, 0.0)
        assert np.all(LoiDispersion(1, M=7.0, ET=3.0).tirer(50) == 0.0)

    def test_le_type_2_est_constant_a_M(self) -> None:
        assert np.all(LoiDispersion(2, M=7.0, ET=3.0).tirer(50) == 7.0)

    def test_l_uniforme_couvre_M_plus_ou_moins_ET(self) -> None:
        assert LoiDispersion(3, M=0.5, ET=0.2).support() == pytest.approx((0.3, 0.7))

    @pytest.mark.parametrize(("type_loi", "demi"), [(5, 1.5), (6, 1.0)])
    def test_les_tronquees_coupent_au_bon_multiple_de_ET(self, type_loi: int, demi: float) -> None:
        """±3σ et ±2σ avec σ = ET/2, soit ±1.5·ET et ±1.0·ET."""
        M, ET = 0.5, 0.2
        bas, haut = LoiDispersion(type_loi, M, ET).support()
        assert (bas, haut) == pytest.approx((M - demi * ET, M + demi * ET))

    def test_sigma_nominal_vaut_la_moitie_de_ET(self) -> None:
        """La convention qui coûte le plus cher quand on l'ignore."""
        assert LoiDispersion(4, 0.0, 0.2).sigma_nominal == pytest.approx(0.1)

    def test_ET_n_est_pas_un_ecart_type(self) -> None:
        """Garde-fou explicite : lire ET comme un σ double la dispersion."""
        loi = LoiDispersion(4, M=0.0, ET=0.2)
        assert loi.ET_theorique == pytest.approx(0.1)
        assert loi.ET_theorique != pytest.approx(loi.ET)

    @pytest.mark.parametrize(("type_loi", "ratio"), [(5, 0.98658), (6, 0.87963)])
    def test_la_troncature_resserre_l_ecart_type(self, type_loi: int, ratio: float) -> None:
        """Une gaussienne tronquée est plus étroite que sa gaussienne mère.

        C'est pour cela que la validation compare à ``ET_theorique`` et non à
        ``sigma_nominal`` : au type 6 l'écart est de 12 %, largement de quoi
        rejeter un tirage correct.
        """
        loi = LoiDispersion(type_loi, M=0.5, ET=0.2)
        assert loi.ET_theorique / loi.sigma_nominal == pytest.approx(ratio, rel=1e-4)
        assert loi.ET_theorique < loi.sigma_nominal


# ---------------------------------------------------------------------------
# Les deux pièges OpenTURNS
# ---------------------------------------------------------------------------


class TestPiegesOpenTurns:
    def test_le_support_de_la_gaussienne_est_infini(self) -> None:
        """``getRange()`` rendrait un intervalle fini, qui n'est pas le support.

        OpenTURNS borne numériquement une loi non bornée (≈ M ± 7.65 σ). Prendre
        cela pour le support ferait passer une queue légitime pour un point hors
        support, et donc rejeter des tirages corrects.
        """
        loi = LoiDispersion(4, M=0.0, ET=2.0)
        assert loi.support() == (-math.inf, math.inf)
        assert not loi.est_bornee

        plage = loi.distribution.getRange()
        assert math.isfinite(plage.getLowerBound()[0])

    def test_la_plage_utile_reste_finie_pour_la_gaussienne(self) -> None:
        """Pour tracer, il faut des bornes finies — et pas ±7.65 σ."""
        loi = LoiDispersion(4, M=0.0, ET=2.0)  # sigma = 1
        bas, haut = loi.plage_utile(k=4.0, marge=0.0)
        assert (bas, haut) == pytest.approx((-4.0, 4.0))

    def test_la_plage_utile_d_une_loi_degeneree_n_est_pas_de_largeur_nulle(self) -> None:
        bas, haut = LoiDispersion(2, M=3.0).plage_utile()
        assert haut > bas

    @pytest.mark.parametrize("type_loi", [3, 4, 5, 6])
    def test_ET_nul_donne_une_masse_en_M(self, type_loi: int) -> None:
        """OpenTURNS accepte ``Normal(M, 0)`` mais refuse ``Uniform(M, M)``.

        Se reposer sur ces refus donnerait quatre comportements pour la même
        situation : ET nul est donc ramené explicitement à un Dirac.
        """
        loi = LoiDispersion(type_loi, M=1.25, ET=0.0)
        assert loi.est_degeneree
        assert loi.support() == pytest.approx((1.25, 1.25))
        assert np.all(loi.tirer(20) == 1.25)

    def test_le_tirage_est_de_forme_n_et_non_n_1(self) -> None:
        """``getSample`` rend du ``(n, 1)`` ; aplati, sinon il se diffuse.

        Un ``(n, 1)`` multiplié par un balayage ``(npts,)`` donne un
        ``(n, npts)`` d'allure crédible et faux — le bug silencieux le plus
        probable de ce portage.
        """
        echantillon = LoiDispersion(4, 0.0, 1.0).tirer(37)
        assert echantillon.shape == (37,)
        assert echantillon.ndim == 1

    def test_le_tirage_est_modifiable(self) -> None:
        """Une vue sur le tampon OpenTURNS arriverait en lecture seule."""
        echantillon = LoiDispersion(4, 0.0, 1.0).tirer(10, graine=1)
        echantillon[0] = 42.0
        assert echantillon[0] == 42.0

    def test_le_tirage_ne_pollue_pas_le_flux_global(self) -> None:
        """Poser une graine ne doit pas décaler la suite du flux de l'appelant."""
        ot.RandomGenerator.SetSeed(123)
        avant = np.array(ot.Normal().getSample(4)).ravel()

        ot.RandomGenerator.SetSeed(123)
        LoiDispersion(4, 0.0, 1.0).tirer(1000, graine=999)
        apres = np.array(ot.Normal().getSample(4)).ravel()

        assert np.allclose(avant, apres)


# ---------------------------------------------------------------------------
# Tirage
# ---------------------------------------------------------------------------


class TestTirage:
    def test_meme_graine_meme_tirage(self) -> None:
        loi = LoiDispersion(5, 0.0, 1.0)
        assert np.array_equal(loi.tirer(100, graine=3), loi.tirer(100, graine=3))

    def test_graines_differentes_tirages_differents(self) -> None:
        loi = LoiDispersion(5, 0.0, 1.0)
        assert not np.array_equal(loi.tirer(100, graine=3), loi.tirer(100, graine=4))

    @pytest.mark.parametrize("methode", ["mc", "lhs", "sobol"])
    def test_les_trois_plans_respectent_la_loi(self, methode: str) -> None:
        loi = LoiDispersion(3, M=0.5, ET=0.2)
        echantillon = loi.tirer(2000, graine=11, methode=methode)

        assert echantillon.shape == (2000,)
        assert echantillon.min() >= 0.3 - 1e-9
        assert echantillon.max() <= 0.7 + 1e-9
        assert echantillon.mean() == pytest.approx(0.5, abs=0.02)

    def test_lhs_couvre_mieux_que_le_monte_carlo(self) -> None:
        """La raison d'être des plans : moins de trous à effectif égal.

        Mesuré par le plus grand écart entre deux tirages consécutifs triés —
        le « plus gros trou » laissé dans le support.
        """
        loi = LoiDispersion(3, M=0.0, ET=1.0)
        trou = {
            m: np.diff(np.sort(loi.tirer(500, graine=5, methode=m))).max() for m in ("mc", "lhs")
        }
        assert trou["lhs"] < trou["mc"]

    def test_une_methode_inconnue_est_refusee(self) -> None:
        with pytest.raises(ValueError, match="méthode inconnue"):
            LoiDispersion(4, 0.0, 1.0).tirer(10, methode="bogosort")

    @pytest.mark.parametrize("n", [0, -5])
    def test_un_effectif_non_positif_est_refuse(self, n: int) -> None:
        with pytest.raises(ValueError, match="strictement positif"):
            LoiDispersion(4, 0.0, 1.0).tirer(n)


# ---------------------------------------------------------------------------
# Densité, répartition, quantiles
# ---------------------------------------------------------------------------


class TestDensiteEtRepartition:
    def test_la_pdf_a_la_forme_de_l_entree(self) -> None:
        loi = LoiDispersion(4, 0.0, 2.0)
        assert loi.pdf(np.linspace(-3, 3, 11)).shape == (11,)
        assert loi.pdf(0.0).shape == (1,)

    def test_la_pdf_est_nulle_hors_du_support(self) -> None:
        loi = LoiDispersion(6, M=0.0, ET=0.1)  # support ±0.1
        assert loi.pdf([-0.2, 0.2]) == pytest.approx([0.0, 0.0])
        assert loi.pdf(0.0)[0] > 0.0

    def test_la_cdf_va_de_zero_a_un_sur_le_support(self) -> None:
        loi = LoiDispersion(3, M=0.0, ET=1.0)
        assert loi.cdf([-1.0, 0.0, 1.0]) == pytest.approx([0.0, 0.5, 1.0], abs=1e-9)

    def test_la_cdf_croit(self) -> None:
        loi = LoiDispersion(5, M=0.0, ET=1.0)
        valeurs = loi.cdf(np.linspace(-0.75, 0.75, 25))
        assert np.all(np.diff(valeurs) >= 0.0)

    def test_les_quantiles_inversent_la_cdf(self) -> None:
        loi = LoiDispersion(4, M=1.0, ET=0.4)
        probas = np.array([0.1, 0.25, 0.5, 0.75, 0.9])
        assert loi.cdf(loi.quantile(probas)) == pytest.approx(probas, abs=1e-6)

    def test_une_probabilite_hors_bornes_est_refusee(self) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            LoiDispersion(4, 0.0, 1.0).quantile([0.5, 1.4])


# ---------------------------------------------------------------------------
# Validation des entrées et description
# ---------------------------------------------------------------------------


class TestValidationDesEntrees:
    @pytest.mark.parametrize("type_loi", [0, 7, -1, 99])
    def test_un_type_inconnu_est_refuse(self, type_loi: int) -> None:
        with pytest.raises(ValueError, match="type de loi inconnu"):
            LoiDispersion(type_loi, 0.0, 1.0)

    def test_un_ET_negatif_est_refuse(self) -> None:
        with pytest.raises(ValueError, match="demi-étendue"):
            LoiDispersion(4, 0.0, -0.5)

    @pytest.mark.parametrize("valeur", [math.nan, math.inf])
    def test_M_et_ET_doivent_etre_finis(self, valeur: float) -> None:
        with pytest.raises(ValueError, match="fini"):
            LoiDispersion(4, valeur, 1.0)
        with pytest.raises(ValueError, match="fini"):
            LoiDispersion(4, 0.0, valeur)

    def test_les_champs_sont_normalises_en_flottants(self) -> None:
        """Sinon ``LoiDispersion(4, 0, 1)`` et ``(4, 0.0, 1.0)`` diffèrent."""
        loi = LoiDispersion(4, 0, 1)
        assert isinstance(loi.M, float)
        assert loi == LoiDispersion(4, 0.0, 1.0)

    def test_la_loi_est_hachable(self) -> None:
        """Requis par le cache de construction, et pratique en clé de dict."""
        assert len({LoiDispersion(4, 0.0, 1.0), LoiDispersion(4, 0.0, 1.0)}) == 1


class TestDescription:
    def test_tous_les_types_ont_un_libelle(self) -> None:
        assert set(LIBELLES_TYPE) == set(TYPES_VALIDES) == {1, 2, 3, 4, 5, 6}

    def test_libelle_type(self) -> None:
        assert libelle_type(5) == "Gaussienne ±3σ"

    def test_libelle_type_refuse_l_inconnu(self) -> None:
        with pytest.raises(ValueError, match="type de loi inconnu"):
            libelle_type(42)

    def test_label_suit_le_type(self) -> None:
        assert LoiDispersion(6, 0.0, 1.0).label == "Gaussienne ±2σ"

    @pytest.mark.parametrize(
        ("type_loi", "ET", "degeneree"),
        [(1, 0.0, True), (2, 0.0, True), (3, 0.1, False), (4, 0.0, True), (6, 0.1, False)],
    )
    def test_est_degeneree(self, type_loi: int, ET: float, degeneree: bool) -> None:
        assert LoiDispersion(type_loi, 0.0, ET).est_degeneree is degeneree
