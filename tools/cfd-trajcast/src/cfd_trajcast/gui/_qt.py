"""Préparer Qt **avant** d'importer PyQt5 : bibliothèques de la roue, synchronisation verticale.

Deux pièges mesurés au jalon G0 (``00_DOC/09_INTERFACE.md``) :

* **Deux Qt dans le même processus.** Un ``LD_LIBRARY_PATH`` qui contient
  ``/usr/lib/x86_64-linux-gnu`` — ce que fait l'environnement OpenFOAM — fait trouver
  au chargeur le Qt du système avant celui de la roue PyQt5, et Qt s'arrête net :
  « Cannot mix incompatible Qt library (5.15.13) with this library (5.15.19) ». Le
  ``LD_LIBRARY_PATH`` est lu au démarrage du processus, le modifier ensuite ne sert à
  rien : on **précharge** les bibliothèques Qt de la roue par leur chemin complet
  (``RTLD_GLOBAL``), comme le TBB de bpy. Les suivantes se résolvent alors par leur nom
  sur celles déjà chargées.
* **VTK à 2 images/s** sous XWayland : Mesa attend la synchronisation verticale d'une
  fenêtre qu'il ne voit pas. ``vblank_mode=0`` (Mesa) et ``__GL_SYNC_TO_VBLANK=0``
  (NVIDIA) la coupent ; 250 images/s ensuite. Un choix explicite de l'utilisateur prime.
"""

from __future__ import annotations

import ctypes
import importlib.util
import os
import sys
from pathlib import Path

__all__ = ["BIBLIOTHEQUES", "preparer_qt"]

#: Dans l'ordre des dépendances ; celles qui manquent (roue allégée) sont ignorées.
BIBLIOTHEQUES = ("Core", "DBus", "Gui", "Network", "Widgets", "OpenGL", "PrintSupport", "Svg",
                 "X11Extras", "XcbQpa", "WaylandClient", "EglFSDeviceIntegration")

_FAIT: list[str] = []


def preparer_qt() -> list[str]:
    """Précharge le Qt de la roue PyQt5 et coupe la synchronisation verticale ; idempotent.

    Renvoie les bibliothèques préchargées (vide hors Linux ou sans roue PyQt5).
    """
    if _FAIT:
        return list(_FAIT)
    os.environ.setdefault("vblank_mode", "0")
    os.environ.setdefault("__GL_SYNC_TO_VBLANK", "0")
    os.environ.setdefault("QT_API", "pyqt5")  # pyvistaqt passe par qtpy : le même Qt que nous
    spec = importlib.util.find_spec("PyQt5")
    if spec is None or spec.origin is None or not sys.platform.startswith("linux"):
        return []
    dossier = Path(spec.origin).parent / "Qt5" / "lib"
    for nom in BIBLIOTHEQUES:
        chemin = dossier / f"libQt5{nom}.so.5"
        if not chemin.is_file():
            continue
        try:
            ctypes.CDLL(str(chemin), mode=ctypes.RTLD_GLOBAL)
        except OSError:
            continue  # dépendance système absente : cette bibliothèque ne servira pas
        _FAIT.append(nom)
    return list(_FAIT)
