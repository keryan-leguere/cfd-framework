"""Assistant « Nouveau vol depuis un CSV » : déclarer les conventions, enregistrer le YAML, l'ouvrir.

Rien n'est deviné en silence. Les listes sont **préremplies** par les mêmes noms de
colonnes que la lecture reconnaît (``q0..q3``, ``qw..qz``, ``lacet/tangage/roulis``…),
mais chaque convention reste à confirmer. La dernière page valide le tout avec le
parseur de configuration et l'état du vol : ce qui serait refusé à l'ouverture est
refusé ici, avec le même message, avant que rien ne soit écrit.

:func:`configuration_depuis_reponses` (sans Qt) fabrique le dictionnaire YAML depuis
les réponses ; c'est lui que les tests vérifient.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from cfd_trajcast.data.cdg import AXES_CDG, REFERENCES_CDG
from cfd_trajcast.data.configuration import configuration_depuis_dict
from cfd_trajcast.data.maquette import UNITES_CAO
from cfd_trajcast.data.trajectoire import (
    COLONNES_EULER_CONNUES,
    COLONNES_QUATERNION_CONNUES,
    ORDRES,
    SENS,
    UNITES_ANGLE,
    UNITES_LONGUEUR,
    UNITES_TEMPS,
)
from cfd_trajcast.data.vent import SENS_VENT, UNITES_VENT, VZ_VENT
from cfd_trajcast.engine.etat_vol import EtatVol

__all__ = ["AssistantCsv", "colonnes_csv", "configuration_depuis_reponses", "valider"]

AXES_CAO = ("+X", "-X", "+Y", "-Y", "+Z", "-Z")
_AUCUNE = "—"


def colonnes_csv(chemin: Path, lignes: int = 30) -> pd.DataFrame:
    """Les premières lignes du CSV, lues comme le fera la trajectoire (séparateur deviné, # ignorés)."""
    return pd.read_csv(chemin, sep=None, engine="python", comment="#", nrows=lignes)


def _deviner(colonnes: Sequence[str], candidats: Sequence[str]) -> str:
    bas = {c.lower(): c for c in colonnes}
    return next((bas[c] for c in candidats if c in bas), _AUCUNE)


def configuration_depuis_reponses(r: Mapping[str, Any]) -> dict[str, Any]:
    """Le dictionnaire YAML depuis les réponses de l'assistant (chemins relatifs au YAML)."""
    d: dict[str, Any] = {
        "etude": {"titre": r.get("titre") or Path(r["csv"]).stem},
        "trajectoire": {
            "source": "csv", "fichier": r["csv"], "repere": r["repere"],
            "unites": {"temps": r["unite_temps"], "longueur": r["unite_longueur"], "angle": r["unite_angle"]},
            "colonnes": {k: r[f"colonne_{k}"] for k in ("t", "x", "y", "z")},
            "attitude": {"type": r["attitude"], "colonnes": list(r["colonnes_attitude"])},
        },
        "maquette": {"fichier": r["maquette"], "axe_nez": r["axe_nez"], "axe_haut": r["axe_haut"],
                     "origine": r.get("origine", "base")},
        "vues": {"ensemble": {"mode": "ensemble", "repere": r.get("repere_vue", "ned")}},
    }
    att = d["trajectoire"]["attitude"]
    if r["attitude"] == "quaternion":
        att.update(ordre=r["ordre"], sens=r["sens"], corps=r["corps"])
    else:
        att.update(sequence=r["sequence"], corps=r["corps"])
    if r.get("unite_maquette"):
        d["maquette"]["unite"] = r["unite_maquette"]
    if r.get("longueur_imposee"):
        d["maquette"]["longueur_imposee"] = float(r["longueur_imposee"])
    if r.get("vent"):
        d["vent"] = {"colonnes": list(r["colonnes_vent"]), "vz": r["vz"], "sens": r["sens_vent"],
                     "unite": r["unite_vent"]}
    if r.get("cdg"):
        d["cdg"] = {"colonnes": list(r["colonnes_cdg"]), "unite": r["unite_cdg"], "reference": r["reference_cdg"]}
        if len(r["colonnes_cdg"]) == 1:
            d["cdg"]["axe"] = r["axe_cdg"]
    return d


def valider(d: Mapping[str, Any], base: Path) -> str | None:
    """None si le fichier s'ouvrira, sinon le message qu'on aurait à l'ouverture."""
    try:
        cfg = configuration_depuis_dict(d, base)
        EtatVol.depuis_configuration(cfg, utiliser_cache=False)
    except Exception as exc:
        return str(exc)
    return None


def _combo(valeurs: Sequence[str], choisie: str | None = None) -> QComboBox:
    c = QComboBox()
    c.addItems(list(valeurs))
    if choisie is not None and choisie in valeurs:
        c.setCurrentText(choisie)
    return c


class _PageFichier(QWizardPage):
    def __init__(self, assistant: AssistantCsv) -> None:
        super().__init__()
        self.assistant = assistant
        self.setTitle("Fichier de trajectoire")
        self.setSubTitle("Le CSV : une ligne par instant, positions, attitude et toute autre colonne.")
        self.chemin = QLineEdit()
        self.chemin.setReadOnly(True)
        parcourir = QPushButton("Choisir…")
        parcourir.clicked.connect(self._choisir)
        ligne = QHBoxLayout()
        ligne.addWidget(self.chemin)
        ligne.addWidget(parcourir)
        self.apercu = QTableWidget()
        lay = QVBoxLayout(self)
        lay.addLayout(ligne)
        lay.addWidget(self.apercu)
        self.registerField("csv*", self.chemin)

    def _choisir(self) -> None:
        chemin, _ = QFileDialog.getOpenFileName(self, "Trajectoire", "", "CSV (*.csv *.txt *.dat);;Tous (*)")
        if chemin:
            self.charger(Path(chemin))

    def charger(self, chemin: Path) -> None:
        try:
            df = colonnes_csv(chemin)
        except Exception as exc:
            self.setSubTitle(f"Illisible : {exc}")
            return
        self.assistant.colonnes = [str(c) for c in df.columns]
        self.chemin.setText(str(chemin))
        self.apercu.setColumnCount(len(df.columns))
        self.apercu.setRowCount(len(df))
        self.apercu.setHorizontalHeaderLabels(self.assistant.colonnes)
        for i, rang in enumerate(df.itertuples(index=False)):
            for j, v in enumerate(rang):
                self.apercu.setItem(i, j, QTableWidgetItem(str(v)))
        self.completeChanged.emit()


class _PageTrajectoire(QWizardPage):
    def __init__(self, assistant: AssistantCsv) -> None:
        super().__init__()
        self.assistant = assistant
        self.setTitle("Positions et attitude")
        self.setSubTitle("Déclarez les conventions du fichier : rien n'est supposé.")
        self.f = QFormLayout(self)

    def initializePage(self) -> None:
        while self.f.rowCount():
            self.f.removeRow(0)
        cols = self.assistant.colonnes
        self.repere = _combo(("ENU", "NED"))
        self.unite_temps = _combo(tuple(UNITES_TEMPS), "s")
        self.unite_longueur = _combo(tuple(UNITES_LONGUEUR), "m")
        self.unite_angle = _combo(tuple(UNITES_ANGLE), "deg")
        self.colonnes = {k: _combo(cols, _deviner(cols, cands)) for k, cands in (
            ("t", ("t", "temps", "time")), ("x", ("x", "n", "north", "nord")),
            ("y", ("y", "e", "east", "est")), ("z", ("z", "d", "down", "bas", "h")))}
        quaternion = next((c for c in COLONNES_QUATERNION_CONNUES if set(c) <= set(cols)), None)
        euler = next((c for c in COLONNES_EULER_CONNUES if set(c) <= set(cols)), None)
        self.attitude = _combo(("quaternion", "euler"), "quaternion" if quaternion or not euler else "euler")
        defaut = quaternion or euler or (cols[:4] if len(cols) >= 4 else cols)
        self.att = [_combo(cols, defaut[i] if i < len(defaut) else None) for i in range(4)]
        self.ordre = _combo(ORDRES)
        self.sens = _combo(SENS)
        self.sequence = QLineEdit("ZYX")
        self.corps = _combo(("FRD", "FLU"))
        for nom, w in (("Repère des positions", self.repere), ("Unité de temps", self.unite_temps),
                       ("Unité de longueur", self.unite_longueur), ("Unité d'angle", self.unite_angle)):
            self.f.addRow(nom, w)
        for k, w in self.colonnes.items():
            self.f.addRow(f"Colonne {k}", w)
        self.f.addRow("Attitude", self.attitude)
        att = QHBoxLayout()
        for w in self.att:
            att.addWidget(w)
        self.f.addRow("Colonnes d'attitude (3 en Euler)", att)
        self.f.addRow("Quaternion : ordre", self.ordre)
        self.f.addRow("Quaternion : sens", self.sens)
        self.f.addRow("Euler : séquence (majuscules = intrinsèque)", self.sequence)
        self.f.addRow("Axes du corps", self.corps)
        self.attitude.currentTextChanged.connect(lambda t: self.att[3].setEnabled(t == "quaternion"))
        self.att[3].setEnabled(self.attitude.currentText() == "quaternion")

    def reponses(self) -> dict[str, Any]:
        n = 4 if self.attitude.currentText() == "quaternion" else 3
        r = {"repere": self.repere.currentText(), "unite_temps": self.unite_temps.currentText(),
             "unite_longueur": self.unite_longueur.currentText(), "unite_angle": self.unite_angle.currentText(),
             "attitude": self.attitude.currentText(), "colonnes_attitude": [w.currentText() for w in self.att[:n]],
             "ordre": self.ordre.currentText(), "sens": self.sens.currentText(),
             "sequence": self.sequence.text().strip(), "corps": self.corps.currentText()}
        r.update({f"colonne_{k}": w.currentText() for k, w in self.colonnes.items()})
        return r


class _PageMaquette(QWizardPage):
    def __init__(self) -> None:
        super().__init__()
        self.setTitle("Maquette (CAO)")
        self.setSubTitle("STEP, STL, OBJ… ; un STL n'a pas d'unité : la déclarer.")
        f = QFormLayout(self)
        self.fichier = QLineEdit()
        parcourir = QPushButton("Choisir…")
        parcourir.clicked.connect(self._choisir)
        ligne = QHBoxLayout()
        ligne.addWidget(self.fichier)
        ligne.addWidget(parcourir)
        f.addRow("Fichier", ligne)
        self.unite = _combo(("", *UNITES_CAO), "")
        self.axe_nez = _combo(AXES_CAO, "+X")
        self.axe_haut = _combo(AXES_CAO, "+Z")
        self.origine = _combo(("base", "centre_volume"))
        self.longueur = QDoubleSpinBox()
        self.longueur.setRange(0.0, 1000.0)
        self.longueur.setDecimals(3)
        self.longueur.setSpecialValueText("telle quelle")
        self.longueur.setSuffix(" m")
        for nom, w in (("Unité (vide : celle du STEP)", self.unite), ("Axe CAO du nez", self.axe_nez),
                       ("Axe CAO du haut", self.axe_haut), ("Origine (point suivi)", self.origine),
                       ("Longueur imposée", self.longueur)):
            f.addRow(nom, w)
        self.registerField("maquette*", self.fichier)

    def _choisir(self) -> None:
        chemin, _ = QFileDialog.getOpenFileName(self, "Maquette", "", "CAO (*.step *.stp *.stl *.obj *.ply *.glb *.gltf)")
        if chemin:
            self.fichier.setText(chemin)

    def reponses(self) -> dict[str, Any]:
        return {"maquette": self.fichier.text(), "unite_maquette": self.unite.currentText() or None,
                "axe_nez": self.axe_nez.currentText(), "axe_haut": self.axe_haut.currentText(),
                "origine": self.origine.currentText(), "longueur_imposee": self.longueur.value() or None}


class _PageVentCdg(QWizardPage):
    def __init__(self, assistant: AssistantCsv) -> None:
        super().__init__()
        self.assistant = assistant
        self.setTitle("Vent et CDG (facultatifs)")
        self.setSubTitle("Les positions du fichier sont celles du CDG : la maquette se place autour de lui.")
        self.f = QFormLayout(self)

    def initializePage(self) -> None:
        while self.f.rowCount():
            self.f.removeRow(0)
        cols = self.assistant.colonnes
        self.vent = QCheckBox("Le fichier contient le vent")
        self.colonnes_vent = [_combo(cols, _deviner(cols, c)) for c in (("vn", "wind_n"), ("ve", "wind_e"),
                                                                         ("vz", "vd", "wind_z"))]
        self.vent.setChecked(all(w.currentText() != _AUCUNE and w.currentText() in cols for w in self.colonnes_vent))
        self.vz = _combo(VZ_VENT)
        self.sens_vent = _combo(SENS_VENT)
        self.unite_vent = _combo(tuple(UNITES_VENT))
        self.cdg = QCheckBox("Le fichier contient le CDG")
        self.colonnes_cdg = [_combo((_AUCUNE, *cols), _deviner(cols, c)) for c in (("xcg",), ("ycg",), ("zcg",))]
        self.cdg.setChecked(self.colonnes_cdg[0].currentText() != _AUCUNE)
        self.unite_cdg = _combo(tuple(UNITES_LONGUEUR), "m")
        self.reference = _combo(REFERENCES_CDG)
        self.axe_cdg = _combo(AXES_CDG)
        self.f.addRow(self.vent)
        ligne = QHBoxLayout()
        for w in self.colonnes_vent:
            ligne.addWidget(w)
        self.f.addRow("Colonnes Nord, Est, vertical", ligne)
        self.f.addRow("Vertical positif vers le", self.vz)
        self.f.addRow("Sens (vers : vitesse de l'air)", self.sens_vent)
        self.f.addRow("Unité", self.unite_vent)
        self.f.addRow(self.cdg)
        ligne = QHBoxLayout()
        for w in self.colonnes_cdg:
            ligne.addWidget(w)
        self.f.addRow("Xcg (et Ycg, Zcg en axes CAO)", ligne)
        self.f.addRow("Unité", self.unite_cdg)
        self.f.addRow("Mesuré depuis", self.reference)
        self.f.addRow("Une colonne : croît", self.axe_cdg)

    def reponses(self) -> dict[str, Any]:
        cdg = [w.currentText() for w in self.colonnes_cdg if w.currentText() != _AUCUNE]
        return {"vent": self.vent.isChecked(), "colonnes_vent": [w.currentText() for w in self.colonnes_vent],
                "vz": self.vz.currentText(), "sens_vent": self.sens_vent.currentText(),
                "unite_vent": self.unite_vent.currentText(),
                "cdg": self.cdg.isChecked() and len(cdg) in (1, 3), "colonnes_cdg": cdg,
                "unite_cdg": self.unite_cdg.currentText(), "reference_cdg": self.reference.currentText(),
                "axe_cdg": self.axe_cdg.currentText()}


class _PageEnregistrer(QWizardPage):
    def __init__(self, assistant: AssistantCsv) -> None:
        super().__init__()
        self.assistant = assistant
        self.setTitle("Enregistrer la configuration")
        f = QFormLayout(self)
        self.yaml = QLineEdit()
        parcourir = QPushButton("…")
        parcourir.clicked.connect(self._choisir)
        ligne = QHBoxLayout()
        ligne.addWidget(self.yaml)
        ligne.addWidget(parcourir)
        f.addRow("Fichier YAML", ligne)
        self.message = QLabel()
        self.message.setWordWrap(True)
        f.addRow(self.message)

    def initializePage(self) -> None:
        csv = Path(self.field("csv"))
        self.yaml.setText(str(csv.with_name(f"CONFIG_{csv.stem}.yaml")))
        self.message.setText("Le fichier est vérifié comme à l'ouverture avant d'être écrit.")

    def _choisir(self) -> None:
        chemin, _ = QFileDialog.getSaveFileName(self, "Configuration", self.yaml.text(), "YAML (*.yaml)")
        if chemin:
            self.yaml.setText(chemin)

    def validatePage(self) -> bool:
        cible = Path(self.yaml.text()).with_suffix(".yaml")
        d = self.assistant.dictionnaire(cible.parent)
        erreur = valider(d, cible.parent)
        if erreur:
            self.message.setText(f"<b>Refusé</b> — {erreur}")
            return False
        cible.write_text(yaml.safe_dump(d, allow_unicode=True, sort_keys=False), encoding="utf-8")
        self.assistant.ecrit = cible
        return True


class AssistantCsv(QWizard):
    """L'assistant ; après ``exec_()`` réussi, :attr:`ecrit` est le YAML enregistré."""

    def __init__(self, parent: QWidget | None = None, csv: Path | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nouveau vol depuis un CSV")
        self.colonnes: list[str] = []
        self.ecrit: Path | None = None
        self.p_fichier = _PageFichier(self)
        self.p_trajectoire = _PageTrajectoire(self)
        self.p_maquette = _PageMaquette()
        self.p_options = _PageVentCdg(self)
        self.p_enregistrer = _PageEnregistrer(self)
        for page in (self.p_fichier, self.p_trajectoire, self.p_maquette, self.p_options, self.p_enregistrer):
            self.addPage(page)
        self.resize(820, 620)
        if csv is not None:
            self.p_fichier.charger(csv)

    def reponses(self) -> dict[str, Any]:
        r: dict[str, Any] = {"csv": self.field("csv")}
        for page in (self.p_trajectoire, self.p_maquette, self.p_options):
            r.update(page.reponses())
        return r

    def dictionnaire(self, dossier_yaml: Path) -> dict[str, Any]:
        """Le YAML à écrire dans ``dossier_yaml`` (chemins relatifs quand c'est possible)."""
        r = self.reponses()
        for cle in ("csv", "maquette"):
            p = Path(r[cle])
            try:
                r[cle] = str(p.resolve().relative_to(dossier_yaml.resolve()))
            except ValueError:
                r[cle] = str(p.resolve())
        return configuration_depuis_reponses(r)
