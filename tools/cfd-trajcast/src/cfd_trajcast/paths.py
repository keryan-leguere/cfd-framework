"""Où trouver les données livrées avec le paquet (jamais relativement au dépôt)."""

from __future__ import annotations

from pathlib import Path

#: Racine du paquet installé.
PACKAGE_DIR = Path(__file__).resolve().parent

#: Exemple recopié par ``cfd-trajcast exemple``.
EXEMPLE_DIR = PACKAGE_DIR / "01_EXEMPLE"

__all__ = ["EXEMPLE_DIR", "PACKAGE_DIR"]
