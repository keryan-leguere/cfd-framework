"""Écriture des images : MP4 H.264 en flux (imageio-ffmpeg) et PNG (Pillow).

Le binaire ffmpeg vient de la roue ``imageio-ffmpeg`` : rien à installer côté
système. Deux pièges, réglés ici une fois pour toutes :

* imageio-ffmpeg **redimensionne** par défaut toute image dont un côté n'est pas
  multiple de 16 (1080 → 1088, image déformée) : ``macro_block_size=1`` ;
* yuv420p (le seul format que lisent tous les lecteurs, PowerPoint compris)
  exige des dimensions **paires**.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from numpy.typing import NDArray

__all__ = ["Encodeur", "InfoVideo", "concatener", "ecrire_png", "lire_images", "sonder_video"]


class Encodeur:
    """Reçoit des images RGB ``uint8`` une par une et les écrit en MP4."""

    def __init__(self, chemin: str | Path, largeur: int, hauteur: int, ips: float,
                 *, crf: int = 18, preset: str = "medium", threads: int | None = None) -> None:
        if largeur % 2 or hauteur % 2:
            raise ValueError(f"dimensions {largeur}×{hauteur} : paires exigées par yuv420p")
        self.chemin = Path(chemin)
        self.chemin.parent.mkdir(parents=True, exist_ok=True)
        self.forme = (hauteur, largeur, 3)
        self.n_images = 0
        self._flux = imageio_ffmpeg.write_frames(
            str(self.chemin), (largeur, hauteur), fps=ips, codec="libx264",
            pix_fmt_in="rgb24", pix_fmt_out="yuv420p", quality=None, macro_block_size=1,
            output_params=["-crf", str(crf), "-preset", preset, "-movflags", "+faststart",
                           *([] if threads is None else ["-threads", str(threads)])],
        )
        self._flux.send(None)

    def ajouter(self, image: NDArray[np.uint8]) -> None:
        """Ajoute une image ``(hauteur, largeur, 3)``."""
        if image.shape != self.forme or image.dtype != np.uint8:
            raise ValueError(f"image {image.shape} {image.dtype}, attendu {self.forme} uint8")
        self._flux.send(np.ascontiguousarray(image))
        self.n_images += 1

    def fermer(self) -> None:
        """Termine le fichier (indispensable : l'index MP4 est écrit à la fin)."""
        self._flux.close()

    def __enter__(self) -> Encodeur:
        return self

    def __exit__(self, *exc: object) -> None:
        self.fermer()


@dataclass(frozen=True)
class InfoVideo:
    """Ce que ffmpeg dit d'un fichier vidéo."""

    largeur: int
    hauteur: int
    ips: float
    n_images: int
    duree: float
    codec: str
    format_pixels: str


def sonder_video(chemin: str | Path) -> InfoVideo:
    """Dimensions, cadence, nombre d'images (décodées, pas estimées), codec."""
    n, duree = imageio_ffmpeg.count_frames_and_secs(str(chemin))
    sortie = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(chemin)],
                            capture_output=True, text=True, check=False).stderr
    m = re.search(r"Video: (\w+).*?, (\w+)(?:\([^)]*\))?, (\d+)x(\d+).*?, ([\d.]+) fps", sortie)
    if m is None:
        raise ValueError(f"{chemin} : pas de flux vidéo lisible\n{sortie}")
    return InfoVideo(largeur=int(m.group(3)), hauteur=int(m.group(4)), ips=float(m.group(5)),
                     n_images=int(n), duree=float(duree), codec=m.group(1), format_pixels=m.group(2))


def lire_images(chemin: str | Path) -> Iterator[NDArray[np.uint8]]:
    """Les images décodées d'une vidéo, ``(hauteur, largeur, 3)`` RGB, une par une."""
    lecteur = imageio_ffmpeg.read_frames(str(chemin), pix_fmt="rgb24")
    meta = next(lecteur)
    largeur, hauteur = meta["size"]
    for octets in lecteur:
        yield np.frombuffer(octets, dtype=np.uint8).reshape(hauteur, largeur, 3)


def ecrire_png(image: NDArray[np.uint8], chemin: str | Path) -> Path:
    """Écrit une image RGB en PNG."""
    from PIL import Image

    p = Path(chemin)
    p.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(p)
    return p


def concatener(troncons: list[Path], sortie: str | Path) -> Path:
    """Recolle des MP4 encodés à l'identique, **sans réencoder** (démultiplexeur concat de ffmpeg).

    Chaque tronçon commence par une image clé (début de flux) : la copie des paquets
    suffit et l'opération coûte le temps d'écrire le fichier.
    """
    if not troncons:
        raise ValueError("aucun tronçon à recoller")
    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    liste = sortie.with_name(f".{sortie.name}.troncons.txt")
    # Échappement du démultiplexeur concat : chemins entre apostrophes, ' → '\''
    liste.write_text("".join("file '" + str(Path(p).resolve()).replace("'", "'\\''") + "'\n"
                             for p in troncons), encoding="utf-8")
    try:
        r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "concat", "-safe", "0", "-i", str(liste), "-c", "copy",
                            "-movflags", "+faststart", str(sortie)],
                           capture_output=True, text=True, check=False)
    finally:
        liste.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg n'a pas pu recoller les tronçons : {r.stderr.strip()}")
    return sortie
