"""Adaptateur RocketPy : conventions (faux Flight, sans RocketPy) puis une vraie simulation."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.data import rocketpy_ as rp
from cfd_trajcast.data.configuration import ErreurConfiguration, charger_configuration
from cfd_trajcast.data.trajectoire import Evenement


class Fonction:
    """Imite rocketpy.Function : get_value sur un tableau."""

    def __init__(self, f):  # type: ignore[no-untyped-def]
        self.f = f

    def get_value(self, t):  # type: ignore[no-untyped-def]
        return self.f(np.asarray(t))


def faux_flight(elevation: float = 150.0, doublon: bool = False) -> SimpleNamespace:
    """Montée droite à 80° d'inclinaison, cap 30° ; corps RocketPy : z vers le nez, roulis nul."""
    t = np.linspace(0.0, 20.0, 201)
    if doublon:
        t = np.insert(t, 50, t[50])
    inclinaison, cap = np.radians(80.0), np.radians(30.0)
    u = np.array([np.cos(inclinaison) * np.sin(cap), np.cos(inclinaison) * np.cos(cap), np.sin(inclinaison)])
    s = 5.0 * t**2
    p = s[:, None] * u + np.array([0.0, 0.0, elevation])
    v = (10.0 * t)[:, None] * u
    # Repère corps RocketPy : z_rp = u, x_rp horizontal, y_rp = z_rp × x_rp.
    x_rp = np.array([np.cos(cap), -np.sin(cap), 0.0])
    y_rp = np.cross(u, x_rp)
    q = np.tile(rot.depuis_matrice(np.stack([x_rp, y_rp, u], axis=1)), (len(t), 1))
    sol = np.column_stack([t, p, v, q, np.zeros((len(t), 3))])
    return SimpleNamespace(
        solution=sol.tolist(), env=SimpleNamespace(elevation=elevation),
        out_of_rail_time=0.4, apogee_time=99.0, rocket=SimpleNamespace(motor=SimpleNamespace(burn_out_time=3.9)),
        parachute_events=[[12.0, SimpleNamespace(name="Principal")]], terminate_on_apogee=False,
        mach_number=Fonction(lambda tt: tt / 10.0), speed=Fonction(lambda tt: 10.0 * tt),
        name="faux", _u=u, _x_rp=x_rp,
    )


def test_conventions_faux_flight() -> None:
    f = faux_flight()
    traj = rp.trajectoire_depuis_flight(f)
    # Origine à la rampe : l'élévation est retranchée.
    assert np.allclose(traj.positions[0], 0.0)
    # Le nez (x FRD) est l'axe z de RocketPy ; y FRD = x RocketPy ; z FRD = y RocketPy.
    assert np.allclose(traj.axe_nez, f._u, atol=1e-12)
    assert np.allclose(rot.tourner(traj.attitude, np.array([0.0, 1.0, 0.0])), f._x_rp, atol=1e-12)
    # Grandeurs échantillonnées, absentes ignorées sans erreur.
    assert np.allclose(traj.donnees["mach_number"], traj.t / 10.0)
    assert "dynamic_pressure" not in traj.donnees
    assert any(c.code == "rocketpy_grandeurs" for c in traj.constats)


def test_evenements_faux_flight() -> None:
    traj = rp.trajectoire_depuis_flight(faux_flight(), evenements=[Evenement(5.0, "Mach 1")])
    noms = [e.nom for e in traj.evenements]
    # Apogée hors du vol (99 s) : écartée ; pas d'impact (le vol finit en l'air).
    assert noms == ["Sortie de rampe", "Fin de propulsion", "Mach 1", "Parachute « Principal »"]


def test_instants_repetes_retires() -> None:
    traj = rp.trajectoire_depuis_flight(faux_flight(doublon=True))
    assert np.all(np.diff(traj.t) > 0)
    assert any(c.code == "rocketpy_doublons" for c in traj.constats)


def test_objet_qui_n_est_pas_un_flight() -> None:
    with pytest.raises(rp.ErreurRocketPy, match=r"rocketpy\.Flight"):
        rp.trajectoire_depuis_flight(object())


def _script(dossier: Path, compteur: Path) -> Path:
    """Un script qui rend un faux Flight et compte ses exécutions."""
    (dossier / "faux.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, {str(Path(__file__).parent)!r})\n"
        "from test_rocketpy import faux_flight\n"
        "def simuler():\n"
        f"    with open({str(compteur)!r}, 'a') as f:\n"
        "        f.write('x')\n"
        "    return faux_flight()\n",
        encoding="utf-8",
    )
    return dossier / "faux.py"


def test_script_et_cache(tmp_path: Path) -> None:
    compteur = tmp_path / "compteur.log"  # .log : hors des fichiers d entree hachés
    script = _script(tmp_path, compteur)
    a = rp.trajectoire_depuis_script(script)
    b = rp.trajectoire_depuis_script(script)
    assert compteur.read_text() == "x"  # la seconde lecture vient du cache
    assert np.array_equal(a.positions, b.positions) and np.array_equal(a.attitude, b.attitude)
    assert [e.nom for e in a.evenements] == [e.nom for e in b.evenements]
    assert any(c.code == "cache" for c in b.constats)
    rp.trajectoire_depuis_script(script, utiliser_cache=False)
    assert compteur.read_text() == "xx"
    # Un fichier d'entrée du dossier qui change invalide le cache.
    (tmp_path / "moteur.eng").write_text("poussée", encoding="utf-8")
    rp.trajectoire_depuis_script(script)
    assert compteur.read_text() == "xxx"


def test_script_sans_fonction(tmp_path: Path) -> None:
    (tmp_path / "vide.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(rp.ErreurRocketPy, match="simuler"):
        rp.trajectoire_depuis_script(tmp_path / "vide.py")


def test_configuration_rocketpy(tmp_path: Path) -> None:
    compteur = tmp_path / "compteur.log"  # .log : hors des fichiers d entree hachés
    _script(tmp_path, compteur)
    (tmp_path / "MAQ.stl").write_bytes(b"")
    yaml = tmp_path / "C.yaml"
    yaml.write_text(
        "trajectoire: { source: rocketpy, script: faux.py, evenements: [{t: 5, nom: Mach 1}] }\n"
        "maquette: { fichier: MAQ.stl, unite: m, axe_nez: '+X', axe_haut: '+Z' }\n", encoding="utf-8")
    cfg = charger_configuration(yaml)
    assert cfg.trajectoire.source == "rocketpy" and cfg.trajectoire.fonction == "simuler"
    traj = cfg.trajectoire.charger()
    assert "Mach 1" in [e.nom for e in traj.evenements]
    yaml.write_text(yaml.read_text().replace("source: rocketpy,", "source: rocketpy, repere: ENU,"),
                    encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match="inutile"):
        charger_configuration(yaml)


# -- une vraie simulation ----------------------------------------------------------------
@pytest.mark.skipif(sys.version_info < (3, 10), reason="RocketPy exige Python ≥ 3.10")
def test_vraie_simulation(exemple: Path) -> None:
    pytest.importorskip("rocketpy")
    traj = rp.trajectoire_depuis_script(exemple / "ROCKETPY" / "vol_rocketpy.py")
    assert np.allclose(traj.positions[0], 0.0, atol=1e-6)  # origine à la rampe
    noms = [e.nom for e in traj.evenements]
    for nom in ("Sortie de rampe", "Fin de propulsion", "Apogée", "Parachute « Principal »", "Impact"):
        assert nom in noms
    t_rampe = next(e.t for e in traj.evenements if e.nom == "Sortie de rampe")
    t_fin = next(e.t for e in traj.evenements if e.nom == "Fin de propulsion")
    # Propulsé et hors de la rampe : le nez suit la vitesse (convention corps et quaternion justes).
    k = (traj.t > t_rampe + 0.2) & (traj.t < t_fin)
    v = traj.vitesse[k] / np.linalg.norm(traj.vitesse[k], axis=1, keepdims=True)
    angle = np.degrees(np.arccos(np.clip(np.sum(v * traj.axe_nez[k], axis=1), -1, 1)))
    assert np.median(angle) < 2.0
    # Inclinaison 85°, cap 30° : le nez au départ.
    nez0 = traj.axe_nez[0]
    assert np.degrees(np.arcsin(nez0[2])) == pytest.approx(85.0, abs=0.5)
    assert np.degrees(np.arctan2(nez0[0], nez0[1])) == pytest.approx(30.0, abs=0.5)
    assert {"mach_number", "dynamic_pressure", "angle_of_attack"} <= set(traj.donnees)
