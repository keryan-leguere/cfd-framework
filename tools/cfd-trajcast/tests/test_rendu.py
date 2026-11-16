"""Rendu : la chaîne repères → CAO → caméra est vérifiée géométriquement.

La silhouette rendue doit avoir exactement la boîte englobante de la projection
des sommets (modèle sténopé de la caméra VTK). Une erreur de convention (quaternion
conjugué, axe de la CAO, caméra) la déplace ou la tourne : à quelques pixels près,
la comparaison est indépendante du pilote OpenGL (GPU ou llvmpipe).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from conftest import dataframe_enu_quaternion

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.camera import ParametresPoursuite, PisteCamera
from cfd_trajcast.core.disposition import Case
from cfd_trajcast.data.configuration import ConfigVideo
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.engine.encodage import sonder_video
from cfd_trajcast.engine.pipeline import Film
from cfd_trajcast.engine.rendu.pyvista_ import MoteurPyVista
from cfd_trajcast.engine.scene import Plan, Scene

pytestmark = pytest.mark.usefixtures("rendu")
L, H = 320, 240


@pytest.fixture
def maquette(exemple: Path) -> Maquette:
    return Maquette.depuis_fichier(exemple / "MAQUETTE" / "Aim9.stl", unite="mm", axe_nez="-X",
                                   axe_haut="+Z", origine=(19.05, 0, 0), longueur_imposee=2.87)


def _projection(points: np.ndarray, camera: np.ndarray, champ: float) -> np.ndarray:
    avant = -camera / np.linalg.norm(camera)
    droite = np.cross(avant, [0.0, 0.0, 1.0])
    droite /= np.linalg.norm(droite)
    haut = np.cross(droite, avant)
    d = points - camera
    f = (H / 2) / np.tan(np.radians(champ) / 2)
    x = L / 2 + f * (d @ droite) / (d @ avant)
    y = H / 2 - f * (d @ haut) / (d @ avant)
    return np.stack([x, y], axis=1)


@pytest.mark.parametrize(("euler", "camera"), [
    ((30.0, 20.0, 45.0), (6.0, -4.0, 2.0)),
    ((-120.0, 70.0, 10.0), (-3.0, 5.0, -1.5)),
    ((0.0, -10.0, 170.0), (0.5, 7.0, 0.5)),
])
def test_silhouette_egale_projection(maquette: Maquette, euler: tuple, camera: tuple) -> None:  # type: ignore[type-arg]
    q = rot.depuis_euler(np.radians(euler), "ZYX")
    cam = np.array(camera, dtype=float)
    plan = Plan(
        t_video=np.zeros(1), t_vol=np.zeros(1), positions=np.array([[100.0, -50.0, 900.0]]),
        attitudes=q[None, :],
        cameras={"v": PisteCamera(decalage=cam[None, :], visee=np.zeros((1, 3)),
                                  haut=np.array([[0.0, 0.0, 1.0]]), champ=np.array([40.0]))},
        ensembles={},
        agencements=((Case("v", 0, 0, L, H),),), etape=np.zeros(1, dtype=np.int64),
        etape_prec=np.zeros(1, dtype=np.int64), fondu=np.zeros(1), ips=1.0, largeur=L, hauteur=H,
    )
    scene = Scene(maquette=maquette, fond="#ffffff", couleur_fusee="#202020")
    with MoteurPyVista(scene, plan) as m:
        image = m.image(0)
    assert image.shape == (H, L, 3)
    masque = np.any(np.abs(image.astype(int) - 255) > 60, axis=2)
    ys, xs = np.nonzero(masque)
    attendu = _projection(maquette.sommets @ rot.vers_matrice(q).T, cam, 40.0)
    np.testing.assert_allclose([xs.min(), xs.max() + 1], [attendu[:, 0].min(), attendu[:, 0].max()], atol=2.5)
    np.testing.assert_allclose([ys.min(), ys.max() + 1], [attendu[:, 1].min(), attendu[:, 1].max()], atol=2.5)


def test_film_mp4(tmp_path: Path, maquette: Maquette) -> None:
    traj = Trajectoire.depuis_dataframe(dataframe_enu_quaternion(), repere="ENU", attitude="quaternion")
    film = Film(traj, maquette, video=ConfigVideo(resolution=(128, 72), ips=10, preset="ultrafast"),
                vues={"poursuite": ParametresPoursuite()})
    r = film.rendre(tmp_path / "v.mp4", de=1.0, a=2.0)
    info = sonder_video(r.chemin)
    assert (info.largeur, info.hauteur, info.n_images) == (128, 72, 10)
    assert r.t_vol == (1.0, pytest.approx(1.9))
    img = film.image(5.0, tmp_path / "i.png")
    assert img.shape == (72, 128, 3) and img.std() > 5


def test_film_multivues(tmp_path: Path, exemple: Path) -> None:
    from dataclasses import replace

    from cfd_trajcast.data.configuration import charger_configuration

    cfg = charger_configuration(exemple / "CONFIG_MULTIVUES.yaml")
    cfg = replace(cfg, video=ConfigVideo(resolution=(320, 180), ips=10, preset="ultrafast"))
    film = Film.depuis_configuration(cfg)
    r = film.rendre(tmp_path / "mv.mp4", de=1.0, a=4.0)
    info = sonder_video(r.chemin)
    assert (info.largeur, info.hauteur, info.n_images) == (320, 180, 30)
    # Grille à t = 40 s : la case télémétrie (en bas à droite) est sombre, les vues claires.
    img = film.image(40.0).astype(float)
    assert img[100:, 170:].mean() < 60 and img[:80, :150].mean() > 150


def test_vue_ensemble(tmp_path: Path, exemple: Path) -> None:
    from dataclasses import replace

    from cfd_trajcast.data.configuration import charger_configuration

    cfg = charger_configuration(exemple / "CONFIG_ENSEMBLE.yaml")
    cfg = replace(cfg, video=ConfigVideo(resolution=(640, 360), ips=10, preset="ultrafast"),
                  montage=replace(cfg.montage, titre_debut=0, generique_fin=0, bandeaux_evenements=False))
    film = Film.depuis_configuration(cfg)

    def orange(t: float) -> int:  # pixels du trajet parcouru dans la colonne de la vue d'ensemble
        img = film.image(t).astype(int)[:, :280]
        return int(np.count_nonzero((img[..., 0] > 200) & (img[..., 1] > 90) & (img[..., 1] < 160) & (img[..., 2] < 80)))

    # La partie parcourue (orange) s'allonge au fil du vol.
    debut, milieu, fin = orange(8.0), orange(25.0), orange(50.0)
    assert 0 < debut < milieu < fin


def _film_style(exemple: Path, sans_propulsion: bool = False, **style):  # type: ignore[no-untyped-def]
    from dataclasses import replace

    from cfd_trajcast.data.configuration import ConfigMontage, charger_configuration

    cfg = charger_configuration(exemple / "CONFIG_VIRAGE.yaml")
    cfg = replace(cfg, video=replace(cfg.video, resolution=(320, 180), preset="ultrafast"),
                  montage=ConfigMontage(titre_debut=0, generique_fin=0, bandeaux_evenements=False,
                                        etiquettes_vues=False),
                  disposition=replace(cfg.disposition, type="unique", incrustations=(), telemetrie="aucune"),
                  style=replace(cfg.style, **style),
                  propulsion=None if sans_propulsion else cfg.propulsion)
    return Film.depuis_configuration(cfg)


def test_ciel_et_trainee(exemple: Path) -> None:
    film = _film_style(exemple)
    apogee = film.image(40.5).astype(int)          # caméra à l'horizontale : du ciel en haut
    assert apogee[2, :, 2].mean() < apogee[60, :, 2].mean() + 1  # dégradé : bleu plus foncé en haut
    assert apogee[2, :, 0].mean() < apogee[60, :, 0].mean()
    # La fumée est éclairée (grise côté ombre) : on compare aux images sans traînée.
    sans_film = _film_style(exemple, sans_propulsion=True)
    change = lambda a, b: int(np.count_nonzero(np.abs(a.astype(int) - b.astype(int)).max(axis=2) > 30))  # noqa: E731
    assert change(film.image(3.0), sans_film.image(3.0)) > 200    # visible pendant la propulsion
    assert change(film.image(12.0), sans_film.image(12.0)) < 20   # disparue après


def test_trainee_evenement_inconnu(exemple: Path) -> None:
    with pytest.raises(ValueError, match="événement « Largage » inconnu"):
        _film_style(exemple, sans_propulsion=True, trainee=True, trainee_jusqu_a="Largage")


def test_ralentis_dans_la_video(tmp_path: Path, exemple: Path) -> None:
    film = _film_style(exemple)
    plan = film.plan(de=2.0, a=6.0)   # ralenti ×4 sur [3,4 ; 4,6], rampes de 0,5 s
    v = np.diff(plan.t_vol) * plan.ips
    assert v.min() == pytest.approx(0.25) and v.max() == pytest.approx(1.0, abs=1e-9)
    r = film.rendre(tmp_path / "r.mp4", de=2.0, a=6.0)
    assert sonder_video(r.chemin).n_images == len(plan) == r.n_images


def test_flamme_visible(exemple: Path) -> None:
    from dataclasses import replace

    from cfd_trajcast.data.configuration import ConfigMontage, charger_configuration

    cfg = charger_configuration(exemple / "SCENARIOS" / "FUSEE_BI_ETAGE.yaml")
    cfg = replace(cfg, video=replace(cfg.video, resolution=(640, 360), preset="ultrafast"),
                  montage=ConfigMontage(titre_debut=0, generique_fin=0, bandeaux_evenements=False,
                                        etiquettes_vues=False),
                  disposition=replace(cfg.disposition, type="unique", incrustations=(), telemetrie="aucune"))
    avec = Film.depuis_configuration(cfg)
    sans = Film.depuis_configuration(replace(cfg, propulsion=None))
    change = lambda t: int(np.count_nonzero(  # noqa: E731
        np.abs(avec.image(t).astype(int) - sans.image(t).astype(int)).max(axis=2) > 40))
    assert change(1.5) > 300 and change(8.0) > 100   # étage 1 (flamme + panache), étage 2
    assert change(25.0) < 10                          # propulsion éteinte, fumées dissipées
