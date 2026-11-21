"""L'état du vol à un instant quelconque : ce que l'interface montre, sans Qt.

:class:`EtatVol` rassemble une trajectoire, sa maquette et, s'ils sont déclarés, le
vent et le CDG variable. Il précalcule sur les instants de la trajectoire tout ce qui
se trace en fonction du temps — les **séries** : grandeurs calculées, angles
aérodynamiques, Xcg et **toutes** les colonnes numériques du fichier — puis
:meth:`EtatVol.a` donne l'état à n'importe quel instant (interpolé), repères locaux
compris. L'interface ne fait qu'afficher ce qu'il rend : tout ce qui compte est ici,
testé sans écran.

Les séries calculées sont dans l'unité d'affichage par défaut de ``CALCULEES``
(altitude en m, angles en °…) ; les colonnes du fichier restent dans **ses** unités,
qu'il ne déclare pas : leur unité affichée est vide.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core import reperes_locaux as rl
from cfd_trajcast.core import rotations as rot
from cfd_trajcast.data.cdg import DeclarationCdg, cdg_corps
from cfd_trajcast.data.configuration import CALCULEES, Configuration
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.data.vent import DeclarationVent, vent_enu
from cfd_trajcast.engine.telemetrie import calculs

__all__ = ["EtatVol", "Instant", "SerieVol"]

Tableau = NDArray[np.float64]
_DEG = 180 / np.pi


@dataclass(frozen=True, eq=False)
class SerieVol:
    """Une grandeur sur les instants de la trajectoire, dans son unité d'affichage."""

    cle: str
    libelle: str
    unite: str
    valeurs: Tableau
    source: str  # "calcul", "vent", "cdg" ou "colonne"
    decimales: int | None = None


@dataclass(frozen=True, eq=False)
class Instant:
    """L'état à un instant ``t`` : grandeurs physiques en ENU (m, m/s), repères en colonnes ENU."""

    t: float
    position: Tableau
    attitude: Tableau
    vitesse_sol: Tableau
    vent: Tableau | None
    vitesse_air: Tableau | None
    incidence: float
    derapage: float
    cdg_corps: Tableau | None
    axes: dict[str, Tableau]
    valeurs: dict[str, float] = field(default_factory=dict)


class EtatVol:
    """Trajectoire + maquette (+ vent, + CDG) : séries précalculées et état à tout instant."""

    def __init__(self, trajectoire: Trajectoire, maquette: Maquette, *,
                 vent: DeclarationVent | None = None, cdg: DeclarationCdg | None = None) -> None:
        self.trajectoire, self.maquette = trajectoire, maquette
        self.decl_vent, self.decl_cdg = vent, cdg
        traj = trajectoire
        self.t = np.asarray(traj.t, dtype=float)
        self.vent: Tableau | None = vent_enu(traj, vent) if vent is not None else None
        self.cdg: Tableau | None = cdg_corps(traj, maquette, cdg) if cdg is not None else None
        self.series: dict[str, SerieVol] = {}
        fonctions = calculs(traj)
        for cle, (libelle, unites) in CALCULEES.items():
            facteur, texte, decimales = next(iter(unites.values()))
            self.series[cle] = SerieVol(cle, libelle, texte, np.asarray(fonctions[cle](), dtype=float) * facteur,
                                        "calcul", decimales)
        if self.vent is not None:
            v_air = traj.vitesse - self.vent
            alpha, beta, v = rl.angles_aero(traj.attitude, v_air)
            self.series["incidence"] = SerieVol("incidence", "Incidence α", "°", alpha * _DEG, "vent", 1)
            self.series["derapage"] = SerieVol("derapage", "Dérapage β", "°", beta * _DEG, "vent", 1)
            self.series["vitesse_air"] = SerieVol("vitesse_air", "Vitesse air", "m/s", v, "vent", 1)
            self.series["vent_horizontal"] = SerieVol("vent_horizontal", "Vent horizontal", "m/s",
                                                      np.hypot(self.vent[:, 0], self.vent[:, 1]), "vent", 1)
        if self.cdg is not None:
            self.series["xcg"] = SerieVol("xcg", "CDG (x corps)", "m", self.cdg[:, 0], "cdg", 3)
        for nom, valeurs in traj.donnees.items():
            if len(valeurs) != len(self.t):
                continue
            # Une colonne homonyme d'une grandeur calculée (« roulis ») reste cochable.
            cle = nom if nom not in self.series else f"{nom} (fichier)"
            self.series[cle] = SerieVol(cle, nom, "", np.asarray(valeurs, dtype=float), "colonne")

    @classmethod
    def depuis_configuration(cls, cfg: Configuration, *, utiliser_cache: bool = True) -> EtatVol:
        """Charge trajectoire et maquette d'un fichier, avec son vent et son CDG s'ils sont déclarés."""
        return cls(cfg.trajectoire.charger(utiliser_cache=utiliser_cache),
                   Maquette.depuis_declaration(cfg.maquette), vent=cfg.vent, cdg=cfg.cdg)

    # -- temps --------------------------------------------------------------------------
    @property
    def debut(self) -> float:
        return float(self.t[0])

    @property
    def fin(self) -> float:
        return float(self.t[-1])

    def borner(self, t: float) -> float:
        return float(min(max(t, self.debut), self.fin))

    def colonnes_fichier(self) -> list[str]:
        """Les séries qui viennent du fichier, dans son ordre."""
        return [c for c, s in self.series.items() if s.source == "colonne"]

    def series_calculees(self) -> list[str]:
        return [c for c, s in self.series.items() if s.source != "colonne"]

    def _interp(self, valeurs: Tableau, t: float) -> float:
        return float(np.interp(t, self.t, valeurs))

    def _vecteur(self, valeurs: Tableau, t: float) -> Tableau:
        return np.array([np.interp(t, self.t, valeurs[:, i]) for i in range(3)])

    # -- état -----------------------------------------------------------------------------
    def a(self, t: float) -> Instant:
        """L'état à l'instant ``t`` (borné au vol)."""
        t = self.borner(t)
        positions, attitudes = self.trajectoire.etat(np.array([t]))
        q = attitudes[0]
        v_sol = np.asarray(self.trajectoire.vitesse_a(np.array([t]))[0], dtype=float)
        vent = self._vecteur(self.vent, t) if self.vent is not None else None
        v_air = v_sol - vent if vent is not None else None
        axes = {"corps": rl.axes_corps(q)[0], "ned": rl.axes_ned_local(1)[0],
                "trajectoire": rl.axes_trajectoire(v_sol)[0]}
        alpha = beta = float("nan")
        if v_air is not None:
            axes["aero"] = rl.axes_aero(q, v_air)[0]
            a_, b_, _ = rl.angles_aero(q, v_air)
            alpha, beta = float(a_[0]), float(b_[0])
        cdg = self._vecteur(self.cdg, t) if self.cdg is not None else None
        valeurs = {c: self._interp(s.valeurs, t) for c, s in self.series.items()}
        return Instant(t=t, position=np.asarray(positions[0], dtype=float), attitude=np.asarray(q, dtype=float),
                       vitesse_sol=v_sol, vent=vent, vitesse_air=v_air, incidence=alpha, derapage=beta,
                       cdg_corps=cdg, axes=axes, valeurs=valeurs)

    def placer(self, sommets_corps: Tableau, t: float, echelle: float = 1.0) -> Tableau:
        """Sommets de la maquette en ENU à l'instant ``t``, agrandis de ``echelle`` **autour du CDG**.

        Le CDG est le point que suit la trajectoire : ``position + R · echelle · (s − cdg)``.
        Sans CDG déclaré, c'est l'origine de la maquette.
        """
        positions, attitudes = self.trajectoire.etat(np.array([self.borner(t)]))
        r = rot.vers_matrice(attitudes[0])
        cdg = self._vecteur(self.cdg, t) if self.cdg is not None else np.zeros(3)
        return np.asarray(positions[0] + (echelle * (np.asarray(sommets_corps) - cdg)) @ r.T, dtype=float)

    def valeur(self, cle: str, t: float) -> float:
        return self._interp(self.series[cle].valeurs, self.borner(t))

    def description(self) -> dict[str, Any]:
        """Ce que l'état sait faire, pour les rapports et la barre d'état."""
        return {"vent": self.decl_vent.decrire() if self.decl_vent else None,
                "cdg": self.decl_cdg.decrire() if self.decl_cdg else None,
                "series": len(self.series), "colonnes": len(self.colonnes_fichier())}
