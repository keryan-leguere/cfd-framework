"""La démarche de la réduction, rédigée pas à pas (``cfd-doe domaine --verbose``).

Le moteur ne se contente pas de donner les sous-domaines : il dit comment il
les a obtenus. Chaque étape (trajectoire, repère, groupe de symétries,
découpage, recollement) est un arbre de :class:`Noeud` ; une feuille du
découpage porte le **numéro du sous-domaine** du tableau auquel elle aboutit,
pour que le raisonnement se lise contre le résultat.

Rien ici n'est formaté pour un terminal : ce sont des phrases et des numéros.
La couche ``report`` les met en forme.

Le découpage par changements de signe est reconstitué à partir du journal de
:func:`~cfd_doe.core.domaine_fondamental.stratifier_signes` : la démarche
raconte la récurrence qui a réellement tourné, elle ne la refait pas.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from cfd_doe.core.domaine_fondamental import Condition, Coupe, Evenement, Feuille, Strate
from cfd_doe.core.intervalle import TOLERANCE, Intervalle
from cfd_doe.core.symetrie import ElementSigne
from cfd_doe.data.format import formater_intervalle, formater_nombre
from cfd_doe.data.variables import SYMBOLES, VARIABLES_CARTESIENNES, VARIABLES_POLAIRES

__all__ = [
    "Brouillon",
    "Etape",
    "Noeud",
    "Redaction",
    "arbre_signes",
    "borne",
    "decrire_element",
    "numeroteur",
    "symbole",
]

#: Ordre d'écriture des variables dans une phrase.
_ORDRE = (*VARIABLES_CARTESIENNES, *VARIABLES_POLAIRES)


@dataclass(frozen=True)
class Noeud:
    """Une ligne de la démarche, et ce qui en découle.

    ``numero`` : le sous-domaine auquel aboutit cette branche (feuilles du
    découpage seulement).
    """

    texte: str
    enfants: tuple[Noeud, ...] = ()
    numero: int | None = None

    def feuilles(self) -> Iterable[Noeud]:
        """Les nœuds numérotés, en profondeur d'abord."""
        if self.numero is not None:
            yield self
        for enfant in self.enfants:
            yield from enfant.feuilles()


@dataclass(frozen=True)
class Etape:
    """Une étape de la démarche : un titre, des nœuds."""

    titre: str
    noeuds: tuple[Noeud, ...]

    def feuilles(self) -> Iterable[Noeud]:
        """Les nœuds numérotés de l'étape."""
        for noeud in self.noeuds:
            yield from noeud.feuilles()


# ---------------------------------------------------------------------------
# Rédaction
# ---------------------------------------------------------------------------


class Brouillon:
    """Nœud en cours d'écriture ; la strate d'une feuille attend son numéro."""

    def __init__(self, texte: str, strate: Strate | None = None) -> None:
        self.texte = texte
        self.strate = strate
        self.enfants: list[Brouillon] = []

    def ajouter(self, texte: str, strate: Strate | None = None) -> Brouillon:
        """Ajoute un enfant et le renvoie."""
        enfant = Brouillon(texte, strate)
        self.enfants.append(enfant)
        return enfant

    def figer(self, numeroter: Callable[[Strate], int]) -> Noeud:
        """Le nœud définitif, feuilles numérotées."""
        return Noeud(
            self.texte,
            tuple(e.figer(numeroter) for e in self.enfants),
            None if self.strate is None else numeroter(self.strate),
        )


class Redaction:
    """Les étapes, dans l'ordre où le moteur les franchit."""

    def __init__(self) -> None:
        self._etapes: list[Brouillon] = []

    def etape(self, titre: str) -> Brouillon:
        """Ouvre une étape ; ses nœuds sont les enfants du brouillon renvoyé."""
        racine = Brouillon(titre)
        self._etapes.append(racine)
        return racine

    def figer(self, numeroter: Callable[[Strate], int]) -> tuple[Etape, ...]:
        """Les étapes définitives."""
        return tuple(
            Etape(r.texte, tuple(e.figer(numeroter) for e in r.enfants)) for r in self._etapes
        )


# ---------------------------------------------------------------------------
# Phrases
# ---------------------------------------------------------------------------


def symbole(variable: str) -> str:
    """α, δmB… ; un couple ``"DMB,DNB"`` devient ``(δmB, δnB)``."""
    if "," in variable:
        return "(" + ", ".join(symbole(v) for v in variable.split(",")) + ")"
    return SYMBOLES.get(variable, variable)


def _symboles(variables: Iterable[str]) -> str:
    rang = {v: i for i, v in enumerate(_ORDRE)}
    return ", ".join(symbole(v) for v in sorted(variables, key=lambda v: rang.get(v, len(rang))))


def borne(variable: str, intervalle: Intervalle) -> str:
    """``β ∈ [−5 ; 5]``, ou ``φa = 0`` pour un point."""
    if intervalle.est_point:
        return f"{symbole(variable)} = {formater_nombre(intervalle.bas)}"
    return f"{symbole(variable)} ∈ {formater_intervalle(intervalle)}"


def decrire_element(element: ElementSigne) -> str:
    """``miroir V (β, δn, δl)`` : le nom, et les variables dont il change le signe."""
    return f"{element.nom} ({_symboles(element.inverse)})"


def _condition(c: Condition) -> str:
    return f"{symbole(c.variable)} {c.texte}"


def _texte_coupe(coupe: Coupe) -> str:
    v = symbole(coupe.variable)
    agissent = "agit" if len(coupe.groupe) == 1 else "agissent"
    debut = f"{agissent} : {', '.join(decrire_element(e) for e in coupe.groupe)}"
    if coupe.recollee:
        return f"{debut} ; seul {v} est retourné → on garde {v} ≥ 0"
    par = ", ".join(e.nom for e in coupe.retournent)
    return f"{debut} ; {v} retourné par {par} → {v} > 0 et {v} = 0"


def arbre_signes(parent: Brouillon, journal: Sequence[Evenement]) -> None:
    """Rédige sous ``parent`` la récurrence d'un appel à ``stratifier_signes``.

    Chaque nœud dit quelles symétries agissent encore au bout de son chemin, et
    quelle variable elles forcent à couper ; les feuilles sont les strates où
    plus rien n'agit. Si rien n'agit dès le départ, ``parent`` devient la
    feuille.
    """
    coupes = {e.chemin: e for e in journal if isinstance(e, Coupe)}
    feuilles = {e.strate.chemin: e.strate for e in journal if isinstance(e, Feuille)}
    racine = min((*coupes, *feuilles), key=len)

    def descendre(noeud: Brouillon, coupe: Coupe) -> None:
        if coupe.recollee:
            noeud.strate = feuilles[(*coupe.chemin, Condition(coupe.variable, "≥ 0"))]
            return
        for signe in ("> 0", "= 0"):
            chemin = (*coupe.chemin, Condition(coupe.variable, signe))
            suite = coupes.get(chemin)
            prefixe = _condition(chemin[-1]) + " : "
            if suite is None:
                noeud.ajouter(prefixe + "plus aucune symétrie n'agit", feuilles[chemin])
            else:
                descendre(noeud.ajouter(prefixe + _texte_coupe(suite)), suite)

    # La racine se fond dans ``parent`` : c'est lui qui dit où l'on est.
    coupe = coupes.get(racine)
    if coupe is None:
        parent.texte += " ; aucune symétrie n'agit sur ce qui reste libre"
        parent.strate = feuilles[racine]
        return
    parent.texte += " ; " + _texte_coupe(coupe)
    descendre(parent, coupe)


# ---------------------------------------------------------------------------
# Numérotation
# ---------------------------------------------------------------------------


def _inclus(a: Intervalle, b: Intervalle) -> bool:
    """``a ⊂ b``, bornes ouvertes comprises."""
    if a.bas < b.bas - TOLERANCE or a.haut > b.haut + TOLERANCE:
        return False
    if abs(a.bas - b.bas) <= TOLERANCE and a.bas_inclus and not b.bas_inclus:
        return False
    return not (abs(a.haut - b.haut) <= TOLERANCE and a.haut_inclus and not b.haut_inclus)


def numeroteur(finales: Sequence[Strate]) -> Callable[[Strate], int]:
    """Associe une strate du découpage au sous-domaine (numéroté à partir de 1) qui la contient.

    Une strate recollée à une voisine est contenue dans leur union ; une strate
    intacte est égale à son sous-domaine. Les sous-domaines étant disjoints,
    exactement un convient : sinon le découpage et son récit divergent, c'est
    un défaut du moteur et non une erreur d'entrée.
    """

    def numero(strate: Strate) -> int:
        candidats = [
            i
            for i, f in enumerate(finales, start=1)
            if f.contraintes == strate.contraintes
            and f.bornes.keys() == strate.bornes.keys()
            and all(_inclus(strate.bornes[v], f.bornes[v]) for v in f.bornes)
        ]
        if len(candidats) != 1:
            raise RuntimeError(
                f"démarche : la strate {strate.nom!r} {dict(strate.bornes)} est contenue dans "
                f"{len(candidats)} sous-domaine(s) au lieu d'un"
            )
        return candidats[0]

    return numero
