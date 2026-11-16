"""``cfd-trajcast diagnostic`` : de quoi cette machine est-elle capable ?

Chaque fenêtre OpenGL est essayée dans un **sous-processus** : une fenêtre
impossible (OSMesa absent, X refusé) fait planter VTK au lieu de lever une
exception.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import subprocess
import sys
from dataclasses import dataclass

import imageio_ffmpeg

from cfd_trajcast.engine.rendu.pyvista_ import PREFIXE_SONDE

__all__ = ["Sonde", "diagnostiquer", "sonder_fenetre"]

#: Fenêtres VTK essayées : nom → variables d'environnement.
FENETRES: dict[str, dict[str, str]] = {
    "EGL (GPU par défaut)": {"VTK_DEFAULT_OPENGL_WINDOW": "vtkEGLRenderWindow"},
    "EGL périphérique 1 (souvent llvmpipe, logiciel)": {
        "VTK_DEFAULT_OPENGL_WINDOW": "vtkEGLRenderWindow", "VTK_DEFAULT_EGL_DEVICE_INDEX": "1"},
    "X11 (si DISPLAY)": {"VTK_DEFAULT_OPENGL_WINDOW": "vtkXOpenGLRenderWindow"},
}


@dataclass(frozen=True)
class Sonde:
    """Résultat d'un essai."""

    nom: str
    ok: bool
    detail: str


def sonder_fenetre(nom: str, env: dict[str, str], delai: float = 90.0) -> Sonde:
    """Lance la sonde de rendu avec ``env`` dans un sous-processus."""
    environnement = {**os.environ, **env}
    if "X11" in nom and not os.environ.get("DISPLAY"):
        return Sonde(nom, False, "DISPLAY non défini")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "cfd_trajcast.engine.rendu.pyvista_", "--sonde"],
            env=environnement, capture_output=True, text=True, timeout=delai, check=False,
        )
    except subprocess.TimeoutExpired:
        return Sonde(nom, False, f"pas de réponse en {delai:.0f} s")
    lignes = [ligne[len(PREFIXE_SONDE):].strip() for ligne in r.stdout.splitlines()
              if ligne.startswith(PREFIXE_SONDE)]
    pilote = next((ligne.split(":", 1)[1].strip() for ligne in lignes if "renderer string" in ligne), "")
    if r.returncode == 0:
        return Sonde(nom, True, pilote or "rendu correct")
    raison = "processus arrêté par un signal" if r.returncode < 0 else (pilote or "image vide")
    erreur = next((ligne for ligne in r.stderr.splitlines() if "ERR" in ligne or "rror" in ligne), "")
    return Sonde(nom, False, f"{raison} {erreur[-120:]}".strip())


def diagnostiquer() -> list[Sonde]:
    """Python, ffmpeg, extras, puis chaque fenêtre de rendu."""
    sondes = [Sonde("Python", True, f"{platform.python_version()} ({sys.executable})")]
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        version = subprocess.run([exe, "-version"], capture_output=True, text=True, check=False)
        sondes.append(Sonde("ffmpeg", True, version.stdout.splitlines()[0][:80]))
    except (RuntimeError, OSError, IndexError) as exc:
        sondes.append(Sonde("ffmpeg", False, str(exc)))
    for module, extra in (("cascadio", "[step] — lecture des STEP"), ("rocketpy", "[rocketpy]"),
                          ("bpy", "[blender] — moteur Blender (bpy 5.x : Python 3.13)")):
        present = importlib.util.find_spec(module) is not None
        sondes.append(Sonde(module, present, f"extra {extra}" + ("" if present else " : absent")))
    sondes.append(Sonde("DISPLAY", bool(os.environ.get("DISPLAY")), os.environ.get("DISPLAY", "non défini")))
    sondes += [sonder_fenetre(nom, env) for nom, env in FENETRES.items()]
    return sondes
