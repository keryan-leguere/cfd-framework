"""Identification d'une exécution : où, quand, avec quoi, sur quelles données.

C'est l'en-tête de toute pièce justificative (DO-178C §11.16, ECSS-E-ST-40
« configuration item », IEEE 29119-3 « test environment ») : un résultat de
test sans la version des outils et l'empreinte des données qui l'ont produit
ne se rejoue pas, donc ne prouve rien.

L'empreinte d'une table porte sur son **contenu** (noms de colonnes, types,
valeurs), pas sur son fichier : deux CSV formatés différemment mais lus à
l'identique ont la même empreinte, et une valeur modifiée d'un ULP la change.
"""

from __future__ import annotations

import getpass
import hashlib
import platform
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd

__all__ = ["Empreinte", "Environnement", "capturer_environnement", "empreinte_table"]


@dataclass(frozen=True)
class Empreinte:
    """Taille et SHA-256 du contenu d'une table."""

    n_lignes: int
    n_colonnes: int
    sha256: str

    @property
    def courte(self) -> str:
        return self.sha256[:16]


def empreinte_table(df: pd.DataFrame) -> Empreinte:
    """SHA-256 des noms, types et valeurs (l'index n'y entre pas)."""
    h = hashlib.sha256()
    for nom, dtype in zip(df.columns, df.dtypes):
        h.update(f"{nom}\x1f{dtype}\x1e".encode())
    valeurs = pd.util.hash_pandas_object(df, index=False).to_numpy(dtype=np.uint64)
    h.update(valeurs.tobytes())
    return Empreinte(n_lignes=len(df), n_colonnes=df.shape[1], sha256=h.hexdigest())


@dataclass(frozen=True)
class Environnement:
    """Machine, logiciels et horodatage de l'exécution du contrôle."""

    date: str
    hote: str
    utilisateur: str
    systeme: str
    python: str
    versions: Mapping[str, str] = field(default_factory=dict)


def _utilisateur() -> str:
    try:
        return getpass.getuser()
    except Exception:  # pas de compte résolu (conteneur) : sans conséquence
        return "inconnu"


def capturer_environnement() -> Environnement:
    """L'environnement courant, horodaté en UTC (ISO 8601)."""
    from cfd_validation import __version__

    versions = {"cfd-validation": __version__, "numpy": np.__version__, "pandas": pd.__version__}
    return Environnement(
        date=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        hote=platform.node() or "inconnu",
        utilisateur=_utilisateur(),
        systeme=f"{platform.system()} {platform.release()} ({platform.machine()})",
        python=f"{platform.python_implementation()} {sys.version.split()[0]}",
        versions=versions,
    )
