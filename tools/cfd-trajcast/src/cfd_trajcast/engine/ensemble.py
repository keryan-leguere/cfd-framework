"""``VueEnsemble`` : la vue d'ensemble seule — schéma SVG du vol entier, ou vidéo complète.

::

    vue = VueEnsemble.depuis_yaml("CONFIG_ENSEMBLE.yaml")
    vue.svg("vol.svg")               # le vol entier, vectoriel, sans moteur 3D (≈ 0,1 s)
    vue.rendre("vol.mp4")            # la vue d'ensemble en vidéo, tout le vol
    vue.image(40.5, "apogee.png")    # une image de cette vidéo

Les réglages de la vue (azimut, élévation, cadrage, agrandissement de la maquette)
sont ceux de la première vue ``mode: ensemble`` du fichier (ou de celle nommée par
``vue=``), à défaut ceux par défaut : n'importe quelle configuration convient, même
sans vue d'ensemble. Le schéma SVG et la vidéo partagent caméra, boîte graduée,
agrandissement et couleurs (``style.ensemble``).

La vidéo est un :class:`~cfd_trajcast.engine.pipeline.Film` à une seule vue : le
format (``video``), l'habillage (``montage``, ``etude``) et la télémétrie du fichier
sont repris, mais **tout le vol** est montré (``video.de``/``video.a`` ignorés, sauf
``de``/``a`` explicites) ; la télémétrie, si le fichier en a une, va dans une bande à
droite. Le moteur est toujours PyVista : c'est lui qui dessine la vue d'ensemble.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core.camera import ParametresEnsemble
from cfd_trajcast.core.disposition import Disposition
from cfd_trajcast.data.configuration import (
    ConfigMontage,
    ConfigStyle,
    ConfigTelemetrie,
    Configuration,
    ConfigVideo,
    Etude,
    charger_configuration,
)
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.engine.pipeline import Film, Progression, ResultatRendu
from cfd_trajcast.engine.schema_ensemble import Schema, schema_ensemble

__all__ = ["NOM_VUE", "VueEnsemble"]

#: Nom de la vue dans la vidéo (et de son étiquette, si ``montage.etiquettes_vues``).
NOM_VUE = "ensemble"


def _montage_vue_unique(montage: ConfigMontage) -> ConfigMontage:
    """Télémétrie en bande à droite sur toute la hauteur : un logo prévu à droite (au-dessus du
    panneau d'une disposition libre) en recouvrirait les valeurs ; il passe du côté gauche, et
    les bandeaux d'événements quittent ce coin s'ils y étaient."""
    logo = montage.logo
    if logo is None or not logo.coin.endswith("droite"):
        return montage
    coin = logo.coin.replace("droite", "gauche")
    bandeaux = montage.coin_bandeaux
    if bandeaux == coin:
        bandeaux = coin.replace("haut", "bas") if coin.startswith("haut") else coin.replace("bas", "haut")
    return replace(montage, logo=replace(logo, coin=coin), coin_bandeaux=bandeaux)


class VueEnsemble:
    """La vue d'ensemble d'un vol, en schéma SVG ou en vidéo."""

    def __init__(
        self,
        trajectoire: Trajectoire,
        maquette: Maquette,
        *,
        parametres: ParametresEnsemble | None = None,
        style: ConfigStyle | None = None,
        etude: Etude | None = None,
        video: ConfigVideo | None = None,
        montage: ConfigMontage | None = None,
        telemetrie: ConfigTelemetrie | None = None,
    ) -> None:
        self.trajectoire = trajectoire
        self.maquette = maquette
        self.parametres = parametres or ParametresEnsemble()
        self.style = style or ConfigStyle()
        self.etude = etude or Etude()
        self.video = video or ConfigVideo()
        # Une seule vue : son étiquette ne dirait rien.
        self.montage = replace(montage, etiquettes_vues=False) if montage is not None else \
            ConfigMontage(titre_debut=0, generique_fin=0, etiquettes_vues=False)
        self.telemetrie = telemetrie

    @classmethod
    def depuis_configuration(cls, cfg: Configuration, *, vue: str | None = None,
                             utiliser_cache: bool = True) -> VueEnsemble:
        """Depuis un fichier déjà chargé ; ``vue`` : nom d'une vue ``mode: ensemble``."""
        ensembles = [(nom, p) for nom, p in cfg.vues if isinstance(p, ParametresEnsemble)]
        if vue is not None:
            choisies = [p for nom, p in ensembles if nom == vue]
            if not choisies:
                raise ValueError(f"vue « {vue} » : pas de vue `mode: ensemble` de ce nom ; vues d'ensemble : "
                                 f"{', '.join(nom for nom, _ in ensembles) or 'aucune'}")
            parametres = choisies[0]
        else:
            parametres = ensembles[0][1] if ensembles else ParametresEnsemble()
        return cls(cfg.trajectoire.charger(utiliser_cache=utiliser_cache),
                   Maquette.depuis_declaration(cfg.maquette), parametres=parametres, style=cfg.style,
                   etude=cfg.etude, video=cfg.video, montage=cfg.montage, telemetrie=cfg.telemetrie)

    @classmethod
    def depuis_yaml(cls, chemin: str | Path, *, vue: str | None = None,
                    utiliser_cache: bool = True) -> VueEnsemble:
        """Charge un fichier de configuration (n'importe lequel : la vue d'ensemble est optionnelle)."""
        return cls.depuis_configuration(charger_configuration(chemin), vue=vue, utiliser_cache=utiliser_cache)

    # -- schéma SVG ------------------------------------------------------------------------
    def schema(self, *, taille: int = 1600, poses: int | Sequence[float | str] | None = None,
               titre: str | None = None, sous_titre: str | None = None, theme: str | None = None) -> Schema:
        """Le schéma SVG en mémoire (voir :func:`~cfd_trajcast.engine.schema_ensemble.schema_ensemble`).

        ``titre``/``sous_titre`` : ceux de l'étude par défaut, ``""`` pour aucun ;
        ``theme`` : ``clair``/``sombre``, par défaut ``style.ensemble``.
        """
        return schema_ensemble(
            self.trajectoire, self.maquette, self.parametres,
            theme=theme or self.style.ensemble_theme, sol_altitude=self.style.sol_altitude,
            taille=taille, poses=poses,
            titre=self.etude.titre if titre is None else titre,
            sous_titre=self.etude.sous_titre if sous_titre is None else sous_titre,
        )

    def svg(self, chemin: str | Path, *, taille: int = 1600, poses: int | Sequence[float | str] | None = None,
            titre: str | None = None, sous_titre: str | None = None, theme: str | None = None) -> Schema:
        """Écrit le schéma SVG du vol entier ; aucun rendu 3D."""
        return self.schema(taille=taille, poses=poses, titre=titre, sous_titre=sous_titre,
                           theme=theme).ecrire(chemin)

    # -- vidéo -------------------------------------------------------------------------------
    def film(self, *, telemetrie: bool | None = None, resolution: tuple[int, int] | None = None,
             duree: float | None = None, vitesse: float | None = None) -> Film:
        """Le :class:`Film` à une vue qui rend la vue d'ensemble.

        ``telemetrie`` : bande de télémétrie à droite (None : si le fichier en configure une).
        ``resolution``, ``duree`` (s de vidéo pour tout le vol) et ``vitesse`` (s de vol par
        s de vidéo) remplacent ceux de ``video`` ; ``duree`` et ``vitesse`` s'excluent.
        """
        avec_telemetrie = self.telemetrie is not None if telemetrie is None else telemetrie
        if avec_telemetrie and self.telemetrie is None:
            config_telemetrie: ConfigTelemetrie | None = ConfigTelemetrie()
        else:
            config_telemetrie = self.telemetrie if avec_telemetrie else None
        video = replace(self.video, de=None, a=None)
        if resolution is not None:
            video = replace(video, resolution=resolution)
        if duree is not None or vitesse is not None:
            video = replace(video, duree=duree, vitesse=vitesse, ralentis=() if duree is not None else video.ralentis)
        disposition = Disposition(type="unique", principale=NOM_VUE,
                                  telemetrie="droite" if avec_telemetrie else "aucune")
        montage = _montage_vue_unique(self.montage) if avec_telemetrie else self.montage
        return Film(self.trajectoire, self.maquette, video=video, vues={NOM_VUE: self.parametres},
                    disposition=disposition, telemetrie=config_telemetrie, montage=montage,
                    etude=self.etude, style=self.style)

    def rendre(self, chemin: str | Path, *, de: float | None = None, a: float | None = None,
               apercu: bool = False, processus: int | None = None, progression: Progression | None = None,
               telemetrie: bool | None = None, resolution: tuple[int, int] | None = None,
               duree: float | None = None, vitesse: float | None = None) -> ResultatRendu:
        """La vidéo MP4 de la vue d'ensemble, tout le vol par défaut (``de``/``a`` pour une partie)."""
        film = self.film(telemetrie=telemetrie, resolution=resolution, duree=duree, vitesse=vitesse)
        return film.rendre(chemin, de=de, a=a, apercu=apercu, processus=processus, progression=progression)

    def image(self, t: float, chemin: str | Path | None = None, *, apercu: bool = False,
              telemetrie: bool | None = None, resolution: tuple[int, int] | None = None) -> NDArray[np.uint8]:
        """L'image de la vidéo à l'instant de vol ``t`` (PNG si ``chemin``)."""
        return self.film(telemetrie=telemetrie, resolution=resolution).image(t, chemin, apercu=apercu)
