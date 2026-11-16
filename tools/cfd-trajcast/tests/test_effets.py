"""Effets d'image (J6) : ciel composé, étoiles projetées, lueur ; préréglage nuit."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cfd_trajcast.data.configuration import (
    PRESETS_STYLE,
    ErreurConfiguration,
    charger_configuration,
)
from cfd_trajcast.engine.effets import Ciel, composer_ciel, degrade_ciel, etoiles, lueur, projeter

L, H = 320, 180


def test_projection_centre_et_derriere() -> None:
    cam = (np.zeros(3), np.array([0.0, 1.0, 0.0]), np.array([0.0, 0.0, 1.0]), 60.0)
    d = np.array([[0.0, 1.0, 0.0], [0.0, -1.0, 0.0], [0.0, 1.0, np.tan(np.radians(30.0))]])
    px, py, vis = projeter(d, *cam, (L, H))
    assert vis[0] and px[0] == pytest.approx(L / 2) and py[0] == pytest.approx(H / 2)
    assert not vis[1]                       # derrière la caméra
    assert py[2] == pytest.approx(0.0, abs=1e-6)  # au bord haut : demi-champ vertical = 30°
    # Vers l'est (x) : à droite de l'image quand on regarde le nord.
    px2, _, _ = projeter(np.array([[0.3, 1.0, 0.0]]), *cam, (L, H))
    assert px2[0] > L / 2


def test_catalogue_deterministe() -> None:
    a, b = etoiles(), etoiles()
    assert a is b and np.allclose(np.linalg.norm(a.directions, axis=1), 1.0)
    assert a.directions[:, 2].min() >= -0.05 and 0 < a.eclat.min() and a.eclat.max() <= 1


def test_ciel_derriere_la_scene() -> None:
    rgba = np.zeros((H, L, 4), np.uint8)
    rgba[60:120, 100:200] = (200, 50, 50, 255)           # objet opaque
    rgba[10:20, 10:20] = (50, 50, 50, 128)                # translucide, prémultiplié
    image = composer_ciel(rgba, Ciel("#000040", "#4060a0"))
    assert np.array_equal(image[90, 150], [200, 50, 50])  # l'opaque n'est pas touché
    fond = degrade_ciel("#000040", "#4060a0", (L, H))
    assert np.allclose(image[150, 10], fond[150, 10] * 255, atol=1)
    assert image[0, 300, 2] < image[179, 300, 2]          # dégradé du haut vers le bas
    m = image[15, 15].astype(float)
    assert np.allclose(m, 50 + (1 - 128 / 255) * fond[15, 15] * 255, atol=1.5)


def test_etoiles_suivent_la_camera() -> None:
    rgba = np.zeros((H, L, 4), np.uint8)
    ciel = Ciel("#000000", "#000000", etoiles=1.0)
    haut = (np.zeros(3), np.array([0.0, 0.3, 1.0]), np.array([0.0, 1.0, 0.0]), 60.0)
    a = composer_ciel(rgba, ciel, camera=haut)
    assert (a.max(axis=2) > 40).sum() > 10              # des étoiles en regardant le ciel
    tourne = (np.zeros(3), np.array([0.3, 0.3, 1.0]), np.array([0.0, 1.0, 0.0]), 60.0)
    assert not np.array_equal(a, composer_ciel(rgba, ciel, camera=tourne))
    sol = (np.zeros(3), np.array([0.0, 0.1, -1.0]), np.array([0.0, 1.0, 0.0]), 40.0)
    assert composer_ciel(rgba, ciel, camera=sol).max() < 10  # pas d'étoiles sous l'horizon
    rgba[:] = 255                                          # scène opaque partout : rien derrière
    assert np.array_equal(composer_ciel(rgba, ciel, camera=haut), rgba[..., :3])


def test_lueur() -> None:
    image = np.full((H, L, 3), 10, np.uint8)
    image[85:95, 155:165] = 255
    halo = lueur(image, 1.0)
    assert halo[90, 140].mean() > image[90, 140].mean() + 5   # le halo déborde
    assert halo[5, 5].mean() == pytest.approx(10, abs=1)      # loin, rien
    assert np.array_equal(lueur(image, 0.0), image)
    sombre = np.full((H, L, 3), 60, np.uint8)
    assert np.array_equal(lueur(sombre, 1.0), sombre)         # sous le seuil : rien


def test_preset_nuit_et_cles(tmp_path: Path, exemple: Path) -> None:
    nuit = PRESETS_STYLE["nuit"]
    assert nuit.ciel_etoiles > 0 and nuit.lueur > 0 and nuit.lumiere_jets > 0
    assert nuit.ensemble_theme == "sombre"
    texte = (exemple / "CONFIG.yaml").read_text(encoding="utf-8")
    texte = texte.replace("vol_reference.csv", str(exemple / "vol_reference.csv")).replace(
        "MAQUETTE/", str(exemple / "MAQUETTE") + "/")
    p = tmp_path / "C.yaml"
    p.write_text(texte + "\nstyle:\n  preset: nuit\n  ciel: { etoiles: 0.5 }\n  lueur: 0.3\n"
                 "  eclairage: { couleur: \"#ffeedd\", jets: 1.0 }\n  ensemble: clair\n"
                 "moteur: { type: blender, rendu: cycles, echantillons: 64 }\n", encoding="utf-8")
    cfg = charger_configuration(p)
    s = cfg.style
    assert (s.preset, s.ciel_etoiles, s.lueur, s.lumiere_couleur, s.lumiere_jets, s.ensemble_theme) == (
        "nuit", 0.5, 0.3, "#ffeedd", 1.0, "clair")
    assert (cfg.moteur.type, cfg.moteur.rendu, cfg.moteur.echantillons) == ("blender", "cycles", 64)
    p.write_text(texte + "\nmoteur: { type: povray }\n", encoding="utf-8")
    with pytest.raises(ErreurConfiguration, match=r"moteur\.type"):
        charger_configuration(p)


@pytest.mark.usefixtures("rendu")
def test_rendu_nuit(exemple: Path) -> None:
    """Préréglage nuit de bout en bout : ciel sombre étoilé, flamme lumineuse avec halo."""
    from dataclasses import replace

    from cfd_trajcast.engine.pipeline import Film

    cfg = charger_configuration(exemple / "SCENARIOS" / "FUSEE_BI_ETAGE.yaml")
    cfg = replace(cfg, style=PRESETS_STYLE["nuit"],
                  video=replace(cfg.video, resolution=(480, 270)))
    film = Film.depuis_configuration(cfg)
    image = film.image(2.0)
    assert image[:20].mean() < 40                   # ciel de nuit
    assert image.max() == 255                        # la flamme brille
