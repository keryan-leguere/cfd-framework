"""Exports depuis l'interface : vue courante, courbes, panneau vent, figure paper, vidéo.

Les images sont écrites dans le processus (quelques secondes au plus). La vidéo, elle,
tourne dans un sous-processus (:mod:`cfd_trajcast.gui.tache_video`) lancé par
``QProcess`` : l'interface reste réactive, une barre de progression suit les lignes
``PROGRES`` et « Annuler » tue le processus — aucun fichier à moitié écrit n'est gardé.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QProcess, Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QRadioButton,
    QWidget,
)

from cfd_trajcast.gui.tache_video import TacheVideo

__all__ = ["RESOLUTIONS", "DialogueVideo", "ExecutionVideo", "demander_fichier"]

#: Résolutions proposées pour la vidéo.
RESOLUTIONS = {"540p (960 × 540)": (960, 540), "1080p (1920 × 1080)": (1920, 1080),
               "4K (3840 × 2160)": (3840, 2160)}


def demander_fichier(parent: QWidget, titre: str, defaut: Path, filtres: str) -> Path | None:
    chemin, _ = QFileDialog.getSaveFileName(parent, titre, str(defaut), filtres)
    return Path(chemin) if chemin else None


class DialogueVideo(QDialog):
    """Mode (sans rendu / rendu 3D), intervalle, résolution, durée, fichier."""

    def __init__(self, debut: float, fin: float, sortie: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Exporter une vidéo")
        f = QFormLayout(self)
        self.sans_rendu = QRadioButton("Figure animée — sans rendu 3D (ni OpenGL ni GPU)")
        self.rendu = QRadioButton("Vue d'ensemble rendue en 3D (PyVista)")
        self.sans_rendu.setChecked(True)
        f.addRow(self.sans_rendu)
        f.addRow(self.rendu)
        self.de, self.a = QDoubleSpinBox(), QDoubleSpinBox()
        for w, v in ((self.de, debut), (self.a, fin)):
            w.setRange(debut, fin)
            w.setDecimals(2)
            w.setSuffix(" s")
            w.setValue(v)
        intervalle = QHBoxLayout()
        intervalle.addWidget(self.de)
        intervalle.addWidget(self.a)
        f.addRow("Intervalle du vol", intervalle)
        self.resolution = QComboBox()
        for nom in RESOLUTIONS:
            self.resolution.addItem(nom)
        self.resolution.setCurrentIndex(1)
        f.addRow("Résolution", self.resolution)
        self.fixer_duree = QCheckBox("imposer la durée")
        self.duree = QDoubleSpinBox()
        self.duree.setRange(1.0, 3600.0)
        self.duree.setValue(20.0)
        self.duree.setSuffix(" s de vidéo")
        self.duree.setEnabled(False)
        self.fixer_duree.toggled.connect(self.duree.setEnabled)
        ligne = QHBoxLayout()
        ligne.addWidget(self.fixer_duree)
        ligne.addWidget(self.duree)
        f.addRow("Durée (sinon : section video)", ligne)
        self.sortie = QLineEdit(str(sortie))
        parcourir = QPushButton("…")
        parcourir.clicked.connect(self._parcourir)
        ligne = QHBoxLayout()
        ligne.addWidget(self.sortie)
        ligne.addWidget(parcourir)
        f.addRow("Fichier", ligne)
        boutons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        boutons.accepted.connect(self._valider)
        boutons.rejected.connect(self.reject)
        f.addRow(boutons)

    def _parcourir(self) -> None:
        chemin = demander_fichier(self, "Vidéo", Path(self.sortie.text()), "Vidéo MP4 (*.mp4)")
        if chemin is not None:
            self.sortie.setText(str(chemin.with_suffix(".mp4")))

    def _valider(self) -> None:
        if self.a.value() <= self.de.value():
            QMessageBox.warning(self, "Intervalle", "La fin doit être après le début.")
            return
        self.accept()

    def tache(self, config: Path, repere: str | None = None) -> TacheVideo:
        return TacheVideo(
            config=str(config), sortie=str(Path(self.sortie.text()).with_suffix(".mp4")),
            mode="sans_rendu" if self.sans_rendu.isChecked() else "rendu",
            de=float(self.de.value()), a=float(self.a.value()),
            resolution=RESOLUTIONS[self.resolution.currentText()],
            duree=float(self.duree.value()) if self.fixer_duree.isChecked() else None, repere=repere,
        )


class ExecutionVideo:
    """Lance une :class:`TacheVideo` dans un sous-processus, avec progression et annulation."""

    def __init__(self, tache: TacheVideo, parent: QWidget) -> None:
        self.tache, self.parent = tache, parent
        self.resultat: str | None = None
        self.erreur: str | None = None
        self.processus = QProcess(parent)
        self.processus.setProcessChannelMode(QProcess.SeparateChannels)
        self.progres = QProgressDialog("Vidéo en préparation…", "Annuler", 0, 0, parent)
        self.progres.setWindowTitle("Export vidéo")
        self.progres.setWindowModality(Qt.WindowModal)
        self.progres.setMinimumDuration(0)
        self.progres.canceled.connect(self.annuler)
        self.processus.readyReadStandardOutput.connect(self._lire)
        self.processus.finished.connect(self._fini)
        self._reste = ""

    def demarrer(self) -> None:
        self.processus.start(sys.executable, ["-m", "cfd_trajcast.gui.tache_video", self.tache.vers_json()])

    def attendre(self, ms: int = -1) -> bool:
        """Pour les tests et les scripts : bloque jusqu'à la fin."""
        return bool(self.processus.waitForFinished(ms))

    def annuler(self) -> None:
        if self.processus.state() != QProcess.NotRunning:
            self.processus.kill()
            self.processus.waitForFinished(5000)
            Path(self.tache.sortie).unlink(missing_ok=True)
            self.erreur = "annulée"

    def _lire(self) -> None:
        texte = self._reste + bytes(self.processus.readAllStandardOutput()).decode("utf-8", "replace")
        *lignes, self._reste = texte.split("\n")
        for ligne in lignes:
            mots = ligne.strip().split(" ", 1)
            if mots[0] == "PROGRES":
                fait, total = (int(x) for x in mots[1].split())
                self.progres.setMaximum(total)
                self.progres.setValue(fait)
                self.progres.setLabelText(f"Image {fait} / {total}")
            elif mots[0] == "FINI":
                self.resultat = mots[1]
            elif mots[0] == "ERREUR":
                self.erreur = mots[1] if len(mots) > 1 else "échec"

    def _fini(self, code: int, *_: Any) -> None:
        self._lire()
        self.progres.reset()
        if self.erreur is None and (code != 0 or self.resultat is None):
            erreur = bytes(self.processus.readAllStandardError()).decode("utf-8", "replace").strip()
            self.erreur = erreur.splitlines()[-1] if erreur else f"code de retour {code}"
