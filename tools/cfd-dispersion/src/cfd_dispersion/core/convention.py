"""Comment un biais et un facteur d'échelle reconstruisent un coefficient.

Le tirage rend deux nombres par coefficient — un biais et un facteur d'échelle
(FE) — mais il ne dit pas comment les recombiner avec la valeur nominale. Or
la relation employée varie d'une équipe et d'un dossier à l'autre, et deux
d'entre elles diffèrent d'un facteur 100 :

    linéaire      c_disp = biais + FE · c
    pourcentage   c_disp = biais + (1 + FE/100) · c
    relatif       c_disp = biais + (1 + FE) · c

Rien dans une figure ne trahit qu'on s'est trompé de convention : la courbe
reste lisse et l'ordre de grandeur reste crédible. La relation est donc un
objet à part entière, qui porte sa propre formule en clair et se retrouve
imprimée dans chaque boîte de paramètres et chaque légende.

Une relation maison s'écrit directement ::

    ma_convention = Convention(
        nom="tabulee",
        formule="biais + FE · c · (1 + c²)",
        appliquer=lambda c, biais, fe: biais + fe * c * (1 + c**2),
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Union

import numpy as np

__all__ = ["CONVENTIONS", "CONVENTION_PAR_DEFAUT", "Convention", "convention"]

#: Signature d'une relation de reconstruction : ``(c, biais, fe) -> c_dispersé``.
Relation = Callable[..., np.ndarray]


@dataclass(frozen=True)
class Convention:
    """Une relation de reconstruction, avec sa formule en clair.

    Parameters
    ----------
    nom:
        Identifiant court, celui qu'on passe aux fonctions du paquet.
    formule:
        La relation écrite pour un humain — elle finit dans les boîtes de
        paramètres des figures, de sorte qu'un tracé ne puisse jamais cacher
        sous quelle convention il a été produit.
    appliquer:
        ``(coeff, biais, fe) -> coeff_dispersé``, vectorisable numpy.
    """

    nom: str
    formule: str
    appliquer: Relation

    def __call__(self, coeff: object, biais: object, fe: object) -> np.ndarray:
        """Applique la relation ; diffuse comme numpy."""
        resultat = self.appliquer(
            np.asarray(coeff, dtype=float),
            np.asarray(biais, dtype=float),
            np.asarray(fe, dtype=float),
        )
        return np.asarray(resultat, dtype=float)


#: Les relations livrées, par nom.
CONVENTIONS: dict[str, Convention] = {
    "lineaire": Convention(
        nom="lineaire",
        formule="biais + FE · c",
        appliquer=lambda c, biais, fe: biais + fe * c,
    ),
    "pourcentage": Convention(
        nom="pourcentage",
        formule="biais + (1 + FE/100) · c",
        appliquer=lambda c, biais, fe: biais + (1.0 + fe / 100.0) * c,
    ),
    "relatif": Convention(
        nom="relatif",
        formule="biais + (1 + FE) · c",
        appliquer=lambda c, biais, fe: biais + (1.0 + fe) * c,
    ),
}

#: La convention retenue quand l'appelant n'en nomme pas.
CONVENTION_PAR_DEFAUT = "lineaire"

#: Ce qu'accepte tout paramètre ``convention=`` du paquet.
ConventionArg = Union[str, Convention, None]


def convention(choix: ConventionArg = None) -> Convention:
    """Résout un nom, un objet, ou None, en une :class:`Convention`.

    Parameters
    ----------
    choix:
        Le nom d'une convention livrée, une :class:`Convention` déjà construite
        (relation maison), ou None pour la convention par défaut.

    Raises
    ------
    ValueError
        Si le nom est inconnu ; le message énumère les noms disponibles.

    Examples
    --------
    >>> convention("pourcentage").formule
    'biais + (1 + FE/100) · c'
    >>> float(convention("lineaire")(2.0, 0.1, 1.5))
    3.1
    """
    if choix is None:
        return CONVENTIONS[CONVENTION_PAR_DEFAUT]
    if isinstance(choix, Convention):
        return choix
    if choix not in CONVENTIONS:
        raise ValueError(
            f"convention inconnue : {choix!r} ; attendu l'une de {sorted(CONVENTIONS)} "
            "ou un objet Convention"
        )
    return CONVENTIONS[choix]
