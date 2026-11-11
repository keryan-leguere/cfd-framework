"""Domaine fondamental d'une action de symétrie, découpé en strates.

Un domaine fondamental contient **exactement un représentant** de chaque
orbite : chaque point du domaine d'entrée y a une image par une symétrie de
l'engin, et une seule. C'est ce qui fait qu'aucun calcul n'est perdu ni fait
deux fois.

Il ne se décrit pas d'un seul pavé : sur un plan de symétrie, une partie du
groupe agit encore sur les variables restantes et les réduit à son tour. On le
découpe donc en **strates**, chacune un produit d'intervalles (éventuellement
assorti d'une contrainte de secteur ou de disque), deux à deux disjointes.

Trois constructions :

- :func:`stratifier_signes` — groupe de changements de signe (cartésien, ou
  braquages sur un plan de symétrie polaire) ;
- :func:`replier_arc` — repliement d'un arc de φa dans le secteur fondamental
  du groupe diédral D_N ;
- :func:`strates_diedrales_plan` — action de D_N sur un plan de braquages
  (δm, δn), utile à αt = 0 où le roulis aérodynamique n'est plus défini.

:func:`stratifier_signes` et :func:`fusionner` acceptent un ``journal`` : la
liste reçoit, dans l'ordre où elles sont prises, les décisions du découpage
(:class:`Coupe`, :class:`Feuille`, :class:`Recollement`). C'est la matière de
la démarche affichée par ``cfd-doe domaine --verbose`` ; elle ne contient aucun
texte, le moteur la rédige.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Union

from cfd_doe.core.angles import Arc, normaliser_angle
from cfd_doe.core.intervalle import TOLERANCE, Intervalle
from cfd_doe.core.symetrie import ElementSigne, restreindre

__all__ = [
    "Condition",
    "Contrainte",
    "Coupe",
    "Disque",
    "Evenement",
    "Feuille",
    "Recollement",
    "Secteur",
    "Strate",
    "fusionner",
    "replier_arc",
    "strates_diedrales_plan",
    "stratifier_signes",
]


# ---------------------------------------------------------------------------
# Contraintes non cartésiennes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Secteur:
    """Points du plan (x, y), hors origine, dont l'angle atan2(y, x) est dans [min, max].

    Angles en degrés dans [0, 360[. ``angle_min == angle_max`` décrit une
    demi-droite.
    """

    x: str
    y: str
    angle_min: float
    angle_max: float
    min_inclus: bool = True
    max_inclus: bool = True

    def contient(self, point: Mapping[str, float], tol: float = TOLERANCE) -> bool:
        """Appartenance d'un point (les autres variables sont ignorées)."""
        px, py = point[self.x], point[self.y]
        if math.hypot(px, py) <= tol:
            return False
        angle = normaliser_angle(math.degrees(math.atan2(py, px)))
        if angle > 360.0 - 1e-7:
            angle = 0.0
        return Intervalle(
            self.angle_min, self.angle_max, self.min_inclus, self.max_inclus
        ).contient(angle, tol=1e-7)


@dataclass(frozen=True)
class Disque:
    """Points du plan (x, y) tels que x² + y² ≤ rayon²."""

    x: str
    y: str
    rayon: float

    def contient(self, point: Mapping[str, float], tol: float = TOLERANCE) -> bool:
        """Appartenance d'un point (les autres variables sont ignorées)."""
        return math.hypot(point[self.x], point[self.y]) <= self.rayon + tol


Contrainte = Union[Secteur, Disque]


# ---------------------------------------------------------------------------
# Strates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Condition:
    """Une étape du découpage : « β > 0 », « δnB = 0 »…

    ``variable`` peut nommer un couple, ``"DMB,DNB"``, pour une condition de
    secteur dans le plan des braquages.
    """

    variable: str
    texte: str


@dataclass(frozen=True)
class Strate:
    """Un morceau du domaine fondamental."""

    bornes: dict[str, Intervalle]
    contraintes: tuple[Contrainte, ...] = ()
    nom: str = ""
    chemin: tuple[Condition, ...] = field(default=())

    def contient(self, point: Mapping[str, float], tol: float = TOLERANCE) -> bool:
        """Vrai si le point est dans les bornes et satisfait les contraintes."""
        return self.dans_bornes(point, tol) and all(
            c.contient(point, tol) for c in self.contraintes
        )

    def dans_bornes(self, point: Mapping[str, float], tol: float = TOLERANCE) -> bool:
        """Appartenance aux seules bornes (contraintes ignorées)."""
        return all(i.contient(point[v], tol) for v, i in self.bornes.items())

    @property
    def dimension(self) -> int:
        """Nombre de variables non réduites à un point."""
        return sum(not i.est_point for i in self.bornes.values()) - sum(
            isinstance(c, Secteur) and abs(c.angle_max - c.angle_min) <= TOLERANCE
            for c in self.contraintes
        )


# ---------------------------------------------------------------------------
# Journal du découpage
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Coupe:
    """Une décision de :func:`stratifier_signes`, prise au bout de ``chemin``.

    ``groupe`` : les symétries qui agissent encore là, vues sur les variables
    libres ; ``retournent`` : celles qui changent le signe de ``variable``.
    ``recollee`` : ``variable`` est seule retournée, on garde ``variable ≥ 0``
    au lieu de couper en ``> 0`` et ``= 0``.
    """

    chemin: tuple[Condition, ...]
    variable: str
    groupe: tuple[ElementSigne, ...]
    retournent: tuple[ElementSigne, ...]
    recollee: bool


@dataclass(frozen=True)
class Feuille:
    """Une strate terminée : plus aucune symétrie n'y relie deux points."""

    strate: Strate


@dataclass(frozen=True)
class Recollement:
    """Deux strates recollées par :func:`fusionner` le long de ``variable``."""

    variable: str
    noms: tuple[str, str]
    avant: tuple[Intervalle, Intervalle]
    union: Intervalle


Evenement = Union[Coupe, Feuille]


def stratifier_signes(
    bornes: Mapping[str, Intervalle],
    elements: Sequence[ElementSigne],
    ordre: Sequence[str],
    *,
    nom: str = "",
    contraintes: tuple[Contrainte, ...] = (),
    chemin: tuple[Condition, ...] = (),
    journal: list[Evenement] | None = None,
) -> list[Strate]:
    """Domaine fondamental d'un groupe de changements de signe.

    Récurrence : on prend la première variable de ``ordre`` qu'un élément
    change de signe, v. Toute orbite a un représentant avec v ≥ 0.

    - Sur ``v > 0``, seuls les éléments qui laissent v inchangé relient encore
      deux points : le groupe se réduit à ce sous-groupe.
    - Sur ``v = 0``, tout le groupe agit encore, mais sur les autres variables.

    On recommence jusqu'à un groupe trivial. Si une seule variable est encore
    affectée, et seule, les deux branches se recollent en ``v ∈ [0, M]``.

    Les variables changées de signe doivent avoir une plage symétrique ; sinon
    le groupe ne préserve pas le domaine (l'appelant symétrise d'abord).
    """
    libres = [v for v in ordre if v in bornes and not bornes[v].est_point]
    groupe = [e for e in restreindre(elements, libres) if e.inverse]
    if not groupe:
        feuille = Strate(dict(bornes), contraintes, nom, chemin)
        if journal is not None:
            journal.append(Feuille(feuille))
        return [feuille]

    agitees = [v for v in libres if any(v in e.inverse for e in groupe)]
    v = agitees[0]
    if not bornes[v].est_symetrique:
        raise ValueError(
            f"la plage de {v} doit être symétrique pour cette symétrie (reçu {bornes[v]})"
        )

    recollee = all(e.inverse == frozenset({v}) for e in groupe)
    if journal is not None:
        retournent = tuple(e for e in groupe if v in e.inverse)
        journal.append(Coupe(chemin, v, tuple(groupe), retournent, recollee))

    if recollee:
        nouvelles = {**bornes, v: bornes[v].partie_positive()}
        feuille = Strate(nouvelles, contraintes, nom, (*chemin, Condition(v, "≥ 0")))
        if journal is not None:
            journal.append(Feuille(feuille))
        return [feuille]

    positif = {**bornes, v: bornes[v].partie_positive_stricte()}
    sous_groupe = [e for e in groupe if v not in e.inverse]
    nul = {**bornes, v: Intervalle.point(0.0)}
    return [
        *stratifier_signes(
            positif,
            sous_groupe,
            ordre,
            nom=nom,
            contraintes=contraintes,
            chemin=(*chemin, Condition(v, "> 0")),
            journal=journal,
        ),
        *stratifier_signes(
            nul,
            groupe,
            ordre,
            nom=nom,
            contraintes=contraintes,
            chemin=(*chemin, Condition(v, "= 0")),
            journal=journal,
        ),
    ]


# ---------------------------------------------------------------------------
# Repliement d'un arc de φa
# ---------------------------------------------------------------------------


def _morceaux(arc: Arc) -> list[tuple[float, float]]:
    """Un arc découpé en intervalles de [0, 360]."""
    fin = arc.debut + arc.longueur
    if fin <= 360.0 + TOLERANCE:
        return [(arc.debut, min(fin, 360.0))]
    return [(arc.debut, 360.0), (0.0, fin - 360.0)]


def replier_arc(arc: Arc, n_rotation: int, miroirs: bool) -> list[Intervalle]:
    """Partie du secteur fondamental de D_N (ou C_N) atteinte par un arc de φa.

    Le secteur est [0, 180/N] avec miroirs (plans φs = k·180/N), [0, 360/N[
    sans. Un point du secteur est nécessaire dès qu'une de ses images tombe
    dans l'arc : on réunit donc les images de l'arc par tout le groupe,
    coupées au secteur.
    """
    if n_rotation < 1:
        raise ValueError("n_rotation doit valoir au moins 1")
    longueur = (180.0 if miroirs else 360.0) / n_rotation
    ferme_haut = miroirs
    if arc.est_complet:
        return [Intervalle(0.0, longueur, haut_inclus=ferme_haut)]

    images = [Arc(arc.debut + k * 360.0 / n_rotation, arc.longueur) for k in range(n_rotation)]
    if miroirs:
        images += [
            Arc(2.0 * (k * 180.0 / n_rotation) - arc.debut - arc.longueur, arc.longueur)
            for k in range(n_rotation)
        ]

    segments: list[tuple[float, float]] = []
    for image in images:
        for bas, haut in _morceaux(image):
            b, h = max(bas, 0.0), min(haut, longueur)
            if b <= h + TOLERANCE:
                segments.append((b, max(b, h)))
    segments.sort()

    fusion: list[list[float]] = []
    for bas, haut in segments:
        if fusion and bas <= fusion[-1][1] + TOLERANCE:
            fusion[-1][1] = max(fusion[-1][1], haut)
        else:
            fusion.append([bas, haut])

    resultat = []
    for bas, haut in fusion:
        ouvert = not ferme_haut and haut >= longueur - TOLERANCE
        if ouvert and haut - bas <= TOLERANCE:
            continue
        resultat.append(Intervalle(bas, haut, haut_inclus=not ouvert))
    return resultat


# ---------------------------------------------------------------------------
# D_N sur un plan de braquages
# ---------------------------------------------------------------------------


def strates_diedrales_plan(
    bornes: Mapping[str, Intervalle],
    x: str,
    y: str,
    roulis: str,
    n_rotation: int,
    *,
    nom: str = "",
    contraintes: tuple[Contrainte, ...] = (),
) -> list[Strate]:
    """Domaine fondamental de D_N (N ≥ 3) agissant sur le plan (x, y).

    Les rotations d'angle k·360/N agissent sur (x, y) seuls ; les N miroirs
    d'axes k·180/N agissent sur (x, y) et changent le signe de ``roulis``.
    Le secteur fondamental est 0 ≤ atan2(y, x) ≤ 180/N :

    - secteur ouvert : stabilisateur trivial, ``roulis`` libre ;
    - demi-droite angle 0, avec l'origine : y = 0, x ≥ 0, ``roulis`` ≥ 0 ;
    - demi-droite angle 180/N, hors origine : ``roulis`` ≥ 0.

    Pour N ≤ 2, l'action est un changement de signe : utiliser
    :func:`stratifier_signes`.
    """
    if n_rotation < 3:
        raise ValueError("strates_diedrales_plan est réservé à N ≥ 3")
    angle = 180.0 / n_rotation
    rl = bornes[roulis]
    rl_positif = rl if rl.est_point else rl.partie_positive()
    cond_roulis = () if rl.est_point else (Condition(roulis, "≥ 0"),)

    interieur = Strate(
        dict(bornes),
        (*contraintes, Secteur(x, y, 0.0, angle, min_inclus=False, max_inclus=False)),
        nom,
        (Condition(f"{x},{y}", f"secteur ]0° ; {angle:g}°["),),
    )
    axe = Strate(
        {**bornes, x: bornes[x].partie_positive(), y: Intervalle.point(0.0), roulis: rl_positif},
        contraintes,
        nom,
        (Condition(y, "= 0"), *cond_roulis),
    )
    bord = Strate(
        {**bornes, roulis: rl_positif},
        (*contraintes, Secteur(x, y, angle, angle)),
        nom,
        (Condition(f"{x},{y}", f"demi-droite {angle:g}°"), *cond_roulis),
    )
    return [interieur, axe, bord]


# ---------------------------------------------------------------------------
# Recollement
# ---------------------------------------------------------------------------


def _recoller(a: Intervalle, b: Intervalle) -> Intervalle | None:
    """L'union de deux intervalles disjoints et contigus, ou ``None``."""
    if a.bas > b.bas or (abs(a.bas - b.bas) <= TOLERANCE and not a.bas_inclus):
        a, b = b, a
    if abs(a.haut - b.bas) > TOLERANCE or (a.haut_inclus == b.bas_inclus):
        return None
    return Intervalle(a.bas, b.haut, a.bas_inclus, b.haut_inclus)


def fusionner(strates: Sequence[Strate], journal: list[Recollement] | None = None) -> list[Strate]:
    """Recolle les strates qui ne diffèrent que par une variable, sur des intervalles contigus.

    Typique en polaire sans braquage : plan φa = 0, secteur ]0, 45[ et plan
    φa = 45 portent les mêmes bornes ailleurs, et se recollent en φa ∈ [0, 45].
    Le nom retenu est celui de la strate de plus grande dimension ; le chemin
    ne garde que les conditions communes.
    """
    courantes = list(strates)
    change = True
    while change:
        change = False
        for i in range(len(courantes)):
            for j in range(i + 1, len(courantes)):
                a, b = courantes[i], courantes[j]
                if a.contraintes != b.contraintes or a.bornes.keys() != b.bornes.keys():
                    continue
                differentes = [v for v in a.bornes if a.bornes[v] != b.bornes[v]]
                if len(differentes) != 1:
                    continue
                v = differentes[0]
                union = _recoller(a.bornes[v], b.bornes[v])
                if union is None:
                    continue
                principale = a if a.dimension >= b.dimension else b
                if journal is not None:
                    journal.append(
                        Recollement(v, (a.nom, b.nom), (a.bornes[v], b.bornes[v]), union)
                    )
                chemin = tuple(c for c in a.chemin if c in b.chemin and c.variable != v)
                courantes[i] = replace(principale, bornes={**a.bornes, v: union}, chemin=chemin)
                del courantes[j]
                change = True
                break
            if change:
                break
    return courantes
