"""Rendre la commande ``cfd-perf`` utilisable quand le script console ne l'est pas.

``pip`` grave dans le script console le chemin absolu de l'interpréteur qui a
lancé l'installation (``sys.executable``). Ce chemin n'est pas toujours valable
là où l'utilisateur tape la commande :

* Python fourni par une **image conteneur** (Apptainer/Singularity ``.sif``)
  chargée par ``module load`` : ``pip`` tourne *dans* l'image et grave un chemin
  interne (``/opt/python/bin/python3``) que l'hôte ne voit pas ;
* environnement déplacé après coup (venv renommé, installation partagée
  migrée) ;
* chemin d'interpréteur trop long : au-delà de 127 octets le noyau refuse le
  ``#!``, et ``pip`` bascule sur la forme ``#!/bin/sh`` + ``'''exec' …``.

Dans les trois cas le script existe, il est exécutable, et il répond
``bad interpreter: No such file or directory``.

Le lanceur écrit ici ne grave aucun interpréteur : il résout ``python3`` sur le
``PATH`` au moment de l'appel. Il suit donc l'environnement chargé — module,
venv, conda, image conteneur — au lieu d'un chemin figé à l'installation.
"""

from __future__ import annotations

import os
import shlex
import stat
from pathlib import Path
from shutil import which

LAUNCHER_NAME = "cfd-perf"
ENV_PYTHON = "CFD_PERF_PYTHON"

# Marqueur de la forme « shebang long » émise par pip/setuptools quand le
# chemin de l'interpréteur dépasse la limite du noyau.
_EXEC_LONG = "'''exec'"

_SHELLS = frozenset({"sh", "bash", "dash", "zsh", "ksh"})

_LAUNCHER = """\
#!/usr/bin/env bash
# ---------------------------------------------------------------------
#  Lanceur cfd-perf — écrit par « cfd-perf shim ».
#
#  Aucun interpréteur n'est gravé ici : « python3 » est résolu sur le PATH
#  à chaque appel. La commande suit donc l'environnement chargé (module,
#  venv, conda, image conteneur) au lieu du chemin figé par pip.
#
#  Si Python vient d'un module, décommentez et adaptez :
#      module load python/3.11 2>/dev/null || true
#
#  Pour imposer un interpréteur : export CFD_PERF_PYTHON=/chemin/vers/python
# ---------------------------------------------------------------------
set -euo pipefail

PY="${CFD_PERF_PYTHON:-python3}"

if ! command -v "$PY" >/dev/null 2>&1; then
    echo "cfd-perf : interpréteur « $PY » introuvable sur le PATH." >&2
    echo "           Chargez votre module Python, ou exportez CFD_PERF_PYTHON." >&2
    exit 127
fi

exec "$PY" -m cfd_perf "$@"
"""


def render_launcher() -> str:
    """Le texte du lanceur, tel qu'il sera écrit sur le disque."""
    return _LAUNCHER


def write_launcher(dest_dir: Path | str, *, force: bool = False) -> Path:
    """Écrit ``DEST/cfd-perf`` et le rend exécutable ; renvoie son chemin.

    Lève ``FileExistsError`` si le fichier est déjà là et que ``force`` est faux
    — écraser en silence un lanceur maison serait une mauvaise surprise.
    """
    repertoire = Path(dest_dir).expanduser()
    cible = repertoire / LAUNCHER_NAME
    if cible.exists() and not force:
        raise FileExistsError(str(cible))
    repertoire.mkdir(parents=True, exist_ok=True)
    cible.write_text(render_launcher(), encoding="utf-8")
    cible.chmod(cible.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return cible


def interpreter_of(script: Path) -> str | None:
    """L'interpréteur qu'un script console exécutera réellement.

    ``None`` quand le script n'en désigne aucun de façon exploitable — un
    lanceur ``#!/usr/bin/env bash`` comme celui écrit ici, par exemple.
    """
    try:
        with script.open("r", encoding="utf-8", errors="replace") as fh:
            premiere = fh.readline()
            seconde = fh.readline()
    except OSError:
        return None

    if not premiere.startswith("#!"):
        return None
    try:
        mots = shlex.split(premiere[2:].strip())
    except ValueError:
        return None
    if not mots:
        return None

    # Forme « shebang long » : le vrai interpréteur est sur la ligne 2.
    if Path(mots[0]).name in {"sh", "bash"} and seconde.lstrip().startswith(_EXEC_LONG):
        reste = seconde.strip()[len(_EXEC_LONG) :]
        try:
            arguments = shlex.split(reste)
        except ValueError:
            return None
        return arguments[0] if arguments else None

    # « #!/usr/bin/env python3 » : c'est python3, pas env, qu'il faut trouver.
    interpreteur = mots[1] if Path(mots[0]).name == "env" and len(mots) > 1 else mots[0]

    # Un lanceur shell ne grave aucun interpréteur : rien à vérifier.
    if Path(interpreteur).name in _SHELLS:
        return None
    return interpreteur


def interpreter_exists(interpreter: str) -> bool:
    """L'interpréteur désigné est-il atteignable depuis ici ?"""
    if os.path.isabs(interpreter):
        return os.path.exists(interpreter)
    return which(interpreter) is not None


def is_runnable(script: Path) -> bool:
    """Le script se lancera-t-il, ou mourra-t-il en « bad interpreter » ?"""
    interpreteur = interpreter_of(script)
    return True if interpreteur is None else interpreter_exists(interpreteur)


def commands_on_path(name: str = LAUNCHER_NAME) -> list[Path]:
    """Tous les ``cfd-perf`` du ``PATH``, dans l'ordre où le shell les trouve.

    Le premier de la liste est celui qui gagne. En voir plusieurs est le
    symptôme classique de deux installations superposées.
    """
    trouves: list[Path] = []
    for repertoire in os.environ.get("PATH", "").split(os.pathsep):
        if not repertoire:
            continue
        candidat = Path(repertoire) / name
        if candidat.is_file() and os.access(str(candidat), os.X_OK) and candidat not in trouves:
            trouves.append(candidat)
    return trouves


def dir_is_on_path(directory: Path | str) -> bool:
    """Le répertoire est-il sur le ``PATH`` ? (comparaison sur chemins résolus)"""
    cible = Path(directory).expanduser().resolve()
    for repertoire in os.environ.get("PATH", "").split(os.pathsep):
        if repertoire and Path(repertoire).expanduser().resolve() == cible:
            return True
    return False
