"""Additionner plusieurs contrôles en un seul rapport.

Un contrôle isolé se lit dans sa sortie ; une campagne de validation se lit
dans un tableau récapitulatif et dans un code de retour. C'est tout ce que fait
ce module — et il le fait sans rien savoir des contrôles qu'il agrège, puisqu'il
ne voit que des :class:`~cfd_validation.engine.controle.Verdict`.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass

from cfd_validation.engine.controle import Controle, Verdict

__all__ = ["Rapport", "Suite", "rapport_de"]


@dataclass(frozen=True)
class Rapport:
    """Le résultat d'une suite : tous les verdicts, et de quoi conclure."""

    verdicts: tuple[Verdict, ...] = ()

    @property
    def conforme(self) -> bool:
        """Vrai si tous les verdicts sont conformes."""
        return all(verdict.conforme for verdict in self.verdicts)

    @property
    def total(self) -> int:
        """Nombre de points examinés, tous contrôles confondus."""
        return sum(verdict.total for verdict in self.verdicts)

    @property
    def fautifs(self) -> int:
        """Nombre de points hors tolérance, tous contrôles confondus."""
        return sum(verdict.fautifs for verdict in self.verdicts)

    @property
    def echecs(self) -> tuple[Verdict, ...]:
        """Les seuls verdicts non conformes."""
        return tuple(verdict for verdict in self.verdicts if not verdict.conforme)

    def par_controle(self) -> dict[str, tuple[Verdict, ...]]:
        """Les verdicts regroupés par contrôle, dans l'ordre d'apparition."""
        groupes: dict[str, list[Verdict]] = {}
        for verdict in self.verdicts:
            groupes.setdefault(verdict.controle, []).append(verdict)
        return {nom: tuple(liste) for nom, liste in groupes.items()}

    def code_retour(self) -> int:
        """``0`` si tout est conforme, ``2`` sinon.

        ``2`` et non ``1`` : la commande a bien abouti, c'est son *résultat* qui
        exige une action. ``1`` reste l'erreur d'entrée. Même convention que
        ``cfd-traj``.
        """
        return 0 if self.conforme else 2

    def __iter__(self) -> Iterator[Verdict]:
        return iter(self.verdicts)

    def __len__(self) -> int:
        return len(self.verdicts)


class Suite:
    """Une campagne de contrôles.

    .. code-block:: python

        suite = Suite([ControleTables(module, specs, modele=mon_modele)])
        rapport = suite.executer()
        raise SystemExit(rapport.code_retour())
    """

    def __init__(self, controles: Sequence[Controle] = ()) -> None:
        self.controles = list(controles)

    def ajouter(self, controle: Controle) -> Suite:
        """Ajoute un contrôle et rend la suite, pour enchaîner les appels."""
        self.controles.append(controle)
        return self

    def executer(self) -> Rapport:
        """Exécute tous les contrôles, dans l'ordre où ils ont été ajoutés."""
        verdicts: list[Verdict] = []
        for controle in self.controles:
            verdicts.extend(controle.executer())
        return Rapport(verdicts=tuple(verdicts))

    def __iter__(self) -> Iterator[Controle]:
        return iter(self.controles)

    def __len__(self) -> int:
        return len(self.controles)


def rapport_de(verdicts: Iterable[Verdict]) -> Rapport:
    """Un rapport bâti sur des verdicts déjà obtenus."""
    return Rapport(verdicts=tuple(verdicts))
