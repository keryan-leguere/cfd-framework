"""Constats : ce que la lecture et la validation ont remarqué, et à quel point c'est grave."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

__all__ = ["ALERTE", "ERREUR", "INFO", "NIVEAUX", "Constat", "a_des_erreurs"]

INFO = "info"
ALERTE = "alerte"
ERREUR = "erreur"
#: Du moins au plus grave.
NIVEAUX = (INFO, ALERTE, ERREUR)


@dataclass(frozen=True)
class Constat:
    """Un fait remarqué. ``code`` est stable (tests, filtrage) ; ``indice`` dit quoi faire."""

    niveau: str
    code: str
    message: str
    indice: str = ""

    def __post_init__(self) -> None:
        if self.niveau not in NIVEAUX:
            raise ValueError(f"niveau {self.niveau!r} inconnu")


def a_des_erreurs(constats: Iterable[Constat]) -> bool:
    """Vrai si au moins un constat est une erreur."""
    return any(c.niveau == ERREUR for c in constats)
