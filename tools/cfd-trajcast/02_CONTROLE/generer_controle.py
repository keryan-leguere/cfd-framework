"""Contrôle qualitatif d'un jalon : images à regarder, rangées dans ``02_CONTROLE/<jalon>/``.

    python 02_CONTROLE/generer_controle.py --jalon J1

Hors paquet, à dessein : il passe par l'API publique, exactement comme un
utilisateur, et peut se servir de PyVista / Matplotlib / Pillow sans que le
paquet ait besoin de ces chemins de code avant leur jalon.
"""

from __future__ import annotations

import argparse
import os
import platform
import sys
import time
from pathlib import Path

import numpy as np

from cfd_trajcast import Maquette, Trajectoire, __version__, charger_configuration, verifier
from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.reperes import matrice_vers_enu
from cfd_trajcast.paths import EXEMPLE_DIR

ICI = Path(__file__).resolve().parent

#: Couleurs des axes : convention habituelle x/y/z = rouge/vert/bleu.
ROUGE, VERT, BLEU, JAUNE, GRIS = "#d62728", "#2ca02c", "#1f77b4", "#e6b800", "#7f7f7f"


def _lire(config: str) -> tuple[Trajectoire, Maquette, list[str]]:
    cfg = charger_configuration(EXEMPLE_DIR / config)
    traj = cfg.trajectoire.charger()
    maquette = Maquette.depuis_declaration(cfg.maquette)
    constats = [f"{c.niveau:7s} {c.message}" for c in verifier(traj, maquette)]
    return traj, maquette, constats


def _vue_instant(traj: Trajectoire, maquette: Maquette, t: float, titre: str, taille: tuple[int, int]) -> np.ndarray:
    import pyvista as pv

    pos, q = traj.etat(t)
    q = q[0]
    r = rot.vers_matrice(q)
    # Origine flottante : la fusée est au centre de la scène, quel que soit son altitude.
    faces = np.hstack([np.full((len(maquette.faces), 1), 3), maquette.faces]).ravel()
    fusee = pv.PolyData(maquette.sommets @ r.T, faces)

    p = pv.Plotter(off_screen=True, window_size=taille)
    p.set_background("#f4f4f4")
    # Corps translucide : les axes partent du point de référence, à l'intérieur.
    p.add_mesh(fusee, color="#b0b0b0", smooth_shading=True, split_sharp_edges=True, opacity=0.45)
    L = maquette.longueur
    longueurs = (0.7 * L, 0.3 * L, 0.3 * L)  # le nez dépasse du dôme
    for axe, couleur, lg in zip(np.eye(3), (ROUGE, VERT, BLEU), longueurs):
        p.add_mesh(pv.Arrow(start=(0, 0, 0), direction=r @ axe, scale=lg, shaft_radius=0.02,
                            tip_radius=0.05), color=couleur)
    v = np.array([np.interp(t, traj.t, traj.vitesse[:, i]) for i in range(3)])
    if np.linalg.norm(v) > 1e-6:
        # Plus longue et plus fine que la flèche du nez : les deux restent visibles superposées.
        p.add_mesh(pv.Arrow(start=(0, 0, 0), direction=v / np.linalg.norm(v), scale=0.95 * L,
                            shaft_radius=0.008, tip_radius=0.022), color=JAUNE)
    cap = np.radians(30.0)
    horizontale = np.array([np.sin(cap), np.cos(cap), 0.0])
    cote = np.cross(np.array([0.0, 0.0, 1.0]), horizontale)
    # Trièdre ENU, gris, décalé en bas à gauche de la fusée.
    coin = -0.62 * L * horizontale - 0.55 * L * np.array([0.0, 0.0, 1.0])
    for axe, nom in zip(np.eye(3), "ENU"):
        p.add_mesh(pv.Arrow(start=coin, direction=axe, scale=0.22 * L, shaft_radius=0.02,
                            tip_radius=0.05), color=GRIS)
        p.add_point_labels([coin + 0.28 * L * axe], [nom], font_size=14, text_color=GRIS,
                           shape=None, show_points=False, always_visible=True)
    # Vue de côté : perpendiculaire au plan vertical de la trajectoire, la portée vers la droite.
    p.camera_position = [tuple(-cote * 4.2 * L), (0, 0, -0.05 * L), (0, 0, 1)]
    mach = float(np.interp(t, traj.t, traj.mach))
    nez = r[:, 0]
    pente = np.degrees(np.arcsin(np.clip(nez[2], -1, 1)))
    vh = np.linalg.norm(v)
    incidence = np.degrees(np.arccos(np.clip(nez @ v / vh, -1, 1))) if vh > 1e-6 else float("nan")
    # Retour aux angles d'Euler NED, le chemin inverse de la lecture.
    q_ned = rot.produit(rot.depuis_matrice(matrice_vers_enu("NED").T), q)
    lacet, tangage, roulis = np.degrees(rot.vers_euler(q_ned, "ZYX"))
    p.add_text(f"{titre}\nt = {t:.3f} s   altitude {pos[0, 2]:.0f} m   Mach {mach:.2f}\n"
               f"pente du nez {pente:+.1f}°   angle nez/vitesse {incidence:.2f}°\n"
               f"Euler NED : lacet {lacet:.1f}°  tangage {tangage:+.1f}°  roulis {roulis:+.1f}°",
               position="upper_left", font_size=11, color="black")
    image = p.screenshot(return_img=True)
    p.close()
    return np.asarray(image)


def _vue_ensemble(traj: Trajectoire, instants: list[tuple[float, str]], taille: tuple[int, int]) -> np.ndarray:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cap = np.radians(30.0)
    portee = traj.positions[:, 0] * np.sin(cap) + traj.positions[:, 1] * np.cos(cap)
    fig, ax = plt.subplots(figsize=(taille[0] / 100, taille[1] / 100), dpi=100)
    ax.plot(portee / 1e3, traj.positions[:, 2] / 1e3, color="black", lw=1.5)
    for i, (t, nom) in enumerate(instants, 1):
        k = int(np.argmin(np.abs(traj.t - t)))
        ax.plot(portee[k] / 1e3, traj.positions[k, 2] / 1e3, "o", color=ROUGE)
        ax.annotate(f"{i}. {nom}", (portee[k] / 1e3, traj.positions[k, 2] / 1e3),
                    textcoords="offset points", xytext=(8, -4), fontsize=10)
    ax.set_xlabel("portée selon le cap 30° (km)")
    ax.set_ylabel("altitude (km)")
    ax.set_title("Vol de référence — vue dans le plan de tir (même sens que les vignettes)")
    ax.grid(alpha=0.3)
    legende = ("Flèches : rouge = x corps (nez), vert = y corps (droite), bleu = z corps (bas),\n"
               "jaune = vitesse ; trièdre gris = E, N, U. Attendu : rouge ≡ jaune ; à roulis nul le vert\n"
               "est horizontal, perpendiculaire au plan de tir ; vert et bleu tournent de 90 °/s autour du rouge.")
    fig.text(0.01, 0.01, legende, fontsize=9, color="#333333", va="bottom")
    fig.subplots_adjust(bottom=0.3)
    fig.canvas.draw()
    image = np.asarray(fig.canvas.buffer_rgba())[..., :3].copy()
    plt.close(fig)
    return image


def controle_j1(sortie: Path) -> list[str]:
    """Conventions : trièdres corps/ENU sur l'Aim9 à quatre instants, sans scène."""
    from PIL import Image

    traj, maquette, constats = _lire("CONFIG.yaml")
    traj_euler, maquette_step, constats_euler = _lire("CONFIG_EULER.yaml")
    ecart_att = float(np.degrees(np.max(rot.angle_entre(traj.attitude, traj_euler.attitude))))
    ecart_pos = float(np.max(np.abs(traj.positions - traj_euler.positions)))
    # Le STEP sort de cascadio avec des sommets non fusionnés : on compare les boîtes.
    boite = np.stack([maquette.sommets.min(0), maquette.sommets.max(0)])
    boite_step = np.stack([maquette_step.sommets.min(0), maquette_step.sommets.max(0)])
    ecart_cao = float(np.max(np.abs(boite - boite_step)))

    evenements = {e.nom: e.t for e in traj.evenements}
    t_apo = evenements["Apogée"]
    instants = [(0.5, "rampe"), (evenements["Mach 1"], "Mach 1"),
                (round((evenements["Fin de propulsion"] + t_apo) / 2, 2), "montée balistique"),
                (t_apo, "apogée")]
    vignette = (960, 540)
    vues = [_vue_instant(traj, maquette, t, f"{i}. {nom}", vignette) for i, (t, nom) in enumerate(instants, 1)]
    for i, (vue, (_, nom)) in enumerate(zip(vues, instants), 1):
        Image.fromarray(vue).save(sortie / f"{i}_{nom.replace(' ', '_')}.png")
    ensemble = _vue_ensemble(traj, instants, (2 * vignette[0], 420))
    planche = np.full((2 * vignette[1] + ensemble.shape[0], 2 * vignette[0], 3), 255, np.uint8)
    for i, vue in enumerate(vues):
        y, x = divmod(i, 2)
        planche[y * vignette[1]:(y + 1) * vignette[1], x * vignette[0]:(x + 1) * vignette[0]] = vue[..., :3]
    planche[2 * vignette[1]:, :ensemble.shape[1]] = ensemble[:, :2 * vignette[0]]
    Image.fromarray(planche).save(sortie / "planche_J1.png")

    return [
        "Jalon J1 — conventions (repères, attitude, CAO)",
        "",
        "Images",
        "  planche_J1.png           les 4 instants + vue d'ensemble du vol",
        *(f"  {i}_{nom.replace(' ', '_')}.png" for i, (_, nom) in enumerate(instants, 1)),
        "",
        "À regarder",
        "  - flèche rouge (nez) superposée à la jaune (vitesse) aux 4 instants",
        "  - pente du nez : forte et constante en propulsion, ~0° à l'apogée",
        "  - roulis : la flèche bleue (z corps, ventre) tourne autour du nez d'une vignette à l'autre",
        "  - dôme et canards du côté de la flèche rouge, empennage côté culot",
        "  - E, N, U : U vers le haut ; la fusée monte vers la droite (cap 30°, vue de côté)",
        "",
        "Lecture du même vol par les deux configurations",
        "  CONFIG.yaml (ENU, quaternion, STL) vs CONFIG_EULER.yaml (NED, Euler ZYX, STEP)",
        f"  écart d'attitude max {ecart_att:.2e}°, de position {ecart_pos:.2e} m, de boîte CAO {ecart_cao:.2e} m",
        "",
        "Constats de `cfd-trajcast check CONFIG.yaml`",
        *(f"  {c}" for c in constats),
        "",
        "Constats de `cfd-trajcast check CONFIG_EULER.yaml`",
        *(f"  {c}" for c in constats_euler),
    ]


def controle_j2(sortie: Path) -> list[str]:
    """Premier MP4 : caméra de poursuite, fond uni, tracé du vol, quadrillage au sol."""
    from dataclasses import replace

    from PIL import Image, ImageDraw

    from cfd_trajcast import Film
    from cfd_trajcast.engine.encodage import sonder_video

    film = Film.depuis_yaml(EXEMPLE_DIR / "CONFIG.yaml")
    evenements = {e.nom: e.t for e in film.trajectoire.evenements}
    instants = [(0.5, "rampe"), (evenements["Mach 1"], "Mach 1"),
                (round((evenements["Fin de propulsion"] + evenements["Apogée"]) / 2, 2), "montée balistique"),
                (evenements["Apogée"], "apogée")]
    vues = []
    for i, (t, nom) in enumerate(instants, 1):
        image = film.image(t, sortie / f"{i}_{nom.replace(' ', '_')}.png")
        vues.append(Image.fromarray(image).resize((960, 540), Image.Resampling.LANCZOS))
    import matplotlib
    from PIL import ImageFont

    # La police par défaut de Pillow n'a pas d'accents ; DejaVu vient avec matplotlib.
    police = ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"), 22)
    planche = Image.new("RGB", (1920, 1080), "white")
    dessin = ImageDraw.Draw(planche)
    for i, (vue, (t, nom)) in enumerate(zip(vues, instants)):
        y, x = divmod(i, 2)
        planche.paste(vue, (x * 960, y * 540))
        dessin.text((x * 960 + 14, y * 540 + 10), f"{i + 1}. {nom} — t = {t:.3f} s", fill="black", font=police)
    for x0, y0, x1, y1 in ((959, 0, 960, 1080), (0, 539, 1920, 540)):
        dessin.rectangle((x0, y0, x1, y1), fill="#888888")
    planche.save(sortie / "planche_J2.png")

    film10 = Film(film.trajectoire, film.maquette, video=replace(film.video, duree=10.0, vitesse=None),
                  vue=film.vue)
    r = film10.rendre(sortie / "vol_complet_10s_1080p.mp4")
    plan = film10.plan()
    direction = plan.camera.decalage / np.linalg.norm(plan.camera.decalage, axis=1, keepdims=True)
    saut = float(np.degrees(np.max(np.arccos(np.clip(np.sum(direction[1:] * direction[:-1], axis=1), -1, 1)))))
    info = sonder_video(r.chemin)
    return [
        "Jalon J2 — premier MP4 (caméra de poursuite, fond uni)",
        "",
        "Fichiers",
        "  vol_complet_10s_1080p.mp4  tout le vol (55,5 s) en 10 s de vidéo, 1080p, 30 ips",
        "  planche_J2.png             4 instants rendus par `cfd-trajcast image`, réduits",
        *(f"  {i}_{nom.replace(' ', '_')}.png" for i, (_, nom) in enumerate(instants, 1)),
        "",
        "À regarder",
        "  - la fusée reste centrée, à taille constante (distance auto, cadrage 35 %)",
        "  - la caméra est à 60° à droite de la route, 10° au-dessus : on voit la fusée de 3/4 arrière",
        "  - aucun tressautement de caméra, y compris au départ quasi vertical et à l'apogée",
        "  - le roulis (90 °/s) se voit sur les ailettes ; la caméra, elle, ne roule pas",
        "  - le tracé gris du vol passe par la fusée ; le quadrillage au sol défile au départ",
        "  - pas de sol ni de ciel : ils arrivent au J4 (en altitude, seul le tracé donne le mouvement)",
        "",
        "Vidéo contrôlée par ffmpeg",
        f"  {info.largeur}×{info.hauteur}, {info.ips:g} ips, {info.n_images} images, {info.duree:.2f} s, "
        f"{info.codec} {info.format_pixels}",
        f"  rendu en {r.secondes:.1f} s ({1000 * r.secondes / r.n_images:.0f} ms/image, un seul processus)",
        f"  plus grand pivotement de la caméra d'une image à la suivante : {saut:.2f}°",
        "  (le vol de référence garde un cap constant : le lissage de la route n'y est pas",
        "  sollicité ; il l'est par tests/test_camera.py, et le sera par un vol à virage au J4)",
    ]


def controle_j3(sortie: Path) -> list[str]:
    """Multi-vues : séquence de dispositions, caméras sol/embarquée, télémétrie, habillage."""
    import matplotlib
    from PIL import Image, ImageDraw, ImageFont

    from cfd_trajcast import Film
    from cfd_trajcast.engine.encodage import sonder_video

    film = Film.depuis_yaml(EXEMPLE_DIR / "CONFIG_MULTIVUES.yaml")
    instants = [(1.5, "départ — vue sol seule + titre"), (2.65, "fondu vers la disposition par défaut"),
                (4.2, "médaillons + bandeaux Mach 1 / fin de propulsion"), (20.0, "montée balistique"),
                (36.3, "fondu vers la grille"), (45.0, "grille, après l'apogée")]
    police = ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"), 22)
    planche = Image.new("RGB", (1920, 1620), "white")
    dessin = ImageDraw.Draw(planche)
    for i, (t, nom) in enumerate(instants):
        image = film.image(t, sortie / f"{i + 1}_t{t:g}.png")
        y, x = divmod(i, 2)
        planche.paste(Image.fromarray(image).resize((960, 540), Image.Resampling.LANCZOS), (x * 960, y * 540))
        dessin.text((x * 960 + 14, y * 540 + 506), f"{i + 1}. t = {t:g} s — {nom}", fill="#ffcc00", font=police,
                    stroke_width=2, stroke_fill="black")
    for x0, y0, x1, y1 in ((959, 0, 960, 1620), (0, 539, 1920, 540), (0, 1079, 1920, 1080)):
        dessin.rectangle((x0, y0, x1, y1), fill="#888888")
    planche.save(sortie / "planche_J3.png")

    r = film.rendre(sortie / "vol_multivues_1080p.mp4")
    info = sonder_video(r.chemin)
    return [
        "Jalon J3 — multi-vues, télémétrie, montage (CONFIG_MULTIVUES.yaml)",
        "",
        "Fichiers",
        "  vol_multivues_1080p.mp4   tout le vol en temps réel, 1080p, 30 ips",
        "  planche_J3.png            6 instants : chaque étape de la séquence et ses fondus",
        *(f"  {i + 1}_t{t:g}.png          {nom}" for i, (t, nom) in enumerate(instants)),
        "",
        "À regarder",
        "  - séquence : vue sol seule (0 → 2,5 s), puis poursuite + médaillons, puis grille à 36 s",
        "  - fondus de 0,6 s entre dispositions (pas de saut d'image)",
        "  - caméra sol : zoom qui garde la fusée à taille constante malgré l'éloignement",
        "  - caméra embarquée : roule avec la fusée (voulu) ; le corps occupe le bas de l'image",
        "  - télémétrie : valeurs en français (virgule, espace fine), courbe qui se remplit,",
        "    accélération cinématique ≈ 9,2 g en propulsion puis 1 g (chute libre)",
        "  - bandeaux Mach 1 (3,7 s) et fin de propulsion (4,0 s) empilés au-dessus du logo",
        "  - titre au début, générique (assombri + titre) sur les 3 dernières secondes",
        "",
        "Vidéo contrôlée par ffmpeg",
        f"  {info.largeur}×{info.hauteur}, {info.ips:g} ips, {info.n_images} images, {info.duree:.2f} s, "
        f"{info.codec} {info.format_pixels}",
        f"  rendu en {r.secondes:.1f} s ({1000 * r.secondes / r.n_images:.0f} ms/image, un seul processus)",
    ]


def controle_j3b(sortie: Path) -> list[str]:
    """Retours sur J3 : titre en haut, vue d'ensemble NED en principale, zooms autour."""
    import matplotlib
    from PIL import Image, ImageDraw, ImageFont

    from cfd_trajcast import Film
    from cfd_trajcast.engine.encodage import sonder_video

    film = Film.depuis_yaml(EXEMPLE_DIR / "CONFIG_ENSEMBLE.yaml")
    instants = [(1.0, "départ, titre en haut"), (4.3, "bandeaux Mach 1 / fin de propulsion"),
                (25.0, "montée balistique"), (40.565, "apogée"), (54.0, "générique")]
    police = ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"), 22)
    planche = Image.new("RGB", (1920, 1620), "white")
    dessin = ImageDraw.Draw(planche)
    for i, (t, nom) in enumerate(instants):
        image = film.image(t, sortie / f"{i + 1}_t{t:g}.png")
        y, x = divmod(i, 2)
        planche.paste(Image.fromarray(image).resize((960, 540), Image.Resampling.LANCZOS), (x * 960, y * 540))
        dessin.text((x * 960 + 14, y * 540 + 506), f"{i + 1}. t = {t:g} s — {nom}", fill="#ffcc00",
                    font=police, stroke_width=2, stroke_fill="black")
    planche.save(sortie / "planche_J3b.png")
    r = film.rendre(sortie / "vol_ensemble_1080p.mp4")
    info = sonder_video(r.chemin)
    return [
        "Jalon J3b — retours sur J3 (CONFIG_ENSEMBLE.yaml)",
        "",
        "Fichiers",
        "  vol_ensemble_1080p.mp4    tout le vol en temps réel, 1080p, 30 ips",
        "  planche_J3b.png           5 instants",
        "",
        "À regarder",
        "  - titre en haut de l'image : il ne cache plus la fusée",
        "  - vue d'ensemble (principale) : repère NED gradué en mètres (Nord, Est, Bas — le Bas est",
        "    négatif au-dessus du sol), trajectoire complète en gris, partie parcourue en orange,",
        "    trace au sol, événements nommés, fusée agrandie (facteur affiché en bas à droite)",
        "    qui avance et s'oriente ; caméra fixe, cadrage ajusté aux 8 coins de la boîte",
        "  - colonne haute à gauche : ce vol fait 7,3 km de haut pour 2,2 km de portée",
        "  - zooms au milieu : embarquée, poursuite, sol ; télémétrie à droite, logo au-dessus",
        "  - bandeaux d'événements en haut à gauche de la vue d'ensemble",
        "",
        "Vidéo contrôlée par ffmpeg",
        f"  {info.largeur}×{info.hauteur}, {info.ips:g} ips, {info.n_images} images, {info.duree:.2f} s, "
        f"{info.codec} {info.format_pixels}",
        f"  rendu en {r.secondes:.1f} s ({1000 * r.secondes / r.n_images:.0f} ms/image, un seul processus)",
    ]


def controle_j4(sortie: Path) -> list[str]:
    """Scène soignée : sobre contre conférence, puis le vol à virage complet."""
    from dataclasses import replace

    import matplotlib
    from PIL import Image, ImageDraw, ImageFont

    from cfd_trajcast import Film
    from cfd_trajcast.data.configuration import PRESETS_STYLE, charger_configuration
    from cfd_trajcast.engine.encodage import sonder_video

    police = ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"), 22)
    cfg = charger_configuration(EXEMPLE_DIR / "CONFIG_MULTIVUES.yaml")
    instants = [(4.2, "médaillons + bandeaux"), (20.0, "montée balistique"), (45.0, "grille, après l'apogée")]
    planche = Image.new("RGB", (1920, 540 * len(instants)), "white")
    dessin = ImageDraw.Draw(planche)
    for x, preset in enumerate(("sobre", "conference")):
        film = Film.depuis_configuration(replace(cfg, style=PRESETS_STYLE[preset]))
        for y, (t, nom) in enumerate(instants):
            image = Image.fromarray(film.image(t))
            image.save(sortie / f"{preset}_t{t:g}.png")
            planche.paste(image.resize((960, 540), Image.Resampling.LANCZOS), (x * 960, y * 540))
            dessin.text((x * 960 + 14, y * 540 + 506), f"{preset} — t = {t:g} s — {nom}", fill="#ffcc00",
                        font=police, stroke_width=2, stroke_fill="black")
    planche.save(sortie / "planche_J4_sobre_conference.png")

    virage = Film.depuis_yaml(EXEMPLE_DIR / "CONFIG_VIRAGE.yaml")
    images_virage = [(1.0, "départ, caméra de face"), (4.0, "ralenti ×4, traînée"), (14.0, "virage"),
                     (40.5, "apogée, ralenti ×2")]
    planche_v = Image.new("RGB", (1920, 1080), "white")
    dessin = ImageDraw.Draw(planche_v)
    for i, (t, nom) in enumerate(images_virage):
        image = Image.fromarray(virage.image(t, sortie / f"virage_t{t:g}.png"))
        y, x = divmod(i, 2)
        planche_v.paste(image.resize((960, 540), Image.Resampling.LANCZOS), (x * 960, y * 540))
        dessin.text((x * 960 + 14, y * 540 + 506), f"t = {t:g} s — {nom}", fill="#ffcc00", font=police,
                    stroke_width=2, stroke_fill="black")
    planche_v.save(sortie / "planche_J4_virage.png")
    r = virage.rendre(sortie / "vol_virage_1080p.mp4")
    info = sonder_video(r.chemin)
    plan = virage.plan()
    poursuite = np.diff(plan.t_vol) * plan.ips
    return [
        "Jalon J4 — scène soignée, caméras orbite / images clés, ralentis",
        "",
        "Fichiers",
        "  planche_J4_sobre_conference.png  CONFIG_MULTIVUES aux instants du J3 : sobre | conférence",
        "  planche_J4_virage.png            CONFIG_VIRAGE (conférence) : 4 instants",
        "  vol_virage_1080p.mp4             tout le vol à virage, 1080p, 30 ips, avec ralentis",
        "",
        "À regarder",
        "  - conférence : ciel en dégradé, terrain texturé (tuile raccordable de 400 m), soleil,",
        "    traînée qui s'élargit et s'efface, arrêtée à « Fin de propulsion »",
        "  - sobre : identique au J3 (préréglage par défaut, rien ne change pour les anciens fichiers)",
        "  - caméra « cinema » à images clés : de face au départ, de côté pendant le virage,",
        "    à l'horizontale à l'apogée, par-dessous à la fin — transitions sans à-coup",
        "  - orbite en médaillon : un tour en 18 s de vidéo",
        "  - ralentis : ×4 autour de Mach 1 / fin de propulsion, ×2 à l'apogée, rampes de 0,5 s",
        "  - télémétrie : la route passe de 30° à 100° pendant le virage",
        "",
        "Vidéo contrôlée par ffmpeg",
        f"  {info.largeur}×{info.hauteur}, {info.ips:g} ips, {info.n_images} images, {info.duree:.2f} s "
        f"(vol de {plan.t_vol[-1] - plan.t_vol[0]:.1f} s), {info.codec} {info.format_pixels}",
        f"  vitesse de lecture de {poursuite.min():.2f} à {poursuite.max():.2f} s de vol par seconde",
        f"  rendu en {r.secondes:.1f} s ({1000 * r.secondes / r.n_images:.0f} ms/image, un seul processus)",
    ]


def controle_j4b(sortie: Path) -> list[str]:
    """Jets par phases et scénarios génériques : une planche et une vidéo 1080p par scénario."""
    import matplotlib
    from PIL import Image, ImageDraw, ImageFont

    from cfd_trajcast import Film
    from cfd_trajcast.engine.encodage import sonder_video

    police = ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"), 22)
    scenarios = {
        "AVION_MANOEUVRES": [(20.0, "roulage, postcombustion"), (31.0, "rotation (ralenti)"),
                             (90.0, "virage à 60°"), (120.0, "boucle, postcombustion"),
                             (148.5, "tonneau (ralenti)"), (165.0, "descente en virage")],
        "AVION_PANNE": [(10.0, "croisière"), (17.0, "panne : feu, fumée noire"), (55.0, "grand virage"),
                        (78.0, "perte de contrôle"), (90.0, "spirale, orbite"), (105.0, "fin de spirale")],
        "FUSEE_BI_ETAGE": [(1.5, "étage 1 : poudre"), (3.5, "fin d'étage 1 (ralenti)"),
                           (5.6, "allumage étage 2"), (9.0, "étage 2 : liquide"), (30.0, "vol balistique"),
                           (58.0, "point culminant")],
    }
    lignes = ["Jalon J4b — jets par phases, scénarios génériques (01_EXEMPLE/SCENARIOS)", ""]
    for nom, instants in scenarios.items():
        film = Film.depuis_yaml(EXEMPLE_DIR / "SCENARIOS" / f"{nom}.yaml")
        planche = Image.new("RGB", (1920, 1620), "white")
        dessin = ImageDraw.Draw(planche)
        for i, (t, legende) in enumerate(instants):
            image = Image.fromarray(film.image(t))
            y, x = divmod(i, 2)
            planche.paste(image.resize((960, 540), Image.Resampling.LANCZOS), (x * 960, y * 540))
            dessin.text((x * 960 + 14, y * 540 + 506), f"t = {t:g} s — {legende}", fill="#ffcc00", font=police,
                        stroke_width=2, stroke_fill="black")
        planche.save(sortie / f"planche_{nom}.png")
        r = film.rendre(sortie / f"{nom}_1080p.mp4")
        info = sonder_video(r.chemin)
        lignes += [
            f"{nom}",
            f"  planche_{nom}.png, {nom}_1080p.mp4",
            f"  {info.largeur}×{info.hauteur}, {info.ips:g} ips, {info.n_images} images, {info.duree:.1f} s, "
            f"{info.codec} {info.format_pixels} ; rendu en {r.secondes:.0f} s ({1000 * r.secondes / r.n_images:.0f} ms/image)",
            "",
        ]
    lignes += [
        "À regarder",
        "  - flammes : évasées, cœur blanc, dégradé de couleur, scintillement ; disques de Mach (étage 2,",
        "    postcombustion) ; fumée qui s'ouvre en cône derrière la flamme et dérive en vieillissant",
        "  - phases : postcombustion ↔ réacteur sec (avion), poudre → liquide (fusée), réacteur → panne",
        "    (feu vacillant, fumée noire) — chaque fumée garde la couleur de sa phase d'émission",
        "  - généricité : avion au roulage (sol abaissé de 1,6 m), boucle, tonneau, spirale ; vue",
        "    d'ensemble « maquette agrandie » ; télémétrie avion (kt, ft, g, inclinaison, pente, cap)",
        "  - anticrénelage SSAA (préréglage conférence) : bords d'ailes et de fumée lisses",
    ]
    return lignes


def _planche(film, instants: list[tuple[float, str]], chemin: Path) -> None:  # type: ignore[no-untyped-def]
    import matplotlib
    from PIL import Image, ImageDraw, ImageFont

    police = ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"), 22)
    planche = Image.new("RGB", (1920, 540 * ((len(instants) + 1) // 2)), "white")
    dessin = ImageDraw.Draw(planche)
    for i, (t, legende) in enumerate(instants):
        image = Image.fromarray(film.image(t))
        y, x = divmod(i, 2)
        planche.paste(image.resize((960, 540), Image.Resampling.LANCZOS), (x * 960, y * 540))
        dessin.text((x * 960 + 14, y * 540 + 506), f"t = {t:g} s — {legende}", fill="#ffcc00", font=police,
                    stroke_width=2, stroke_fill="black")
    planche.save(chemin)


def controle_j5(sortie: Path) -> list[str]:
    """RocketPy (vidéo + planche), cache, débit série / parallèle, scénarios avion avec l'Aim9."""
    from dataclasses import replace

    from cfd_trajcast import Film
    from cfd_trajcast.engine.encodage import sonder_video

    lignes = ["Jalon J5 — RocketPy, cache, rendu parallèle par tronçons", ""]

    # 1. RocketPy : simulation exécutée puis relue du cache.
    config = EXEMPLE_DIR / "ROCKETPY" / "CONFIG_ROCKETPY.yaml"
    cfg = charger_configuration(config)
    t0 = time.perf_counter()
    cfg.trajectoire.charger(utiliser_cache=False)
    t_sim = time.perf_counter() - t0
    cfg.trajectoire.charger()  # écrit le cache
    t0 = time.perf_counter()
    traj = cfg.trajectoire.charger()
    t_cache = time.perf_counter() - t0
    film = Film.depuis_configuration(cfg)
    _planche(film, [(0.2, "sur la rampe"), (2.0, "propulsion"), (4.5, "fin de propulsion"),
                    (12.0, "vol balistique"), (26.5, "apogée, extracteur"), (44.0, "début de descente")],
             sortie / "planche_ROCKETPY.png")
    r = film.rendre(sortie / "ROCKETPY_1080p.mp4")
    info = sonder_video(r.chemin)
    lignes += [
        "RocketPy — 01_EXEMPLE/ROCKETPY/CONFIG_ROCKETPY.yaml (fusée-sonde générique, maquette Aim9)",
        f"  simulation RocketPy : {t_sim:.2f} s ; relue du cache : {t_cache:.2f} s",
        f"  {len(traj.t)} échantillons, {traj.duree:.1f} s de vol ; événements : "
        + ", ".join(f"{e.nom} ({e.t:.2f} s)" for e in traj.evenements),
        f"  planche_ROCKETPY.png, ROCKETPY_1080p.mp4 : {info.largeur}×{info.hauteur}, {info.n_images} images, "
        f"{info.duree:.1f} s ; rendu en {r.secondes:.0f} s ({r.ms_par_image:.0f} ms/image, "
        f"{r.processus} processus, {r.troncons} tronçons)",
        "",
    ]

    # 2. Débit : le même extrait 1080p en série puis en parallèle, deux préréglages x264.
    lignes += ["Débit — AVION_MANOEUVRES 1080p, vol 40 → 80 s (4 vues + télémétrie, préréglage conférence)",
               f"  machine : {os.cpu_count()} cœurs, {platform.processor() or platform.machine()}"]
    base = Film.depuis_yaml(EXEMPLE_DIR / "SCENARIOS" / "AVION_MANOEUVRES.yaml")
    essais = [(1, "medium"), (4, "medium"), (6, "medium"), (6, "veryfast")]
    for n, preset in essais:
        base.video = replace(base.video, preset=preset)
        res = base.rendre(sortie / f"debit_{n}_{preset}.mp4", de=40.0, a=80.0, processus=n)
        taille = (sortie / f"debit_{n}_{preset}.mp4").stat().st_size / 1e6
        lignes.append(f"  {n} processus, x264 {preset:8s} : {res.n_images} images en {res.secondes:5.1f} s → "
                      f"{1000 / res.ms_par_image:5.1f} images/s ({res.ms_par_image:.0f} ms/image), {taille:.1f} Mo")
        (sortie / f"debit_{n}_{preset}.mp4").unlink()
    lignes.append("")

    # 3. Scénarios d'avion, maquette Aim9 (demande utilisateur après J4b).
    scenarios = {
        "AVION_MANOEUVRES": [(20.0, "roulage, postcombustion"), (31.0, "rotation (ralenti)"),
                             (90.0, "virage à 60°"), (120.0, "boucle, postcombustion"),
                             (148.5, "tonneau (ralenti)"), (165.0, "descente en virage")],
        "AVION_PANNE": [(10.0, "croisière"), (17.0, "panne : feu, fumée noire"), (55.0, "grand virage"),
                        (78.0, "perte de contrôle"), (90.0, "spirale, orbite"), (105.0, "fin de spirale")],
    }
    for nom, instants in scenarios.items():
        film = Film.depuis_yaml(EXEMPLE_DIR / "SCENARIOS" / f"{nom}.yaml")
        _planche(film, instants, sortie / f"planche_{nom}.png")
        r = film.rendre(sortie / f"{nom}_1080p.mp4")
        lignes.append(f"{nom} (Aim9) : planche_{nom}.png, {nom}_1080p.mp4 — {r.n_images} images en "
                      f"{r.secondes:.0f} s ({r.ms_par_image:.0f} ms/image, {r.processus} processus)")
    lignes += [
        "",
        "À regarder",
        "  - ROCKETPY : bandeaux d'événements venus de RocketPy (rampe, fin de propulsion, apogée,",
        "    extracteur), télémétrie lue dans le Flight (Mach, pression dynamique, incidence, marge",
        "    statique), nez dans l'axe de la vitesse pendant la propulsion",
        "  - vidéos rendues en parallèle : aucune saute ni image dupliquée aux raccords de tronçons",
        "  - scénarios d'avion avec la CAO Aim9 : cadrages, caméra embarquée, roulage au-dessus du sol",
    ]
    return lignes


def controle_j6(sortie: Path) -> list[str]:
    """4K de nuit (vidéo complète), moteur Blender (extrait), comparaison PyVista / Blender.

    À lancer avec un Python qui a bpy (3.13 pour bpy 5.x) ; sans lui, la partie Blender
    est sautée et le manifeste le dit.
    """
    import matplotlib
    from PIL import Image, ImageDraw, ImageFont

    from cfd_trajcast import Film
    from cfd_trajcast.data.configuration import ConfigMoteur
    from cfd_trajcast.engine.encodage import sonder_video
    from cfd_trajcast.engine.rendu.blender import bpy_disponible

    lignes = ["Jalon J6 — 4K, préréglage nuit, moteur Blender", ""]
    scenarios = EXEMPLE_DIR / "SCENARIOS"
    instants = [(0.6, "allumage étage 1"), (3.2, "fin d'étage 1 (ralenti)"), (5.6, "allumage étage 2"),
                (9.0, "étage 2"), (30.0, "vol balistique"), (58.0, "point culminant")]

    # 1. La vidéo 4K de nuit, complète, rendue en parallèle.
    film = Film.depuis_yaml(scenarios / "FUSEE_NUIT_4K.yaml")
    _planche(film, instants, sortie / "planche_NUIT_4K.png")
    r = film.rendre(sortie / "FUSEE_NUIT_4K.mp4")
    info = sonder_video(r.chemin)
    lignes += [
        "FUSEE_NUIT_4K.yaml — préréglage nuit, 3840×2160, 3 vues + télémétrie",
        f"  planche_NUIT_4K.png ; FUSEE_NUIT_4K.mp4 : {info.largeur}×{info.hauteur}, {info.ips:g} ips, "
        f"{info.n_images} images, {info.duree:.1f} s, {info.codec} {info.format_pixels}",
        f"  rendu en {r.secondes:.0f} s : {r.ms_par_image:.0f} ms/image, {1000 / r.ms_par_image:.1f} images/s "
        f"({r.processus} processus, {r.troncons} tronçons), {r.chemin.stat().st_size / 1e6:.0f} Mo",
        "",
    ]

    # 2. Blender : un extrait, et la même scène que PyVista, côte à côte.
    if not bpy_disponible():
        lignes += ["Blender : bpy absent dans ce Python — partie sautée (pip install bpy, Python 3.13)", ""]
    else:
        from cfd_trajcast.engine.rendu.blender import importer_bpy

        bpy = importer_bpy()
        blender = Film.depuis_yaml(scenarios / "FUSEE_NUIT_BLENDER.yaml")
        # Un processus bpy pèse plus lourd que l'estimation de processus_auto : 2, explicitement.
        r = blender.rendre(sortie / "FUSEE_NUIT_BLENDER.mp4", processus=2)
        lignes += [
            f"FUSEE_NUIT_BLENDER.yaml — bpy {bpy.app.version_string}, EEVEE, {blender.moteur.echantillons} échantillons",
            f"  FUSEE_NUIT_BLENDER.mp4 : vol 0 → 8 s, {r.n_images} images 1080p en {r.secondes:.0f} s "
            f"({r.ms_par_image:.0f} ms/image, {r.processus} processus)",
        ]
        pyvista_1080 = Film.depuis_yaml(scenarios / "FUSEE_NUIT_BLENDER.yaml")
        pyvista_1080.moteur = ConfigMoteur(type="pyvista")
        police = ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts/ttf/DejaVuSans.ttf"), 22)
        comparaison = [(0.6, "allumage"), (3.2, "fin d'étage 1"), (5.6, "allumage étage 2"), (7.5, "étage 2")]
        planche = Image.new("RGB", (1920, 540 * len(comparaison)), "white")
        dessin = ImageDraw.Draw(planche)
        for i, (t, legende) in enumerate(comparaison):
            for x, (f, nom) in enumerate(((pyvista_1080, "PyVista"), (blender, "Blender EEVEE"))):
                image = Image.fromarray(f.image(t))
                planche.paste(image.resize((960, 540), Image.Resampling.LANCZOS), (x * 960, i * 540))
                dessin.text((x * 960 + 14, i * 540 + 506), f"{nom} — t = {t:g} s, {legende}", fill="#ffcc00",
                            font=police, stroke_width=2, stroke_fill="black")
        planche.save(sortie / "comparaison_PYVISTA_BLENDER.png")
        lignes += ["  comparaison_PYVISTA_BLENDER.png : mêmes instants, PyVista à gauche, Blender à droite", ""]

    lignes += [
        "À regarder",
        "  - 4K : netteté des bords (SSAA), textes et télémétrie à l'échelle, aucun élément à la taille 1080p",
        "  - nuit : étoiles fixes dans le ciel quand la caméra tourne, cachées par la fumée et le sol ;",
        "    halo autour des flammes ; culot, fumée et sol éclairés en orange au décollage ; lune bleutée",
        "  - bandeau « Allumage étage 1 » sous le titre au début (il le chevauchait au J4b)",
        "  - Blender : ombres, peinture, flammes émissives ; même ciel et mêmes couleurs que PyVista",
    ]
    return lignes


def controle_g(sortie: Path) -> list[str]:
    """Interface (G0–G6) : fenêtre à trois instants, vue VTK, assistant, exports."""
    from cfd_trajcast.gui import application

    app = application()
    from PyQt5.QtCore import QSettings

    # Réglages de la fenêtre écrits dans le dossier du contrôle, pas dans ~/.config de l'utilisateur.
    for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
        QSettings.setPath(fmt, QSettings.UserScope, str(sortie / "reglages"))
    from cfd_trajcast.gui.assistant import AssistantCsv
    from cfd_trajcast.gui.fenetre import FenetrePrincipale

    def attendre(n: int = 30) -> None:
        for _ in range(n):
            app.processEvents()
            time.sleep(0.02)

    lignes = [f"Jalon G — interface interactive (cfd-trajcast gui), plateforme Qt « {app.platformName()} »", ""]
    f = FenetrePrincipale()
    f.resize(1800, 1050)
    f.show()
    f.ouvrir(EXEMPLE_DIR / "CONFIG_GUI.yaml")
    f.telemetrie.cocher(["altitude", "incidence", "derapage", "vitesse_air", "Xcg", "masse"])
    poses = [(3.0, {"corps", "ned"}, False, "propulsion : CDG qui avance, corps et NED"),
             (12.0, {"corps", "ned", "aero", "trajectoire"}, True, "les quatre repères et le vent"),
             (40.565, {"aero", "trajectoire"}, True, "apogée : repères aérodynamique et trajectoire")]
    for t, reperes, vent, quoi in poses:
        for nom, case in f.affichage.reperes.items():
            case.setChecked(nom in reperes)
        f.affichage.vent.setChecked(vent)
        f.navigation.aller(t)
        attendre()
        nom = f"fenetre_t{t:05.1f}.png".replace(".", "_", 1)
        f.grab().save(str(sortie / nom))
        lignes.append(f"  {nom} : t = {t:g} s, {quoi}")
    f.vent.raise_()
    attendre()
    f.grab().save(str(sortie / "fenetre_dock_vent.png"))
    lignes.append("  fenetre_dock_vent.png : onglet Vent (hodographe, vent vertical, point courant)")
    f.vue.exporter(sortie / "export_vue.pdf")
    from cfd_trajcast.engine.courbes import exporter_figure

    exporter_figure(f.telemetrie.canevas.figure, sortie / "export_courbes.pdf")
    lignes.append("  export_vue.pdf, export_courbes.pdf : exports de la vue et des courbes")
    f.zoomer("engin")
    f.navigation.aller(25.0)
    attendre()
    f.grab().save(str(sortie / "fenetre_zoom_engin.png"))
    f.vue.exporter(sortie / "export_vue_zoom.pdf")
    lignes.append(f"  fenetre_zoom_engin.png, export_vue_zoom.pdf : t = 25 s, « Cadrer l'engin » "
                  f"(zoom × {f.vue.zoom:.1f}), boîte cubique centrée sur le CDG, qui le suit")
    f.zoomer("entier")
    if f.choisir_moteur("vtk"):
        f.navigation.aller(12.0)
        attendre()
        f.grab().save(str(sortie / "fenetre_vtk.png"))
        lignes.append(f"  fenetre_vtk.png : même instant, vue VTK ({f._sonde[1] if f._sonde else ''})")
        f.zoomer("engin")
        f.navigation.aller(25.0)
        attendre()
        f.grab().save(str(sortie / "fenetre_vtk_zoom_engin.png"))
        lignes.append("  fenetre_vtk_zoom_engin.png : t = 25 s, « Cadrer l'engin » en VTK")
    else:
        lignes.append(f"  (vue VTK indisponible ici : {f._sonde[1] if f._sonde else '?'})")
    # Libérer la fenêtre (et sa vue VTK) maintenant, pas au hasard d'un ramasse-miettes plus tard :
    # un QtInteractor détruit après coup, pendant un import de vtk, fait planter le processus.
    import gc

    f.close()
    f.deleteLater()
    attendre(5)
    del f
    gc.collect()
    a = AssistantCsv(csv=EXEMPLE_DIR / "vol_vent_cdg.csv")
    a.show()
    a.next()
    attendre(10)
    a.grab().save(str(sortie / "assistant_trajectoire.png"))
    a.next()
    a.next()
    attendre(10)
    a.grab().save(str(sortie / "assistant_vent_cdg.png"))
    a.close()
    lignes += ["  assistant_trajectoire.png, assistant_vent_cdg.png : pages préremplies de l'assistant CSV", "",
               "À regarder",
               "  - la maquette glisse autour du CDG (t = 3 s) : le CDG reste sur la trajectoire",
               "  - repères au CDG : couleurs de la légende, axes nommés, NED vertical vers le bas",
               "  - flèches de vent qui tournent avec l'altitude ; ascendant visible vers 2 500 m",
               "  - courbes : curseur à l'instant courant, valeurs de la liste égales aux courbes",
               "  - VTK : même scène, même repère, image non miroir (Est, Nord, haut direct)"]
    return lignes


JALONS = {"G": controle_g, "J1": controle_j1, "J2": controle_j2, "J3": controle_j3, "J3b": controle_j3b, "J4": controle_j4,
          "J4b": controle_j4b, "J5": controle_j5, "J6": controle_j6}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--jalon", required=True, choices=sorted(JALONS))
    args = parser.parse_args()
    sortie = ICI / args.jalon
    sortie.mkdir(parents=True, exist_ok=True)
    debut = time.perf_counter()
    lignes = JALONS[args.jalon](sortie)
    import pyvista as pv
    import vtk

    lignes += [
        "",
        f"Généré le {time.strftime('%Y-%m-%d %H:%M')} en {time.perf_counter() - debut:.1f} s",
        f"cfd-trajcast {__version__}, Python {platform.python_version()}, pyvista {pv.__version__}, "
        f"vtk {vtk.vtkVersion.GetVTKVersion()}, DISPLAY={os.environ.get('DISPLAY', '')!r}",
    ]
    (sortie / "MANIFESTE.txt").write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print("\n".join(lignes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
