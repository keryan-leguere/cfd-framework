"""Montage : collage, liseré, calques, habillage dans le temps."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cfd_trajcast.core.disposition import Case
from cfd_trajcast.data.configuration import ConfigMontage, Etude, Logo
from cfd_trajcast.data.trajectoire import Evenement
from cfd_trajcast.engine.montage import Calque, Habillage, coller, encadrer, melanger, poser
from cfd_trajcast.engine.telemetrie import chemin_police

L, H = 320, 180


def test_coller_et_encadrer() -> None:
    c = np.zeros((H, L, 3), np.uint8)
    case = Case("a", 10, 20, 100, 50, medaillon=True)
    coller(c, case, np.full((50, 100, 3), 200, np.uint8))
    assert np.all(c[20:70, 10:110] == 200) and c.sum() == 200 * 3 * 50 * 100
    with pytest.raises(ValueError, match="attendu"):
        coller(c, case, np.zeros((10, 10, 3), np.uint8))
    encadrer(c, case, epaisseur=2)
    assert np.all(c[20, 10:110] == [244, 246, 248]) and np.all(c[40, 30] == 200)


def test_poser_alpha_et_bords() -> None:
    c = np.zeros((10, 10, 3), np.uint8)
    rgba = np.zeros((4, 4, 4), np.uint8)
    rgba[..., :3] = 255
    rgba[..., 3] = 255
    poser(c, Calque(rgba, 8, 8), opacite=0.5)  # déborde : découpé
    assert np.all(c[8:, 8:] == 128) and c[:8].sum() == 0


def test_melanger() -> None:
    a, b = np.full((2, 2, 3), 200, np.uint8), np.zeros((2, 2, 3), np.uint8)
    assert np.all(melanger(a, b, 0.25) == 50)


def _habillage(tmp_path: Path, **cfg) -> Habillage:  # type: ignore[no-untyped-def]
    t_video = np.arange(300) / 30          # 10 s de vidéo
    t_vol = t_video * 2                    # vitesse 2 : 20 s de vol
    return Habillage(ConfigMontage(**cfg), Etude("Titre", "Sous-titre"), (Evenement(8.0, "Apogée"),),
                     (L, H), t_video, t_vol, chemin_police(), duree=10.0)


def _ecart(h: Habillage, t: float) -> float:
    gris = np.full((H, L, 3), 100, np.uint8)
    return float(np.abs(h.appliquer(gris.copy(), t).astype(int) - 100).sum())


def test_titre_bandeau_generique(tmp_path: Path) -> None:
    h = _habillage(tmp_path, titre_debut=2.0, generique_fin=2.0, duree_bandeau=1.5)
    assert _ecart(h, 0.5) > 0              # titre
    assert _ecart(h, 3.0) == 0             # rien
    assert _ecart(h, 4.3) > 0              # bandeau : événement à 8 s de vol = 4 s de vidéo
    assert _ecart(h, 6.0) == 0
    assert _ecart(h, 9.5) > _ecart(h, 0.5)  # générique : assombri + titre


def test_sans_habillage(tmp_path: Path) -> None:
    h = _habillage(tmp_path, titre_debut=0, generique_fin=0, bandeaux_evenements=False)
    assert all(_ecart(h, t) == 0 for t in (0.0, 4.3, 9.9))


def test_logo_dans_son_coin(tmp_path: Path) -> None:
    from PIL import Image

    f = tmp_path / "logo.png"
    Image.new("RGBA", (40, 20), (255, 0, 0, 255)).save(f)
    h = _habillage(tmp_path, titre_debut=0, generique_fin=0, bandeaux_evenements=False,
                   logo=Logo(f, "bas_droite", 0.1))
    image = h.appliquer(np.zeros((H, L, 3), np.uint8), 5.0)
    ys, xs = np.nonzero(image[..., 0] > 200)
    assert ys.min() > H / 2 and xs.min() > L / 2 and ys.max() - ys.min() + 1 == 18


@pytest.mark.parametrize("position", ["haut", "centre", "bas"])
def test_position_du_titre(tmp_path: Path, position: str) -> None:
    h = _habillage(tmp_path, titre_debut=2.0, generique_fin=0, bandeaux_evenements=False,
                   position_titre=position)
    gris = np.full((H, L, 3), 100, np.uint8)
    ys = np.nonzero(np.any(h.appliquer(gris.copy(), 0.5) != 100, axis=2))[0]
    milieu = (ys.min() + ys.max()) / 2
    attendu = {"haut": H * 0.25, "centre": H * 0.5, "bas": H * 0.75}[position]
    assert abs(milieu - attendu) < H * 0.2


def test_coin_des_bandeaux(tmp_path: Path) -> None:
    h = _habillage(tmp_path, titre_debut=0, generique_fin=0, coin_bandeaux="haut_droite")
    gris = np.full((H, L, 3), 100, np.uint8)
    ys, xs = np.nonzero(np.any(h.appliquer(gris.copy(), 4.6) != 100, axis=2))
    assert xs.min() > L / 2 and ys.max() < H / 2


def test_bandeau_ne_chevauche_pas_le_titre(tmp_path: Path) -> None:
    """Un événement pendant le titre (en haut) : la pile de bandeaux passe sous le titre."""
    taille, t_video = (640, 360), np.arange(300) / 30
    etude = Etude("Un titre vraiment long, pour la démonstration", "et son sous-titre")

    def habillage(bandeaux: bool) -> Habillage:
        return Habillage(ConfigMontage(titre_debut=3.0, generique_fin=0, coin_bandeaux="haut_gauche",
                                       bandeaux_evenements=bandeaux), etude, (Evenement(0.0, "Allumage"),),
                         taille, t_video, t_video, chemin_police(), duree=10.0)

    h, seul = habillage(True), habillage(False)
    titre = h._titre
    assert titre is not None
    bas_titre = titre.y + titre.rgba.shape[0]
    noir = np.zeros((360, 640, 3), np.uint8)
    ajout = np.any(h.appliquer(noir.copy(), 0.5) != seul.appliquer(noir.copy(), 0.5), axis=2)
    assert np.nonzero(ajout)[0].min() >= bas_titre      # sous le titre, pas dessus
    # Titre effacé : la pile est revenue dans son coin, en haut.
    fin = np.any(h.appliquer(noir.copy(), 2.95) != seul.appliquer(noir.copy(), 2.95), axis=2)
    assert np.nonzero(fin)[0].min() < bas_titre
