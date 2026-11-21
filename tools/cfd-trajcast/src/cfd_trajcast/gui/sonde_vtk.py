"""La vue VTK interactive marche-t-elle ici ? À lancer **dans un sous-processus**.

``python -m cfd_trajcast.gui.sonde_vtk`` ouvre une fenêtre Qt avec un ``QtInteractor``,
rend une sphère et vérifie que l'image n'est pas vide. Un OpenGL cassé fait planter VTK
(signal, pas exception) : seul un sous-processus permet à l'interface, et à
``cfd-trajcast diagnostic``, de le constater sans tomber avec lui. Sous la plateforme
``offscreen`` de Qt il n'y a pas d'OpenGL : l'image est vide et la sonde échoue, ce qui
est la bonne réponse.
"""

from __future__ import annotations

import subprocess
import sys

__all__ = ["PREFIXE", "sonde_vtk", "sonder"]

PREFIXE = "SONDE_VTK:"


def sonder() -> int:
    """Corps de la sonde (dans le sous-processus) ; 0 si l'image rendue n'est pas vide."""
    from cfd_trajcast.gui import application

    app = application()
    import numpy as np
    import pyvista as pv
    from PyQt5.QtWidgets import QMainWindow
    from pyvistaqt import QtInteractor

    fenetre = QMainWindow()
    qi = QtInteractor(fenetre)
    fenetre.setCentralWidget(qi.interactor)
    fenetre.resize(200, 200)
    fenetre.show()
    qi.add_mesh(pv.Sphere(), color="red")
    app.processEvents()
    qi.render()
    image = np.asarray(qi.screenshot(return_img=True))
    pilote = next((ligne.split(":", 1)[1].strip() for ligne in qi.ren_win.ReportCapabilities().splitlines()
                   if "renderer string" in ligne), "?")
    print(PREFIXE, app.platformName(), "|", pilote, "|", "non vide" if image.std() > 1 else "vide", flush=True)
    qi.close()
    return 0 if image.std() > 1 else 1


def sonde_vtk(delai: float = 60.0) -> tuple[bool, str]:
    """Lance la sonde dans un sous-processus : (utilisable, explication)."""
    try:
        r = subprocess.run([sys.executable, "-m", "cfd_trajcast.gui.sonde_vtk"], capture_output=True,
                           text=True, timeout=delai, check=False)
    except subprocess.TimeoutExpired:
        return False, f"pas de réponse en {delai:.0f} s"
    ligne = next((x[len(PREFIXE):].strip() for x in r.stdout.splitlines() if x.startswith(PREFIXE)), "")
    if r.returncode == 0:
        return True, ligne
    erreur = next((x for x in reversed(r.stderr.splitlines()) if x.strip()), "")
    raison = ligne or (f"arrêtée par le signal {-r.returncode}" if r.returncode < 0 else f"code {r.returncode}")
    return False, f"{raison} {erreur[-200:]}".strip()


if __name__ == "__main__":
    sys.exit(sonder())
