"""Le critère d'acceptation d'un écart numérique.

Une valeur testée ``t`` est acceptée contre sa référence ``r`` si ::

    |t − r| ≤ atol + rtol · |r|

C'est le critère de :func:`numpy.isclose`, **asymétrique** à dessein : la
référence est l'oracle, c'est elle qui fixe l'échelle. ``atol`` protège les
valeurs voisines de zéro (un ``CY`` nul à β = 0 ne supporte aucun écart
relatif) ; ``rtol`` porte l'essentiel.

Une tolérance n'est une preuve que si elle est **justifiée** : d'où l'origine
(défaut ou déclarée) et la justification portées avec elle, et reprises dans
le rapport. ``rtol = atol = 0`` exige l'identité bit pour bit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from cfd_validation.core.format import formater_court

__all__ = [
    "ATOL_DEFAUT",
    "ORIGINE_DECLAREE",
    "ORIGINE_DEFAUT",
    "RTOL_DEFAUT",
    "Tolerance",
]

#: Tolérance relative par défaut : quelques milliers d'ULP en double précision,
#: l'ordre de grandeur d'un changement de compilateur ou d'options
#: d'optimisation sur un code qui n'accumule pas d'erreur. **À justifier.**
RTOL_DEFAUT = 1e-9
#: Tolérance absolue par défaut, pour les sorties de l'ordre de l'unité. **À justifier.**
ATOL_DEFAUT = 1e-12

ORIGINE_DEFAUT = "defaut"
ORIGINE_DECLAREE = "declaree"


@dataclass(frozen=True)
class Tolerance:
    """Critère ``|t − r| ≤ atol + rtol·|r|`` et sa traçabilité.

    Attributes
    ----------
    rtol, atol
        Tolérances relative et absolue, finies et positives.
    justification
        Pourquoi cette valeur (erreur de troncature attendue, précision du
        format d'échange, exigence client…). Reprise dans le rapport.
    origine
        ``"defaut"`` si personne ne l'a déclarée, ``"declaree"`` sinon.
    """

    rtol: float = RTOL_DEFAUT
    atol: float = ATOL_DEFAUT
    justification: str | None = None
    origine: str = ORIGINE_DECLAREE

    def __post_init__(self) -> None:
        for nom, valeur in (("rtol", self.rtol), ("atol", self.atol)):
            if not isinstance(valeur, (int, float)) or isinstance(valeur, bool):
                raise TypeError(f"{nom} doit être un nombre, reçu {valeur!r}")
            if not math.isfinite(valeur) or valeur < 0:
                raise ValueError(f"{nom} doit être fini et positif, reçu {valeur!r}")
        if self.origine not in (ORIGINE_DEFAUT, ORIGINE_DECLAREE):
            raise ValueError(f"origine inconnue : {self.origine!r}")

    @property
    def exacte(self) -> bool:
        """Vrai si le critère exige l'identité bit pour bit."""
        return self.rtol == 0 and self.atol == 0

    def seuil(self, reference: NDArray[np.float64]) -> NDArray[np.float64]:
        """Écart admissible en chaque point : ``atol + rtol·|r|``."""
        return self.atol + self.rtol * np.abs(reference)

    def decrire(self) -> str:
        """Le critère en clair : ``|Δ| ≤ 1e-12 + 1e-09·|réf|``."""
        if self.exacte:
            return "identité bit pour bit"
        termes = []
        if self.atol:
            termes.append(formater_court(self.atol))
        if self.rtol:
            termes.append(f"{formater_court(self.rtol)}·|réf|")
        return "|Δ| ≤ " + " + ".join(termes)
