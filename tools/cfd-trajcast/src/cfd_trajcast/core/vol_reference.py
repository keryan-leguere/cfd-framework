"""Vol de référence analytique : position, vitesse et attitude exactes à tout instant.

Sert aux tests (toute lecture du même vol, quelle que soit sa convention, doit
retomber sur ces valeurs) et à l'exemple livré. Deux phases en forme fermée :

1. **propulsion** (``0 ≤ t ≤ t_p``) : poussée d'accélération constante ``a`` selon
   la direction de rampe ``u``, plus la pesanteur. L'accélération totale
   ``a·u − g·ẑ`` est constante, donc la trajectoire est une **droite** parcourue
   en ``½·A·t²`` ;
2. **balistique** (``t > t_p``) : parabole, la vitesse horizontale est conservée.

L'axe de la fusée suit la vitesse (incidence nulle) et elle roule à vitesse
constante. En angles d'Euler ZYX par rapport au NED, corps FRD : lacet = cap,
tangage = pente de la vitesse, roulis = ``ω·t``. Le vol n'est pas réaliste
(pas de traînée) ; il est *exact*, c'est tout ce qu'on lui demande.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike, NDArray

from cfd_trajcast.core import reperes
from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.atmosphere import mach, masse_volumique

__all__ = ["VolReference"]

Tableau = NDArray[np.float64]


@dataclass(frozen=True)
class VolReference:
    """Paramètres du vol ; toutes les grandeurs en SI, angles en degrés."""

    acceleration_poussee: float = 100.0
    duree_propulsion: float = 4.0
    elevation_rampe: float = 84.0
    cap: float = 30.0
    vitesse_roulis: float = 90.0
    g: float = 9.80665

    # -- géométrie de la phase propulsée -------------------------------------------
    def _rampe(self) -> Tableau:
        el, cap = np.radians(self.elevation_rampe), np.radians(self.cap)
        return np.array([np.sin(cap) * np.cos(el), np.cos(cap) * np.cos(el), np.sin(el)], dtype=float)

    def _acceleration_propulsee(self) -> Tableau:
        return np.asarray(self.acceleration_poussee * self._rampe() - np.array([0.0, 0.0, self.g]), dtype=float)

    def _etat_fin_propulsion(self) -> tuple[Tableau, Tableau]:
        a, tp = self._acceleration_propulsee(), self.duree_propulsion
        return 0.5 * a * tp**2, a * tp

    # -- instants remarquables -----------------------------------------------------
    @property
    def t_apogee(self) -> float:
        """Instant de l'apogée (s)."""
        _, v = self._etat_fin_propulsion()
        return self.duree_propulsion + float(v[2]) / self.g

    @property
    def t_mach_1(self) -> float:
        """Premier passage à Mach 1 (s), ``nan`` s'il n'a pas lieu avant l'apogée."""
        t = np.linspace(0.0, self.t_apogee, 20_001)
        m = self.mach(t) - 1.0
        i = np.flatnonzero((m[:-1] < 0) & (m[1:] >= 0))
        if len(i) == 0:
            return float("nan")
        k = int(i[0])
        return float(t[k] - m[k] * (t[k + 1] - t[k]) / (m[k + 1] - m[k]))

    # -- états ----------------------------------------------------------------------
    def position(self, t: ArrayLike) -> Tableau:
        """Position ENU (m), ``(N, 3)``."""
        tt = np.atleast_1d(np.asarray(t, dtype=float))[:, None]
        a, tp = self._acceleration_propulsee(), self.duree_propulsion
        pb, vb = self._etat_fin_propulsion()
        dt = tt - tp
        balistique = pb + vb * dt - 0.5 * self.g * dt**2 * np.array([0.0, 0.0, 1.0])
        return np.asarray(np.where(tt <= tp, 0.5 * a * tt**2, balistique), dtype=float)

    def vitesse(self, t: ArrayLike) -> Tableau:
        """Vitesse ENU (m/s), ``(N, 3)``."""
        tt = np.atleast_1d(np.asarray(t, dtype=float))[:, None]
        a, tp = self._acceleration_propulsee(), self.duree_propulsion
        _, vb = self._etat_fin_propulsion()
        balistique = vb - self.g * (tt - tp) * np.array([0.0, 0.0, 1.0])
        return np.where(tt <= tp, a * tt, balistique)

    def acceleration(self, t: ArrayLike) -> Tableau:
        """Accélération ENU (m/s²), ``(N, 3)`` (discontinue à la fin de propulsion)."""
        tt = np.atleast_1d(np.asarray(t, dtype=float))[:, None]
        chute = np.array([0.0, 0.0, -self.g])
        return np.where(tt <= self.duree_propulsion, self._acceleration_propulsee(), chute)

    def mach(self, t: ArrayLike) -> Tableau:
        """Mach (ISA, vent nul)."""
        return np.asarray(mach(np.linalg.norm(self.vitesse(t), axis=1), self.position(t)[:, 2]), dtype=float)

    def pression_dynamique(self, t: ArrayLike) -> Tableau:
        """q₀ = ½ ρ V² (Pa), ISA, vent nul."""
        v = np.linalg.norm(self.vitesse(t), axis=1)
        return np.asarray(0.5 * masse_volumique(self.position(t)[:, 2]) * v**2, dtype=float)

    def euler_ned(self, t: ArrayLike) -> Tableau:
        """Lacet, tangage, roulis (rad) — ZYX intrinsèque, NED, corps FRD."""
        tt = np.atleast_1d(np.asarray(t, dtype=float))
        v = self.vitesse(tt)
        # À t = 0 la vitesse est nulle : la direction est la limite, celle de la phase propulsée.
        v = np.where((tt <= self.duree_propulsion)[:, None], self._acceleration_propulsee(), v)
        tangage = np.arctan2(v[:, 2], np.hypot(v[:, 0], v[:, 1]))
        lacet = np.full_like(tt, np.radians(self.cap))
        roulis = np.radians(self.vitesse_roulis) * tt
        roulis = (roulis + np.pi) % (2 * np.pi) - np.pi
        return np.stack([lacet, tangage, roulis], axis=1)

    def quaternion(self, t: ArrayLike) -> Tableau:
        """Quaternion corps FRD → ENU, ``(w, x, y, z)``, série continue."""
        q_ned = rot.depuis_euler(self.euler_ned(t), "ZYX")
        q, _ = rot.continuite_hemisphere(reperes.quaternion_vers_enu(q_ned, "NED"))
        return q
