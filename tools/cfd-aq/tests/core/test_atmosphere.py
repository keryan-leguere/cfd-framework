"""Atmosphere access, with and without the sibling package ``cfd-atm``.

The point of this module is the last test: the built-in fallback and
``cfd-atm`` must return the same ISA, to the last digit that matters. A
fallback that is allowed to drift is a second model, and a package with two
atmospheres gives two answers depending on what happens to be installed.
"""

from __future__ import annotations

import pytest

from cfd_aq.core import atmosphere
from cfd_aq.core.atmosphere import (
    ALTITUDE_MAX,
    HAS_CFD_ATM,
    PointAtmospherique,
    conditions,
    etat_isa,
    mach_depuis_vitesse,
)

besoin_cfd_atm = pytest.mark.skipif(not HAS_CFD_ATM, reason="cfd-atm n'est pas installé")


@pytest.fixture()
def sans_cfd_atm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the fallback path, whatever is installed."""
    monkeypatch.setattr(atmosphere, "get_cfd_atm", lambda: None)


# --- ISA de base ----------------------------------------------------------


def test_niveau_de_la_mer() -> None:
    temperature, pression = etat_isa(0.0)
    assert temperature == pytest.approx(288.15, abs=1e-3)
    assert pression == pytest.approx(101325.0, rel=1e-6)
    assert pression / (287.05287 * temperature) == pytest.approx(1.225, abs=1e-4)


@pytest.mark.parametrize(
    ("altitude", "temperature", "pression"),
    # Altitudes géopotentielles de la table ISA, converties en géométriques.
    [
        (5004.0, 255.650, 54019.9),
        (11019.1, 216.650, 22632.1),
        (20063.1, 216.650, 5474.89),
    ],
)
def test_contre_la_table_isa(altitude: float, temperature: float, pression: float) -> None:
    t, p = etat_isa(altitude)
    assert t == pytest.approx(temperature, abs=0.02)
    assert p == pytest.approx(pression, rel=2e-4)


def test_pression_decroissante() -> None:
    pressions = [etat_isa(float(z))[1] for z in range(0, 30001, 2000)]
    assert all(p1 < p0 for p0, p1 in zip(pressions, pressions[1:]))


def test_point_annonce_sa_provenance() -> None:
    point = conditions(11000.0)
    assert isinstance(point, PointAtmospherique)
    assert point.modele == "ISA"
    assert point.source == ("cfd-atm" if HAS_CFD_ATM else "repli")


def test_type_altitude_inconnu_refuse() -> None:
    with pytest.raises(ValueError, match="type d'altitude"):
        conditions(1000.0, type_altitude="radioaltimetrique")


# --- ce que seul cfd-atm apporte ------------------------------------------


@besoin_cfd_atm
def test_journee_chaude() -> None:
    """ISA + ΔT shifts T by exactly ΔT and raises the pressure with it."""
    froid = conditions(11000.0)
    chaud = conditions(11000.0, delta_isa=15.0)
    assert chaud.temperature == pytest.approx(froid.temperature + 15.0, abs=1e-6)
    assert chaud.pression > froid.pression
    assert "15" in chaud.modele


@besoin_cfd_atm
def test_altitude_pression() -> None:
    """At a pressure altitude of 11 000 m the ISA pressure is exact by definition."""
    point = conditions(11000.0, type_altitude="pression")
    assert point.pression == pytest.approx(22632.04, rel=1e-5)


@besoin_cfd_atm
def test_altitude_geopotentielle_contre_geometrique() -> None:
    """The geopotential altitude is the smaller of the two, so the air is cooler."""
    geometrique = conditions(11000.0, type_altitude="geometrique")
    geopotentielle = conditions(11000.0, type_altitude="geopotentielle")
    assert geopotentielle.temperature < geometrique.temperature


@besoin_cfd_atm
def test_vitesse_conventionnelle_vers_mach() -> None:
    """FL360: Vc ≈ 140.4 m/s (273 kt) is M = 0.82 — the cruise identity."""
    point = conditions(11000.0)
    assert mach_depuis_vitesse(point, vitesse_conventionnelle=140.437) == pytest.approx(
        0.82, abs=1e-4
    )


@besoin_cfd_atm
def test_les_trois_vitesses_donnent_le_meme_mach() -> None:
    point = conditions(11000.0)
    mach_vc = mach_depuis_vitesse(point, vitesse_conventionnelle=140.437)
    mach_tas = mach_depuis_vitesse(point, vitesse_vraie=242.026)
    mach_eas = mach_depuis_vitesse(point, vitesse_equivalente=132.075)
    assert mach_vc == pytest.approx(mach_tas, abs=1e-4)
    assert mach_vc == pytest.approx(mach_eas, abs=1e-4)


@besoin_cfd_atm
def test_ordre_des_vitesses_en_croisiere() -> None:
    """TAS > Vc > EAS at FL360.

    TAS above the other two is the density effect, and expected. Vc **above**
    EAS is the compressibility one: the pitot over-reads, and the gap is 8 m/s
    at M = 0.82 — which is exactly why a cruise condition must be entered as a
    Mach number or a Vc, never as "the airspeed".
    """
    point = conditions(11000.0)
    cfd_atm = atmosphere.get_cfd_atm()
    assert cfd_atm is not None
    jeu = cfd_atm.airspeeds(point.pression, point.temperature, mach=0.82)
    assert jeu.tas > jeu.cas > jeu.eas


def test_une_seule_vitesse_a_la_fois() -> None:
    point = conditions(0.0)
    with pytest.raises(ValueError, match="exactement une vitesse"):
        mach_depuis_vitesse(point)
    with pytest.raises(ValueError, match="exactement une vitesse"):
        mach_depuis_vitesse(point, vitesse_vraie=100.0, vitesse_equivalente=100.0)


# --- le repli -------------------------------------------------------------


@pytest.mark.usefixtures("sans_cfd_atm")
def test_le_repli_couvre_l_isa_geometrique() -> None:
    point = conditions(11000.0)
    assert point.source == "repli"
    assert point.temperature == pytest.approx(216.7735, abs=1e-3)


@pytest.mark.usefixtures("sans_cfd_atm")
@pytest.mark.parametrize("altitude", (-1.0, ALTITUDE_MAX + 1.0))
def test_le_repli_borne_son_domaine(altitude: float) -> None:
    with pytest.raises(ValueError, match="cfd-atm"):
        conditions(altitude)


@pytest.mark.usefixtures("sans_cfd_atm")
def test_le_repli_refuse_un_ecart_isa() -> None:
    """Never a silently wrong number: the message names the install command."""
    with pytest.raises(RuntimeError) as erreur:
        conditions(11000.0, delta_isa=15.0)
    assert "ΔT" in str(erreur.value)
    assert "pip install -e tools/cfd-atm" in str(erreur.value)


@pytest.mark.usefixtures("sans_cfd_atm")
@pytest.mark.parametrize("type_altitude", ("pression", "geopotentielle"))
def test_le_repli_refuse_les_autres_altitudes(type_altitude: str) -> None:
    with pytest.raises(RuntimeError) as erreur:
        conditions(11000.0, type_altitude=type_altitude)
    assert type_altitude in str(erreur.value)
    assert "pip install -e tools/cfd-atm" in str(erreur.value)


@pytest.mark.usefixtures("sans_cfd_atm")
def test_le_repli_refuse_les_conversions_de_vitesse() -> None:
    point = conditions(5000.0)
    with pytest.raises(RuntimeError, match="pip install -e tools/cfd-atm"):
        mach_depuis_vitesse(point, vitesse_conventionnelle=120.0)


@besoin_cfd_atm
@pytest.mark.parametrize("altitude", (0.0, 1500.0, 5000.0, 11000.0, 20000.0, 31000.0))
def test_le_repli_et_cfd_atm_donnent_la_meme_isa(
    altitude: float, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback is a degraded entry point, never a second model.

    If this ever fails, the fallback has drifted and cfd-aq answers two
    different things depending on what is installed — which is worse than
    having no fallback at all.
    """
    reference = conditions(altitude)
    monkeypatch.setattr(atmosphere, "get_cfd_atm", lambda: None)
    repli = conditions(altitude)
    assert repli.temperature == pytest.approx(reference.temperature, rel=1e-9)
    assert repli.pression == pytest.approx(reference.pression, rel=5e-5)
