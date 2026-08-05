"""Point d'entrée ``python -m cfd_perf``.

Équivalent strict de la commande ``cfd-perf``. Il existe pour les
installations où aucun script console n'est disponible — sources simplement
posées sur le disque et atteintes par ``PYTHONPATH``, sans ``pip install``
(voir la section « Rendre ``cfd-perf`` disponible » du README).
"""

from __future__ import annotations

import sys

from cfd_perf.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
