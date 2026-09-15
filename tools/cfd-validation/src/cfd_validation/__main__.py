"""Point d'entrée ``python -m cfd_validation``.

Équivalent strict de la commande ``cfd-validation``. Il existe pour les
installations où aucun script console n'est utilisable — sources simplement
posées sur le disque et atteintes par ``PYTHONPATH``, ou interpréteur servi
depuis une image Apptainer, où le shebang gravé par pip pointe un chemin
interne à l'image.
"""

from __future__ import annotations

import sys

from cfd_validation.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
