"""Vue d'ensemble seule : schéma SVG (sans rendu), ``VueEnsemble`` (SVG, vidéo), commande ``ensemble``.

Le schéma n'a pas de moteur 3D : il projette lui-même. La garantie qu'il montre la
même chose que la vidéo est double — il partage la caméra (``cadre_ensemble``) et la
boîte graduée (``boite_ensemble``) avec le moteur PyVista, et sa projection
(``projeter``) est comparée ici à celle de VTK, point par point.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from conftest import dataframe_enu_quaternion

from cfd_trajcast.cli.main import EXIT_ERREUR_ENTREE, EXIT_OK, _poses, main
from cfd_trajcast.core.camera import (
    ParametresEnsemble,
    boite_ensemble,
    cadre_ensemble,
    projeter,
    vers_ned,
)
from cfd_trajcast.data.configuration import ConfigVideo, Logo
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import Evenement, Trajectoire
from cfd_trajcast.engine.ensemble import NOM_VUE, VueEnsemble
from cfd_trajcast.engine.schema_ensemble import schema_ensemble, simplifier

SVG = "{http://www.w3.org/2000/svg}"


@pytest.fixture
def maquette(exemple: Path) -> Maquette:
    return Maquette.depuis_fichier(exemple / "MAQUETTE" / "Aim9.stl", unite="mm", axe_nez="-X",
                                   axe_haut="+Z", origine=(19.05, 0, 0), longueur_imposee=2.87)


@pytest.fixture
def traj() -> Trajectoire:
    return Trajectoire.depuis_dataframe(
        dataframe_enu_quaternion(), repere="ENU", attitude="quaternion",
        evenements=[Evenement(3.744, "Mach 1"), Evenement(4.0, "Fin de propulsion"), Evenement(40.565, "Apogée")],
    )


def _dimensions(svg: str) -> tuple[float, float]:
    racine = ET.fromstring(svg.split("?>", 1)[1])
    _, _, l_, h = (float(v) for v in racine.attrib["viewBox"].split())
    return l_, h


# -- géométrie partagée ------------------------------------------------------------------
def test_boite_contient_le_vol_et_le_sol(traj: Trajectoire) -> None:
    b = boite_ensemble(traj.positions, sol_altitude=-50.0)
    ned = vers_ned(traj.positions)
    assert np.all(b.bas <= ned.min(axis=0)) and np.all(b.haut >= ned.max(axis=0))
    assert b.sol == 50.0 and b.haut[2] >= 50.0
    for axe in range(3):
        g = b.graduations(axe)
        assert g[0] == b.bas[axe] and g[-1] == pytest.approx(b.haut[axe])
        np.testing.assert_allclose(g / b.pas, np.round(g / b.pas), atol=1e-9)


def test_projection_centre_et_sens() -> None:
    xy, prof = projeter([[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
                        position=(-10.0, 0.0, 0.0), vise=(0.0, 0.0, 0.0), haut=(0.0, 0.0, 1.0),
                        champ=60.0, largeur=400, hauteur=200)
    np.testing.assert_allclose(xy[0], [200, 100])
    np.testing.assert_allclose(prof, 10.0)
    assert xy[1, 0] < 200  # y+ est à gauche quand on regarde vers +x, haut +z
    assert xy[2, 1] < 100  # le haut de la scène est en haut de l'image (y pixel vers le bas)


@pytest.mark.usefixtures("rendu")
def test_projection_egale_vtk(traj: Trajectoire) -> None:
    """Même caméra, mêmes points : la projection NumPy tombe sur celle de VTK à 0,01 px près."""
    import pyvista as pv

    largeur, hauteur = 640, 360
    params = ParametresEnsemble(azimut=35.0, elevation=25.0)
    b = boite_ensemble(traj.positions)
    position, vise, haut = cadre_ensemble(traj.positions, params, largeur / hauteur, (b.bas, b.haut))
    p = pv.Plotter(off_screen=True, window_size=(largeur, hauteur))
    try:
        p.add_mesh(pv.Sphere())
        c = p.camera
        c.position, c.focal_point, c.up = tuple(position), tuple(vise), tuple(haut)
        c.view_angle = params.champ
        p.render()
        points = vers_ned(traj.positions[::200])
        ren = p.renderer
        vtk_xy = []
        for pt in points:
            ren.SetWorldPoint(*pt, 1.0)
            ren.WorldToDisplay()
            x, y, _ = ren.GetDisplayPoint()
            vtk_xy.append((x, hauteur - y))
    finally:
        p.close()
    xy, _ = projeter(points, position, vise, haut, params.champ, largeur, hauteur)
    np.testing.assert_allclose(xy, np.array(vtk_xy), atol=0.01)


# -- schéma SVG ----------------------------------------------------------------------------
def test_schema_svg_valide(traj: Trajectoire, maquette: Maquette, tmp_path: Path) -> None:
    s = schema_ensemble(traj, maquette, titre="Vol <test> & co", sous_titre="sous-titre")
    racine = ET.fromstring(s.svg.split("?>", 1)[1])  # XML bien formé, texte échappé
    textes = [t.text for t in racine.iter(f"{SVG}text")]
    assert "Vol <test> & co" in textes and "Nord (m)" in textes and "Bas (m)" in textes
    assert any(t and t.startswith("Apogée · 40,6") for t in textes)
    assert len(list(racine.iter(f"{SVG}circle"))) == 3  # un point par événement
    assert len(list(racine.iter(f"{SVG}polyline"))) == 2  # le vol et sa trace au sol
    assert (s.largeur, s.hauteur) == tuple(round(v) for v in _dimensions(s.svg))
    # Poses par défaut : aux événements, sauf la fin de propulsion, à 0,26 s de Mach 1 (même endroit).
    assert s.poses == (3.744, 40.565)
    assert s.echelle > 100 and s.faces == len(maquette.faces)
    sortie = s.ecrire(tmp_path / "sous" / "e.svg")
    assert sortie.chemin is not None and sortie.chemin.read_text(encoding="utf-8") == s.svg


def test_schema_poses(traj: Trajectoire, maquette: Maquette) -> None:
    sans = schema_ensemble(traj, maquette, poses=0)
    assert sans.poses == () and "<path" not in sans.svg
    choisies = schema_ensemble(traj, maquette, poses=[10.0, "Fin de propulsion"])
    assert choisies.poses == (10.0, 4.0)  # demandées explicitement : gardées même rapprochées
    assert "10,0" in choisies.svg  # une pose hors événement porte son instant
    assert len(schema_ensemble(traj, maquette, poses=4).poses) == 4
    triangles = choisies.svg.count("<path")
    assert 0 < triangles <= 2 * len(maquette.faces)
    with pytest.raises(ValueError, match="inconnu"):
        schema_ensemble(traj, maquette, poses=["Parachute"])
    with pytest.raises(ValueError, match="hors du vol"):
        schema_ensemble(traj, maquette, poses=[1e4])
    with pytest.raises(ValueError, match="theme"):
        schema_ensemble(traj, maquette, theme="rose")


def test_schema_proportions_vraies(traj: Trajectoire, maquette: Maquette) -> None:
    """Le cadre suit le vol : haut pour un vol presque vertical, large pour un vol à plat."""
    l_, h = _dimensions(schema_ensemble(traj, maquette, taille=800).svg)
    assert h > 1.8 * l_
    t = np.linspace(0, 60, 601)
    plat = pd.DataFrame({"t": t, "x": 200.0 * t, "y": 20.0 * t, "z": 1000 + 5 * t,
                         "qw": 1.0, "qx": 0.0, "qy": 0.0, "qz": 0.0})
    vol_plat = Trajectoire.depuis_dataframe(plat, repere="ENU", attitude="quaternion")
    l_, h = _dimensions(schema_ensemble(vol_plat, maquette, taille=800).svg)
    assert l_ > 1.3 * h


def test_schema_theme_sombre(traj: Trajectoire, maquette: Maquette) -> None:
    s = schema_ensemble(traj, maquette, theme="sombre", poses=0)
    assert 'fill="#0b1220"' in s.svg


def test_simplifier_garde_la_forme(maquette: Maquette) -> None:
    sommets, faces = simplifier(maquette.sommets, maquette.faces, maquette.taille / 60)
    assert 0 < len(faces) < len(maquette.faces)
    np.testing.assert_allclose(sommets.min(axis=0), maquette.sommets.min(axis=0), atol=maquette.taille / 60)
    np.testing.assert_allclose(sommets.max(axis=0), maquette.sommets.max(axis=0), atol=maquette.taille / 60)
    assert faces.max() < len(sommets)


# -- VueEnsemble ---------------------------------------------------------------------------
def test_vue_depuis_yaml(exemple: Path) -> None:
    vue = VueEnsemble.depuis_yaml(exemple / "CONFIG_ENSEMBLE.yaml")
    assert vue.parametres == ParametresEnsemble(elevation=20.0, cadrage=0.85)
    assert vue.etude.titre.startswith("Vol de référence")
    # Une configuration sans vue d'ensemble convient aussi : réglages par défaut.
    assert VueEnsemble.depuis_yaml(exemple / "CONFIG.yaml").parametres == ParametresEnsemble()
    with pytest.raises(ValueError, match="poursuite"):
        VueEnsemble.depuis_yaml(exemple / "CONFIG_ENSEMBLE.yaml", vue="poursuite")


def test_film_a_une_vue(exemple: Path) -> None:
    vue = VueEnsemble.depuis_yaml(exemple / "CONFIG_ENSEMBLE.yaml")
    film = vue.film()
    assert [nom for nom, _ in film.vues] == [NOM_VUE]
    assert film.disposition.type == "unique" and film.disposition.telemetrie == "droite"
    assert film.de is None and film.a is None  # tout le vol
    assert not film.montage.etiquettes_vues
    # Le logo, prévu au-dessus du panneau de la disposition libre, ne recouvre pas la bande.
    assert film.montage.logo is not None and film.montage.logo.coin == "haut_gauche"
    assert film.montage.coin_bandeaux == "bas_gauche"
    sans = vue.film(telemetrie=False, resolution=(1080, 1920), duree=20.0)
    assert sans.disposition.telemetrie == "aucune" and sans.telemetrie is None
    assert sans.montage.logo is not None and sans.montage.logo.coin == "haut_droite"
    assert sans.video.resolution == (1080, 1920) and sans.video.duree == 20.0
    # Sans télémétrie configurée, `telemetrie=True` prend le panneau par défaut.
    assert VueEnsemble.depuis_yaml(exemple / "CONFIG.yaml").film(telemetrie=True).telemetrie is not None


def test_logo_a_gauche_reste(exemple: Path) -> None:
    from dataclasses import replace

    vue = VueEnsemble.depuis_yaml(exemple / "CONFIG_ENSEMBLE.yaml")
    vue.montage = replace(vue.montage, logo=Logo(exemple / "logo.png", coin="bas_gauche"))
    assert vue.film().montage.logo == vue.montage.logo


@pytest.mark.usefixtures("rendu")
def test_vue_rendre_mp4(tmp_path: Path, exemple: Path) -> None:
    from cfd_trajcast.engine.encodage import sonder_video

    vue = VueEnsemble.depuis_yaml(exemple / "CONFIG_ENSEMBLE.yaml")
    vue.video = ConfigVideo(resolution=(320, 180), ips=10, preset="ultrafast")
    r = vue.rendre(tmp_path / "e.mp4", duree=2.0, processus=1)
    info = sonder_video(r.chemin)
    assert (info.largeur, info.hauteur, info.n_images) == (320, 180, 20)
    assert r.t_vol[0] == 0.0 and r.t_vol[1] == pytest.approx(vue.trajectoire.t[-1], abs=3.0)
    img = vue.image(30.0, tmp_path / "e.png", telemetrie=False)
    assert img.shape == (180, 320, 3) and (tmp_path / "e.png").is_file()


# -- ligne de commande ---------------------------------------------------------------------
def test_poses_cli() -> None:
    assert _poses("5") == 5
    assert _poses("12.5,Apogée") == [12.5, "Apogée"]
    assert _poses("12") == 12 and _poses("12.") == [12.0]


def test_cli_ensemble_svg(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["exemple", str(tmp_path / "ex")])
    cfg = tmp_path / "ex" / "CONFIG_ENSEMBLE.yaml"
    assert main(["ensemble", str(cfg), "--schema", "--poses", "Apogée,20", "--taille", "600"]) == EXIT_OK
    svg = (tmp_path / "ex" / "CONFIG_ENSEMBLE_ensemble.svg").read_text(encoding="utf-8")
    assert re.search(r'viewBox="[^"]+"', svg)
    assert "40.6 s, 20.0 s" in capsys.readouterr().out
    assert not (tmp_path / "ex" / "CONFIG_ENSEMBLE_ensemble.mp4").exists()  # pas de vidéo sans --video
    assert main(["ensemble", str(cfg), "--poses", "Parachute"]) == EXIT_ERREUR_ENTREE
    assert main(["ensemble", str(cfg), "--vue", "sol"]) == EXIT_ERREUR_ENTREE
