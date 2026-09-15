"""Désigner un module ou une fonction par une chaîne, comme sur la ligne de commande.

``cfd-validation valider --modele mon_paquet.aero:appeler`` doit pouvoir aller
chercher cet objet sans que l'utilisateur écrive une ligne de Python. C'est le
seul endroit du paquet qui importe du code arbitraire, et il le fait en
nommant l'échec : un ``ModuleNotFoundError`` brut devant un module compilé
absent n'aide personne.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from cfd_validation.wrap.construire import charger_module

__all__ = ["ErreurResolution", "resoudre_module", "resoudre_objet"]


class ErreurResolution(ValueError):
    """Impossible d'atteindre l'objet désigné."""


def resoudre_module(designation: str) -> ModuleType:
    """Un module, désigné par son nom pointé **ou** par un chemin de fichier.

    Un chemin est reconnu à son existence sur le disque : ``./aero.so``,
    ``build/aero.cpython-312-x86_64-linux-gnu.so``, ou un ``.py`` quelconque.
    """
    chemin = Path(designation)
    if chemin.exists() and chemin.is_file():
        return charger_module(chemin)
    # Un module posé à côté, sans installation : cas courant d'un `.so` fraîchement compilé.
    if str(Path.cwd()) not in sys.path:
        sys.path.insert(0, str(Path.cwd()))
    try:
        return importlib.import_module(designation)
    except ImportError as erreur:
        raise ErreurResolution(
            f"module « {designation} » introuvable : {erreur}.\n"
            "Donnez un nom importable, ou le chemin du fichier compilé "
            "(par exemple build/aero.cpython-312-x86_64-linux-gnu.so)."
        ) from erreur


def resoudre_objet(designation: str) -> Any:
    """Un objet d'un module, désigné ``module:attribut`` (ou ``module.attribut``).

    La forme à deux-points est préférée, et c'est celle que documente la CLI :
    elle lève toute ambiguïté entre un sous-module et un attribut.
    """
    if ":" in designation:
        module_nom, _, attribut = designation.partition(":")
    elif "." in designation:
        module_nom, _, attribut = designation.rpartition(".")
    else:
        raise ErreurResolution(
            f"« {designation} » ne désigne pas un objet. "
            "Attendu « module:fonction », par exemple mon_paquet.aero:appeler."
        )

    module = resoudre_module(module_nom)
    try:
        return getattr(module, attribut)
    except AttributeError as erreur:
        publics = sorted(nom for nom in dir(module) if not nom.startswith("_"))
        raise ErreurResolution(
            f"« {module_nom} » ne porte pas d'attribut « {attribut} ». Disponible(s) : {publics}."
        ) from erreur
