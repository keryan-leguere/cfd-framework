"""Le contrat commun à tous les contrôles.

Un paquet de validation n'a d'intérêt que si les contrôles s'additionnent : on
en écrit un deuxième, un dixième, et le rapport reste un seul rapport. D'où ce
protocole, volontairement mince — un nom, et une exécution qui rend des
verdicts.

La relecture de tables (:mod:`cfd_validation.engine.tables`) en est la première
implémentation. Rien d'autre n'est bâti par anticipation : le jour où un
deuxième contrôle arrive, c'est ce protocole qu'il implémente, et
:class:`~cfd_validation.engine.suite.Suite` agrège sans rien savoir de lui.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = ["Controle", "Verdict"]


@dataclass(frozen=True)
class Verdict:
    """Ce qu'un contrôle dit d'un sujet, sous la forme qu'un rapport agrège.

    Volontairement pauvre : un contrôle qui a beaucoup à raconter garde son
    résultat détaillé pour lui et n'expose ici que de quoi faire une ligne de
    tableau et un code de retour.
    """

    #: Nom du contrôle, par exemple ``"relecture de tables"``.
    controle: str
    #: Ce sur quoi il a porté : une table, un fichier, une routine.
    sujet: str
    #: Grandeur contrôlée à l'intérieur du sujet, s'il y en a plusieurs.
    grandeur: str
    conforme: bool
    #: Nombre de points examinés, et combien sont hors tolérance.
    total: int
    fautifs: int
    #: Une phrase, en français, qui tient sur une ligne de tableau.
    message: str

    @property
    def part_fautive(self) -> float:
        """Part des points hors tolérance, dans [0, 1]."""
        return self.fautifs / self.total if self.total else 0.0


@runtime_checkable
class Controle(Protocol):
    """Ce qu'un contrôle doit savoir faire."""

    @property
    def nom(self) -> str:
        """Nom affichable du contrôle."""
        ...  # pragma: no cover - protocole

    def executer(self) -> tuple[Verdict, ...]:
        """Exécute le contrôle et rend un verdict par sujet contrôlé."""
        ...  # pragma: no cover - protocole
