"""Vent lu dans les colonnes de la trajectoire, converti en ENU (m/s) à la lecture.

Comme pour les positions et l'attitude, le fichier **déclare** ses conventions et
rien n'est supposé : le sens de la composante verticale (``vz: haut`` ou ``bas``) est
obligatoire, faute de quoi un ascendant se lirait en rafale descendante.

* ``colonnes`` : trois noms, composantes Nord, Est, verticale (dans cet ordre) ;
* ``vz`` : ``haut`` (VZ > 0 = l'air monte) ou ``bas`` (NED strict, VZ > 0 = l'air descend) ;
* ``sens`` : ``vers`` (défaut : la vitesse de l'air, là où il va) ou ``depuis``
  (convention météo : d'où il vient — le vecteur est alors retourné) ;
* ``unite`` : ``m/s``, ``km/h`` ou ``kt``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.data.trajectoire import Trajectoire

__all__ = ["SENS_VENT", "UNITES_VENT", "VZ_VENT", "DeclarationVent", "ErreurVent", "vent_enu"]

Tableau = NDArray[np.float64]

UNITES_VENT = {"m/s": 1.0, "km/h": 1 / 3.6, "kt": 1852 / 3600}
VZ_VENT = ("haut", "bas")
SENS_VENT = ("vers", "depuis")


class ErreurVent(ValueError):
    """Déclaration du vent impossible à appliquer à cette trajectoire."""


@dataclass(frozen=True)
class DeclarationVent:
    """Colonnes Nord, Est, verticale du vent et leurs conventions."""

    colonnes: tuple[str, str, str]
    vz: str
    sens: str = "vers"
    unite: str = "m/s"

    def __post_init__(self) -> None:
        if len(self.colonnes) != 3:
            raise ErreurVent("vent.colonnes : trois noms, composantes Nord, Est et verticale")
        if self.vz not in VZ_VENT:
            raise ErreurVent("vent.vz : haut (VZ > 0, l'air monte) ou bas (NED, VZ > 0, l'air descend)")
        if self.sens not in SENS_VENT:
            raise ErreurVent("vent.sens : vers (où l'air va) ou depuis (convention météo)")
        if self.unite not in UNITES_VENT:
            raise ErreurVent(f"vent.unite : {', '.join(UNITES_VENT)}")

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> DeclarationVent:
        colonnes = d.get("colonnes")
        if not isinstance(colonnes, (list, tuple)):
            raise ErreurVent("vent.colonnes : une liste de trois noms de colonnes [VN, VE, VZ]")
        if "vz" not in d:
            raise ErreurVent("vent.vz : obligatoire — haut (VZ > 0, l'air monte) ou bas (NED)")
        return cls(colonnes=tuple(str(c) for c in colonnes), vz=str(d["vz"]),  # type: ignore[arg-type]
                   sens=str(d.get("sens", "vers")), unite=str(d.get("unite", "m/s")))

    def decrire(self) -> str:
        """La convention en clair, pour les rapports."""
        vertical = "VZ > 0 vers le haut" if self.vz == "haut" else "VZ > 0 vers le bas (NED)"
        sens = "vitesse de l'air" if self.sens == "vers" else "d'où vient le vent (météo)"
        return f"{', '.join(self.colonnes)} en {self.unite}, {vertical}, {sens}"


def vent_enu(traj: Trajectoire, decl: DeclarationVent) -> Tableau:
    """Le vent aux instants de la trajectoire, ``(n, 3)`` en ENU (m/s), vitesse de l'air."""
    absentes = [c for c in decl.colonnes if c not in traj.donnees]
    if absentes:
        raise ErreurVent(f"vent : colonne(s) {', '.join(absentes)} absente(s) de la trajectoire "
                         f"(colonnes numériques : {', '.join(traj.donnees) or 'aucune'})")
    vn, ve, vz = (np.asarray(traj.donnees[c], dtype=float) for c in decl.colonnes)
    if len(vn) != len(traj.t):
        raise ErreurVent("vent : les colonnes n'ont pas une valeur par instant de la trajectoire")
    haut = vz if decl.vz == "haut" else -vz
    enu = np.column_stack([ve, vn, haut]) * UNITES_VENT[decl.unite]
    return -enu if decl.sens == "depuis" else enu
