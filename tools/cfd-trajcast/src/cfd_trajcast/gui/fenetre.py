"""Fenêtre principale : vue d'ensemble en grand, frise temporelle, docks, menus."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from PyQt5.QtCore import QSettings, QSignalBlocker, Qt, QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QActionGroup,
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QShortcut,
    QStackedWidget,
    QWidget,
)

from cfd_trajcast.core.camera import ParametresEnsemble
from cfd_trajcast.data.configuration import Configuration, charger_configuration
from cfd_trajcast.engine.etat_vol import EtatVol
from cfd_trajcast.engine.vue3d_mpl import PAS_ZOOM, OptionsVue, VueMpl
from cfd_trajcast.gui.canevas import Canevas
from cfd_trajcast.gui.docks import DockAffichage, DockTelemetrie, DockVent
from cfd_trajcast.gui.frise import PAS_IMAGE, FriseTemporelle
from cfd_trajcast.gui.navigation import Navigation

__all__ = ["SELECTION_DEFAUT", "FenetrePrincipale"]

#: Grandeurs cochées à la première ouverture d'un fichier.
SELECTION_DEFAUT = ("altitude", "vitesse", "mach")
#: Un relâcher à moins de tant de pixels de l'appui est un clic, pas une rotation.
TOLERANCE_CLIC_PX = 4


def _cle_fichier(chemin: Path) -> str:
    return hashlib.sha1(str(chemin.resolve()).encode("utf-8")).hexdigest()[:16]


class FenetrePrincipale(QMainWindow):
    """L'interface ; :meth:`ouvrir` charge un fichier de configuration."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("cfd-trajcast")
        self.resize(1600, 1000)
        self.reglages = QSettings("cfd-framework", "cfd-trajcast")
        self.navigation = Navigation()
        self.configuration: Configuration | None = None
        self.etat: EtatVol | None = None
        self.vue: VueMpl | None = None
        self.vue_vtk: Any = None
        self.moteur = "mpl"
        self._sonde: tuple[bool, str] | None = None
        self.canevas: Canevas | None = None
        self._appui: tuple[float, float] | None = None

        self.centre = QStackedWidget()
        accueil = QLabel("Fichier \u203a Ouvrir… un fichier de configuration (YAML)")
        accueil.setAlignment(Qt.AlignCenter)
        self.centre.addWidget(accueil)
        self.setCentralWidget(self.centre)
        self.frise = FriseTemporelle(self.navigation)
        self.frise.setEnabled(False)
        from PyQt5.QtWidgets import QDockWidget

        bas = QDockWidget("Temps", self)
        bas.setObjectName("dock_temps")
        bas.setWidget(self.frise)
        bas.setFeatures(QDockWidget.NoDockWidgetFeatures)
        bas.setTitleBarWidget(QWidget())
        self.addDockWidget(Qt.BottomDockWidgetArea, bas)
        self.telemetrie = DockTelemetrie(self)
        self.affichage = DockAffichage(self)
        self.vent = DockVent(self)
        # La vue 3D au centre, en grand : Affichage étroit à gauche, Télémétrie et Vent en onglets
        # à droite (la disposition modifiée par l'utilisateur est retrouvée à l'ouverture suivante).
        self.addDockWidget(Qt.LeftDockWidgetArea, self.affichage)
        self.addDockWidget(Qt.RightDockWidgetArea, self.telemetrie)
        self.tabifyDockWidget(self.telemetrie, self.vent)
        self.telemetrie.raise_()
        self.resizeDocks([self.affichage, self.telemetrie], [270, 480], Qt.Horizontal)
        self.statut = QLabel()
        self.statusBar().addPermanentWidget(self.statut)

        self.navigation.temps_change.connect(self._poser)
        self.affichage.options_change.connect(self._options)
        self.affichage.zoom_demande.connect(self._demander_zoom)
        self.affichage.suivi_change.connect(self.suivre_engin)
        self.telemetrie.selection_change.connect(self._memoriser_selection)
        self.telemetrie.relier_clic(self._aller_pause)
        self._menus()
        self._raccourcis()
        etat = self.reglages.value("fenetre/etat")
        if etat is not None:
            self.restoreState(etat)

    # -- menus ------------------------------------------------------------------------------
    def _menus(self) -> None:
        fichier = self.menuBar().addMenu("&Fichier")
        ouvrir = QAction("&Ouvrir une configuration…", self)
        ouvrir.setShortcut(QKeySequence.Open)
        ouvrir.triggered.connect(self._ouvrir_dialogue)
        fichier.addAction(ouvrir)
        nouveau = QAction("&Nouveau vol depuis un CSV…", self)
        nouveau.setShortcut(QKeySequence.New)
        nouveau.triggered.connect(self.assistant_csv)  # type: ignore[arg-type]  # « checked » écarté plus bas
        fichier.addAction(nouveau)
        self.menu_fichier = fichier
        fichier.addSeparator()
        quitter = QAction("&Quitter", self)
        quitter.setShortcut(QKeySequence.Quit)
        quitter.triggered.connect(self._quitter)
        fichier.addAction(quitter)
        self.menu_exporter = self.menuBar().addMenu("&Exporter")
        for texte, rappel in (("Vue courante (PDF, SVG, PNG)…", self.exporter_vue),
                              ("Courbes de télémétrie…", self.exporter_courbes),
                              ("Panneau vent…", self.exporter_vent),
                              ("Figure paper du vol entier…", self.exporter_figure),
                              (None, None),
                              ("Vidéo…", self.exporter_video)):
            if texte is None:
                self.menu_exporter.addSeparator()
                continue
            action = QAction(texte, self)
            action.triggered.connect(rappel)  # type: ignore[arg-type]  # PyQt ignore le booléen « checked »
            self.menu_exporter.addAction(action)
        self.menu_exporter.setEnabled(False)
        affichage = self.menuBar().addMenu("&Affichage")
        for dock in (self.telemetrie, self.affichage, self.vent):
            affichage.addAction(dock.toggleViewAction())
        affichage.addSeparator()
        self.menu_moteur = affichage.addMenu("Moteur de la vue 3D")
        self.groupe_moteur = QActionGroup(self)
        for moteur, texte in (("mpl", "Matplotlib (sans OpenGL)"), ("vtk", "VTK (OpenGL, rotation fluide)")):
            action = QAction(texte, self)
            action.setCheckable(True)
            action.setChecked(moteur == "mpl")
            action.setData(moteur)
            self.groupe_moteur.addAction(action)
            self.menu_moteur.addAction(action)
        self.groupe_moteur.triggered.connect(self._moteur_choisi)
        affichage.addSeparator()
        self.menu_zoom = affichage.addMenu("&Zoom")
        for texte, touche, cle in (("Zoomer", QKeySequence.ZoomIn, "plus"), ("Dézoomer", QKeySequence.ZoomOut, "moins"),
                                   ("Vol entier", "Ctrl+0", "entier"), ("Cadrer l'engin", "Ctrl+1", "engin")):
            action = QAction(texte, self)
            # Ctrl+= aussi : sur un clavier AZERTY comme QWERTY, « + » demande la touche Maj.
            action.setShortcuts([QKeySequence(touche)] + ([QKeySequence("Ctrl+=")] if cle == "plus" else []))
            action.setShortcutContext(Qt.ApplicationShortcut)
            action.triggered.connect(lambda _=False, c=cle: self._demander_zoom(c))
            self.menu_zoom.addAction(action)
        self.action_suivre = QAction("Suivre l'engin", self)
        self.action_suivre.setCheckable(True)
        self.action_suivre.toggled.connect(self.suivre_engin)
        self.menu_zoom.addAction(self.action_suivre)
        self.menu_zoom.setEnabled(False)

    def _raccourcis(self) -> None:
        nav = self.navigation
        for touche, action in (
            ("Space", nav.basculer),
            ("Left", lambda: nav.pas(-PAS_IMAGE)), ("Right", lambda: nav.pas(PAS_IMAGE)),
            ("Shift+Left", lambda: nav.pas(-20 * PAS_IMAGE)), ("Shift+Right", lambda: nav.pas(20 * PAS_IMAGE)),
            ("Home", lambda: self._aller_pause(nav.debut)), ("End", lambda: self._aller_pause(nav.fin)),
        ):
            raccourci = QShortcut(QKeySequence(touche), self)
            raccourci.setContext(Qt.ApplicationShortcut)
            raccourci.activated.connect(action)

    # -- chargement ---------------------------------------------------------------------------
    def assistant_csv(self, csv: Path | None = None) -> Path | None:
        """Assistant CSV → YAML ; ouvre le fichier écrit."""
        from cfd_trajcast.gui.assistant import AssistantCsv

        assistant = AssistantCsv(self, csv if isinstance(csv, Path) else None)
        if assistant.exec_() and assistant.ecrit is not None:
            self.ouvrir(assistant.ecrit)
            return assistant.ecrit
        return None

    def _ouvrir_dialogue(self) -> None:
        chemin, _ = QFileDialog.getOpenFileName(self, "Ouvrir une configuration", "",
                                                "Configuration cfd-trajcast (*.yaml *.yml)")
        if chemin:
            self.ouvrir(Path(chemin))

    def ouvrir(self, chemin: Path) -> bool:
        """Charge un fichier ; un message d'erreur clair plutôt qu'une exception."""
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            cfg = charger_configuration(chemin)
            etat = EtatVol.depuis_configuration(cfg)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Fichier illisible", f"{chemin}\n\n{exc}")
            return False
        try:
            self._installer(cfg, etat)
        finally:
            QApplication.restoreOverrideCursor()
        self.setWindowTitle(f"cfd-trajcast — {chemin.name}")
        return True

    def _parametres(self, cfg: Configuration) -> ParametresEnsemble:
        return next((p for _, p in cfg.vues if isinstance(p, ParametresEnsemble)), ParametresEnsemble())

    def _installer(self, cfg: Configuration, etat: EtatVol) -> None:
        self.navigation.pause()
        self.configuration, self.etat = cfg, etat
        self._cle = _cle_fichier(cfg.chemin) if cfg.chemin else "sans_fichier"
        options = OptionsVue(reperes=frozenset({"corps"}), vent=etat.vent is not None)
        canevas = Canevas(10, 8)
        self.vue = VueMpl(canevas.figure, etat, self._parametres(cfg), sol_altitude=cfg.style.sol_altitude,
                          options=options)
        if self.canevas is not None:
            self.centre.removeWidget(self.canevas)
            self.canevas.deleteLater()
        self.canevas = canevas
        self.centre.addWidget(canevas)
        self.centre.setCurrentWidget(canevas)
        canevas.mpl_connect("button_press_event", self._appuyer)
        canevas.mpl_connect("button_release_event", self._relacher)
        canevas.mpl_connect("scroll_event", self._molette)
        if self.vue_vtk is not None:
            self.centre.removeWidget(self.vue_vtk.widget)
            self.vue_vtk.fermer()
            self.vue_vtk = None
        self.moteur = "mpl"
        self._cocher_moteur("mpl")
        self.navigation.bornes(etat.debut, etat.fin)
        self.frise.configurer(etat.debut, etat.fin, [(e.nom, float(e.t)) for e in etat.trajectoire.evenements])
        self.frise.setEnabled(True)
        self.menu_exporter.setEnabled(True)
        self.menu_zoom.setEnabled(True)
        self._zoom_affiche()
        selection = self.reglages.value(f"telemetrie/{self._cle}")
        cochees = [c for c in (selection if isinstance(selection, list) else SELECTION_DEFAUT) if c in etat.series]
        self.telemetrie.charger(etat, cochees)
        self.affichage.afficher(options, self.vue.scene.echelle, etat.vent is not None)
        self.vent.charger(etat)
        d = etat.description()
        morceaux = [f"{len(etat.t)} instants, {d['colonnes']} colonnes",
                    f"vent : {d['vent']}" if d["vent"] else "sans vent",
                    f"CDG : {d['cdg']}" if d["cdg"] else "CDG = point suivi"]
        self.statut.setText(" · ".join(morceaux))
        self._poser(self.navigation.t)

    # -- synchronisation ---------------------------------------------------------------------
    def _poser(self, t: float) -> None:
        if self.vue is None or self.canevas is None:
            return
        if self.moteur == "vtk" and self.vue_vtk is not None:
            self.vue_vtk.poser(t)
        else:
            self.vue.poser(t)
            self.canevas.draw_idle()
        self.telemetrie.poser(t)
        self.vent.poser(t)

    def _options(self, options: OptionsVue) -> None:
        if self.vue is not None and self.canevas is not None:
            self.vue.regler(options)
            self.canevas.draw_idle()
        if self.vue_vtk is not None:
            self.vue_vtk.regler(options)

    # -- zoom ---------------------------------------------------------------------------------------
    def _vue_active(self) -> Any:
        return self.vue_vtk if self.moteur == "vtk" and self.vue_vtk is not None else self.vue

    def zoomer(self, demande: str, vers: Any = None) -> float:
        """« plus », « moins », « entier » ou « engin » sur la vue active ; renvoie le zoom obtenu."""
        vue = self._vue_active()
        if vue is None:
            return 1.0
        if demande == "entier":
            vue.vue_entiere()
        elif demande == "engin":
            vue.cadrer_engin()
        elif vers is not None and vue is self.vue:
            vue.zoomer(PAS_ZOOM if demande == "plus" else 1 / PAS_ZOOM, vers=vers)
        else:
            vue.zoomer(PAS_ZOOM if demande == "plus" else 1 / PAS_ZOOM)
        self._redessiner()
        self._zoom_affiche()
        return float(vue.zoom)

    def _demander_zoom(self, demande: str) -> None:
        self.zoomer(demande)

    def suivre_engin(self, oui: bool) -> None:
        vue = self._vue_active()
        if vue is None or vue.suivre == bool(oui):
            self._zoom_affiche()
            return
        vue.suivre_engin(bool(oui))
        self._redessiner()
        self._zoom_affiche()

    def _redessiner(self) -> None:
        if self.vue is not None and self.canevas is not None and self._vue_active() is self.vue:
            self.canevas.draw_idle()

    def _zoom_affiche(self) -> None:
        vue = self._vue_active()
        if vue is None:
            return
        self.affichage.afficher_zoom(float(vue.zoom), bool(vue.suivre))
        bloqueur = QSignalBlocker(self.action_suivre)
        self.action_suivre.setChecked(bool(vue.suivre))
        del bloqueur

    def _molette(self, event: Any) -> None:
        """Molette : zoom vers le point du vol sous la souris s'il y en a un, sinon vers le centre."""
        if self.vue is None or not event.step:
            return
        vers = self.vue.point_proche(event.x, event.y)
        self.vue.zoomer(PAS_ZOOM ** float(event.step), vers=vers)
        self._redessiner()
        self._zoom_affiche()

    def _aller_pause(self, t: float) -> None:
        self.navigation.pause()
        self.navigation.aller(t)

    def _memoriser_selection(self, cles: list[str]) -> None:
        if self.etat is not None:
            self.reglages.setValue(f"telemetrie/{self._cle}", cles)

    def _appuyer(self, event: Any) -> None:
        self._appui = (event.x, event.y) if event.button == 1 else None

    def _relacher(self, event: Any) -> None:
        if self._appui is None or self.vue is None or event.button != 1:
            return
        dx, dy = event.x - self._appui[0], event.y - self._appui[1]
        self._appui = None
        if dx * dx + dy * dy > TOLERANCE_CLIC_PX**2:
            return  # c'était une rotation de la vue
        t = self.vue.instant_proche(event.x, event.y)
        if t is not None:
            self._aller_pause(t)

    def _quitter(self) -> None:
        self.close()

    # -- exports -------------------------------------------------------------------------------
    def _dossier(self) -> Path:
        cfg = self.configuration
        return cfg.chemin.parent if cfg is not None and cfg.chemin is not None else Path.cwd()

    def _nom(self, suffixe: str) -> Path:
        cfg = self.configuration
        base = cfg.chemin.stem if cfg is not None and cfg.chemin is not None else "vol"
        return self._dossier() / f"{base}_{suffixe}_t{self.navigation.t:.2f}".replace(".", "_")

    def _signaler(self, chemin: Path) -> None:
        self.statusBar().showMessage(f"Écrit : {chemin}", 8000)

    def exporter_vue(self) -> Path | None:
        from cfd_trajcast.gui.exports import demander_fichier

        vtk = self.moteur == "vtk" and self.vue_vtk is not None
        filtres = "Image PNG (*.png)" if vtk else "PDF (*.pdf);;SVG (*.svg);;PNG 300 dpi (*.png)"
        chemin = demander_fichier(self, "Exporter la vue", self._nom("vue").with_suffix(".png" if vtk else ".pdf"),
                                  filtres)
        if chemin is None or self.vue is None:
            return None
        ecrit = self.vue_vtk.exporter(chemin) if vtk else self.vue.exporter(chemin)
        self._signaler(ecrit)
        return Path(ecrit)

    def exporter_courbes(self) -> Path | None:
        from cfd_trajcast.engine.courbes import exporter_figure
        from cfd_trajcast.gui.exports import demander_fichier

        chemin = demander_fichier(self, "Exporter les courbes", self._nom("courbes").with_suffix(".pdf"),
                                  "PDF (*.pdf);;SVG (*.svg);;PNG 300 dpi (*.png)")
        if chemin is None:
            return None
        ecrit = exporter_figure(self.telemetrie.canevas.figure, chemin)
        self._signaler(ecrit)
        return ecrit

    def exporter_vent(self) -> Path | None:
        from cfd_trajcast.engine.courbes import exporter_figure
        from cfd_trajcast.gui.exports import demander_fichier

        if self.vent.panneau is None:
            QMessageBox.information(self, "Vent", "Pas de vent déclaré dans ce fichier.")
            return None
        chemin = demander_fichier(self, "Exporter le panneau vent", self._nom("vent").with_suffix(".pdf"),
                                  "PDF (*.pdf);;SVG (*.svg);;PNG 300 dpi (*.png)")
        if chemin is None:
            return None
        ecrit = exporter_figure(self.vent.canevas.figure, chemin)
        self._signaler(ecrit)
        return ecrit

    def exporter_figure(self) -> list[Path]:
        from cfd_trajcast.engine.ensemble import VueEnsemble
        from cfd_trajcast.gui.exports import demander_fichier

        if self.configuration is None or self.vue is None:
            return []
        chemin = demander_fichier(self, "Figure paper du vol (base des fichiers)",
                                  self._dossier() / f"{self._nom('figure').name.split('_t')[0]}.pdf",
                                  "PDF + SVG + PNG (*.pdf)")
        if chemin is None:
            return []
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            vue = VueEnsemble.depuis_configuration(self.configuration)
            vue.parametres = self.vue.parametres
            figure = vue.figure(chemin.with_suffix(""))
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Figure paper", str(exc))
            return []
        QApplication.restoreOverrideCursor()
        QMessageBox.information(self, "Figure paper", "\n".join(str(p) for p in figure.fichiers)
                                + f"\n\nLégende proposée :\n{figure.legende}")
        return list(figure.fichiers)

    def exporter_video(self) -> Any:
        from cfd_trajcast.gui.exports import DialogueVideo, ExecutionVideo

        cfg = self.configuration
        if cfg is None or cfg.chemin is None or self.etat is None or self.vue is None:
            return None
        dialogue = DialogueVideo(self.etat.debut, self.etat.fin, self._nom("video").with_suffix(".mp4"), self)
        if dialogue.exec_() != dialogue.Accepted:
            return None
        execution = ExecutionVideo(dialogue.tache(cfg.chemin, self.vue.parametres.repere), self)
        execution.processus.finished.connect(lambda *_: self._video_finie(execution))
        execution.demarrer()
        self._execution = execution
        return execution

    def _video_finie(self, execution: Any) -> None:
        if execution.erreur == "annulée":
            self.statusBar().showMessage("Vidéo annulée", 6000)
        elif execution.erreur:
            QMessageBox.critical(self, "Vidéo", execution.erreur)
        elif execution.resultat:
            self._signaler(Path(execution.resultat))

    def _moteur_choisi(self, action: Any) -> None:
        self.choisir_moteur(str(action.data()))

    def _cocher_moteur(self, moteur: str) -> None:
        for action in self.groupe_moteur.actions():
            action.setChecked(action.data() == moteur)

    def choisir_moteur(self, moteur: str) -> bool:
        """Bascule la vue 3D (``mpl`` ou ``vtk``) ; False si ce moteur n'est pas utilisable ici.

        Avant la première vue VTK, la sonde tourne dans un sous-processus : un OpenGL cassé
        ferait planter l'interface au lieu de lever une exception.
        """
        if self.etat is None or self.vue is None or self.canevas is None:
            self._cocher_moteur(self.moteur)
            return False
        if moteur == "mpl":
            self.moteur = "mpl"
            self.centre.setCurrentWidget(self.canevas)
            self._poser(self.navigation.t)
            self._cocher_moteur("mpl")
            self._zoom_affiche()
            return True
        if self.vue_vtk is None:
            if self._sonde is None:
                from cfd_trajcast.gui.sonde_vtk import sonde_vtk

                QApplication.setOverrideCursor(Qt.WaitCursor)
                try:
                    self._sonde = sonde_vtk()
                finally:
                    QApplication.restoreOverrideCursor()
            ok, detail = self._sonde
            if not ok:
                QMessageBox.warning(self, "Vue VTK indisponible",
                                    f"L'OpenGL ne fonctionne pas ici ({detail}).\n\n"
                                    "La vue Matplotlib, qui n'en a pas besoin, reste active.")
                self._cocher_moteur(self.moteur)
                return False
            from cfd_trajcast.engine.rendu.pyvista_interactif import VueVtk

            assert self.configuration is not None
            self.vue_vtk = VueVtk(self.centre, self.etat, self.vue.parametres,
                                  sol_altitude=self.configuration.style.sol_altitude, options=self.vue.options)
            self.vue_vtk.sur_double_clic(self._aller_pause)
            # La molette VTK est native : on relit le zoom après son passage.
            for evenement in ("MouseWheelForwardEvent", "MouseWheelBackwardEvent"):
                self.vue_vtk.plotter.iren.add_observer(evenement, lambda *_: QTimer.singleShot(0, self._zoom_affiche))
            self.centre.addWidget(self.vue_vtk.widget)
        self.moteur = "vtk"
        self.centre.setCurrentWidget(self.vue_vtk.widget)
        self._poser(self.navigation.t)
        self._cocher_moteur("vtk")
        self._zoom_affiche()
        self.statusBar().showMessage("Vue VTK : double-clic sur le vol pour s'y placer", 6000)
        return True

    def closeEvent(self, event: Any) -> None:
        self.navigation.pause()
        if self.vue_vtk is not None:
            self.vue_vtk.fermer()
            self.vue_vtk = None
        self.reglages.setValue("fenetre/etat", self.saveState())
        super().closeEvent(event)
