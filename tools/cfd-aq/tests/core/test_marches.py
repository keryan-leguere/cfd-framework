"""The correlations, checked against what AGARD-AG-264 says in prose.

The strongest tests here are the ones that cross-check an independently
digitised figure against a *published* table. The step lines (Figures 4.23 and
4.28) were read off scans; the square-ridge coefficients were printed. The
report then states how the two relate — "about 50 % below […] at the lower
Mach numbers", "not present in the M = 2.8 data" — so reproducing that
relation is a check on the digitisation that does not depend on it.
"""

from __future__ import annotations

import math
from collections.abc import Callable

import pytest

from cfd_aq.core import donnees, marches
from cfd_aq.core.marches import TypeAsperite

H_PLUS_TYPIQUES = (25.0, 100.0, 500.0, 1000.0, 2000.0)
FONCTIONS = (
    marches.ratio_marche_montante,
    marches.ratio_marche_descendante,
    marches.ratio_arete,
)


# --- forme générale des corrélations --------------------------------------


@pytest.mark.parametrize("fonction", FONCTIONS)
@pytest.mark.parametrize("mach", (0.2, 0.6, 0.8, 1.0, 1.2, 1.4, 2.0, 2.8))
def test_la_trainee_croit_avec_h_plus(
    fonction: Callable[[float, float], float], mach: float
) -> None:
    """A taller step always costs more, at every Mach number."""
    valeurs = [fonction(h, mach) for h in H_PLUS_TYPIQUES]
    assert all(v1 > v0 for v0, v1 in zip(valeurs, valeurs[1:])), (fonction.__name__, mach)


@pytest.mark.parametrize("fonction", FONCTIONS)
@pytest.mark.parametrize("h_plus", H_PLUS_TYPIQUES)
def test_la_droite_est_lineaire_en_log_h_plus(
    fonction: Callable[[float, float], float], h_plus: float
) -> None:
    """Doubling log₁₀(h⁺) spacing gives a constant increment — eq. 4(37) shape."""
    mach = 0.5
    a = fonction(h_plus, mach)
    b = fonction(h_plus * 10.0, mach)
    c = fonction(h_plus * 100.0, mach)
    assert (b - a) == pytest.approx(c - b, rel=1e-9)


@pytest.mark.parametrize("fonction", FONCTIONS)
def test_continuite_aux_bornes_transsoniques(fonction: Callable[[float, float], float]) -> None:
    """No step at M = 0.8 or M = 1.4, where the blend takes over and hands back."""
    for mach in (0.8, 1.4):
        avant = fonction(500.0, mach - 1e-9)
        apres = fonction(500.0, mach + 1e-9)
        assert avant == pytest.approx(apres, rel=1e-6), (fonction.__name__, mach)


@pytest.mark.parametrize("fonction", FONCTIONS)
def test_h_plus_non_physique_refuse(fonction: Callable[[float, float], float]) -> None:
    with pytest.raises(ValueError, match="h⁺"):
        fonction(0.0, 0.8)


# --- comportement en Mach, tel que le rapport le décrit -------------------


def test_marche_montante_plafonne_au_dela_de_mach_1_4() -> None:
    """§4.3.1.1.1: one single supersonic line, so Mach stops mattering."""
    reference = marches.ratio_marche_montante(1000.0, 1.4)
    for mach in (1.6, 2.0, 2.8, 4.0):
        assert marches.ratio_marche_montante(1000.0, mach) == pytest.approx(reference)


def test_marche_descendante_passe_par_un_maximum_transsonique() -> None:
    """§4.3.1.2.1: the rearward step peaks near M ≈ 1.15 then falls away."""
    machs = [0.2 + 0.01 * i for i in range(261)]
    valeurs = [marches.ratio_marche_descendante(1000.0, m) for m in machs]
    mach_pic = machs[valeurs.index(max(valeurs))]
    assert 1.1 <= mach_pic <= 1.25
    assert valeurs[-1] < max(valeurs)  # redescend après le pic


def test_arete_passe_par_un_pic_transsonique_marque() -> None:
    """§4.3.2.1: the ridge drag jumps well above the subsonic level just past M = 1.

    The report quotes "50 % higher" from the raw data of Figure 4.37 at
    h⁺ = 1200; the recommended route (eq. 4(37) + PC₃) is a little flatter
    than that, and how much flatter depends on h⁺ — so what is pinned here is
    the size and the location of the peak, not a single number the report
    never claimed for this formula.
    """
    machs = [0.8 + 0.005 * i for i in range(121)]
    for h_plus in (200.0, 1200.0):
        valeurs = [marches.ratio_arete(h_plus, m) for m in machs]
        pic = max(valeurs)
        assert pic / valeurs[0] > 1.3, h_plus
        assert machs[valeurs.index(pic)] == pytest.approx(1.03, abs=0.04), h_plus


# --- interférence arête / somme des marches -------------------------------


@pytest.mark.parametrize("h_plus", (100.0, 500.0, 1000.0, 2000.0))
@pytest.mark.parametrize("mach", (0.2, 0.5, 0.8))
def test_superposition_sous_estime_de_moitie_a_bas_mach(h_plus: float, mach: float) -> None:
    """§4.3.2.1: "about 50 % below the drag of square ridges at the lower Mach numbers".

    This is the cross-check that matters: the two step lines come from scanned
    figures, the ridge coefficients from a printed table, and the report fixes
    the relation between them.
    """
    _, _, rapport = marches.interference_arete(h_plus, mach)
    assert 0.45 <= rapport <= 0.65, (h_plus, mach, rapport)


def test_interference_disparait_a_mach_2_8() -> None:
    """§4.3.2.1: "not present in the M = 2.8 data"."""
    for h_plus in (200.0, 1000.0, 2000.0):
        _, _, rapport = marches.interference_arete(h_plus, 2.8)
        assert rapport == pytest.approx(1.0, abs=0.12), (h_plus, rapport)


def test_interference_decroit_avec_le_mach() -> None:
    """The deficit shrinks monotonically over the supersonic range."""
    rapports = [marches.interference_arete(1000.0, m)[2] for m in (1.4, 1.7, 2.0, 2.2, 2.8)]
    assert all(r1 >= r0 for r0, r1 in zip(rapports, rapports[1:])), rapports


# --- épaisseur d'arête ----------------------------------------------------


def test_arete_carree_est_le_cas_t_sur_h_egal_un() -> None:
    for mach in (0.2, 0.8, 1.1, 2.0):
        assert marches.ratio_arete(500.0, mach, 1.0) == pytest.approx(
            marches.ratio_arete(500.0, mach)
        )


def test_epaisseur_fait_chuter_la_trainee_puis_plafonne() -> None:
    """Figure 4.40: T falls from ≈ 1.07 to a 0.58 plateau past t/h ≈ 4."""
    assert marches.facteur_epaisseur_arete(1.0) == pytest.approx(1.0, abs=1e-9)
    assert marches.facteur_epaisseur_arete(0.25) > 1.0
    assert marches.facteur_epaisseur_arete(2.0) == pytest.approx(0.789, abs=0.02)
    assert marches.facteur_epaisseur_arete(6.0) == pytest.approx(
        marches.facteur_epaisseur_arete(5.0)
    )


def test_la_table_t_egal_2h_croise_l_arete_carree_vers_h_plus_1000() -> None:
    """§4.3.2.1 in numbers: thicker is worse at low h⁺, better at high h⁺.

    "For low values of h⁺, where h/δ was about 0.01 to 0.02, the drag of the
    rectangular ridge is higher than for square ridges […] At higher values of
    h⁺ […] the drag of the rectangular ridge becomes less." The two published
    tables cross at h⁺ ≈ 1000, which is exactly that sentence.
    """
    for h_plus, attendu_plus_fort in ((100.0, True), (300.0, True), (2000.0, False)):
        carree = marches.ratio_arete(h_plus, 0.2, t_sur_h=1.0)
        rectangulaire = marches.ratio_arete_rectangulaire_2h(h_plus, 0.2)
        assert (rectangulaire > carree) is attendu_plus_fort, h_plus
    assert marches.ratio_arete_rectangulaire_2h(1000.0, 0.2) == pytest.approx(
        marches.ratio_arete(1000.0, 0.2, t_sur_h=1.0), rel=0.01
    )


def test_les_deux_routes_pour_t_egal_2h_divergent() -> None:
    """The contradiction of the report, pinned so it cannot drift unnoticed.

    ``T(2)·(square ridge)`` and the dedicated t = 2h table never meet: the
    generic route sits 21 % below the square ridge at every h⁺, while the
    dedicated one crosses it. The T curve comes from Wieghardt's ridges, all
    at h/δ > 3 %; the crossover lives at h/δ ≈ 0.02–0.03. Both are in the
    report, and :func:`ratio_arete` follows the generic route because it is
    the only one defined for every t/h.
    """
    for h_plus, ecart_minimal in ((100.0, 1.6), (1000.0, 1.2)):
        generique = marches.ratio_arete(h_plus, 0.2, t_sur_h=2.0)
        dediee = marches.ratio_arete_rectangulaire_2h(h_plus, 0.2)
        assert dediee / generique > ecart_minimal, h_plus


# --- corrections de forme -------------------------------------------------


def test_corrections_neutres_sur_une_marche_vive() -> None:
    """r = 0, θ = 90°, α = 90° must all be exactly transparent."""
    for mach in (0.2, 0.8, 1.4, 2.0):
        assert marches.facteur_arrondi_montante(0.0, mach) == pytest.approx(1.0)
        assert marches.facteur_chanfrein_montante(90.0, mach) == pytest.approx(1.0)
        assert marches.facteur_chanfrein_descendante(90.0, mach) == pytest.approx(1.0)
    assert marches.facteur_arrondi_descendante(0.0) == pytest.approx(1.0)
    assert marches.facteur_derapage(90.0) == pytest.approx(1.0)


def test_arrondir_une_marche_montante_reduit_la_trainee() -> None:
    """Figure 4.26(a), and the benefit collapses with Mach number."""
    for mach in (0.2, 0.8, 1.4, 2.0):
        facteurs = [marches.facteur_arrondi_montante(r, mach) for r in (0.0, 0.2, 0.4, 0.8)]
        assert all(f1 <= f0 for f0, f1 in zip(facteurs, facteurs[1:])), mach
    gain_subsonique = 1.0 - marches.facteur_arrondi_montante(0.4, 0.8)
    gain_supersonique = 1.0 - marches.facteur_arrondi_montante(0.4, 2.0)
    assert gain_subsonique > 5.0 * gain_supersonique


def test_arrondir_une_marche_descendante_augmente_la_trainee() -> None:
    """Equation 4(34): the sign is the opposite of the forward step's."""
    assert marches.facteur_arrondi_descendante(0.33) == pytest.approx(1.472, abs=1e-3)
    assert marches.facteur_arrondi_descendante(0.66) > marches.facteur_arrondi_descendante(0.33)


def test_chanfrein_descendante_sans_effet_au_dela_de_45_degres() -> None:
    """§4.3.1.2.2: "for chamfer angles down to 45° almost no change occurs"."""
    for mach in (0.2, 0.8, 1.4, 2.0):
        for angle in (45.0, 60.0, 75.0, 90.0):
            assert marches.facteur_chanfrein_descendante(angle, mach) == pytest.approx(
                1.0, abs=0.05
            ), (mach, angle)


def test_chanfrein_descendante_chute_sous_12_degres() -> None:
    """§4.3.1.2.2: "Below 12°, there is a sharp drop for all Mach numbers"."""
    for mach in (0.2, 0.8, 1.2, 1.4, 1.7, 2.0):
        assert marches.facteur_chanfrein_descendante(5.0, mach) < 0.60, mach
        assert marches.facteur_chanfrein_descendante(0.0, mach) == pytest.approx(0.0, abs=1e-9)


def test_derapage_suit_sin_carre() -> None:
    """Equations 4(30), 4(35), 4(41) — Figure 4.45 validated sin²α on ridges."""
    for angle in (0.0, 15.0, 30.0, 45.0, 60.0, 90.0):
        assert marches.facteur_derapage(angle) == pytest.approx(math.sin(math.radians(angle)) ** 2)


@pytest.mark.parametrize(
    ("fonction", "argument"),
    [
        (marches.facteur_chanfrein_montante, 95.0),
        (marches.facteur_chanfrein_descendante, -1.0),
    ],
)
def test_angles_hors_bornes_refuses(
    fonction: Callable[[float, float], float], argument: float
) -> None:
    with pytest.raises(ValueError, match="chanfrein"):
        fonction(argument, 0.8)


def test_derapage_hors_bornes_refuse() -> None:
    with pytest.raises(ValueError, match="dérapage"):
        marches.facteur_derapage(120.0)


def test_rayon_negatif_refuse() -> None:
    with pytest.raises(ValueError, match="r/h"):
        marches.facteur_arrondi_montante(-0.1, 0.8)
    with pytest.raises(ValueError, match="r/h"):
        marches.facteur_arrondi_descendante(-0.1)


def test_epaisseur_negative_refusee() -> None:
    with pytest.raises(ValueError, match="t/h"):
        marches.ratio_arete(500.0, 0.8, t_sur_h=-1.0)


# --- domaine de validité --------------------------------------------------


def test_aucun_avertissement_au_coeur_du_domaine() -> None:
    assert marches.verifier_domaine(TypeAsperite.MONTANTE, 500.0, 0.8, 0.01) == []


@pytest.mark.parametrize("h_plus", (10.0, 5000.0))
def test_h_plus_hors_plage_signale(h_plus: float) -> None:
    avertissements = marches.verifier_domaine(TypeAsperite.MONTANTE, h_plus, 0.8)
    assert [a.grandeur for a in avertissements] == ["h+"]
    assert avertissements[0].domaine == (donnees.H_PLUS_MIN, donnees.H_PLUS_MAX)


def test_mach_hors_plage_signale() -> None:
    avertissements = marches.verifier_domaine(TypeAsperite.DESCENDANTE, 500.0, 3.5)
    assert [a.grandeur for a in avertissements] == ["Mach"]
    assert "3.5" in avertissements[0].message


def test_immersion_excessive_signalee() -> None:
    avertissements = marches.verifier_domaine(TypeAsperite.ARETE, 500.0, 0.8, 0.12)
    assert [a.grandeur for a in avertissements] == ["h/delta"]


def test_le_mach_plafond_depend_de_la_forme() -> None:
    """The forward step's table stops at 1.4, the rearward's at 2.8."""
    assert marches.verifier_domaine(TypeAsperite.MONTANTE, 500.0, 2.0) != []
    assert marches.verifier_domaine(TypeAsperite.DESCENDANTE, 500.0, 2.0) == []


def test_la_corrélation_ne_rend_jamais_de_trainee_negative() -> None:
    """Below h⁺ ≈ 20 the published straight lines go through zero.

    That is why :data:`cfd_aq.core.donnees.H_PLUS_MIN` is 25: the fits are out
    of range there, and :func:`verifier_domaine` says so. The ratio is clamped
    at zero rather than returned negative, because a negative excrescence drag
    would quietly subtract from a drag budget.
    """
    for fonction in FONCTIONS:
        for h_plus in (1.0, 5.0, 15.0, 20.0):
            for mach in (0.2, 0.8, 1.1, 1.4, 2.8):
                assert fonction(h_plus, mach) >= 0.0, (fonction.__name__, h_plus, mach)
    assert marches.ratio_arete(15.0, 0.2) == 0.0
    assert marches.verifier_domaine(TypeAsperite.ARETE, 15.0, 0.2) != []
