"""Interface graphique interactive (PyQt5) : naviguer dans un vol.

::

    cfd-trajcast gui CONFIG.yaml        # ou : python -m cfd_trajcast gui CONFIG.yaml

La vue d'ensemble en grand (Matplotlib 3D, ou VTK si l'OpenGL fonctionne), une frise
temporelle (curseur, lecture, vitesse, événements), la télémétrie de n'importe quelle
colonne du fichier, les repères locaux au CDG et le vent. Toute la logique est dans
``engine`` (:class:`~cfd_trajcast.engine.etat_vol.EtatVol`,
:class:`~cfd_trajcast.engine.vue3d_mpl.VueMpl`, :mod:`~cfd_trajcast.engine.courbes`) ;
ce paquet ne fait que le câblage Qt, et il est le seul à importer PyQt5.

Ce module n'importe **pas** PyQt5 : :func:`lancer` prépare d'abord Qt
(:func:`~cfd_trajcast.gui._qt.preparer_qt`), sans quoi un environnement OpenFOAM
chargé fait se croiser deux Qt.
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path

__all__ = ["ErreurInterface", "disponible", "lancer"]


class ErreurInterface(RuntimeError):
    """PyQt5 (ou cfd-plot) absent."""


def disponible() -> str | None:
    """None si l'interface peut démarrer, sinon ce qui manque."""
    manquants = [m for m, nom in (("PyQt5", "PyQt5"), ("cfd_plot", "cfd-plot"))
                 if importlib.util.find_spec(m) is None]
    if manquants:
        return (f"il manque {', '.join(manquants)} : pip install 'cfd-trajcast[gui]' "
                "(et tools/cfd-plot du dépôt)")
    return None


def application(argv: Sequence[str] | None = None):  # type: ignore[no-untyped-def]
    """La ``QApplication`` (créée au besoin, Qt préparé d'abord)."""
    from cfd_trajcast.gui._qt import preparer_qt

    preparer_qt()
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv) if argv is not None else sys.argv[:1])
        app.setApplicationName("cfd-trajcast")
        app.setOrganizationName("cfd-framework")
        # Boutons et boîtes standard de Qt en français (traductions livrées dans la roue PyQt5).
        from PyQt5.QtCore import QLibraryInfo, QTranslator

        traduction = QTranslator(app)
        if traduction.load("qtbase_fr", QLibraryInfo.location(QLibraryInfo.TranslationsPath)):
            app.installTranslator(traduction)
    return app


def lancer(chemin: str | Path | None = None, *, moteur: str = "mpl") -> int:
    """Ouvre la fenêtre (et ``chemin`` s'il est donné) ; rend la main à sa fermeture."""
    manque = disponible()
    if manque:
        raise ErreurInterface(manque)
    app = application()
    from cfd_trajcast.gui.fenetre import FenetrePrincipale

    fenetre = FenetrePrincipale()
    fenetre.show()
    if chemin is not None:
        fenetre.ouvrir(Path(chemin))
        if moteur != "mpl":
            fenetre.choisir_moteur(moteur)
    return int(app.exec_())
