"""Les variables du DOE et leurs noms.

Les noms *internes* sont ceux du fichier d'étude (``alpha``, ``DM``…). Les
symboles (α, δm…) ne servent qu'à l'affichage.

En polaire, (α, β) deviennent (αt, φa) et (δm, δn) deviennent les braquages
en repère mixte (δmB, δnB) ; δl ne change pas (00_DOC/01_BASE_AERO.md §7.1).
"""

from __future__ import annotations

__all__ = [
    "BRAQUAGES",
    "SYMBOLES",
    "UNITE",
    "VARIABLES",
    "VARIABLES_CARTESIENNES",
    "VARIABLES_POLAIRES",
]

#: Variables d'entrée, dans l'ordre du fichier d'étude.
VARIABLES: tuple[str, ...] = ("alpha", "beta", "DL", "DM", "DN")

#: Variables des braquages équivalents.
BRAQUAGES: tuple[str, ...] = ("DL", "DM", "DN")

#: Ordre des colonnes, et ordre de découpage par les symétries : les angles de
#: vol d'abord, puis tangage, lacet, et le roulis en dernier — c'est lui que le
#: dernier plan de symétrie réduit de moitié.
VARIABLES_CARTESIENNES: tuple[str, ...] = ("alpha", "beta", "DM", "DN", "DL")
VARIABLES_POLAIRES: tuple[str, ...] = ("alphat", "phia", "DMB", "DNB", "DL")

SYMBOLES: dict[str, str] = {
    "alpha": "α",
    "beta": "β",
    "alphat": "αt",
    "phia": "φa",
    "DL": "δl",
    "DM": "δm",
    "DN": "δn",
    "DMB": "δmB",
    "DNB": "δnB",
}

#: Toutes les variables sont des angles en degrés.
UNITE = "°"
