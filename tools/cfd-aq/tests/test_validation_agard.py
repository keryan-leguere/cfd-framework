"""Validation against AGARD-AG-264 itself, and regression anchors.

Three layers:

1. **Published numbers.** The ridge coefficients are printed in the report, so
   ``A·log₁₀(h⁺) + B`` can be checked to the digit at any h⁺.
2. **Statements the report makes in prose**, which cross a digitised figure
   against a published table and therefore test the digitisation without
   depending on it. Those live in ``test_marches.py``.
3. **Anchors.** Every number below was computed once, checked against the
   source figure by eye, and frozen. They exist so an edit to
   :mod:`cfd_aq.core.donnees` cannot quietly move an answer: a change here is
   a change to the physics the package claims, and must be deliberate.
"""

from __future__ import annotations

import math

import pytest

from cfd_aq.core import donnees, marches

# (forme, h⁺, M, CDe/Cfe attendu)
ANCRES = [
    # Marche montante — Figure 4.23. Les deux droites subsoniques sont
    # proches ; la droite supersonique unique vaut pour tout M ≥ 1,4.
    ("montante", 100.0, 0.2, 41.0),
    ("montante", 100.0, 0.8, 49.0),
    ("montante", 1000.0, 0.2, 101.0),
    ("montante", 1000.0, 0.8, 110.5),
    ("montante", 1000.0, 1.4, 170.9),
    ("montante", 1000.0, 2.8, 170.9),
    # Marche descendante — Figure 4.28. Niveau bien plus bas au subsonique,
    # maximum vers M = 1,4 puis décroissance.
    ("descendante", 100.0, 0.2, 24.5),
    ("descendante", 1000.0, 0.2, 40.5),
    ("descendante", 1000.0, 0.8, 47.0),
    ("descendante", 1000.0, 1.4, 125.8),
    ("descendante", 1000.0, 2.8, 92.2),
    # Arête carrée — coefficients publiés, eq. 4(37) : exacts.
    ("arete", 100.0, 0.2, 110.0),
    ("arete", 1000.0, 0.2, 260.0),
    ("arete", 1000.0, 0.8, 290.0),
    ("arete", 1000.0, 1.4, 355.0),
    ("arete", 1000.0, 2.8, 256.0),
]

FONCTIONS = {
    "montante": marches.ratio_marche_montante,
    "descendante": marches.ratio_marche_descendante,
    "arete": marches.ratio_arete,
}


@pytest.mark.parametrize(("forme", "h_plus", "mach", "attendu"), ANCRES)
def test_ancres(forme: str, h_plus: float, mach: float, attendu: float) -> None:
    assert FONCTIONS[forme](h_plus, mach) == pytest.approx(attendu, abs=0.05)


@pytest.mark.parametrize("mach", sorted(donnees.ARETE_CARREE))
@pytest.mark.parametrize("h_plus", (25.0, 100.0, 1000.0, 2000.0))
def test_arete_reproduit_exactement_les_coefficients_publies(mach: float, h_plus: float) -> None:
    """Equation 4(37) with the printed A and B, to machine precision."""
    a, b = donnees.ARETE_CARREE[mach]
    assert marches.ratio_arete(h_plus, mach) == pytest.approx(a * math.log10(h_plus) + b, rel=1e-12)


@pytest.mark.parametrize("mach", sorted(donnees.ARETE_RECTANGULAIRE_2H))
def test_arete_rectangulaire_reproduit_ses_coefficients(mach: float) -> None:
    a, b = donnees.ARETE_RECTANGULAIRE_2H[mach]
    assert marches.ratio_arete_rectangulaire_2h(800.0, mach) == pytest.approx(
        a * math.log10(800.0) + b, rel=1e-12
    )


@pytest.mark.parametrize("forme", sorted(FONCTIONS))
def test_les_bornes_du_blend_transsonique_rendent_les_droites(forme: str) -> None:
    """PC = 0 gives back the M = 0.8 line, PC = 1 the M = 1.4 line."""
    table = {
        "montante": donnees.MARCHE_MONTANTE,
        "descendante": donnees.MARCHE_DESCENDANTE,
        "arete": donnees.ARETE_CARREE,
    }[forme]
    for mach in (0.8, 1.4):
        a, b = table[mach]
        assert FONCTIONS[forme](750.0, mach) == pytest.approx(a * math.log10(750.0) + b, rel=1e-12)


def test_hierarchie_des_trois_formes_au_subsonique() -> None:
    """Rearward < forward < ridge, over the measured subsonic range.

    The range starts at h⁺ = 55 on purpose: below that, Figure 4.23's
    subsonic forward-step lines are not drawn at all, and extrapolating their
    steep slope downwards drops them under the rearward step's.
    :func:`verifier_domaine` warns about it; see the next test.
    """
    for h_plus in (60.0, 100.0, 500.0, 2000.0):
        for mach in (0.2, 0.5, 0.8):
            descendante = marches.ratio_marche_descendante(h_plus, mach)
            montante = marches.ratio_marche_montante(h_plus, mach)
            arete = marches.ratio_arete(h_plus, mach)
            assert descendante < montante < arete, (h_plus, mach)


def test_une_marche_montante_traine_deux_a_trois_fois_la_descendante() -> None:
    """A well-known rule of thumb, and here it comes out of the data."""
    for h_plus in (100.0, 500.0, 2000.0):
        rapport = marches.ratio_marche_montante(h_plus, 0.5) / marches.ratio_marche_descendante(
            h_plus, 0.5
        )
        assert 1.6 <= rapport <= 3.0, (h_plus, rapport)


def test_ordre_de_grandeur_sur_un_cas_de_croisiere() -> None:
    """Sanity of the whole chain against a hand calculation.

    FL360, M = 0.82, 10 m of turbulent run, a 1 mm forward step 1 m wide.
    τ_w ≈ 16.6 Pa and CDe/Cfe ≈ 60, so ΔD ≈ 60 × 16.6 × 1e-3 ≈ 1 N — a
    plausible number for a step one can feel with a fingernail.
    """
    from cfd_aq.core.couche_limite import CoucheLimite, EtatLocal
    from cfd_aq.core.marches import TypeAsperite
    from cfd_aq.core.trainee import Asperite, calculer_trainee

    etat = EtatLocal.isa(11000.0, 0.82)
    couche = CoucheLimite.plaque_plane(etat, 10.0)
    resultat = calculer_trainee(Asperite(TypeAsperite.MONTANTE, 1e-3, 1.0), etat, couche)
    assert 14.0 < couche.cisaillement_paroi < 20.0
    assert 120.0 < resultat.h_plus < 180.0
    assert 0.7 < resultat.trainee < 1.4
    assert resultat.avertissements == []


def test_extrapolation_basse_de_la_marche_montante_signalee() -> None:
    """Between h⁺ = 25 and 55 the subsonic forward-step line is an extrapolation."""
    avertissements = marches.verifier_domaine(marches.TypeAsperite.MONTANTE, 40.0, 0.2)
    assert [a.grandeur for a in avertissements] == ["h+"]
    assert "Figure 4.23" in avertissements[0].message
    # L'artefact que l'avertissement décrit : montante sous descendante.
    assert marches.ratio_marche_montante(40.0, 0.2) < marches.ratio_marche_descendante(40.0, 0.2)
    # Le mélange transsonique s'appuie sur la droite M = 0,8 : même mise en garde.
    assert marches.verifier_domaine(marches.TypeAsperite.MONTANTE, 40.0, 1.0) != []
    # Au supersonique la droite part bien de h⁺ = 10 : plus d'avertissement.
    assert marches.verifier_domaine(marches.TypeAsperite.MONTANTE, 40.0, 1.4) == []
