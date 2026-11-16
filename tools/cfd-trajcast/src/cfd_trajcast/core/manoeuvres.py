"""Trajectoires synthétiques par manœuvres : un point matériel piloté, en NumPy pur.

Sert à fabriquer des scénarios d'exemple et de test (avion qui décolle et
manœuvre, avion en panne qui part en spirale, fusée à deux étages) **sans**
dépendre d'un code de mécanique du vol. Ce n'est pas un simulateur de vol : pas
d'aérodynamique réelle, mais une cinématique cohérente — l'attitude découle des
efforts (portance, poussée, pesanteur), ce qui donne des vidéos crédibles.

Modèle, repère ENU :

    a = (T − k·V²)·x̂  +  n·g₀·(−ẑ_w)  +  g

* ``x̂`` : direction de la vitesse ; ``ẑ_w`` : « bas » du repère aérodynamique,
  incliné de ``μ`` (inclinaison, positive aile droite basse) autour de ``x̂`` ;
* ``T`` : poussée spécifique (m/s²), donnée ou asservie sur une vitesse visée ;
* ``n`` : facteur de charge (portance / poids), donné ou asservi sur une pente ;
* ``k·V²`` : traînée, ``g`` : pesanteur.

L'attitude du corps est le repère aérodynamique cabré de l'incidence ``α``
(``α = incidence_par_g × n``, nulle pour une fusée) : x corps vers le nez.

Chaque :class:`Segment` dure ``duree`` secondes et fixe des consignes ; les
commandes y convergent avec des constantes de temps, donc sans à-coup. Le sol
(z = 0) arrête la chute et porte l'avion au roulage.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.atmosphere import G0, mach

__all__ = ["Conditions", "Mobile", "Segment", "Simulation", "simuler"]

Tableau = NDArray[np.float64]
_HAUT = np.array([0.0, 0.0, 1.0])


@dataclass(frozen=True)
class Mobile:
    """Paramètres du mobile simulé (avion par défaut ; ``Mobile.fusee()`` pour une fusée)."""

    trainee: float = 1.5e-4           # k (1/m) : traînée spécifique = k·V²
    incidence_par_g: float = 2.5      # ° d'incidence par g de facteur de charge
    n_min: float = -3.0
    n_max: float = 7.5
    taux_roulis_max: float = 150.0    # °/s
    tau_roulis: float = 0.8           # s
    tau_charge: float = 0.6           # s
    tau_vitesse: float = 4.0          # s
    gain_pente: float = 1.2           # 1/s : n corrige l'écart de pente
    gain_cap: float = 2.0             # ° d'inclinaison par ° d'écart de cap
    inclinaison_max: float = 60.0     # ° (asservissement de cap)

    @classmethod
    def fusee(cls) -> Mobile:
        """Pas de portance par défaut, pas d'incidence, très peu de traînée."""
        return cls(trainee=2e-5, incidence_par_g=0.0, n_min=-1.0, n_max=1.0, taux_roulis_max=720.0)


@dataclass(frozen=True)
class Conditions:
    """État initial : position ENU (m), vitesse (m/s), cap et pente de la vitesse, inclinaison (°),
    facteur de charge (1 pour un avion en palier, 0 pour une fusée sur sa rampe)."""

    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    vitesse: float = 1.0
    cap: float = 0.0
    pente: float = 0.0
    inclinaison: float = 0.0
    facteur_charge: float = 1.0


@dataclass(frozen=True)
class Segment:
    """Consignes tenues pendant ``duree`` s ; ``nom`` devient un événement au début du segment.

    Poussée : ``vitesse`` (m/s visée) **ou** ``poussee`` (m/s², fixe). Trajectoire
    verticale : ``pente`` (° visée) **ou** ``facteur_charge`` (fixe). Latérale :
    ``cap`` (° visé, l'inclinaison s'en déduit) **ou** ``inclinaison`` (° visée)
    **ou** ``taux_roulis`` (°/s imposé : tonneau, boucle sans roulis, vrille).
    Une consigne absente reprend la valeur du segment précédent.
    """

    duree: float
    nom: str = ""
    vitesse: float | None = None
    poussee: float | None = None
    pente: float | None = None
    facteur_charge: float | None = None
    cap: float | None = None
    inclinaison: float | None = None
    taux_roulis: float | None = None
    au_sol: bool = False

    def __post_init__(self) -> None:
        if not self.duree > 0:
            raise ValueError("segment : duree > 0")
        for a, b in (("vitesse", "poussee"), ("pente", "facteur_charge")):
            if getattr(self, a) is not None and getattr(self, b) is not None:
                raise ValueError(f"segment : {a} et {b} s'excluent")
        if sum(getattr(self, k) is not None for k in ("cap", "inclinaison", "taux_roulis")) > 1:
            raise ValueError("segment : cap, inclinaison et taux_roulis s'excluent")


@dataclass(frozen=True, eq=False)
class Simulation:
    """Trajectoire échantillonnée : temps, positions ENU, vitesses ENU, quaternions corps FRD → ENU."""

    t: Tableau
    positions: Tableau
    vitesses: Tableau
    attitudes: Tableau
    donnees: dict[str, Tableau] = field(default_factory=dict)
    evenements: tuple[tuple[float, str], ...] = ()


def _rotation_axe(v: Tableau, axe: Tableau, angle: float) -> Tableau:
    """Rotation de ``v`` autour de ``axe`` unitaire (Rodrigues)."""
    c, s = np.cos(angle), np.sin(angle)
    return np.asarray(v * c + np.cross(axe, v) * s + axe * float(axe @ v) * (1 - c))


def _bas_horizontal(x: Tableau, precedent: Tableau) -> Tableau:
    """« Bas » à inclinaison nulle : la verticale descendante, rendue perpendiculaire à ``x``."""
    d = -_HAUT - float(-_HAUT @ x) * x
    n = np.linalg.norm(d)
    return precedent if n < 1e-6 else d / n


def _inclinaison(x: Tableau, z_w: Tableau, d0: Tableau) -> float:
    """Angle signé de ``d0`` à ``z_w`` autour de ``x`` (positif : aile droite basse)."""
    return float(np.arctan2(float(np.cross(d0, z_w) @ x), float(d0 @ z_w)))


def simuler(conditions: Conditions, segments: Sequence[Segment], mobile: Mobile | None = None,
            *, pas: float = 0.005, sortie: float = 0.05, arret_sous: float | None = None) -> Simulation:
    """Intègre les segments ; échantillonne toutes les ``sortie`` s.

    ``arret_sous`` : arrête la simulation quand l'altitude passe sous cette cote
    (après avoir décollé), pour un scénario qui finit en chute.
    """
    m = mobile or Mobile()
    cap0, pente0, mu0 = np.radians([conditions.cap, conditions.pente, conditions.inclinaison])
    x = np.array([np.sin(cap0) * np.cos(pente0), np.cos(cap0) * np.cos(pente0), np.sin(pente0)])
    p = np.asarray(conditions.position, dtype=float)
    v = x * max(conditions.vitesse, 1e-3)
    d0 = _bas_horizontal(x, np.array([0.0, 0.0, -1.0]) if abs(x[2]) < 0.999 else np.array([0.0, -1.0, 0.0]))
    z_w = _rotation_axe(d0, x, mu0)
    n, poussee = float(conditions.facteur_charge), 0.0
    consignes: dict[str, float | None] = {k: None for k in
                                          ("vitesse", "poussee", "pente", "facteur_charge", "cap", "inclinaison",
                                           "taux_roulis")}
    t = 0.0
    sorties: dict[str, list[float]] = {k: [] for k in
                                       ("V", "mach", "altitude", "n", "inclinaison", "pente", "cap", "incidence")}
    T, P, V, Q = [], [], [], []
    evenements = []
    a_decolle = p[2] > 1.0

    def enregistrer(t: float, p: Tableau, v: Tableau, z_w: Tableau, n: float, au_sol: bool, d0: Tableau) -> None:
        vit = float(np.linalg.norm(v))
        x_n = v / max(vit, 1e-9)
        incidence = 0.0 if au_sol else np.radians(m.incidence_par_g) * n
        y_w = np.cross(z_w, x_n)
        corps = np.stack([x_n, y_w, z_w], axis=1)       # colonnes : axes aéro en ENU
        c, s_ = np.cos(incidence), np.sin(incidence)
        cabre = np.array([[c, 0, s_], [0, 1, 0], [-s_, 0, c]])  # rotation de +α autour de y
        Q.append(rot.depuis_matrice(corps @ cabre))
        T.append(round(t, 6))
        P.append(p.copy())
        V.append(v.copy())
        for k, val in (("V", vit), ("mach", float(mach(vit, p[2]))), ("altitude", p[2]), ("n", n),
                       ("inclinaison", np.degrees(_inclinaison(x_n, z_w, _bas_horizontal(x_n, d0)))),
                       ("pente", np.degrees(np.arcsin(np.clip(x_n[2], -1, 1)))),
                       ("cap", np.degrees(np.arctan2(x_n[0], x_n[1])) % 360),
                       ("incidence", np.degrees(incidence))):
            sorties[k].append(float(val))

    enregistrer(0.0, p, v, z_w, n, bool(segments and segments[0].au_sol), d0)
    prochain = sortie
    for seg in segments:
        if seg.nom:
            evenements.append((round(t, 6), seg.nom))
        for groupe in (("vitesse", "poussee"), ("pente", "facteur_charge"), ("cap", "inclinaison", "taux_roulis")):
            if any(getattr(seg, k) is not None for k in groupe):
                for k in groupe:
                    consignes[k] = getattr(seg, k)
        fin = t + seg.duree
        while t < fin - 1e-9:
            vit = float(np.linalg.norm(v))
            x = v / vit
            d0 = _bas_horizontal(x, d0)
            mu = _inclinaison(x, z_w, d0)
            gamma = float(np.arcsin(np.clip(x[2], -1, 1)))
            cap = float(np.arctan2(x[0], x[1]))
            # Roulis.
            if consignes["taux_roulis"] is not None:
                taux = np.radians(consignes["taux_roulis"])
            else:
                if consignes["cap"] is not None:
                    ecart = (np.radians(consignes["cap"]) - cap + np.pi) % (2 * np.pi) - np.pi
                    cible = np.clip(m.gain_cap * ecart, -np.radians(m.inclinaison_max), np.radians(m.inclinaison_max))
                else:
                    cible = np.radians(consignes["inclinaison"] or 0.0)
                erreur = (cible - mu + np.pi) % (2 * np.pi) - np.pi
                taux = erreur / m.tau_roulis
            taux = float(np.clip(taux, -np.radians(m.taux_roulis_max), np.radians(m.taux_roulis_max)))
            z_w = _rotation_axe(z_w, x, taux * pas)
            # Facteur de charge.
            cos_mu = np.cos(mu) if abs(np.cos(mu)) > 0.25 else 0.25 * np.sign(np.cos(mu) or 1.0)
            if consignes["facteur_charge"] is not None:
                n_cible = consignes["facteur_charge"]
            elif consignes["pente"] is not None:
                n_cible = (np.cos(gamma) + m.gain_pente * (np.radians(consignes["pente"]) - gamma) * vit / G0) / cos_mu
            else:
                n_cible = np.cos(gamma) / cos_mu
            if seg.au_sol:
                n_cible = 1.0
            n += (float(np.clip(n_cible, m.n_min, m.n_max)) - n) * min(1.0, pas / m.tau_charge)
            # Poussée.
            trainee = m.trainee * vit**2
            if consignes["poussee"] is not None:
                poussee = consignes["poussee"]
            elif consignes["vitesse"] is not None:
                poussee = G0 * np.sin(gamma) + trainee + (consignes["vitesse"] - vit) / m.tau_vitesse
            a = (poussee - trainee) * x + n * G0 * (-z_w) - G0 * _HAUT
            v = v + a * pas
            p = p + v * pas
            if p[2] <= 0.0:                      # le sol porte
                p[2] = 0.0
                v[2] = max(v[2], 0.0)
            a_decolle = a_decolle or p[2] > 5.0
            vit = float(np.linalg.norm(v))
            x_n = v / max(vit, 1e-9)
            z_w = z_w - float(z_w @ x_n) * x_n
            z_w /= np.linalg.norm(z_w)
            t += pas
            if t >= prochain - 1e-9:
                prochain += sortie
                enregistrer(t, p, v, z_w, n, seg.au_sol, d0)
            if arret_sous is not None and a_decolle and p[2] < arret_sous:
                break
        if arret_sous is not None and a_decolle and p[2] < arret_sous:
            if T[-1] < round(t, 6):
                enregistrer(t, p, v, z_w, n, seg.au_sol, d0)   # l'état sous la cote d'arrêt
            break
    q, _ = rot.continuite_hemisphere(np.array(Q))
    return Simulation(t=np.array(T), positions=np.array(P), vitesses=np.array(V), attitudes=q,
                      donnees={k: np.array(x_) for k, x_ in sorties.items()}, evenements=tuple(evenements))
