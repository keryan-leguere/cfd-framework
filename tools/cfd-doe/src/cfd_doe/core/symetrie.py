"""Actions de symétrie par changements de signe.

En cartésien (repère engin), les symétries exploitables d'un engin agissent
toutes en changeant le signe de certaines variables (00_DOC/01_BASE_AERO.md
§4.4) : le miroir vertical change β, δl, δn ; le miroir horizontal change α,
δl, δm ; leur composée, la rotation de 180°, change α, β, δm, δn. En polaire,
sur un plan de symétrie φa = φs, le miroir change δl et δnB (§7.2).

Un élément de groupe est donc décrit par l'ensemble des variables dont il
change le signe, et la composition est la différence symétrique de ces
ensembles. Le groupe engendré est commutatif et chaque élément est sa propre
inverse : un sous-groupe de (Z/2)^n.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

__all__ = ["IDENTITE", "ElementSigne", "engendrer", "restreindre"]


@dataclass(frozen=True)
class ElementSigne:
    """Un élément du groupe : son nom, et les variables dont il change le signe."""

    nom: str
    inverse: frozenset[str]

    def compose(self, autre: ElementSigne) -> ElementSigne:
        """Composée ``self ∘ autre`` (commutative)."""
        return ElementSigne(f"{self.nom}∘{autre.nom}", self.inverse ^ autre.inverse)

    def agit(self, point: dict[str, float]) -> dict[str, float]:
        """Image d'un point (variables absentes de ``inverse`` inchangées)."""
        return {v: (-x if v in self.inverse else x) for v, x in point.items()}


#: L'élément neutre.
IDENTITE = ElementSigne("id", frozenset())


def engendrer(generateurs: Iterable[ElementSigne]) -> tuple[ElementSigne, ...]:
    """Le groupe engendré, identité en tête, chaque élément nommé une seule fois.

    Quand deux mots donnent le même ensemble de signes, le premier trouvé
    (le plus court) garde le nom ; c'est ainsi que ``V∘H`` reste ``V∘H`` même
    si l'appelant fournit aussi la rotation de 180° comme générateur nommé —
    auquel cas c'est ce nom-là qui l'emporte, car les générateurs passent
    d'abord.
    """
    elements: dict[frozenset[str], ElementSigne] = {IDENTITE.inverse: IDENTITE}
    gens = list(generateurs)
    for g in gens:
        elements.setdefault(g.inverse, g)
    file = list(elements.values())
    while file:
        courant = file.pop(0)
        for g in gens:
            produit = courant.compose(g) if courant is not IDENTITE else g
            if produit.inverse not in elements:
                elements[produit.inverse] = produit
                file.append(produit)
    return tuple(elements.values())


def restreindre(
    elements: Sequence[ElementSigne], variables: Iterable[str]
) -> tuple[ElementSigne, ...]:
    """L'action du groupe vue sur ``variables`` seulement.

    Deux éléments qui ne diffèrent que sur des variables absentes (fixées à 0,
    donc insensibles au signe) deviennent le même élément ; on garde le premier
    nom rencontré.
    """
    garde = frozenset(variables)
    vus: dict[frozenset[str], ElementSigne] = {}
    for e in elements:
        cle = e.inverse & garde
        if cle not in vus:
            vus[cle] = ElementSigne(e.nom if cle else "id", cle)
    vus.setdefault(frozenset(), IDENTITE)
    identite = vus.pop(frozenset())
    return (identite, *vus.values())
