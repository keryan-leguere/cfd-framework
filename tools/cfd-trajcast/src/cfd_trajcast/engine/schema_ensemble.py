"""Schéma SVG de la vue d'ensemble : le vol entier, **sans moteur 3D**.

Même caméra (:func:`~cfd_trajcast.core.camera.cadre_ensemble`), même boîte graduée
(:func:`~cfd_trajcast.core.camera.boite_ensemble`), même agrandissement de la maquette
et mêmes couleurs que la vue ``ensemble`` de la vidéo — mais projetés en NumPy
(:func:`~cfd_trajcast.core.camera.projeter`) et écrits en SVG : pas d'OpenGL, pas
d'écran, un fichier vectoriel qui s'ouvre partout et se retouche dans Inkscape.

Ce qu'il montre : le plan du sol et la trace au sol, la boîte NED graduée (grilles
sur les faces du fond, comme ``show_grid`` de VTK), le vol entier, les événements
(point, nom, instant, et un fil à plomb jusqu'au sol pour lire la 3D), et la
maquette agrandie posée à quelques instants (``poses``).

La maquette est dessinée par l'algorithme du peintre — triangles du plus loin au
plus proche, ombrés d'un Lambert à deux faces — parce que le sens des faces d'un
STL n'est pas garanti : éliminer les faces arrière sur un maillage mal orienté
trouerait la silhouette. Au-delà de :data:`FACES_MAX` faces, le maillage est
simplifié par regroupement de sommets (une maquette CAO en a vite 10⁵, et au plus
quelques centaines de pixels à l'écran).

Le cadrage est **ajusté au contenu** : la caméra est celle de la vidéo, mais l'image
est recadrée sur ce qu'elle montre, donc un vol presque vertical donne une image
haute — proportions vraies, jamais d'axes étirés.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.camera import (
    ENU_VERS_NED,
    BoiteEnsemble,
    ParametresEnsemble,
    boite_ensemble,
    cadre_ensemble,
    echelle_ensemble,
    projeter,
    vers_ned,
)
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.engine.scene import THEMES_ENSEMBLE

__all__ = ["AIRE_MIN_PX", "FACES_MAX", "POSES_DEFAUT", "Schema", "schema_ensemble", "simplifier"]

Tableau = NDArray[np.float64]

#: Au-delà, la maquette est simplifiée (regroupement de sommets) avant d'être dessinée.
FACES_MAX = 4000
#: Aire (px²) en dessous de laquelle un triangle de la maquette n'est pas écrit.
AIRE_MIN_PX = 0.1
#: Poses de la maquette quand le vol n'a pas d'événement.
POSES_DEFAUT = 5
#: Points du vol échantillonnés (au moins ; 60 par seconde de vol sinon), comme la vidéo.
POINTS_TRACE = 4000
#: Tracé simplifié : un point gardé dès qu'il s'écarte de tant de pixels du précédent.
PAS_TRACE_PX = 0.6
POLICE = "DejaVu Sans, Helvetica, Arial, sans-serif"
AXES = ("Nord (m)", "Est (m)", "Bas (m)")


@dataclass(frozen=True)
class Schema:
    """Un schéma SVG de la vue d'ensemble.

    ``poses`` : instants de vol où la maquette est dessinée ; ``echelle`` : son
    agrandissement ; ``faces`` : faces dessinées par pose (après simplification).
    """

    svg: str
    largeur: int
    hauteur: int
    poses: tuple[float, ...]
    echelle: float
    faces: int
    chemin: Path | None = None

    def ecrire(self, chemin: str | Path) -> Schema:
        """Écrit le SVG ; renvoie le schéma, chemin renseigné."""
        chemin = Path(chemin)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(self.svg, encoding="utf-8")
        return Schema(self.svg, self.largeur, self.hauteur, self.poses, self.echelle, self.faces, chemin)


# -- maquette ---------------------------------------------------------------------------
def simplifier(sommets: Tableau, faces: NDArray[np.int64], cellule: float) -> tuple[Tableau, NDArray[np.int64]]:
    """Regroupement de sommets sur une grille de pas ``cellule`` (m) ; faces dégénérées ôtées."""
    cles = np.floor(sommets / cellule).astype(np.int64)
    _, inverse, effectifs = np.unique(cles, axis=0, return_inverse=True, return_counts=True)
    inverse = inverse.ravel()
    nouveaux = np.zeros((len(effectifs), 3))
    np.add.at(nouveaux, inverse, sommets)
    nouveaux /= effectifs[:, None]
    f = inverse[faces]
    garde = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
    f = np.unique(np.sort(f[garde], axis=1), axis=0) if garde.any() else f[:0]
    return nouveaux, f.astype(np.int64)


def _maillage(maquette: Maquette) -> tuple[Tableau, NDArray[np.int64]]:
    sommets = np.asarray(maquette.sommets, dtype=float)
    faces = np.asarray(maquette.faces, dtype=np.int64)
    cellule = maquette.taille / 400
    while len(faces) > FACES_MAX:
        sommets_s, faces_s = simplifier(sommets, faces, cellule)
        if len(faces_s) <= FACES_MAX or cellule > maquette.taille / 20:
            return sommets_s, faces_s
        cellule *= 1.5
    return sommets, faces


def _rgb(couleur: str) -> Tableau:
    return np.array([int(couleur[i:i + 2], 16) for i in (1, 3, 5)], dtype=float)


def _hex(rgb: Tableau) -> str:
    r, g, b = (int(v) for v in np.clip(np.round(rgb), 0, 255))
    return f"#{r:02x}{g:02x}{b:02x}"


# -- mise en page -----------------------------------------------------------------------
def _nombre(v: float) -> str:
    """``-1250`` → ``−1 250`` (espace fine insécable, vrai signe moins)."""
    texte = f"{v:,.0f}".replace(",", "\u202f")
    return "0" if texte == "-0" else texte.replace("-", "\u2212")


def _secondes(t: float) -> str:
    return f"{t:.1f}".replace(".", ",") + "\u00a0s"


def _largeur_texte(texte: str, corps: float) -> float:
    """Largeur approchée d'un texte (le SVG ne mesure pas : on estime pour cadrer)."""
    return 0.58 * corps * len(texte)


class _Dessin:
    """Accumule les éléments SVG et l'emprise de ce qu'ils couvrent (pour le recadrage)."""

    def __init__(self) -> None:
        self.elements: list[str] = []
        self.mini = np.array([np.inf, np.inf])
        self.maxi = np.array([-np.inf, -np.inf])
        #: Rectangles (x0, y0, x1, y1) des textes déjà posés, pour ne pas les superposer.
        self.occupe: list[tuple[float, float, float, float]] = []

    def libre(self, rect: tuple[float, float, float, float]) -> bool:
        """Le rectangle ne recouvre aucun texte déjà posé."""
        x0, y0, x1, y1 = rect
        return all(x1 <= a0 or x0 >= a1 or y1 <= b0 or y0 >= b1 for a0, b0, a1, b1 in self.occupe)

    def couvre(self, xy: Tableau) -> None:
        xy = np.atleast_2d(xy)
        finis = xy[np.isfinite(xy).all(axis=1)]
        if len(finis):
            self.mini = np.minimum(self.mini, finis.min(axis=0))
            self.maxi = np.maximum(self.maxi, finis.max(axis=0))

    def ajouter(self, element: str, xy: Tableau | None = None) -> None:
        self.elements.append(element)
        if xy is not None:
            self.couvre(xy)

    def rect_texte(self, x: float, y: float, texte: str, corps: float, ancre: str = "start",
                   ) -> tuple[float, float, float, float]:
        w = _largeur_texte(texte, corps)
        x0 = {"start": x, "middle": x - w / 2, "end": x - w}[ancre]
        return (x0, y - corps, x0 + w, y + 0.3 * corps)

    def texte(self, x: float, y: float, texte: str, corps: float, couleur: str, *,
              ancre: str = "start", angle: float = 0.0, poids: str = "normal", opacite: float = 1.0) -> None:
        w = _largeur_texte(texte, corps)
        x0 = {"start": x, "middle": x - w / 2, "end": x - w}[ancre]
        if angle == 0.0:
            self.couvre(np.array([[x0, y - corps], [x0 + w, y + 0.3 * corps]]))
            self.occupe.append((x0, y - corps, x0 + w, y + 0.3 * corps))
        else:
            self.couvre(np.array([[x - w, y - w], [x + w, y + w]]))
        rotation = f' transform="rotate({angle:.1f} {x:.1f} {y:.1f})"' if angle else ""
        self.elements.append(
            f'<text x="{x:.1f}" y="{y:.1f}" font-size="{corps:.1f}" fill="{couleur}" '
            f'text-anchor="{ancre}" font-weight="{poids}" opacity="{opacite:g}"{rotation}>{escape(texte)}</text>'
        )


def _points(xy: Tableau) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)


def _alleger(xy: Tableau, pas: float) -> Tableau:
    """Garde un point dès qu'il s'écarte de ``pas`` pixels du dernier gardé (et le dernier)."""
    gardes = [0]
    for i in range(1, len(xy)):
        if np.hypot(*(xy[i] - xy[gardes[-1]])) >= pas:
            gardes.append(i)
    if gardes[-1] != len(xy) - 1:
        gardes.append(len(xy) - 1)
    return xy[gardes]


def _resoudre_poses(traj: Trajectoire, poses: int | Sequence[float | str] | None) -> tuple[float, ...]:
    t0, t1 = float(traj.t[0]), float(traj.t[-1])
    evenements = {e.nom: float(e.t) for e in traj.evenements if t0 <= e.t <= t1}
    if poses is None:
        if evenements:
            return tuple(sorted(evenements.values()))
        poses = POSES_DEFAUT
    if isinstance(poses, int):
        if poses < 0:
            raise ValueError("poses : un nombre positif ou nul")
        return tuple(float(t) for t in np.linspace(t0, t1, poses)) if poses else ()
    out = []
    for p in poses:
        if isinstance(p, str):
            if p not in evenements:
                raise ValueError(f"poses : événement « {p} » inconnu ; événements : "
                                 f"{', '.join(evenements) or 'aucun'}")
            out.append(evenements[p])
        else:
            if not t0 <= float(p) <= t1:
                raise ValueError(f"poses : t = {float(p):g} s hors du vol [{t0:g} ; {t1:g}] s")
            out.append(float(p))
    return tuple(out)


def _espacer(instants: tuple[float, ...], traj: Trajectoire, proj: _Projection,
             longueur: float) -> tuple[float, ...]:
    """Poses par défaut : on saute celles qui tomberaient à moins d'une maquette (à l'écran)
    d'une pose déjà retenue — deux événements rapprochés feraient deux maquettes superposées."""
    positions = vers_ned(traj.etat(np.array(instants))[0])
    ecran = proj(positions)
    f = (proj.cote / 2) / np.tan(np.radians(proj.champ) / 2)
    taille_px = f * longueur / np.maximum(proj.profondeur(positions), 1e-9)
    gardes: list[int] = []
    for i in range(len(instants)):
        if all(np.hypot(*(ecran[i] - ecran[j])) >= 0.8 * max(taille_px[i], taille_px[j]) for j in gardes):
            gardes.append(i)
    return tuple(instants[i] for i in gardes)


# -- la boîte graduée -------------------------------------------------------------------
def _coin(boite: BoiteEnsemble, cote: Sequence[int]) -> Tableau:
    """Coin de la boîte : ``cote[i]`` = 0 (borne basse) ou 1 (haute) sur l'axe ``i``."""
    return np.array([(boite.bas, boite.haut)[c][i] for i, c in enumerate(cote)])


def _faces_du_fond(boite: BoiteEnsemble, camera: Tableau) -> set[tuple[int, int]]:
    """Faces ``(axe, côté)`` dont la normale sortante s'éloigne de la caméra."""
    centre = (boite.bas + boite.haut) / 2
    fond = set()
    for axe in range(3):
        for cote in (0, 1):
            point = centre.copy()
            point[axe] = (boite.bas, boite.haut)[cote][axe]
            normale = np.zeros(3)
            normale[axe] = 1.0 if cote else -1.0
            if (point - camera) @ normale > 0:
                fond.add((axe, cote))
    return fond


def _dessiner_boite(d: _Dessin, boite: BoiteEnsemble, proj: _Projection, th: dict[str, str], u: float) -> None:
    fond = _faces_du_fond(boite, proj.camera)
    trait = max(0.5, 0.8 * u)
    # Grilles sur les faces du fond.
    lignes = []
    for axe, cote in sorted(fond):
        autres = [i for i in range(3) if i != axe]
        for a, b in (autres, autres[::-1]):
            for v in boite.graduations(a):
                p0 = np.empty(3)
                p0[axe] = (boite.bas, boite.haut)[cote][axe]
                p0[a] = v
                p1 = p0.copy()
                p0[b], p1[b] = boite.bas[b], boite.haut[b]
                lignes.append(proj(np.array([p0, p1])))
    for seg in lignes:
        d.ajouter(f'<line x1="{seg[0, 0]:.1f}" y1="{seg[0, 1]:.1f}" x2="{seg[1, 0]:.1f}" y2="{seg[1, 1]:.1f}"/>', seg)
    d.elements.insert(len(d.elements) - len(lignes),
                      f'<g stroke="{th["grille"]}" stroke-width="{trait:.2f}" opacity="0.28">')
    d.ajouter("</g>")
    # Les douze arêtes.
    aretes = []
    for axe in range(3):
        autres = [i for i in range(3) if i != axe]
        for ca in (0, 1):
            for cb in (0, 1):
                c0, c1 = [0, 0, 0], [0, 0, 0]
                c0[autres[0]] = c1[autres[0]] = ca
                c0[autres[1]] = c1[autres[1]] = cb
                c1[axe] = 1
                aretes.append((axe, (ca, cb), proj(np.array([_coin(boite, c0), _coin(boite, c1)]))))
    d.ajouter(f'<g stroke="{th["grille"]}" stroke-width="{1.2 * trait:.2f}" opacity="0.75" fill="none">')
    for _, _, seg in aretes:
        d.ajouter(f'<line x1="{seg[0, 0]:.1f}" y1="{seg[0, 1]:.1f}" x2="{seg[1, 0]:.1f}" y2="{seg[1, 1]:.1f}"/>', seg)
    d.ajouter("</g>")
    # Graduations : sur une arête de silhouette (une face du fond, une face de devant), la plus
    # basse à l'écran pour Nord et Est, la plus à gauche pour Bas.
    centre_ecran = proj(((boite.bas + boite.haut) / 2)[None, :])[0]
    corps = 13.0 * u
    for axe in range(3):
        autres = [i for i in range(3) if i != axe]
        candidates = [(cotes, seg) for a, cotes, seg in aretes if a == axe
                      and ((autres[0], cotes[0]) in fond) != ((autres[1], cotes[1]) in fond)]
        if not candidates:
            candidates = [(cotes, seg) for a, cotes, seg in aretes if a == axe]
        if axe == 2:
            _, seg = min(candidates, key=lambda c: float(c[1][:, 0].mean()))
        else:
            _, seg = max(candidates, key=lambda c: float(c[1][:, 1].mean()))
        direction = seg[1] - seg[0]
        longueur = float(np.hypot(*direction))
        if longueur < 1e-6:
            continue
        tangente = direction / longueur
        normale = np.array([-tangente[1], tangente[0]])
        if (seg.mean(axis=0) - centre_ecran) @ normale < 0:
            normale = -normale
        ancre = "start" if normale[0] > 0.35 else ("end" if normale[0] < -0.35 else "middle")
        dernier: Tableau | None = None
        valeurs = boite.graduations(axe)
        etendue = boite.haut[axe] - boite.bas[axe]
        for v in valeurs:
            s = (v - boite.bas[axe]) / etendue if etendue > 0 else 0.0
            pied = seg[0] + s * direction
            if dernier is not None and np.hypot(*(pied - dernier)) < 2.6 * corps:
                continue
            bout = pied + 5 * u * normale
            pos = pied + 9 * u * normale
            xt, yt = float(pos[0]), float(pos[1] + 0.35 * corps + 0.5 * corps * normale[1])
            if not d.libre(d.rect_texte(xt, yt, _nombre(float(v)), corps, ancre)):
                continue  # coin commun à deux axes : la graduation de l'autre axe y est déjà
            dernier = pied
            d.ajouter(f'<line x1="{pied[0]:.1f}" y1="{pied[1]:.1f}" x2="{bout[0]:.1f}" y2="{bout[1]:.1f}" '
                      f'stroke="{th["grille"]}" stroke-width="{trait:.2f}"/>', np.array([pied, bout]))
            d.texte(xt, yt, _nombre(float(v)), corps, th["grille"], ancre=ancre)
        # Titre de l'axe, le long de l'arête, au-delà des graduations.
        largeur_max = max(_largeur_texte(_nombre(float(v)), corps) for v in valeurs)
        recul = 9 * u + (largeur_max if abs(normale[0]) > 0.35 else 0) + 2.2 * corps
        milieu = seg.mean(axis=0) + recul * normale
        angle = float(np.degrees(np.arctan2(tangente[1], tangente[0])))
        if angle > 90:
            angle -= 180
        elif angle <= -90:
            angle += 180
        d.texte(float(milieu[0]), float(milieu[1] + 0.35 * corps), AXES[axe], 1.15 * corps, th["texte"],
                ancre="middle", angle=angle)


@dataclass(frozen=True)
class _Projection:
    camera: Tableau
    vise: Tableau
    haut: Tableau
    champ: float
    cote: float

    def __call__(self, points_ned: Tableau) -> Tableau:
        xy, _ = projeter(points_ned, self.camera, self.vise, self.haut, self.champ, self.cote, self.cote)
        return xy

    def profondeur(self, points_ned: Tableau) -> Tableau:
        return projeter(points_ned, self.camera, self.vise, self.haut, self.champ, self.cote, self.cote)[1]


# -- le schéma --------------------------------------------------------------------------
def schema_ensemble(
    trajectoire: Trajectoire,
    maquette: Maquette,
    parametres: ParametresEnsemble | None = None,
    *,
    theme: str = "clair",
    sol_altitude: float = 0.0,
    taille: int = 1600,
    poses: int | Sequence[float | str] | None = None,
    titre: str = "",
    sous_titre: str = "",
) -> Schema:
    """Le vol entier en SVG, vu par la caméra de la vue ``ensemble``.

    ``taille`` : plus grand côté de la figure (px, hors marges et textes) ; l'autre
    suit les proportions du vol. ``poses`` : instants où dessiner la maquette — un
    nombre (régulièrement répartis), une liste d'instants (s) ou de noms d'événements ;
    ``None`` : à chaque événement (ou :data:`POSES_DEFAUT` s'il n'y en a pas).
    """
    if theme not in THEMES_ENSEMBLE:
        raise ValueError(f"theme : {', '.join(THEMES_ENSEMBLE)}")
    if taille < 200:
        raise ValueError("taille : au moins 200 px")
    params = parametres or ParametresEnsemble()
    th = THEMES_ENSEMBLE[theme]
    instants_poses = _resoudre_poses(trajectoire, poses)

    t = np.linspace(trajectoire.t[0], trajectoire.t[-1],
                    max(POINTS_TRACE, int(60 * (trajectoire.t[-1] - trajectoire.t[0]))))
    trace_enu, _ = trajectoire.etat(t)
    trace = vers_ned(trace_enu)
    boite = boite_ensemble(trace_enu, sol_altitude)
    camera, vise, haut = cadre_ensemble(trace_enu, params, 1.0, (boite.bas, boite.haut))
    # Projection dans un carré provisoire, puis mise à l'échelle : le plus grand côté de la
    # géométrie (boîte et sol) vaut `taille` pixels.
    brut = _Projection(camera, vise, haut, params.champ, 1000.0)
    sol_coins = np.array([[boite.mini[0] - boite.marge, boite.mini[1] - boite.marge, boite.sol],
                          [boite.maxi[0] + boite.marge, boite.mini[1] - boite.marge, boite.sol],
                          [boite.maxi[0] + boite.marge, boite.maxi[1] + boite.marge, boite.sol],
                          [boite.mini[0] - boite.marge, boite.maxi[1] + boite.marge, boite.sol]])
    coins = np.array([_coin(boite, (a, b, c)) for a in (0, 1) for b in (0, 1) for c in (0, 1)])
    xy = brut(np.vstack([coins, sol_coins, trace]))
    etendue = float(np.max(xy.max(axis=0) - xy.min(axis=0)))
    proj = _Projection(camera, vise, haut, params.champ, 1000.0 * taille / etendue)
    u = taille / 1600

    d = _Dessin()
    # Sol, puis grilles du fond (le plancher de la boîte est au-dessus du plan du sol).
    d.ajouter(f'<polygon points="{_points(proj(sol_coins))}" fill="{th["sol"]}" opacity="0.7"/>',
              proj(sol_coins))
    _dessiner_boite(d, boite, proj, th, u)
    # Trace au sol, fils à plomb des événements, vol.
    au_sol = trace.copy()
    au_sol[:, 2] = boite.sol
    xy_sol = _alleger(proj(au_sol), PAS_TRACE_PX)
    d.ajouter(f'<polyline points="{_points(xy_sol)}" fill="none" stroke="{th["trace_sol"]}" '
              f'stroke-width="{1.5 * u:.2f}" stroke-linejoin="round"/>', xy_sol)
    evenements = [(e.nom, float(e.t)) for e in trajectoire.evenements
                  if trajectoire.t[0] <= e.t <= trajectoire.t[-1]]
    pos_ev = vers_ned(trajectoire.etat(np.array([te for _, te in evenements]))[0]) if evenements else np.zeros((0, 3))
    for p in pos_ev:
        pied = p.copy()
        pied[2] = boite.sol
        seg = proj(np.array([p, pied]))
        d.ajouter(f'<line x1="{seg[0, 0]:.1f}" y1="{seg[0, 1]:.1f}" x2="{seg[1, 0]:.1f}" y2="{seg[1, 1]:.1f}" '
                  f'stroke="{th["trace_sol"]}" stroke-width="{u:.2f}" stroke-dasharray="{4 * u:.1f} {3 * u:.1f}"/>')
    xy_vol = _alleger(proj(trace), PAS_TRACE_PX)
    d.ajouter(f'<polyline points="{_points(xy_vol)}" fill="none" stroke="{th["parcouru"]}" '
              f'stroke-width="{3 * u:.2f}" stroke-linejoin="round" stroke-linecap="round"/>', xy_vol)

    # Maquette agrandie aux poses, de la plus lointaine à la plus proche.
    echelle = echelle_ensemble(trace_enu, maquette.taille, params)
    sommets, faces = _maillage(maquette)
    if poses is None and len(instants_poses) > 1:
        instants_poses = _espacer(instants_poses, trajectoire, proj, echelle * maquette.taille)
    if instants_poses:
        positions, attitudes = trajectoire.etat(np.array(instants_poses))
        lumiere = np.array([-0.35, 0.45, -0.82])  # Nord-Ouest, d'en haut (NED)
        lumiere /= np.linalg.norm(lumiere)
        base = _rgb(th["fusee"])
        clair = np.clip(base * 1.9 + 40, 0, 255)
        ordre = np.argsort(-proj.profondeur(vers_ned(positions)))
        for k in ordre:
            r = echelle * (ENU_VERS_NED @ rot.vers_matrice(attitudes[k]))
            monde = vers_ned(positions[k])[None, :] + sommets @ r.T
            tri = monde[faces]
            normales = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
            n = np.linalg.norm(normales, axis=1)
            normales = normales / np.where(n > 0, n, 1.0)[:, None]
            eclairement = 0.25 + 0.75 * np.abs(normales @ lumiere)
            couleurs = base + (clair - base) * eclairement[:, None] ** 1.5
            ecran = proj(tri.reshape(-1, 3)).reshape(-1, 3, 2)
            # Un triangle vu par la tranche ou plus petit qu'un dixième de pixel ne se voit pas :
            # le trait de même couleur de ses voisins le couvre (allège le fichier de moitié).
            a, b = ecran[:, 1] - ecran[:, 0], ecran[:, 2] - ecran[:, 0]
            visibles = np.flatnonzero(np.abs(a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) / 2 >= AIRE_MIN_PX)
            loin = visibles[np.argsort(-proj.profondeur(tri[visibles].mean(axis=1)))]
            d.ajouter(f'<g stroke-width="{0.35 * u:.2f}" stroke-linejoin="round">', ecran.reshape(-1, 2))
            for j in loin:
                c = _hex(couleurs[j])
                p = ecran[j]
                d.ajouter(f'<path d="M{p[0, 0]:.1f} {p[0, 1]:.1f}L{p[1, 0]:.1f} {p[1, 1]:.1f}'
                          f'L{p[2, 0]:.1f} {p[2, 1]:.1f}Z" fill="{c}" stroke="{c}"/>')
            d.ajouter("</g>")
    # Événements : point, nom et instant.
    corps_ev = 15.0 * u
    for (nom, te), p in zip(evenements, pos_ev):
        x, y = proj(p[None, :])[0]
        d.ajouter(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{5 * u:.1f}" fill="{th["evenement"]}" '
                  f'stroke="{th["fond"]}" stroke-width="{1.2 * u:.2f}"/>', np.array([[x, y]]))
        libelle = f"{nom} · {_secondes(te)}"
        w = _largeur_texte(libelle, corps_ev)
        bx, by = x + 9 * u, y - 9 * u - corps_ev
        for _ in range(12):
            if d.libre((bx, by, bx + w + 10 * u, by + 1.45 * corps_ev)):
                break
            by += 1.6 * corps_ev
        if by > y - 9 * u - corps_ev:  # étiquette déplacée : un filet la relie à son point
            d.ajouter(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{bx:.1f}" y2="{by + 0.7 * corps_ev:.1f}" '
                      f'stroke="{th["evenement"]}" stroke-width="{u:.2f}"/>')
        d.ajouter(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{w + 10 * u:.1f}" height="{corps_ev * 1.45:.1f}" '
                  f'rx="{3 * u:.1f}" fill="{th["etiquette"]}" opacity="0.6"/>')
        d.texte(bx + 5 * u, by + 1.08 * corps_ev, libelle, corps_ev, th["texte"])
        d.occupe.append((bx, by, bx + w + 10 * u, by + 1.45 * corps_ev))
    # Instants des poses qui ne sont pas des événements.
    instants_ev = {round(te, 6) for _, te in evenements}
    if instants_poses:
        for tp, pp in zip(instants_poses, positions):
            if round(tp, 6) in instants_ev:
                continue
            x, y = proj(vers_ned(pp)[None, :])[0]
            d.texte(float(x + 12 * u), float(y + 4 * u), _secondes(tp), 12.0 * u, th["grille"])

    # Recadrage sur le contenu, puis titres au-dessus et légende en dessous.
    marge = 24 * u
    x0, y0 = d.mini - marge
    x1, y1 = d.maxi + marge
    # En-tête : chaque ligne (corps, interligne, couleur, texte) au-dessus du contenu.
    lignes = [(28 * u, 34 * u, th["texte"], titre), (18 * u, 26 * u, th["grille"], sous_titre)]
    lignes = [ligne for ligne in lignes if ligne[3]]
    hauteur_entete = sum(ligne[1] for ligne in lignes) + (18 * u if lignes else 0.0)
    y0 -= hauteur_entete
    entete, y = [], y0
    for corps, interligne, couleur, texte in lignes:
        y += interligne
        entete.append(f'<text x="{x0 + marge:.1f}" y="{y:.1f}" font-size="{corps:.1f}" '
                      f'fill="{couleur}">{escape(texte)}</text>')
    legende = (f"maquette agrandie × {echelle:.0f} · " if echelle > 1 else "") + \
        f"vol {_secondes(float(trajectoire.t[0]))} → {_secondes(float(trajectoire.t[-1]))} · repère NED"
    y1 += 22 * u
    largeur_min = max([_largeur_texte(legende, 13 * u)] + [_largeur_texte(ligne[3], ligne[0]) for ligne in lignes])
    x1 = max(x1, x0 + largeur_min + 2 * marge)
    pied = (f'<text x="{x1 - marge:.1f}" y="{y1 - marge / 2:.1f}" font-size="{13 * u:.1f}" '
            f'fill="{th["grille"]}" text-anchor="end">{escape(legende)}</text>')
    l_px, h_px = round(x1 - x0), round(y1 - y0)
    svg = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{l_px}" height="{h_px}" '
        f'viewBox="{x0:.1f} {y0:.1f} {x1 - x0:.1f} {y1 - y0:.1f}" font-family="{POLICE}">',
        f"<title>{escape(titre or 'Vue d’ensemble du vol')}</title>",
        f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" fill="{th["fond"]}"/>',
        *entete,
        *d.elements,
        pied,
        "</svg>",
        "",
    ])
    return Schema(svg=svg, largeur=l_px, hauteur=h_px, poses=instants_poses, echelle=echelle, faces=len(faces))
