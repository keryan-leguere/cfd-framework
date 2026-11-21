"""Vidéo de la vue d'ensemble pour l'interface, **dans un sous-processus** — sans Qt.

``python -m cfd_trajcast.gui.tache_video '{"config": …, "sortie": …, "mode": "sans_rendu", …}'``

L'interface lance cette tâche par ``QProcess`` plutôt que dans un fil : le rendu VTK
hors écran à côté d'une vue OpenGL interactive, ou le style Matplotlib changé pendant
que l'interface dessine, sont des sources de plantage et de scintillement ; un
sous-processus isole tout, et s'annule en le tuant. La progression est écrite sur la
sortie standard, une ligne ``PROGRES fait total`` par image ; la fin, ``FINI chemin``
ou ``ERREUR message``.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

__all__ = ["MODES", "TacheVideo", "executer"]

MODES = ("sans_rendu", "rendu")


@dataclass(frozen=True)
class TacheVideo:
    """Ce que demande la boîte de dialogue d'export."""

    config: str
    sortie: str
    mode: str = "sans_rendu"
    de: float | None = None
    a: float | None = None
    resolution: tuple[int, int] | None = None
    duree: float | None = None
    repere: str | None = None

    def vers_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def depuis_json(cls, texte: str) -> TacheVideo:
        d: dict[str, Any] = json.loads(texte)
        if d.get("resolution") is not None:
            d["resolution"] = tuple(d["resolution"])
        return cls(**d)


def executer(tache: TacheVideo) -> Path:
    """Fait la vidéo ; écrit la progression sur la sortie standard."""
    from dataclasses import replace

    from cfd_trajcast.engine.ensemble import VueEnsemble

    if tache.mode not in MODES:
        raise ValueError(f"mode : {', '.join(MODES)}")
    vue = VueEnsemble.depuis_yaml(tache.config)
    if tache.repere is not None:
        vue.parametres = replace(vue.parametres, repere=tache.repere)

    def progression(fait: int, total: int) -> None:
        print(f"PROGRES {fait} {total}", flush=True)

    if tache.mode == "sans_rendu":
        return vue.animer(tache.sortie, de=tache.de, a=tache.a, resolution=tache.resolution, duree=tache.duree,
                          progression=progression).chemin
    return vue.rendre(tache.sortie, de=tache.de, a=tache.a, resolution=tache.resolution, duree=tache.duree,
                      progression=progression, telemetrie=False).chemin


def main(argv: list[str] | None = None) -> int:
    # Aucun Qt dans ce sous-processus : sans Agg, Matplotlib prendrait le backend Qt (PyQt5 est
    # installé avec l'interface) et croiserait le Qt du système (cf. gui/_qt.py).
    os.environ.setdefault("MPLBACKEND", "Agg")
    args = sys.argv[1:] if argv is None else argv
    try:
        chemin = executer(TacheVideo.depuis_json(args[0]))
    except Exception as exc:
        print(f"ERREUR {type(exc).__name__} : {exc}", flush=True)
        return 1
    print(f"FINI {chemin}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
