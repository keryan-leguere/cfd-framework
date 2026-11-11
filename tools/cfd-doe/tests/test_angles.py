"""Passage (α, β) ↔ (αt, φa) : les valeurs numériques de 00_DOC/01_BASE_AERO.md."""

from __future__ import annotations

import itertools

import pytest

from cfd_doe.core.angles import (
    arc_phia_rectangle,
    braquages_engin,
    braquages_mixtes,
    incidence_totale,
    normaliser_angle,
    plage_alphat_rectangle,
    vers_alpha_beta,
    vers_alphat_phia,
)
from cfd_doe.core.intervalle import Intervalle


class TestPassage:
    def test_exemple_section_2_4(self) -> None:
        alphat, phia = vers_alphat_phia(10.0, 5.0)
        assert alphat == pytest.approx(11.17, abs=0.005)
        assert phia == pytest.approx(26.7, abs=0.05)

    @pytest.mark.parametrize(
        ("alpha", "beta", "alphat", "phia"),
        [
            (12.0, 0.0, 12.0, 0.0),
            (-12.0, 0.0, 12.0, 180.0),
            (0.0, 7.0, 7.0, 90.0),
            (0.0, -7.0, 7.0, 270.0),
        ],
    )
    def test_cas_particuliers_section_2_3(
        self, alpha: float, beta: float, alphat: float, phia: float
    ) -> None:
        assert vers_alphat_phia(alpha, beta) == pytest.approx((alphat, phia))

    def test_vent_dans_l_axe(self) -> None:
        assert vers_alphat_phia(0.0, 0.0) == (0.0, 0.0)

    @pytest.mark.parametrize(
        ("alpha", "beta"), list(itertools.product([-35, -10, 0, 3, 20, 60], [-40, -5, 0, 5, 25]))
    )
    def test_aller_retour(self, alpha: float, beta: float) -> None:
        assert vers_alpha_beta(*vers_alphat_phia(alpha, beta)) == pytest.approx(
            (alpha, beta), abs=1e-9
        )

    def test_controle_v2_plus_w2(self) -> None:
        """sin² β + sin² α cos² β = sin² αt (§2.2, contrôle utile)."""
        import math

        a, b = math.radians(20), math.radians(20)
        at = math.radians(incidence_totale(20, 20))
        assert math.sin(b) ** 2 + math.sin(a) ** 2 * math.cos(b) ** 2 == pytest.approx(
            math.sin(at) ** 2
        )
        # Et le piège : αt ≠ √(α² + β²) (28,0° contre 28,3°).
        assert incidence_totale(20, 20) == pytest.approx(28.0, abs=0.05)

    def test_miroir_45_section_4_4(self) -> None:
        """Le miroir à 45° envoie (10°, 5°) sur (5,08°, 9,96°), pas sur (5°, 10°)."""
        alphat, phia = vers_alphat_phia(10.0, 5.0)
        alpha, beta = vers_alpha_beta(alphat, 90.0 - phia)
        assert alpha == pytest.approx(5.08, abs=0.01)
        assert beta == pytest.approx(9.96, abs=0.01)

    def test_normaliser(self) -> None:
        assert normaliser_angle(-30.0) == pytest.approx(330.0)
        assert normaliser_angle(720.0) == 0.0
        assert normaliser_angle(360.0 - 1e-12) == 0.0


class TestBraquages:
    def test_aller_retour(self) -> None:
        dmb, dnb = braquages_mixtes(12.0, -7.0, 33.0)
        assert braquages_engin(dmb, dnb, 33.0) == pytest.approx((12.0, -7.0))

    def test_rotation_90_echange_tangage_et_lacet(self) -> None:
        assert braquages_mixtes(10.0, 0.0, 90.0) == pytest.approx((0.0, 10.0), abs=1e-12)


class TestRectangle:
    def test_alphat_max_section_5_1(self) -> None:
        plage = plage_alphat_rectangle(Intervalle(-20, 20), Intervalle(-5, 5))
        assert plage.bas == 0.0
        assert plage.haut == pytest.approx(20.6, abs=0.01)

    def test_alphat_min_hors_origine(self) -> None:
        plage = plage_alphat_rectangle(Intervalle(5, 20), Intervalle(-2, 3))
        assert plage.bas == pytest.approx(5.0)

    def test_arc_complet_si_origine_interieure(self) -> None:
        assert arc_phia_rectangle(Intervalle(-1, 1), Intervalle(-1, 1)).est_complet

    def test_arc_quadrant(self) -> None:
        arc = arc_phia_rectangle(Intervalle(0, 20), Intervalle(0, 5))
        assert (arc.debut, arc.longueur) == pytest.approx((0.0, 90.0))

    def test_arc_demi_plan(self) -> None:
        arc = arc_phia_rectangle(Intervalle(0, 20), Intervalle(-5, 5))
        assert (arc.debut, arc.longueur) == pytest.approx((270.0, 180.0))

    def test_arc_contient_tous_les_points(self) -> None:
        alpha, beta = Intervalle(4, 20), Intervalle(-6, 9)
        arc = arc_phia_rectangle(alpha, beta)
        for a in range(4, 21):
            for b in range(-6, 10):
                phia = vers_alphat_phia(a, b)[1]
                assert (phia - arc.debut) % 360.0 <= arc.longueur + 1e-9
