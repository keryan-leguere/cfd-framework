"""Tests de installer_lanceurs.py : ``pytest tools/installation``.

Aucun paquet du framework n'a besoin d'être installé : les points d'entrée sont
de faux modules écrits dans ``tmp_path``, et la complétion est exécutée par un
vrai bash.
"""

from __future__ import annotations

import argparse
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import installer_lanceurs as il

PIP_COURT = """#!/opt/python/bin/python3.12
# -*- coding: utf-8 -*-
import re
import sys
from paquet.cli.main import main
if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\\.pyw|\\.exe)?$', '', sys.argv[0])
    sys.exit(main())
"""

PIP_LONG = """#!/bin/sh
'''exec' /un/chemin/tres/long/python3.12 "$0" "$@"
' '''
# -*- coding: utf-8 -*-
import re
import sys
from paquet.cli.main import main
if __name__ == '__main__':
    sys.exit(main())
"""

SHIM_BASH = '#!/usr/bin/env bash\nexec "${PYTHON:-python3}" -m paquet "$@"\n'


def _commande(script: Path | None = None, valeur: str = "paquet.cli.main:main") -> il.Commande:
    return il.Commande("paquet", "paquet", valeur, script)


# --- paquets ------------------------------------------------------------------

def test_paquets_de_tools() -> None:
    noms = il.noms_des_paquets()
    assert {"cfd-trajcast", "cfd-perf", "slurm-utils"} <= noms
    assert not any("digitizer" in n for n in noms), "pas de pyproject : pas un paquet"


# --- shebang ------------------------------------------------------------------

def test_contenu_lanceur() -> None:
    texte = il.contenu_lanceur(_commande())
    assert texte.startswith("#!/usr/bin/env python3\n")
    assert "from paquet.cli.main import main\n" in texte and "sys.exit(main())" in texte
    pointe = il.contenu_lanceur(_commande(valeur="paquet.cli:App.lancer"))
    assert "from paquet.cli import App\n" in pointe and "sys.exit(App.lancer())" in pointe


@pytest.mark.parametrize(("texte", "attendu"), [(PIP_COURT, True), (PIP_LONG, True), (SHIM_BASH, False)])
def test_reconnaitre_un_lanceur_pip(texte: str, attendu: bool) -> None:
    assert il.est_lanceur_pip(texte, "paquet.cli.main") is attendu


def _script(tmp_path: Path, texte: str) -> Path:
    chemin = tmp_path / "paquet"
    chemin.write_text(texte, encoding="utf-8")
    chemin.chmod(0o755)
    return chemin


def test_reecrit_si_python3_du_path_importe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(il, "python3_du_path_importe", lambda module: (True, "/usr/bin/python3"))
    script = _script(tmp_path, PIP_LONG)
    assert "réécrit" in il.reecrire_shebang(_commande(script), a_blanc=False, forcer=False)
    assert script.read_text(encoding="utf-8") == il.contenu_lanceur(_commande(script))
    assert script.stat().st_mode & stat.S_IXUSR, "le droit d'exécution est gardé"
    assert "déjà" in il.reecrire_shebang(_commande(script), a_blanc=False, forcer=False)


def test_refuse_si_python3_du_path_ne_voit_pas_le_paquet(tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(il, "python3_du_path_importe", lambda module: (False, "/usr/bin/python3"))
    script = _script(tmp_path, PIP_COURT)
    assert "NON réécrit" in il.reecrire_shebang(_commande(script), a_blanc=False, forcer=False)
    assert script.read_text(encoding="utf-8") == PIP_COURT
    assert "réécrit" in il.reecrire_shebang(_commande(script), a_blanc=False, forcer=True)
    assert script.read_text(encoding="utf-8").startswith(il.SHEBANG)


def test_a_blanc_et_script_etranger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(il, "python3_du_path_importe", lambda module: (True, "/usr/bin/python3"))
    script = _script(tmp_path, PIP_COURT)
    assert "serait réécrit" in il.reecrire_shebang(_commande(script), a_blanc=True, forcer=False)
    assert script.read_text(encoding="utf-8") == PIP_COURT
    shim = _script(tmp_path, SHIM_BASH)
    assert "laissé tel quel" in il.reecrire_shebang(_commande(shim), a_blanc=False, forcer=True)


# --- capture ------------------------------------------------------------------

MODULE_FAUX = '''
import argparse, sys

def _parseur():
    p = argparse.ArgumentParser(prog="faux")
    p.add_argument("--niveau", type=int)
    return p

def main(argv=None):
    if len(sys.argv) == 1:  # comme cfd-stats : l'aide sans analyser
        print("aide"); return 0
    try:
        _parseur().parse_args(argv)
    except Exception:  # ne doit pas avaler la capture
        return 3
    raise AssertionError("parse_args aurait dû être intercepté")
'''


def test_capture_du_parseur(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "faux_cli.py").write_text(MODULE_FAUX, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    argv = list(sys.argv)
    parseur = il.capturer_parseur(il.Commande("faux", "faux", "faux_cli:main", None))
    assert parseur.prog == "faux" and any("--niveau" in a.option_strings for a in parseur._actions)
    assert sys.argv == argv
    assert argparse.ArgumentParser.parse_args.__name__ == "parse_args", "analyseur restauré"


# --- complétion ---------------------------------------------------------------

def _parseur_exemple() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="outil")
    p.add_argument("--version", action="version", version="1")
    p.add_argument("--cache", help=argparse.SUPPRESS)
    sous = p.add_subparsers(dest="commande")
    r = sous.add_parser("rendre")
    r.add_argument("config")
    r.add_argument("--format", choices=["svg", "png", "deux mots"])
    r.add_argument("-j", "--processus", type=int)
    r.add_argument("--sortie")
    r.add_argument("--apercu", action="store_true")
    g = sous.add_parser("groupe")
    gs = g.add_subparsers(dest="action")
    gs.add_parser("lister").add_argument("--tri", choices=["nom", "date"])
    return p


def _completer(tmp_path: Path, *mots: str) -> list[str]:
    script = tmp_path / "completion.bash"
    script.write_text(il.completion_bash("outil", _parseur_exemple()), encoding="utf-8")
    (tmp_path / "ma_config.yaml").write_text("", encoding="utf-8")
    programme = (
        f'source {script}\n'
        f'COMP_WORDS=({" ".join(repr(m) for m in ("outil", *mots))})\n'
        "COMP_CWORD=$(( ${#COMP_WORDS[@]} - 1 ))\n"
        "_outil_completion\n"
        "printf '%s\\n' \"${COMPREPLY[@]}\"\n"
    )
    r = subprocess.run(["bash", "-c", programme], cwd=tmp_path, capture_output=True, text=True, check=True)
    return [ligne for ligne in r.stdout.splitlines() if ligne]


pytestmark_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash absent")


@pytestmark_bash
def test_completion_sous_commandes_et_options(tmp_path: Path) -> None:
    assert _completer(tmp_path, "") == ["rendre", "groupe"]
    assert _completer(tmp_path, "re") == ["rendre"]
    assert _completer(tmp_path, "--") == ["--help", "--version"], "--cache caché"
    options = _completer(tmp_path, "rendre", "--")
    assert {"--format", "--processus", "--sortie", "--apercu"} <= set(options)


@pytestmark_bash
def test_completion_des_valeurs(tmp_path: Path) -> None:
    assert _completer(tmp_path, "rendre", "--format", "") == ["svg", "png", "deux mots"]
    assert _completer(tmp_path, "rendre", "-j", "") == [], "entier : rien à proposer"
    assert "ma_config.yaml" in _completer(tmp_path, "rendre", "--sortie", "ma")
    assert _completer(tmp_path, "rendre", "ma") == ["ma_config.yaml"], "positionnel : fichiers"


@pytestmark_bash
def test_completion_imbriquee(tmp_path: Path) -> None:
    assert _completer(tmp_path, "groupe", "") == ["lister"]
    assert _completer(tmp_path, "groupe", "lister", "--tri", "") == ["nom", "date"]


@pytestmark_bash
def test_completion_vraie_syntaxe_bash(tmp_path: Path) -> None:
    script = tmp_path / "c.bash"
    script.write_text(il.completion_bash("outil", _parseur_exemple()), encoding="utf-8")
    subprocess.run(["bash", "-n", str(script)], check=True)


def test_bashrc_une_seule_fois(tmp_path: Path) -> None:
    bashrc = tmp_path / ".bashrc"
    bashrc.write_text("alias ll='ls -l'", encoding="utf-8")
    cible = tmp_path / "completion.bash"
    assert il.ajouter_au_bashrc(bashrc, cible)
    assert not il.ajouter_au_bashrc(bashrc, cible)
    texte = bashrc.read_text(encoding="utf-8")
    assert texte.startswith("alias ll='ls -l'\n") and texte.count(il.DEBUT_BASHRC) == 1
