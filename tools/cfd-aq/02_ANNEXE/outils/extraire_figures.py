#!/usr/bin/env python3
"""Prépare toutes les images de l'annexe Word.

    python3 outils/extraire_figures.py

Trois familles d'images, écrites dans ``02_ANNEXE/FIGURES/`` :

``orig_*.png``
    la figure telle qu'elle est dans le rapport — capture directe du PDF,
    recadrée et binarisée, rien d'autre ;
``verif_*.png``
    la même, avec les courbes du script tracées par-dessus en tiretés : le
    trait d'origine reste visible dessous, c'est la preuve de la numérisation ;
``ext_*.png``
    l'extraction seule, redessinée proprement depuis les tables du script.

Les ``ext_*`` sont produites par ``trainee_marches.py`` lui-même : les
planches de l'annexe sortent donc exactement du fichier livré au client.

Il faut ``pdftoppm`` (poppler-utils) et le rapport source à la racine du
paquet. Les étalonnages en pixels ci-dessous ont été établis une fois, en
repérant les étiquettes d'axes dans le rendu à 400 dpi ; ils sont propres à
ce PDF.
"""

from __future__ import annotations

import importlib.util
import math
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

RACINE = Path(__file__).resolve().parent.parent
PDF = RACINE.parent / "DTIC_ADA106030.pdf"
FIGURES = RACINE / "FIGURES"
LARGEUR = 1700


def _charger_script():
    """Importe trainee_marches.py sans l'installer."""
    chemin = RACINE / "trainee_marches.py"
    spec = importlib.util.spec_from_file_location("trainee_marches", chemin)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["trainee_marches"] = module  # dataclasses a besoin du module
    spec.loader.exec_module(module)
    return module


# --- 1. Captures brutes du PDF --------------------------------------------


@dataclass(frozen=True)
class Capture:
    """Une figure à découper dans une page, en fractions de la page."""

    page: int
    nom: str
    y0: float
    y1: float
    x0: float = 0.03
    x1: float = 0.97


CAPTURES = (
    Capture(88, "4_23", 0.030, 0.460, 0.10, 0.95),
    Capture(90, "4_25", 0.190, 0.640, 0.20, 0.90),
    Capture(91, "4_26a", 0.050, 0.315, 0.15, 0.85),
    Capture(91, "4_26b", 0.315, 0.615, 0.15, 0.85),
    Capture(93, "4_28", 0.110, 0.450, 0.18, 0.86),
    Capture(94, "4_30", 0.550, 0.930, 0.20, 0.90),
    Capture(96, "4_33", 0.520, 0.950, 0.20, 0.90),
    Capture(98, "4_34", 0.207, 0.500, 0.15, 0.85),
    Capture(100, "4_38", 0.565, 0.900, 0.15, 0.80),
    Capture(102, "4_40", 0.715, 0.960, 0.25, 0.90),
    Capture(106, "4_45", 0.600, 0.960, 0.10, 0.80),
)


def _rendre(page: int, repertoire: Path, resolution: int = 400) -> Path:
    prefixe = repertoire / f"p{page}"
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(page),
            "-l",
            str(page),
            "-r",
            str(resolution),
            "-png",
            str(PDF),
            str(prefixe),
        ],
        check=True,
        capture_output=True,
    )
    rendus = sorted(repertoire.glob(f"p{page}-*.png"))
    if not rendus:
        raise RuntimeError(f"pdftoppm n'a rien produit pour la page {page}")
    return rendus[0]


def _binariser(image: Image.Image, largeur: int = LARGEUR) -> Image.Image:
    """Binarise puis réduit. Dans cet ordre : le scan est une trame de
    microfiche, l'antialiasing d'une réduction en niveaux de gris triple le
    poids du PNG pour une image moins nette."""
    image = image.convert("L").point(lambda v: 0 if v < 150 else 255, mode="1")
    image = image.convert("L")
    hauteur = round(image.height * largeur / image.width)
    reduite = image.resize((largeur, hauteur), Image.LANCZOS)
    return reduite.point(lambda v: 0 if v < 140 else 255).convert("L")


def _boite(page: Path, capture: Capture, marge: int = 40) -> tuple[int, int, int, int]:
    import numpy as np

    a = np.asarray(Image.open(page).convert("L"))
    hauteur, largeur = a.shape
    y0, y1 = int(capture.y0 * hauteur), int(capture.y1 * hauteur)
    x0, x1 = int(capture.x0 * largeur), int(capture.x1 * largeur)
    encre = a[y0:y1, x0:x1] < 150
    lignes = np.nonzero(encre.sum(axis=1) > 3)[0]
    colonnes = np.nonzero(encre.sum(axis=0) > 3)[0]
    return (
        max(0, x0 + int(colonnes[0]) - marge),
        max(0, y0 + int(lignes[0]) - marge),
        min(largeur, x0 + int(colonnes[-1]) + marge),
        min(hauteur, y0 + int(lignes[-1]) + marge),
    )


# --- 2. Superpositions -----------------------------------------------------


@dataclass(frozen=True)
class Etalonnage:
    """Étalonnage en pixels d'une figure scannée, au rendu 400 dpi."""

    page: int
    nom: str
    x_h10: float  # abscisse de h+ = 10
    px_decade: float  # pixels par décade de h+
    y_zero: float  # ordonnée de CDe/Cfe = 0
    px_unite: float  # pixels par unité de CDe/Cfe
    recadrage: tuple[int, int, int, int]
    h_min: float = 25.0


_VERT, _BLEU, _ROUGE = (0, 160, 0), (0, 0, 255), (255, 0, 0)
_ORANGE, _MAGENTA, _CYAN, _BRUN = (255, 140, 0), (160, 0, 160), (0, 180, 180), (120, 80, 0)


def superpositions(script) -> Sequence[tuple[Etalonnage, Sequence, Callable]]:
    return (
        (
            Etalonnage(88, "4_23", 828.0, 947.0, 1621.0, 5.60, (600, 250, 3250, 1750), 55.0),
            [(0.2, _VERT), (0.8, _BLEU), (2.0, _ROUGE)],
            script.ratio_marche_montante,
        ),
        (
            Etalonnage(93, "4_28", 1181.0, 691.4, 1554.5, 5.52, (980, 820, 2900, 1700)),
            [
                (0.2, _VERT),
                (0.8, _BLEU),
                (1.4, _ROUGE),
                (1.7, _ORANGE),
                (2.0, _MAGENTA),
                (2.2, _CYAN),
                (2.8, _BRUN),
            ],
            script.ratio_marche_descendante,
        ),
        (
            Etalonnage(98, "4_34", 1054.0, 697.0, 2045.0, 2.73, (840, 900, 2850, 2150)),
            [(0.2, _VERT), (0.8, _BLEU), (1.4, _ROUGE), (2.2, _ORANGE), (2.8, _MAGENTA)],
            script.ratio_arete,
        ),
    )


def _superposer(etalonnage: Etalonnage, courbes, fonction, source: Path, destination: Path) -> Path:
    x0, y0, x1, _y1 = etalonnage.recadrage
    fond = Image.open(source).convert("L").crop(etalonnage.recadrage)
    echelle = LARGEUR / (x1 - x0)
    image = _binariser(fond).convert("RGB")
    dessin = ImageDraw.Draw(image)

    for mach, couleur in courbes:
        points = []
        for i in range(400):
            h_plus = 10 ** (
                math.log10(etalonnage.h_min)
                + i / 399.0 * (math.log10(2000.0) - math.log10(etalonnage.h_min))
            )
            valeur = fonction(h_plus, mach)
            points.append(
                (
                    (etalonnage.x_h10 + etalonnage.px_decade * (math.log10(h_plus) - 1.0) - x0)
                    * echelle,
                    (etalonnage.y_zero - valeur * etalonnage.px_unite - y0) * echelle,
                )
            )
        # Tiretés : le trait d'origine reste visible dessous.
        for debut, fin in zip(points[::2], points[1::2]):
            dessin.line([debut, fin], fill=couleur, width=3)

    image.quantize(colors=16, method=Image.Quantize.MEDIANCUT).save(destination, optimize=True)
    return destination


# --- 3. Chef d'orchestre ---------------------------------------------------


def main() -> int:
    if shutil.which("pdftoppm") is None:
        print("pdftoppm est introuvable (apt install poppler-utils).", file=sys.stderr)
        return 1
    if not PDF.exists():
        print(f"Le rapport source est absent : {PDF}", file=sys.stderr)
        return 1

    FIGURES.mkdir(parents=True, exist_ok=True)
    script = _charger_script()

    with tempfile.TemporaryDirectory() as brut:
        repertoire = Path(brut)
        rendus: dict[int, Path] = {}

        print("Captures du rapport :")
        for capture in CAPTURES:
            page = rendus.setdefault(capture.page, _rendre(capture.page, repertoire))
            destination = FIGURES / f"orig_{capture.nom}.png"
            _binariser(Image.open(page).crop(_boite(page, capture))).save(
                destination, optimize=True
            )
            print(f"   {destination.name:22s} ({destination.stat().st_size // 1024} ko)")

        print("Superpositions :")
        for etalonnage, courbes, fonction in superpositions(script):
            page = rendus.setdefault(etalonnage.page, _rendre(etalonnage.page, repertoire))
            destination = FIGURES / f"verif_{etalonnage.nom}.png"
            _superposer(etalonnage, courbes, fonction, page, destination)
            print(f"   {destination.name:22s} ({destination.stat().st_size // 1024} ko)")

    print("Extractions (tracées par trainee_marches.py) :")
    for chemin in script.tracer_extractions(str(FIGURES)):
        taille = Path(chemin).stat().st_size // 1024
        print(f"   {Path(chemin).name:22s} ({taille} ko)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
