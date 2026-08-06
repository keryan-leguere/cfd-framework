"""Où trouver les données livrées avec le paquet.

Les adaptateurs bash (``ADAPTATEUR/``) et l'exemple prêt à l'emploi
(``01_EXEMPLE/``) sont embarqués *dans* le paquet et non à côté : c'est ce qui
permet à ``pip install cfd-perf`` de suffire, sans dépôt cloné ni variable
d'environnement pointant vers une arborescence.

Un adaptateur maison n'a donc pas à être déposé dans le site-packages : il
suffit de passer son chemin à ``--adaptateur``, ou de pointer
``CFD_PERF_ADAPTATEUR_DIR`` vers son propre répertoire d'adaptateurs.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Racine du paquet installé.
PACKAGE_DIR = Path(__file__).resolve().parent

#: Adaptateurs bash livrés (``interface.sh``, ``mock.sh``, ``OF.sh``).
ADAPTATEUR_DIR = PACKAGE_DIR / "ADAPTATEUR"

#: Exemple complet, copié par ``cfd-perf example``.
EXEMPLE_DIR = PACKAGE_DIR / "01_EXEMPLE"

#: Variable d'environnement pointant vers un répertoire d'adaptateurs maison.
ENV_ADAPTATEUR_DIR = "CFD_PERF_ADAPTATEUR_DIR"

HOTES_NOM = "hotes.yaml"


def adaptateur_dir() -> Path:
    """Répertoire d'adaptateurs actif : celui de l'utilisateur, sinon celui livré."""
    perso = os.environ.get(ENV_ADAPTATEUR_DIR, "").strip()
    if perso:
        return Path(perso).expanduser()
    return ADAPTATEUR_DIR


def hotes_file() -> Path:
    """Catalogue des machines connues, celui de l'utilisateur étant prioritaire."""
    perso = adaptateur_dir() / HOTES_NOM
    if perso.is_file():
        return perso
    return ADAPTATEUR_DIR / HOTES_NOM
