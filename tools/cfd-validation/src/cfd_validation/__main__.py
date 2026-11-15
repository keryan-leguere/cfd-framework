"""Point d'entrée ``python -m cfd_validation``, équivalent strict de la commande ``cfd-validation``.

Utile là où le script console est inutilisable (interpréteur servi depuis une
image Apptainer, venv déplacé).
"""

from __future__ import annotations

import sys

from cfd_validation.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
