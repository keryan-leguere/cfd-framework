"""The digitised tables must satisfy what the source figures assert by construction.

These are not round-trips of the digitisation against itself: every assertion
below is a statement the AGARDograph makes — a factor that is 0 or 1 at a
defining point, a curve that is monotone, a published coefficient. A typo in
:mod:`cfd_aq.core.donnees` that survives these is a typo that does not change
the physics.
"""

from __future__ import annotations

import pytest

from cfd_aq.core import donnees


def _courbes() -> list[tuple[str, donnees.Courbe]]:
    courbes: list[tuple[str, donnees.Courbe]] = [
        ("PC1", donnees.PC1_MARCHE_MONTANTE),
        ("PC2", donnees.PC2_MARCHE_DESCENDANTE),
        ("PC3", donnees.PC3_ARETE),
        ("T(t/h)", donnees.EPAISSEUR_ARETE),
    ]
    for famille, nom in (
        (donnees.ARRONDI_MONTANTE, "arrondi montante"),
        (donnees.CHANFREIN_MONTANTE, "chanfrein montante"),
        (donnees.CHANFREIN_DESCENDANTE, "chanfrein descendante"),
    ):
        for mach, courbe in famille.items():
            courbes.append((f"{nom} M={mach}", courbe))
    return courbes


@pytest.mark.parametrize(("nom", "courbe"), _courbes())
def test_abscisses_strictement_croissantes(nom: str, courbe: donnees.Courbe) -> None:
    """A tabulated curve read by linear interpolation needs a sorted abscissa."""
    abscisses, ordonnees = courbe
    assert len(abscisses) == len(ordonnees), nom
    assert all(x1 > x0 for x0, x1 in zip(abscisses, abscisses[1:])), nom


@pytest.mark.parametrize(
    ("nom", "courbe"),
    [
        ("PC1", donnees.PC1_MARCHE_MONTANTE),
        ("PC2", donnees.PC2_MARCHE_DESCENDANTE),
        ("PC3", donnees.PC3_ARETE),
    ],
)
def test_facteurs_pc_ancres(nom: str, courbe: donnees.Courbe) -> None:
    """PC = 0 at M = 0.8 and 1 at M = 1.4 — the definition of the blend."""
    abscisses, ordonnees = courbe
    assert abscisses[0] == 0.8
    assert abscisses[-1] == 1.4
    assert ordonnees[0] == 0.0
    assert ordonnees[-1] == pytest.approx(1.0, abs=1e-9)


def test_pc2_depasse_un() -> None:
    """The rearward step peaks above its M = 1.4 value — Figure 4.29, not a glitch."""
    assert max(donnees.PC2_MARCHE_DESCENDANTE[1]) > 1.2


def test_pc3_pic_transsonique() -> None:
    """The ridge peaks near M = 1.03 at about 1.6 — §4.3.2.1: 50 % above subsonic."""
    machs, valeurs = donnees.PC3_ARETE
    pic = max(range(len(valeurs)), key=lambda i: valeurs[i])
    assert machs[pic] == pytest.approx(1.025, abs=0.03)
    assert valeurs[pic] == pytest.approx(1.58, abs=0.05)


def test_facteur_epaisseur_vaut_un_a_t_egal_h() -> None:
    """T(1) = 1 — equation 4(39) is normalised on the square ridge."""
    abscisses, ordonnees = donnees.EPAISSEUR_ARETE
    indice = list(abscisses).index(1.0)
    assert ordonnees[indice] == pytest.approx(1.0, abs=1e-9)


def test_facteur_epaisseur_plateau() -> None:
    """T saturates near 0.58 past t/h ≈ 4: the flow reattaches between the faces."""
    abscisses, ordonnees = donnees.EPAISSEUR_ARETE
    queue = [y for x, y in zip(abscisses, ordonnees) if x >= 4.0]
    assert all(y == pytest.approx(0.577, abs=0.01) for y in queue)


@pytest.mark.parametrize("mach", sorted(donnees.ARRONDI_MONTANTE))
def test_arrondi_montante_part_de_zero_et_croit(mach: float) -> None:
    """No radius, no benefit; and a larger radius never helps less."""
    abscisses, ordonnees = donnees.ARRONDI_MONTANTE[mach]
    assert abscisses[0] == 0.0
    assert ordonnees[0] == 0.0
    assert all(y1 >= y0 for y0, y1 in zip(ordonnees, ordonnees[1:]))
    assert max(ordonnees) < 1.0


@pytest.mark.parametrize("mach", sorted(donnees.CHANFREIN_MONTANTE))
def test_chanfrein_montante_ancre(mach: float) -> None:
    """E = 1 for a complete fairing, E = 0 for a square face; monotone between."""
    abscisses, ordonnees = donnees.CHANFREIN_MONTANTE[mach]
    assert (abscisses[0], abscisses[-1]) == (0.0, 90.0)
    assert ordonnees[0] == 1.0
    assert ordonnees[-1] == 0.0
    assert all(y1 <= y0 for y0, y1 in zip(ordonnees, ordonnees[1:]))


@pytest.mark.parametrize("mach", sorted(donnees.CHANFREIN_DESCENDANTE))
def test_chanfrein_descendante_ancre(mach: float) -> None:
    """G = 1 at θ = 0, G = 0 at a square face and beyond 45° — §4.3.1.2.2."""
    abscisses, ordonnees = donnees.CHANFREIN_DESCENDANTE[mach]
    assert abscisses[0] == 0.0
    assert ordonnees[0] == 1.0
    assert ordonnees[-1] == 0.0
    au_dela_de_45 = [y for x, y in zip(abscisses, ordonnees) if x >= 45.0]
    assert all(abs(y) <= 0.05 for y in au_dela_de_45)


def test_chanfrein_descendante_augmente_la_trainee_au_supersonique() -> None:
    """Between 12° and 45°, a chamfer makes it worse at M ≥ 1.2 — G goes negative."""
    for mach in (1.2, 1.4, 1.7):
        abscisses, ordonnees = donnees.CHANFREIN_DESCENDANTE[mach]
        bande = [y for x, y in zip(abscisses, ordonnees) if 12.0 <= x <= 45.0]
        assert min(bande) < 0.0, mach


def test_coefficients_publies_des_aretes() -> None:
    """The ridge tables are transcriptions of the printed table under eq. 4(37)."""
    assert donnees.ARETE_CARREE[0.2] == (150.0, -190.0)
    assert donnees.ARETE_CARREE[0.8] == (150.0, -160.0)
    assert donnees.ARETE_CARREE[1.4] == (160.0, -125.0)
    assert donnees.ARETE_CARREE[2.2] == (110.0, -42.0)
    assert donnees.ARETE_CARREE[2.8] == (100.0, -44.0)
    assert donnees.ARETE_RECTANGULAIRE_2H[0.2] == (105.0, -55.0)
    assert donnees.ARETE_RECTANGULAIRE_2H[1.7] == (100.0, 20.0)


@pytest.mark.parametrize(
    "table",
    [donnees.MARCHE_MONTANTE, donnees.MARCHE_DESCENDANTE, donnees.ARETE_CARREE],
)
def test_pentes_positives(table: donnees.DroitesLogH) -> None:
    """Drag grows with h⁺ at every Mach number: every slope A is positive."""
    assert all(a > 0.0 for a, _ in table.values())


def test_les_tables_transsoniques_portent_bien_0_8_et_1_4() -> None:
    """Equations 4(27), 4(32) and 4(38) blend exactly those two lines."""
    for table in (donnees.MARCHE_MONTANTE, donnees.MARCHE_DESCENDANTE, donnees.ARETE_CARREE):
        assert 0.8 in table
        assert 1.4 in table
