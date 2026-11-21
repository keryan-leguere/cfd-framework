"""Vue d'ensemble en **figure paper** (Matplotlib 3D, style ``paper`` de cfd-plot) et en
**vidéo sans rendu 3D** (la même figure animée, ``cfd_plot.anim``).

Ni OpenGL ni écran : Matplotlib dessine en 2D la projection d'une scène 3D. C'est ce
qui rend la figure prête pour un article — police, graduations, cadre et couleurs
sont ceux de toutes les figures cfd-plot, la sortie est vectorielle (PDF, SVG) — et
la vidéo possible sur une machine sans GPU.

Conventions de la figure
------------------------
* Toujours le **NED classique** : axes Nord, Est, Bas, Bas positif vers le sol (les
  valeurs négatives sont donc au-dessus du sol). En ``repere: ned_local``, seul le zéro
  de l'axe Bas change : il est au point de départ.
* Tracé en ``x = Est``, ``y = Nord``, ``z = Bas`` avec l'axe ``z`` **inversé** : le haut
  de l'image est le haut du ciel, et le trièdre affiché (Est, Nord, Haut) est direct.
  Mettre Nord en ``x`` donnerait (Nord, Est, Haut), indirect : l'image serait le
  **miroir** du vol — un virage à droite s'y lirait à gauche.
* **Proportions vraies** (boîte proportionnelle aux étendues) et projection
  **orthographique** par défaut : une distance se lit pareil au premier plan et au
  fond. ``projection="persp"`` reprend la perspective de la vidéo (angle ``champ``).
* Graduations rentrantes, pas de graduations mineures, fonds blancs
  (:func:`cfd_plot.tidy_axes3d`) ; nombres en français (espace fine des milliers,
  vrai signe moins, virgule décimale) ; couleurs Okabe-Ito pour les événements, avec
  une forme de marqueur chacun (la figure se lit aussi en noir et blanc).
* La maquette, agrandie, est ombrée en niveaux de gris (Lambert à deux faces : le
  sens des faces d'un STL n'est pas garanti) et triée par profondeur par Matplotlib.

cfd-plot est exigé ici (et seulement ici) : sans lui, ``cfd-trajcast ensemble`` se
replie sur le schéma SVG maison (:mod:`cfd_trajcast.engine.schema_ensemble`).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.camera import (
    ENU_VERS_NED,
    ParametresEnsemble,
    azimut_ensemble,
    boite_ensemble,
    echelle_ensemble,
    ned_ensemble,
    origine_ensemble,
    titres_axes_ensemble,
)
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.engine.schema_ensemble import POINTS_TRACE, _resoudre_poses, simplifier

__all__ = [
    "FORMATS_FIGURE",
    "PROJECTIONS",
    "AnimationEnsemble",
    "ErreurFigure",
    "FigureEnsemble",
    "SceneEnsemble",
    "animation_ensemble",
    "axes_ensemble",
    "cfd_plot_disponible",
    "decor_ensemble",
    "en_trace",
    "figure_ensemble",
    "marqueurs_ensemble",
    "nombre_fr",
    "ombrer",
]

Tableau = NDArray[np.float64]

FORMATS_FIGURE = ("pdf", "svg", "png")
PROJECTIONS = ("ortho", "persp")
#: Faces de la maquette au plus : figure fixe, puis animation (redessinée à chaque image).
FACES_FIGURE = 3000
FACES_ANIMATION = 1200
#: Couleurs des événements : Okabe-Ito sans le noir (réservé à la trajectoire).
COULEURS_EVENEMENTS = ("#E69F00", "#0072B2", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442")
MARQUEURS_EVENEMENTS = ("o", "s", "D", "^", "v", "P", "X")
#: Points par pouce des PNG de la figure.
DPI_PNG = 300
_CM = 1 / 2.54
_LUMIERE = np.array([-0.35, 0.45, -0.82]) / np.linalg.norm([-0.35, 0.45, -0.82])  # NED, d'en haut


class ErreurFigure(RuntimeError):
    """cfd-plot absent, ou demande impossible."""


def _cfd_plot() -> Any:
    try:
        import cfd_plot  # type: ignore[import-untyped,unused-ignore]
    except ImportError as exc:
        raise ErreurFigure(
            "la figure paper et l'animation sans rendu demandent le paquet cfd-plot "
            "(tools/cfd-plot du dépôt : pip install tools/cfd-plot)"
        ) from exc
    return cfd_plot


def cfd_plot_disponible() -> bool:
    """cfd-plot est-il importable ici ?"""
    try:
        _cfd_plot()
    except ErreurFigure:
        return False
    return True


# -- nombres ----------------------------------------------------------------------------
_ESPACE_FINE = "\u2009"
_MOINS = "\u2212"


def _nombre(v: float, decimales: int = 0) -> str:
    """``-1250`` → ``−1 250`` (espace fine, vrai signe moins) ; ``3.7`` (1 déc.) → ``3,7``."""
    texte = f"{v:,.{decimales}f}".replace(",", _ESPACE_FINE).replace(".", ",").replace("-", _MOINS)
    if not texte.strip(_MOINS + "0," + _ESPACE_FINE):  # « −0 », « −0,0 » : pas de signe
        return texte.lstrip(_MOINS)
    return texte


def _secondes(t: float) -> str:
    return f"{_nombre(t, 1)}\u00a0s"


# -- scène ------------------------------------------------------------------------------
@dataclass(frozen=True)
class FigureEnsemble:
    """Une figure paper écrite : ``fichiers`` (un par format), ``legende`` = légende proposée."""

    fichiers: tuple[Path, ...]
    poses: tuple[float, ...]
    echelle: float
    repere: str
    projection: str
    legende: str
    taille_cm: tuple[float, float]


@dataclass(frozen=True)
class AnimationEnsemble:
    """Une vidéo sans rendu 3D écrite."""

    chemin: Path
    images: int
    ips: int
    duree: float
    taille: tuple[int, int]
    encodeur: str
    repere: str


def _maillage(maquette: Maquette, faces_max: int) -> tuple[Tableau, NDArray[np.int64]]:
    sommets = np.asarray(maquette.sommets, dtype=float)
    faces = np.asarray(maquette.faces, dtype=np.int64)
    cellule = maquette.taille / 400
    while len(faces) > faces_max and cellule <= maquette.taille / 15:
        sommets, faces = simplifier(np.asarray(maquette.sommets, dtype=float),
                                    np.asarray(maquette.faces, dtype=np.int64), cellule)
        cellule *= 1.5
    return sommets, faces


def _trace(xyz_ned: Tableau) -> Tableau:
    """NED → coordonnées tracées (x = Est, y = Nord, z = Bas)."""
    return np.asarray(xyz_ned, dtype=float)[..., [1, 0, 2]]


class _Scene:
    """Les données de la vue d'ensemble, prêtes à tracer (coordonnées x = Est, y = Nord, z = Bas)."""

    def __init__(self, traj: Trajectoire, maquette: Maquette, params: ParametresEnsemble,
                 sol_altitude: float, faces_max: int) -> None:
        self.traj, self.params = traj, params
        self.t = np.linspace(traj.t[0], traj.t[-1], max(POINTS_TRACE, int(60 * (traj.t[-1] - traj.t[0]))))
        trace_enu, _ = traj.etat(self.t)
        self.origine = origine_ensemble(trace_enu, params.repere)
        self.ned = ned_ensemble(trace_enu, self.origine)
        self.xyz = _trace(self.ned)
        boite = boite_ensemble(trace_enu, sol_altitude, self.origine)
        self.sol = boite.sol
        m = boite.marge
        # Bornes tracées : x = Est, y = Nord, z = Bas — le sol compris, un peu de ciel au-dessus.
        self.bas = np.array([boite.mini[1] - m, boite.mini[0] - m, boite.mini[2] - m])
        self.haut = np.array([boite.maxi[1] + m, boite.maxi[0] + m, max(boite.maxi[2], self.sol)])
        self.echelle = echelle_ensemble(trace_enu, maquette.taille, params)
        self.sommets, self.faces = _maillage(maquette, faces_max)
        self.azimut = azimut_ensemble(trace_enu, params)
        self.evenements = [(e.nom, float(e.t)) for e in traj.evenements if traj.t[0] <= e.t <= traj.t[-1]]
        self.titres = titres_axes_ensemble(params.repere)

    def position(self, t: float | Tableau) -> Tableau:
        return _trace(ned_ensemble(self.traj.etat(np.atleast_1d(np.asarray(t, dtype=float)))[0], self.origine))

    def vers_trace(self, points_enu: Tableau) -> Tableau:
        """Points ENU → coordonnées tracées (x = Est, y = Nord, z = Bas, origine du repère)."""
        return _trace(ned_ensemble(points_enu, self.origine))

    def fusee(self, t: float) -> tuple[Tableau, Tableau]:
        """Triangles (n, 3, 3) en coordonnées tracées, et leur gris (n,) ombré."""
        positions, attitudes = self.traj.etat(np.array([t]))
        r = self.echelle * (ENU_VERS_NED @ rot.vers_matrice(attitudes[0]))
        monde = ned_ensemble(positions[0], self.origine)[None, :] + self.sommets @ r.T
        tri = monde[self.faces]
        normales = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        n = np.linalg.norm(normales, axis=1)
        normales = normales / np.where(n > 0, n, 1.0)[:, None]
        gris = 0.30 + 0.55 * np.abs(normales @ _LUMIERE) ** 1.2
        return _trace(tri), gris

    def regard(self) -> tuple[float, float]:
        """(élévation, azimut) Matplotlib : l'azimut NED se mesure depuis le Nord vers l'Est,
        celui de Matplotlib depuis +x (Est) vers +y (Nord)."""
        return float(self.params.elevation), float(90.0 - self.azimut)

    def espacer(self, instants: tuple[float, ...]) -> tuple[float, ...]:
        """Poses par défaut : on saute celles à moins d'une maquette d'une pose gardée (deux
        événements rapprochés — Mach 1 et fin de propulsion — superposeraient deux maquettes)."""
        if len(instants) < 2:
            return instants
        p = self.position(np.array(instants))
        longueur = self.echelle * float(np.ptp(self.sommets, axis=0).max())
        gardes: list[int] = []
        for i in range(len(instants)):
            if all(np.linalg.norm(p[i] - p[j]) >= longueur for j in gardes):
                gardes.append(i)
        return tuple(instants[i] for i in gardes)

    def proportions(self, projection: str) -> float:
        """Hauteur / largeur de la boîte projetée (pour dimensionner la figure)."""
        el, az = np.radians(self.regard())
        vers_oeil = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
        haut = np.array([0.0, 0.0, 1.0])
        droite = np.cross(haut, vers_oeil)
        droite /= np.linalg.norm(droite)
        haut_ecran = np.cross(vers_oeil, droite)
        coins = np.array([[x, y, -z] for x in (self.bas[0], self.haut[0]) for y in (self.bas[1], self.haut[1])
                          for z in (self.bas[2], self.haut[2])])
        w = float(np.ptp(coins @ droite))
        h = float(np.ptp(coins @ haut_ecran))
        return h / w if w > 0 else 1.0


def _axes(cp: Any, fig: Any, scene: _Scene, rect: Sequence[float], projection: str,
          ecart_titre_bas: float = 38.0) -> Any:
    ax = fig.add_axes(rect, projection="3d", computed_zorder=False)
    cp.true_proportions(ax, scene.bas, scene.haut)
    ax.set_zlim(scene.haut[2], scene.bas[2])  # Bas vers le bas de l'image : le ciel en haut
    cp.tidy_axes3d(ax, nbins=8)
    from matplotlib.ticker import FuncFormatter

    formateur = FuncFormatter(lambda v, _: _nombre(v))
    for axe in (ax.xaxis, ax.yaxis, ax.zaxis):
        axe.set_major_formatter(formateur)
        axe.set_tick_params(pad=4)
    # En 3D, une étiquette de graduation est *centrée* à `pad` de son axe : un « −7 000 »
    # chevaucherait l'axe vertical. On l'écarte d'une demi-étiquette, le titre avec.
    ax.zaxis.set_tick_params(pad=16)
    ax.set_xlabel(scene.titres[1], labelpad=8)
    ax.set_ylabel(scene.titres[0], labelpad=8)
    ax.set_zlabel(scene.titres[2], labelpad=ecart_titre_bas)
    el, az = scene.regard()
    ax.view_init(elev=el, azim=az)
    if projection == "persp":
        ax.set_proj_type("persp", focal_length=1 / np.tan(np.radians(scene.params.champ) / 2))
    else:
        ax.set_proj_type("ortho")
    return ax


def _decor(ax: Any, scene: _Scene, *, aplombs: bool = True) -> Any:
    """Sol, trace au sol, fils à plomb des événements ; renvoie la trace au sol (légende)."""
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # type: ignore[import-untyped,unused-ignore]

    b, h, s = scene.bas, scene.haut, scene.sol
    sol = [[(b[0], b[1], s), (h[0], b[1], s), (h[0], h[1], s), (b[0], h[1], s)]]
    ax.add_collection3d(Poly3DCollection(sol, facecolor="0.94", edgecolor="0.70", linewidth=0.4, zorder=0.5))
    (trace_sol,) = ax.plot(scene.xyz[:, 0], scene.xyz[:, 1], np.full(len(scene.xyz), s), color="0.62",
                           linewidth=0.7, zorder=1.0, label="Trace au sol")
    if aplombs:
        for _, te in scene.evenements:
            p = scene.position(te)[0]
            ax.plot([p[0], p[0]], [p[1], p[1]], [p[2], s], color="0.55", linewidth=0.5,
                    linestyle=(0, (1.5, 1.5)), zorder=1.5)
    return trace_sol


def _marqueurs(ax: Any, scene: _Scene) -> list[tuple[float, Any]]:
    """Un marqueur par événement (couleur et forme), étiqueté pour la légende."""
    out = []
    for k, (nom, te) in enumerate(scene.evenements):
        p = scene.position(te)[0]
        (m,) = ax.plot([p[0]], [p[1]], [p[2]], linestyle="none", marker=MARQUEURS_EVENEMENTS[k % 7],
                       markersize=5.5, color=COULEURS_EVENEMENTS[k % 7], markeredgecolor="black",
                       markeredgewidth=0.6, zorder=4.0, label=f"{nom} ({_secondes(te)})")
        out.append((te, m))
    return out


def _poly_fusee(ax: Any, scene: _Scene, t: float, zorder: float) -> Any:
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # type: ignore[import-untyped,unused-ignore]

    tri, gris = scene.fusee(t)
    couleurs = np.column_stack([gris, gris, gris * 1.04, np.ones_like(gris)]).clip(0, 1)
    poly = Poly3DCollection(tri, facecolors=couleurs, edgecolors=couleurs, linewidths=0.15, zorder=zorder)
    ax.add_collection3d(poly)
    return poly


def _proxy_fusee(echelle: float) -> Any:
    from matplotlib.patches import Patch

    texte = f"Maquette (agrandie ×\u2009{_nombre(echelle)})" if echelle > 1 else "Maquette"
    return Patch(facecolor="0.55", edgecolor="0.30", linewidth=0.5, label=texte)


def _placer_legende(cp: Any, fig: Any, ax: Any, poignees: Sequence[Any]) -> None:
    """À droite de tout ce qui est dessiné (graduations et titre de l'axe Bas compris), à
    mi-hauteur de la boîte."""
    dessin = cp.bbox3d(fig, pad=0.0)
    coins = cp.box3d_corners_px(ax)
    milieu = float(fig.transFigure.inverted().transform((0.0, coins[:, 1].mean()))[1])
    x = (dessin.x1 + 0.12) / fig.get_size_inches()[0]
    fig.legend(handles=list(poignees), loc="center left", bbox_to_anchor=(x, milieu), frameon=True, fontsize=8)


def _legende_proposee(scene: _Scene, poses: tuple[float, ...], projection: str) -> str:
    t0, t1 = float(scene.traj.t[0]), float(scene.traj.t[-1])
    repere = ("repère NED local (origine verticale au point de départ)" if scene.params.repere == "ned_local"
              else "repère NED")
    morceaux = [f"Vue d'ensemble du vol de {_secondes(t0)} à {_secondes(t1)}, {repere}."]
    if poses:
        quand = ", ".join(_secondes(t) for t in poses)
        agrandie = f"agrandie {_nombre(scene.echelle)} fois, " if scene.echelle > 1 else ""
        morceaux.append(f"Maquette {agrandie}posée à {quand}.")
    morceaux.append("Projection orthographique, proportions vraies." if projection == "ortho"
                    else "Projection perspective, proportions vraies.")
    return " ".join(morceaux)


# -- figure fixe ------------------------------------------------------------------------
def figure_ensemble(
    trajectoire: Trajectoire,
    maquette: Maquette,
    parametres: ParametresEnsemble | None = None,
    chemin: str | Path | None = None,
    *,
    sol_altitude: float = 0.0,
    poses: int | Sequence[float | str] | None = None,
    largeur_cm: float = 12.0,
    formats: Sequence[str] = FORMATS_FIGURE,
    projection: str = "ortho",
    titre: str = "",
    legende: bool = True,
) -> FigureEnsemble:
    """La vue d'ensemble en figure paper ; écrite en ``chemin``.<format> pour chaque format.

    ``poses`` : comme :func:`~cfd_trajcast.engine.schema_ensemble.schema_ensemble` (défaut :
    aux événements). ``largeur_cm`` : largeur de la figure (la hauteur suit les proportions
    du vol). ``legende`` : encadré des éléments et des événements, à droite de la boîte.
    """
    cp = _cfd_plot()
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    if projection not in PROJECTIONS:
        raise ErreurFigure(f"projection : {', '.join(PROJECTIONS)}")
    inconnus = [f for f in formats if f not in FORMATS_FIGURE]
    if inconnus or not formats:
        raise ErreurFigure(f"formats : parmi {', '.join(FORMATS_FIGURE)} (reçu : {', '.join(formats) or 'aucun'})")
    if not 4 <= largeur_cm <= 40:
        raise ErreurFigure("largeur_cm : entre 4 et 40 cm")
    params = parametres or ParametresEnsemble()
    scene = _Scene(trajectoire, maquette, params, sol_altitude, FACES_FIGURE)
    instants = _resoudre_poses(trajectoire, poses)
    if poses is None:
        instants = scene.espacer(instants)

    with cp.style_context("paper"):
        # Figure + canevas Agg, jamais pyplot : pyplot choisirait le backend Qt dès que PyQt5 est
        # installé (interface) et chargerait Qt sans en avoir besoin (cf. gui/_qt.py).
        fig = Figure(figsize=(6.0, 6.0))
        FigureCanvasAgg(fig)
        fig.set_layout_engine("none")
        ax = _axes(cp, fig, scene, (0.0, 0.0, 1.0, 1.0), projection)
        trace_sol = _decor(ax, scene)
        (ligne,) = ax.plot(*scene.xyz.T, color="black", linewidth=1.4, zorder=2.0, label="Trajectoire")
        # Maquettes, de la plus lointaine à la plus proche (ordre de dessin entre poses).
        if instants:
            positions = scene.position(np.array(instants))
            el, az = np.radians(scene.regard())
            vers_oeil = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), -np.sin(el)])
            ordre = np.argsort(positions @ vers_oeil)
            for rang, k in enumerate(ordre):
                _poly_fusee(ax, scene, instants[k], 3.0 + 0.01 * rang)
            evenements = {round(te, 6) for _, te in scene.evenements}
            for tp, p in zip(instants, positions):
                if round(tp, 6) not in evenements:
                    ax.text(p[0], p[1], p[2], f"  {_secondes(tp)}", fontsize=7, color="0.25", zorder=5.0)
        marqueurs = _marqueurs(ax, scene)
        if titre:
            ax.set_title(titre)
        poignees = [ligne, trace_sol] + ([_proxy_fusee(scene.echelle)] if instants else [])
        poignees += [m for _, m in marqueurs]
        # Graduations, titres et légende ont une taille fixe (en points) : la boîte prend le
        # reste de la largeur demandée, corrigée en quelques passes sur l'emprise mesurée.
        cible = largeur_cm * _CM
        boite = cible * (0.62 if legende else 0.82)
        for _ in range(3):
            cp.fit_box3d(ax, boite)
            for ancienne in list(fig.legends):
                ancienne.remove()
            if legende:
                _placer_legende(cp, fig, ax, poignees)
            ecart = cible - (cp.bbox3d(fig, pad=0.03).width)
            if abs(ecart) < 0.02 * cible:
                break
            boite = max(0.3 * cible, boite + ecart)
        emprise = cp.bbox3d(fig, pad=0.03)
        fichiers: list[Path] = []
        if chemin is not None:
            base = Path(chemin)
            if base.suffix.lower().lstrip(".") in FORMATS_FIGURE:
                base = base.with_suffix("")
            base.parent.mkdir(parents=True, exist_ok=True)
            for fmt in formats:
                # Pas de with_suffix : « vol_M0.85 » perdrait son « .85 ».
                sortie = base.parent / f"{base.name}.{fmt}"
                fig.savefig(sortie, format=fmt, dpi=DPI_PNG, bbox_inches=emprise)
                fichiers.append(sortie)
        taille = (emprise.width / _CM, emprise.height / _CM)
    return FigureEnsemble(
        fichiers=tuple(fichiers), poses=instants, echelle=scene.echelle, repere=params.repere,
        projection=projection, legende=_legende_proposee(scene, instants, projection),
        taille_cm=(float(taille[0]), float(taille[1])),
    )


# -- animation ---------------------------------------------------------------------------
def animation_ensemble(
    trajectoire: Trajectoire,
    maquette: Maquette,
    parametres: ParametresEnsemble | None,
    chemin: str | Path,
    instants: Sequence[float] | Tableau,
    *,
    ips: float = 30.0,
    resolution: tuple[int, int] = (1920, 1080),
    sol_altitude: float = 0.0,
    titre: str = "",
    crf: int = 18,
    progression: Callable[[int, int], None] | None = None,
) -> AnimationEnsemble:
    """La figure de la vue d'ensemble, animée : MP4 sans rendu 3D.

    ``instants`` : instant de vol de chaque image (ceux de la vidéo rendue :
    :func:`~cfd_trajcast.core.temps.instants_de_vol`, ralentis compris). La trajectoire se
    trace au fil du vol (le reste en gris clair), la maquette la parcourt avec son
    attitude, les événements s'allument quand ils sont atteints, et un panneau à droite
    donne l'instant, l'altitude et la vitesse.
    """
    cp = _cfd_plot()
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.lines import Line2D

    t_vol = np.asarray(instants, dtype=float)
    if t_vol.ndim != 1 or len(t_vol) < 1:
        raise ErreurFigure("animation : au moins un instant")
    largeur_px, hauteur_px = resolution
    params = parametres or ParametresEnsemble()
    scene = _Scene(trajectoire, maquette, params, sol_altitude, FACES_ANIMATION)
    fps = max(1, round(ips))
    dpi = hauteur_px / 5.4
    chemin = Path(chemin)

    with cp.style_context("paper"):
        fig = Figure(figsize=(largeur_px / dpi, hauteur_px / dpi), dpi=dpi)
        FigureCanvasAgg(fig)
        fig.set_layout_engine("none")
        ax = _axes(cp, fig, scene, (0.0, 0.07, 0.66, 0.90), "ortho", ecart_titre_bas=44.0)
        cp.fit_box3d(ax, fill=0.80)  # taille imposée : seul le zoom s'ajuste
        _decor(ax, scene)
        chemin_vol = cp.PathReveal(
            ax, scene.t, *scene.xyz.T,
            ghost_kw={"color": "0.80", "linewidth": 1.0, "zorder": 1.8},
            trail_kw={"color": "black", "linewidth": 1.6, "zorder": 2.0},
            head_kw={"marker": "", "zorder": 2.1},
        )
        marqueurs = _marqueurs(ax, scene)
        for _, m in marqueurs:
            m.set_visible(False)
        fusee = _poly_fusee(ax, scene, float(t_vol[0]), 3.0)
        if titre:
            fig.text(0.02, 0.97, titre, fontsize=12, va="top", fontfamily=cp.TITLE_FONT)

        # Panneau de droite : instant, altitude, vitesse, puis les événements atteints.
        x0 = 0.68
        horloge = fig.text(x0, 0.86, "", fontsize=16, va="top")
        lignes = fig.text(x0, 0.76, "", fontsize=10, va="top", linespacing=1.6)
        etiquettes = []
        for k, (nom, te) in enumerate(scene.evenements):
            y = 0.52 - 0.055 * k
            point = Line2D([x0 + 0.008], [y + 0.012], transform=fig.transFigure, linestyle="none",
                               marker=MARQUEURS_EVENEMENTS[k % 7], markersize=7,
                               color=COULEURS_EVENEMENTS[k % 7], markeredgecolor="black", markeredgewidth=0.6)
            fig.add_artist(point)
            texte = fig.text(x0 + 0.025, y, f"{nom} — {_secondes(te)}", fontsize=10)
            etiquettes.append((te, point, texte))
        if scene.evenements:
            fig.text(x0, 0.58, "Événements", fontsize=10, color="0.35")
        fig.text(x0, 0.03, f"Maquette agrandie ×\u2009{_nombre(scene.echelle)}"
                 if scene.echelle > 1 else "", fontsize=8, color="0.40")

        vitesses = trajectoire.vitesse_a(t_vol)
        altitudes = trajectoire.etat(t_vol)[0][:, 2]
        with cp.animate(fig, chemin, fps=fps, width_px=largeur_px, hold_first=0.0, hold_last=1.0,
                        crf=crf) as anim:
            for k, t in enumerate(t_vol):
                chemin_vol.update(float(t))
                tri, gris = scene.fusee(float(t))
                couleurs = np.column_stack([gris, gris, gris * 1.04, np.ones_like(gris)]).clip(0, 1)
                fusee.set_verts(tri)
                fusee.set_facecolor(couleurs)
                fusee.set_edgecolor(couleurs)
                for te, m in marqueurs:
                    m.set_visible(bool(t >= te - 1e-9))
                for te, point, texte in etiquettes:
                    atteint = bool(t >= te - 1e-9)
                    point.set_alpha(1.0 if atteint else 0.25)
                    texte.set_color("black" if atteint else "0.70")
                horloge.set_text(f"t = {_secondes(float(t))}")
                lignes.set_text(f"Altitude   {_nombre(float(altitudes[k]))} m\n"
                                f"Vitesse    {_nombre(float(np.linalg.norm(vitesses[k])))} m/s")
                anim.capture()
                if progression is not None:
                    progression(k + 1, len(t_vol))
    resultat = anim.result
    assert resultat is not None
    return AnimationEnsemble(
        chemin=resultat.paths[0], images=resultat.n_frames, ips=fps, duree=resultat.duration_s,
        taille=resultat.size_px, encodeur=resultat.backend, repere=params.repere,
    )


def ombrer(triangles_trace: Tableau) -> Tableau:
    """Couleurs RGBA ``(n, 4)`` des triangles (coordonnées tracées) : Lambert à deux faces, en gris."""
    tri = np.asarray(triangles_trace, dtype=float)[..., [1, 0, 2]]  # retour en NED pour la lumière
    normales = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n = np.linalg.norm(normales, axis=1)
    normales = normales / np.where(n > 0, n, 1.0)[:, None]
    gris = 0.30 + 0.55 * np.abs(normales @ _LUMIERE) ** 1.2
    return np.column_stack([gris, gris, gris * 1.04, np.ones_like(gris)]).clip(0, 1)


# Noms publics des briques de la scène, pour la vue interactive (engine/vue3d_mpl.py).
SceneEnsemble = _Scene
axes_ensemble = _axes
decor_ensemble = _decor
marqueurs_ensemble = _marqueurs
en_trace = _trace
nombre_fr = _nombre
