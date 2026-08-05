"""Point d'entrée ``python -m cfd_traj``.

Équivalent strict de la commande ``cfd-traj``. Il existe pour les
installations où aucun script console n'est disponible — sources simplement
posées sur le disque et atteintes par ``PYTHONPATH``, sans ``pip install``.
"""

from __future__ import annotations

import sys

from cfd_traj.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
