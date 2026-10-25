"""Assembling a geometry and a boundary layer into a force.

The chain is short enough to be checked end to end by hand, which is what
most of these tests do: recompute ΔD from τ_w and the frontal area, and check
that the package's number is the same one.
"""

from __future__ import annotations

import pytest

from cfd_aq.core.couche_limite import CoucheLimite, EtatLocal
from cfd_aq.core.marches import TypeAsperite, ratio_marche_montante
from cfd_aq.core.trainee import (
    Asperite,
    calculer_trainee,
    facteur_amplification_nash_bradshaw,
)


def test_la_trainee_se_recalcule_a_la_main(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    """ΔD = (CDe/Cfe)·τ_w·f_e — the local dynamic pressure cancels out."""
    asperite = Asperite(TypeAsperite.MONTANTE, hauteur=1.2e-3, envergure=3.0)
    resultat = calculer_trainee(asperite, etat_croisiere, couche_croisiere)

    ratio = ratio_marche_montante(couche_croisiere.h_plus(asperite.hauteur), etat_croisiere.mach)
    attendu = ratio * couche_croisiere.cisaillement_paroi * asperite.aire_frontale
    assert resultat.trainee == pytest.approx(attendu)
    assert resultat.cde_sur_cfe == pytest.approx(ratio)


def test_cde_est_bien_rapporte_a_l_aire_frontale(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    asperite = Asperite(TypeAsperite.ARETE, hauteur=8e-4, envergure=1.5)
    resultat = calculer_trainee(asperite, etat_croisiere, couche_croisiere)
    assert resultat.cde == pytest.approx(
        resultat.trainee / (etat_croisiere.pression_dynamique * asperite.aire_frontale)
    )


def test_delta_cx_rapporte_a_la_surface_de_reference(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    asperite = Asperite(TypeAsperite.MONTANTE, hauteur=1e-3, envergure=2.0)
    resultat = calculer_trainee(asperite, etat_croisiere, couche_croisiere, 122.6)
    assert resultat.delta_cx == pytest.approx(
        resultat.trainee / (etat_croisiere.pression_dynamique * 122.6)
    )


def test_pas_de_delta_cx_sans_surface(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    asperite = Asperite(TypeAsperite.MONTANTE, hauteur=1e-3, envergure=2.0)
    assert calculer_trainee(asperite, etat_croisiere, couche_croisiere).delta_cx is None


def test_la_trainee_est_lineaire_en_envergure(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    court = calculer_trainee(
        Asperite(TypeAsperite.MONTANTE, 1e-3, 1.0), etat_croisiere, couche_croisiere
    )
    long = calculer_trainee(
        Asperite(TypeAsperite.MONTANTE, 1e-3, 4.0), etat_croisiere, couche_croisiere
    )
    assert long.trainee == pytest.approx(4.0 * court.trainee)


def test_la_trainee_croit_plus_vite_que_la_hauteur(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    """ΔD ∝ h·(A·log₁₀h⁺ + B): doubling h more than doubles the drag."""
    petit = calculer_trainee(
        Asperite(TypeAsperite.MONTANTE, 1e-3, 2.0), etat_croisiere, couche_croisiere
    )
    grand = calculer_trainee(
        Asperite(TypeAsperite.MONTANTE, 2e-3, 2.0), etat_croisiere, couche_croisiere
    )
    assert grand.trainee > 2.0 * petit.trainee


def test_une_marche_montante_traine_plus_qu_une_descendante(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    """True over the whole subsonic range — Figures 4.23 and 4.28."""
    commun = {"hauteur": 1e-3, "envergure": 2.0}
    montante = calculer_trainee(
        Asperite(TypeAsperite.MONTANTE, **commun), etat_croisiere, couche_croisiere
    )
    descendante = calculer_trainee(
        Asperite(TypeAsperite.DESCENDANTE, **commun), etat_croisiere, couche_croisiere
    )
    arete = calculer_trainee(
        Asperite(TypeAsperite.ARETE, **commun), etat_croisiere, couche_croisiere
    )
    assert descendante.trainee < montante.trainee < arete.trainee


# --- corrections de forme -------------------------------------------------


def test_les_corrections_se_multiplient(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    """A chamfer and a sweep angle together give the product of their factors."""
    from cfd_aq.core.marches import facteur_chanfrein_montante, facteur_derapage

    asperite = Asperite(
        TypeAsperite.MONTANTE,
        hauteur=1e-3,
        envergure=2.0,
        angle_chanfrein=30.0,
        angle_derapage=60.0,
    )
    attendu = facteur_chanfrein_montante(30.0, etat_croisiere.mach) * facteur_derapage(60.0)
    resultat = calculer_trainee(asperite, etat_croisiere, couche_croisiere)
    assert resultat.facteur_forme == pytest.approx(attendu)


def test_marche_vive_normale_au_flux_sans_correction(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    asperite = Asperite(TypeAsperite.MONTANTE, 1e-3, 2.0)
    assert calculer_trainee(
        asperite, etat_croisiere, couche_croisiere
    ).facteur_forme == pytest.approx(1.0)


def test_arrondi_et_chanfrein_simultanes_refuses() -> None:
    with pytest.raises(ValueError, match="soit arrondie soit chanfreinée"):
        Asperite(
            TypeAsperite.MONTANTE,
            hauteur=1e-3,
            envergure=1.0,
            rayon_sur_h=0.3,
            angle_chanfrein=45.0,
        )


def test_arrondir_une_marche_descendante_coute_plus_cher(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    vive = calculer_trainee(
        Asperite(TypeAsperite.DESCENDANTE, 1e-3, 2.0), etat_croisiere, couche_croisiere
    )
    arrondie = calculer_trainee(
        Asperite(TypeAsperite.DESCENDANTE, 1e-3, 2.0, rayon_sur_h=0.5),
        etat_croisiere,
        couche_croisiere,
    )
    assert arrondie.trainee > vive.trainee


@pytest.mark.parametrize(
    ("hauteur", "envergure"), [(0.0, 1.0), (-1e-3, 1.0), (1e-3, 0.0), (1e-3, -1.0)]
)
def test_geometrie_non_physique_refusee(hauteur: float, envergure: float) -> None:
    with pytest.raises(ValueError):
        Asperite(TypeAsperite.MONTANTE, hauteur, envergure)


def test_surface_de_reference_non_physique_refusee(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    with pytest.raises(ValueError, match="surface de référence"):
        calculer_trainee(
            Asperite(TypeAsperite.MONTANTE, 1e-3, 2.0),
            etat_croisiere,
            couche_croisiere,
            surface_reference=0.0,
        )


def test_amplification_non_physique_refusee(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    with pytest.raises(ValueError, match="amplification"):
        calculer_trainee(
            Asperite(TypeAsperite.MONTANTE, 1e-3, 2.0),
            etat_croisiere,
            couche_croisiere,
            amplification=0.0,
        )


# --- avertissements -------------------------------------------------------


def test_hors_domaine_remonte_dans_le_resultat(etat_croisiere: EtatLocal) -> None:
    """A 2 cm step on a thin layer is both too tall and too proud: two warnings."""
    couche = CoucheLimite.plaque_plane(etat_croisiere, 0.5)
    resultat = calculer_trainee(Asperite(TypeAsperite.MONTANTE, 2e-2, 1.0), etat_croisiere, couche)
    grandeurs = {a.grandeur for a in resultat.avertissements}
    assert "h+" in grandeurs
    assert "h/delta" in grandeurs


def test_point_nominal_sans_avertissement(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    resultat = calculer_trainee(
        Asperite(TypeAsperite.MONTANTE, 1e-3, 2.0), etat_croisiere, couche_croisiere
    )
    assert resultat.avertissements == []


# --- Nash-Bradshaw --------------------------------------------------------


def test_nash_bradshaw_vaut_un_sur_plaque_plane() -> None:
    """m_d = 1 exactly when nothing varies between the step and the trailing edge."""
    assert facteur_amplification_nash_bradshaw(1.0, 1.0, 1.0) == pytest.approx(1.0)


def test_nash_bradshaw_amplifie_sur_un_pic_de_survitesse() -> None:
    """§5.1: m_d can be badly underestimated by taking (u_eo/V₀)² instead."""
    m_d = facteur_amplification_nash_bradshaw(1.25, 0.95, 0.4)
    assert m_d > 1.25**2
    assert m_d == pytest.approx(1.25**4.2 / 0.95 * 0.4**0.2, rel=1e-12)


def test_nash_bradshaw_exposants() -> None:
    """The three exponents of equation 5(5): 4.2, −1 and 1/5."""
    base = facteur_amplification_nash_bradshaw(1.0, 1.0, 1.0)
    assert facteur_amplification_nash_bradshaw(2.0, 1.0, 1.0) / base == pytest.approx(2.0**4.2)
    assert facteur_amplification_nash_bradshaw(1.0, 2.0, 1.0) / base == pytest.approx(0.5)
    assert facteur_amplification_nash_bradshaw(1.0, 1.0, 2.0) / base == pytest.approx(2.0**0.2)


def test_amplification_appliquee_lineairement(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    asperite = Asperite(TypeAsperite.MONTANTE, 1e-3, 2.0)
    simple = calculer_trainee(asperite, etat_croisiere, couche_croisiere)
    amplifie = calculer_trainee(asperite, etat_croisiere, couche_croisiere, amplification=2.5)
    assert amplifie.trainee == pytest.approx(2.5 * simple.trainee)


@pytest.mark.parametrize("argument", (0, 1, 2))
def test_nash_bradshaw_refuse_les_rapports_nuls(argument: int) -> None:
    valeurs = [1.0, 1.0, 1.0]
    valeurs[argument] = 0.0
    with pytest.raises(ValueError):
        facteur_amplification_nash_bradshaw(*valeurs)
