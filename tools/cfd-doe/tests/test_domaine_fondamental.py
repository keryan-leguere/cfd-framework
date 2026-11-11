"""Domaine fondamental : un et un seul représentant par orbite.

C'est la propriété qui garantit qu'aucun calcul n'est perdu ni doublé. Elle se
vérifie par énumération : pour chaque point d'une grille, on calcule son orbite
complète et on compte combien de ses images (distinctes) tombent dans la
réunion des strates. La réponse doit être exactement 1.
"""

from __future__ import annotations

import itertools

import pytest

from cfd_doe.core.angles import Arc
from cfd_doe.core.domaine_fondamental import (
    Strate,
    fusionner,
    replier_arc,
    stratifier_signes,
)
from cfd_doe.core.intervalle import Intervalle
from cfd_doe.core.symetrie import ElementSigne, engendrer, restreindre

V = ElementSigne("V", frozenset({"beta", "DL", "DN"}))
H = ElementSigne("H", frozenset({"alpha", "DL", "DM"}))
ORDRE = ("alpha", "beta", "DM", "DN", "DL")


def _cle(point: dict[str, float]) -> tuple[float, ...]:
    return tuple(round(point[v], 9) + 0.0 for v in sorted(point))


def _representants(
    point: dict[str, float], groupe: tuple[ElementSigne, ...], strates: list[Strate]
) -> int:
    images = {_cle(g.agit(point)): g.agit(point) for g in groupe}
    return sum(any(s.contient(p) for s in strates) for p in images.values())


class TestGroupe:
    def test_engendrer_v_h(self) -> None:
        groupe = engendrer([V, H])
        assert len(groupe) == 4
        assert {"alpha", "beta", "DM", "DN"} in [set(e.inverse) for e in groupe]

    def test_restreindre_fusionne_les_elements_indiscernables(self) -> None:
        groupe = restreindre(engendrer([V, H]), ["alpha", "DM"])
        assert len(groupe) == 2  # seul H agit encore


class TestStratificationSignes:
    @pytest.mark.parametrize("generateurs", [[], [V], [H], [V, H]], ids=["aucune", "V", "H", "V+H"])
    def test_un_representant_par_orbite(self, generateurs: list[ElementSigne]) -> None:
        groupe = engendrer(generateurs)
        bornes = {v: Intervalle(-2, 2) for v in ORDRE}
        strates = stratifier_signes(bornes, groupe, ORDRE)
        for valeurs in itertools.product(range(-2, 3), repeat=len(ORDRE)):
            point = dict(zip(ORDRE, map(float, valeurs)))
            assert _representants(point, groupe, strates) == 1, point

    def test_exemple_plan_vertical(self) -> None:
        bornes = {v: Intervalle(-10, 10) for v in ORDRE}
        strates = stratifier_signes(bornes, engendrer([V]), ORDRE)
        assert [[(c.variable, c.texte) for c in s.chemin] for s in strates] == [
            [("beta", "> 0")],
            [("beta", "= 0"), ("DN", "> 0")],
            [("beta", "= 0"), ("DN", "= 0"), ("DL", "≥ 0")],
        ]

    def test_plage_asymetrique_refusee(self) -> None:
        with pytest.raises(ValueError, match="symétrique"):
            stratifier_signes({"beta": Intervalle(-2, 5)}, engendrer([V]), ORDRE)

    def test_plan_de_symetrie_section_7_4(self) -> None:
        """Sur un plan φa = φs, 65 combinaisons sur 125 (§7.4)."""
        miroir = ElementSigne("m", frozenset({"DL", "DNB"}))
        bornes = {v: Intervalle(-20, 20) for v in ("DMB", "DNB", "DL")}
        strates = stratifier_signes(bornes, engendrer([miroir]), ("DMB", "DNB", "DL"))
        grille = range(-20, 21, 10)
        n = sum(
            any(s.contient({"DMB": a, "DNB": b, "DL": c}) for s in strates)
            for a, b, c in itertools.product(grille, repeat=3)
        )
        assert n == 65


class TestRepliement:
    @pytest.mark.parametrize(
        ("n", "miroirs", "largeur"),
        [(1, False, 360.0), (1, True, 180.0), (2, True, 90.0), (4, True, 45.0), (3, True, 60.0)],
    )
    def test_arc_complet_donne_le_secteur_section_4_3(
        self, n: int, miroirs: bool, largeur: float
    ) -> None:
        (secteur,) = replier_arc(Arc(0.0, 360.0), n, miroirs)
        assert (secteur.bas, secteur.haut) == (0.0, largeur)
        assert secteur.haut_inclus is miroirs

    def test_petit_arc_reste_petit(self) -> None:
        (secteur,) = replier_arc(Arc(0.0, 11.5), 4, True)
        assert (secteur.bas, secteur.haut) == pytest.approx((0.0, 11.5))

    def test_arc_replie_par_le_miroir_a_45(self) -> None:
        (secteur,) = replier_arc(Arc(60.0, 10.0), 4, True)  # [60, 70] → [20, 30]
        assert (secteur.bas, secteur.haut) == pytest.approx((20.0, 30.0))

    def test_arc_a_cheval_sur_zero_sans_symetrie(self) -> None:
        morceaux = replier_arc(Arc(330.0, 60.0), 1, False)
        assert [(m.bas, m.haut, m.haut_inclus) for m in morceaux] == [
            (0.0, 30.0, True),
            (330.0, 360.0, False),
        ]


class TestFusion:
    def test_recolle_plan_secteur_plan(self) -> None:
        base = {"x": Intervalle(0, 1)}
        strates = [
            Strate({**base, "phia": Intervalle(0, 45, False, False)}, nom="secteur"),
            Strate({**base, "phia": Intervalle.point(0)}, nom="plan"),
            Strate({**base, "phia": Intervalle.point(45)}, nom="plan"),
        ]
        (seule,) = fusionner(strates)
        assert seule.bornes["phia"] == Intervalle(0, 45)
        assert seule.nom == "secteur"

    def test_ne_recolle_pas_deux_variables(self) -> None:
        strates = [
            Strate({"a": Intervalle(0, 1, False), "b": Intervalle(0, 1)}),
            Strate({"a": Intervalle.point(0), "b": Intervalle.point(0)}),
        ]
        assert len(fusionner(strates)) == 2
