"""Petites compatibilités entre versions de Python.

cfd-perf doit s'installer tel quel sur les calculateurs isolés, où l'inter-
préteur disponible est souvent celui de la distribution — Python 3.9 sur les
bases RHEL 8 / Rocky 8 encore très répandues en CFD. Ce module regroupe les
rares endroits où la bibliothèque standard a changé depuis, pour que le reste
du code s'écrive une seule fois.
"""

from __future__ import annotations

import enum


class StrEnum(str, enum.Enum):
    """Énumération dont les membres *sont* leur valeur texte.

    Équivalent de ``enum.StrEnum`` (Python 3.11+), défini ici pour toutes les
    versions plutôt que conditionnellement : le formatage des énumérations
    mixtes a changé en 3.11 (``f"{Strategy.FASTEST}"`` donnait la valeur avant,
    ``Strategy.FASTEST`` après). En fixant ``__str__`` et ``__format__``, un
    message d'erreur ou un YAML généré est identique quel que soit
    l'interpréteur.
    """

    def __str__(self) -> str:
        return str(self.value)

    def __format__(self, format_spec: str) -> str:
        return str.__format__(str(self.value), format_spec)
