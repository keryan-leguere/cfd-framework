"""Point d'entrée ``python -m cfd_doe``, équivalent strict de la commande ``cfd-doe``.

Utile là où le script console est inutilisable (interpréteur servi depuis une
image Apptainer, venv déplacé).
"""

from __future__ import annotations

import sys

from cfd_doe.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
