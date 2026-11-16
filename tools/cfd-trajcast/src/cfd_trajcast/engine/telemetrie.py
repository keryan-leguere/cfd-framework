"""Panneau de télémétrie animé — le seul module qui importe matplotlib.

Une rangée par grandeur : libellé, valeur courante en grand, et une courbe du vol
entier (pâle) que la partie déjà parcourue repasse en couleur, avec un point à
l'instant courant. Le fond (axes, courbes pâles, libellés) est dessiné une fois ;
chaque image ne redessine que les éléments animés (*blitting*), ce qui coûte
quelques millisecondes.

Grandeurs (``telemetrie.grandeurs``) : n'importe quelle **colonne** de la
trajectoire (valeur × ``facteur``, unité affichée telle que déclarée), ou une
grandeur **calculée**, en SI avant conversion d'affichage :

* ``altitude`` — cote ENU au-dessus de la rampe ;
* ``vitesse`` — norme de la vitesse (dérivée des positions) ;
* ``mach`` — vitesse / célérité du son ISA à cette cote (vent nul) ;
* ``acceleration`` — norme de l'accélération **cinématique** (dérivée seconde des
  positions ; pesanteur non retranchée, ce n'est pas le facteur de charge) ;
* ``incidence_totale`` — angle entre l'axe du nez et la vitesse (vent nul) ;
* ``facteur_de_charge`` — force spécifique ressentie, ‖a − g‖ (1 g au repos, 0 en chute libre) ;
* ``cap``, ``pente`` — direction de la vitesse (route, depuis le Nord) et son inclinaison ;
* ``lacet``, ``tangage``, ``roulis`` — angles d'Euler ZYX de l'attitude par rapport au NED.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.reperes import matrice_vers_enu
from cfd_trajcast.data.configuration import ConfigTelemetrie
from cfd_trajcast.data.trajectoire import Trajectoire

__all__ = ["G0", "PanneauTelemetrie", "Serie", "chemin_police", "formater", "series"]

Tableau = NDArray[np.float64]

G0 = 9.80665
#: Séparateur de milliers et espace avant l'unité, à la française.
ESPACE_FINE = "\N{NARROW NO-BREAK SPACE}"
ESPACE_INSECABLE = "\N{NO-BREAK SPACE}"
#: Couleurs des lignes, dans l'ordre, quand la grandeur n'en déclare pas.
PALETTE = ("#4fc3f7", "#81c784", "#ffb74d", "#e57373", "#ba68c8", "#4db6ac", "#f06292", "#dce775")
FOND = "#0f1720"
TEXTE = "#e8eef5"
DISCRET = "#7d8b99"


def chemin_police() -> Path:
    """DejaVu Sans, livrée avec matplotlib : accents garantis, sans dépendre du système."""
    from matplotlib import font_manager

    trouver: Any = font_manager.findfont
    return Path(trouver("DejaVu Sans"))


@dataclass(frozen=True, eq=False)
class Serie:
    """Une grandeur sur les instants de la trajectoire, déjà dans son unité d'affichage."""

    cle: str
    libelle: str
    t: Tableau
    valeurs: Tableau
    unite: str
    source: str
    couleur: str
    decimales: int | None = None
    plage: tuple[float, float] | None = None
    etendue_min: float = 0.0


def _calculs(traj: Trajectoire) -> dict[str, Callable[[], Tableau]]:
    def incidence() -> Tableau:
        v = traj.vitesse
        norme = np.linalg.norm(v, axis=1)
        with np.errstate(invalid="ignore", divide="ignore"):
            cos = np.sum(traj.axe_nez * v, axis=1) / norme
        angle = np.arccos(np.clip(cos, -1.0, 1.0))
        return np.where(norme > 1e-6, angle, np.nan)

    def euler(i: int) -> Callable[[], Tableau]:
        # Angles d'Euler ZYX par rapport au NED (lacet, tangage, roulis) : la convention aéronautique.
        def f() -> Tableau:
            q_ned = rot.produit(rot.depuis_matrice(matrice_vers_enu("NED").T), traj.attitude)
            return np.asarray(rot.vers_euler(q_ned, "ZYX")[:, i])
        return f

    def facteur_de_charge() -> Tableau:
        # Force spécifique ressentie : accélération moins pesanteur (1 g au repos, 0 en chute libre).
        return np.asarray(np.linalg.norm(traj.acceleration + np.array([0.0, 0.0, G0]), axis=1))

    return {
        "facteur_de_charge": facteur_de_charge,
        "cap": lambda: np.asarray(np.arctan2(traj.vitesse[:, 0], traj.vitesse[:, 1]) % (2 * np.pi)),
        "pente": lambda: np.asarray(np.arctan2(traj.vitesse[:, 2], np.hypot(traj.vitesse[:, 0], traj.vitesse[:, 1]))),
        "lacet": euler(0),
        "tangage": euler(1),
        "roulis": euler(2),
        "altitude": lambda: traj.positions[:, 2],
        "vitesse": lambda: np.linalg.norm(traj.vitesse, axis=1),
        "mach": lambda: traj.mach,
        "acceleration": lambda: np.linalg.norm(traj.acceleration, axis=1),
        "incidence_totale": incidence,
    }


def series(traj: Trajectoire, cfg: ConfigTelemetrie) -> list[Serie]:
    """Les lignes du panneau : calculées, ou lues dans une colonne de la trajectoire."""
    calculs = _calculs(traj)
    out = []
    for i, g in enumerate(cfg.grandeurs):
        if g.colonne is not None:
            if g.colonne not in traj.donnees:
                raise ValueError(
                    f"telemetrie : colonne « {g.colonne} » absente de la trajectoire "
                    f"(colonnes numériques : {', '.join(traj.donnees) or 'aucune'})"
                )
            brut, source = traj.donnees[g.colonne], f"colonne {g.colonne}"
        else:
            brut, source = calculs[g.cle](), "calculée"
        out.append(Serie(cle=g.cle, libelle=g.libelle, t=traj.t,
                         valeurs=np.asarray(brut, dtype=float) * g.facteur, unite=g.unite,
                         source=source, couleur=g.couleur or PALETTE[i % len(PALETTE)],
                         decimales=g.decimales, plage=g.plage, etendue_min=g.etendue_min))
    return out


def formater(valeur: float, unite: str = "", decimales: int | None = None) -> str:
    """Valeur à la française : virgule décimale, espace fine insécable entre milliers.

    Sans ``decimales`` : 0 au-delà de 100, 1 au-delà de 10, 2 en dessous.
    """
    if not np.isfinite(valeur):
        texte = "—"
    else:
        if decimales is None:
            decimales = 0 if abs(valeur) >= 100 else 1 if abs(valeur) >= 10 else 2
        texte = f"{valeur:,.{decimales}f}".replace(",", ESPACE_FINE).replace(".", ",").replace("-", "−")
    return f"{texte}{ESPACE_INSECABLE}{unite}" if unite else texte


def _graduation(valeur: float, _position: object = None) -> str:
    """Graduation à la française, sans zéros inutiles."""
    return f"{valeur:g}".replace(".", ",").replace("-", "−")


def _alleger(s: Serie, n_max: int, t_debut: float, t_fin: float) -> Serie:
    """La série rééchantillonnée sur ``n_max`` instants réguliers de ``[t_debut ; t_fin]``.

    Les extrêmes de chaque intervalle sont gardés (enveloppe min/max) : un pic bref
    reste visible. Rien n'est fait si la série a déjà assez peu de points.
    """
    dans = (s.t >= t_debut) & (s.t <= t_fin)
    if np.count_nonzero(dans) <= n_max or n_max < 4:
        return s
    t, v = s.t[dans], s.valeurs[dans]
    bords = np.linspace(t[0], t[-1], n_max // 2 + 1)
    case = np.clip(np.searchsorted(bords, t, side="right") - 1, 0, len(bords) - 2)
    garde = np.zeros(len(t), dtype=bool)
    garde[[0, -1]] = True
    for extreme in (np.fmin, np.fmax):
        meilleur = np.full(len(bords) - 1, np.nan)
        extreme.at(meilleur, case, v)
        garde |= v == meilleur[case]
    return replace(s, t=t[garde], valeurs=v[garde])


class PanneauTelemetrie:
    """Rend le panneau à une taille donnée, pour n'importe quel instant de vol."""

    def __init__(self, series_: list[Serie], taille: tuple[int, int], t_debut: float, t_fin: float) -> None:
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        from matplotlib.figure import Figure
        from matplotlib.ticker import FuncFormatter, MaxNLocator

        self.series = series_
        largeur, hauteur = taille
        self.taille = taille
        fig = Figure(figsize=(largeur / 100, hauteur / 100), dpi=100, facecolor=FOND)
        # matplotlib n'est pas typé pour mypy strict : le canevas est manipulé en Any.
        self._canvas: Any = cast(Any, FigureCanvasAgg(fig))
        self._fig = fig
        n = len(series_)
        echelle = min(hauteur / n / 110, largeur / 320)
        taille_ticks = max(5.0, 8 * echelle)
        self._animes: list[tuple[Serie, Serie, Any, Any, Any]] = []
        libelles: list[tuple[Any, Any, str]] = []
        # Bas du panneau réservé, en pixels, aux graduations et au titre de l'axe des temps.
        zone_bas = min(0.3, 3.2 * taille_ticks / 72 * 100 / hauteur)
        hr = (1 - zone_bas) / n
        for i, s in enumerate(series_):
            haut = 1 - i * hr
            derniere = i == n - 1
            libelle = fig.text(0.07, haut - 0.14 * hr, s.libelle, color=DISCRET,
                     fontsize=max(6.0, 11 * echelle), va="top", ha="left")
            valeur = fig.text(0.93, haut - 0.12 * hr, "", color=TEXTE,
                              fontsize=max(8.0, 22 * echelle), va="top", ha="right", animated=True)
            ax = fig.add_axes((0.15, haut - hr + 0.08 * hr, 0.78, 0.48 * hr))
            ax.set_facecolor(FOND)
            for cote in ("top", "right"):
                ax.spines[cote].set_visible(False)
            for cote in ("left", "bottom"):
                ax.spines[cote].set_color(DISCRET)
            ax.tick_params(colors=DISCRET, labelsize=taille_ticks, length=2)
            ax.yaxis.set_major_locator(MaxNLocator(3))
            ax.yaxis.set_major_formatter(FuncFormatter(_graduation))
            ax.xaxis.set_major_formatter(FuncFormatter(_graduation))
            if derniere:
                ax.set_xlabel("temps de vol (s)", color=DISCRET, fontsize=taille_ticks)
            else:
                ax.tick_params(labelbottom=False)
            dans = (s.t >= t_debut) & (s.t <= t_fin)
            v = s.valeurs[dans] if dans.any() else s.valeurs
            v = v[np.isfinite(v)] if np.isfinite(v).any() else np.zeros(1)
            bas, haut_v = float(np.min(v)), float(np.max(v))
            # Une grandeur presque constante (accélération en propulsion) ne doit pas faire
            # zoomer l'axe sur son bruit numérique.
            if s.plage is not None:
                ax.set_ylim(*s.plage)
            else:
                etendue = max(haut_v - bas, 0.05 * max(abs(bas), abs(haut_v)), s.etendue_min, 1e-6)
                centre = (bas + haut_v) / 2
                ax.set_ylim(centre - 0.58 * etendue, centre + 0.58 * etendue)
            # Le texte de valeur le plus large que cette ligne affichera (mesuré plus bas).
            candidats = [formater(float(x), s.unite, s.decimales) for x in (bas, haut_v)]
            libelles.append((libelle, valeur, max(candidats, key=len)))
            ax.set_xlim(t_debut, t_fin)
            # Pas plus de points qu'il n'en faut à la largeur de l'axe : chaque image redessine
            # la courbe parcourue, et des milliers d'échantillons y coûtent sans rien montrer.
            leger = _alleger(s, 3 * int(0.78 * largeur), t_debut, t_fin)
            ax.plot(leger.t, leger.valeurs, color=s.couleur, alpha=0.25, lw=1.2)
            (passe,) = ax.plot([], [], color=s.couleur, lw=2.0, animated=True)
            (point,) = ax.plot([], [], "o", color=s.couleur, ms=max(3.0, 6 * echelle), animated=True)
            self._animes.append((s, leger, valeur, passe, point))
        # Un libellé long ne doit pas passer sous la valeur : il prend la place que laisse
        # la valeur la plus large de sa ligne, et rétrécit s'il le faut.
        rendu = self._canvas.get_renderer()
        for libelle, valeur, texte_large in libelles:
            valeur.set_text(texte_large)
            place = 0.86 * largeur - valeur.get_window_extent(renderer=rendu).width - 0.04 * largeur
            valeur.set_text("")
            largeur_px = libelle.get_window_extent(renderer=rendu).width
            if largeur_px > place > 0:
                libelle.set_fontsize(max(5.0, libelle.get_fontsize() * place / largeur_px))
        self._canvas.draw()
        self._fond = self._canvas.copy_from_bbox(fig.bbox)

    def image(self, t: float) -> NDArray[np.uint8]:
        """Le panneau à l'instant de vol ``t``, RGB ``(hauteur, largeur, 3)``."""
        self._canvas.restore_region(self._fond)
        for s, leger, valeur, passe, point in self._animes:
            v_t = float(np.interp(t, s.t, s.valeurs))
            k = int(np.searchsorted(leger.t, t, side="right"))
            passe.set_data(np.append(leger.t[:k], t), np.append(leger.valeurs[:k], v_t))
            point.set_data([t], [v_t])
            valeur.set_text(formater(v_t, s.unite, s.decimales))
            for artiste in (passe, point, valeur):
                self._fig.draw_artist(artiste)
        tampon = np.asarray(self._canvas.buffer_rgba())
        largeur, hauteur = self.taille
        return np.ascontiguousarray(tampon[:hauteur, :largeur, :3])
