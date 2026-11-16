"""Textures procédurales du sol : raccordables, au bon format."""

from __future__ import annotations

import numpy as np

from cfd_trajcast.engine.textures import bruit_periodique, texture_damier, texture_terrain


def test_bruit_raccordable() -> None:
    b = bruit_periodique(128, 0.05, 1)
    assert b.min() == 0 and b.max() == 1
    # Le saut à la couture (dernière → première colonne) est de l'ordre d'un pas intérieur.
    interieur = np.abs(np.diff(b, axis=1)).mean()
    couture = np.abs(b[:, 0] - b[:, -1]).mean()
    assert couture < 2 * interieur


def test_textures() -> None:
    t = texture_terrain("#5d7a3e", taille=64)
    assert t.shape == (64, 64, 3) and t.dtype == np.uint8 and t.std() > 2
    d = texture_damier("#808080", taille=8)
    assert d.shape == (8, 8, 3) and d[0, 0, 0] != d[0, 7, 0]
