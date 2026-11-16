"""Point d'entrée ``python -m cfd_trajcast``, équivalent strict de la commande ``cfd-trajcast``."""

from __future__ import annotations

import sys

from cfd_trajcast.cli.main import main

if __name__ == "__main__":
    sys.exit(main())
