"""L'interface peut-elle s'ouvrir ici ? À lancer **dans un sous-processus**.

``python -m cfd_trajcast.gui.sonde_qt`` prépare Qt comme l'interface, ouvre une fenêtre
et rend la main. Ce qui peut échouer, et que ``cfd-trajcast diagnostic`` doit dire
avant l'utilisateur : le greffon de plateforme (``xcb``) qui ne se charge pas faute de
bibliothèques système (``libxcb-xinerama0``, ``libxkbcommon-x11-0``…), ou deux Qt qui
se croisent. Qt s'arrête alors par ``abort()``, d'où le sous-processus.
"""

from __future__ import annotations

import sys

__all__ = ["PREFIXE", "sonder"]

PREFIXE = "SONDE_QT:"


def sonder() -> int:
    from cfd_trajcast.gui import application

    app = application()
    from PyQt5.QtCore import qVersion
    from PyQt5.QtWidgets import QLabel

    fenetre = QLabel("sonde")
    fenetre.show()
    app.processEvents()
    print(PREFIXE, f"Qt {qVersion()}, plateforme {app.platformName()}", flush=True)
    fenetre.close()
    return 0


if __name__ == "__main__":
    sys.exit(sonder())
