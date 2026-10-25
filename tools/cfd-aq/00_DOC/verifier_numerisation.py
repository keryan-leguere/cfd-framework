"""Superpose the package's correlations on the scanned figures of the report.

This is the check that matters, and it is the one nobody can do from a table
of numbers: it renders Figures 4.23, 4.28 and 4.34 out of the source PDF and
draws `cfd-aq`'s own curves on top of them, dashed, so the original stroke
stays visible underneath.

    python 00_DOC/verifier_numerisation.py [--sortie 00_DOC/FIGURES]

Needs ``pdftoppm`` (poppler-utils) and ``DTIC_ADA106030.pdf`` at the root of
the package. Both are checked up front; the script says what is missing
rather than failing halfway.

The pixel calibrations below were established once, by locating each figure's
axis labels in the 400 dpi render, and are what make the superposition
meaningful. They are specific to this PDF.
"""

from __future__ import annotations

import argparse
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
PDF = RACINE / "DTIC_ADA106030.pdf"
RESOLUTION = 400

#: Largeur des planches écrites, en pixels. Les scans sont rendus à 400 dpi
#: pour être numérisés ; 1600 px suffisent à les relire dans un README.
LARGEUR_SORTIE = 1600


@dataclass(frozen=True)
class Etalonnage:
    """Pixel calibration of one scanned figure, at :data:`RESOLUTION` dpi.

    Attributes:
        page: 1-based page of the PDF.
        titre: figure caption, for the output file name.
        x_h10: pixel abscissa of h⁺ = 10.
        px_decade: pixels per decade of h⁺.
        y_zero: pixel ordinate of CDe/Cfe = 0.
        px_unite: pixels per unit of CDe/Cfe.
        recadrage: crop box of the output image.
        h_min: lowest h⁺ worth drawing on this figure.
    """

    page: int
    titre: str
    x_h10: float
    px_decade: float
    y_zero: float
    px_unite: float
    recadrage: tuple[int, int, int, int]
    h_min: float = 25.0


FIGURES: dict[str, tuple[Etalonnage, Sequence[tuple[float, tuple[int, int, int]]]]] = {}


def _enregistrer(
    nom: str,
    etalonnage: Etalonnage,
    courbes: Sequence[tuple[float, tuple[int, int, int]]],
) -> None:
    FIGURES[nom] = (etalonnage, courbes)


_VERT = (0, 160, 0)
_BLEU = (0, 0, 255)
_ROUGE = (255, 0, 0)
_ORANGE = (255, 140, 0)
_MAGENTA = (160, 0, 160)
_CYAN = (0, 180, 180)
_BRUN = (120, 80, 0)

_enregistrer(
    "10_verification_4.23_marche_montante",
    Etalonnage(88, "Figure 4.23", 828.0, 947.0, 1621.0, 5.60, (600, 250, 3250, 1750), 55.0),
    [(0.2, _VERT), (0.8, _BLEU), (2.0, _ROUGE)],
)
_enregistrer(
    "11_verification_4.28_marche_descendante",
    Etalonnage(93, "Figure 4.28", 1181.0, 691.4, 1554.5, 5.52, (980, 820, 2900, 1700)),
    [
        (0.2, _VERT),
        (0.8, _BLEU),
        (1.4, _ROUGE),
        (1.7, _ORANGE),
        (2.0, _MAGENTA),
        (2.2, _CYAN),
        (2.8, _BRUN),
    ],
)
_enregistrer(
    "12_verification_4.34_arete_carree",
    Etalonnage(98, "Figure 4.34", 1054.0, 697.0, 2045.0, 2.73, (840, 900, 2850, 2150)),
    [(0.2, _VERT), (0.8, _BLEU), (1.4, _ROUGE), (2.2, _ORANGE), (2.8, _MAGENTA)],
)

FONCTIONS: dict[str, Callable[[float, float], float]] = {}


def _charger_fonctions() -> None:
    from cfd_aq.core import marches

    FONCTIONS["10_verification_4.23_marche_montante"] = marches.ratio_marche_montante
    FONCTIONS["11_verification_4.28_marche_descendante"] = marches.ratio_marche_descendante
    FONCTIONS["12_verification_4.34_arete_carree"] = marches.ratio_arete


def _rendre_page(page: int, repertoire: Path) -> Path:
    prefixe = repertoire / f"p{page}"
    subprocess.run(
        [
            "pdftoppm",
            "-f",
            str(page),
            "-l",
            str(page),
            "-r",
            str(RESOLUTION),
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


def _superposer(nom: str, source: Path, destination: Path) -> Path:
    """Draw the package's curves over the scanned figure, dashed.

    The scan is cropped, binarised and reduced **first**, and the curves are
    drawn on the reduced image afterwards. Drawing then reducing would
    antialias the coloured strokes into the halftone grey of the microfiche
    and triple the file size for a worse picture.
    """
    etalonnage, courbes = FIGURES[nom]
    fonction = FONCTIONS[nom]

    x0, y0, x1, y1 = etalonnage.recadrage
    fond = Image.open(source).convert("L").crop(etalonnage.recadrage)
    # Le scan est déjà pratiquement binaire ; le rendre franchement noir et
    # blanc laisse une palette de deux teintes sous les sept du tracé.
    fond = fond.point(lambda v: 0 if v < 150 else 255, mode="1").convert("L")
    echelle = LARGEUR_SORTIE / (x1 - x0)
    hauteur = round((y1 - y0) * echelle)
    image = fond.resize((LARGEUR_SORTIE, hauteur), Image.LANCZOS)
    image = image.point(lambda v: 0 if v < 150 else 255).convert("RGB")
    dessin = ImageDraw.Draw(image)

    h_max = 2000.0
    for mach, couleur in courbes:
        points = []
        for i in range(400):
            fraction = i / 399.0
            h_plus = 10 ** (
                math.log10(etalonnage.h_min)
                + fraction * (math.log10(h_max) - math.log10(etalonnage.h_min))
            )
            valeur = fonction(h_plus, mach)
            points.append(
                (
                    (etalonnage.x_h10 + etalonnage.px_decade * (math.log10(h_plus) - 1.0) - x0)
                    * echelle,
                    (etalonnage.y_zero - valeur * etalonnage.px_unite - y0) * echelle,
                )
            )
        # Tiretés : le trait d'origine reste visible dessous, ce qui est tout
        # l'intérêt de la superposition.
        for debut_segment, fin_segment in zip(points[::2], points[1::2]):
            dessin.line([debut_segment, fin_segment], fill=couleur, width=3)

    destination.parent.mkdir(parents=True, exist_ok=True)
    image.quantize(colors=16, method=Image.Quantize.MEDIANCUT).save(destination, optimize=True)
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    parseur = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parseur.add_argument(
        "--sortie",
        type=Path,
        default=RACINE / "00_DOC" / "FIGURES",
        help="répertoire de sortie",
    )
    arguments = parseur.parse_args(argv)

    if shutil.which("pdftoppm") is None:
        print(
            "pdftoppm est introuvable. Installer poppler-utils "
            "(apt install poppler-utils / dnf install poppler-utils).",
            file=sys.stderr,
        )
        return 1
    if not PDF.exists():
        print(f"Le rapport source est absent : {PDF}", file=sys.stderr)
        return 1

    _charger_fonctions()
    with tempfile.TemporaryDirectory() as brut:
        for nom, (etalonnage, _) in FIGURES.items():
            rendu = _rendre_page(etalonnage.page, Path(brut))
            ecrit = _superposer(nom, rendu, arguments.sortie / f"{nom}.png")
            print(f"{etalonnage.titre:14s} → {ecrit}")
    print(
        "\nLes traits pointillés sont ceux de cfd-aq, les traits pleins ceux du "
        "rapport.\nIls doivent se recouvrir sur toute la plage h⁺ = 25 à 2000."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
