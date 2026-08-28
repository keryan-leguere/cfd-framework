#!/usr/bin/env python3
"""Génère les figures d'exemple livrées avec cfd-plot-digitizer.

Ces images ne servent qu'à la démonstration et aux essais : elles imitent des
tracés dont on ne possède plus les données (rapport scanné, article, notice
constructeur), c'est-à-dire le cas d'usage même de l'outil.

    python3 exemples/generer_exemples.py

Nécessite matplotlib. Les valeurs de référence sont écrites à côté de chaque
figure pour pouvoir mesurer l'erreur de digitalisation.
"""
import json
import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ICI = pathlib.Path(__file__).resolve().parent


def en_indice_pixel(x_ecran, y_ecran, hauteur):
    """Coordonnées écran matplotlib -> indices de pixels de l'image.

    Deux conventions se croisent ici, et les confondre coûte un demi-pixel
    systématique sur toute mesure d'exactitude :

      - matplotlib repère l'écran depuis le coin BAS-gauche, l'image se lit
        depuis le coin HAUT-gauche : d'où l'inversion de l'ordonnée ;
      - une coordonnée écran désigne un BORD de pixel, alors qu'un indice de
        pixel en désigne le CENTRE. Le pixel d'indice 0 occupe [0, 1] en
        coordonnées écran, son centre vaut donc 0.5 : d'où le retrait de 0.5.
    """
    return x_ecran - 0.5, (hauteur - y_ecran) - 0.5


def ancres(fig, ax, points, log_x=False, log_y=False):
    """Position pixel exacte de quatre valeurs connues des axes.

    Ces ancres donnent la calibration « parfaite » : elles permettent de mesurer
    l'erreur de l'outil seule, sans y mêler l'imprécision du pointage humain.
    """
    hauteur = fig.canvas.get_width_height()[1]
    sortie = {"logX": log_x, "logY": log_y, "reperes": {}}
    for cle, (x, y, valeur) in points.items():
        px, py = en_indice_pixel(*ax.transData.transform((x, y)), hauteur)
        sortie["reperes"][cle] = {"px": float(px), "py": float(py),
                                  "valeur": float(valeur)}
    return sortie


def cadres(fig, ax, legende):
    """Rectangles utiles en pixels image : zone de tracé et boîte de légende.

    La légende est le piège classique de la digitalisation automatique : elle
    contient des segments de la couleur EXACTE des courbes. La livrer permet à
    la suite de tests d'exercer l'exclusion de zone plutôt que de la contourner
    avec des coordonnées choisies à la main.
    """
    hauteur = fig.canvas.get_width_height()[1]

    def en_pixels(bbox):
        x0, y1 = en_indice_pixel(bbox.x0, bbox.y0, hauteur)
        x1, y0 = en_indice_pixel(bbox.x1, bbox.y1, hauteur)
        return {"x0": float(x0), "x1": float(x1), "y0": float(y0), "y1": float(y1)}

    return {
        "trace": en_pixels(ax.patch.get_window_extent()),
        "legende": en_pixels(legende.get_window_extent()),
        # Bornes des axes : servent à normaliser l'erreur de digitalisation.
        "limites": {"x": list(ax.get_xlim()), "y": list(ax.get_ylim()),
                    "logX": ax.get_xscale() == "log",
                    "logY": ax.get_yscale() == "log"},
    }


def polaire():
    """Trois polaires Cz(Cx) — axes linéaires, trois couleurs franches."""
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)

    cz = np.linspace(-0.4, 1.6, 400)
    couleurs = {"Re = 3e6": "#c1121f", "Re = 6e6": "#1d3557", "Re = 9e6": "#2a9d8f"}
    reference = {}
    for i, (nom, couleur) in enumerate(couleurs.items()):
        cx = 0.0085 - 0.0008 * i + cz ** 2 / (np.pi * 7.5 * 0.86)
        ax.plot(cx, cz, color=couleur, linewidth=2.0, label=nom)
        reference[nom] = {"x": cx.tolist(), "y": cz.tolist()}

    ax.set_xlabel("Cx  [-]")
    ax.set_ylabel("Cz  [-]")
    ax.set_title("Polaire — profil NACA 63-412")
    ax.grid(True, color="#cccccc", linewidth=0.6)
    ax.set_xlim(0, 0.12)
    ax.set_ylim(-0.5, 1.8)
    legende = ax.legend(loc="lower right", framealpha=1.0)
    fig.tight_layout()
    fig.canvas.draw()
    cadre = cadres(fig, ax, legende)
    cal = ancres(fig, ax, {
        "x1": (0.02, 0.0, 0.02), "x2": (0.10, 0.0, 0.10),
        "y1": (0.0, 0.0, 0.0), "y2": (0.0, 1.5, 1.5),
    })
    fig.savefig(ICI / "exemple_polaire.png")
    plt.close(fig)
    return {"calibration": cal, "courbes": reference, "cadres": cadre,
            "couleurs": {n: c for n, c in couleurs.items()}}


def convergence():
    """Résidus en échelle semi-log — vérifie l'axe logarithmique."""
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)

    it = np.arange(1, 2001)
    reference = {}
    for nom, couleur, tau in (("continuite", "#c1121f", 320.0),
                              ("Ux", "#1d3557", 240.0),
                              ("k", "#e07a00", 400.0)):
        res = 1e-1 * np.exp(-it / tau) + 1e-7
        ax.semilogy(it, res, color=couleur, linewidth=1.8, label=nom)
        reference[nom] = {"x": it.tolist(), "y": res.tolist()}

    ax.set_xlabel("Itérations")
    ax.set_ylabel("Résidu initial")
    ax.set_title("Convergence — RANS stationnaire")
    ax.grid(True, which="both", color="#cccccc", linewidth=0.6)
    ax.set_xlim(0, 2000)
    ax.set_ylim(1e-8, 1e0)
    legende = ax.legend(loc="upper right", framealpha=1.0)
    fig.tight_layout()
    fig.canvas.draw()
    cadre = cadres(fig, ax, legende)
    cal = ancres(fig, ax, {
        "x1": (500, 1e-4, 500), "x2": (1500, 1e-4, 1500),
        "y1": (0, 1e-6, 1e-6), "y2": (0, 1e-2, 1e-2),
    }, log_y=True)
    fig.savefig(ICI / "exemple_convergence.png")
    plt.close(fig)
    return {"calibration": cal, "courbes": reference, "cadres": cadre,
            "couleurs": {"continuite": "#c1121f", "Ux": "#1d3557", "k": "#e07a00"}}


def traits():
    """Trois courbes NOIRES distinguées par leur seul tracé.

    Le cas des planches en noir et blanc, et la raison d'être du tri par type de
    trait : ici la couleur ne distingue rien du tout, les trois courbes étant
    rigoureusement identiques de ce point de vue.
    """
    fig, ax = plt.subplots(figsize=(6.4, 4.8), dpi=100)

    x = np.linspace(0, 10, 500)
    styles = {"continu": "-", "tirets": "--", "pointille": ":"}
    reference = {}
    for i, (nom, style) in enumerate(styles.items()):
        y = 1.0 - 0.08 * (i + 1) * x + 0.004 * (i + 1) * x ** 2
        ax.plot(x, y, style, color="#101010", linewidth=1.8, label=nom)
        reference[nom] = {"x": x.tolist(), "y": y.tolist()}

    ax.set_xlabel("x  [-]")
    ax.set_ylabel("y  [-]")
    ax.set_title("Trois tracés, une seule couleur")
    ax.grid(True, color="#cccccc", linewidth=0.6)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 1.1)
    legende = ax.legend(loc="upper right", framealpha=1.0)
    fig.tight_layout()
    fig.canvas.draw()
    cadre = cadres(fig, ax, legende)
    cal = ancres(fig, ax, {
        "x1": (2, 0.0, 2), "x2": (8, 0.0, 8),
        "y1": (0, 0.2, 0.2), "y2": (0, 1.0, 1.0),
    })
    fig.savefig(ICI / "exemple_traits.png")
    plt.close(fig)
    return {"calibration": cal, "courbes": reference, "cadres": cadre,
            "couleurs": {nom: "#101010" for nom in styles},
            "styles": {"continu": "continu", "tirets": "tirets",
                       "pointille": "pointillé"}}


def main():
    ref = {"exemple_polaire.png": polaire(),
           "exemple_convergence.png": convergence(),
           "exemple_traits.png": traits()}
    with open(ICI / "reference.json", "w", encoding="utf-8") as f:
        json.dump(ref, f)
    for chemin in sorted(ICI.glob("*.png")):
        print("%-28s %6.1f ko" % (chemin.name, chemin.stat().st_size / 1024))


if __name__ == "__main__":
    main()
