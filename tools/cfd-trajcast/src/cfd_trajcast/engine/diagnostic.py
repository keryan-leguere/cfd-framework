"""``cfd-trajcast diagnostic`` : de quoi cette machine est-elle capable ?

Chaque fenêtre OpenGL est essayée dans un **sous-processus** : une fenêtre
impossible (OSMesa absent, X refusé) fait planter VTK au lieu de lever une
exception.

Quand aucune fenêtre ne marche, il faut savoir *pourquoi* sans relancer quoi que
ce soit à la main (machine air-gap). D'où, en plus des essais :

* les **versions** de la pile Python, lues dans les métadonnées (sans importer :
  un pyvista cassé ne doit pas casser le diagnostic), comparées aux minimums de
  ``pyproject.toml`` — un pyvista trop ancien est *refusé*, pas signalé ;
* l'**étape** à laquelle chaque essai meurt (import, fenêtre, rendu) et son erreur
  **complète** : les trois essais morts à l'import, c'est la pile Python, pas le GPU ;
* ce que la roue VTK attend du **système** : bibliothèques glvnd, fournisseurs EGL,
  droits sur les périphériques GPU ;
* la fenêtre que le **rendu** utilisera réellement, qui n'est pas forcément celle
  qu'un essai a réussie.
"""

from __future__ import annotations

import ctypes.util
import glob
import importlib.metadata
import importlib.util
import os
import platform
import re
import signal
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass

import imageio_ffmpeg

from cfd_trajcast.engine.rendu.pyvista_ import PREFIXE_SONDE, fenetre_choisie

__all__ = [
    "ETAPES",
    "VERSIONS_MINIMALES",
    "Sonde",
    "cause_probable",
    "diagnostiquer",
    "sonder_fenetre",
    "sonder_interface",
    "sonder_versions",
]

#: Fenêtres VTK essayées : nom → variables d'environnement.
FENETRES: dict[str, dict[str, str]] = {
    "EGL (GPU par défaut)": {"VTK_DEFAULT_OPENGL_WINDOW": "vtkEGLRenderWindow"},
    "EGL périphérique 1 (souvent llvmpipe, logiciel)": {
        "VTK_DEFAULT_OPENGL_WINDOW": "vtkEGLRenderWindow", "VTK_DEFAULT_EGL_DEVICE_INDEX": "1"},
    "X11 (si DISPLAY)": {"VTK_DEFAULT_OPENGL_WINDOW": "vtkXOpenGLRenderWindow"},
}

#: Minimums de ``pyproject.toml`` (un test vérifie qu'ils n'ont pas divergé).
VERSIONS_MINIMALES: dict[str, str] = {
    "numpy": "1.22",
    "vtk": "9.3",
    "pyvista": "0.44",
    "trimesh": "4.0",
    "matplotlib": "3.5",
    "pillow": "9.1",
    "imageio-ffmpeg": "0.5",
}

#: Étapes de la sonde, dans l'ordre où elle les annonce.
ETAPES = ("import", "fenetre", "rendu")

#: Lignes d'erreur gardées par essai (la fin : c'est là qu'est la cause).
LIGNES_TRACE = 40

_REPERTOIRES_EGL = ("/usr/share/glvnd/egl_vendor.d", "/etc/glvnd/egl_vendor.d")


@dataclass(frozen=True)
class Sonde:
    """Résultat d'un essai.

    ``categorie`` : python, version, extra, systeme, fenetre, rendu ou interface ;
    ``etape`` : dernière étape atteinte par un essai de fenêtre ;
    ``trace`` : erreur complète (fin du stderr) d'un essai raté.
    """

    nom: str
    ok: bool
    detail: str
    categorie: str = ""
    etape: str = ""
    trace: str = ""


# --- versions -----------------------------------------------------------------

def _tuple_version(texte: str) -> tuple[int, ...]:
    m = re.match(r"\d+(?:\.\d+)*", texte)
    return tuple(int(x) for x in m.group(0).split(".")) if m else ()


def _version_installee(distribution: str) -> str | None:
    # Python 3.9 ne normalise pas les noms : « Pillow », « imageio_ffmpeg »…
    for nom in dict.fromkeys((distribution, distribution.replace("-", "_"), distribution.capitalize())):
        try:
            return importlib.metadata.version(nom)
        except importlib.metadata.PackageNotFoundError:
            continue
    return None


def sonder_versions(installees: dict[str, str | None] | None = None) -> list[Sonde]:
    """Une sonde par dépendance : présente, et au moins au minimum déclaré.

    ``installees`` remplace la lecture des métadonnées (tests).
    """
    lues = installees if installees is not None else {
        d: _version_installee(d) for d in VERSIONS_MINIMALES}
    sondes = []
    for dist, minimum in VERSIONS_MINIMALES.items():
        v = lues.get(dist)
        if v is None:
            sondes.append(Sonde(dist, False, f"absent ; ≥ {minimum} exigé", "version"))
        elif _tuple_version(v) < _tuple_version(minimum):
            detail = f"{v} — trop ancien, ≥ {minimum} exigé"
            numpy = lues.get("numpy")
            if dist == "pyvista" and numpy and _tuple_version(numpy) >= (2,):
                detail += f" (pyvista < 0.44 est antérieur à NumPy 2, installé ici en {numpy})"
            sondes.append(Sonde(dist, False, detail, "version"))
        else:
            sondes.append(Sonde(dist, True, v, "version"))
    return sondes


# --- système ------------------------------------------------------------------

def sonder_systeme() -> list[Sonde]:
    """Ce que la roue VTK prend au système : glvnd, fournisseurs EGL, périphériques."""
    libs = {nom: ctypes.util.find_library(nom) for nom in ("EGL", "OpenGL", "GLX", "GL")}
    detail_libs = ", ".join(f"lib{n} : {chemin or 'absente'}" for n, chemin in libs.items())
    sondes = [Sonde("bibliothèques GL", bool(libs["EGL"]) and bool(libs["OpenGL"] or libs["GL"]),
                    detail_libs, "systeme")]

    repertoires = [d for d in os.environ.get("__EGL_VENDOR_LIBRARY_DIRS", "").split(":") if d]
    fichiers = [f for f in os.environ.get("__EGL_VENDOR_LIBRARY_FILENAMES", "").split(":") if f]
    for d in repertoires or _REPERTOIRES_EGL:
        fichiers += sorted(glob.glob(os.path.join(d, "*.json")))
    noms = [os.path.basename(f) for f in fichiers]
    sondes.append(Sonde("fournisseurs EGL", bool(noms),
                        ", ".join(noms) if noms else "aucun fichier *.json (pilote installé sans EGL ?)",
                        "systeme"))

    peripheriques = sorted(glob.glob("/dev/dri/renderD*")) + [
        p for p in ("/dev/nvidia0", "/dev/nvidiactl") if os.path.exists(p)]
    etats = [f"{os.path.basename(p)} {'accessible' if os.access(p, os.R_OK | os.W_OK) else 'refusé'}"
             for p in peripheriques]
    accessible = any(os.access(p, os.R_OK | os.W_OK) for p in peripheriques)
    detail = ", ".join(etats) if etats else "aucun /dev/dri/renderD* ni /dev/nvidia*"
    if etats and not accessible:
        detail += " (droits : groupes video/render ?)"
    try:
        with open("/proc/driver/nvidia/version", encoding="utf-8") as f:
            pilote = re.search(r"Kernel Module\s+(\S+)", f.readline())
        if pilote:
            detail += f" ; pilote NVIDIA {pilote.group(1)}"
    except OSError:
        pass
    sondes.append(Sonde("périphériques GPU", accessible, detail, "systeme"))
    return sondes


# --- fenêtres -----------------------------------------------------------------

def _raison_code(code: int) -> str:
    if code >= 0:
        return f"code retour {code}"
    try:
        return f"tué par {signal.Signals(-code).name}"
    except ValueError:
        return f"tué par le signal {-code}"


def sonder_fenetre(nom: str, env: dict[str, str], delai: float = 90.0) -> Sonde:
    """Lance la sonde de rendu avec ``env`` dans un sous-processus."""
    environnement = {**os.environ, **env}
    if "X11" in nom and not os.environ.get("DISPLAY"):
        return Sonde(nom, False, "DISPLAY non défini", "fenetre")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "cfd_trajcast.engine.rendu.pyvista_", "--sonde"],
            env=environnement, capture_output=True, text=True, timeout=delai, check=False,
        )
    except subprocess.TimeoutExpired:
        return Sonde(nom, False, f"pas de réponse en {delai:.0f} s", "fenetre")
    return lire_sonde(nom, r.returncode, r.stdout, r.stderr)


def lire_sonde(nom: str, code: int, stdout: str, stderr: str) -> Sonde:
    """Interprète la sortie d'une sonde de fenêtre (séparé pour les tests)."""
    lignes = [ligne[len(PREFIXE_SONDE):].strip() for ligne in stdout.splitlines()
              if ligne.startswith(PREFIXE_SONDE)]
    pilote = next((ligne.split(":", 1)[1].strip() for ligne in lignes if "renderer string" in ligne), "")
    etapes = [ligne.split()[1] for ligne in lignes if ligne.startswith("etape ") and len(ligne.split()) > 1]
    etape = etapes[-1] if etapes else ""
    if code == 0:
        return Sonde(nom, True, pilote or "rendu correct", "fenetre", etape)
    if code == 1 and etape == "rendu" and any("image vide" in ligne for ligne in lignes):
        raison = f"image vide ({pilote})" if pilote else "image vide"
    else:
        lieu = f"à l'étape « {etape} »" if etape else "avant même l'import de pyvista"
        raison = f"échec {lieu}, {_raison_code(code)}"
    trace = "\n".join(stderr.rstrip().splitlines()[-LIGNES_TRACE:])
    derniere = next((ligne.strip() for ligne in reversed(stderr.splitlines()) if ligne.strip()), "")
    detail = f"{raison} : {derniere[-160:]}" if derniere else raison
    return Sonde(nom, False, detail, "fenetre", etape, trace)


def sonder_rendu(fenetres: Sequence[Sonde]) -> Sonde:
    """La fenêtre que le moteur prendra — et si l'essai correspondant a réussi."""
    classe, raison = fenetre_choisie()
    essai = {"vtkEGLRenderWindow": "EGL (GPU par défaut)", "vtkXOpenGLRenderWindow": "X11 (si DISPLAY)"}
    # Sans choix imposé, VTK essaie X11 en premier (DISPLAY est alors défini).
    nom = essai.get(classe or "vtkXOpenGLRenderWindow")
    if os.environ.get("VTK_DEFAULT_EGL_DEVICE_INDEX", "0") not in ("", "0") and classe == "vtkEGLRenderWindow":
        nom = None  # périphérique imposé : pas l'un des essais
    resultat = next((s for s in fenetres if s.nom == nom), None)
    texte = f"{classe or 'choix de VTK (X11 en général)'} — {raison}"
    if resultat is None:
        return Sonde("fenêtre du rendu", any(s.ok for s in fenetres), texte, "rendu")
    if resultat.ok:
        return Sonde("fenêtre du rendu", True, texte, "rendu")
    autre = next((s for s in fenetres if s.ok), None)
    conseil = ""
    if autre is not None:
        conseil = " ; essai réussi : " + autre.nom + " → " + _export_pour(autre.nom)
    return Sonde("fenêtre du rendu", False, f"{texte}, dont l'essai a échoué{conseil}", "rendu")


def _export_pour(nom: str) -> str:
    env = FENETRES.get(nom, {})
    return " ".join(f"export {k}={v}" for k, v in env.items()) or "?"


# --- ensemble -----------------------------------------------------------------

def _sous_processus(module: str, prefixe: str, delai: float = 60.0) -> tuple[bool, str]:
    """Lance ``python -m module`` ; (réussi, ligne de résultat ou erreur)."""
    try:
        r = subprocess.run([sys.executable, "-m", module], capture_output=True, text=True,
                           timeout=delai, check=False)
    except subprocess.TimeoutExpired:
        return False, f"pas de réponse en {delai:.0f} s"
    ligne = next((x[len(prefixe):].strip() for x in r.stdout.splitlines() if x.startswith(prefixe)), "")
    if r.returncode == 0:
        return True, ligne
    erreur = next((x.strip() for x in reversed(r.stderr.splitlines())
                   if x.strip() and "XDG_SESSION_TYPE" not in x and "vblank_mode" not in x), "")
    raison = ligne or (_raison_code(r.returncode))
    return False, f"{raison} : {erreur[-180:]}" if erreur else raison


def sonder_interface() -> list[Sonde]:
    """L'interface (extra [gui]) : bibliothèques, fenêtre Qt, vue VTK interactive.

    Facultative : ces sondes ne changent pas le code de sortie du diagnostic.
    """
    sondes = []
    for dist in ("PyQt5", "pyvistaqt"):
        v = _version_installee(dist)
        sondes.append(Sonde(dist, v is not None, v or "absent : pip install 'cfd-trajcast[gui]'", "interface"))
    if not sondes[0].ok:
        return sondes
    ok, detail = _sous_processus("cfd_trajcast.gui.sonde_qt", "SONDE_QT:")
    if not ok and "xcb" in detail:
        detail += " — bibliothèques système du greffon xcb (libxcb-xinerama0, libxkbcommon-x11-0…)"
    sondes.append(Sonde("fenêtre Qt", ok, detail, "interface"))
    if ok and sondes[1].ok:
        ok_vtk, detail_vtk = _sous_processus("cfd_trajcast.gui.sonde_vtk", "SONDE_VTK:")
        if not ok_vtk:
            detail_vtk += " — l'interface reste utilisable avec la vue Matplotlib"
        sondes.append(Sonde("vue VTK interactive", ok_vtk, detail_vtk, "interface"))
    return sondes


def cause_probable(sondes: Sequence[Sonde]) -> str | None:
    """Ce qu'il faut corriger en premier quand aucune fenêtre ne marche (sinon ``None``)."""
    fenetres = [s for s in sondes if s.categorie == "fenetre"]
    if any(s.ok for s in fenetres):
        return None
    vieilles = [s for s in sondes if s.categorie == "version" and not s.ok]
    essayees = [s for s in fenetres if s.detail != "DISPLAY non défini"]
    avant_fenetre = bool(essayees) and all(s.etape in ("", "import") for s in essayees)
    if vieilles and (avant_fenetre or not essayees):
        noms = ", ".join(f"{s.nom} ({s.detail})" for s in vieilles)
        return f"pile Python : {noms}. Apporter des roues conformes avant de regarder le GPU."
    if avant_fenetre:
        return ("tous les essais meurent avant d'ouvrir une fenêtre : c'est la pile Python "
                "(import de pyvista/vtk), pas le GPU — voir les erreurs complètes ci-dessous.")
    systeme = {s.nom: s for s in sondes if s.categorie == "systeme"}
    if "bibliothèques GL" in systeme and not systeme["bibliothèques GL"].ok:
        return ("bibliothèques glvnd manquantes (libEGL.so.1 / libOpenGL.so.0) : paquet libglvnd "
                "de la distribution (RHEL : libglvnd-egl libglvnd-opengl).")
    if "fournisseurs EGL" in systeme and not systeme["fournisseurs EGL"].ok:
        return ("aucun fournisseur EGL déclaré : pilote GPU installé sans ses fichiers EGL/OpenGL, "
                "ou Mesa absente (mesa-libEGL mesa-dri-drivers).")
    if "périphériques GPU" in systeme and not systeme["périphériques GPU"].ok:
        return f"GPU inaccessible : {systeme['périphériques GPU'].detail}."
    if vieilles:
        return "versions hors minimum : " + ", ".join(f"{s.nom} ({s.detail})" for s in vieilles) + "."
    return None


def diagnostiquer() -> list[Sonde]:
    """Python, versions, ffmpeg, extras, système, puis chaque fenêtre de rendu."""
    sondes = [Sonde("Python", True, f"{platform.python_version()} ({sys.executable})", "python")]
    sondes += sonder_versions()
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        version = subprocess.run([exe, "-version"], capture_output=True, text=True, check=False)
        sondes.append(Sonde("ffmpeg", True, version.stdout.splitlines()[0][:80], "extra"))
    except (RuntimeError, OSError, IndexError) as exc:
        sondes.append(Sonde("ffmpeg", False, str(exc), "extra"))
    for module, extra in (("cascadio", "[step] — lecture des STEP"), ("rocketpy", "[rocketpy]"),
                          ("bpy", "[blender] — moteur Blender (bpy 5.x : Python 3.13)")):
        present = importlib.util.find_spec(module) is not None
        sondes.append(Sonde(module, present, f"extra {extra}" + ("" if present else " : absent"), "extra"))
    if sys.platform.startswith("linux"):
        sondes += sonder_systeme()
    sondes.append(Sonde("DISPLAY", bool(os.environ.get("DISPLAY")),
                        os.environ.get("DISPLAY", "non défini"), "systeme"))
    fenetres = [sonder_fenetre(nom, env) for nom, env in FENETRES.items()]
    return sondes + fenetres + [sonder_rendu(fenetres)] + sonder_interface()
