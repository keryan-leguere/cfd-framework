"""Écriture des nombres et des intervalles, à la française.

Partagé par les messages du moteur et par le rapport, pour qu'un avertissement
et une cellule de tableau écrivent la même valeur de la même façon.
"""

from __future__ import annotations

from cfd_doe.core.intervalle import Intervalle

__all__ = ["DECIMALES_NOEUD", "formater_intervalle", "formater_nombre", "nombre_csv"]

#: Arrondi qui identifie un nœud de grille : écriture et relecture des CSV le partagent.
DECIMALES_NOEUD = 9


def formater_nombre(x: float, decimales: int = 2) -> str:
    """Virgule décimale, signe moins typographique, zéros inutiles ôtés."""
    texte = f"{x:.{decimales}f}".rstrip("0").rstrip(".")
    if texte in ("-0", ""):
        texte = "0"
    return texte.replace("-", "−").replace(".", ",")


def nombre_csv(x: float) -> str:
    """Une coordonnée de nœud pour un CSV, relue au même nœud.

    Arrondie à :data:`DECIMALES_NOEUD` décimales puis écrite au plus court
    (``repr``), sans ``.0`` pour un entier. Un format en chiffres
    *significatifs* (``.10g``) tronquait au contraire les niveaux non ronds
    au-delà de 10 (``42,4264068712`` → ``42,42640687``) : relu, le point ne
    tombait plus sur son nœud et la table restait trouée.
    """
    v = round(float(x), DECIMALES_NOEUD) + 0.0
    return str(int(v)) if v.is_integer() and abs(v) < 1e15 else repr(v)


def formater_intervalle(i: Intervalle, *, espace: bool = True) -> str:
    """``[−20 ; 20]``, ``]0 ; 45[``, ou la valeur seule pour un point."""
    if i.est_point:
        return formater_nombre(i.bas)
    gauche = "[" if i.bas_inclus else "]"
    droite = "]" if i.haut_inclus else "["
    sep = " ; " if espace else ";"
    return f"{gauche}{formater_nombre(i.bas)}{sep}{formater_nombre(i.haut)}{droite}"
