"""Écriture des nombres et des intervalles, à la française.

Partagé par les messages du moteur et par le rapport, pour qu'un avertissement
et une cellule de tableau écrivent la même valeur de la même façon.
"""

from __future__ import annotations

from cfd_doe.core.intervalle import Intervalle

__all__ = ["formater_intervalle", "formater_nombre"]


def formater_nombre(x: float, decimales: int = 2) -> str:
    """Virgule décimale, signe moins typographique, zéros inutiles ôtés."""
    texte = f"{x:.{decimales}f}".rstrip("0").rstrip(".")
    if texte in ("-0", ""):
        texte = "0"
    return texte.replace("-", "−").replace(".", ",")


def formater_intervalle(i: Intervalle, *, espace: bool = True) -> str:
    """``[−20 ; 20]``, ``]0 ; 45[``, ou la valeur seule pour un point."""
    if i.est_point:
        return formater_nombre(i.bas)
    gauche = "[" if i.bas_inclus else "]"
    droite = "]" if i.haut_inclus else "["
    sep = " ; " if espace else ";"
    return f"{gauche}{formater_nombre(i.bas)}{sep}{formater_nombre(i.haut)}{droite}"
