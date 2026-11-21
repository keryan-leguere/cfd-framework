"""Interface Qt, hors écran (``QT_QPA_PLATFORM=offscreen``) ; sautée sans PyQt5 ou cfd-plot.

La logique est testée ailleurs (``test_etat_vol``, ``test_vent_cdg``) : ici, le câblage
— le temps circule, les coches font des courbes, un clic place le temps, les réglages
sont retenus.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PyQt5")
pytest.importorskip("cfd_plot")

from cfd_trajcast import gui
from cfd_trajcast.cli.main import EXIT_ERREUR_ENTREE, main
from cfd_trajcast.paths import EXEMPLE_DIR

CONFIG = Path(EXEMPLE_DIR) / "CONFIG_GUI.yaml"


@pytest.fixture(scope="module")
def app() -> Any:
    return gui.application()


@pytest.fixture
def reglages(tmp_path: Path, app: Any) -> Iterator[None]:
    """Réglages Qt isolés dans tmp_path (jamais ceux de l'utilisateur)."""
    from PyQt5.QtCore import QSettings

    # QSettings(organisation, application) prend le format natif (un .conf sous Linux) :
    # c'est ce chemin-là qu'il faut détourner, sinon les tests écrivent chez l'utilisateur.
    utilisateur = Path.home() / ".config" / "cfd-framework" / "cfd-trajcast.conf"
    avant = utilisateur.read_bytes() if utilisateur.exists() else None
    for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
        QSettings.setPath(fmt, QSettings.UserScope, str(tmp_path))
    yield
    apres = utilisateur.read_bytes() if utilisateur.exists() else None
    assert apres == avant, "les tests ont modifié les réglages de l'utilisateur"


@pytest.fixture
def fenetre(app: Any, reglages: None) -> Iterator[Any]:
    from cfd_trajcast.gui.fenetre import FenetrePrincipale

    f = FenetrePrincipale()
    f.resize(1400, 900)
    f.show()
    assert f.ouvrir(CONFIG)
    yield f
    f.close()
    f.deleteLater()


def _attendre(app: Any, secondes: float) -> None:
    fin = time.monotonic() + secondes
    while time.monotonic() < fin:
        app.processEvents()
        time.sleep(0.01)


def test_qt_prepare_sans_conflit(app: Any) -> None:
    from cfd_trajcast.gui._qt import preparer_qt

    assert "Core" in preparer_qt() and preparer_qt() == preparer_qt()  # idempotent
    assert app.platformName() == "offscreen"


def test_navigation_bornee_et_lecture(app: Any) -> None:
    from cfd_trajcast.gui.navigation import Navigation

    nav = Navigation(0.0, 10.0)
    vus: list[float] = []
    nav.temps_change.connect(vus.append)
    nav.aller(-3.0)
    assert vus == []  # déjà au début : pas d'émission
    nav.aller(20.0)
    assert nav.t == 10.0 and vus == [10.0]
    nav.aller(0.0)
    nav.vitesse = 5.0
    nav.lire()
    _attendre(app, 0.4)
    nav.pause()
    # Temps réel × vitesse : environ 2 s de vol en 0,4 s, quelle que soit la cadence d'affichage.
    assert 1.0 < nav.t < 3.0 and not nav.en_lecture


def test_le_temps_circule(fenetre: Any, app: Any) -> None:
    fenetre.navigation.aller(12.0)
    app.processEvents()
    assert fenetre.vue.t == 12.0
    assert fenetre.frise.instant.value() == pytest.approx(12.0)
    assert fenetre.frise.curseur.value() == 1200
    alt = fenetre.etat.valeur("altitude", 12.0)
    textes = {it.data(0, 0x0100): it.text(1) for it in fenetre.telemetrie._items()}
    assert textes["altitude"].replace("\u202f", "").startswith(f"{alt:.0f}")
    # La frise pilote aussi : déplacer le curseur déplace le temps.
    fenetre.frise.curseur.setValue(3000)
    assert fenetre.navigation.t == pytest.approx(30.0)


def test_cocher_fait_des_courbes_et_le_clic_place_le_temps(fenetre: Any) -> None:
    fenetre.telemetrie.cocher(["altitude", "masse", "VZ"])
    courbes = fenetre.telemetrie.courbes
    # Dans l'ordre de la liste (calculées, puis colonnes du fichier), quel que soit l'ordre des coches.
    assert courbes.cles == ["altitude", "VZ", "masse"] and len(courbes.axes) == 3
    t = courbes.instant(courbes.axes[1], 21.5)
    assert t == 21.5
    assert courbes.instant(object(), 21.5) is None


def test_selection_retenue_par_fichier(fenetre: Any, app: Any) -> None:
    from cfd_trajcast.gui.fenetre import FenetrePrincipale

    fenetre.telemetrie.cocher(["mach", "poussee"])
    autre = FenetrePrincipale()
    assert autre.ouvrir(CONFIG)
    assert autre.telemetrie.cochees() == ["mach", "poussee"]
    autre.close()


def test_couches_et_reperes(fenetre: Any) -> None:
    vue = fenetre.vue
    fenetre.affichage.reperes["aero"].setChecked(True)
    fenetre.affichage.reperes["corps"].setChecked(False)
    fenetre.navigation.aller(20.0)
    assert vue.options.reperes == frozenset({"aero"})
    assert all(ligne.get_visible() for ligne, _ in vue.reperes["aero"])
    assert not any(ligne.get_visible() for ligne, _ in vue.reperes["corps"])
    fenetre.affichage.vent.setChecked(False)
    assert not vue.vent.get_visible()
    fenetre.affichage.auto.setChecked(False)
    fenetre.affichage.agrandissement.setValue(50)
    assert vue.echelle == 50.0


def test_zoom_boutons_menu_et_molette(fenetre: Any) -> None:
    from types import SimpleNamespace

    vue, dock = fenetre.vue, fenetre.affichage
    assert dock.niveau_zoom.text() == "vol entier"
    dock.boutons_zoom["plus"].click()
    assert vue.zoom > 1 and "zoom" in dock.niveau_zoom.text()
    dock.boutons_zoom["engin"].click()
    assert vue.suivre and dock.suivre.isChecked() and fenetre.action_suivre.isChecked()
    fenetre.navigation.aller(30.0)
    np.testing.assert_allclose(vue.centre(), vue.cdg(), atol=1e-6)
    dock.suivre.setChecked(False)
    assert not vue.suivre and not fenetre.action_suivre.isChecked()
    actions = {a.text(): a for a in fenetre.menu_zoom.actions()}
    actions["Vol entier"].trigger()
    assert vue.zoom == pytest.approx(1.0) and dock.niveau_zoom.text() == "vol entier"
    # Molette sur un point du vol : il reste sous la souris.
    fenetre.canevas.draw()
    point = np.asarray(vue.scene.xyz[len(vue.scene.xyz) // 2], dtype=float)
    x, y = vue._ecran(point)
    fenetre._molette(SimpleNamespace(step=2, x=x, y=y))
    assert vue.zoom == pytest.approx(1.25**2)
    np.testing.assert_allclose(vue._ecran(point), (x, y), atol=0.5)
    fenetre._molette(SimpleNamespace(step=-10, x=x, y=y))
    assert vue.zoom == pytest.approx(1.0)


def test_clic_sur_la_trajectoire(fenetre: Any) -> None:
    from mpl_toolkits.mplot3d import proj3d

    vue = fenetre.vue
    fenetre.canevas.draw()
    i = len(vue.scene.t) // 3
    x, y, z = vue.scene.xyz[i]
    xs, ys, _ = proj3d.proj_transform(np.array([x]), np.array([y]), np.array([z]), vue.ax.get_proj())
    px, py = vue.ax.transData.transform([[xs[0], ys[0]]])[0]
    t = vue.instant_proche(px + 2, py - 2)
    assert t is not None and abs(t - vue.scene.t[i]) < 1.0
    assert vue.instant_proche(px + 300, py + 300) is None or abs(vue.instant_proche(px + 300, py + 300) - t) > 1


def test_evenements_dans_la_frise(fenetre: Any) -> None:
    combo = fenetre.frise.evenements
    assert combo.count() == 4  # « Événements… » + 3
    combo.activated.emit(3)
    assert fenetre.navigation.t == pytest.approx(40.565)
    assert fenetre.frise.curseur.evenements == [3.744, 4.0, 40.565]


def test_fichier_illisible_sans_exception(app: Any, reglages: None, tmp_path: Path, monkeypatch: Any) -> None:
    from PyQt5.QtWidgets import QMessageBox

    from cfd_trajcast.gui.fenetre import FenetrePrincipale

    messages: list[str] = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a: messages.append(a[2]))
    f = FenetrePrincipale()
    (tmp_path / "x.yaml").write_text("trajectoire: {}\n", encoding="utf-8")
    assert not f.ouvrir(tmp_path / "x.yaml")
    assert messages and "x.yaml" in messages[0]
    f.close()


def test_cli_sans_pyqt(monkeypatch: Any, capsys: Any) -> None:
    monkeypatch.setattr(gui, "disponible", lambda: "il manque PyQt5")
    assert main(["gui", str(CONFIG)]) == EXIT_ERREUR_ENTREE
    assert "PyQt5" in capsys.readouterr().err


# -- G5 : moteur VTK ------------------------------------------------------------------------
def test_vtk_refuse_proprement_sans_opengl(fenetre: Any, monkeypatch: Any) -> None:
    from PyQt5.QtWidgets import QMessageBox

    import cfd_trajcast.gui.sonde_vtk as sonde

    messages: list[str] = []
    monkeypatch.setattr(sonde, "sonde_vtk", lambda: (False, "offscreen | vide"))
    monkeypatch.setattr(QMessageBox, "warning", lambda *a: messages.append(a[2]))
    assert not fenetre.choisir_moteur("vtk")
    assert fenetre.moteur == "mpl" and "offscreen" in messages[0]
    assert [a.isChecked() for a in fenetre.groupe_moteur.actions()] == [True, False]


def test_sonde_vtk_echoue_hors_ecran() -> None:
    from cfd_trajcast.gui.sonde_vtk import sonde_vtk

    ok, detail = sonde_vtk()
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        assert not ok and "vide" in detail  # pas d'OpenGL sans écran : la bonne réponse


# -- G6 : exports et assistant -------------------------------------------------------------
def test_exporter_la_vue_et_les_courbes(fenetre: Any, tmp_path: Path, monkeypatch: Any) -> None:
    import cfd_trajcast.gui.exports as ex

    fenetre.navigation.aller(15.0)
    cibles = iter([tmp_path / "vue.pdf", tmp_path / "courbes.svg", tmp_path / "vent.png"])
    monkeypatch.setattr(ex, "demander_fichier", lambda *a: next(cibles))
    assert fenetre.exporter_vue().read_bytes()[:5] == b"%PDF-"
    assert b"<svg" in fenetre.exporter_courbes().read_bytes()[:500]
    assert fenetre.exporter_vent().stat().st_size > 10_000


def test_video_en_sous_processus(fenetre: Any, tmp_path: Path) -> None:
    from cfd_trajcast.gui.exports import ExecutionVideo
    from cfd_trajcast.gui.tache_video import TacheVideo

    tache = TacheVideo(config=str(CONFIG), sortie=str(tmp_path / "v.mp4"), de=0.0, a=10.0,
                       resolution=(320, 180), duree=1.0)
    assert TacheVideo.depuis_json(tache.vers_json()) == tache
    execution = ExecutionVideo(tache, fenetre)
    execution.demarrer()
    assert execution.attendre(180_000)
    execution._fini(execution.processus.exitCode())
    assert execution.erreur is None, execution.erreur
    assert Path(execution.resultat or "").stat().st_size > 1000
    assert execution.progres.maximum() > 0


def test_video_annulee_sans_fichier(fenetre: Any, tmp_path: Path, app: Any) -> None:
    from cfd_trajcast.gui.exports import ExecutionVideo
    from cfd_trajcast.gui.tache_video import TacheVideo

    tache = TacheVideo(config=str(CONFIG), sortie=str(tmp_path / "a.mp4"), resolution=(320, 180), duree=30.0)
    execution = ExecutionVideo(tache, fenetre)
    execution.demarrer()
    _attendre(app, 2.0)
    execution.annuler()
    assert execution.erreur == "annulée" and not (tmp_path / "a.mp4").exists()


def test_tache_video_erreur_en_clair(capsys: Any, tmp_path: Path) -> None:
    from cfd_trajcast.gui.tache_video import TacheVideo
    from cfd_trajcast.gui.tache_video import main as tache

    assert tache([TacheVideo(config=str(tmp_path / "absent.yaml"), sortie=str(tmp_path / "x.mp4")).vers_json()]) == 1
    assert capsys.readouterr().out.startswith("ERREUR ")


def _reponses_exemple() -> dict[str, Any]:
    return {
        "csv": "vol_vent_cdg.csv", "repere": "ENU", "unite_temps": "s", "unite_longueur": "m", "unite_angle": "deg",
        "colonne_t": "t", "colonne_x": "x", "colonne_y": "y", "colonne_z": "z",
        "attitude": "quaternion", "colonnes_attitude": ["qw", "qx", "qy", "qz"], "ordre": "wxyz",
        "sens": "corps_vers_reference", "sequence": "ZYX", "corps": "FRD",
        "maquette": "MAQUETTE/Aim9.stl", "unite_maquette": "mm", "axe_nez": "-X", "axe_haut": "+Z",
        "origine": "base", "longueur_imposee": 2.87,
        "vent": True, "colonnes_vent": ["VN", "VE", "VZ"], "vz": "haut", "sens_vent": "vers", "unite_vent": "m/s",
        "cdg": True, "colonnes_cdg": ["Xcg"], "unite_cdg": "m", "reference_cdg": "nez", "axe_cdg": "vers_culot",
    }


def test_reponses_vers_yaml_valide() -> None:
    from cfd_trajcast.gui.assistant import configuration_depuis_reponses, valider

    d = configuration_depuis_reponses(_reponses_exemple())
    assert valider(d, Path(EXEMPLE_DIR)) is None
    assert d["cdg"]["axe"] == "vers_culot" and d["vent"]["vz"] == "haut"
    r = {**_reponses_exemple(), "colonnes_vent": ["VN", "VE", "W"]}
    erreur = valider(configuration_depuis_reponses(r), Path(EXEMPLE_DIR))
    assert erreur is not None and "W" in erreur


def test_assistant_de_bout_en_bout(app: Any, reglages: None, tmp_path: Path) -> None:
    import shutil

    import yaml as yaml_

    from cfd_trajcast.data.configuration import charger_configuration
    from cfd_trajcast.gui.assistant import AssistantCsv

    shutil.copy(Path(EXEMPLE_DIR) / "vol_vent_cdg.csv", tmp_path / "vol.csv")
    shutil.copytree(Path(EXEMPLE_DIR) / "MAQUETTE", tmp_path / "MAQUETTE")
    a = AssistantCsv(csv=tmp_path / "vol.csv")
    a.show()
    assert "qw" in a.colonnes and "Xcg" in a.colonnes
    a.next()
    page = a.p_trajectoire
    assert [w.currentText() for w in page.att] == ["qw", "qx", "qy", "qz"]  # prérempli
    assert page.colonnes["t"].currentText() == "t"
    a.next()
    m = a.p_maquette
    m.fichier.setText(str(tmp_path / "MAQUETTE" / "Aim9.stl"))
    m.unite.setCurrentText("mm")
    m.axe_nez.setCurrentText("-X")
    m.longueur.setValue(2.87)
    a.next()
    o = a.p_options
    assert o.vent.isChecked() and [w.currentText() for w in o.colonnes_vent] == ["VN", "VE", "VZ"]
    assert o.cdg.isChecked() and o.colonnes_cdg[0].currentText() == "Xcg"
    a.next()
    assert a.currentPage() is a.p_enregistrer
    assert a.p_enregistrer.validatePage()
    assert a.ecrit == tmp_path / "CONFIG_vol.yaml"
    d = yaml_.safe_load(a.ecrit.read_text(encoding="utf-8"))
    assert d["trajectoire"]["fichier"] == "vol.csv" and d["maquette"]["fichier"] == "MAQUETTE/Aim9.stl"
    cfg = charger_configuration(a.ecrit)
    assert cfg.vent is not None and cfg.cdg is not None
    # Une convention fausse est refusée avec le message de l'ouverture, et rien n'est écrit.
    a.ecrit.unlink()
    o.colonnes_cdg[0].setCurrentText("masse")
    o.unite_cdg.setCurrentText("km")
    a.p_options.colonnes_vent[2].setCurrentText("q0")
    a.p_trajectoire.repere.setCurrentText("ENU")
    a.p_trajectoire.att[0].setCurrentText("x")
    assert not a.p_enregistrer.validatePage()
    assert "Refusé" in a.p_enregistrer.message.text() and not (tmp_path / "CONFIG_vol.yaml").exists()
    a.close()
