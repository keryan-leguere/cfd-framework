"""Local state, wall conditions and the flat-plate correlation.

The point of these tests is not that the 1/7-power law is right — it is an
engineering correlation — but that cfd-aq uses it consistently: that τ_w, C_fe
and q_e stay mutually coherent, that the wall values h⁺ is built on are wall
values, and that handing in a measured τ_w bypasses the correlation exactly.
"""

from __future__ import annotations

import math

import pytest

from cfd_aq.core.couche_limite import (
    CoucheLimite,
    EtatLocal,
    cf_plaque_plane,
    epaisseur_plaque_plane,
    temperature_paroi_adiabatique,
    temperature_reference_eckert,
    viscosite_sutherland,
)

# --- état local -----------------------------------------------------------


def test_sutherland_a_la_temperature_de_reference() -> None:
    assert viscosite_sutherland(273.15) == pytest.approx(1.716e-5, rel=1e-12)
    assert viscosite_sutherland(288.15) == pytest.approx(1.789e-5, rel=5e-3)


def test_sutherland_croit_avec_la_temperature() -> None:
    valeurs = [viscosite_sutherland(t) for t in (200.0, 250.0, 300.0, 500.0)]
    assert all(v1 > v0 for v0, v1 in zip(valeurs, valeurs[1:]))


def test_grandeurs_derivees_coherentes(etat_croisiere: EtatLocal) -> None:
    etat = etat_croisiere
    assert etat.celerite == pytest.approx(math.sqrt(1.4 * 287.05287 * etat.temperature))
    assert etat.vitesse == pytest.approx(etat.mach * etat.celerite)
    assert etat.masse_volumique == pytest.approx(etat.pression / (287.05287 * etat.temperature))
    assert etat.pression_dynamique == pytest.approx(0.5 * etat.masse_volumique * etat.vitesse**2)


def test_pression_dynamique_contre_la_forme_en_mach(etat_croisiere: EtatLocal) -> None:
    """q = ½γpM² is the same number by another route."""
    attendu = 0.5 * 1.4 * etat_croisiere.pression * etat_croisiere.mach**2
    assert etat_croisiere.pression_dynamique == pytest.approx(attendu)


@pytest.mark.parametrize(
    ("champ", "valeur"),
    [("mach", 0.0), ("temperature", -1.0), ("pression", 0.0), ("gamma", 1.0)],
)
def test_etat_non_physique_refuse(champ: str, valeur: float) -> None:
    arguments = {"mach": 0.8, "temperature": 288.15, "pression": 101325.0}
    arguments[champ] = valeur
    with pytest.raises(ValueError):
        EtatLocal(**arguments)


def test_temperature_paroi_adiabatique(etat_croisiere: EtatLocal) -> None:
    """T_aw = T_e·(1 + r·(γ−1)/2·M²), r = Pr^(1/3) ≈ 0.896."""
    etat = etat_croisiere
    r = 0.72 ** (1.0 / 3.0)
    attendu = etat.temperature * (1.0 + r * 0.2 * etat.mach**2)
    assert temperature_paroi_adiabatique(etat) == pytest.approx(attendu)
    assert temperature_paroi_adiabatique(etat) > etat.temperature


def test_temperature_de_reference_entre_paroi_et_bord(etat_croisiere: EtatLocal) -> None:
    t_paroi = temperature_paroi_adiabatique(etat_croisiere)
    t_etoile = temperature_reference_eckert(etat_croisiere, t_paroi)
    assert etat_croisiere.temperature < t_etoile < t_paroi


def test_temperature_de_reference_degenere_en_incompressible() -> None:
    """At M → 0 with a wall at T_e, T* must collapse onto T_e."""
    etat = EtatLocal(mach=1e-6, temperature=288.15, pression=101325.0)
    assert temperature_reference_eckert(etat, 288.15) == pytest.approx(288.15, rel=1e-9)


# --- frottement -----------------------------------------------------------


def test_cf_decroit_avec_la_distance(etat_croisiere: EtatLocal) -> None:
    valeurs = [cf_plaque_plane(etat_croisiere, x) for x in (1.0, 5.0, 10.0, 30.0)]
    assert all(v1 < v0 for v0, v1 in zip(valeurs, valeurs[1:]))


def test_cf_suit_la_loi_en_puissance_moins_un_cinquieme() -> None:
    """Incompressible limit: cf ∝ Re_x^(−1/5), so ×10 on x gives ×10^(−0.2)."""
    etat = EtatLocal(mach=0.05, temperature=288.15, pression=101325.0)
    assert cf_plaque_plane(etat, 10.0) / cf_plaque_plane(etat, 1.0) == pytest.approx(
        10.0**-0.2, rel=1e-3
    )


def test_cf_incompressible_contre_la_valeur_tabulee() -> None:
    """cf = 0.0592·Re_x^(−0.2) at Re_x = 10⁷ is 2.65e-3, a textbook value."""
    etat = EtatLocal(mach=0.05, temperature=288.15, pression=101325.0)
    x = 1e7 * etat.viscosite / (etat.masse_volumique * etat.vitesse)
    assert cf_plaque_plane(etat, x) == pytest.approx(0.0592 * 1e7**-0.2, rel=5e-3)


def test_la_compressibilite_reduit_le_frottement() -> None:
    """At the same Reynolds number, a higher Mach number lowers cf."""
    chaud = EtatLocal(mach=2.5, temperature=216.65, pression=22632.0)
    froid = EtatLocal(mach=0.3, temperature=216.65, pression=22632.0)
    x_chaud = 2e7 * chaud.viscosite / (chaud.masse_volumique * chaud.vitesse)
    x_froid = 2e7 * froid.viscosite / (froid.masse_volumique * froid.vitesse)
    assert cf_plaque_plane(chaud, x_chaud) < cf_plaque_plane(froid, x_froid)


def test_epaisseur_plausible(etat_croisiere: EtatLocal) -> None:
    """δ/x ≈ 1 % after 10 m at flight Reynolds numbers."""
    delta = epaisseur_plaque_plane(etat_croisiere, 10.0)
    assert 0.05 < delta < 0.20


@pytest.mark.parametrize("longueur", (0.0, -1.0))
def test_distance_non_physique_refusee(etat_croisiere: EtatLocal, longueur: float) -> None:
    with pytest.raises(ValueError, match="bord d'attaque"):
        cf_plaque_plane(etat_croisiere, longueur)


# --- couche limite --------------------------------------------------------


def test_les_trois_constructeurs_donnent_la_meme_couche(etat_croisiere: EtatLocal) -> None:
    """depuis_cf, depuis_cisaillement and plaque_plane must agree exactly."""
    par_x = CoucheLimite.plaque_plane(etat_croisiere, 10.0)
    par_cf = CoucheLimite.depuis_cf(etat_croisiere, par_x.cf)
    par_tau = CoucheLimite.depuis_cisaillement(etat_croisiere, par_x.cisaillement_paroi)
    for autre in (par_cf, par_tau):
        assert autre.cf == pytest.approx(par_x.cf)
        assert autre.cisaillement_paroi == pytest.approx(par_x.cisaillement_paroi)
        assert autre.vitesse_frottement == pytest.approx(par_x.vitesse_frottement)
        assert autre.h_plus(1e-3) == pytest.approx(par_x.h_plus(1e-3))


def test_cisaillement_et_cf_sont_lies_par_q(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    assert couche_croisiere.cisaillement_paroi == pytest.approx(
        couche_croisiere.cf * etat_croisiere.pression_dynamique
    )


def test_vitesse_de_frottement_batie_sur_les_valeurs_paroi(
    etat_croisiere: EtatLocal, couche_croisiere: CoucheLimite
) -> None:
    """u_τ uses ρ_w, not ρ_e — the two differ by the T_w/T_e ratio."""
    rho_paroi = etat_croisiere.pression / (
        etat_croisiere.r_gaz * couche_croisiere.temperature_paroi
    )
    assert couche_croisiere.vitesse_frottement == pytest.approx(
        math.sqrt(couche_croisiere.cisaillement_paroi / rho_paroi)
    )
    assert rho_paroi < etat_croisiere.masse_volumique  # paroi plus chaude, donc moins dense


def test_h_plus_proportionnel_a_la_hauteur(couche_croisiere: CoucheLimite) -> None:
    assert couche_croisiere.h_plus(2e-3) == pytest.approx(2.0 * couche_croisiere.h_plus(1e-3))


def test_h_plus_realiste_en_croisiere(couche_croisiere: CoucheLimite) -> None:
    """A 1 mm step at FL360, 10 m aft of the leading edge, lands mid-range."""
    assert 100.0 < couche_croisiere.h_plus(1e-3) < 250.0
    immersion = couche_croisiere.immersion(1e-3)
    assert immersion is not None
    assert immersion < 0.03


def test_immersion_inconnue_sans_epaisseur(etat_croisiere: EtatLocal) -> None:
    couche = CoucheLimite.depuis_cf(etat_croisiere, 0.0015)
    assert couche.epaisseur is None
    assert couche.immersion(1e-3) is None


@pytest.mark.parametrize("hauteur", (0.0, -1e-3))
def test_hauteur_non_physique_refusee(couche_croisiere: CoucheLimite, hauteur: float) -> None:
    with pytest.raises(ValueError, match="hauteur"):
        couche_croisiere.h_plus(hauteur)


def test_cf_non_physique_refuse(etat_croisiere: EtatLocal) -> None:
    with pytest.raises(ValueError, match="Cf"):
        CoucheLimite.depuis_cf(etat_croisiere, 0.0)
    with pytest.raises(ValueError, match="τ_w"):
        CoucheLimite.depuis_cisaillement(etat_croisiere, -1.0)
