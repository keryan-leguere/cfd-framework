"""Styles du rapport terminal, définis à un seul endroit.

**Le gras n'est pas utilisé pour porter une information.** Beaucoup de
terminaux et de thèmes rendent le gras par une couleur plus claire
(« bright ») plutôt que par une graisse : sur un fond clair, le texte gras
devient alors délavé, parfois illisible — et c'est précisément le texte le plus
important du rapport (le verdict, les en-têtes) qui disparaît. La hiérarchie
visuelle repose donc ici sur la **couleur** et sur l'atténuation, qui se
comportent de la même façon partout.

``CFD_VALIDATION_GRAS=1`` rétablit le gras par-dessus les couleurs, pour ceux
dont le terminal le rend correctement.

Les valeurs sont de simples chaînes de style Rich, pas des noms de thème : un
tableau construit par :mod:`cfd_validation.report.console` reste ainsi
affichable sur n'importe quelle ``Console``, y compris celle d'un script
appelant.
"""

from __future__ import annotations

import os

__all__ = [
    "ACCENT",
    "ATTENTION",
    "COULEUR_VERDICT",
    "DISCRET",
    "ENTETE",
    "ENTETE_ALT",
    "ENV_GRAS",
    "ERREUR",
    "OK",
    "STYLE_VERDICT",
    "TITRE",
    "VALEUR",
    "gras_actif",
]

#: Variable d'environnement réactivant le gras.
ENV_GRAS = "CFD_VALIDATION_GRAS"

_VRAI = {"1", "true", "vrai", "oui", "yes", "on"}


def gras_actif() -> bool:
    """Vrai si l'utilisateur a demandé le gras via ``CFD_VALIDATION_GRAS``."""
    return os.environ.get(ENV_GRAS, "").strip().lower() in _VRAI


def _emphase(style: str) -> str:
    return f"bold {style}" if gras_actif() else style


#: Titres de panneaux et de tableaux.
TITRE = _emphase("cyan")
#: La réponse elle-même : le verdict d'ensemble, le chiffre qu'on est venu lire.
ACCENT = _emphase("green")
#: Conforme.
OK = _emphase("green")
#: Mesurable et toléré, ou une précaution à prendre.
ATTENTION = _emphase("yellow")
#: Hors tolérance, ou refusé.
ERREUR = _emphase("red")
#: En-têtes de colonne.
ENTETE = _emphase("cyan")
#: En-têtes des tableaux secondaires.
ENTETE_ALT = _emphase("magenta")
#: Un nombre mis en avant dans une phrase.
VALEUR = _emphase("default")
#: Libellés, unités, commentaires. Jamais emphatisé : c'est le fond du texte.
DISCRET = "dim"

#: Style Rich associé à un verdict.
STYLE_VERDICT: dict[bool, str] = {True: OK, False: ERREUR}

#: Couleurs Matplotlib des verdicts, pour les annotations de figure. Les mêmes
#: que le terminal, pour qu'une planche et un rapport se lisent ensemble.
COULEUR_VERDICT: dict[bool, str] = {True: "#1b7837", False: "#b2182b"}
