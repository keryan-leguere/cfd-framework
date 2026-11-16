"""Montage image par image : vues dans leurs cases, puis habillage.

Tout est en NumPy (collage, mélanges) ; Pillow ne sert qu'à dessiner les textes
et le logo, **une fois**, en calques RGBA réutilisés à chaque image avec une
opacité qui varie (fondus).

Habillage, en temps vidéo :

* **titre** sur les ``titre_debut`` premières secondes, qui s'efface en fondu ; en
  haut par défaut (``position_titre``), parce qu'au centre il cache la fusée ;
* **générique** sur les ``generique_fin`` dernières : l'image s'assombrit et le
  titre revient ;
* **bandeaux d'événements** : à l'instant de vol de chaque événement, un bandeau
  « nom · T+ x s » dans le coin ``coin_bandeaux`` (en écartant le logo s'il y est),
  empilés s'ils se chevauchent, pendant ``duree_bandeau`` ;
* **logo** dans un coin, toujours ;
* **étiquettes** : le nom de chaque vue, en haut à gauche de sa case.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core.disposition import TELEMETRIE, Case
from cfd_trajcast.data.configuration import ConfigMontage, Etude
from cfd_trajcast.data.trajectoire import Evenement

__all__ = ["Calque", "Habillage", "coller", "couleur", "encadrer", "melanger", "poser"]

Image = NDArray[np.uint8]
#: Durée des fondus d'entrée/sortie des textes (s de vidéo).
FONDU_TEXTE = 0.4
#: Assombrissement maximal pendant le générique.
NOIR_GENERIQUE = 0.65


def couleur(hexa: str) -> tuple[int, int, int]:
    """``"#rrggbb"`` → (r, g, b)."""
    h = hexa.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def coller(canevas: Image, case: Case, image: Image) -> None:
    """Colle ``image`` (déjà à la taille de la case) à sa place."""
    if image.shape[:2] != (case.hauteur, case.largeur):
        raise ValueError(f"case {case.nom} : image {image.shape[:2]}, attendu {(case.hauteur, case.largeur)}")
    canevas[case.y:case.y + case.hauteur, case.x:case.x + case.largeur] = image


def encadrer(canevas: Image, case: Case, epaisseur: int = 2, teinte: str = "#f4f6f8") -> None:
    """Liseré autour d'un médaillon, pour le détacher de la vue qu'il recouvre."""
    r = couleur(teinte)
    y0, y1, x0, x1 = case.y, case.y + case.hauteur, case.x, case.x + case.largeur
    e = epaisseur
    canevas[y0:y0 + e, x0:x1] = r
    canevas[y1 - e:y1, x0:x1] = r
    canevas[y0:y1, x0:x0 + e] = r
    canevas[y0:y1, x1 - e:x1] = r


def melanger(a: Image, b: Image, poids_a: float) -> Image:
    """``poids_a · a + (1 − poids_a) · b``."""
    return np.asarray(np.round(a * poids_a + b * (1.0 - poids_a)), dtype=np.uint8)


@dataclass(frozen=True, eq=False)
class Calque:
    """Une image RGBA à poser en ``(x, y)``."""

    rgba: NDArray[np.uint8]
    x: int
    y: int


def poser(canevas: Image, calque: Calque, opacite: float = 1.0) -> None:
    """Pose un calque RGBA avec une opacité globale, découpé aux bords de l'image."""
    if opacite <= 0:
        return
    h, w = calque.rgba.shape[:2]
    H, W = canevas.shape[:2]
    x0, y0 = max(calque.x, 0), max(calque.y, 0)
    x1, y1 = min(calque.x + w, W), min(calque.y + h, H)
    if x1 <= x0 or y1 <= y0:
        return
    morceau = calque.rgba[y0 - calque.y:y1 - calque.y, x0 - calque.x:x1 - calque.x]
    # Entiers 16 bits plutôt que flottants (deux fois moins de mémoire à traverser), et
    # seulement les lignes que le calque couvre vraiment (un titre est surtout transparent).
    a8 = morceau[..., 3]
    lignes = np.flatnonzero(a8.any(axis=1))
    if len(lignes) == 0:
        return
    l0, l1 = int(lignes[0]), int(lignes[-1]) + 1
    a: NDArray[np.uint16] = a8[l0:l1, :, None].astype(np.uint16)
    if opacite < 1:
        a = ((a * np.uint16(round(255 * opacite)) + np.uint16(127)) // np.uint16(255)).astype(np.uint16)
    zone = canevas[y0 + l0:y0 + l1, x0:x1]
    melange = (morceau[l0:l1, :, :3] * a + zone * (255 - a) + 127) // 255
    zone[...] = melange.astype(np.uint8)


@lru_cache(maxsize=32)
def _police(chemin: str, taille: int):  # type: ignore[no-untyped-def]
    from PIL import ImageFont

    return ImageFont.truetype(chemin, taille)


def _texte(lignes: list[tuple[str, int, str]], police: Path, *, fond: tuple[int, int, int, int] | None,
           marge: int, alignement: str = "gauche") -> NDArray[np.uint8]:
    """Bloc de lignes ``(texte, taille, couleur)`` en RGBA, avec un fond optionnel."""
    from PIL import Image as Img
    from PIL import ImageDraw

    mesure = ImageDraw.Draw(Img.new("RGBA", (1, 1)))
    boites = [mesure.textbbox((0, 0), t, font=_police(str(police), s)) for t, s, _ in lignes]
    largeur = int(max(b[2] - b[0] for b in boites) + 2 * marge)
    interligne = [int((b[3] - b[1]) * 1.35) for b in boites]
    hauteur = int(sum(interligne) + 2 * marge)
    image = Img.new("RGBA", (largeur, hauteur), fond or (0, 0, 0, 0))
    dessin = ImageDraw.Draw(image)
    y = marge
    for (texte, taille, teinte), b, pas in zip(lignes, boites, interligne):
        largeur_t = b[2] - b[0]
        x = marge if alignement == "gauche" else (largeur - largeur_t) // 2
        dessin.text((x - b[0], y - b[1]), texte, font=_police(str(police), taille), fill=teinte)
        y += pas
    return np.asarray(image, dtype=np.uint8)


def _secondes(t: float) -> str:
    return f"{t:.1f}".replace(".", ",")


class Habillage:
    """Les calques précalculés d'une vidéo et leur opacité à chaque instant."""

    def __init__(self, cfg: ConfigMontage, etude: Etude, evenements: tuple[Evenement, ...],
                 taille: tuple[int, int], t_video: NDArray[np.float64], t_vol: NDArray[np.float64],
                 police: Path, duree: float, zone_titre: tuple[int, int] | None = None) -> None:
        self.cfg = cfg
        largeur, hauteur = taille
        self.taille = taille
        self.police = police
        #: Durée de la vidéo **entière** : le générique se place par rapport à elle, même
        #: quand on ne compose qu'un début de plan (``Film.image``).
        self.duree = duree
        u = hauteur / 1080
        self._titre: Calque | None = None
        if etude.titre and (cfg.titre_debut > 0 or cfg.generique_fin > 0):
            lignes = [(etude.titre, int(64 * u), "#ffffff")]
            if etude.sous_titre:
                lignes.append((etude.sous_titre, int(34 * u), "#d5dde6"))
            rgba = _texte(lignes, police, fond=(10, 16, 24, 170), marge=int(36 * u), alignement="centre")
            y = {"haut": int(40 * u), "centre": (hauteur - rgba.shape[0]) // 2,
                 "bas": hauteur - rgba.shape[0] - int(40 * u)}[cfg.position_titre]
            # Centré sur la vue principale (``zone_titre`` = x, largeur), pas sur l'image entière :
            # la bande de télémétrie le décentrerait.
            x0, l0 = zone_titre if zone_titre is not None else (0, largeur)
            x = max(0, min(largeur - rgba.shape[1], x0 + (l0 - rgba.shape[1]) // 2))
            self._titre = Calque(rgba, x, y)
        # Bandeaux : un par événement montré, avec son instant vidéo.
        self._bandeaux: list[tuple[float, Calque]] = []
        if cfg.bandeaux_evenements and len(t_vol):
            for e in evenements:
                if not t_vol[0] <= e.t <= t_vol[-1]:
                    continue
                tau = float(np.interp(e.t, t_vol, t_video))
                rgba = _texte([(e.nom, int(38 * u), "#ffffff"), (f"T+ {_secondes(e.t)} s", int(24 * u), "#ffcc80")],
                              police, fond=(10, 16, 24, 190), marge=int(18 * u))
                x = int(32 * u) if cfg.coin_bandeaux.endswith("gauche") else largeur - rgba.shape[1] - int(32 * u)
                self._bandeaux.append((tau, Calque(rgba, x, 0)))
        self._logo: Calque | None = None
        if cfg.logo is not None:
            from PIL import Image as Img

            logo = Img.open(cfg.logo.fichier).convert("RGBA")
            h = max(2, int(cfg.logo.hauteur * hauteur))
            logo = logo.resize((max(1, round(logo.width * h / logo.height)), h), Img.Resampling.LANCZOS)
            rgba = np.asarray(logo, dtype=np.uint8)
            m = int(24 * u)
            x = m if cfg.logo.coin.endswith("gauche") else largeur - rgba.shape[1] - m
            y = m if cfg.logo.coin.startswith("haut") else hauteur - rgba.shape[0] - m
            self._logo = Calque(rgba, x, y)

    def etiquette(self, case: Case) -> Calque | None:
        """Nom de la vue en haut à gauche de sa case (pas pour la télémétrie)."""
        if not self.cfg.etiquettes_vues or case.nom == TELEMETRIE:
            return None
        u = self.taille[1] / 1080
        taille = max(10, int((18 if case.medaillon else 22) * u))
        rgba = _texte([(case.nom, taille, "#ffffff")], self.police, fond=(10, 16, 24, 150), marge=max(4, int(8 * u)))
        return Calque(rgba, case.x + int(12 * u), case.y + int(12 * u))

    @staticmethod
    def _rampe(t: float, debut: float, fin: float) -> float:
        """1 sur [debut ; fin], avec entrée et sortie en fondu."""
        if t < debut or t > fin:
            return 0.0
        return float(min(1.0, (t - debut) / FONDU_TEXTE, (fin - t) / FONDU_TEXTE))

    def _eviter_titre(self, bord: int, en_bas: bool, opacite_titre: float, u: float) -> int:
        """Pendant que le titre est affiché, la pile de bandeaux passe de l'autre côté de lui.

        Le décalage suit l'opacité du titre : quand il s'efface, la pile glisse vers son
        coin au lieu de sauter. Seulement si titre et bandeaux se recouvrent en largeur.
        """
        titre = self._titre
        if titre is None or opacite_titre <= 0 or not self._bandeaux:
            return bord
        x0 = min(c.x for _, c in self._bandeaux)
        x1 = max(c.x + c.rgba.shape[1] for _, c in self._bandeaux)
        if x1 <= titre.x or x0 >= titre.x + titre.rgba.shape[1]:
            return bord
        h_titre = titre.rgba.shape[0]
        if en_bas:
            cible = titre.y - int(12 * u)
            if cible >= bord:
                return bord
        else:
            cible = titre.y + h_titre + int(12 * u)
            if cible <= bord:
                return bord
        # Le titre n'est concerné que s'il est du même côté que la pile.
        if en_bas != (titre.y > self.taille[1] / 2):
            return bord
        return round(bord + min(1.0, opacite_titre) * (cible - bord))

    def appliquer(self, image: Image, t_video: float) -> Image:
        """Pose l'habillage de l'instant ``t_video`` sur une image composée."""
        cfg, hauteur = self.cfg, self.taille[1]
        fin = cfg.generique_fin
        if fin > 0 and t_video > self.duree - fin:
            sombre = NOIR_GENERIQUE * min(1.0, (t_video - (self.duree - fin)) / max(FONDU_TEXTE, 1e-6))
            image = np.asarray(image * (1 - sombre), dtype=np.uint8)
        opacite_titre = 0.0
        if self._titre is not None:
            opacite = 0.0
            if cfg.titre_debut > 0 and t_video <= cfg.titre_debut:
                opacite = min(1.0, (cfg.titre_debut - t_video) / FONDU_TEXTE)
            if fin > 0 and t_video >= self.duree - fin:
                opacite = max(opacite, min(1.0, (t_video - (self.duree - fin)) / FONDU_TEXTE))
            poser(image, self._titre, opacite)
            opacite_titre = opacite
        u = hauteur / 1080
        # Pile de bandeaux : part du coin choisi et s'en éloigne ; évite le logo s'il y est.
        en_bas = cfg.coin_bandeaux.startswith("bas")
        # En haut, on laisse la place de l'étiquette de la vue.
        bord = hauteur - int(40 * u) if en_bas else int(72 * u)
        if self._logo is not None and cfg.logo is not None and cfg.logo.coin == cfg.coin_bandeaux:
            bord = self._logo.y - int(16 * u) if en_bas else self._logo.y + self._logo.rgba.shape[0] + int(16 * u)
        bord = self._eviter_titre(bord, en_bas, opacite_titre, u)
        for tau, calque in self._bandeaux:
            opacite = self._rampe(t_video, tau, tau + cfg.duree_bandeau)
            if opacite > 0:
                h = calque.rgba.shape[0]
                y = bord - h if en_bas else bord
                poser(image, Calque(calque.rgba, calque.x, y), opacite)
                bord = y - int(12 * u) if en_bas else y + h + int(12 * u)
        if self._logo is not None:
            poser(image, self._logo)
        return image
