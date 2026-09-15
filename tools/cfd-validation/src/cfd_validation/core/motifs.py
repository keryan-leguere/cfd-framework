"""Nommer le motif d'une panne de relecture de table.

Un contrôle qui dit « 347 points sur 2 100 sont hors tolérance » a fait la
moitié du travail. L'autre moitié est de dire **pourquoi** — et les façons dont
un code se trompe en lisant une table sont en petit nombre, chacune laissant
une signature nette dans les écarts :

===========================  ================================================
motif                        ce qu'il attrape
===========================  ================================================
``queue_non_renseignee``     les fautifs sont exactement la fin du tableau
``facteur_echelle``          ``obtenu ≈ k·référence`` — une unité, un signe
``decalage_constant``        ``obtenu ≈ référence + c``
``axes_transposes``          deux colonnes indépendantes permutées à la lecture
``axe_ignore``               une colonne n'entre pas dans l'indexation
``decalage_indice``          le code lit le nœud voisin — le sempiternel ±1
``ecretage``                 le ±1 confiné aux bords, donc un indice saturé
``diffus``                   aucun motif : les pires points et leur position
===========================  ================================================

**Tous les détecteurs qui se déclenchent sont rapportés**, classés par la part
des points fautifs qu'ils expliquent. Un « premier trouvé » masquerait un
défaut composite — un facteur d'unité *et* un décalage d'indice arrivent très
bien ensemble, et n'avoir que le premier coûte une deuxième campagne.

Rien ici ne reconnaît une colonne à son nom : les noms ne servent qu'à écrire
le message. Un détecteur qui saurait ce qu'est un « mach » ne marcherait que
sur les tables de celui qui l'a écrit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import numpy.typing as npt

from cfd_validation.core.ecart import Ecart

__all__ = [
    "DETECTEURS",
    "Contexte",
    "Motif",
    "detecter",
]

Tableau = npt.NDArray[np.float64]
Cle = tuple[float, ...]

#: En deçà de cette part des points fautifs, un motif n'est pas rapporté : il
#: expliquerait trop peu pour orienter, et ferait du bruit dans le rapport.
PART_MINIMALE = 0.25

#: Du plus spécifique au plus général. Sert d'unique départage à part expliquée
#: égale — « le code sature son indice au bord » est un renseignement plus
#: actionnable que « le code lit le voisin », qui l'englobe.
ORDRE_SPECIFICITE: tuple[str, ...] = (
    "queue_non_renseignee",
    "ecretage",
    "axes_transposes",
    "axe_ignore",
    "decalage_indice",
    "facteur_echelle",
    "decalage_constant",
    "diffus",
)


@dataclass(frozen=True)
class Contexte:
    """Tout ce qu'un détecteur a le droit de regarder.

    *noeuds* porte les colonnes **indépendantes** de la table, dans l'ordre
    déclaré : une ligne par point, une colonne par variable. C'est la
    géométrie de la table, et c'est elle qui permet de parler d'axe, de voisin
    et de bord.
    """

    noeuds: Tableau
    ecart: Ecart
    noms: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.noeuds.ndim != 2:
            raise ValueError(f"noeuds doit être un tableau 2-D, reçu {self.noeuds.ndim}-D")
        if self.noeuds.shape[0] != self.ecart.n:
            raise ValueError(
                f"noeuds porte {self.noeuds.shape[0]} lignes pour {self.ecart.n} points comparés"
            )
        if self.noeuds.shape[1] != len(self.noms):
            raise ValueError(
                f"noeuds porte {self.noeuds.shape[1]} colonnes "
                f"pour {len(self.noms)} noms de colonne"
            )

    @property
    def fautifs(self) -> npt.NDArray[np.intp]:
        """Indices des points hors tolérance."""
        return self.ecart.indices_fautifs

    def tolere(self, attendu: Tableau, obtenu: Tableau) -> npt.NDArray[np.bool_]:
        """Le critère de conformité du contrôle, réappliqué à une hypothèse."""
        proche: npt.NDArray[np.bool_] = np.abs(obtenu - attendu) <= (
            self.ecart.atol + self.ecart.rtol * np.abs(attendu)
        )
        return proche & ~(np.isnan(attendu) | np.isnan(obtenu))


@dataclass(frozen=True)
class Motif:
    """Une hypothèse sur la panne, et ce qui l'étaye."""

    #: Identifiant stable, celui du tableau en tête de module.
    nom: str
    #: Part des points fautifs que cette hypothèse explique, dans [0, 1].
    part_expliquee: float
    #: Une phrase, en français, adressée à l'ingénieur qui lit le rapport.
    message: str
    #: Les chiffres qui étayent, pour affichage. Jamais interprétés.
    preuve: dict[str, object] = field(default_factory=dict)

    @property
    def specificite(self) -> int:
        """Rang dans :data:`ORDRE_SPECIFICITE` ; plus petit, plus spécifique."""
        try:
            return ORDRE_SPECIFICITE.index(self.nom)
        except ValueError:  # pragma: no cover - un motif hors liste reste possible
            return len(ORDRE_SPECIFICITE)


# ---------------------------------------------------------------------------
# Outillage commun aux détecteurs
# ---------------------------------------------------------------------------


def _index_par_noeud(noeuds: Tableau) -> dict[Cle, int]:
    """Associe à chaque nœud son indice de ligne.

    Les clés sont les ``float`` du tableau, sans arrondi : les nœuds qu'un
    détecteur cherche viennent de cette table-ci, donc leurs coordonnées sont
    littéralement les mêmes objets flottants. Arrondir introduirait un seuil à
    régler là où l'égalité exacte suffit.
    """
    index: dict[Cle, int] = {}
    for ligne in range(noeuds.shape[0]):
        index.setdefault(tuple(noeuds[ligne].tolist()), ligne)
    return index


def _valeurs_d_axe(noeuds: Tableau, axe: int) -> Tableau:
    """Valeurs distinctes prises par une colonne, triées."""
    return np.unique(noeuds[:, axe])


def _part(explique: npt.NDArray[np.bool_], fautifs: npt.NDArray[np.intp]) -> float:
    """Part des points fautifs couverts par *explique*."""
    if fautifs.size == 0:
        return 0.0
    return float(explique[fautifs].sum()) / float(fautifs.size)


def _coordonnees(contexte: Contexte, ligne: int) -> str:
    """Les coordonnées d'un point, telles qu'on les lit dans un rapport."""
    return ", ".join(
        f"{nom}={contexte.noeuds[ligne, axe]:g}" for axe, nom in enumerate(contexte.noms)
    )


#: Facteurs d'échelle dont la présence dit tout de suite ce qui s'est passé.
_FACTEURS_CONNUS: tuple[tuple[float, str], ...] = (
    (-1.0, "signe inversé"),
    (np.pi / 180.0, "des degrés lus comme des radians"),
    (180.0 / np.pi, "des radians lus comme des degrés"),
    (0.01, "un pourcentage lu comme une fraction"),
    (100.0, "une fraction lue comme un pourcentage"),
    (0.5, "un facteur 2 — pression dynamique ?"),
    (2.0, "un facteur 2 — pression dynamique ?"),
    (9.80665, "des kgf lus comme des newtons"),
    (4.4482216152605, "des lbf lus comme des newtons"),
    (0.3048, "des pieds lus comme des mètres"),
    (1.0 / 0.3048, "des mètres lus comme des pieds"),
    (0.45359237, "des livres lues comme des kilogrammes"),
    (1.0 / 0.45359237, "des kilogrammes lus comme des livres"),
)


def _nommer_facteur(k: float) -> str | None:
    """Le facteur ressemble-t-il à une conversion d'unité connue ?"""
    for valeur, libelle in _FACTEURS_CONNUS:
        if abs(k - valeur) <= 1e-6 * abs(valeur):
            return libelle
    return None


# ---------------------------------------------------------------------------
# Les détecteurs
# ---------------------------------------------------------------------------


def queue_non_renseignee(contexte: Contexte) -> Motif | None:
    """Les points fautifs sont exactement la fin du tableau.

    Un tableau Fortran est dimensionné au maximum et un entier voisin dit
    combien de lignes sont réellement remplies. Oublier de déclarer cet entier
    fait comparer le modèle à des lignes qui ne veulent rien dire — et la
    signature en est parfaitement nette : un suffixe contigu.
    """
    fautifs = contexte.fautifs
    n = contexte.ecart.n
    if fautifs.size == 0 or fautifs[0] == 0:
        return None
    if not np.array_equal(fautifs, np.arange(fautifs[0], n)):
        return None

    debut = int(fautifs[0])
    queue = contexte.ecart.reference[debut:]
    constante = bool(np.all(queue == queue[0])) if queue.size else False
    detail = (
        f" La référence y est constante ({queue[0]:g}), ce qui est la marque d'une zone"
        " jamais remplie."
        if constante
        else ""
    )
    return Motif(
        nom="queue_non_renseignee",
        part_expliquee=1.0,
        message=(
            f"Les {fautifs.size} points fautifs sont exactement les lignes {debut} à {n - 1},"
            " c'est-à-dire la fin du tableau." + detail + " Déclarez le nombre de lignes"
            " réellement renseignées avec la clé `lignes`."
        ),
        preuve={
            "premiere_ligne_fautive": debut,
            "lignes_declarees": n,
            "queue_constante": constante,
        },
    )


def facteur_echelle(contexte: Contexte) -> Motif | None:
    """``obtenu ≈ k·référence`` — une unité, un signe, un demi."""
    fautifs = contexte.fautifs
    if fautifs.size == 0:
        return None
    ref = contexte.ecart.reference
    obt = contexte.ecart.obtenu
    fini = np.isfinite(ref) & np.isfinite(obt)
    denominateur = float(np.sum(ref[fini] ** 2))
    if denominateur == 0.0:
        return None

    k = float(np.sum(ref[fini] * obt[fini]) / denominateur)
    if abs(k - 1.0) <= 1e-6:
        return None

    explique = contexte.tolere(k * ref, obt)
    part = _part(explique, fautifs)
    if part < PART_MINIMALE:
        return None

    libelle = _nommer_facteur(k)
    suffixe = f" Cela ressemble à {libelle}." if libelle else ""
    return Motif(
        nom="facteur_echelle",
        part_expliquee=part,
        message=(
            f"Le modèle rend {k:.12g} fois la valeur tabulée sur {part:.0%} des points fautifs."
            + suffixe
        ),
        preuve={"facteur": k, "conversion": libelle or "—"},
    )


def decalage_constant(contexte: Contexte) -> Motif | None:
    """``obtenu ≈ référence + c``."""
    fautifs = contexte.fautifs
    if fautifs.size == 0:
        return None
    difference = contexte.ecart.difference
    fini = np.isfinite(difference)
    if not fini.any():
        return None

    c = float(np.median(difference[fini]))
    if c == 0.0:
        return None

    explique = contexte.tolere(contexte.ecart.reference + c, contexte.ecart.obtenu)
    part = _part(explique, fautifs)
    if part < PART_MINIMALE:
        return None
    return Motif(
        nom="decalage_constant",
        part_expliquee=part,
        message=(
            f"Le modèle rend la valeur tabulée décalée de {c:+.12g}"
            f" sur {part:.0%} des points fautifs."
        ),
        preuve={"decalage": c},
    )


def axes_transposes(contexte: Contexte) -> Motif | None:
    """Deux colonnes indépendantes ont été permutées à l'indexation.

    Le test est constructif : on va chercher, dans la table elle-même, la
    valeur du nœud dont les deux coordonnées sont échangées, et on regarde si
    c'est *celle-là* que le modèle a rendue. Pas de seuil à régler, et aucune
    autre panne ne produit cette coïncidence par hasard.
    """
    fautifs = contexte.fautifs
    if fautifs.size == 0 or contexte.noeuds.shape[1] < 2:
        return None

    index = _index_par_noeud(contexte.noeuds)
    meilleur: Motif | None = None

    for premier in range(contexte.noeuds.shape[1]):
        for second in range(premier + 1, contexte.noeuds.shape[1]):
            explique = np.zeros(contexte.ecart.n, dtype=bool)
            for ligne in fautifs:
                cle = list(contexte.noeuds[ligne].tolist())
                cle[premier], cle[second] = cle[second], cle[premier]
                jumeau = index.get(tuple(cle))
                if jumeau is None:
                    continue
                explique[ligne] = bool(
                    contexte.tolere(
                        contexte.ecart.reference[jumeau : jumeau + 1],
                        contexte.ecart.obtenu[ligne : ligne + 1],
                    )[0]
                )
            part = _part(explique, fautifs)
            if part < PART_MINIMALE:
                continue
            if meilleur is not None and part <= meilleur.part_expliquee:
                continue
            meilleur = Motif(
                nom="axes_transposes",
                part_expliquee=part,
                message=(
                    f"Sur {part:.0%} des points fautifs, le modèle rend la valeur du nœud où"
                    f" « {contexte.noms[premier]} » et « {contexte.noms[second]} » sont"
                    " échangés : les deux axes sont permutés à la lecture."
                ),
                preuve={"axes": (contexte.noms[premier], contexte.noms[second])},
            )
    return meilleur


def axe_ignore(contexte: Contexte) -> Motif | None:
    """Une colonne n'entre pas du tout dans l'indexation.

    Signature : à toutes les autres coordonnées fixées, la référence varie le
    long de cet axe et le modèle, lui, rend une constante. C'est le cas d'un
    code qui n'indexe que deux axes d'une table qui en a trois — panne qu'aucun
    des autres détecteurs ne voit, parce qu'elle ne ressemble ni à un décalage
    ni à un facteur.
    """
    fautifs = contexte.fautifs
    if fautifs.size == 0 or contexte.noeuds.shape[1] < 2:
        return None

    meilleur: Motif | None = None
    for axe in range(contexte.noeuds.shape[1]):
        autres = [colonne for colonne in range(contexte.noeuds.shape[1]) if colonne != axe]
        groupes: dict[Cle, list[int]] = {}
        for ligne in range(contexte.ecart.n):
            groupes.setdefault(tuple(contexte.noeuds[ligne, autres].tolist()), []).append(ligne)

        explique = np.zeros(contexte.ecart.n, dtype=bool)
        for lignes in groupes.values():
            if len(lignes) < 2:
                continue
            ref = contexte.ecart.reference[lignes]
            obt = contexte.ecart.obtenu[lignes]
            reference_varie = not bool(np.all(contexte.tolere(np.full_like(ref, ref[0]), ref)))
            modele_constant = bool(np.all(contexte.tolere(np.full_like(obt, obt[0]), obt)))
            if reference_varie and modele_constant:
                explique[lignes] = True

        part = _part(explique, fautifs)
        if part < PART_MINIMALE:
            continue
        if meilleur is not None and part <= meilleur.part_expliquee:
            continue
        meilleur = Motif(
            nom="axe_ignore",
            part_expliquee=part,
            message=(
                f"Sur {part:.0%} des points fautifs, la valeur rendue ne change pas quand"
                f" « {contexte.noms[axe]} » seul change, alors que la table, elle, change :"
                " cet axe n'entre pas dans l'indexation."
            ),
            preuve={"axe": contexte.noms[axe]},
        )
    return meilleur


def decalage_indice(contexte: Contexte) -> Motif | None:
    """Le modèle rend la valeur du nœud voisin le long d'un axe."""
    resultat = _chercher_voisinage(contexte, confine_aux_bords=False)
    if resultat is None:
        return None
    axe, sens, part = resultat
    mot = "suivant" if sens > 0 else "précédent"
    return Motif(
        nom="decalage_indice",
        part_expliquee=part,
        message=(
            f"Sur {part:.0%} des points fautifs, le modèle rend la valeur du nœud {mot}"
            f" le long de « {contexte.noms[axe]} » : l'indice est décalé de {sens:+d}."
        ),
        preuve={"axe": contexte.noms[axe], "sens": sens},
    )


def ecretage(contexte: Contexte) -> Motif | None:
    """Le décalage d'indice, mais confiné aux bords d'un axe.

    C'est la marque d'un indice saturé : le code borne son indice à ``n-1`` et
    le dernier nœud se met à rendre l'avant-dernier, sans que l'intérieur de la
    table bouge d'un pouce. Distinguer ce cas de :func:`decalage_indice` vaut
    la peine, parce que le correctif n'est pas le même — une borne à reprendre,
    pas une base d'indexation.
    """
    resultat = _chercher_voisinage(contexte, confine_aux_bords=True)
    if resultat is None:
        return None
    axe, _sens, part = resultat
    return Motif(
        nom="ecretage",
        part_expliquee=part,
        message=(
            f"Tous les points fautifs sont aux bornes de « {contexte.noms[axe]} », et"
            f" {part:.0%} d'entre eux rendent la valeur du nœud immédiatement intérieur :"
            " l'indice est saturé au bord."
        ),
        preuve={"axe": contexte.noms[axe]},
    )


def _chercher_voisinage(
    contexte: Contexte, *, confine_aux_bords: bool
) -> tuple[int, int, float] | None:
    """Cherche l'axe le long duquel le modèle rend un nœud voisin.

    Quand *confine_aux_bords* est vrai, l'axe n'est retenu que si **tous** les
    points fautifs sont sur une borne de cet axe, et le voisin regardé est
    toujours celui de l'intérieur.
    """
    fautifs = contexte.fautifs
    if fautifs.size == 0:
        return None

    index = _index_par_noeud(contexte.noeuds)
    meilleur: tuple[int, int, float] | None = None

    for axe in range(contexte.noeuds.shape[1]):
        valeurs = _valeurs_d_axe(contexte.noeuds, axe)
        if valeurs.size < 2:
            continue
        rang = {float(valeur): position for position, valeur in enumerate(valeurs.tolist())}

        aux_bornes = np.isin(contexte.noeuds[fautifs, axe], [valeurs[0], valeurs[-1]])
        if confine_aux_bords and not bool(np.all(aux_bornes)):
            continue

        for sens in (1, -1):
            explique = np.zeros(contexte.ecart.n, dtype=bool)
            for ligne in fautifs:
                position = rang[float(contexte.noeuds[ligne, axe])]
                pas = sens
                if confine_aux_bords:
                    # Au bord, le seul voisin est celui de l'intérieur.
                    pas = 1 if position == 0 else -1
                cible = position + pas
                if not 0 <= cible < valeurs.size:
                    continue
                cle = list(contexte.noeuds[ligne].tolist())
                cle[axe] = float(valeurs[cible])
                jumeau = index.get(tuple(cle))
                if jumeau is None:
                    continue
                explique[ligne] = bool(
                    contexte.tolere(
                        contexte.ecart.reference[jumeau : jumeau + 1],
                        contexte.ecart.obtenu[ligne : ligne + 1],
                    )[0]
                )
            part = _part(explique, fautifs)
            if part < PART_MINIMALE:
                continue
            if meilleur is not None and part <= meilleur[2]:
                continue
            meilleur = (axe, sens, part)
            if confine_aux_bords:
                # Le sens est imposé par la borne ; inutile d'essayer l'autre.
                break
    return meilleur


def diffus(contexte: Contexte) -> Motif | None:
    """Aucun motif : on donne les pires points et la forme de la dérive.

    Part expliquée nulle, donc toujours en dernier : ce n'est pas une
    hypothèse, c'est ce qu'il reste à regarder à la main.
    """
    pire = contexte.ecart.indice_pire
    if pire is None:
        return None
    quantiles = contexte.ecart.quantiles()
    return Motif(
        nom="diffus",
        part_expliquee=0.0,
        message=(
            f"Écart le plus fort au point {pire} ({_coordonnees(contexte, pire)}) :"
            f" table {contexte.ecart.reference[pire]:.12g},"
            f" modèle {contexte.ecart.obtenu[pire]:.12g}"
            f" (écart relatif {contexte.ecart.relatif[pire]:.3g})."
            f" Médiane des écarts relatifs {quantiles[0.5]:.3g},"
            f" 99ᵉ centile {quantiles[0.99]:.3g}."
        ),
        preuve={
            "indice_pire": pire,
            "coordonnees": _coordonnees(contexte, pire),
            "quantiles": quantiles,
        },
    )


#: Les détecteurs, dans l'ordre où ils sont interrogés. L'ordre n'influe pas
#: sur le classement — seule la part expliquée le fait — mais il fixe celui des
#: égalités parfaites, et rend la sortie reproductible.
DETECTEURS: tuple[Callable[[Contexte], Motif | None], ...] = (
    queue_non_renseignee,
    ecretage,
    axes_transposes,
    axe_ignore,
    decalage_indice,
    facteur_echelle,
    decalage_constant,
    diffus,
)


def detecter(contexte: Contexte) -> tuple[Motif, ...]:
    """Tous les motifs qui se déclenchent, du plus explicatif au moins.

    À part expliquée égale, le plus **spécifique** passe devant : c'est celui
    qui nomme le correctif le plus précis.
    """
    motifs = [motif for detecteur in DETECTEURS if (motif := detecteur(contexte)) is not None]
    motifs.sort(key=lambda motif: (-motif.part_expliquee, motif.specificite))
    return tuple(motifs)
