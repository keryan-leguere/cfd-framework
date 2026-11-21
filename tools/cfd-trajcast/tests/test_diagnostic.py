"""Diagnostic : versions, étape de l'échec, erreur complète, cause probable.

Rien ici n'exige de GPU : les sorties de sonde sont fabriquées, sauf un essai
réel dont l'import de pyvista est volontairement cassé.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from rich.console import Console

from cfd_trajcast.engine import diagnostic as diag
from cfd_trajcast.engine.diagnostic import Sonde, cause_probable, lire_sonde, sonder_versions
from cfd_trajcast.engine.rendu.pyvista_ import PREFIXE_SONDE, fenetre_choisie
from cfd_trajcast.report.rendu import rapport_diagnostic

RACINE = Path(__file__).resolve().parents[1]

_TRACE_IMPORT = """Traceback (most recent call last):
  File "pyvista/__init__.py", line 12, in <module>
AttributeError: `np.bool8` was removed in the NumPy 2.0 release. Use `np.bool` instead."""


def _sortie(*etapes: str) -> str:
    return "\n".join(f"{PREFIXE_SONDE} etape {e}" for e in etapes)


def _versions_ok() -> dict[str, str | None]:
    return dict(diag.VERSIONS_MINIMALES)


def test_minimums_identiques_a_pyproject() -> None:
    texte = (RACINE / "pyproject.toml").read_text(encoding="utf-8")
    bloc = texte.split("dependencies = [", 1)[1].split("]", 1)[0]
    declares = dict(re.findall(r'"([A-Za-z0-9_-]+)>=([0-9.]+)"', bloc))
    for dist, minimum in diag.VERSIONS_MINIMALES.items():
        assert declares.get(dist) == minimum, dist


def test_pyvista_trop_ancien_refuse_et_numpy2_nomme() -> None:
    versions = {**_versions_ok(), "pyvista": "0.43.10", "numpy": "2.1.0"}
    sonde = next(s for s in sonder_versions(versions) if s.nom == "pyvista")
    assert not sonde.ok
    assert "0.43.10" in sonde.detail and "≥ 0.44" in sonde.detail and "NumPy 2" in sonde.detail


def test_version_absente_et_conforme() -> None:
    versions = {**_versions_ok(), "trimesh": None, "vtk": "9.6.2"}
    sondes = {s.nom: s for s in sonder_versions(versions)}
    assert not sondes["trimesh"].ok and "absent" in sondes["trimesh"].detail
    assert sondes["vtk"].ok and sondes["vtk"].detail == "9.6.2"


def test_versions_lues_sur_cette_machine() -> None:
    assert all(s.ok for s in sonder_versions()), "la pile de test est au minimum déclaré"


def test_echec_a_l_import_garde_la_trace_complete() -> None:
    s = lire_sonde("EGL (GPU par défaut)", 1, _sortie("import"), _TRACE_IMPORT)
    assert not s.ok and s.etape == "import"
    assert "« import »" in s.detail and "np.bool8" in s.detail
    assert s.trace == _TRACE_IMPORT


def test_plantage_au_rendu_nomme_le_signal() -> None:
    s = lire_sonde("X11 (si DISPLAY)", -11, _sortie("import", "fenetre", "rendu"), "")
    assert not s.ok and s.etape == "rendu" and "SIGSEGV" in s.detail


def test_image_vide() -> None:
    sortie = _sortie("import", "fenetre", "rendu") + f"\n{PREFIXE_SONDE} image vide"
    assert lire_sonde("EGL", 1, sortie, "").detail.startswith("image vide")


def _fenetres(etape: str) -> list[Sonde]:
    return [Sonde(n, False, "échec", "fenetre", etape, "trace") for n in diag.FENETRES]


def test_cause_pile_python_avant_le_gpu() -> None:
    sondes = sonder_versions({**_versions_ok(), "pyvista": "0.43.10"}) + _fenetres("import")
    cause = cause_probable(sondes)
    assert cause is not None and cause.startswith("pile Python") and "pyvista" in cause


def test_cause_import_sans_version_fautive() -> None:
    cause = cause_probable(sonder_versions(_versions_ok()) + _fenetres("import"))
    assert cause is not None and "pas le GPU" in cause


def test_cause_systeme_apres_la_pile() -> None:
    systeme = [Sonde("bibliothèques GL", True, "", "systeme"),
               Sonde("fournisseurs EGL", False, "aucun", "systeme"),
               Sonde("périphériques GPU", True, "", "systeme")]
    cause = cause_probable(sonder_versions(_versions_ok()) + systeme + _fenetres("rendu"))
    assert cause is not None and "fournisseur EGL" in cause


def test_pas_de_cause_si_une_fenetre_marche() -> None:
    fenetres = _fenetres("rendu")
    fenetres[0] = Sonde(fenetres[0].nom, True, "GPU", "fenetre", "rendu")
    assert cause_probable(fenetres) is None


def test_fenetre_du_rendu_x11_ratee_conseille_egl(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DISPLAY", ":8")
    monkeypatch.delenv("VTK_DEFAULT_OPENGL_WINDOW", raising=False)
    monkeypatch.delenv("VTK_DEFAULT_EGL_DEVICE_INDEX", raising=False)
    assert fenetre_choisie() == (None, "DISPLAY=:8 défini")
    fenetres = _fenetres("rendu")
    fenetres[0] = Sonde("EGL (GPU par défaut)", True, "GPU", "fenetre", "rendu")
    s = diag.sonder_rendu(fenetres)
    assert not s.ok and "export VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow" in s.detail


def test_fenetre_imposee_par_l_utilisateur(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VTK_DEFAULT_OPENGL_WINDOW", "vtkEGLRenderWindow")
    monkeypatch.delenv("VTK_DEFAULT_EGL_DEVICE_INDEX", raising=False)
    fenetres = _fenetres("rendu")
    fenetres[0] = Sonde("EGL (GPU par défaut)", True, "GPU", "fenetre", "rendu")
    assert diag.sonder_rendu(fenetres).ok


def test_rapport_affiche_cause_et_traces() -> None:
    sondes = (sonder_versions({**_versions_ok(), "pyvista": "0.43.10"})
              + [Sonde("cascadio", True, "extra [step] — lecture des STEP", "extra")]
              + [lire_sonde(n, 1, _sortie("import"), _TRACE_IMPORT) for n in diag.FENETRES])
    console = Console(record=True, width=200, color_system=None)
    console.print(rapport_diagnostic(sondes))
    texte = console.export_text()
    assert "cause probable : pile Python" in texte
    assert "erreurs complètes" in texte and "np.bool8" in texte
    assert "extra [step]" in texte, "un crochet ne doit pas être lu comme une balise Rich"


def test_sonde_reelle_import_casse(tmp_path: Path) -> None:
    """Un vrai sous-processus dont ``import pyvista`` échoue : étape et trace remontent."""
    (tmp_path / "pyvista.py").write_text('raise ImportError("pyvista volontairement cassé")\n',
                                         encoding="utf-8")
    s = diag.sonder_fenetre("EGL (GPU par défaut)", {"PYTHONPATH": str(tmp_path)})
    assert not s.ok and s.etape == "import"
    assert "volontairement cassé" in s.detail and "Traceback" in s.trace


def test_interface_absente_dit_quoi_installer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diag, "_version_installee", lambda dist: None)
    sondes = diag.sonder_interface()
    assert [s.nom for s in sondes] == ["PyQt5", "pyvistaqt"]
    assert not any(s.ok for s in sondes) and "[gui]" in sondes[0].detail
    # Facultative : l'interface ne change pas le verdict du rendu.
    assert all(s.categorie == "interface" for s in sondes)


def test_sonde_qt_hors_ecran(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("PyQt5")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    ok, detail = diag._sous_processus("cfd_trajcast.gui.sonde_qt", "SONDE_QT:")
    assert ok and "offscreen" in detail and "Qt 5." in detail
