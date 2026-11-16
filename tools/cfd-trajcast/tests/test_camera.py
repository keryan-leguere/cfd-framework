"""Caméra de poursuite : distance, route lissée, placement."""

from __future__ import annotations

import numpy as np
import pytest

from cfd_trajcast.core.camera import (
    ParametresPoursuite,
    distance_auto,
    piste_poursuite,
    route_lissee,
)


def test_distance_auto() -> None:
    d = distance_auto(3.0, 0.5, 30.0)
    # À cette distance, la hauteur visible vaut 2·d·tan(15°) = longueur / cadrage.
    assert 2 * d * np.tan(np.radians(15)) == pytest.approx(6.0)


def test_route_et_retombees() -> None:
    v = np.array([[0, 0, 10.0], [0, 0, 10.0], [3, 4, 10.0], [0, 0, 5.0], [0, 0, 1.0]])
    r = route_lissee(v, np.arange(5.0), lissage=0.0)
    # Indéfinie au début : reprise de la première définie ; ensuite, gardée.
    np.testing.assert_allclose(r, np.tile([0.6, 0.8, 0.0], (5, 1)))
    np.testing.assert_allclose(route_lissee(np.tile([0, 0, 1.0], (3, 1)), np.arange(3.0), 0.0),
                               np.tile([0, 1.0, 0], (3, 1)))


def test_lissage_progressif() -> None:
    v = np.array([[0, 1.0, 0]] * 10 + [[1.0, 0, 0]] * 50)
    r = route_lissee(v, np.arange(60) / 30, lissage=0.5)
    np.testing.assert_allclose(np.linalg.norm(r, axis=1), 1.0)
    angle = np.degrees(np.arctan2(r[:, 0], r[:, 1]))
    assert angle[10] < 10 and 80 < angle[-1] <= 90.0
    assert np.all(np.diff(angle) >= -1e-9)


def test_placement() -> None:
    p = ParametresPoursuite(distance=10.0, azimut=90.0, elevation=0.0, lissage=0.0)
    piste = piste_poursuite(np.arange(2.0), np.array([[0, 50.0, 1], [0, 50.0, 1]]), 3.0, p)
    # Route au Nord, caméra à droite (Est), regardant la fusée.
    np.testing.assert_allclose(piste.decalage[0], [10.0, 0, 0], atol=1e-12)
    p = ParametresPoursuite(distance=10.0, azimut=0.0, elevation=30.0, lissage=0.0)
    d = piste_poursuite(np.arange(1.0), np.array([[0, 50.0, 0]]), 3.0, p).decalage[0]
    np.testing.assert_allclose(d, [0, -10 * np.cos(np.radians(30)), 5.0], atol=1e-12)


@pytest.mark.parametrize("champs", [{"cadrage": 0}, {"elevation": 90}, {"distance": -1}, {"champ": 0}])
def test_parametres_controles(champs: dict) -> None:  # type: ignore[type-arg]
    with pytest.raises(ValueError):
        ParametresPoursuite(**champs)


def test_sol_vise_et_zoome() -> None:
    from cfd_trajcast.core.camera import ParametresSol, piste_sol

    positions = np.array([[0.0, 0.0, 100.0], [0.0, 0.0, 1000.0]])
    p = ParametresSol(position=(300.0, 0.0, 0.0), cadrage=0.25)
    piste = piste_sol(positions, 3.0, p)
    np.testing.assert_allclose(piste.decalage, [[300, 0, -100], [300, 0, -1000]])
    d = np.linalg.norm(piste.decalage, axis=1)
    # Hauteur visible à la distance de la fusée = longueur / cadrage.
    np.testing.assert_allclose(2 * d * np.tan(np.radians(piste.champ) / 2), 12.0, rtol=1e-12)
    fixe = piste_sol(positions, 3.0, ParametresSol(position=(300.0, 0.0, 0.0), champ=20.0))
    np.testing.assert_allclose(fixe.champ, 20.0)


def test_sol_a_la_verticale() -> None:
    from cfd_trajcast.core.camera import ParametresSol, piste_sol

    piste = piste_sol(np.array([[0.0, 0.0, 500.0]]), 3.0, ParametresSol(position=(0.0, 0.0, 0.0)))
    np.testing.assert_allclose(piste.haut[0], [0, 1, 0])  # pas de « haut » colinéaire à la visée


def test_embarquee_suit_le_corps() -> None:
    from cfd_trajcast.core import rotations as rot
    from cfd_trajcast.core.camera import ParametresEmbarquee, piste_embarquee

    q = rot.elementaire("z", np.array([0.0, np.pi / 2]))  # nez à l'Est, puis au Nord
    p = ParametresEmbarquee(position_corps=(-1.0, 0.0, -0.2), visee=(1.0, 0.0, 0.0))
    piste = piste_embarquee(q, p)
    np.testing.assert_allclose(piste.decalage, [[-1, 0, -0.2], [0, -1, -0.2]], atol=1e-12)
    np.testing.assert_allclose(piste.visee - piste.decalage, [[1, 0, 0], [0, 1, 0]], atol=1e-12)
    # Quaternion identité : FRD aligné sur ENU, donc ventre en l'air — le « haut » de l'image
    # (−z corps) pointe vers le bas. C'est la convention, pas une erreur.
    np.testing.assert_allclose(piste.haut, [[0, 0, -1], [0, 0, -1]], atol=1e-12)


def test_vers_ned_et_echelle() -> None:
    from cfd_trajcast.core.camera import ParametresEnsemble, echelle_ensemble, vers_ned

    np.testing.assert_allclose(vers_ned([[1.0, 2.0, 3.0]]), [[2.0, 1.0, -3.0]])
    pos = np.array([[0.0, 0.0, 0.0], [0.0, 1000.0, 5000.0]])
    assert echelle_ensemble(pos, 2.5, ParametresEnsemble(part_fusee=0.1)) == pytest.approx(200.0)
    assert echelle_ensemble(pos, 2.5, ParametresEnsemble(echelle_fusee=7.0)) == 7.0
    assert echelle_ensemble(pos[:1] + np.array([[0, 0, 1.0]]), 2.5, ParametresEnsemble()) == 1.0  # jamais rétrécie


@pytest.mark.parametrize("aspect", [0.6, 16 / 9])
@pytest.mark.parametrize("elevation", [5.0, 35.0])
def test_cadre_ensemble_tient_la_boite(aspect: float, elevation: float) -> None:
    from cfd_trajcast.core.camera import ParametresEnsemble, cadre_ensemble, vers_ned

    pos = np.array([[0.0, 0.0, 0.0], [1100.0, 1900.0, 7300.0], [1600.0, 2700.0, 6000.0]])
    p = ParametresEnsemble(elevation=elevation, cadrage=0.8, champ=30.0)
    position, vise, haut = cadre_ensemble(pos, p, aspect)
    ned = vers_ned(pos)
    mini, maxi = ned.min(0), ned.max(0)
    maxi[2] = max(maxi[2], 0)
    coins = np.array([[x, y, z] for x in (mini[0], maxi[0]) for y in (mini[1], maxi[1]) for z in (mini[2], maxi[2])])
    avant = (vise - position) / np.linalg.norm(vise - position)
    droite = np.cross(avant, haut)
    droite /= np.linalg.norm(droite)
    h = np.cross(droite, avant)
    d = coins - position
    tan_v = np.tan(np.radians(15)) * 0.8
    x, y = np.abs(d @ droite) / (d @ avant), np.abs(d @ h) / (d @ avant)
    assert np.all(x <= tan_v * aspect + 1e-9) and np.all(y <= tan_v + 1e-9)
    assert max(x.max() / (tan_v * aspect), y.max() / tan_v) == pytest.approx(1.0)  # ajusté, pas lâche
    # Azimut auto : de flanc, un peu en arrière, du côté droit de la route (route + 110°).
    route = np.degrees(np.arctan2(1600.0, 2700.0))  # cap du premier au dernier point (E, N)
    cote = np.degrees(np.arctan2(*(position - vise)[[1, 0]]))
    assert cote == pytest.approx(route + 110, abs=1e-6)


def test_orbite() -> None:
    from cfd_trajcast.core.camera import ParametresOrbite, piste_orbite

    p = ParametresOrbite(distance=10.0, azimut=0.0, elevation=0.0, vitesse_angulaire=90.0)
    piste = piste_orbite(np.array([0.0, 1.0, 2.0]), 3.0, p)
    # Nord, puis Est, puis Sud : un quart de tour par seconde de vidéo.
    np.testing.assert_allclose(piste.decalage, [[0, 10, 0], [10, 0, 0], [0, -10, 0]], atol=1e-12)


def test_images_cles() -> None:
    from cfd_trajcast.core.camera import Cle, ParametresImagesCles, piste_images_cles

    p = ParametresImagesCles(cles=(Cle(0.0, azimut=350.0, elevation=0.0, distance=10.0),
                                   Cle(2.0, azimut=10.0, elevation=30.0, distance=20.0)), lissage=0.0)
    t = np.array([0.0, 1.0, 2.0, 3.0])
    v = np.tile([0.0, 50.0, 0.0], (4, 1))     # route au Nord
    piste = piste_images_cles(t, t, v, 3.0, p)
    d = np.linalg.norm(piste.decalage, axis=1)
    np.testing.assert_allclose(d, [10, 15, 20, 20])
    # Par le petit arc (350° → 10°, via 0°) : à mi-chemin la caméra est juste derrière.
    np.testing.assert_allclose(piste.decalage[1] / d[1], [0, -np.cos(np.radians(15)), np.sin(np.radians(15))], atol=1e-12)
    with pytest.raises(ValueError, match="croissants"):
        ParametresImagesCles(cles=(Cle(2.0), Cle(1.0)))


def test_poursuite_lisse_le_virage() -> None:
    import pandas as pd

    from cfd_trajcast.core.camera import ParametresPoursuite, piste_poursuite
    from cfd_trajcast.data.trajectoire import Trajectoire
    from cfd_trajcast.paths import EXEMPLE_DIR

    df = pd.read_csv(EXEMPLE_DIR / "vol_virage.csv", comment="#")
    traj = Trajectoire.depuis_dataframe(df, repere="ENU", attitude={"type": "quaternion", "colonnes": ["qw", "qx", "qy", "qz"]})
    t = np.arange(0.5, 50.0, 1 / 30)
    piste = piste_poursuite(t, traj.vitesse_a(t), 2.87, ParametresPoursuite())
    u = piste.decalage / np.linalg.norm(piste.decalage, axis=1, keepdims=True)
    pivot = np.degrees(np.arccos(np.clip(np.sum(u[1:] * u[:-1], axis=1), -1, 1)))
    route = np.degrees(np.arctan2(*traj.vitesse_a(t)[:, :2].T))
    assert route.max() - route.min() > 65          # le virage a bien lieu
    assert pivot.max() < 0.5                       # sans à-coup d'une image à l'autre
