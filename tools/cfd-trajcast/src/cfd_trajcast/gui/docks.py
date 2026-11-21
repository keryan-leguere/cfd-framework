"""Panneaux latéraux : Télémétrie (colonnes à cocher + courbes), Affichage (couches), Vent."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from PyQt5.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QCheckBox,
    QDockWidget,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cfd_trajcast.core.reperes_locaux import REPERES_LOCAUX
from cfd_trajcast.engine.courbes import Courbes, PanneauVent
from cfd_trajcast.engine.etat_vol import EtatVol
from cfd_trajcast.engine.telemetrie import formater
from cfd_trajcast.engine.vue3d_mpl import COULEURS_REPERES, LIBELLES_REPERES, OptionsVue
from cfd_trajcast.gui.canevas import Canevas

__all__ = ["DockAffichage", "DockTelemetrie", "DockVent"]

_GROUPES = {"calcul": "Calculées", "vent": "Vent", "cdg": "CDG", "colonne": "Colonnes du fichier"}


class DockTelemetrie(QDockWidget):
    """Toutes les séries (calculées et colonnes du fichier), à cocher ; une courbe par coche."""

    selection_change = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Télémétrie", parent)
        self.setObjectName("dock_telemetrie")
        self.etat: EtatVol | None = None
        self.filtre = QLineEdit()
        self.filtre.setPlaceholderText("Filtrer les grandeurs…")
        self.filtre.setClearButtonEnabled(True)
        self.arbre = QTreeWidget()
        self.arbre.setHeaderLabels(["Grandeur", "Valeur"])
        self.arbre.setRootIsDecorated(True)
        self.canevas = Canevas(5, 6)
        self.courbes: Courbes | None = None
        haut = QWidget()
        lay = QVBoxLayout(haut)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.filtre)
        lay.addWidget(self.arbre)
        separateur = QSplitter(Qt.Vertical)
        separateur.addWidget(haut)
        separateur.addWidget(self.canevas)
        separateur.setSizes([260, 520])
        self.setWidget(separateur)
        self.filtre.textChanged.connect(self._filtrer)
        self.arbre.itemChanged.connect(self._coche)

    def charger(self, etat: EtatVol, cochees: Sequence[str] = ()) -> None:
        self.etat = etat
        self.courbes = Courbes(self.canevas.figure, etat)
        with QSignalBlocker(self.arbre):
            self.arbre.clear()
            groupes: dict[str, QTreeWidgetItem] = {}
            for cle, serie in etat.series.items():
                if serie.source not in groupes:
                    g = QTreeWidgetItem([_GROUPES.get(serie.source, serie.source)])
                    g.setFlags(g.flags() & ~Qt.ItemIsUserCheckable)
                    self.arbre.addTopLevelItem(g)
                    groupes[serie.source] = g
                texte = f"{serie.libelle} ({serie.unite})" if serie.unite else serie.libelle
                item = QTreeWidgetItem([texte, ""])
                item.setData(0, Qt.UserRole, cle)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(0, Qt.Checked if cle in cochees else Qt.Unchecked)
                item.setToolTip(0, f"{cle} — {'colonne du fichier' if serie.source == 'colonne' else 'calculée'}")
                groupes[serie.source].addChild(item)
            self.arbre.expandAll()
            self.arbre.resizeColumnToContents(0)
        self._appliquer()

    def cochees(self) -> list[str]:
        out = []
        for i in range(self.arbre.topLevelItemCount()):
            g = self.arbre.topLevelItem(i)
            for j in range(g.childCount()):
                item = g.child(j)
                if item.checkState(0) == Qt.Checked:
                    out.append(str(item.data(0, Qt.UserRole)))
        return out

    def cocher(self, cles: Sequence[str]) -> None:
        with QSignalBlocker(self.arbre):
            for item in self._items():
                item.setCheckState(0, Qt.Checked if item.data(0, Qt.UserRole) in cles else Qt.Unchecked)
        self._appliquer()

    def _items(self) -> list[Any]:
        items: list[Any] = []
        for i in range(self.arbre.topLevelItemCount()):
            groupe = self.arbre.topLevelItem(i)
            items += [groupe.child(j) for j in range(groupe.childCount())]
        return items

    def _coche(self, item: QTreeWidgetItem, colonne: int) -> None:
        if colonne == 0 and item.data(0, Qt.UserRole) is not None:
            self._appliquer()

    def _appliquer(self) -> None:
        if self.courbes is None:
            return
        cles = self.cochees()
        self.courbes.choisir(cles)
        if self.etat is not None:
            self.courbes.poser(self.courbes.t)
        self.canevas.draw_idle()
        self.selection_change.emit(cles)

    def _filtrer(self, texte: str) -> None:
        texte = texte.strip().lower()
        for item in self._items():
            item.setHidden(bool(texte) and texte not in item.text(0).lower()
                           and texte not in str(item.data(0, Qt.UserRole)).lower())

    def poser(self, t: float) -> None:
        """Valeurs à l'instant ``t`` et curseur des courbes."""
        if self.etat is None or self.courbes is None:
            return
        for item in self._items():
            if item.isHidden():
                continue
            cle = str(item.data(0, Qt.UserRole))
            serie = self.etat.series[cle]
            item.setText(1, formater(self.etat.valeur(cle, t), serie.unite, serie.decimales))
        self.courbes.poser(t)
        self.canevas.draw_idle()

    def relier_clic(self, aller: Callable[[float], None]) -> None:
        """Un clic dans une courbe place le temps."""
        def clic(event: Any) -> None:
            if self.courbes is not None and event.button == 1:
                t = self.courbes.instant(event.inaxes, event.xdata)
                if t is not None:
                    aller(t)
        self.canevas.mpl_connect("button_press_event", clic)


class DockAffichage(QDockWidget):
    """Couches de la vue 3D (repères au CDG, vent, maquette, trace au sol, agrandissement) et zoom."""

    options_change = pyqtSignal(object)
    #: « plus », « moins », « entier » (le vol entier) ou « engin » (cadrer l'engin).
    zoom_demande = pyqtSignal(str)
    suivi_change = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Affichage", parent)
        self.setObjectName("dock_affichage")
        corps = QWidget()
        lay = QVBoxLayout(corps)
        groupe = QGroupBox("Repères au CDG")
        g = QVBoxLayout(groupe)
        self.reperes: dict[str, QCheckBox] = {}
        for nom in REPERES_LOCAUX:
            case = QCheckBox(LIBELLES_REPERES[nom])
            case.setStyleSheet(f"QCheckBox {{ color: {COULEURS_REPERES[nom]}; }}")
            g.addWidget(case)
            self.reperes[nom] = case
        lay.addWidget(groupe)
        couches = QGroupBox("Couches")
        f = QFormLayout(couches)
        self.vent = QCheckBox("Flèches de vent le long du vol")
        self.maquette = QCheckBox("Maquette")
        self.trace_sol = QCheckBox("Trace au sol")
        self.evenements = QCheckBox("Événements atteints")
        for w in (self.vent, self.maquette, self.trace_sol, self.evenements):
            f.addRow(w)
        self.auto = QCheckBox("auto")
        self.agrandissement = QDoubleSpinBox()
        self.agrandissement.setRange(1.0, 100000.0)
        self.agrandissement.setDecimals(0)
        self.agrandissement.setPrefix("× ")
        f.addRow("Agrandissement de la maquette", self.agrandissement)
        f.addRow("", self.auto)
        lay.addWidget(couches)
        zoom = QGroupBox("Zoom")
        z = QVBoxLayout(zoom)
        ligne = QHBoxLayout()
        self.boutons_zoom: dict[str, QPushButton] = {}
        for cle, texte, aide in (("moins", "\u2212", "Dézoomer (Ctrl+\u2212)"), ("plus", "+", "Zoomer (Ctrl++, molette)"),
                                 ("entier", "Vol entier", "Tout le vol (Ctrl+0)"),
                                 ("engin", "Engin", "Cadrer l'engin et le suivre (Ctrl+1)")):
            bouton = QPushButton(texte)
            bouton.setToolTip(aide)
            if cle in ("moins", "plus"):
                bouton.setFixedWidth(32)
            bouton.clicked.connect(lambda _=False, c=cle: self.zoom_demande.emit(c))
            ligne.addWidget(bouton)
            self.boutons_zoom[cle] = bouton
        z.addLayout(ligne)
        self.suivre = QCheckBox("Suivre l'engin (centre = CDG)")
        self.suivre.toggled.connect(self.suivi_change.emit)
        z.addWidget(self.suivre)
        self.niveau_zoom = QLabel()
        self.niveau_zoom.setStyleSheet("color: gray;")
        z.addWidget(self.niveau_zoom)
        lay.addWidget(zoom)
        self.afficher_zoom(1.0, False)
        lay.addStretch(1)
        self.setWidget(corps)
        for w in (*self.reperes.values(), self.vent, self.maquette, self.trace_sol, self.evenements, self.auto):
            w.toggled.connect(self._emettre)
        self.agrandissement.valueChanged.connect(self._emettre)

    def afficher(self, options: OptionsVue, echelle_auto: float, vent_disponible: bool) -> None:
        bloqueurs = [QSignalBlocker(w) for w in (*self.reperes.values(), self.vent, self.maquette,
                                                 self.trace_sol, self.evenements, self.auto, self.agrandissement)]
        for nom, case in self.reperes.items():
            case.setChecked(nom in options.reperes)
        self.reperes["aero"].setEnabled(vent_disponible)
        self.reperes["aero"].setToolTip("" if vent_disponible else "demande une section vent dans le YAML")
        self.vent.setChecked(options.vent and vent_disponible)
        self.vent.setEnabled(vent_disponible)
        self.maquette.setChecked(options.maquette)
        self.trace_sol.setChecked(options.trace_sol)
        self.evenements.setChecked(options.evenements)
        self.auto.setChecked(options.agrandissement is None)
        self.agrandissement.setValue(options.agrandissement or echelle_auto)
        self.agrandissement.setEnabled(options.agrandissement is not None)
        del bloqueurs

    def afficher_zoom(self, zoom: float, suivre: bool) -> None:
        """Niveau de zoom et case « suivre », sans réémettre de signal."""
        bloqueur = QSignalBlocker(self.suivre)
        self.suivre.setChecked(suivre)
        del bloqueur
        texte = f"{zoom:.1f}".replace(".", ",") if zoom < 10 else f"{zoom:.0f}"
        self.niveau_zoom.setText("vol entier" if zoom < 1.01 else f"zoom × {texte}")

    def options(self) -> OptionsVue:
        return OptionsVue(
            reperes=frozenset(n for n, c in self.reperes.items() if c.isChecked() and c.isEnabled()),
            vent=self.vent.isChecked() and self.vent.isEnabled(), maquette=self.maquette.isChecked(),
            trace_sol=self.trace_sol.isChecked(), evenements=self.evenements.isChecked(),
            agrandissement=None if self.auto.isChecked() else float(self.agrandissement.value()),
        )

    def _emettre(self, *_: object) -> None:
        self.agrandissement.setEnabled(not self.auto.isChecked())
        self.options_change.emit(self.options())


class DockVent(QDockWidget):
    """Hodographe et vent vertical, point courant marqué."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Vent", parent)
        self.setObjectName("dock_vent")
        self.canevas = Canevas(7, 3)
        self.panneau: PanneauVent | None = None
        self.setWidget(self.canevas)

    def charger(self, etat: EtatVol) -> None:
        self.canevas.figure.clear()
        self.panneau = PanneauVent(self.canevas.figure, etat) if etat.vent is not None else None
        if self.panneau is None:
            self.canevas.figure.text(0.5, 0.5, "Pas de vent déclaré (section vent du YAML)", ha="center",
                                     va="center", color="0.5")
        self.canevas.draw_idle()

    def poser(self, t: float) -> None:
        if self.panneau is not None and self.isVisible():
            self.panneau.poser(t)
            self.canevas.draw_idle()
