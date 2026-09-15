"""Compiler du Fortran ou du C en module Python, par f2py.

Une seule fonction fait le travail, et elle **refuse avant de tenter** quand la
chaîne de compilation est incomplète : ce que produit ``f2py -c`` sans meson
est une trace de plusieurs dizaines de lignes qui ne nomme jamais le remède.
Voir :mod:`cfd_validation.wrap.toolchain`.

Le module construit se charge ensuite par son chemin, sans passer par
``sys.path`` : plusieurs versions d'un même modèle coexistent alors dans une
même session, ce qui est exactement ce qu'on veut quand on compare un code
d'avant et d'après correction.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

from cfd_validation.wrap.toolchain import inspecter_toolchain

__all__ = ["ErreurConstruction", "charger_module", "construire"]

#: Au-delà, on considère que la compilation est partie en vrille.
DELAI_DEFAUT = 600.0


class ErreurConstruction(RuntimeError):
    """La compilation n'a pas abouti, ou n'a pas pu être tentée."""


def construire(
    sources: str | Path | Sequence[str | Path],
    *,
    nom_module: str | None = None,
    destination: str | Path | None = None,
    options: Sequence[str] = (),
    delai: float = DELAI_DEFAUT,
) -> Path:
    """Compile *sources* en module d'extension et rend le chemin du ``.so``.

    Parameters
    ----------
    sources:
        Un fichier, ou plusieurs. ``.f``, ``.f90``, ``.c`` — ce que f2py sait lire.
    nom_module:
        Nom du module produit. Par défaut, celui de la première source.
    destination:
        Répertoire où écrire. Par défaut, celui de la première source.
    options:
        Options passées telles quelles à f2py (``"--f90flags=-O2"``, ``"-DNDEBUG"``…).
    delai:
        Secondes avant abandon.

    Raises
    ------
    ErreurConstruction
        Chaîne incomplète (le message nomme le remède), source absente,
        compilation en échec, ou module introuvable après coup.
    """
    chemins = _sources(sources)
    nom = nom_module or chemins[0].stem
    dossier = Path(destination) if destination is not None else chemins[0].parent
    dossier.mkdir(parents=True, exist_ok=True)

    chaine = inspecter_toolchain()
    if not chaine.pret:
        raise ErreurConstruction(
            f"compilation impossible : {', '.join(chaine.manques)} manque(nt) "
            f"(NumPy {chaine.numpy}, moteur f2py « {chaine.backend} »).\n"
            f"Remède : {chaine.remede}"
        )

    commande = [
        sys.executable,
        "-m",
        "numpy.f2py",
        "-c",
        "-m",
        nom,
        *(str(chemin) for chemin in chemins),
        *options,
    ]
    try:
        acheve = subprocess.run(
            commande,
            cwd=dossier,
            capture_output=True,
            text=True,
            timeout=delai,
            check=False,
        )
    except subprocess.TimeoutExpired as erreur:
        raise ErreurConstruction(
            f"compilation de « {nom} » abandonnée après {delai:g} s."
        ) from erreur

    if acheve.returncode != 0:
        raise ErreurConstruction(
            f"f2py a échoué (code {acheve.returncode}) sur « {nom} ».\n"
            f"--- sortie standard ---\n{_queue(acheve.stdout)}\n"
            f"--- sortie d'erreur ---\n{_queue(acheve.stderr)}"
        )

    produits = sorted(dossier.glob(f"{nom}*.so")) + sorted(dossier.glob(f"{nom}*.pyd"))
    if not produits:
        raise ErreurConstruction(
            f"f2py a rendu 0 mais aucun module « {nom} » n'a été écrit dans {dossier}."
        )
    return produits[0]


def charger_module(chemin: str | Path, *, nom: str | None = None) -> ModuleType:
    """Importe un module d'extension **par son chemin**, hors ``sys.path``.

    Deux compilations d'un même modèle peuvent ainsi vivre côte à côte dans une
    session — le cas exact d'une comparaison avant/après correctif.
    """
    chemin = Path(chemin).resolve()
    if not chemin.exists():
        raise ErreurConstruction(f"module introuvable : {chemin}")
    module_nom = nom or chemin.name.split(".")[0]
    specification = importlib.util.spec_from_file_location(module_nom, chemin)
    if specification is None or specification.loader is None:
        raise ErreurConstruction(f"{chemin} n'est pas un module Python importable.")
    module = importlib.util.module_from_spec(specification)
    sys.modules.setdefault(module_nom, module)
    specification.loader.exec_module(module)
    return module


def _sources(sources: str | Path | Sequence[str | Path]) -> list[Path]:
    """Normalise et vérifie l'existence des sources."""
    brutes: Sequence[str | Path]
    brutes = [sources] if isinstance(sources, (str, Path)) else list(sources)
    if not brutes:
        raise ErreurConstruction("aucune source à compiler.")
    chemins = [Path(source).resolve() for source in brutes]
    absentes = [str(chemin) for chemin in chemins if not chemin.exists()]
    if absentes:
        raise ErreurConstruction(f"source(s) introuvable(s) : {absentes}")
    return chemins


def _queue(texte: str, lignes: int = 25) -> str:
    """Les dernières lignes d'une sortie : le reste n'apprend rien."""
    morceaux = (texte or "").strip().splitlines()
    return "\n".join(morceaux[-lignes:]) if morceaux else "(vide)"
