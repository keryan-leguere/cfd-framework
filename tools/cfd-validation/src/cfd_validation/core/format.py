"""Formatage des nombres pour le terminal, le journal et les figures."""

from __future__ import annotations

import math
import re

__all__ = ["formater", "formater_court", "pourcentage"]


def formater(valeur: float | int | None, chiffres: int = 3) -> str:
    """Un nombre lisible à ``chiffres`` significatifs : ``0``, ``1.23e-12``, ``0.85``, ``—``.

    Les entiers restent entiers ; NaN et ``None`` donnent un tiret, l'infini ``inf``.
    """
    if valeur is None:
        return "—"
    if isinstance(valeur, bool):
        return str(valeur)
    if isinstance(valeur, int):
        return str(valeur)
    x = float(valeur)
    if math.isnan(x):
        return "—"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    if x == 0:
        return "0"
    if 1e-3 <= abs(x) < 1e5:
        texte = f"{x:.{chiffres}g}"
        if "e" not in texte:  # 99999.99 s'arrondit en « 1e+05 » : passer à la forme scientifique
            return texte
    return f"{x:.{max(chiffres - 1, 0)}e}"


def formater_court(valeur: float) -> str:
    """Le plus court qui relise la valeur : ``1e-12``, ``5e-9``, ``0.001``, ``2.5e-7``."""
    texte = f"{float(valeur):.15g}"
    return re.sub(r"e([+-])0*(\d)", lambda m: "e" + ("-" if m.group(1) == "-" else "") + m.group(2), texte)


def pourcentage(part: int, total: int) -> str:
    """``12.5 %`` ; ``100 %`` et ``0 %`` ne s'affichent que s'ils sont exacts."""
    if total == 0:
        return "—"
    p = 100.0 * part / total
    if part == total:
        return "100 %"
    if part == 0:
        return "0 %"
    if p >= 99.95:
        return "> 99.9 %"
    if p < 0.05:
        return "< 0.1 %"
    return f"{p:.1f} %"
