"""De quoi f2py a besoin ici, et ce qui manque.

``f2py -c`` a changé de moteur : jusqu'à NumPy 1.26 il compilait par
``numpy.distutils``, retiré depuis, et depuis NumPy 2 il délègue à **meson** et
**ninja**. Aucun des deux n'est une dépendance de NumPy, si bien que
``pip install numpy`` donne un ``f2py`` qui sait générer des sources et pas les
compiler — et l'échec, en l'état, est une trace de compilation illisible.

Ce module rend cet état **explicite et nommable** avant la première tentative,
et c'est ce que ``cfd-validation construire`` affiche quand il ne peut pas
travailler.

.. note:: Calculateur isolé

   ``meson`` et ``ninja`` sont des roues PyPI, pas des paquets système : elles
   doivent être dans le cache de roues hors-ligne, sinon toute la partie
   compilation est morte sur site. Le reste du paquet — lecture de tables,
   comparaison, diagnostic, figures — n'en dépend pas.
"""

from __future__ import annotations

import shutil
import sys
import sysconfig
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path

__all__ = ["Toolchain", "inspecter_toolchain"]


@dataclass(frozen=True)
class Toolchain:
    """L'état de la chaîne de compilation, vu depuis cet interpréteur."""

    #: Version de NumPy, telle qu'importée.
    numpy: str
    #: Moteur que ``f2py -c`` emploiera : ``"meson"`` ou ``"distutils"``.
    backend: str
    #: Compilateurs trouvés sur le ``PATH``, chemin absolu ou ``None``.
    gfortran: str | None
    gcc: str | None
    #: Outils du moteur meson, chemin absolu ou ``None``.
    meson: str | None
    ninja: str | None
    #: ``numpy.distutils`` est-il encore importable ?
    distutils: bool
    #: Ce qui manque pour compiler, nommé.
    manques: tuple[str, ...]
    #: Outils installés à côté de l'interpréteur mais **absents du PATH**.
    #: f2py les lance par leur nom : introuvables sur le PATH, ils n'existent
    #: pas pour lui, et l'échec brut est un ``FileNotFoundError: 'meson'`` qui
    #: ne dit pas d'activer son environnement.
    hors_path: tuple[str, ...] = ()

    @property
    def pret(self) -> bool:
        """Vrai si une compilation Fortran peut aboutir."""
        return not self.manques

    @property
    def remede(self) -> str:
        """La commande à taper, ou une phrase vide si tout est là."""
        if self.pret:
            return ""
        remedes: list[str] = []
        if self.hors_path:
            accord = "sont installés" if len(self.hors_path) > 1 else "est installé"
            remedes.append(
                f"{', '.join(self.hors_path)} {accord} dans {_bin_interpreteur()} "
                "mais absent(s) du PATH — activez l'environnement virtuel, ou "
                f'export PATH="{_bin_interpreteur()}:$PATH"'
            )
        absents = [
            outil
            for outil in ("meson", "ninja")
            if outil in self.manques and outil not in self.hors_path
        ]
        if absents:
            remedes.append(f"pip install {' '.join(absents)}")
        if "numpy.distutils" in self.manques:
            remedes.append(
                "numpy.distutils a été retiré de NumPy ; "
                "passez au moteur meson (NumPy >= 2 + pip install meson ninja)"
            )
        if "gfortran" in self.manques:
            remedes.append("installez gfortran (dnf install gcc-gfortran / apt install gfortran)")
        if "gcc" in self.manques:
            remedes.append("installez gcc")
        return " ; ".join(remedes)


def inspecter_toolchain() -> Toolchain:
    """Regarde ce dont f2py dispose, sans rien compiler."""
    import numpy

    version = str(numpy.__version__)
    majeure = int(version.split(".")[0])
    distutils = find_spec("numpy.distutils") is not None
    backend = "meson" if majeure >= 2 else ("distutils" if distutils else "meson")

    # `shutil.which` et rien d'autre : c'est exactement ce que f2py fera, qui
    # lance ces outils par leur nom dans un sous-processus.
    meson = shutil.which("meson")
    ninja = shutil.which("ninja")
    gfortran = shutil.which("gfortran")
    gcc = shutil.which("gcc")

    manques: list[str] = []
    hors_path: list[str] = []
    if backend == "meson":
        for outil, trouve in (("meson", meson), ("ninja", ninja)):
            if trouve is not None:
                continue
            manques.append(outil)
            if (_bin_interpreteur() / outil).exists():
                hors_path.append(outil)
    elif not distutils:  # pragma: no cover - dépend de l'environnement
        manques.append("numpy.distutils")
    if gfortran is None:
        manques.append("gfortran")
    if gcc is None:
        manques.append("gcc")

    return Toolchain(
        numpy=version,
        backend=backend,
        gfortran=gfortran,
        gcc=gcc,
        meson=meson,
        ninja=ninja,
        distutils=distutils,
        manques=tuple(manques),
        hors_path=tuple(hors_path),
    )


def _bin_interpreteur() -> Path:
    """Le répertoire des scripts de l'interpréteur courant.

    C'est là que ``pip install meson`` les dépose dans un environnement
    virtuel — et c'est ce répertoire qui manque au PATH quand l'environnement
    n'est pas activé.

    Surtout pas de ``resolve()`` ici : dans un environnement virtuel,
    ``sys.executable`` est un lien symbolique vers l'interpréteur système, et
    le résoudre désignerait ``/usr/bin`` — c'est-à-dire tout sauf le
    répertoire qu'on cherche.
    """
    scripts = sysconfig.get_path("scripts")
    return Path(scripts) if scripts else Path(sys.executable).parent
