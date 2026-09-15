"""Où trouver les données livrées avec le paquet.

L'exemple est une donnée de paquet : un simple ``pip install cfd-validation``
suffit, rien ici n'est résolu relativement au dépôt.
"""

from __future__ import annotations

from pathlib import Path

#: Racine du paquet installé.
PACKAGE_DIR = Path(__file__).resolve().parent

#: Exemple exécutable, recopié par ``cfd-validation exemple``.
EXEMPLE_DIR = PACKAGE_DIR / "01_EXEMPLE"

#: Le jumeau Fortran de l'exemple, compilable par ``cfd-validation construire``.
FORTRAN_DIR = EXEMPLE_DIR / "MODELE_FORTRAN"

__all__ = ["EXEMPLE_DIR", "FORTRAN_DIR", "PACKAGE_DIR"]
