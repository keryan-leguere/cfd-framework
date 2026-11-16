"""Rendu parallèle par tronçons, bornes video.de/a, export CSV : J5."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from cfd_trajcast.cli.main import EXIT_OK, main
from cfd_trajcast.data.configuration import charger_configuration
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.engine import pipeline
from cfd_trajcast.engine.encodage import concatener, lire_images, sonder_video
from cfd_trajcast.engine.pipeline import Film


def _film(exemple: Path, **video: object) -> Film:
    cfg = charger_configuration(exemple / "CONFIG_MULTIVUES.yaml")
    cfg = replace(cfg, video=replace(cfg.video, resolution=(192, 108), preset="ultrafast", **video))
    return Film.depuis_configuration(cfg)


def test_decoupage() -> None:
    troncons = pipeline._decouper(1000, 4)
    assert troncons[0][0] == 0 and troncons[-1][1] == 1000
    assert all(b == c for (_, b), (c, _) in zip(troncons, troncons[1:]))
    assert all(b - a >= 1 for a, b in troncons) and len(troncons) == 16
    assert pipeline._decouper(50, 8) == [(0, 30), (30, 50)]  # jamais moins de TRONCON_MIN


def test_processus_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    beaucoup = 64e9
    monkeypatch.setattr(pipeline.os, "cpu_count", lambda: 8)
    assert pipeline.processus_auto(10_000, memoire=beaucoup) == 6
    assert pipeline.processus_auto(40, memoire=beaucoup) == 1
    monkeypatch.setattr(pipeline.os, "cpu_count", lambda: 2)
    assert pipeline.processus_auto(10_000, memoire=beaucoup) == 1


def test_processus_auto_borne_par_la_memoire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le contrôle J6 a été tué par le noyau (manque de mémoire) avec 6 processus 4K."""
    monkeypatch.setattr(pipeline.os, "cpu_count", lambda: 8)
    libre = 5.8e9                                   # ce que la machine avait de libre au J6
    assert pipeline.processus_auto(10_000, (3840, 2160), memoire=libre) == 2
    assert pipeline.processus_auto(10_000, (1920, 1080), memoire=libre) == 5
    assert pipeline.processus_auto(10_000, (3840, 2160), memoire=1e9) == 1   # jamais zéro
    assert pipeline.memoire_disponible() is None or pipeline.memoire_disponible() > 0


@pytest.mark.usefixtures("rendu")
def test_parallele_egal_serie(exemple: Path, tmp_path: Path) -> None:
    film = _film(exemple)
    serie = film.rendre(tmp_path / "s.mp4", de=1.0, a=4.0, processus=1)
    para = film.rendre(tmp_path / "p.mp4", de=1.0, a=4.0, processus=2)
    assert para.processus == 2 and para.troncons >= 2 and serie.processus == 1
    a, b = sonder_video(tmp_path / "s.mp4"), sonder_video(tmp_path / "p.mp4")
    assert a.n_images == b.n_images == serie.n_images == para.n_images
    assert (b.largeur, b.hauteur, b.codec, b.format_pixels) == (192, 108, "h264", "yuv420p")
    ecarts = [np.abs(x.astype(np.int16) - y.astype(np.int16)).mean()
              for x, y in zip(lire_images(tmp_path / "s.mp4"), lire_images(tmp_path / "p.mp4"))]
    assert len(ecarts) == a.n_images and max(ecarts) < 3.0  # mêmes images, aux arrondis de compression près
    assert not list(tmp_path.glob(".*troncons*"))  # tronçons nettoyés


@pytest.mark.usefixtures("rendu")
def test_concatener(tmp_path: Path) -> None:
    from cfd_trajcast.engine.encodage import Encodeur

    morceaux = []
    for i, n in enumerate((5, 7)):
        p = tmp_path / f"m'{i}.mp4"  # apostrophe : échappement du démultiplexeur
        with Encodeur(p, 32, 32, 10, preset="ultrafast") as e:
            for _ in range(n):
                e.ajouter(np.full((32, 32, 3), 40 * i, dtype=np.uint8))
        morceaux.append(p)
    info = sonder_video(concatener(morceaux, tmp_path / "tout.mp4"))
    assert info.n_images == 12


def test_bornes_video_par_evenement(exemple: Path) -> None:
    film = _film(exemple, de="Fin de propulsion", a=20.0)
    assert film.de == pytest.approx(4.0) and film.a == 20.0
    plan = film.plan()
    assert plan.t_vol[0] == pytest.approx(4.0) and plan.t_vol[-1] == pytest.approx(20.0, abs=0.1)
    with pytest.raises(ValueError, match="inconnu"):
        _film(exemple, de="Pas un événement")


def test_cle_video_de_a(exemple: Path, tmp_path: Path) -> None:
    texte = (exemple / "CONFIG.yaml").read_text(encoding="utf-8")
    p = tmp_path / "C.yaml"
    p.write_text(texte.replace("video:\n", "video:\n  de: \"Apogée\"\n  a: 45\n", 1)
                 .replace("vol_reference.csv", str(exemple / "vol_reference.csv"))
                 .replace("MAQUETTE/", str(exemple / "MAQUETTE") + "/"), encoding="utf-8")
    cfg = charger_configuration(p)
    assert (cfg.video.de, cfg.video.a) == ("Apogée", 45.0)


def test_exporter_relu_a_l_identique(exemple: Path, tmp_path: Path) -> None:
    main(["exemple", str(tmp_path / "ex")])
    cfg = tmp_path / "ex" / "CONFIG_EULER.yaml"  # NED + Euler : l'export doit tout ramener en ENU
    assert main(["exporter", str(cfg), "--sortie", str(tmp_path / "vol.csv")]) == EXIT_OK
    origine = charger_configuration(cfg).trajectoire.charger()
    relu = Trajectoire.depuis_csv(tmp_path / "vol.csv", repere="ENU",
                                  attitude={"type": "quaternion", "colonnes": ["qw", "qx", "qy", "qz"]})
    assert np.allclose(relu.positions, origine.positions, atol=1e-6)
    assert np.allclose(relu.attitude, origine.attitude, atol=1e-8)
    if origine.evenements:
        assert (tmp_path / "vol_evenements.csv").is_file()
