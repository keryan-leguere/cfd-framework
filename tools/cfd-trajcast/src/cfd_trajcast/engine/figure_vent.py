"""Le vent le long du vol, en **figure paper** et en **vidéo sans rendu 3D**.

Deux vues synchronisées par l'instant :

* une **rose Nord/Est** (polaire : Nord en haut, Est à droite, comme une carte) où le
  vent horizontal est une flèche partie du centre ; la trace grise derrière elle est le
  vent sur tout le vol (l'hodographe) ;
* le **profil vertical** du vol, l'altitude en fonction du temps, où l'instant de la
  rose est marqué.

En figure fixe, une rose par instant (rangées de six au plus) sous un profil commun :
chaque instant y porte la couleur et la forme de marqueur de sa rose. En vidéo, une
grande rose à gauche, le profil qui se trace à droite, et l'état courant en texte.

Toutes les roses d'une figure ou d'une vidéo ont le **même rayon** (le plus fort vent
horizontal du vol, arrondi), pour que les flèches se comparent. Conventions dans
:mod:`cfd_trajcast.core.vent_polaire` et ``00_DOC/10_FIGURES_VENT.md``.

Comme :mod:`cfd_trajcast.engine.figure_ensemble` : style ``paper`` de cfd-plot (exigé),
``Figure`` + canevas Agg (jamais pyplot), nombres en français.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core.vent_polaire import SENS_POLAIRE, azimut_module, rayon_polaire, vent_a
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.data.vent import DeclarationVent, vent_enu
from cfd_trajcast.engine.figure_ensemble import (
    COULEURS_EVENEMENTS,
    DPI_PNG,
    FORMATS_FIGURE,
    MARQUEURS_EVENEMENTS,
    ErreurFigure,
    _cfd_plot,
    _nombre,
    _secondes,
)
from cfd_trajcast.engine.schema_ensemble import _resoudre_poses

__all__ = [
    "DIAMETRE_MIN",
    "MAX_ROSES_PAR_RANGEE",
    "AnimationVent",
    "DonneesVent",
    "FigureVent",
    "animation_vent",
    "direction_texte",
    "figure_vent",
]

Tableau = NDArray[np.float64]

#: Roses par rangée dans la figure fixe ; au-delà, une rangée de plus.
MAX_ROSES_PAR_RANGEE = 6
#: Instants au plus dans la figure fixe (au-delà, plus rien ne se lit).
MAX_INSTANTS = 24
#: Diamètre d'une rose au moins (pouces), et la place laissée autour pour « O » et « E ».
DIAMETRE_MIN = 0.75
_AUTOUR_ROSE = 0.38
_CM = 1 / 2.54
_FLECHE = "#D55E00"  # vermillon Okabe-Ito : la flèche de la vidéo
_POINTS_TRACE = 600


@dataclass(frozen=True)
class FigureVent:
    """Une figure de vent écrite : ``fichiers`` (un par format), ``legende`` = légende proposée."""

    fichiers: tuple[Path, ...]
    instants: tuple[float, ...]
    rayon: float
    sens: str
    legende: str
    taille_cm: tuple[float, float]


@dataclass(frozen=True)
class AnimationVent:
    """Une vidéo de vent sans rendu 3D écrite."""

    chemin: Path
    images: int
    ips: int
    duree: float
    taille: tuple[int, int]
    encodeur: str
    sens: str
    rayon: float


class DonneesVent:
    """Le vent et l'altitude d'un vol, prêts à tracer ; tout instant se lit par interpolation."""

    def __init__(self, trajectoire: Trajectoire, vent: DeclarationVent | Tableau, sens: str = "vers") -> None:
        if sens not in SENS_POLAIRE:
            raise ValueError(f"sens : {' ou '.join(SENS_POLAIRE)} (reçu : {sens!r})")
        self.trajectoire, self.sens = trajectoire, sens
        self.t = np.asarray(trajectoire.t, dtype=float)
        enu = vent_enu(trajectoire, vent) if isinstance(vent, DeclarationVent) else np.asarray(vent, dtype=float)
        if enu.shape != (len(self.t), 3):
            raise ValueError("vent : un vecteur (Est, Nord, Haut) par instant de la trajectoire")
        self.vent = enu
        self.altitude = np.asarray(trajectoire.positions[:, 2], dtype=float)
        _, module, _ = azimut_module(enu, sens)
        self.rayon = rayon_polaire(module)
        self.evenements = [(e.nom, float(e.t)) for e in trajectoire.evenements if self.t[0] <= e.t <= self.t[-1]]
        # Trace dense de l'hodographe : azimut déroulé, pour que la ligne ne traverse pas la
        # rose quand le vent passe le Nord.
        self.t_trace = np.linspace(self.t[0], self.t[-1], max(_POINTS_TRACE, len(self.t)))
        theta, rho, _ = azimut_module(vent_a(self.t_trace, self.t, enu), sens)
        self.theta_trace, self.rho_trace = np.unwrap(theta), rho

    def a(self, t: float) -> tuple[float, float, float, float]:
        """``(azimut (rad), module horizontal, vertical, altitude)`` à ``t``."""
        theta, rho, vz = azimut_module(vent_a(float(t), self.t, self.vent), self.sens)
        return float(theta[0]), float(rho[0]), float(vz[0]), float(np.interp(t, self.t, self.altitude))

    def evenement_a(self, t: float) -> str | None:
        """Le nom de l'événement à cet instant, s'il y en a un."""
        for nom, te in self.evenements:
            if abs(te - t) < 1e-6:
                return nom
        return None


def direction_texte(azimut: float, module: float, sens: str) -> str:
    """« 6,2 m/s vers 235° » ; « calme » sous 0,05 m/s."""
    if module < 0.05:
        return "calme"
    degres = round(math.degrees(azimut)) % 360
    return f"{_nombre(module, 1)}\u00a0m/s {sens} {degres:03d}°"


def _vertical_texte(vz: float) -> str:
    if abs(vz) < 0.05:
        return "vertical nul"
    return f"vertical {_nombre(abs(vz), 1)}\u00a0m/s {'montant' if vz > 0 else 'descendant'}"


# -- tracés communs ----------------------------------------------------------------------
def _rose(ax: Any, d: DonneesVent, *, taille_texte: float = 7.0, anneaux: bool = True) -> None:
    """Polaire Nord en haut, Est à droite, rayon commun, hodographe du vol en gris."""
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_thetagrids([0, 90, 180, 270], ["N", "E", "S", "O"], fontsize=taille_texte + 1)
    ax.set_ylim(0, d.rayon)
    anneaux_r = [d.rayon / 2, d.rayon]
    if anneaux:
        # Le dernier anneau porte l'unité : « 10 », « 20 m/s ».
        textes = [_nombre(r, 0 if r >= 10 or r == int(r) else 1) for r in anneaux_r]
        textes[-1] += "\u00a0m/s"
        ax.set_rgrids(anneaux_r, labels=textes, angle=135, fontsize=taille_texte - 1, color="0.40")
    else:
        ax.set_rgrids(anneaux_r, labels=["", ""])
    ax.tick_params(axis="x", pad=-1)
    ax.grid(True, color="0.82", linewidth=0.5)
    ax.plot(d.theta_trace, d.rho_trace, color="0.80", linewidth=0.8, zorder=1.0)


def _fleche(ax: Any, theta: float, rho: float, couleur: str, largeur: float) -> Any:
    return ax.annotate(
        "", xy=(theta, rho), xytext=(0.0, 0.0), zorder=4.0,
        arrowprops={"arrowstyle": "-|>,head_length=0.5,head_width=0.25", "color": couleur, "linewidth": largeur,
                    "shrinkA": 0.0, "shrinkB": 0.0, "mutation_scale": 6 * largeur},
    )


def _profil(ax: Any, d: DonneesVent, *, taille_texte: float = 7.0) -> None:
    """Axes du profil : événements en pointillé, nombres à la française."""
    from matplotlib.ticker import FuncFormatter

    for _, te in d.evenements:
        ax.axvline(te, color="0.70", linewidth=0.6, linestyle=(0, (1.5, 1.5)), zorder=0.5)
    ax.set_xlim(d.t[0], d.t[-1])
    # Les noms des événements en graduations du bord haut : hors du tracé, alignés sur leur
    # pointillé ; deux événements rapprochés (Mach 1, fin de propulsion) partagent une étiquette.
    groupes = _grouper_evenements(d.evenements, 0.04 * float(d.t[-1] - d.t[0]))
    if groupes:
        haut_axe = ax.secondary_xaxis("top")
        haut_axe.set_xticks([t for t, _ in groupes])
        haut_axe.set_xticklabels([nom for _, nom in groupes], fontsize=taille_texte, color="0.35")
        haut_axe.tick_params(axis="x", length=0, pad=2)
    bas, haut = float(d.altitude.min()), float(d.altitude.max())
    marge = 0.06 * (haut - bas) if haut > bas else 1.0
    ax.set_ylim(bas - marge, haut + marge)
    formateur = FuncFormatter(lambda v, _: _nombre(v))
    ax.yaxis.set_major_formatter(formateur)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: _nombre(v, 0 if abs(v) >= 10 or v == int(v) else 1)))
    ax.set_xlabel("Temps (s)")
    ax.set_ylabel("Altitude (m)")
    ax.minorticks_off()


def _grouper_evenements(evenements: Sequence[tuple[str, float]], ecart: float) -> list[tuple[float, str]]:
    """``(instant moyen, « nom / nom »)`` : les événements à moins de ``ecart`` s'un de l'autre ensemble."""
    groupes: list[list[tuple[str, float]]] = []
    for nom, te in sorted(evenements, key=lambda e: e[1]):
        if groupes and te - groupes[-1][-1][1] < ecart:
            groupes[-1].append((nom, te))
        else:
            groupes.append([(nom, te)])
    return [(float(np.mean([te for _, te in g])), " / ".join(nom for nom, _ in g)) for g in groupes]


def _base(chemin: str | Path) -> Path:
    base = Path(chemin)
    if base.suffix.lower().lstrip(".") in FORMATS_FIGURE:
        base = base.with_suffix("")
    return base


def _legende_proposee(d: DonneesVent, instants: Sequence[float]) -> str:
    sens = "où va l'air" if d.sens == "vers" else "d'où vient le vent (convention météo)"
    quand = ", ".join(_secondes(t) for t in instants)
    return (f"Vent rencontré le long du vol, à {quand}. En haut, l'altitude en fonction du temps et les "
            f"instants retenus ; en dessous, une rose par instant (Nord en haut, Est à droite) dont la flèche "
            f"est le vent horizontal et montre {sens}, rayon commun de {_nombre(d.rayon, 1)} m/s. "
            f"Trace grise : le vent horizontal sur tout le vol.")


# -- figure fixe ----------------------------------------------------------------------------
@dataclass(frozen=True, eq=False)
class _Dessin:
    """La figure fixe construite, avant écriture : relue par les tests."""

    figure: Any
    profil: Any
    roses: tuple[Any, ...]
    fleches: tuple[Any, ...]
    instants: tuple[float, ...]
    donnees: DonneesVent


def _dessiner(cp: Any, d: DonneesVent, choisis: tuple[float, ...], largeur_cm: float, titre: str) -> _Dessin:
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    n = len(choisis)
    # Tout se place en pouces, puis se convertit en fractions de la figure.
    largeur = largeur_cm * _CM
    gauche, droite = 0.85, 0.15
    utile = largeur - gauche - droite
    # Autant de roses par rangée que la largeur en loge à DIAMETRE_MIN, six au plus ; chacune
    # garde autour d'elle la place de O et E (ceux de deux roses voisines ne se touchent pas).
    colonnes = max(1, min(n, MAX_ROSES_PAR_RANGEE, int(utile // (DIAMETRE_MIN + _AUTOUR_ROSE))))
    rangees = math.ceil(n / colonnes)
    pas = utile / colonnes
    diametre = min(pas - _AUTOUR_ROSE, 2.0)
    h_profil = min(0.42 * utile, 3.2)
    marge_haut = 0.30 + (0.25 if titre else 0.0)  # noms des événements (et titre) au-dessus du profil
    sous_profil = 0.55  # graduations et titre de l'axe du temps
    titre_rose, sous_rose = 0.36, 0.78  # titre + « N » au-dessus ; « S » + trois lignes dessous
    h_case = titre_rose + diametre + sous_rose
    hauteur = marge_haut + h_profil + sous_profil + rangees * h_case

    def rect(x: float, y_haut: float, w: float, h: float) -> tuple[float, float, float, float]:
        """Un rectangle donné en pouces depuis le coin haut gauche → fractions de figure."""
        return (x / largeur, 1 - (y_haut + h) / hauteur, w / largeur, h / hauteur)

    fig = Figure(figsize=(largeur, hauteur))
    FigureCanvasAgg(fig)
    fig.set_layout_engine("none")
    ax_p = fig.add_axes(rect(gauche, marge_haut, utile, h_profil))
    _profil(ax_p, d)
    ax_p.plot(d.t, d.altitude, color="black", linewidth=1.2, zorder=2.0)
    if titre:
        cp.set_title(ax_p, titre, pad=18)

    roses, fleches = [], []
    for k, t in enumerate(choisis):
        couleur = COULEURS_EVENEMENTS[k % len(COULEURS_EVENEMENTS)]
        marqueur = MARQUEURS_EVENEMENTS[k % len(MARQUEURS_EVENEMENTS)]
        theta, rho, vz, alt = d.a(t)
        ax_p.plot([t], [alt], linestyle="none", marker=marqueur, markersize=6, color=couleur,
                  markeredgecolor="black", markeredgewidth=0.6, zorder=4.0, clip_on=False)
        ax_p.annotate(str(k + 1), xy=(t, alt), xytext=(4, 4), textcoords="offset points", fontsize=7,
                      color="0.15", zorder=4.5)
        rangee, col = divmod(k, colonnes)
        dans_rangee = min(colonnes, n - rangee * colonnes)
        # Une rangée incomplète est centrée sous le profil.
        cx = gauche + (colonnes - dans_rangee) * pas / 2 + (col + 0.5) * pas
        y = marge_haut + h_profil + sous_profil + rangee * h_case + titre_rose
        ax = fig.add_axes(rect(cx - diametre / 2, y, diametre, diametre), projection="polar")
        _rose(ax, d, taille_texte=6.5, anneaux=(k == 0))
        fleches.append(_fleche(ax, theta, rho, couleur, 1.6))
        ax.plot([theta], [rho], linestyle="none", marker=marqueur, markersize=4.5, color=couleur,
                markeredgecolor="black", markeredgewidth=0.5, zorder=5.0)
        evenement = d.evenement_a(t)
        entete = f"{k + 1}. {evenement} ({_secondes(t)})" if evenement else f"{k + 1}. t = {_secondes(t)}"
        ax.set_title(entete, fontsize=7.5, pad=11)
        ax.annotate(f"{direction_texte(theta, rho, d.sens)}\n{_vertical_texte(vz)}\n"
                    f"altitude {_nombre(alt)}\u00a0m", xy=(0.5, 0.0), xycoords="axes fraction",
                    xytext=(0, -13), textcoords="offset points", ha="center", va="top",
                    fontsize=6.5, color="0.20", linespacing=1.35)
        roses.append(ax)
    return _Dessin(fig, ax_p, tuple(roses), tuple(fleches), choisis, d)


def figure_vent(
    trajectoire: Trajectoire,
    vent: DeclarationVent | Tableau,
    chemin: str | Path | None = None,
    *,
    instants: int | Sequence[float | str] | None = None,
    sens: str = "vers",
    formats: Sequence[str] = FORMATS_FIGURE,
    largeur_cm: float = 16.0,
    titre: str = "",
) -> FigureVent:
    """Le profil vertical et une rose du vent par instant ; écrite en ``chemin``.<format>.

    ``vent`` : la déclaration (section ``vent`` du YAML) ou directement le vent ENU
    ``(n, 3)``. ``instants`` : un nombre (répartis sur le vol), ou des instants (s) et
    des noms d'événements ; défaut : aux événements (cinq instants répartis sans événement).
    ``largeur_cm`` : largeur de la figure ; la hauteur suit le nombre de rangées.
    """
    cp = _cfd_plot()
    inconnus = [f for f in formats if f not in FORMATS_FIGURE]
    if inconnus or not formats:
        raise ErreurFigure(f"formats : parmi {', '.join(FORMATS_FIGURE)} (reçu : {', '.join(formats) or 'aucun'})")
    if not 6 <= largeur_cm <= 40:
        raise ErreurFigure("largeur_cm : entre 6 et 40 cm")
    d = DonneesVent(trajectoire, vent, sens)
    choisis = _resoudre_poses(trajectoire, instants)
    if not choisis:
        raise ValueError("instants : au moins un")
    if len(choisis) > MAX_INSTANTS:
        raise ValueError(f"instants : {MAX_INSTANTS} au plus ({len(choisis)} demandés)")

    with cp.style_context("paper"):
        dessin = _dessiner(cp, d, choisis, largeur_cm, titre)
        fig = dessin.figure
        fig.canvas.draw()
        emprise = fig.get_tightbbox(fig.canvas.get_renderer()).padded(0.03)
        fichiers: list[Path] = []
        if chemin is not None:
            base = _base(chemin)
            base.parent.mkdir(parents=True, exist_ok=True)
            for fmt in formats:
                sortie = base.parent / f"{base.name}.{fmt}"  # pas de with_suffix (« vol_M0.85 »)
                fig.savefig(sortie, format=fmt, dpi=DPI_PNG, bbox_inches=emprise)
                fichiers.append(sortie)
    return FigureVent(
        fichiers=tuple(fichiers), instants=tuple(choisis), rayon=d.rayon, sens=sens,
        legende=_legende_proposee(d, choisis),
        taille_cm=(float(emprise.width / _CM), float(emprise.height / _CM)),
    )


# -- animation ---------------------------------------------------------------------------------
def animation_vent(
    trajectoire: Trajectoire,
    vent: DeclarationVent | Tableau,
    chemin: str | Path,
    instants: Sequence[float] | Tableau,
    *,
    sens: str = "vers",
    ips: float = 30.0,
    resolution: tuple[int, int] = (1920, 1080),
    titre: str = "",
    crf: int = 18,
    progression: Callable[[int, int], None] | None = None,
) -> AnimationVent:
    """La rose du vent et le profil vertical, animés ensemble : MP4 sans rendu 3D.

    ``instants`` : instant de vol de chaque image (ceux de
    :func:`~cfd_trajcast.core.temps.instants_de_vol`, ralentis compris). La flèche suit le
    vent courant, la trace des vents déjà rencontrés se dessine derrière elle, le profil
    se trace au fil du vol, et les événements s'allument quand ils sont atteints.
    """
    cp = _cfd_plot()
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D

    t_vol = np.asarray(instants, dtype=float)
    if t_vol.ndim != 1 or len(t_vol) < 1:
        raise ErreurFigure("animation : au moins un instant")
    d = DonneesVent(trajectoire, vent, sens)
    largeur_px, hauteur_px = resolution
    fps = max(1, round(ips))
    dpi = hauteur_px / 5.4
    chemin = Path(chemin)

    with cp.style_context("paper"):
        fig = Figure(figsize=(largeur_px / dpi, hauteur_px / dpi), dpi=dpi)
        FigureCanvasAgg(fig)
        fig.set_layout_engine("none")
        rapport = largeur_px / hauteur_px
        cote = 0.66  # hauteur relative de la rose ; largeur relative = cote / rapport (carrée)
        ax_r = fig.add_axes((0.05, 0.12, cote / rapport, cote), projection="polar")
        _rose(ax_r, d, taille_texte=9.0)
        (deja,) = ax_r.plot([], [], color="0.25", linewidth=1.2, zorder=2.0)
        fleche = _fleche(ax_r, 0.0, 0.0, _FLECHE, 2.4)
        quoi = "où va l'air" if sens == "vers" else "d'où vient le vent"
        ax_r.set_title(f"Vent horizontal, {quoi}", fontsize=10, pad=24)

        # À droite de la rose, avec la place des graduations et du titre de l'axe des altitudes.
        gauche = 0.05 + cote / rapport + 0.11
        ax_p = fig.add_axes((gauche, 0.42, 0.95 - gauche, 0.48))
        _profil(ax_p, d, taille_texte=9.0)
        profil = cp.PathReveal(
            ax_p, d.t_trace, d.t_trace, np.interp(d.t_trace, d.t, d.altitude),
            ghost_kw={"color": "0.82", "linewidth": 1.0, "zorder": 1.8},
            trail_kw={"color": "black", "linewidth": 1.6, "zorder": 2.0},
            head_kw={"marker": "o", "markersize": 7, "color": _FLECHE, "markeredgecolor": "black",
                     "markeredgewidth": 0.6, "zorder": 4.0},
        )
        curseur = ax_p.axvline(float(t_vol[0]), color=_FLECHE, linewidth=0.8, alpha=0.6, zorder=1.5)
        marques = []
        for k, (_, te) in enumerate(d.evenements):
            (m,) = ax_p.plot([te], [float(np.interp(te, d.t, d.altitude))], linestyle="none",
                             marker=MARQUEURS_EVENEMENTS[k % 7], markersize=6, color=COULEURS_EVENEMENTS[k % 7],
                             markeredgecolor="black", markeredgewidth=0.6, zorder=3.5)
            m.set_visible(False)
            marques.append((te, m))
        if titre:
            fig.text(0.02, 0.97, titre, fontsize=12, va="top", fontfamily=cp.TITLE_FONT)

        # État courant, sous le profil, et les événements atteints à droite de lui.
        horloge = fig.text(gauche, 0.30, "", fontsize=15, va="top")
        fig.text(gauche, 0.22, "Altitude\nVent\n", fontsize=10, va="top", linespacing=1.6, color="0.35")
        lignes = fig.text(gauche + 0.07, 0.22, "", fontsize=10, va="top", linespacing=1.6)
        x_evt = gauche + 0.30
        etiquettes = []
        if d.evenements:
            fig.text(x_evt, 0.30, "Événements", fontsize=10, color="0.35", va="top")
        for k, (nom, te) in enumerate(d.evenements[:5]):
            y = 0.24 - 0.045 * k
            point = Line2D([x_evt + 0.006], [y - 0.008], transform=fig.transFigure, linestyle="none",
                           marker=MARQUEURS_EVENEMENTS[k % 7], markersize=6, color=COULEURS_EVENEMENTS[k % 7],
                           markeredgecolor="black", markeredgewidth=0.6)
            fig.add_artist(point)
            texte = fig.text(x_evt + 0.02, y, f"{nom} — {_secondes(te)}", fontsize=9, va="top")
            etiquettes.append((te, point, texte))

        with cp.animate(fig, chemin, fps=fps, width_px=largeur_px, hold_first=0.0, hold_last=1.0,
                        crf=crf) as anim:
            for k, t in enumerate(t_vol):
                t = float(t)
                theta, rho, vz, alt = d.a(t)
                fin = int(np.searchsorted(d.t_trace, t, side="right"))
                # La trace déjà vue finit exactement sur la flèche : azimut déroulé comme la trace.
                th_fin = d.theta_trace[max(fin - 1, 0)]
                theta_d = theta + 2 * np.pi * round((th_fin - theta) / (2 * np.pi))
                deja.set_data(np.append(d.theta_trace[:fin], theta_d), np.append(d.rho_trace[:fin], rho))
                fleche.xy = (theta, rho)
                profil.update(t)
                curseur.set_xdata([t, t])
                for te, m in marques:
                    m.set_visible(bool(t >= te - 1e-9))
                for te, point, texte in etiquettes:
                    atteint = bool(t >= te - 1e-9)
                    point.set_alpha(1.0 if atteint else 0.25)
                    texte.set_color("black" if atteint else "0.70")
                horloge.set_text(f"t = {_secondes(t)}")
                lignes.set_text(f"{_nombre(alt)}\u00a0m\n{direction_texte(theta, rho, sens)}\n"
                                f"{_vertical_texte(vz)}")
                anim.capture()
                if progression is not None:
                    progression(k + 1, len(t_vol))
    resultat = anim.result
    assert resultat is not None
    return AnimationVent(
        chemin=resultat.paths[0], images=resultat.n_frames, ips=fps, duree=resultat.duration_s,
        taille=resultat.size_px, encodeur=resultat.backend, sens=sens, rayon=d.rayon,
    )
