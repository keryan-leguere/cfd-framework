"""The shipped example must run, because it is the first thing a user runs.

Package data is easy to break: it is not imported, so nothing else notices
when a file stops working. These tests execute the example scripts in a
subprocess, the way ``RUN_EXEMPLE.sh`` does.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from cfd_aq.paths import EXEMPLE_DIR


def test_le_repertoire_exemple_est_bien_livre() -> None:
    fichiers = {p.name for p in EXEMPLE_DIR.iterdir()}
    assert fichiers == {
        "01_budget_trainee.py",
        "02_arete_contre_deux_marches.py",
        "CAS_VOILURE.yaml",
        "README.md",
        "RUN_EXEMPLE.sh",
    }


@pytest.mark.parametrize("script", ["01_budget_trainee.py", "02_arete_contre_deux_marches.py"])
def test_les_scripts_s_executent(script: str, tmp_path: Path) -> None:
    resultat = subprocess.run(
        [sys.executable, str(EXEMPLE_DIR / script)],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert resultat.returncode == 0, resultat.stderr
    assert resultat.stdout.strip()


def test_le_budget_donne_des_counts_plausibles(tmp_path: Path) -> None:
    """Six 1 mm joints across an 11 m span should cost a fraction of a count."""
    resultat = subprocess.run(
        [sys.executable, str(EXEMPLE_DIR / "01_budget_trainee.py")],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    lignes = [
        ligne.split() for ligne in resultat.stdout.splitlines() if ligne.strip().startswith("1.0")
    ]
    assert lignes, resultat.stdout
    counts = float(lignes[0][-1])
    assert 0.05 < counts < 1.0, counts


def test_le_script_d_interference_reproduit_la_phrase_du_rapport(tmp_path: Path) -> None:
    """Its last column must go from about 0.54 at M = 0.2 to about 1 at M = 2.8."""
    resultat = subprocess.run(
        [sys.executable, str(EXEMPLE_DIR / "02_arete_contre_deux_marches.py")],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    lignes = {
        ligne.split()[0]: float(ligne.split()[-1])
        for ligne in resultat.stdout.splitlines()
        if ligne.strip() and ligne.split()[0].replace(".", "", 1).isdigit()
    }
    assert lignes["0.2"] == pytest.approx(0.54, abs=0.05)
    assert lignes["2.8"] == pytest.approx(1.0, abs=0.08)


def test_run_exemple_est_executable() -> None:
    chemin = EXEMPLE_DIR / "RUN_EXEMPLE.sh"
    texte = chemin.read_text(encoding="utf-8")
    # Jamais le script de console : voir l'en-tête du fichier.
    assert "-m cfd_aq" in texte
    assert "\ncfd-aq " not in texte
