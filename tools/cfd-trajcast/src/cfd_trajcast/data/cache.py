"""Cache disque des calculs coûteux et déterministes : maillage d'un STEP, vol RocketPy.

Une entrée est un fichier ``.npz`` nommé par l'empreinte SHA-256 de **tout** ce dont
le résultat dépend (contenu des fichiers, réglages, versions des bibliothèques) : une
entrée n'est jamais périmée, elle cesse seulement d'être demandée. Écriture atomique
(fichier temporaire puis renommage), donc sûre entre processus parallèles.

Dossier : ``$CFD_TRAJCAST_CACHE``, sinon ``$XDG_CACHE_HOME/cfd-trajcast``, sinon
``~/.cache/cfd-trajcast``. ``CFD_TRAJCAST_CACHE=0`` désactive le cache. Le vider se fait
à la main (``rm -r``) : rien n'y est indispensable.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Any, cast

import numpy as np
from numpy.typing import NDArray

__all__ = ["VERSION", "dossier", "ecrire", "empreinte", "lire"]

#: Incrémentée quand le format d'une entrée change : les anciennes ne sont plus lues.
VERSION = "1"


def dossier() -> Path | None:
    """Le dossier du cache, ou ``None`` s'il est désactivé."""
    choix = os.environ.get("CFD_TRAJCAST_CACHE", "").strip()
    if choix.lower() in {"0", "non", "false", "off"}:
        return None
    if choix:
        return Path(choix).expanduser()
    base = os.environ.get("XDG_CACHE_HOME", "").strip()
    return (Path(base) if base else Path.home() / ".cache") / "cfd-trajcast"


def empreinte(*parties: bytes | str) -> str:
    """SHA-256 d'une suite de morceaux (chaque morceau préfixé de sa longueur : pas d'ambiguïté)."""
    h = hashlib.sha256(VERSION.encode())
    for p in parties:
        octets = p.encode("utf-8") if isinstance(p, str) else p
        h.update(len(octets).to_bytes(8, "little"))
        h.update(octets)
    return h.hexdigest()


def _chemin(espace: str, cle: str) -> Path | None:
    d = dossier()
    return None if d is None else d / espace / f"{cle}.npz"


def lire(espace: str, cle: str) -> dict[str, NDArray[np.generic]] | None:
    """L'entrée ``cle`` de ``espace``, ou ``None`` (absente, illisible ou cache désactivé)."""
    p = _chemin(espace, cle)
    if p is None or not p.is_file():
        return None
    try:
        with np.load(p, allow_pickle=False) as f:
            return {k: f[k] for k in f.files}
    except (OSError, ValueError, EOFError):
        return None  # entrée abîmée : on recalcule, l'écriture suivante la remplace


def ecrire(espace: str, cle: str, tableaux: dict[str, NDArray[np.generic]]) -> Path | None:
    """Écrit l'entrée ; ``None`` si le cache est désactivé ou le dossier non inscriptible."""
    p = _chemin(espace, cle)
    if p is None:
        return None
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
        with os.fdopen(fd, "wb") as f:
            np.savez(f, **cast("dict[str, Any]", tableaux))
        os.replace(tmp, p)
    except OSError:
        return None  # un cache qui ne peut pas écrire ne doit pas faire échouer le rendu
    return p
