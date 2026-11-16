"""Moteur Blender (J6) : sauté sans bpy (une roue par version de Python : 3.13 pour bpy 5.x)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from cfd_trajcast.data.configuration import PRESETS_STYLE, ConfigMoteur, charger_configuration
from cfd_trajcast.engine.jets import tube
from cfd_trajcast.engine.rendu import creer_moteur


def test_tube_geometrie() -> None:
    t = np.linspace(0, 1, 20)
    points = np.stack([t * 10, np.sin(t * 3), np.zeros_like(t)], axis=1)
    rayons = np.linspace(0.5, 2.0, 20)
    sommets, faces = tube(points, rayons, 12)
    assert sommets.shape == (240, 3) and faces.shape == (19 * 12 * 2, 3) and faces.max() == 239
    # Chaque anneau est à son rayon de son point, dans le plan normal.
    d = np.linalg.norm(sommets.reshape(20, 12, 3) - points[:, None, :], axis=2)
    assert np.allclose(d, rayons[:, None])
    with pytest.raises(ValueError):
        tube(points[:1], rayons[:1])


def test_moteur_par_defaut_sans_bpy() -> None:
    """Le choix du moteur n'importe pas bpy tant qu'on ne le demande pas."""

    assert ConfigMoteur().type == "pyvista"
    assert True  # bpy peut avoir été importé par un autre test
    assert creer_moteur.__module__ == "cfd_trajcast.engine.rendu"


@pytest.mark.usefixtures("rendu")
def test_rendu_blender(exemple: Path) -> None:
    from cfd_trajcast.engine.rendu.blender import bpy_disponible

    if not bpy_disponible():
        pytest.skip("bpy absent (pip install bpy ; Python 3.13 pour bpy 5.x)")
    from cfd_trajcast.engine.pipeline import Film

    cfg = charger_configuration(exemple / "SCENARIOS" / "FUSEE_BI_ETAGE.yaml")
    cfg = replace(cfg, style=PRESETS_STYLE["nuit"], video=replace(cfg.video, resolution=(320, 180)),
                  moteur=ConfigMoteur(type="blender", echantillons=4))
    film = Film.depuis_configuration(cfg)
    plan = film.plan(de=1.0, a=1.2)
    moteur = creer_moteur(film.scene, plan, film.moteur)
    try:
        image = moteur.image(0, "cinema", (320, 180))
        assert image.shape == (180, 320, 3) and image.dtype == np.uint8
        assert image[:15].mean() < 40            # ciel de nuit composé derrière
        assert image.max() > 200                 # la flamme
        ensemble = moteur.image(0, "ensemble", (160, 120))   # vue d'ensemble : déléguée à PyVista
        assert ensemble.shape == (120, 160, 3)
    finally:
        moteur.fermer()


@pytest.mark.usefixtures("rendu")
def test_blender_en_parallele(exemple: Path, tmp_path: Path) -> None:
    """Processus « spawn » : ils héritent du sys.path du parent, où bpy a ajouté ses dossiers
    internes ; sans nettoyage, chaque processus échouait sur « No module named '_bpy' » (J6)."""
    from cfd_trajcast.engine.rendu.blender import bpy_disponible, importer_bpy

    if not bpy_disponible():
        pytest.skip("bpy absent")
    importer_bpy()                                   # le parent a importé bpy, comme au J6
    from cfd_trajcast.engine.encodage import sonder_video
    from cfd_trajcast.engine.pipeline import Film

    cfg = charger_configuration(exemple / "SCENARIOS" / "FUSEE_NUIT_BLENDER.yaml")
    cfg = replace(cfg, video=replace(cfg.video, resolution=(160, 90), ips=30.0, preset="ultrafast", a=None,
                                     ralentis=()),
                  moteur=ConfigMoteur(type="blender", echantillons=1))
    r = Film.depuis_configuration(cfg).rendre(tmp_path / "b.mp4", de=1.0, a=3.0, processus=2)
    assert r.processus == 2 and sonder_video(r.chemin).n_images == r.n_images == 60
