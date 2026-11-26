"""``VueVent`` : le vent le long du vol, en figure paper et en vidéo sans rendu 3D.

::

    vue = VueVent.depuis_yaml("CONFIG_GUI.yaml")          # le fichier doit avoir une section `vent`
    vue.figure("vent")                                    # vent.pdf, vent.svg, vent.png
    vue.figure("vent_8", instants=8, sens="depuis")       # 8 instants, convention météo
    vue.animer("vent_anime.mp4")                          # rose + profil animés, tout le vol

Une rose Nord/Est par instant (flèche = vent horizontal) sous le profil vertical du
vol (altitude en fonction du temps) ; en vidéo, une rose et le profil qui avancent
ensemble. Figure et vidéo demandent cfd-plot, comme la figure de la vue d'ensemble.
Conventions : :mod:`cfd_trajcast.engine.figure_vent` et ``00_DOC/10_FIGURES_VENT.md``.

La vidéo reprend la section ``video`` du fichier (cadence, résolution, vitesse ou
durée, ralentis), sur **tout le vol** par défaut, comme ``VueEnsemble.animer``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from cfd_trajcast.core.temps import instants_de_vol
from cfd_trajcast.data.configuration import Configuration, ConfigVideo, Etude, charger_configuration
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.data.vent import DeclarationVent, ErreurVent
from cfd_trajcast.engine.figure_ensemble import FORMATS_FIGURE
from cfd_trajcast.engine.figure_vent import AnimationVent, FigureVent, animation_vent, figure_vent
from cfd_trajcast.engine.pipeline import Progression, video_apercu

__all__ = ["VueVent"]


class VueVent:
    """Le vent d'un vol : figure paper (roses + profil) et vidéo sans rendu."""

    def __init__(self, trajectoire: Trajectoire, vent: DeclarationVent, *, etude: Etude | None = None,
                 video: ConfigVideo | None = None) -> None:
        self.trajectoire = trajectoire
        self.vent = vent
        self.etude = etude or Etude()
        self.video = video or ConfigVideo()

    @classmethod
    def depuis_configuration(cls, cfg: Configuration, *, utiliser_cache: bool = True) -> VueVent:
        """Depuis un fichier déjà chargé ; il doit déclarer une section ``vent``."""
        if cfg.vent is None:
            raise ErreurVent("pas de section `vent` dans ce fichier : déclarer les colonnes du vent "
                             "(00_DOC/02_CONFIGURATION.md § 12)")
        return cls(cfg.trajectoire.charger(utiliser_cache=utiliser_cache), cfg.vent, etude=cfg.etude,
                   video=cfg.video)

    @classmethod
    def depuis_yaml(cls, chemin: str | Path, *, utiliser_cache: bool = True) -> VueVent:
        return cls.depuis_configuration(charger_configuration(chemin), utiliser_cache=utiliser_cache)

    def figure(self, chemin: str | Path, *, instants: int | Sequence[float | str] | None = None,
               sens: str = "vers", formats: Sequence[str] = FORMATS_FIGURE, largeur_cm: float = 16.0,
               titre: str = "") -> FigureVent:
        """Figure paper : ``chemin``.pdf/.svg/.png. Sans titre par défaut (il va dans la légende
        de l'article, proposée dans ``FigureVent.legende``).

        ``instants`` : un nombre (répartis sur le vol) ou des instants (s) et noms d'événements ;
        défaut : aux événements. ``sens`` : ``vers`` (où va l'air) ou ``depuis`` (météo).
        """
        return figure_vent(self.trajectoire, self.vent, chemin, instants=instants, sens=sens, formats=formats,
                           largeur_cm=largeur_cm, titre=titre)

    def animer(self, chemin: str | Path, *, de: float | None = None, a: float | None = None, sens: str = "vers",
               apercu: bool = False, duree: float | None = None, vitesse: float | None = None,
               resolution: tuple[int, int] | None = None, titre: str | None = None,
               progression: Progression | None = None) -> AnimationVent:
        """Rose et profil animés en MP4, sans rendu 3D ; tout le vol par défaut.

        ``titre`` : celui de l'étude par défaut, ``""`` pour aucun.
        """
        video = replace(self.video, de=None, a=None)
        if resolution is not None:
            video = replace(video, resolution=resolution)
        if duree is not None or vitesse is not None:
            video = replace(video, duree=duree, vitesse=vitesse, ralentis=() if duree is not None else video.ralentis)
        if apercu:
            video = video_apercu(video)
        traj = self.trajectoire
        t0 = float(traj.t[0]) if de is None else float(de)
        t1 = float(traj.t[-1]) if a is None else float(a)
        if not traj.t[0] <= t0 < t1 <= traj.t[-1]:
            raise ValueError(f"intervalle [{t0:g} ; {t1:g}] s : croissant et dans le vol "
                             f"[{traj.t[0]:g} ; {traj.t[-1]:g}] s")
        base = (t1 - t0) / video.duree if video.duree is not None else (video.vitesse or 1.0)
        instants = instants_de_vol(t0, t1, video.ips, base, video.ralentis, video.transition_ralenti)
        return animation_vent(traj, self.vent, chemin, instants, sens=sens, ips=video.ips,
                              resolution=video.resolution, titre=self.etude.titre if titre is None else titre,
                              crf=video.crf, progression=progression)
