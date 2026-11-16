"""Validation : la trajectoire et la maquette tiennent-elles debout, telles que déclarées ?

Par défaut, seuls des contrôles valables pour **toute** trajectoire : on ne suppose
ni montée, ni apogée, ni sol (un vol plané, une descente sous parachute, un tronçon
de vol sont des trajectoires légitimes).

Le contrôle optionnel ``coherence=True`` est la **cohérence attitude / vitesse**,
utile quand la trajectoire contient une montée propulsée ou balistique. Une erreur de
convention (quaternion conjugué, ``xyzw`` lu ``wxyz``, NED déclaré ENU, séquence
extrinsèque lue intrinsèque) ne fait rien planter : elle produit une vidéo fausse.
Or pendant la montée, une fusée stable vole nez au vent — l'angle entre son axe
et sa vitesse reste de quelques degrés. Un angle médian élevé trahit donc une
convention fausse, et en rejouant la conversion sous les autres conventions on
peut dire laquelle rendrait le vol cohérent. Ce contrôle *diagnostique* ; il ne
corrige rien et ne remplace jamais l'attitude par la vitesse.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core import rotations as rot
from cfd_trajcast.core.interpolation import deriver
from cfd_trajcast.data.constats import ALERTE, INFO, Constat
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import (
    DeclarationTrajectoire,
    ErreurTrajectoire,
    Trajectoire,
    convertir,
)

__all__ = ["SEUIL_INCIDENCE_DEG", "angle_nez_vitesse", "fenetre_montee", "verifier"]

Tableau = NDArray[np.float64]

#: Angle médian nez/vitesse (°) au-delà duquel la convention est suspecte.
SEUIL_INCIDENCE_DEG = 20.0
#: Part de la vitesse maximale sous laquelle la direction de la vitesse ne dit rien.
FRACTION_VITESSE = 0.2
#: Échantillons minimaux dans la fenêtre de contrôle.
MIN_ECHANTILLONS = 5


def fenetre_montee(t: Tableau, positions: Tableau) -> NDArray[np.bool_]:
    """Échantillons de la montée assez rapides pour que la vitesse ait une direction."""
    v = deriver(t, positions)
    vitesse = np.linalg.norm(v, axis=1)
    apogee = int(np.argmax(positions[:, 2]))
    masque = (np.arange(len(t)) < apogee) & (v[:, 2] > 0)
    masque &= vitesse > FRACTION_VITESSE * (vitesse[masque].max() if masque.any() else 0.0)
    return masque


def angle_nez_vitesse(t: Tableau, positions: Tableau, attitude: Tableau) -> Tableau:
    """Angle (°) entre l'axe du nez et la vitesse, à chaque échantillon."""
    v = deriver(t, positions)
    norme = np.linalg.norm(v, axis=1, keepdims=True)
    nez = rot.tourner(attitude, np.array([1.0, 0.0, 0.0]))
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = np.sum(nez * v / norme, axis=1)
    return np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))


def _variantes(decl: DeclarationTrajectoire) -> list[tuple[str, DeclarationTrajectoire]]:
    a = decl.attitude
    autre_repere = "NED" if decl.repere == "ENU" else "ENU"
    reperes_ = [(decl.repere, ""), (autre_repere, f"repère {autre_repere}")]
    if a.type == "quaternion":
        autre_ordre = "xyzw" if a.ordre == "wxyz" else "wxyz"
        autre_sens = "reference_vers_corps" if a.sens == "corps_vers_reference" else "corps_vers_reference"
        options = [
            (a.ordre, a.sens, ""),
            (autre_ordre, a.sens, f"ordre {autre_ordre}"),
            (a.ordre, autre_sens, f"sens {autre_sens.replace('_', ' ')}"),
            (autre_ordre, autre_sens, f"ordre {autre_ordre} et sens {autre_sens.replace('_', ' ')}"),
        ]
        attitudes = [(replace(a, ordre=o, sens=s), nom) for o, s, nom in options]
    else:
        autre = a.sequence.swapcase()
        nature = "extrinsèque" if autre.islower() else "intrinsèque"
        attitudes = [(a, ""), (replace(a, sequence=autre), f"séquence {autre} ({nature})")]
    variantes = []
    for repere, nom_r in reperes_:
        for att, nom_a in attitudes:
            nom = " + ".join(n for n in (nom_r, nom_a) if n)
            if nom:
                variantes.append((nom, replace(decl, repere=repere, attitude=att)))
    return variantes


def _coherence(traj: Trajectoire) -> list[Constat]:
    masque = fenetre_montee(traj.t, traj.positions)
    n = int(np.count_nonzero(masque))
    if n < MIN_ECHANTILLONS:
        return [
            Constat(ALERTE, "coherence_non_faite",
                    f"cohérence attitude/vitesse non contrôlée : {n} échantillon(s) de montée "
                    "rapide seulement",
                    "la trajectoire a-t-elle une montée ? Sinon, ne pas demander ce contrôle")
        ]
    angles = angle_nez_vitesse(traj.t, traj.positions, traj.attitude)[masque]
    mediane = float(np.median(angles))
    if mediane <= SEUIL_INCIDENCE_DEG:
        return [
            Constat(INFO, "coherence",
                    f"axe du nez cohérent avec la vitesse pendant la montée : angle médian "
                    f"{mediane:.1f}° sur {n} échantillons")
        ]
    essais: list[tuple[float, str]] = []
    for nom, decl in _variantes(traj.declaration):
        try:
            positions, q, _ = convertir(traj.brut, decl)
        except (ErreurTrajectoire, ValueError):
            continue
        m = fenetre_montee(traj.t, positions)
        if np.count_nonzero(m) >= MIN_ECHANTILLONS:
            essais.append((float(np.median(angle_nez_vitesse(traj.t, positions, q)[m])), nom))
    essais.sort()
    plausibles = [f"{nom} → {a:.1f}°" for a, nom in essais if a <= SEUIL_INCIDENCE_DEG]
    indice = (
        "convention(s) qui rendraient le vol cohérent : " + " ; ".join(plausibles)
        if plausibles
        else "aucune autre convention testée ne rend le vol cohérent "
        "(colonnes interverties ? attitude d'un autre vol ?)"
    )
    return [
        Constat(ALERTE, "coherence",
                f"pendant la montée, l'axe du nez fait {mediane:.0f}° (médiane) avec la vitesse : "
                "convention d'attitude probablement fausse", indice)
    ]


def _plausibilite(traj: Trajectoire) -> list[Constat]:
    constats: list[Constat] = []
    z = traj.positions[:, 2]
    mach_max = float(np.max(traj.mach))
    etendue = float(np.max(np.ptp(traj.positions, axis=0)))
    if len(traj.t) < 10:
        constats.append(Constat(ALERTE, "peu_echantillons", f"{len(traj.t)} échantillons seulement"))
    if etendue > 2000e3:
        constats.append(
            Constat(ALERTE, "etendue", f"la trajectoire s'étend sur {etendue / 1e3:.0f} km",
                    "unité de longueur (pieds, millimètres) ?")
        )
    if mach_max > 30:
        constats.append(
            Constat(ALERTE, "mach_eleve", f"Mach maximal {mach_max:.0f}",
                    "unités de temps ou de longueur ?")
        )
    constats.append(
        Constat(INFO, "resume",
                f"{len(traj.t)} échantillons sur {traj.duree:.2f} s, cote de {z.min():.0f} à "
                f"{z.max():.0f} m, Mach maximal {mach_max:.2f}")
    )
    return constats


def verifier(traj: Trajectoire, maquette: Maquette | None = None, *, coherence: bool = False) -> list[Constat]:
    """Constats de lecture, de plausibilité et de la maquette.

    ``coherence=True`` ajoute le contrôle nez / vitesse sur la montée — à ne demander
    que si la trajectoire en contient une.
    """
    constats = [*traj.constats, *(_coherence(traj) if coherence else []), *_plausibilite(traj)]
    if maquette is not None:
        constats += list(maquette.constats)
        constats.append(
            Constat(INFO, "maquette",
                    f"maquette {maquette.declaration.fichier.name} : {len(maquette.faces)} faces, "
                    f"longueur {maquette.longueur:.3f} m, envergure {maquette.envergure:.3f} m")
        )
    return constats
