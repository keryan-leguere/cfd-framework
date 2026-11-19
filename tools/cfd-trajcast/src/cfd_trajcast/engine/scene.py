"""Le plan de tournage : ce que chaque image montre, indépendamment du moteur de rendu.

Un :class:`Plan` fixe, pour chaque image de la vidéo, l'instant de vol, la pose de
la fusée, la caméra de chaque vue (en origine flottante) et la disposition des vues. La :class:`Scene` y ajoute ce qui
ne change pas d'une image à l'autre : maquette, tracé du vol, sol, fond. Les
moteurs (PyVista, plus tard bpy) ne font que dessiner ce qu'on leur décrit.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core.camera import ParametresEnsemble, ParametresVue, PisteCamera, pas_rond, piste
from cfd_trajcast.core.disposition import Case, Disposition, agencer
from cfd_trajcast.core.temps import instants_de_vol
from cfd_trajcast.data.configuration import (
    ConfigPropulsion,
    ConfigStyle,
    ConfigVideo,
    EtapeSequence,
    Fumee,
    Jet,
    PhasePropulsion,
)
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.engine.jets import Phase

__all__ = [
    "THEMES_ENSEMBLE",
    "ErreurPlan",
    "Plan",
    "Propulsion",
    "Scene",
    "construire_scene",
    "grille_sol",
    "pas_rond",
    "planifier",
    "recaler",
    "resoudre_propulsion",
]

Tableau = NDArray[np.float64]

#: Couleurs de la vue d'ensemble (``style.ensemble``), partagées par la vidéo et le schéma SVG.
THEMES_ENSEMBLE: dict[str, dict[str, str]] = {
    "clair": {"fond": "#f3f5f8", "sol": "#d5dde4", "trace_sol": "#9aa7b4", "trace": "#7d8b99",
              "texte": "#1f2a36", "etiquette": "grey", "fusee": "#1f3b57", "grille": "#4a5866",
              "parcouru": "#ff7a1a", "evenement": "#1f77b4"},
    "sombre": {"fond": "#0b1220", "sol": "#1c2a3a", "trace_sol": "#3d5068", "trace": "#6c7f95",
               "texte": "#e8eef5", "etiquette": "#1c2a3a", "fusee": "#dfe6ee", "grille": "#9fb0c2",
               "parcouru": "#ff7a1a", "evenement": "#1f77b4"},
}

#: Points du tracé du vol dessiné en fond.
POINTS_TRACE = 4000


class ErreurPlan(ValueError):
    """Intervalle ou cadence impossibles."""


@dataclass(frozen=True, eq=False)
class Plan:
    """Une ligne par image de la vidéo.

    ``cameras`` : une piste par vue. ``agencements`` : une disposition (en pixels)
    par étape de la séquence ; ``etape[k]`` dit laquelle montre l'image ``k``.
    Pendant un fondu, ``fondu[k]`` > 0 est le poids de l'agencement précédent,
    ``etape_prec[k]``.
    """

    t_video: Tableau
    t_vol: Tableau
    positions: Tableau
    attitudes: Tableau
    cameras: dict[str, PisteCamera]
    ensembles: dict[str, ParametresEnsemble]
    agencements: tuple[tuple[Case, ...], ...]
    etape: NDArray[np.int64]
    etape_prec: NDArray[np.int64]
    fondu: Tableau
    ips: float
    largeur: int
    hauteur: int

    def __len__(self) -> int:
        return len(self.t_video)

    def vues_utiles(self, k: int) -> list[Case]:
        """Cases à dessiner pour l'image ``k`` (les deux agencements pendant un fondu)."""
        cases = list(self.agencements[int(self.etape[k])])
        if self.fondu[k] > 0:
            cases += self.agencements[int(self.etape_prec[k])]
        return cases


@dataclass(frozen=True, eq=False)
class Propulsion:
    """Propulsion résolue : tuyères (FRD, m), rayon (m), phases aux instants de vol, fondu (s)."""

    tuyeres: Tableau
    rayon: float
    phases: tuple[Phase, ...]
    fondu: float


def _instant(v: float | str | None, traj: Trajectoire, ou: str, defaut: float) -> float:
    if v is None:
        return defaut
    if isinstance(v, str):
        instants = {e.nom: e.t for e in traj.evenements}
        if v not in instants:
            raise ValueError(f"{ou} : événement « {v} » inconnu ; événements : {', '.join(instants) or 'aucun'}")
        return float(instants[v])
    return float(v)


def resoudre_propulsion(cfg: ConfigPropulsion | None, traj: Trajectoire, maquette: Maquette,
                        style: ConfigStyle) -> Propulsion | None:
    """Noms d'événements → instants, tuyère et rayon par défaut ; ``style.trainee`` (ancienne
    écriture, une fumée seule) devient une phase."""
    t0, t1 = float(traj.t[0]), float(traj.t[-1])
    if cfg is None:
        if not style.trainee:
            return None
        rayon = style.trainee_rayon or 0.04 * maquette.taille
        fumee_seule = Fumee(couleur_debut=style.trainee_couleur, couleur_fin=style.trainee_couleur,
                            opacite=0.85, duree=style.trainee_duree, rayon=1.0,
                            expansion=style.trainee_croissance * rayon, turbulence=0.0)
        a = _instant(style.trainee_jusqu_a, traj, "style.trainee.jusqu_a", t1)
        cfg = ConfigPropulsion(rayon_tuyere=rayon, phases=(PhasePropulsion(de=t0, a=a, jet=Jet(None, fumee_seule)),),
                               fondu=0.0)
    if cfg.tuyeres is None:
        culot = maquette.sommets[:, 0].min()
        tuyeres = np.array([[culot, 0.0, 0.0]])
    else:
        tuyeres = np.asarray(cfg.tuyeres, dtype=float)
    phases = []
    for k, p in enumerate(cfg.phases):
        de = _instant(p.de, traj, f"propulsion.phases[{k}].de", t0)
        a = _instant(p.a, traj, f"propulsion.phases[{k}].a", t1)
        if not de < a:
            raise ValueError(f"propulsion.phases[{k}] : début {de:g} s après la fin {a:g} s")
        phases.append(Phase(de=de, a=a, jet=p.jet))
    return Propulsion(tuyeres=tuyeres, rayon=cfg.rayon_tuyere or 0.04 * maquette.taille,
                      phases=tuple(phases), fondu=cfg.fondu)


@dataclass(frozen=True, eq=False)
class Scene:
    """Ce qui ne change pas d'une image à l'autre (coordonnées ENU absolues)."""

    maquette: Maquette
    trace: Tableau | None = None
    #: Instants de vol des points de ``trace`` (pour dessiner la partie parcourue).
    trace_t: Tableau | None = None
    sol: tuple[Tableau, NDArray[np.int64]] | None = None
    fond: str = "#dfe6ee"
    couleur_fusee: str = "#d0d0d0"
    #: (nom, position ENU) des événements, marqués dans la vue d'ensemble.
    evenements: tuple[tuple[str, tuple[float, float, float]], ...] = ()
    #: Attitude aux points de ``trace`` (point d'émission de la traînée).
    trace_attitudes: Tableau | None = None
    style: ConfigStyle = ConfigStyle()  # noqa: RUF009 (gelée)
    propulsion: Propulsion | None = None


def planifier(
    traj: Trajectoire,
    maquette: Maquette,
    video: ConfigVideo,
    vues: Sequence[tuple[str, ParametresVue]],
    disposition: Disposition | None = None,
    sequence: Sequence[EtapeSequence] = (),
    *,
    fondu: float = 0.5,
    de: float | None = None,
    a: float | None = None,
) -> Plan:
    """Instants, poses, caméras et agencements de chaque image pour le vol ``[de ; a]``."""
    t0 = float(traj.t[0]) if de is None else float(de)
    t1 = float(traj.t[-1]) if a is None else float(a)
    if not traj.t[0] <= t0 < t1 <= traj.t[-1]:
        raise ErreurPlan(
            f"intervalle [{t0:g} ; {t1:g}] s invalide : il doit être croissant et dans le vol "
            f"[{traj.t[0]:g} ; {traj.t[-1]:g}] s"
        )
    if not vues:
        raise ErreurPlan("aucune vue")
    if video.duree is not None:
        vitesse = (t1 - t0) / video.duree
    else:
        vitesse = 1.0 if video.vitesse is None else video.vitesse
    t_vol = instants_de_vol(t0, t1, video.ips, vitesse, video.ralentis, video.transition_ralenti)
    n = len(t_vol)
    t_video = np.arange(n) / video.ips
    positions, attitudes = traj.etat(t_vol)
    vitesses = traj.vitesse_a(t_vol)
    cameras = {
        nom: piste(p, t_video=t_video, positions=positions, attitudes=attitudes,
                   vitesses=vitesses, longueur=maquette.taille, t_vol=t_vol)
        for nom, p in vues if not isinstance(p, ParametresEnsemble)
    }
    ensembles = {nom: p for nom, p in vues if isinstance(p, ParametresEnsemble)}
    if disposition is None:
        disposition = Disposition(type="unique", principale=vues[0][0])
    largeur, hauteur = video.resolution
    etapes = [EtapeSequence(de=-np.inf, disposition=disposition), *sequence]
    agencements = tuple(agencer(e.disposition, largeur, hauteur) for e in etapes)
    debuts = np.array([float(e.de) for e in etapes])
    etape = np.searchsorted(debuts, t_vol, side="right") - 1
    etape_prec = etape.copy()
    poids = np.zeros(n)
    n_fondu = max(0, round(fondu * video.ips))
    for k in np.flatnonzero(np.diff(etape)) + 1:
        if etapes[int(etape[k])].transition != "fondu" or n_fondu == 0:
            continue
        for j in range(n_fondu):
            if k + j >= n or etape[k + j] != etape[k]:
                break
            etape_prec[k + j] = etape[k - 1]
            poids[k + j] = 1 - (j + 1) / (n_fondu + 1)
    return Plan(t_video=t_video, t_vol=t_vol, positions=positions, attitudes=attitudes,
                cameras=cameras, ensembles=ensembles, agencements=agencements, etape=etape.astype(np.int64),
                etape_prec=etape_prec.astype(np.int64), fondu=poids, ips=video.ips,
                largeur=largeur, hauteur=hauteur)


def recaler(plan: Plan, traj: Trajectoire, maquette: Maquette,
            vues: Sequence[tuple[str, ParametresVue]], k: int, t: float) -> Plan:
    """Le plan dont l'image ``k`` montre exactement l'instant de vol ``t`` (caméras comprises)."""
    t_vol = plan.t_vol.copy()
    t_vol[k] = t
    positions, attitudes = traj.etat(t_vol)
    vitesses = traj.vitesse_a(t_vol)
    cameras = {
        nom: piste(p, t_video=plan.t_video, positions=positions, attitudes=attitudes,
                   vitesses=vitesses, longueur=maquette.taille, t_vol=t_vol)
        for nom, p in vues if not isinstance(p, ParametresEnsemble)
    }
    return replace(plan, t_vol=t_vol, positions=positions, attitudes=attitudes, cameras=cameras)


def grille_sol(positions: Tableau, marge: float = 2000.0, lignes_max: int = 120,
               altitude: float = 0.0) -> tuple[Tableau, NDArray[np.int64]]:
    """Quadrillage du sol (z = ``altitude``) couvrant la trace au sol du vol : points et segments."""
    mini = positions[:, :2].min(axis=0) - marge
    maxi = positions[:, :2].max(axis=0) + marge
    pas = pas_rond(float(np.max(maxi - mini)) / (lignes_max / 2))
    mini = np.floor(mini / pas) * pas
    maxi = np.ceil(maxi / pas) * pas
    points: list[list[float]] = []
    for x in np.arange(mini[0], maxi[0] + pas / 2, pas):
        points += [[x, mini[1], altitude], [x, maxi[1], altitude]]
    for y in np.arange(mini[1], maxi[1] + pas / 2, pas):
        points += [[mini[0], y, altitude], [maxi[0], y, altitude]]
    pts = np.array(points)
    segments = np.arange(len(pts), dtype=np.int64).reshape(-1, 2)
    return pts, segments


def construire_scene(traj: Trajectoire, maquette: Maquette, style: ConfigStyle | None = None,
                     propulsion: Propulsion | None = None) -> Scene:
    """La fusée, le tracé du vol (60 points par seconde au moins), le sol, le style."""
    style = style or ConfigStyle()
    n = max(POINTS_TRACE, int(60 * (traj.t[-1] - traj.t[0])))
    t = np.linspace(traj.t[0], traj.t[-1], n)
    trace, attitudes = traj.etat(t)
    evenements = tuple(
        (e.nom, tuple(float(v) for v in traj.etat(np.array([e.t]))[0][0]))
        for e in traj.evenements if traj.t[0] <= e.t <= traj.t[-1]
    )
    return Scene(maquette=maquette, trace=trace, trace_t=t,
                 sol=grille_sol(traj.positions, altitude=style.sol_altitude),
                 evenements=evenements, trace_attitudes=attitudes, style=style,  # type: ignore[arg-type]
                 fond=style.ciel_bas, couleur_fusee=style.fusee_couleur, propulsion=propulsion)

