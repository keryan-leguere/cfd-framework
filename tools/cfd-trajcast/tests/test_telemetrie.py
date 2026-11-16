"""Télémétrie : grandeurs calculées ou lues dans n'importe quelle colonne, formats, panneau."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from conftest import VOL, dataframe_enu_quaternion

from cfd_trajcast.data.configuration import ConfigTelemetrie, Grandeur, grandeur_calculee
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.engine.telemetrie import G0, PanneauTelemetrie, formater, series

FINE, NBSP = "\N{NARROW NO-BREAK SPACE}", "\N{NO-BREAK SPACE}"


@pytest.fixture
def traj() -> Trajectoire:
    df = dataframe_enu_quaternion()
    df["pdyn"] = VOL.pression_dynamique(df["t"].to_numpy())
    df["DL"] = np.sin(df["t"])
    return Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion")


def _cfg(*noms: str) -> ConfigTelemetrie:
    return ConfigTelemetrie(grandeurs=tuple(grandeur_calculee(n) for n in noms))


def test_valeurs_calculees(traj: Trajectoire) -> None:
    s = {x.cle: x for x in series(traj, _cfg("altitude", "vitesse", "mach", "acceleration", "incidence_totale"))}
    k = (traj.t > 0.3) & (traj.t < traj.t[-1] - 0.3) & (np.abs(traj.t - VOL.duree_propulsion) > 0.15)
    np.testing.assert_allclose(s["altitude"].valeurs, VOL.position(traj.t)[:, 2], atol=1e-9)
    np.testing.assert_allclose(s["vitesse"].valeurs[k], np.linalg.norm(VOL.vitesse(traj.t), axis=1)[k], atol=1e-6)
    np.testing.assert_allclose(s["mach"].valeurs[k], VOL.mach(traj.t)[k], atol=1e-6)
    # Accélération cinématique, en g.
    a_vraie = np.linalg.norm(VOL.acceleration(traj.t), axis=1) / G0
    np.testing.assert_allclose(s["acceleration"].valeurs[k], a_vraie[k], atol=1e-4)
    # Incidence nulle par construction (nez dans la vitesse), en degrés.
    assert np.nanmax(np.abs(s["incidence_totale"].valeurs[k])) < 1e-3
    assert s["acceleration"].unite == "g" and s["incidence_totale"].unite == "°"
    assert s["mach"].source == "calculée"


def test_colonnes_quelconques(traj: Trajectoire) -> None:
    cfg = ConfigTelemetrie(grandeurs=(
        Grandeur(cle="pdyn", libelle="q₀", unite="kPa", facteur=1e-3, colonne="pdyn"),
        Grandeur(cle="DL", libelle="DL", colonne="DL", couleur="#123456"),
        Grandeur(cle="q1", libelle="q1", colonne="q1"),        # même une colonne d'attitude
        grandeur_calculee("altitude", "km"),
    ))
    pdyn, dl, qx, alt = series(traj, cfg)
    np.testing.assert_allclose(pdyn.valeurs, VOL.pression_dynamique(traj.t) / 1000, rtol=1e-9)
    assert pdyn.source == "colonne pdyn" and dl.couleur == "#123456" and pdyn.couleur != dl.couleur
    np.testing.assert_allclose(dl.valeurs, np.sin(traj.t))
    np.testing.assert_allclose(qx.valeurs, traj.brut.attitude[:, 1])
    np.testing.assert_allclose(alt.valeurs, traj.positions[:, 2] / 1000)


def test_colonne_absente(traj: Trajectoire) -> None:
    with pytest.raises(ValueError, match="« DM » absente"):
        series(traj, ConfigTelemetrie(grandeurs=(Grandeur(cle="DM", libelle="DM", colonne="DM"),)))


@pytest.mark.parametrize(("v", "u", "d", "texte"), [
    (7273.4, "m", 0, "7" + FINE + "273" + NBSP + "m"),
    (44.53, "m/s", None, "44,5" + NBSP + "m/s"),
    (412.2, "m/s", None, "412" + NBSP + "m/s"),
    (1.0712, "", 2, "1,07"),
    (-3.14159, "°", None, "−3,14" + NBSP + "°"),
    (0.0042, "", 4, "0,0042"),
    (float("nan"), "°", 1, "—" + NBSP + "°"),
])
def test_formater(v: float, u: str, d: int | None, texte: str) -> None:
    assert formater(v, u, d) == texte


@pytest.mark.parametrize("taille", [(540, 1080), (960, 540), (300, 200)])
@pytest.mark.parametrize("n", [1, 4, 8])
def test_panneau(traj: Trajectoire, taille: tuple[int, int], n: int) -> None:
    noms = ["altitude", "vitesse", "mach", "acceleration", "incidence_totale"]
    grandeurs = [grandeur_calculee(x) for x in noms] + [
        Grandeur(cle=c, libelle=f"Une colonne au libellé très long : {c}", colonne=c) for c in ("pdyn", "DL", "q0")]
    p = PanneauTelemetrie(series(traj, ConfigTelemetrie(grandeurs=tuple(grandeurs[:n]))), taille, 0.0, float(traj.t[-1]))
    a, b = p.image(2.0), p.image(30.0)
    assert a.shape == (taille[1], taille[0], 3) and a.dtype == np.uint8
    assert np.abs(a.astype(int) - b.astype(int)).sum() > 0  # l'animation change l'image
    np.testing.assert_array_equal(p.image(2.0), a)          # et redessiner est idempotent


def test_grandeurs_avion() -> None:
    from cfd_trajcast.core.manoeuvres import Conditions, Segment, simuler

    sim = simuler(Conditions(position=(0, 0, 2000), vitesse=200), [Segment(30, inclinaison=45, pente=0, vitesse=200)])
    df = pd.DataFrame({"t": sim.t, "x": sim.positions[:, 0], "y": sim.positions[:, 1], "z": sim.positions[:, 2],
                       "q0": sim.attitudes[:, 0], "q1": sim.attitudes[:, 1], "q2": sim.attitudes[:, 2],
                       "q3": sim.attitudes[:, 3]})
    traj = Trajectoire.depuis_dataframe(df, repere="ENU", attitude="quaternion")
    s = {x.cle: x for x in series(traj, _cfg("facteur_de_charge", "cap", "pente", "roulis", "tangage", "lacet"))}
    stable = (traj.t > 15) & (traj.t < traj.t[-1] - 1)
    assert np.median(s["facteur_de_charge"].valeurs[stable]) == pytest.approx(np.sqrt(2), abs=0.05)
    assert np.median(s["roulis"].valeurs[stable]) == pytest.approx(45, abs=2)
    assert np.abs(s["pente"].valeurs[stable]).max() < 1.0
    np.testing.assert_allclose(np.unwrap(np.radians(s["cap"].valeurs[stable])),
                               np.unwrap(np.radians(sim.donnees["cap"][stable])), atol=0.02)
