"""Où trouver les données livrées avec le paquet.

L'exemple est une donnée de paquet : un simple ``pip install`` suffit, rien
n'est résolu relativement au dépôt.
"""

from __future__ import annotations

from pathlib import Path

#: Racine du paquet installé.
PACKAGE_DIR = Path(__file__).resolve().parent

#: Exemple recopié par ``cfd-doe exemple``.
EXEMPLE_DIR = PACKAGE_DIR / "01_EXEMPLE"

__all__ = ["EXEMPLE_DIR", "PACKAGE_DIR"]
