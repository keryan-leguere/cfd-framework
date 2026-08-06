"""Styles du rapport terminal, définis à un seul endroit.

**Le gras n'est pas utilisé pour porter une information.** Beaucoup de
terminaux et de thèmes rendent le gras par une couleur plus claire (« bright »)
plutôt que par une graisse : sur un fond clair, le texte gras devient alors
délavé, parfois illisible — et c'est précisément le texte le plus important du
rapport (la réponse, les titres, les en-têtes de tableau) qui disparaît. La
hiérarchie visuelle repose donc ici sur la **couleur** et sur l'atténuation,
qui se comportent de la même façon partout.

``CFD_PERF_GRAS=1`` rétablit le gras par-dessus les couleurs, pour ceux dont le
terminal le rend correctement.

Les valeurs sont de simples chaînes de style Rich, pas des noms de thème : un
panneau construit par ``cfd_perf.report.console`` reste ainsi affichable sur
n'importe quelle ``Console``, y compris celle d'un script appelant.
"""

from __future__ import annotations

import os

#: Variable d'environnement réactivant le gras.
ENV_GRAS = "CFD_PERF_GRAS"

_VRAI = {"1", "true", "vrai", "oui", "yes", "on"}


def gras_actif() -> bool:
    """Vrai si l'utilisateur a demandé le gras via ``CFD_PERF_GRAS``."""
    return os.environ.get(ENV_GRAS, "").strip().lower() in _VRAI


def _emphase(style: str) -> str:
    return f"bold {style}" if gras_actif() else style


#: Titres de panneaux et de tableaux.
TITRE = _emphase("cyan")

#: La réponse elle-même : le nombre de cœurs recommandé.
ACCENT = _emphase("green")

#: Succès, validation, option retenue.
OK = _emphase("green")

#: Réserve, avertissement, donnée douteuse.
ATTENTION = _emphase("yellow")

#: Échec, contrainte violée, configuration irréalisable.
ERREUR = _emphase("red")

#: En-têtes de colonnes.
ENTETE = _emphase("cyan")

#: En-têtes de colonnes du tableau de comparaison au pilote.
ENTETE_ALT = _emphase("magenta")

#: Valeur chiffrée mise en avant, sur fond de libellés atténués.
VALEUR = _emphase("default")

#: Libellés, unités, commentaires : tout ce qui accompagne sans porter.
DISCRET = "dim"
