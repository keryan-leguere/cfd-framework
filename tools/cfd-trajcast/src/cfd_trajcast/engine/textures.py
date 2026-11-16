"""Textures procédurales du sol, en NumPy pur — **raccordables** (périodiques).

Le sol est un grand plan sur lequel une tuile se répète ; une tuile non
périodique montrerait ses coutures. Le bruit est donc fabriqué dans le domaine
de Fourier (filtre passe-bas d'un bruit blanc) : périodique par construction.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

__all__ = ["bruit_periodique", "teinte", "texture_damier", "texture_terrain"]


def teinte(hexa: str) -> NDArray[np.float64]:
    """``"#rrggbb"`` → (r, g, b) dans [0 ; 1]."""
    h = hexa.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], dtype=float) / 255


def bruit_periodique(taille: int, echelle: float, graine: int) -> NDArray[np.float64]:
    """Bruit lisse périodique dans [0 ; 1] ; ``echelle`` = taille des taches en fraction de tuile."""
    rng = np.random.default_rng(graine)
    blanc = rng.standard_normal((taille, taille))
    f = np.fft.fftfreq(taille)
    rayon2 = f[:, None] ** 2 + f[None, :] ** 2
    # Gaussienne d'écart-type spatial σ = echelle × taille pixels ↔ exp(−2π²σ²f²) en fréquence.
    sigma = echelle * taille
    filtre = np.exp(-2 * np.pi**2 * sigma**2 * rayon2)
    lisse = np.real(np.fft.ifft2(np.fft.fft2(blanc) * filtre))
    lisse -= lisse.min()
    return np.asarray(lisse / max(float(lisse.max()), 1e-12))


@lru_cache(maxsize=8)
def texture_terrain(couleur: str, taille: int = 1024, graine: int = 7) -> NDArray[np.uint8]:
    """Champs et sols nus : trois octaves de bruit autour de ``couleur``.

    Gardée en cache (une par couleur) et rendue en lecture seule : chaque vue et chaque
    taille d'image la redemandent. 1024 px : une tuile de plusieurs kilomètres (préréglage
    ``nuit``, contre la répétition visible vue d'en haut) reste détaillée au sol.
    """
    base = teinte(couleur)
    terre = np.array([0.55, 0.45, 0.32])
    grand = bruit_periodique(taille, 0.18, graine)
    moyen = bruit_periodique(taille, 0.05, graine + 1)
    fin = bruit_periodique(taille, 0.012, graine + 2)
    melange = np.clip((grand - 0.45) * 2.5, 0, 1)[..., None]       # parcelles de terre
    couleur_px = base * (1 - 0.45 * melange) + terre * 0.45 * melange
    lumiere = (0.82 + 0.22 * moyen + 0.10 * fin)[..., None]
    image = np.asarray(np.clip(couleur_px * lumiere, 0, 1) * 255, dtype=np.uint8)
    image.flags.writeable = False
    return image


def texture_damier(couleur: str, taille: int = 256) -> NDArray[np.uint8]:
    """Damier 2 × 2 : deux nuances de ``couleur``."""
    base = teinte(couleur)
    i = np.arange(taille) * 2 // taille
    cases = (i[:, None] + i[None, :]) % 2
    px = np.where(cases[..., None] == 0, base * 0.9, np.clip(base * 1.1, 0, 1))
    return np.asarray(px * 255, dtype=np.uint8)
