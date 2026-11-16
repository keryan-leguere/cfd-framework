"""Effets d'image, indépendants du moteur 3D : ciel composé, étoiles, lueur.

**Ciel composé.** Le moteur rend la scène sur un fond **transparent** (couche
alpha = couverture, couleurs prémultipliées comme le fait OpenGL). Le ciel est
ensuite peint ici, derrière : ``image = rgb + (1 − α)·ciel``. C'est la seule façon
propre de mettre des étoiles *derrière* la fumée et le sol, sans lire le tampon de
profondeur (126 ms en 4K, mesuré) — et c'est la même chose pour PyVista et Blender.

**Étoiles.** Des directions fixes dans le repère ENU, projetées avec la caméra de
l'image : elles tournent avec le regard, comme un vrai ciel. Éclat en loi de
puissance (beaucoup de faibles, quelques brillantes), teinte de bleuté à orangé,
scintillement lent, rien sous l'horizon.

**Lueur** (*bloom*). Ce qui dépasse un seuil de luminance — les flammes, la nuit
— est flouté et rajouté : le halo autour d'une source intense. Calculée au quart
de la résolution (le flou cache la perte), donc peu coûteuse même en 4K.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.engine.textures import teinte

__all__ = ["Ciel", "Etoiles", "composer_ciel", "degrade_ciel", "etoiles", "lueur", "projeter"]

Tableau = NDArray[np.float64]
Image = NDArray[np.uint8]


@dataclass(frozen=True, eq=False)
class Etoiles:
    """Un catalogue d'étoiles : directions unitaires ENU, éclat ∈ ]0 ; 1], couleur RGB ∈ [0 ; 1]."""

    directions: Tableau
    eclat: Tableau
    couleurs: Tableau
    phases: Tableau


@lru_cache(maxsize=4)
def etoiles(n: int = 6000, graine: int = 11) -> Etoiles:
    """Catalogue déterministe : uniformes sur l'hémisphère supérieur (et un peu sous l'horizon)."""
    rng = np.random.default_rng(graine)
    z = rng.uniform(-0.05, 1.0, n)
    phi = rng.uniform(0, 2 * np.pi, n)
    r = np.sqrt(1 - z**2)
    directions = np.stack([r * np.cos(phi), r * np.sin(phi), z], axis=1)
    # Loi de puissance : l'éclat d'une étoile sur dix dépasse 0,5.
    eclat = np.clip(rng.pareto(2.2, n) * 0.25 + 0.12, 0, 1)
    chaud = rng.uniform(0, 1, n)[:, None]
    couleurs = (1 - chaud) * np.array([0.78, 0.86, 1.0]) + chaud * np.array([1.0, 0.9, 0.75])
    return Etoiles(directions, eclat, couleurs, rng.uniform(0, 2 * np.pi, n))


def projeter(directions: Tableau, position: Tableau, visee: Tableau, haut: Tableau, champ: float,
             taille: tuple[int, int]) -> tuple[Tableau, Tableau, NDArray[np.bool_]]:
    """Directions à l'infini → pixels ``(x, y)`` ; ``champ`` = angle de vue **vertical** (°).

    Convention de VTK et de Blender (capteur ajusté en hauteur). Les points derrière la
    caméra ou hors cadre sont marqués invisibles.
    """
    largeur, hauteur = taille
    f = np.asarray(visee, dtype=float) - np.asarray(position, dtype=float)
    f /= np.linalg.norm(f)
    droite = np.cross(f, np.asarray(haut, dtype=float))
    droite /= np.linalg.norm(droite)
    vrai_haut = np.cross(droite, f)
    xc, yc, zc = directions @ droite, directions @ vrai_haut, directions @ f
    devant = zc > 1e-6
    echelle = (hauteur / 2) / np.tan(np.radians(champ) / 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        px = largeur / 2 + echelle * xc / zc
        py = hauteur / 2 - echelle * yc / zc
    visible = devant & (px >= 0) & (px < largeur) & (py >= 0) & (py < hauteur)
    return px, py, visible


@dataclass(frozen=True)
class Ciel:
    """Ciel peint derrière la scène."""

    haut: str
    bas: str
    etoiles: float = 0.0  # 0 : aucune ; 1 : ciel de campagne sans lune


@lru_cache(maxsize=16)
def degrade_ciel(haut: str, bas: str, taille: tuple[int, int]) -> NDArray[np.float32]:
    """Dégradé vertical ``(hauteur, largeur, 3)`` en [0 ; 1], du haut de l'image vers le bas."""
    largeur, hauteur = taille
    u = np.linspace(0.0, 1.0, hauteur, dtype=np.float32)[:, None]
    # Un peu plus de haut que de bas : l'horizon clair reste une bande, comme dehors.
    u = u**1.4
    colonne = (1 - u) * teinte(haut).astype(np.float32) + u * teinte(bas).astype(np.float32)
    return np.ascontiguousarray(np.broadcast_to(colonne[:, None, :], (hauteur, largeur, 3)))


def composer_ciel(rgba: Image, ciel: Ciel, *, camera: tuple[Tableau, Tableau, Tableau, float] | None = None,
                  t: float = 0.0) -> Image:
    """Image RGBA prémultipliée sur fond transparent → RGB avec ciel (et étoiles) derrière.

    ``camera`` : (position, visée, haut, champ vertical en °), dans un repère dont les
    axes sont ceux de l'ENU (l'origine flottante ne change pas une direction).
    """
    hauteur, largeur = rgba.shape[:2]
    fond = degrade_ciel(ciel.haut, ciel.bas, (largeur, hauteur)).copy()
    if ciel.etoiles > 0 and camera is not None:
        cat = etoiles()
        position, visee, haut, champ = camera
        px, py, visible = projeter(cat.directions, position, visee, haut, champ, (largeur, hauteur))
        # Taille d'une étoile en pixels : constante à l'écran, un peu plus grosse en 4K.
        echelle = max(1.0, hauteur / 1080)
        scint = 1 + 0.18 * np.sin(1.3 * t + cat.phases)
        k = np.flatnonzero(visible)
        eclat = np.clip(1.8 * cat.eclat[k] * scint[k] * ciel.etoiles, 0, 1)
        couleur = cat.couleurs[k] * eclat[:, None]
        x, y = px[k], py[k]
        # Dépôt bilinéaire sur les 4 pixels voisins : pas de scintillement d'aliasing quand
        # la caméra tourne lentement.
        for dx in (0, 1):
            for dy in (0, 1):
                xi = np.floor(x).astype(int) + dx
                yi = np.floor(y).astype(int) + dy
                w = (1 - np.abs(x - xi)) * (1 - np.abs(y - yi))
                ok = (xi >= 0) & (xi < largeur) & (yi >= 0) & (yi < hauteur) & (w > 0)
                np.add.at(fond, (yi[ok], xi[ok]), (couleur[ok] * w[ok, None] * echelle).astype(np.float32))
        # Les plus brillantes ont un petit halo.
        brillantes = eclat > 0.55
        if brillantes.any():
            xb, yb = np.round(x[brillantes]).astype(int), np.round(y[brillantes]).astype(int)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                xi, yi = xb + dx, yb + dy
                ok = (xi >= 0) & (xi < largeur) & (yi >= 0) & (yi < hauteur)
                np.add.at(fond, (yi[ok], xi[ok]), (0.25 * couleur[brillantes][ok]).astype(np.float32))
        np.clip(fond, 0, 1, out=fond)
    alpha = rgba[..., 3:4].astype(np.float32) / 255.0
    sortie = rgba[..., :3].astype(np.float32) + (1.0 - alpha) * fond * 255.0
    return np.asarray(np.clip(sortie + 0.5, 0, 255), dtype=np.uint8)


def lueur(image: Image, intensite: float, seuil: float = 0.62, rayon: float = 0.012) -> Image:
    """Halo autour des zones plus lumineuses que ``seuil`` ; ``rayon`` en fraction de la hauteur."""
    if intensite <= 0:
        return image
    from PIL import Image as Pil
    from PIL import ImageFilter

    hauteur, largeur = image.shape[:2]
    f = image.astype(np.float32) / 255.0
    luminance = f @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    exces = np.clip((luminance - seuil) / max(1 - seuil, 1e-3), 0, 1)
    if not exces.any():
        return image
    source = f * exces[..., None]
    petite = (max(1, largeur // 4), max(1, hauteur // 4))
    p = Pil.fromarray(np.asarray(source * 255, dtype=np.uint8)).resize(petite, Pil.Resampling.BILINEAR)
    r = max(1.0, rayon * hauteur / 4)
    # Deux halos : un serré (cœur), un large (atmosphère).
    serre = np.asarray(p.filter(ImageFilter.GaussianBlur(r)), dtype=np.float32)
    large = np.asarray(p.filter(ImageFilter.GaussianBlur(4 * r)), dtype=np.float32)
    halo = Pil.fromarray(np.asarray(np.clip(1.6 * serre + 2.2 * large, 0, 255), dtype=np.uint8))
    halo_plein = np.asarray(halo.resize((largeur, hauteur), Pil.Resampling.BILINEAR), dtype=np.float32)
    sortie = image.astype(np.float32) + intensite * halo_plein
    return np.asarray(np.clip(sortie + 0.5, 0, 255), dtype=np.uint8)
