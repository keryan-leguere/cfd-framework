"""Styles du rapport terminal, définis à un seul endroit.

Le gras n'est pas utilisé pour porter une information : beaucoup de terminaux
le rendent par une couleur « bright » qui devient illisible sur fond clair. La
hiérarchie repose sur la couleur et l'atténuation. ``CFD_DOE_GRAS=1`` rétablit
le gras par-dessus les couleurs.
"""

from __future__ import annotations

import os

__all__ = [
    "ACCENT",
    "ATTENTION",
    "DISCRET",
    "ENTETE",
    "ENV_GRAS",
    "ERREUR",
    "FIXE",
    "OK",
    "TITRE",
    "VALEUR",
    "gras_actif",
]

#: Variable d'environnement réactivant le gras.
ENV_GRAS = "CFD_DOE_GRAS"

_VRAI = {"1", "true", "vrai", "oui", "yes", "on"}


def gras_actif() -> bool:
    """Vrai si ``CFD_DOE_GRAS`` demande le gras."""
    return os.environ.get(ENV_GRAS, "").strip().lower() in _VRAI


def _emphase(style: str) -> str:
    return f"bold {style}" if gras_actif() else style


#: Titres de panneaux et de tableaux.
TITRE = _emphase("cyan")
#: Le chiffre qu'on est venu lire.
ACCENT = _emphase("green")
#: Conforme.
OK = _emphase("green")
#: Précaution à prendre.
ATTENTION = _emphase("yellow")
#: Refus.
ERREUR = _emphase("red")
#: En-têtes de colonne.
ENTETE = _emphase("cyan")
#: Une valeur mise en avant.
VALEUR = _emphase("default")
#: Une variable figée par le sous-domaine (plan de symétrie, axe).
FIXE = "magenta"
#: Libellés, unités, commentaires.
DISCRET = "dim"
