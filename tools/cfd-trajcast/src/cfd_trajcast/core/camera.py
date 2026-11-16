"""Mathématiques de la caméra : où la placer à chaque image, en NumPy pur.

La scène est rendue en **origine flottante** : à chaque image, la fusée est à
l'origine et tout le reste est translaté de ``-position``. Une caméra se réduit
donc à un *décalage* par rapport à la fusée, ce qui garde la précision du tampon
de profondeur quelle que soit l'altitude.

Trois modes :

* ``poursuite`` — voir ci-dessous ;
* ``sol`` — caméra fixe au sol (position ENU absolue), qui suit la fusée du regard ;
  avec ``champ: auto``, elle zoome pour garder la fusée à ``cadrage`` de l'image ;
* ``embarquee`` — caméra liée au corps (position et visée en repère FRD) : elle
  roule avec la fusée, c'est voulu ;
* ``orbite`` — tourne autour de la fusée à vitesse angulaire constante (azimut
  compté depuis le Nord, repère terrestre : on fait le tour de la fusée, pas de sa route) ;
* ``images_cles`` — comme ``poursuite`` (repérée sur la route), mais azimut,
  élévation, distance et champ sont donnés à des instants de vol clés et
  interpolés en douceur entre eux (Hermite à tangentes nulles : chaque clé est un
  arrêt en douceur) ;
* ``ensemble`` — vue macro du vol entier dans un repère **NED** gradué, caméra fixe
  qui cadre toute la trajectoire ; la fusée y est agrandie pour rester visible.
  Pas d'origine flottante ici : la scène est en coordonnées NED absolues.

Mode ``poursuite`` : la caméra suit la fusée à distance fixe, dans une direction
repérée par rapport à sa **route** (direction horizontale de la vitesse), pas par
rapport à son attitude — sinon le roulis ferait tourner l'image. ``azimut`` = 0°
place la caméra derrière, 90° à droite de la route ; ``elevation`` la lève
au-dessus de l'horizontale. La route est lissée (constante de temps ``lissage``
en temps vidéo) pour que la caméra ne tressaute pas.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_trajcast.core import rotations as rot

__all__ = [
    "ENU_VERS_NED",
    "Cle",
    "ParametresEmbarquee",
    "ParametresEnsemble",
    "ParametresImagesCles",
    "ParametresOrbite",
    "ParametresPoursuite",
    "ParametresSol",
    "ParametresVue",
    "PisteCamera",
    "cadre_ensemble",
    "distance_auto",
    "echelle_ensemble",
    "piste",
    "piste_embarquee",
    "piste_images_cles",
    "piste_orbite",
    "piste_poursuite",
    "piste_sol",
    "route_lissee",
    "vers_ned",
]

Tableau = NDArray[np.float64]

_HAUT = np.array([0.0, 0.0, 1.0])
#: En dessous de cette vitesse horizontale (m/s), la route n'est pas définie.
VITESSE_HORIZONTALE_MIN = 0.5


@dataclass(frozen=True)
class ParametresPoursuite:
    """Caméra de poursuite. Angles en degrés, distance en mètres, lissage en secondes."""

    distance: float | None = None
    cadrage: float = 0.35
    azimut: float = 60.0
    elevation: float = 10.0
    lissage: float = 0.8
    champ: float = 30.0

    def __post_init__(self) -> None:
        if self.distance is not None and not self.distance > 0:
            raise ValueError("distance : une longueur positive, ou auto")
        if not 0 < self.cadrage <= 1:
            raise ValueError("cadrage : fraction de la hauteur d'image, dans ]0 ; 1]")
        if not -80 <= self.elevation <= 80:
            raise ValueError("elevation : entre -80° et 80° (la verticale n'a pas de « haut »)")
        if self.lissage < 0:
            raise ValueError("lissage : une durée positive ou nulle")
        if not 1 <= self.champ <= 120:
            raise ValueError("champ : angle de vue vertical entre 1° et 120°")


@dataclass(frozen=True, eq=False)
class PisteCamera:
    """Caméra à chaque image, en origine flottante (fusée à l'origine)."""

    decalage: Tableau
    visee: Tableau
    haut: Tableau
    champ: Tableau

    def __len__(self) -> int:
        return len(self.decalage)


def distance_auto(longueur: float, cadrage: float, champ: float) -> float:
    """Distance à laquelle une fusée de ``longueur`` (vue de flanc) occupe ``cadrage`` de l'image."""
    return float(longueur / (cadrage * 2 * np.tan(np.radians(champ) / 2)))


def route_lissee(vitesse: ArrayLike, t_video: ArrayLike, lissage: float) -> Tableau:
    """Direction horizontale unitaire de la route à chaque image, lissée.

    Là où la vitesse horizontale est trop faible (fusée verticale, à l'arrêt),
    la route est reprise de l'image la plus proche où elle est définie ; si elle
    ne l'est jamais, la caméra regarde vers le Nord.
    """
    v = np.asarray(vitesse, dtype=float)
    t = np.asarray(t_video, dtype=float)
    vh = v.copy()
    vh[:, 2] = 0.0
    norme = np.linalg.norm(vh, axis=1)
    definie = norme > max(VITESSE_HORIZONTALE_MIN, 0.0)
    route = np.full_like(vh, np.nan)
    route[definie] = vh[definie] / norme[definie, None]
    if not definie.any():
        route[:] = [0.0, 1.0, 0.0]
    else:
        indices = np.where(definie, np.arange(len(v)), -1)
        avant = np.maximum.accumulate(indices)
        premier = int(np.argmax(definie))
        avant[avant < 0] = premier
        route = route[avant]
    if lissage <= 0 or len(route) < 2:
        return route
    lisse = np.empty_like(route)
    lisse[0] = route[0]
    alpha = 1 - np.exp(-np.diff(t) / lissage)
    for i in range(1, len(route)):
        s = lisse[i - 1] + alpha[i - 1] * (route[i] - lisse[i - 1])
        n = np.linalg.norm(s)
        lisse[i] = s / n if n > 1e-9 else route[i]
    return lisse


def piste_poursuite(
    t_video: ArrayLike, vitesse: ArrayLike, longueur: float, p: ParametresPoursuite
) -> PisteCamera:
    """Caméra de poursuite pour chaque image."""
    route = route_lissee(vitesse, t_video, p.lissage)
    droite = np.cross(route, _HAUT)
    az, el = np.radians(p.azimut), np.radians(p.elevation)
    d = p.distance if p.distance is not None else distance_auto(longueur, p.cadrage, p.champ)
    direction = np.cos(el) * (-np.cos(az) * route + np.sin(az) * droite) + np.sin(el) * _HAUT
    n = len(route)
    return PisteCamera(
        decalage=d * direction,
        visee=np.zeros((n, 3)),
        haut=np.tile(_HAUT, (n, 1)),
        champ=np.full(n, float(p.champ)),
    )


@dataclass(frozen=True)
class ParametresSol:
    """Caméra fixe. ``position`` en ENU (m, origine à la rampe) ; ``champ`` None = auto."""

    position: tuple[float, float, float]
    champ: float | None = None
    cadrage: float = 0.25
    champ_min: float = 0.1
    champ_max: float = 60.0

    def __post_init__(self) -> None:
        if len(self.position) != 3:
            raise ValueError("position : [x, y, z] en ENU (m)")
        if not 0 < self.cadrage <= 1:
            raise ValueError("cadrage : fraction de la hauteur d'image, dans ]0 ; 1]")
        if not 0.1 <= self.champ_min < self.champ_max <= 120:
            raise ValueError("champ_min < champ_max, entre 0.1° et 120°")
        if self.champ is not None and not 0.1 <= self.champ <= 120:
            raise ValueError("champ : entre 0.1° et 120°, ou auto")


@dataclass(frozen=True)
class ParametresEmbarquee:
    """Caméra liée au corps : position et direction de visée en FRD (m, x vers le nez)."""

    position_corps: tuple[float, float, float] = (-1.0, 0.0, -0.2)
    visee: tuple[float, float, float] = (1.0, 0.0, 0.0)
    champ: float = 60.0

    def __post_init__(self) -> None:
        if len(self.position_corps) != 3 or len(self.visee) != 3:
            raise ValueError("position_corps et visee : trois composantes (FRD)")
        if np.linalg.norm(self.visee) == 0:
            raise ValueError("visee : direction non nulle")
        if not 1 <= self.champ <= 150:
            raise ValueError("champ : angle de vue vertical entre 1° et 150°")


@dataclass(frozen=True)
class ParametresEnsemble:
    """Vue d'ensemble NED. ``azimut`` (° depuis le Nord vers l'Est) : d'où l'on regarde ;
    None = auto (de flanc, un peu en arrière de la route moyenne). ``echelle_fusee`` :
    facteur d'agrandissement, None = auto (fusée ≈ ``part_fusee`` de l'étendue du vol)."""

    azimut: float | None = None
    elevation: float = 20.0
    cadrage: float = 0.85
    echelle_fusee: float | None = None
    part_fusee: float = 0.1
    champ: float = 30.0

    def __post_init__(self) -> None:
        if not -80 <= self.elevation <= 80:
            raise ValueError("elevation : entre -80° et 80°")
        if not 0 < self.cadrage <= 1.5:
            raise ValueError("cadrage : part du cadre occupée par le vol, dans ]0 ; 1.5]")
        if self.echelle_fusee is not None and not self.echelle_fusee > 0:
            raise ValueError("echelle_fusee : un facteur positif, ou auto")
        if not 0 < self.part_fusee <= 0.5:
            raise ValueError("part_fusee : dans ]0 ; 0.5]")
        if not 1 <= self.champ <= 120:
            raise ValueError("champ : angle de vue vertical entre 1° et 120°")


@dataclass(frozen=True)
class ParametresOrbite:
    """Orbite autour de la fusée. ``vitesse_angulaire`` en °/s de **vidéo**."""

    distance: float | None = None
    cadrage: float = 0.35
    azimut: float = 0.0
    elevation: float = 15.0
    vitesse_angulaire: float = 20.0
    champ: float = 30.0

    def __post_init__(self) -> None:
        if self.distance is not None and not self.distance > 0:
            raise ValueError("distance : une longueur positive, ou auto")
        if not 0 < self.cadrage <= 1:
            raise ValueError("cadrage : fraction de la hauteur d'image, dans ]0 ; 1]")
        if not -80 <= self.elevation <= 80:
            raise ValueError("elevation : entre -80° et 80°")
        if not 1 <= self.champ <= 120:
            raise ValueError("champ : angle de vue vertical entre 1° et 120°")


@dataclass(frozen=True)
class Cle:
    """Une image clé : à l'instant de vol ``t``, la caméra est ainsi placée."""

    t: float
    azimut: float = 60.0
    elevation: float = 10.0
    distance: float | None = None
    champ: float = 30.0

    def __post_init__(self) -> None:
        if not -80 <= self.elevation <= 80:
            raise ValueError("elevation : entre -80° et 80°")
        if self.distance is not None and not self.distance > 0:
            raise ValueError("distance : une longueur positive, ou auto")
        if not 1 <= self.champ <= 120:
            raise ValueError("champ : angle de vue vertical entre 1° et 120°")


@dataclass(frozen=True)
class ParametresImagesCles:
    """Caméra repérée sur la route, réglages interpolés entre des images clés."""

    cles: tuple[Cle, ...]
    cadrage: float = 0.35
    lissage: float = 0.8

    def __post_init__(self) -> None:
        if len(self.cles) < 1:
            raise ValueError("images_cles : au moins une clé")
        if any(b.t <= a.t for a, b in zip(self.cles, self.cles[1:])):
            raise ValueError("images_cles : instants `t` strictement croissants")
        if not 0 < self.cadrage <= 1:
            raise ValueError("cadrage : fraction de la hauteur d'image, dans ]0 ; 1]")


ParametresVue = Union[ParametresPoursuite, ParametresSol, ParametresEmbarquee, ParametresEnsemble,
                      ParametresOrbite, ParametresImagesCles]

#: ENU → NED (symétrique, déterminant +1) : ``p_NED = ENU_VERS_NED @ p_ENU``.
ENU_VERS_NED = np.array([[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, -1.0]])


def vers_ned(points_enu: ArrayLike) -> Tableau:
    """Points ou vecteurs ENU ``(..., 3)`` → NED."""
    return np.asarray(np.asarray(points_enu, dtype=float) @ ENU_VERS_NED.T, dtype=float)


def echelle_ensemble(positions_enu: ArrayLike, longueur: float, p: ParametresEnsemble) -> float:
    """Agrandissement de la fusée dans la vue d'ensemble (jamais en dessous de 1)."""
    if p.echelle_fusee is not None:
        return float(p.echelle_fusee)
    etendue = float(np.max(np.ptp(np.asarray(positions_enu, dtype=float), axis=0)))
    return max(1.0, p.part_fusee * etendue / longueur)


def cadre_ensemble(
    positions_enu: ArrayLike, p: ParametresEnsemble, aspect: float,
    boite_ned: tuple[ArrayLike, ArrayLike] | None = None,
) -> tuple[Tableau, Tableau, Tableau]:
    """Caméra fixe (position, point visé, haut) **en NED** qui cadre tout le vol.

    Les 8 coins de la boîte à montrer — celle du vol, sol compris, ou ``boite_ned``
    (mini, maxi) si on dessine une boîte graduée plus grande — tiennent dans le
    cadre réduit à ``cadrage`` ; ``aspect`` = largeur / hauteur de la case.
    """
    ned = vers_ned(positions_enu)
    if boite_ned is None:
        mini, maxi = ned.min(axis=0), ned.max(axis=0)
        maxi[2] = max(maxi[2], 0.0)  # le sol (D = 0) fait partie du cadre
    else:
        mini, maxi = (np.asarray(b, dtype=float) for b in boite_ned)
    centre = (mini + maxi) / 2
    if p.azimut is None:
        depl = ned[-1] - ned[0]
        cap = np.degrees(np.arctan2(depl[1], depl[0])) if np.hypot(depl[0], depl[1]) > 1e-6 else 0.0
        azimut = cap + 110.0
    else:
        azimut = p.azimut
    az, el = np.radians(azimut), np.radians(p.elevation)
    direction = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), -np.sin(el)])
    # Ajustement exact : chacun des 8 coins de la boîte doit tomber dans le cadre réduit à
    # `cadrage`, horizontalement et verticalement (une sphère englobante gaspille l'image
    # dès que le vol est bien plus haut que large).
    vers_camera = direction
    droite = np.cross(np.array([0.0, 0.0, -1.0]), -vers_camera)
    droite /= np.linalg.norm(droite)
    haut_ecran = np.cross(-vers_camera, droite)
    tan_v = np.tan(np.radians(p.champ) / 2) * p.cadrage
    tan_h = tan_v * aspect
    coins = np.array([[x, y, z] for x in (mini[0], maxi[0]) for y in (mini[1], maxi[1])
                      for z in (mini[2], maxi[2])]) - centre
    profondeur = coins @ vers_camera
    distance = float(np.max(np.concatenate([
        profondeur + np.abs(coins @ droite) / tan_h,
        profondeur + np.abs(coins @ haut_ecran) / tan_v,
    ])))
    distance = max(distance, 1.0)
    return centre + distance * direction, centre, np.array([0.0, 0.0, -1.0])


def piste_sol(positions: ArrayLike, longueur: float, p: ParametresSol) -> PisteCamera:
    """Caméra fixe qui regarde la fusée ; zoom automatique si ``champ`` est None."""
    pos = np.asarray(positions, dtype=float)
    decalage = np.asarray(p.position, dtype=float) - pos
    distance = np.linalg.norm(decalage, axis=1)
    if p.champ is None:
        champ = np.degrees(2 * np.arctan(longueur / (2 * p.cadrage * np.maximum(distance, 1e-6))))
        champ = np.clip(champ, p.champ_min, p.champ_max)
    else:
        champ = np.full(len(pos), float(p.champ))
    # Le « haut » de l'image est la verticale, sauf si l'on vise presque à la verticale.
    vise = -decalage / np.maximum(distance, 1e-9)[:, None]
    haut = np.tile(_HAUT, (len(pos), 1))
    quasi_vertical = np.abs(vise[:, 2]) > np.cos(np.radians(2.0))
    haut[quasi_vertical] = [0.0, 1.0, 0.0]
    return PisteCamera(decalage=decalage, visee=np.zeros_like(decalage), haut=haut, champ=champ)


def piste_embarquee(attitudes: ArrayLike, p: ParametresEmbarquee) -> PisteCamera:
    """Caméra solidaire du corps (``attitudes`` : quaternions corps FRD → ENU)."""
    r = rot.vers_matrice(attitudes)
    position = r @ np.asarray(p.position_corps, dtype=float)
    visee = np.asarray(p.visee, dtype=float) / np.linalg.norm(p.visee)
    n = len(r)
    return PisteCamera(
        decalage=position,
        visee=position + r @ visee,
        haut=r @ np.array([0.0, 0.0, -1.0]),
        champ=np.full(n, float(p.champ)),
    )


def piste_orbite(t_video: ArrayLike, longueur: float, p: ParametresOrbite) -> PisteCamera:
    """Caméra qui tourne autour de la fusée (azimut depuis le Nord, vers l'Est)."""
    t = np.asarray(t_video, dtype=float)
    az = np.radians(p.azimut + p.vitesse_angulaire * t)
    el = np.radians(p.elevation)
    d = p.distance if p.distance is not None else distance_auto(longueur, p.cadrage, p.champ)
    decalage = d * np.stack([np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.full_like(az, np.sin(el))], axis=1)
    n = len(t)
    return PisteCamera(decalage=decalage, visee=np.zeros((n, 3)), haut=np.tile(_HAUT, (n, 1)),
                       champ=np.full(n, float(p.champ)))


def _hermite(t: Tableau, cles_t: Tableau, valeurs: Tableau) -> Tableau:
    """Interpolation par morceaux à tangentes nulles (smoothstep), constante hors des clés."""
    if len(cles_t) == 1:
        return np.full_like(t, valeurs[0])
    k = np.clip(np.searchsorted(cles_t, t, side="right") - 1, 0, len(cles_t) - 2)
    u = np.clip((t - cles_t[k]) / (cles_t[k + 1] - cles_t[k]), 0.0, 1.0)
    s = u * u * (3 - 2 * u)
    return np.asarray(valeurs[k] + s * (valeurs[k + 1] - valeurs[k]), dtype=float)


def piste_images_cles(t_video: ArrayLike, t_vol: ArrayLike, vitesse: ArrayLike, longueur: float,
                      p: ParametresImagesCles) -> PisteCamera:
    """Caméra repérée sur la route, réglages interpolés entre les clés (en temps de vol)."""
    tv = np.asarray(t_vol, dtype=float)
    cles_t = np.array([c.t for c in p.cles])
    azimuts = np.unwrap(np.radians([c.azimut for c in p.cles]))
    az = _hermite(tv, cles_t, azimuts)
    el = np.radians(_hermite(tv, cles_t, np.array([c.elevation for c in p.cles])))
    champ = _hermite(tv, cles_t, np.array([c.champ for c in p.cles]))
    distances = np.array([c.distance if c.distance is not None else distance_auto(longueur, p.cadrage, c.champ)
                          for c in p.cles])
    d = _hermite(tv, cles_t, distances)
    route = route_lissee(vitesse, t_video, p.lissage)
    droite = np.cross(route, _HAUT)
    direction = (np.cos(el) * (-np.cos(az)))[:, None] * route + (np.cos(el) * np.sin(az))[:, None] * droite \
        + np.sin(el)[:, None] * _HAUT
    n = len(tv)
    return PisteCamera(decalage=d[:, None] * direction, visee=np.zeros((n, 3)),
                       haut=np.tile(_HAUT, (n, 1)), champ=champ)


def piste(
    p: ParametresVue, *, t_video: ArrayLike, positions: ArrayLike, attitudes: ArrayLike,
    vitesses: ArrayLike, longueur: float, t_vol: ArrayLike | None = None,
) -> PisteCamera:
    """La piste de n'importe quelle vue (sauf ``ensemble``, à caméra fixe)."""
    if isinstance(p, ParametresOrbite):
        return piste_orbite(t_video, longueur, p)
    if isinstance(p, ParametresImagesCles):
        if t_vol is None:
            raise ValueError("images_cles : t_vol requis")
        return piste_images_cles(t_video, t_vol, vitesses, longueur, p)
    if isinstance(p, ParametresPoursuite):
        return piste_poursuite(t_video, vitesses, longueur, p)
    if isinstance(p, ParametresSol):
        return piste_sol(positions, longueur, p)
    if isinstance(p, ParametresEmbarquee):
        return piste_embarquee(attitudes, p)
    raise TypeError("la vue d'ensemble n'a pas de piste : sa caméra est fixe (cadre_ensemble)")
