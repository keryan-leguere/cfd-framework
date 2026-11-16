"""MP4 : dimensions exactes (pas de 1080 → 1088), nombre d'images, codec."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cfd_trajcast.engine.encodage import Encodeur, ecrire_png, sonder_video


def _images(n: int, largeur: int, hauteur: int) -> list[np.ndarray]:
    rng = np.random.default_rng(0)
    return [rng.integers(0, 255, (hauteur, largeur, 3), dtype=np.uint8) for _ in range(n)]


def test_dimensions_non_multiples_de_16(tmp_path: Path) -> None:
    chemin = tmp_path / "v.mp4"
    with Encodeur(chemin, 96, 54, 12, preset="ultrafast") as e:
        for image in _images(12, 96, 54):
            e.ajouter(image)
    info = sonder_video(chemin)
    assert (info.largeur, info.hauteur) == (96, 54)
    assert info.n_images == 12 and info.ips == pytest.approx(12)
    assert info.codec == "h264" and info.format_pixels == "yuv420p"


def test_dimensions_impaires_refusees(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="paires"):
        Encodeur(tmp_path / "v.mp4", 95, 54, 12)


def test_image_de_mauvaise_forme(tmp_path: Path) -> None:
    with Encodeur(tmp_path / "v.mp4", 64, 48, 12, preset="ultrafast") as e:
        e.ajouter(_images(1, 64, 48)[0])
        with pytest.raises(ValueError, match="attendu"):
            e.ajouter(_images(1, 48, 64)[0])


def test_png(tmp_path: Path) -> None:
    from PIL import Image

    p = ecrire_png(_images(1, 20, 10)[0], tmp_path / "a" / "i.png")
    assert Image.open(p).size == (20, 10)
