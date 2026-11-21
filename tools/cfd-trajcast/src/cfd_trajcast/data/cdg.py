"""Position du CDG dans l'engin, variable au cours du vol, lue dans la trajectoire.

Les positions de la trajectoire sont **celles du CDG** : la maquette est placée
autour de lui, donc elle glisse quand le CDG avance (la poudre brûle). Ce module
donne, à chaque instant, le CDG dans le repère corps FRD de la maquette, en mètres,
relatif à l'origine du maillage (``maquette.origine``).

* une colonne (``Xcg``) : distance le long de l'axe de l'engin, depuis ``reference``,
  comptée dans le sens ``axe`` (``vers_culot`` par défaut : la convention habituelle
  d'un Xcg mesuré depuis le nez) ;
* trois colonnes (``Xcg, Ycg, Zcg``) : composantes dans les **axes de la CAO**, convertis
  en FRD par la même matrice que la maquette (``axe_nez``, ``axe_haut``).

``reference`` : ``nez`` (point le plus avant de la maquette sur l'axe x), ``culot``
(le plus arrière) ou ``origine`` (l'origine de la maquette). Les longueurs sont celles
de l'engin réel, dans ``unite`` — la maquette est elle aussi en mètres réels, y compris
après ``longueur_imposee``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core.reperes import matrice_cao_vers_corps
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import UNITES_LONGUEUR, Trajectoire

__all__ = ["AXES_CDG", "REFERENCES_CDG", "DeclarationCdg", "ErreurCdg", "cdg_corps", "point_reference"]

Tableau = NDArray[np.float64]

REFERENCES_CDG = ("nez", "culot", "origine")
AXES_CDG = ("vers_culot", "vers_nez")


class ErreurCdg(ValueError):
    """Déclaration du CDG impossible à appliquer."""


@dataclass(frozen=True)
class DeclarationCdg:
    """Une ou trois colonnes donnant le CDG, et comment les lire."""

    colonnes: tuple[str, ...]
    unite: str = "m"
    reference: str = "nez"
    axe: str = "vers_culot"

    def __post_init__(self) -> None:
        if len(self.colonnes) not in (1, 3):
            raise ErreurCdg("cdg.colonnes : une colonne (Xcg le long de l'axe) ou trois (Xcg, Ycg, Zcg, axes CAO)")
        if self.unite not in UNITES_LONGUEUR:
            raise ErreurCdg(f"cdg.unite : {', '.join(UNITES_LONGUEUR)}")
        if self.reference not in REFERENCES_CDG:
            raise ErreurCdg(f"cdg.reference : {', '.join(REFERENCES_CDG)}")
        if self.axe not in AXES_CDG:
            raise ErreurCdg(f"cdg.axe : {', '.join(AXES_CDG)}")

    @classmethod
    def depuis_dict(cls, d: dict[str, Any]) -> DeclarationCdg:
        colonnes = d.get("colonnes")
        if isinstance(colonnes, str):
            colonnes = [colonnes]
        if not isinstance(colonnes, (list, tuple)):
            raise ErreurCdg("cdg.colonnes : un nom de colonne, ou une liste de trois")
        return cls(colonnes=tuple(str(c) for c in colonnes), unite=str(d.get("unite", "m")),
                   reference=str(d.get("reference", "nez")), axe=str(d.get("axe", "vers_culot")))

    def decrire(self) -> str:
        if len(self.colonnes) == 1:
            sens = "vers le culot" if self.axe == "vers_culot" else "vers le nez"
            return f"{self.colonnes[0]} ({self.unite}) depuis le {self.reference}, compté {sens}"
        return f"{', '.join(self.colonnes)} ({self.unite}, axes CAO) depuis {self.reference}"


def point_reference(maquette: Maquette, reference: str) -> Tableau:
    """Le point de référence dans le repère corps de la maquette (m), sur l'axe x."""
    if reference == "nez":
        return np.array([float(maquette.sommets[:, 0].max()), 0.0, 0.0])
    if reference == "culot":
        return np.array([float(maquette.sommets[:, 0].min()), 0.0, 0.0])
    return np.zeros(3)


def cdg_corps(traj: Trajectoire, maquette: Maquette, decl: DeclarationCdg) -> Tableau:
    """Le CDG aux instants de la trajectoire, ``(n, 3)`` en FRD (m), relatif à l'origine de la maquette."""
    absentes = [c for c in decl.colonnes if c not in traj.donnees]
    if absentes:
        raise ErreurCdg(f"cdg : colonne(s) {', '.join(absentes)} absente(s) de la trajectoire "
                        f"(colonnes numériques : {', '.join(traj.donnees) or 'aucune'})")
    valeurs = np.column_stack([np.asarray(traj.donnees[c], dtype=float) for c in decl.colonnes])
    if len(valeurs) != len(traj.t):
        raise ErreurCdg("cdg : les colonnes n'ont pas une valeur par instant de la trajectoire")
    valeurs = valeurs * UNITES_LONGUEUR[decl.unite]
    origine = point_reference(maquette, decl.reference)
    if len(decl.colonnes) == 1:
        signe = -1.0 if decl.axe == "vers_culot" else 1.0  # +x du corps = vers le nez
        decalage = np.column_stack([signe * valeurs[:, 0], np.zeros(len(valeurs)), np.zeros(len(valeurs))])
    else:
        r = matrice_cao_vers_corps(maquette.declaration.axe_nez, maquette.declaration.axe_haut)
        decalage = valeurs @ r.T
    return np.asarray(origine + decalage, dtype=float)
