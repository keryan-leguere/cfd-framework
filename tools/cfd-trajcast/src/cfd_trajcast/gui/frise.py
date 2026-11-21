"""Frise temporelle : curseur (événements marqués), instant, lecture, vitesse, pas à pas."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PyQt5.QtCore import QPoint, QSignalBlocker, Qt
from PyQt5.QtGui import QColor, QPainter, QPolygon
from PyQt5.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QToolButton,
    QWidget,
)

from cfd_trajcast.gui.navigation import VITESSES, Navigation

__all__ = ["PAS_IMAGE", "CurseurTemps", "FriseTemporelle"]

#: Résolution du curseur (crans par seconde de vol).
CRANS_PAR_S = 100
#: Pas « image par image » (s de vol) ; ×20 avec Maj.
PAS_IMAGE = 0.05


class CurseurTemps(QSlider):
    """Curseur horizontal qui dessine un petit triangle à chaque événement."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Horizontal, parent)
        self.evenements: list[float] = []
        self.debut, self.fin = 0.0, 1.0

    def paintEvent(self, event: Any) -> None:
        super().paintEvent(event)
        if not self.evenements or self.fin <= self.debut:
            return
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        rainure = self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self)
        poignee = self.style().subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self)
        x0 = rainure.left() + poignee.width() // 2
        largeur = rainure.width() - poignee.width()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#0072B2"))
        p.setPen(Qt.NoPen)
        for te in self.evenements:
            x = x0 + round(largeur * (te - self.debut) / (self.fin - self.debut))
            y = rainure.bottom() + 2
            p.drawPolygon(QPolygon([QPoint(x - 4, y + 7), QPoint(x + 4, y + 7), QPoint(x, y)]))
        p.end()


class FriseTemporelle(QWidget):
    """La barre du bas ; ne tient aucun état : tout passe par la :class:`Navigation`."""

    def __init__(self, navigation: Navigation, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.navigation = navigation
        self.lecture = QToolButton()
        self.lecture.setToolTip("Lecture / pause (Espace)")
        self.precedent, self.suivant = QToolButton(), QToolButton()
        self.precedent.setText("◀")
        self.suivant.setText("▶")
        self.precedent.setToolTip(f"Reculer de {PAS_IMAGE:g} s (←, Maj : {20 * PAS_IMAGE:g} s)")
        self.suivant.setToolTip(f"Avancer de {PAS_IMAGE:g} s (→, Maj : {20 * PAS_IMAGE:g} s)")
        self.curseur = CurseurTemps()
        self.instant = QDoubleSpinBox()
        self.instant.setDecimals(2)
        self.instant.setSuffix(" s")
        self.instant.setKeyboardTracking(False)
        self.vitesse = QComboBox()
        for v in VITESSES:
            self.vitesse.addItem(f"×{v:g}".replace(".", ","), v)
        self.vitesse.setCurrentIndex(VITESSES.index(1.0))
        self.vitesse.setToolTip("Vitesse de lecture (s de vol par seconde)")
        self.evenements = QComboBox()
        self.evenements.setToolTip("Aller à un événement")
        disposition = QHBoxLayout(self)
        disposition.setContentsMargins(6, 2, 6, 2)
        for w in (self.lecture, self.precedent, self.suivant):
            disposition.addWidget(w)
        disposition.addWidget(self.curseur, 1)
        disposition.addWidget(self.instant)
        disposition.addWidget(QLabel("Vitesse"))
        disposition.addWidget(self.vitesse)
        disposition.addWidget(self.evenements)
        self._icones()
        self.lecture.clicked.connect(navigation.basculer)
        self.precedent.clicked.connect(lambda: navigation.pas(-PAS_IMAGE))
        self.suivant.clicked.connect(lambda: navigation.pas(PAS_IMAGE))
        self.curseur.valueChanged.connect(lambda v: navigation.aller(self.curseur.debut + v / CRANS_PAR_S))
        self.instant.valueChanged.connect(navigation.aller)
        self.vitesse.currentIndexChanged.connect(lambda i: setattr(navigation, "vitesse", float(VITESSES[i])))
        self.evenements.activated.connect(self._aller_evenement)
        navigation.temps_change.connect(self.afficher)
        navigation.lecture_change.connect(lambda _: self._icones())

    def _icones(self) -> None:
        icone = QStyle.SP_MediaPause if self.navigation.en_lecture else QStyle.SP_MediaPlay
        self.lecture.setIcon(self.style().standardIcon(icone))

    def configurer(self, debut: float, fin: float, evenements: Sequence[tuple[str, float]]) -> None:
        """Bornes du vol et liste des événements (nom, instant)."""
        c = self.curseur
        c.debut, c.fin, c.evenements = debut, fin, [te for _, te in evenements]
        with QSignalBlocker(c), QSignalBlocker(self.instant):
            c.setRange(0, max(1, round((fin - debut) * CRANS_PAR_S)))
            self.instant.setRange(debut, fin)
        self.evenements.clear()
        self.evenements.addItem("Événements…", None)
        for nom, te in evenements:
            self.evenements.addItem(f"{nom} — {te:.2f} s".replace(".", ","), te)
        self.evenements.setEnabled(bool(evenements))
        self.afficher(self.navigation.t)
        c.update()

    def afficher(self, t: float) -> None:
        with QSignalBlocker(self.curseur), QSignalBlocker(self.instant):
            self.curseur.setValue(round((t - self.curseur.debut) * CRANS_PAR_S))
            self.instant.setValue(t)

    def _aller_evenement(self, indice: int) -> None:
        te = self.evenements.itemData(indice)
        if te is not None:
            self.navigation.pause()
            self.navigation.aller(float(te))
        self.evenements.setCurrentIndex(0)
