"""EtatVol : séries précalculées et état interpolé, cohérents avec la trajectoire."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cfd_trajcast.data.configuration import charger_configuration
from cfd_trajcast.engine.etat_vol import EtatVol


@pytest.fixture(scope="module")
def etat() -> EtatVol:
    from cfd_trajcast.paths import EXEMPLE_DIR

    return EtatVol.depuis_configuration(charger_configuration(Path(EXEMPLE_DIR) / "CONFIG_GUI.yaml"))


def test_series(etat: EtatVol) -> None:
    assert {"altitude", "vitesse", "mach", "incidence", "derapage", "vitesse_air", "xcg"} <= set(etat.series)
    assert {"q0", "roulis (fichier)", "VN", "masse", "poussee", "qw"} <= set(etat.colonnes_fichier())
    assert etat.series["roulis"].source == "calcul"  # la grandeur calculée garde son nom
    assert all(len(s.valeurs) == len(etat.t) for s in etat.series.values())
    assert etat.series["altitude"].unite == "m" and etat.series["incidence"].unite == "°"
    assert etat.series["masse"].unite == "" and etat.series["masse"].source == "colonne"


def test_instant_coherent(etat: EtatVol) -> None:
    traj = etat.trajectoire
    t = 12.34
    i = etat.a(t)
    np.testing.assert_allclose(i.position, traj.etat(np.array([t]))[0][0])
    assert i.valeurs["masse"] == pytest.approx(np.interp(t, traj.t, traj.donnees["masse"]))
    assert i.vent is not None and i.vitesse_air is not None
    np.testing.assert_allclose(i.vitesse_air, i.vitesse_sol - i.vent)
    assert set(i.axes) == {"corps", "ned", "trajectoire", "aero"}
    # Le nez est dans la vitesse sol (vol de référence) : avec du vent, l'incidence n'est plus nulle.
    assert abs(np.degrees(i.incidence)) + abs(np.degrees(i.derapage)) > 0.01


def test_borne(etat: EtatVol) -> None:
    assert etat.a(-5.0).t == etat.debut and etat.a(1e6).t == etat.fin
