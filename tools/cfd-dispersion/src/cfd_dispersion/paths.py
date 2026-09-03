"""Où trouver les données livrées avec le paquet.

L'exemple est une donnée de paquet : un simple ``pip install cfd-dispersion``
suffit, rien ici n'est résolu relativement au dépôt.
"""

from __future__ import annotations

from pathlib import Path

#: Racine du paquet installé.
PACKAGE_DIR = Path(__file__).resolve().parent

#: Exemple exécutable, recopié par ``cfd-dispersion exemple``.
EXEMPLE_DIR = PACKAGE_DIR / "01_EXEMPLE"

__all__ = ["EXEMPLE_DIR", "PACKAGE_DIR"]
