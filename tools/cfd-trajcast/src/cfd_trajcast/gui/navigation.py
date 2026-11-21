"""L'instant courant, partagé par toute l'interface, et la lecture animée.

Un seul objet tient ``t`` ; tout le reste s'abonne à :attr:`Navigation.temps_change`.
La lecture avance ``t`` selon le **temps réel écoulé** × la vitesse, pas d'un pas fixe
par image : si le dessin est lent, des images sont sautées mais le vol ne ralentit pas.
"""

from __future__ import annotations

import time

from PyQt5.QtCore import QObject, QTimer, pyqtSignal

__all__ = ["IPS_LECTURE", "VITESSES", "Navigation"]

#: Cadence de la minuterie de lecture.
IPS_LECTURE = 30
#: Vitesses proposées (s de vol par s réelle).
VITESSES = (0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0)


class Navigation(QObject):
    """Instant courant dans ``[debut, fin]``, lecture/pause et vitesse."""

    temps_change = pyqtSignal(float)
    lecture_change = pyqtSignal(bool)

    def __init__(self, debut: float = 0.0, fin: float = 1.0, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.debut, self.fin = float(debut), float(fin)
        self.t = self.debut
        self.vitesse = 1.0
        self._minuterie = QTimer(self)
        self._minuterie.setInterval(round(1000 / IPS_LECTURE))
        self._minuterie.timeout.connect(self._avancer)
        self._dernier = 0.0

    def bornes(self, debut: float, fin: float) -> None:
        self.pause()
        self.debut, self.fin = float(debut), float(fin)
        self.aller(self.debut)

    def aller(self, t: float) -> None:
        """Se place en ``t`` (borné) ; émet ``temps_change`` si l'instant change."""
        t = min(max(float(t), self.debut), self.fin)
        if t != self.t:
            self.t = t
            self.temps_change.emit(t)

    def pas(self, dt: float) -> None:
        self.pause()
        self.aller(self.t + dt)

    @property
    def en_lecture(self) -> bool:
        return bool(self._minuterie.isActive())

    def lire(self) -> None:
        if self.t >= self.fin:
            self.aller(self.debut)
        self._dernier = time.monotonic()
        self._minuterie.start()
        self.lecture_change.emit(True)

    def pause(self) -> None:
        if self._minuterie.isActive():
            self._minuterie.stop()
            self.lecture_change.emit(False)

    def basculer(self) -> None:
        self.pause() if self.en_lecture else self.lire()

    def _avancer(self) -> None:
        maintenant = time.monotonic()
        dt, self._dernier = maintenant - self._dernier, maintenant
        self.aller(self.t + dt * self.vitesse)
        if self.t >= self.fin:
            self.pause()
