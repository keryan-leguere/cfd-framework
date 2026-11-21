"""Le fichier de configuration YAML → objets gelés. Toute clé inconnue est refusée.

Sections : ``etude``, ``trajectoire``, ``maquette``, ``video`` (ralentis compris),
``vues`` (poursuite, sol, embarquee, ensemble, orbite, images_cles),
``disposition``, ``sequence``, ``telemetrie``, ``montage``, ``style``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from cfd_trajcast.core.camera import (
    Cle,
    ParametresEmbarquee,
    ParametresEnsemble,
    ParametresImagesCles,
    ParametresOrbite,
    ParametresPoursuite,
    ParametresSol,
    ParametresVue,
)
from cfd_trajcast.core.disposition import COINS, TELEMETRIE, Disposition, Incrustation, vues_citees
from cfd_trajcast.core.temps import Ralenti
from cfd_trajcast.data.cdg import DeclarationCdg
from cfd_trajcast.data.maquette import DeclarationMaquette, ErreurMaquette
from cfd_trajcast.data.rocketpy_ import (
    DECLARATION_ROCKETPY,
    GRANDEURS_ROCKETPY,
    trajectoire_depuis_script,
)
from cfd_trajcast.data.trajectoire import (
    DeclarationAttitude,
    DeclarationTrajectoire,
    ErreurTrajectoire,
    Evenement,
    Trajectoire,
)
from cfd_trajcast.data.vent import DeclarationVent

__all__ = [
    "CALCULEES",
    "GRANDEURS",
    "GRANDEURS_MAX",
    "JETS",
    "MOTEURS",
    "PRESETS_STYLE",
    "PRESETS_X264",
    "RENDUS_BLENDER",
    "RESOLUTIONS",
    "SECTIONS_A_VENIR",
    "SOLS",
    "TRANSITIONS",
    "UNITES_TELEMETRIE",
    "ConfigMontage",
    "ConfigMoteur",
    "ConfigPropulsion",
    "ConfigStyle",
    "ConfigTelemetrie",
    "ConfigTrajectoire",
    "ConfigVideo",
    "Configuration",
    "ErreurConfiguration",
    "EtapeSequence",
    "Etude",
    "Flamme",
    "Fumee",
    "Grandeur",
    "Jet",
    "Logo",
    "PhasePropulsion",
    "charger_configuration",
    "configuration_depuis_dict",
    "grandeur_calculee",
]

#: Sections prévues par le plan pour les jalons suivants.
SECTIONS_A_VENIR: tuple[str, ...] = ()
#: Résolutions nommées (largeur, hauteur).
RESOLUTIONS = {"540p": (960, 540), "720p": (1280, 720), "1080p": (1920, 1080),
               "1440p": (2560, 1440), "4K": (3840, 2160)}
PRESETS_X264 = ("ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow",
                "slower", "veryslow")
#: Modes de vue prévus ; ``orbite`` et ``images_cles`` arrivent au jalon J4.
MODES_VUE = ("poursuite", "sol", "embarquee", "ensemble", "orbite", "images_cles")
#: Types de sol : quadrillage seul, terrain procédural, damier, aplat, ou rien.
SOLS = ("grille", "terrain", "damier", "uni", "aucun")
ANTICRENELAGES = ("aucun", "fxaa", "ssaa")


TRANSITIONS = ("coupe", "fondu")
#: Où poser le titre : en haut par défaut, pour ne pas cacher la fusée (au centre).
POSITIONS_TITRE = ("haut", "centre", "bas")
#: Grandeurs **calculées** du panneau de télémétrie : unités d'affichage permises
#: → (facteur depuis le SI, texte affiché, décimales). La première unité est le défaut.
CALCULEES: dict[str, tuple[str, dict[str, tuple[float, str, int | None]]]] = {
    "altitude": ("Altitude", {"m": (1.0, "m", 0), "km": (1e-3, "km", 2), "ft": (1 / 0.3048, "ft", 0)}),
    "vitesse": ("Vitesse", {"m/s": (1.0, "m/s", None), "km/h": (3.6, "km/h", 0), "kt": (3600 / 1852, "kt", 0)}),
    "mach": ("Mach", {"": (1.0, "", 2)}),
    "acceleration": ("Accélération", {"g": (1 / 9.80665, "g", 1), "m/s2": (1.0, "m/s²", 1)}),
    "incidence_totale": ("Incidence totale", {"deg": (180 / 3.141592653589793, "°", 1), "rad": (1.0, "rad", 3)}),
    "facteur_de_charge": ("Facteur de charge", {"g": (1 / 9.80665, "g", 1), "m/s2": (1.0, "m/s²", 1)}),
    "cap": ("Cap", {"deg": (180 / 3.141592653589793, "°", 0), "rad": (1.0, "rad", 2)}),
    "pente": ("Pente", {"deg": (180 / 3.141592653589793, "°", 1), "rad": (1.0, "rad", 3)}),
    "roulis": ("Roulis", {"deg": (180 / 3.141592653589793, "°", 0), "rad": (1.0, "rad", 2)}),
    "tangage": ("Tangage", {"deg": (180 / 3.141592653589793, "°", 1), "rad": (1.0, "rad", 3)}),
    "lacet": ("Lacet", {"deg": (180 / 3.141592653589793, "°", 0), "rad": (1.0, "rad", 2)}),
}
#: Grandeurs du panneau par défaut.
GRANDEURS = ("altitude", "vitesse", "mach", "acceleration")
#: Unités permises des grandeurs calculées (compatibilité de ``telemetrie.unites``).
UNITES_TELEMETRIE = {g: tuple(u for u in unites if u) for g, (_, unites) in CALCULEES.items() if g != "mach"}
#: Lignes du panneau au plus (au-delà, elles deviennent illisibles).
GRANDEURS_MAX = 8


class ErreurConfiguration(ValueError):
    """Le fichier de configuration est mal formé ; le message nomme la clé."""


@dataclass(frozen=True)
class Etude:
    """Titres de la vidéo."""

    titre: str = ""
    sous_titre: str = ""


@dataclass(frozen=True)
class ConfigTrajectoire:
    """Où lire la trajectoire, et comment.

    ``source="csv"`` : ``fichier`` est le CSV, lu selon ``declaration``.
    ``source="rocketpy"`` : ``fichier`` est le script, ``fonction()`` y rend un
    ``rocketpy.Flight`` ; ``declaration`` est celle, fixe, de l'adaptateur.
    """

    fichier: Path
    declaration: DeclarationTrajectoire
    evenements: tuple[Evenement, ...] = ()
    source: str = "csv"
    fonction: str = "simuler"
    grandeurs: tuple[str, ...] = GRANDEURS_ROCKETPY
    cache: bool = True

    def charger(self, *, utiliser_cache: bool = True) -> Trajectoire:
        """La trajectoire (simulation RocketPy exécutée ou relue du cache)."""
        if self.source == "rocketpy":
            return trajectoire_depuis_script(self.fichier, self.fonction, grandeurs=self.grandeurs,
                                             evenements=self.evenements,
                                             utiliser_cache=self.cache and utiliser_cache)
        return Trajectoire.depuis_csv(self.fichier, declaration=self.declaration, evenements=self.evenements)


MOTEURS = ("pyvista", "blender")
RENDUS_BLENDER = ("eevee", "cycles")


@dataclass(frozen=True)
class ConfigMoteur:
    """Moteur 3D : ``pyvista`` (rapide, défaut) ou ``blender`` (bpy : EEVEE ou Cycles).

    ``echantillons`` : échantillons par pixel de Blender (anticrénelage, bruit de Cycles).
    """

    type: str = "pyvista"
    rendu: str = "eevee"
    echantillons: int = 16

    def __post_init__(self) -> None:
        if self.type not in MOTEURS:
            raise ErreurConfiguration(f"moteur.type : {', '.join(MOTEURS)}")
        if self.rendu not in RENDUS_BLENDER:
            raise ErreurConfiguration(f"moteur.rendu : {', '.join(RENDUS_BLENDER)}")
        if not 1 <= self.echantillons <= 4096:
            raise ErreurConfiguration("moteur.echantillons : entre 1 et 4096")


@dataclass(frozen=True)
class ConfigVideo:
    """Format de la vidéo. ``vitesse`` = secondes de vol par seconde de vidéo ;
    ``duree`` (s de vidéo) la fixe à la place. Les deux s'excluent. ``de``/``a`` :
    partie du vol montrée (s de vol ou nom d'événement ; ``None`` = début / fin du vol)."""

    resolution: tuple[int, int] = (1920, 1080)
    ips: float = 30.0
    vitesse: float | None = None
    duree: float | None = None
    crf: int = 18
    preset: str = "medium"
    ralentis: tuple[Ralenti, ...] = ()
    transition_ralenti: float = 0.5
    de: float | str | None = None
    a: float | str | None = None

    def __post_init__(self) -> None:
        if self.ralentis and self.duree is not None:
            raise ErreurConfiguration("video.ralentis et video.duree s'excluent : donner `vitesse`")
        if self.transition_ralenti < 0:
            raise ErreurConfiguration("video.transition_ralenti : une durée positive ou nulle (s de vol)")
        largeur, hauteur = self.resolution
        if largeur < 16 or hauteur < 16 or largeur % 2 or hauteur % 2:
            raise ErreurConfiguration(
                f"video.resolution {largeur}×{hauteur} : dimensions paires d'au moins 16 px "
                "(H.264 en yuv420p l'exige)"
            )
        if not 1 <= self.ips <= 240:
            raise ErreurConfiguration("video.ips : entre 1 et 240 images par seconde")
        if self.vitesse is not None and self.duree is not None:
            raise ErreurConfiguration("video.vitesse et video.duree s'excluent : l'une fixe l'autre")
        for nom in ("vitesse", "duree"):
            valeur = getattr(self, nom)
            if valeur is not None and not valeur > 0:
                raise ErreurConfiguration(f"video.{nom} doit être positive")
        if not 0 <= self.crf <= 51:
            raise ErreurConfiguration("video.codec.crf : entre 0 (sans perte) et 51")
        if self.preset not in PRESETS_X264:
            raise ErreurConfiguration(f"video.codec.preset : {', '.join(PRESETS_X264)}")


@dataclass(frozen=True)
class EtapeSequence:
    """À partir de l'instant de vol ``de`` (s, ou nom d'un événement), afficher ``disposition``."""

    de: float | str
    disposition: Disposition
    transition: str = "coupe"


@dataclass(frozen=True)
class Grandeur:
    """Une ligne du panneau de télémétrie.

    ``colonne`` None : grandeur calculée (``cle`` ∈ :data:`CALCULEES`). Sinon la valeur
    est lue dans cette colonne de la trajectoire, multipliée par ``facteur``, et
    ``unite`` n'est qu'un texte affiché. ``decimales`` None : selon l'ordre de grandeur.
    """

    cle: str
    libelle: str
    unite: str = ""
    facteur: float = 1.0
    colonne: str | None = None
    decimales: int | None = None
    couleur: str | None = None
    #: Bornes fixes de l'axe (unité d'affichage) ; None = ajustées aux données.
    plage: tuple[float, float] | None = None
    #: Étendue minimale de l'axe : une grandeur nulle par construction ne doit pas faire
    #: zoomer l'axe sur son bruit numérique.
    etendue_min: float = 0.0


#: Étendue minimale d'axe des grandeurs calculées (unité d'affichage).
_ETENDUE_MIN = {"incidence_totale": {"deg": 5.0, "rad": 0.1}}


def grandeur_calculee(nom: str, unite: str | None = None, colonne: str | None = None) -> Grandeur:
    """Une grandeur calculée (ou lue en SI dans ``colonne``), dans l'unité demandée."""
    libelle, unites = CALCULEES[nom]
    u = next(iter(unites)) if unite is None else unite
    if u not in unites:
        raise ErreurConfiguration(f"telemetrie : unité {u!r} de {nom} ; permises : {', '.join(x for x in unites if x)}")
    facteur, texte, decimales = unites[u]
    return Grandeur(cle=nom, libelle=libelle, unite=texte, facteur=facteur, colonne=colonne,
                    decimales=decimales, etendue_min=_ETENDUE_MIN.get(nom, {}).get(u, 0.0))


@dataclass(frozen=True)
class ConfigTelemetrie:
    """Panneau de télémétrie : une :class:`Grandeur` par ligne, dans l'ordre."""

    grandeurs: tuple[Grandeur, ...] = tuple(grandeur_calculee(g) for g in GRANDEURS)


@dataclass(frozen=True)
class Logo:
    """Logo incrusté ; ``hauteur`` en fraction de la hauteur d'image."""

    fichier: Path
    coin: str = "haut_droite"
    hauteur: float = 0.08


@dataclass(frozen=True)
class ConfigMontage:
    """Habillage : durées en secondes de vidéo."""

    logo: Logo | None = None
    titre_debut: float = 3.0
    generique_fin: float = 3.0
    bandeaux_evenements: bool = True
    duree_bandeau: float = 3.0
    fondu: float = 0.5
    etiquettes_vues: bool = True
    position_titre: str = "haut"
    coin_bandeaux: str = "bas_gauche"


@dataclass(frozen=True)
class ConfigStyle:
    """Apparence de la scène 3D (ciel, sol, traînée, lumière, fusée).

    Couleurs ``"#rrggbb"`` ; ``soleil`` = (azimut depuis le Nord, élévation) en
    degrés, None = éclairage par défaut de VTK (lumières liées à la caméra).
    """

    preset: str = "sobre"
    ciel_haut: str = "#dfe6ee"
    ciel_bas: str = "#dfe6ee"
    sol: str = "grille"
    sol_couleur: str = "#9aa7b4"
    sol_maille: float | None = None
    #: Cote du sol dans le repère de la trajectoire (m) : 0 si l'origine est au sol.
    sol_altitude: float = 0.0
    trace: bool = True
    #: Anticrénelage : aucun | ssaa (sur-échantillonnage). « fxaa » est accepté comme synonyme :
    #: sous EGL, VTK ne sait pas faire de FXAA et passe de toute façon en SSAA.
    antialiasing: str = "aucun"
    trainee: bool = False
    trainee_duree: float = 6.0
    trainee_couleur: str = "#f2f2f2"
    trainee_rayon: float | None = None
    trainee_croissance: float = 0.6
    #: Fin d'émission de la traînée : instant de vol (s) ou nom d'un événement.
    trainee_jusqu_a: float | str | None = None
    soleil: tuple[float, float] | None = None
    intensite: float = 1.0
    ambiance: float = 0.35
    fusee_couleur: str = "#d0d0d0"
    fusee_metal: float = 0.0
    fusee_rugosite: float = 0.5
    #: Étoiles peintes derrière la scène (0 : aucune ; 1 : ciel de campagne sans lune).
    ciel_etoiles: float = 0.0
    #: Halo autour des zones très lumineuses (flammes) ; 0 : aucun.
    lueur: float = 0.0
    #: Couleur de la lumière principale (soleil, lune).
    lumiere_couleur: str = "#ffffff"
    #: Lumière émise par les flammes sur la maquette, la fumée et le sol ; 0 : aucune.
    lumiere_jets: float = 0.0
    #: Vue d'ensemble : clair (fond blanc) ou sombre.
    ensemble_theme: str = "clair"

    def __post_init__(self) -> None:
        if self.sol not in SOLS:
            raise ErreurConfiguration(f"style.sol.type : {', '.join(SOLS)}")
        if self.antialiasing not in ANTICRENELAGES:
            raise ErreurConfiguration(f"style.antialiasing : {', '.join(ANTICRENELAGES)}")
        if self.ensemble_theme not in ("clair", "sombre"):
            raise ErreurConfiguration("style.ensemble : clair ou sombre")
        for nom in ("ciel_etoiles", "lueur", "lumiere_jets"):
            if getattr(self, nom) < 0:
                raise ErreurConfiguration(f"style : {nom} doit être positif ou nul")
        for nom in ("ciel_haut", "ciel_bas", "sol_couleur", "trainee_couleur", "fusee_couleur", "lumiere_couleur"):
            v = getattr(self, nom)
            if not (isinstance(v, str) and len(v) == 7 and v.startswith("#")):
                raise ErreurConfiguration(f"style : couleur {nom} {v!r}, attendu \"#rrggbb\"")
        for nom in ("fusee_metal", "fusee_rugosite"):
            if not 0 <= getattr(self, nom) <= 1:
                raise ErreurConfiguration(f"style.fusee : {nom.split('_')[1]} entre 0 et 1")
        if self.trainee_duree <= 0 or self.trainee_croissance < 0:
            raise ErreurConfiguration("style.trainee : duree > 0, croissance ≥ 0")
        if self.sol_maille is not None and not self.sol_maille > 0:
            raise ErreurConfiguration("style.sol.maille : une longueur positive (m)")


#: Préréglages ; les clés de la section ``style`` les surchargent.
PRESETS_STYLE: dict[str, ConfigStyle] = {
    # Le rendu des jalons J2–J3 : fond uni, quadrillage, pas de traînée, lumières VTK.
    "sobre": ConfigStyle(preset="sobre"),
    "conference": ConfigStyle(
        preset="conference", ciel_haut="#1d4f91", ciel_bas="#b4d2ec", sol="terrain",
        sol_couleur="#5d7a3e", trace=False, trainee=False, trainee_duree=6.0,
        trainee_couleur="#f4f4f4", soleil=(135.0, 35.0), intensite=0.8, ambiance=0.25,
        fusee_couleur="#c9ced5", fusee_metal=0.0, fusee_rugosite=0.45, antialiasing="ssaa",
    ),
    # Tir de nuit : ciel étoilé, clair de lune bleuté, terrain sombre ; les flammes éclairent
    # la maquette, la fumée et le sol, et rayonnent (lueur).
    "nuit": ConfigStyle(
        preset="nuit", ciel_haut="#01030a", ciel_bas="#18233d", ciel_etoiles=1.0, sol="terrain",
        sol_couleur="#26331f", sol_maille=6000.0, trace=False, soleil=(210.0, 30.0), intensite=0.45,
        lumiere_couleur="#a9bcff", ambiance=0.10, fusee_couleur="#c9ced5", fusee_rugosite=0.45,
        antialiasing="ssaa", lueur=0.9, lumiere_jets=2.5, ensemble_theme="sombre",
    ),
}


@dataclass(frozen=True)
class Flamme:
    """Flamme attachée à une tuyère : surface de révolution qui s'évase puis se referme.

    ``longueur`` et les rayons sont en **rayons de tuyère** ; ``evasement`` est le
    demi-angle d'ouverture (°). ``couleurs`` va de la sortie de tuyère au bout ;
    ``coeur`` est la longueur relative du cœur blanc (0 : pas de cœur) ;
    ``diamants`` : nombre de disques de Mach ; ``scintillement`` : amplitude
    relative des variations de longueur.
    """

    longueur: float = 8.0
    evasement: float = 12.0
    couleurs: tuple[str, ...] = ("#fff6d5", "#ffb347", "#ff5a1f")
    opacite: float = 0.85
    coeur: float = 0.45
    diamants: int = 0
    scintillement: float = 0.08


@dataclass(frozen=True)
class Fumee:
    """Fumée émise par une tuyère, figée dans l'air : elle s'élargit, dérive et pâlit avec l'âge.

    Rayon : ``rayon`` (en rayons de tuyère) au départ, + ``evasement`` (demi-angle, °)
    sur la distance parcourue derrière la tuyère — le panache s'ouvre en cône —,
    + ``expansion`` m/s d'âge. ``turbulence`` : dérive latérale (m/s d'âge). Couleur de
    ``couleur_debut`` à ``couleur_fin`` sur ``duree`` s, opacité nulle au-delà ; la
    fumée apparaît derrière la flamme, pas par-dessus.
    """

    couleur_debut: str = "#fbf7f0"
    couleur_fin: str = "#a7abb0"
    opacite: float = 0.8
    duree: float = 6.0
    rayon: float = 1.0
    evasement: float = 6.0
    expansion: float = 1.5
    turbulence: float = 0.6


@dataclass(frozen=True)
class Jet:
    """Ce qui sort d'une tuyère pendant une phase : flamme, fumée, l'une, l'autre ou rien."""

    flamme: Flamme | None = None
    fumee: Fumee | None = None


#: Jets préréglés. Une phase peut partir de l'un d'eux et en surcharger des clés.
JETS: dict[str, Jet] = {
    "fusee_poudre": Jet(
        Flamme(longueur=20.0, evasement=16.0, couleurs=("#fff8e0", "#ffc04d", "#ff6a1a", "#b8301a"),
               opacite=0.9, coeur=0.45, scintillement=0.10),
        Fumee(couleur_debut="#fff1d6", couleur_fin="#b4b8bd", opacite=0.85, duree=8.0, rayon=1.5,
              evasement=7.0, expansion=2.0, turbulence=0.8)),
    "fusee_liquide": Jet(
        Flamme(longueur=16.0, evasement=9.0, couleurs=("#ffffff", "#bcd7ff", "#6f8cff", "#ff9a4d"),
               opacite=0.8, coeur=0.35, diamants=5, scintillement=0.05),
        Fumee(couleur_debut="#ffffff", couleur_fin="#d9dde2", opacite=0.35, duree=4.0, rayon=1.2,
              evasement=4.0, expansion=1.0, turbulence=0.3)),
    "postcombustion": Jet(
        Flamme(longueur=9.0, evasement=8.0, couleurs=("#ffffff", "#9fc4ff", "#ff9d3c", "#ff5c2a"),
               opacite=0.85, coeur=0.3, diamants=5, scintillement=0.06)),
    "reacteur": Jet(
        Flamme(longueur=2.5, evasement=6.0, couleurs=("#ffe9c4", "#ffb070", "#ff7a3d"),
               opacite=0.35, coeur=0.0, scintillement=0.04)),
    "panne": Jet(
        Flamme(longueur=4.0, evasement=25.0, couleurs=("#fff1b0", "#ff8c1a", "#d9361a"),
               opacite=0.8, coeur=0.0, scintillement=0.35),
        Fumee(couleur_debut="#4a3a30", couleur_fin="#77736f", opacite=0.75, duree=12.0, rayon=1.2,
              evasement=8.0, expansion=2.5, turbulence=2.0)),
    "fumee": Jet(None, Fumee()),
    "aucun": Jet(None, None),
}


@dataclass(frozen=True)
class PhasePropulsion:
    """Le jet ``jet`` de ``de`` à ``a`` (instants de vol en s, ou noms d'événements ; ``a`` None :
    jusqu'à la fin)."""

    de: float | str
    a: float | str | None
    jet: Jet
    nom: str = ""


@dataclass(frozen=True)
class ConfigPropulsion:
    """Tuyères (FRD, m, depuis le point de référence ; None = centre du culot), leur rayon
    (None = 4 % de la taille de la maquette), phases, et durée des fondus entre phases (s de vol)."""

    tuyeres: tuple[tuple[float, float, float], ...] | None = None
    rayon_tuyere: float | None = None
    phases: tuple[PhasePropulsion, ...] = ()
    fondu: float = 0.3


@dataclass(frozen=True)
class Configuration:
    """Le fichier entier."""

    chemin: Path | None
    etude: Etude
    trajectoire: ConfigTrajectoire
    maquette: DeclarationMaquette
    video: ConfigVideo = ConfigVideo()
    vues: tuple[tuple[str, ParametresVue], ...] = (("poursuite", ParametresPoursuite()),)
    disposition: Disposition = Disposition(type="unique", principale="poursuite")  # noqa: RUF009 (gelée)
    sequence: tuple[EtapeSequence, ...] = ()
    telemetrie: ConfigTelemetrie | None = None
    montage: ConfigMontage = ConfigMontage()
    style: ConfigStyle = ConfigStyle()
    propulsion: ConfigPropulsion | None = None
    moteur: ConfigMoteur = ConfigMoteur()
    #: Vent (colonnes VN, VE, VZ de la trajectoire) et CDG variable : facultatifs.
    vent: DeclarationVent | None = None
    cdg: DeclarationCdg | None = None
    a_venir: tuple[str, ...] = ()
    remarques: tuple[str, ...] = ()


def _dict(valeur: Any, ou: str) -> Mapping[str, Any]:
    if not isinstance(valeur, Mapping):
        raise ErreurConfiguration(f"{ou} : un dictionnaire est attendu, reçu {type(valeur).__name__}")
    return valeur


def _cles(
    d: Mapping[str, Any], ou: str, permises: set[str], obligatoires: AbstractSet[str] = frozenset()
) -> None:
    inconnues = set(d) - permises
    if inconnues:
        raise ErreurConfiguration(
            f"{ou} : clé(s) inconnue(s) {', '.join(sorted(map(str, inconnues)))} ; "
            f"clés permises : {', '.join(sorted(permises))}"
        )
    manquantes = obligatoires - set(d)
    if manquantes:
        raise ErreurConfiguration(f"{ou} : clé(s) obligatoire(s) manquante(s) : {', '.join(sorted(manquantes))}")


def _chemin(valeur: Any, base: Path, ou: str) -> Path:
    if not isinstance(valeur, str) or not valeur:
        raise ErreurConfiguration(f"{ou} : un chemin de fichier est attendu")
    p = Path(valeur).expanduser()
    return p if p.is_absolute() else base / p


def _evenements_fichier(chemin: Path, ou: str) -> list[dict[str, Any]]:
    """Événements d'un CSV ``t,nom`` (lignes ``#`` ignorées) — typiquement exporté par la simulation."""
    import csv

    if not chemin.is_file():
        raise ErreurConfiguration(f"{ou} : fichier introuvable : {chemin}")
    with open(chemin, encoding="utf-8") as f:
        lignes = [ligne for ligne in f if ligne.strip() and not ligne.lstrip().startswith("#")]
    lecteur = csv.DictReader(lignes)
    if lecteur.fieldnames is None or not {"t", "nom"} <= set(lecteur.fieldnames):
        raise ErreurConfiguration(f"{ou} : {chemin.name} doit avoir les colonnes t et nom")
    try:
        return [{"t": float(r["t"]), "nom": r["nom"]} for r in lecteur]
    except ValueError as exc:
        raise ErreurConfiguration(f"{ou} : {chemin.name} : {exc}") from None


def _attitude(d: Mapping[str, Any]) -> DeclarationAttitude:
    ou = "trajectoire.attitude"
    _cles(d, ou, {"type", "colonnes", "ordre", "sens", "sequence", "corps"}, {"type"})
    champs = dict(d)
    if "colonnes" in champs:
        if not isinstance(champs["colonnes"], list):
            raise ErreurConfiguration(f"{ou}.colonnes : une liste de noms est attendue")
        champs["colonnes"] = tuple(str(c) for c in champs["colonnes"])
    return DeclarationAttitude(**champs)


def _evenements_declares(d: Mapping[str, Any], base: Path, ou: str) -> tuple[Evenement, ...]:
    evenements = []
    brut = d.get("evenements", []) or []
    if isinstance(brut, str):
        brut = _evenements_fichier(_chemin(brut, base, f"{ou}.evenements"), f"{ou}.evenements")
    if not isinstance(brut, list):
        raise ErreurConfiguration(f"{ou}.evenements : une liste, ou un fichier CSV (colonnes t, nom)")
    for i, e in enumerate(brut):
        ev = _dict(e, f"{ou}.evenements[{i}]")
        _cles(ev, f"{ou}.evenements[{i}]", {"t", "nom"}, {"t", "nom"})
        evenements.append(Evenement(t=float(ev["t"]), nom=str(ev["nom"])))
    return tuple(evenements)


def _trajectoire_rocketpy(d: Mapping[str, Any], base: Path) -> ConfigTrajectoire:
    ou = "trajectoire"
    _cles(d, ou, {"source", "script", "fonction", "grandeurs", "cache", "evenements"}, {"script"})
    grandeurs = d.get("grandeurs", list(GRANDEURS_ROCKETPY))
    if not isinstance(grandeurs, list) or not all(isinstance(g, str) for g in grandeurs):
        raise ErreurConfiguration(f"{ou}.grandeurs : une liste de noms de grandeurs de rocketpy.Flight")
    cache = d.get("cache", True)
    if not isinstance(cache, bool):
        raise ErreurConfiguration(f"{ou}.cache : true ou false")
    return ConfigTrajectoire(
        fichier=_chemin(d["script"], base, f"{ou}.script"),
        declaration=DECLARATION_ROCKETPY,
        evenements=_evenements_declares(d, base, ou),
        source="rocketpy",
        fonction=str(d.get("fonction", "simuler")),
        grandeurs=tuple(grandeurs),
        cache=cache,
    )


def _trajectoire(d: Mapping[str, Any], base: Path) -> ConfigTrajectoire:
    ou = "trajectoire"
    source = d.get("source", "csv")
    if source == "rocketpy":
        for cle in ("repere", "attitude", "unites", "colonnes", "fichier"):
            if cle in d:
                raise ErreurConfiguration(
                    f"{ou}.{cle} : inutile avec source: rocketpy — RocketPy fixe ses conventions "
                    "(ENU depuis la rampe, quaternion corps → inertiel) ; donner `script`"
                )
        return _trajectoire_rocketpy(d, base)
    if source != "csv":
        raise ErreurConfiguration(f"{ou}.source : {source!r} inconnue ; csv ou rocketpy")
    _cles(d, ou, {"source", "fichier", "repere", "unites", "colonnes", "attitude", "evenements"},
          {"fichier", "repere"})
    if "attitude" not in d:
        raise ErreurConfiguration(
            f"{ou}.attitude manquante : déclarer type: quaternion ou type: euler — "
            "l'attitude n'est jamais déduite de la vitesse"
        )
    unites = _dict(d.get("unites", {}), f"{ou}.unites")
    _cles(unites, f"{ou}.unites", {"temps", "longueur", "angle"})
    colonnes = _dict(d.get("colonnes", {}), f"{ou}.colonnes")
    _cles(colonnes, f"{ou}.colonnes", {"t", "x", "y", "z"})
    evenements = _evenements_declares(d, base, ou)
    declaration = DeclarationTrajectoire(
        repere=str(d["repere"]),
        attitude=_attitude(_dict(d["attitude"], f"{ou}.attitude")),
        unite_temps=str(unites.get("temps", "s")),
        unite_longueur=str(unites.get("longueur", "m")),
        unite_angle=str(unites.get("angle", "deg")),
        **{k: str(v) for k, v in colonnes.items()},
    )
    return ConfigTrajectoire(
        fichier=_chemin(d["fichier"], base, f"{ou}.fichier"),
        declaration=declaration,
        evenements=evenements,
    )


def _maquette(d: Mapping[str, Any], base: Path) -> DeclarationMaquette:
    ou = "maquette"
    _cles(d, ou, {"fichier", "unite", "axe_nez", "axe_haut", "origine", "longueur_attendue",
                  "longueur_imposee"}, {"fichier", "axe_nez", "axe_haut"})
    origine = d.get("origine", "base")
    if isinstance(origine, list):
        origine = tuple(float(v) for v in origine)
    return DeclarationMaquette(
        fichier=_chemin(d["fichier"], base, f"{ou}.fichier"),
        axe_nez=str(d["axe_nez"]),
        axe_haut=str(d["axe_haut"]),
        unite=None if d.get("unite") is None else str(d["unite"]),
        origine=origine,
        longueur_attendue=None if d.get("longueur_attendue") is None else float(d["longueur_attendue"]),
        longueur_imposee=None if d.get("longueur_imposee") is None else float(d["longueur_imposee"]),
    )


def _nombre(valeur: Any, ou: str) -> float:
    if isinstance(valeur, bool) or not isinstance(valeur, (int, float)):
        raise ErreurConfiguration(f"{ou} : un nombre est attendu, reçu {valeur!r}")
    return float(valeur)


def _moteur(d: Mapping[str, Any]) -> ConfigMoteur:
    ou = "moteur"
    _cles(d, ou, {"type", "rendu", "echantillons"})
    return ConfigMoteur(type=str(d.get("type", "pyvista")), rendu=str(d.get("rendu", "eevee")),
                        echantillons=int(_nombre(d.get("echantillons", 16), f"{ou}.echantillons")))


def _video(d: Mapping[str, Any]) -> ConfigVideo:
    ou = "video"
    _cles(d, ou, {"resolution", "ips", "vitesse", "duree", "codec", "ralentis", "transition_ralenti", "de", "a"})
    bornes: dict[str, float | str | None] = {}
    for cle in ("de", "a"):
        v = d.get(cle)
        bornes[cle] = v if v is None or isinstance(v, str) else _nombre(v, f"{ou}.{cle}")
    ralentis = []
    brut = d.get("ralentis", []) or []
    if not isinstance(brut, list):
        raise ErreurConfiguration(f"{ou}.ralentis : une liste de {{de, a, vitesse}}")
    for k, r in enumerate(brut):
        e = _dict(r, f"{ou}.ralentis[{k}]")
        _cles(e, f"{ou}.ralentis[{k}]", {"de", "a", "vitesse"}, {"de", "a", "vitesse"})
        try:
            ralentis.append(Ralenti(de=_nombre(e["de"], f"{ou}.ralentis[{k}].de"),
                                    a=_nombre(e["a"], f"{ou}.ralentis[{k}].a"),
                                    vitesse=_nombre(e["vitesse"], f"{ou}.ralentis[{k}].vitesse")))
        except ValueError as exc:
            if isinstance(exc, ErreurConfiguration):
                raise
            raise ErreurConfiguration(f"{ou}.ralentis[{k}] : {exc}") from None
    if any(b.de < a.a for a, b in zip(ralentis, ralentis[1:])):
        raise ErreurConfiguration(f"{ou}.ralentis : intervalles croissants et disjoints")
    brute = d.get("resolution", "1080p")
    if isinstance(brute, str):
        if brute not in RESOLUTIONS:
            raise ErreurConfiguration(
                f"{ou}.resolution {brute!r} : {', '.join(RESOLUTIONS)} ou [largeur, hauteur]"
            )
        resolution = RESOLUTIONS[brute]
    elif isinstance(brute, list) and len(brute) == 2 and all(isinstance(v, int) for v in brute):
        resolution = (int(brute[0]), int(brute[1]))
    else:
        raise ErreurConfiguration(f"{ou}.resolution : {', '.join(RESOLUTIONS)} ou [largeur, hauteur]")
    codec = _dict(d.get("codec", {}) or {}, f"{ou}.codec")
    _cles(codec, f"{ou}.codec", {"crf", "preset"})
    duree = d.get("duree", "auto")
    return ConfigVideo(
        resolution=resolution,
        ips=_nombre(d.get("ips", 30), f"{ou}.ips"),
        vitesse=None if d.get("vitesse") is None else _nombre(d["vitesse"], f"{ou}.vitesse"),
        duree=None if duree == "auto" else _nombre(duree, f"{ou}.duree"),
        crf=int(_nombre(codec.get("crf", 18), f"{ou}.codec.crf")),
        preset=str(codec.get("preset", "medium")),
        ralentis=tuple(ralentis),
        transition_ralenti=_nombre(d.get("transition_ralenti", 0.5), f"{ou}.transition_ralenti"),
        de=bornes["de"],
        a=bornes["a"],
    )


def _triplet(valeur: Any, ou: str) -> tuple[float, float, float]:
    if not isinstance(valeur, list) or len(valeur) != 3:
        raise ErreurConfiguration(f"{ou} : [x, y, z] attendu")
    x, y, z = (_nombre(v, ou) for v in valeur)
    return (x, y, z)


_CLES_VUE = {
    "poursuite": {"mode", "distance", "cadrage", "azimut", "elevation", "lissage", "champ"},
    "sol": {"mode", "position", "champ", "cadrage", "champ_min", "champ_max"},
    "embarquee": {"mode", "position_corps", "visee", "champ"},
    "ensemble": {"mode", "azimut", "elevation", "cadrage", "echelle_fusee", "part_fusee", "champ", "repere"},
    "orbite": {"mode", "distance", "cadrage", "azimut", "elevation", "vitesse_angulaire", "champ"},
    "images_cles": {"mode", "cles", "cadrage", "lissage"},
}


def _vue(nom: str, v: Mapping[str, Any]) -> ParametresVue:
    ou = f"vues.{nom}"
    mode = v.get("mode")
    if mode not in MODES_VUE:
        raise ErreurConfiguration(f"{ou}.mode : {', '.join(MODES_VUE)}")
    if mode not in _CLES_VUE:
        raise ErreurConfiguration(f"{ou} : mode {mode} inconnu")
    if nom == TELEMETRIE:
        raise ErreurConfiguration(f"vues : « {TELEMETRIE} » est réservé au panneau de télémétrie")
    _cles(v, ou, _CLES_VUE[mode], {"position"} if mode == "sol" else set())
    try:
        if mode == "sol":
            champ = v.get("champ", "auto")
            return ParametresSol(
                position=_triplet(v["position"], f"{ou}.position"),
                champ=None if champ == "auto" else _nombre(champ, f"{ou}.champ"),
                **{k: _nombre(v[k], f"{ou}.{k}") for k in ("cadrage", "champ_min", "champ_max") if k in v},
            )
        if mode == "orbite":
            return ParametresOrbite(**{
                k: _nombre(x, f"{ou}.{k}") for k, x in v.items() if k != "mode" and x != "auto"
            })
        if mode == "images_cles":
            brutes = v.get("cles")
            if not isinstance(brutes, list) or not brutes:
                raise ErreurConfiguration(f"{ou}.cles : une liste de {{t, azimut, elevation, distance, champ}}")
            cles = []
            for i, c in enumerate(brutes):
                e = _dict(c, f"{ou}.cles[{i}]")
                _cles(e, f"{ou}.cles[{i}]", {"t", "azimut", "elevation", "distance", "champ"}, {"t"})
                cles.append(Cle(**{x: _nombre(y, f"{ou}.cles[{i}].{x}") for x, y in e.items() if y != "auto"}))
            return ParametresImagesCles(
                cles=tuple(cles),
                **{k: _nombre(v[k], f"{ou}.{k}") for k in ("cadrage", "lissage") if k in v},
            )
        if mode == "ensemble":
            champs_ensemble: dict[str, Any] = {
                k: (str(x) if k == "repere" else _nombre(x, f"{ou}.{k}"))
                for k, x in v.items() if k != "mode" and x != "auto"
            }
            return ParametresEnsemble(**champs_ensemble)
        if mode == "embarquee":
            champs: dict[str, Any] = {}
            for k in ("position_corps", "visee"):
                if k in v:
                    champs[k] = _triplet(v[k], f"{ou}.{k}")
            if "champ" in v:
                champs["champ"] = _nombre(v["champ"], f"{ou}.champ")
            return ParametresEmbarquee(**champs)
        return ParametresPoursuite(
            **{k: _nombre(x, f"{ou}.{k}") for k, x in v.items() if k != "mode" and x != "auto"}
        )
    except ValueError as exc:
        if isinstance(exc, ErreurConfiguration):
            raise
        raise ErreurConfiguration(f"{ou} : {exc}") from None


def _vues(d: Mapping[str, Any]) -> tuple[tuple[str, ParametresVue], ...]:
    if not d:
        raise ErreurConfiguration("vues : au moins une vue")
    return tuple((str(nom), _vue(str(nom), _dict(brut, f"vues.{nom}"))) for nom, brut in d.items())


def _disposition(d: Mapping[str, Any], ou: str, vues: Sequence[str], telemetrie: bool) -> Disposition:
    type_ = d.get("type", "unique")
    permises = {
        "unique": {"type", "principale", "telemetrie"},
        "incrustation": {"type", "principale", "incrustations", "telemetrie"},
        "grille": {"type", "cases"},
        "libre": {"type", "cases"},
    }
    if type_ not in permises:
        raise ErreurConfiguration(f"{ou}.type : {', '.join(permises)}")
    _cles(d, ou, permises[type_])
    try:
        incrustations = []
        for k, inc in enumerate(d.get("incrustations", []) or []):
            e = _dict(inc, f"{ou}.incrustations[{k}]")
            _cles(e, f"{ou}.incrustations[{k}]", {"vue", "coin", "largeur"}, {"vue"})
            incrustations.append(Incrustation(
                vue=str(e["vue"]), coin=str(e.get("coin", "bas_gauche")),
                largeur=_nombre(e.get("largeur", 0.25), f"{ou}.incrustations[{k}].largeur"),
            ))
        cases: tuple[tuple[str, ...], ...] = ()
        libres: list[tuple[str, tuple[float, float, float, float]]] = []
        if type_ == "grille":
            brut = d.get("cases")
            if not isinstance(brut, list) or not all(isinstance(r, list) for r in brut):
                raise ErreurConfiguration(f"{ou}.cases : liste de rangées, ex. [[poursuite, sol], [embarquee, telemetrie]]")
            cases = tuple(tuple(str(n) for n in r) for r in brut)
        if type_ == "libre":
            for k, c in enumerate(d.get("cases", []) or []):
                e = _dict(c, f"{ou}.cases[{k}]")
                _cles(e, f"{ou}.cases[{k}]", {"vue", "rect"}, {"vue", "rect"})
                r = e["rect"]
                if not isinstance(r, list) or len(r) != 4:
                    raise ErreurConfiguration(f"{ou}.cases[{k}].rect : [x, y, largeur, hauteur] en fractions")
                x, y, lg, h = (_nombre(v, f"{ou}.cases[{k}].rect") for v in r)
                libres.append((str(e["vue"]), (x, y, lg, h)))
        defaut_tm = "droite" if telemetrie else "aucune"
        disposition = Disposition(
            type=type_,
            principale=None if d.get("principale") is None else str(d["principale"]),
            telemetrie=str(d.get("telemetrie", defaut_tm)) if type_ in ("unique", "incrustation") else "aucune",
            incrustations=tuple(incrustations), cases=cases, libres=tuple(libres),
        )
    except ValueError as exc:
        if isinstance(exc, ErreurConfiguration):
            raise
        raise ErreurConfiguration(f"{ou} : {exc}") from None
    for nom in vues_citees(disposition):
        if nom == TELEMETRIE:
            if not telemetrie:
                raise ErreurConfiguration(f"{ou} : la télémétrie est affichée mais la section telemetrie manque")
        elif nom not in vues:
            raise ErreurConfiguration(f"{ou} : vue « {nom} » inconnue ; vues définies : {', '.join(vues)}")
    return disposition


def _sequence(brut: Any, defaut: Disposition, vues: Sequence[str], telemetrie: bool) -> tuple[EtapeSequence, ...]:
    if not isinstance(brut, list) or not brut:
        raise ErreurConfiguration("sequence : une liste d'étapes {de, disposition, transition}")
    etapes = []
    for k, e in enumerate(brut):
        ou = f"sequence[{k}]"
        etape = _dict(e, ou)
        _cles(etape, ou, {"de", "disposition", "transition"}, {"de", "disposition"})
        transition = str(etape.get("transition", "coupe"))
        if transition not in TRANSITIONS:
            raise ErreurConfiguration(f"{ou}.transition : {', '.join(TRANSITIONS)}")
        brute = etape["disposition"]
        if brute == "defaut":
            disposition = defaut
        else:
            disposition = _disposition(_dict(brute, f"{ou}.disposition"), f"{ou}.disposition", vues, telemetrie)
        etapes.append(EtapeSequence(de=_instant(etape["de"], f"{ou}.de"), disposition=disposition,
                                    transition=transition))
    numeriques = [e.de for e in etapes]
    if all(isinstance(x, float) for x in numeriques) and any(
            b <= a for a, b in zip(numeriques, numeriques[1:])):  # type: ignore[operator]
        raise ErreurConfiguration("sequence : les instants `de` doivent être strictement croissants")
    return tuple(etapes)


def _grandeur(brut: Any, ou: str, unites: Mapping[str, Any], colonnes: Mapping[str, Any]) -> Grandeur:
    if isinstance(brut, str):
        if brut in CALCULEES:
            u = unites.get(brut)
            return grandeur_calculee(brut, None if u is None else str(u),
                                     None if brut not in colonnes else str(colonnes[brut]))
        return Grandeur(cle=brut, libelle=brut, colonne=brut)
    e = _dict(brut, ou)
    _cles(e, ou, {"grandeur", "colonne", "libelle", "unite", "facteur", "decimales", "couleur", "plage"})
    plage = None
    if "plage" in e:
        b = e["plage"]
        if not isinstance(b, list) or len(b) != 2:
            raise ErreurConfiguration(f"{ou}.plage : [min, max] (unité affichée)")
        bas, haut = (_nombre(v, f"{ou}.plage") for v in b)
        if not bas < haut:
            raise ErreurConfiguration(f"{ou}.plage : min < max")
        plage = (bas, haut)
    if ("grandeur" in e) == ("colonne" in e):
        raise ErreurConfiguration(f"{ou} : donner soit `grandeur` (calculée), soit `colonne` (lue)")
    decimales = e.get("decimales")
    if decimales is not None and (not isinstance(decimales, int) or isinstance(decimales, bool)
                                  or not 0 <= decimales <= 6):
        raise ErreurConfiguration(f"{ou}.decimales : un entier de 0 à 6")
    couleur = e.get("couleur")
    if couleur is not None and not (isinstance(couleur, str) and len(couleur) == 7 and couleur.startswith("#")):
        raise ErreurConfiguration(f"{ou}.couleur : \"#rrggbb\"")
    if "grandeur" in e:
        nom = str(e["grandeur"])
        if nom not in CALCULEES:
            raise ErreurConfiguration(f"{ou}.grandeur : {', '.join(CALCULEES)} (sinon, `colonne`)")
        if "facteur" in e:
            raise ErreurConfiguration(f"{ou} : `facteur` ne vaut que pour une colonne ; choisir `unite`")
        g = grandeur_calculee(nom, None if e.get("unite") is None else str(e["unite"]))
    else:
        g = Grandeur(cle=str(e["colonne"]), libelle=str(e["colonne"]), unite=str(e.get("unite", "")),
                     facteur=_nombre(e.get("facteur", 1.0), f"{ou}.facteur"), colonne=str(e["colonne"]))
    return replace(g, libelle=str(e.get("libelle", g.libelle)),
                   decimales=g.decimales if decimales is None else int(decimales), couleur=couleur,
                   plage=plage)


def _telemetrie(d: Mapping[str, Any]) -> ConfigTelemetrie:
    ou = "telemetrie"
    _cles(d, ou, {"grandeurs", "unites", "colonnes"})
    unites = _dict(d.get("unites", {}) or {}, f"{ou}.unites")
    _cles(unites, f"{ou}.unites", set(UNITES_TELEMETRIE))
    colonnes = _dict(d.get("colonnes", {}) or {}, f"{ou}.colonnes")
    _cles(colonnes, f"{ou}.colonnes", set(CALCULEES))
    brutes = d.get("grandeurs", list(GRANDEURS))
    if not isinstance(brutes, list) or not 1 <= len(brutes) <= GRANDEURS_MAX:
        raise ErreurConfiguration(
            f"{ou}.grandeurs : une liste de 1 à {GRANDEURS_MAX} grandeurs — calculées "
            f"({', '.join(CALCULEES)}), noms de colonnes, ou {{colonne: …, libelle: …, unite: …}}"
        )
    grandeurs = tuple(_grandeur(b, f"{ou}.grandeurs[{k}]", unites, colonnes) for k, b in enumerate(brutes))
    cles = [g.cle for g in grandeurs]
    doublons = sorted({c for c in cles if cles.count(c) > 1})
    if doublons:
        raise ErreurConfiguration(f"{ou}.grandeurs : affichée(s) deux fois : {', '.join(doublons)}")
    return ConfigTelemetrie(grandeurs=grandeurs)


def _montage(d: Mapping[str, Any], base: Path) -> ConfigMontage:
    ou = "montage"
    _cles(d, ou, {"logo", "titre_debut", "generique_fin", "bandeaux_evenements", "duree_bandeau",
                  "fondu", "etiquettes_vues", "position_titre", "coin_bandeaux"})
    positions: dict[str, Any] = {}
    if "position_titre" in d:
        if d["position_titre"] not in POSITIONS_TITRE:
            raise ErreurConfiguration(f"{ou}.position_titre : {', '.join(POSITIONS_TITRE)}")
        positions["position_titre"] = str(d["position_titre"])
    if "coin_bandeaux" in d:
        if d["coin_bandeaux"] not in COINS:
            raise ErreurConfiguration(f"{ou}.coin_bandeaux : {', '.join(COINS)}")
        positions["coin_bandeaux"] = str(d["coin_bandeaux"])
    logo = None
    if d.get("logo"):
        e = _dict(d["logo"], f"{ou}.logo")
        _cles(e, f"{ou}.logo", {"fichier", "coin", "hauteur"}, {"fichier"})
        coin = str(e.get("coin", "haut_droite"))
        if coin not in COINS:
            raise ErreurConfiguration(f"{ou}.logo.coin : {', '.join(COINS)}")
        hauteur = _nombre(e.get("hauteur", 0.08), f"{ou}.logo.hauteur")
        if not 0.01 <= hauteur <= 0.5:
            raise ErreurConfiguration(f"{ou}.logo.hauteur : fraction de la hauteur d'image, 0.01 → 0.5")
        fichier = _chemin(e["fichier"], base, f"{ou}.logo.fichier")
        if not fichier.is_file():
            raise ErreurConfiguration(f"{ou}.logo.fichier introuvable : {fichier}")
        logo = Logo(fichier=fichier, coin=coin, hauteur=hauteur)
    durees: dict[str, Any] = {k: _nombre(d[k], f"{ou}.{k}") for k in ("titre_debut", "generique_fin", "duree_bandeau", "fondu") if k in d}
    for k, v in durees.items():
        if v < 0:
            raise ErreurConfiguration(f"{ou}.{k} : une durée positive ou nulle (s)")
    booleens: dict[str, Any] = {}
    for k in ("bandeaux_evenements", "etiquettes_vues"):
        if k in d:
            if not isinstance(d[k], bool):
                raise ErreurConfiguration(f"{ou}.{k} : true ou false")
            booleens[k] = d[k]
    return ConfigMontage(logo=logo, **durees, **booleens, **positions)


def _couleur(v: Any, ou: str) -> str:
    if not (isinstance(v, str) and len(v) == 7 and v.startswith("#")):
        raise ErreurConfiguration(f"{ou} : couleur \"#rrggbb\" attendue, reçu {v!r}")
    return v


def _style(d: Mapping[str, Any]) -> ConfigStyle:
    ou = "style"
    _cles(d, ou, {"preset", "ciel", "sol", "trace", "trainee", "eclairage", "fusee", "antialiasing", "lueur",
                  "ensemble"})
    if "antialiasing" in d and d["antialiasing"] not in ANTICRENELAGES:
        raise ErreurConfiguration(f"{ou}.antialiasing : {', '.join(ANTICRENELAGES)}")
    preset = str(d.get("preset", "sobre"))
    if preset not in PRESETS_STYLE:
        raise ErreurConfiguration(f"{ou}.preset : {', '.join(PRESETS_STYLE)}")
    champs: dict[str, Any] = {}
    ciel = _dict(d.get("ciel", {}) or {}, f"{ou}.ciel")
    _cles(ciel, f"{ou}.ciel", {"haut", "bas", "etoiles"})
    for k in ("haut", "bas"):
        if k in ciel:
            champs[f"ciel_{k}"] = _couleur(ciel[k], f"{ou}.ciel.{k}")
    if "etoiles" in ciel:
        champs["ciel_etoiles"] = _nombre(ciel["etoiles"], f"{ou}.ciel.etoiles")
    if "lueur" in d:
        champs["lueur"] = _nombre(d["lueur"], f"{ou}.lueur")
    if "ensemble" in d:
        champs["ensemble_theme"] = str(d["ensemble"])
    sol = _dict(d.get("sol", {}) or {}, f"{ou}.sol")
    _cles(sol, f"{ou}.sol", {"type", "couleur", "maille", "altitude"})
    if "altitude" in sol:
        champs["sol_altitude"] = _nombre(sol["altitude"], f"{ou}.sol.altitude")
    if "type" in sol:
        champs["sol"] = str(sol["type"])
    if "couleur" in sol:
        champs["sol_couleur"] = _couleur(sol["couleur"], f"{ou}.sol.couleur")
    if "maille" in sol:
        champs["sol_maille"] = _nombre(sol["maille"], f"{ou}.sol.maille")
    if "trace" in d:
        if not isinstance(d["trace"], bool):
            raise ErreurConfiguration(f"{ou}.trace : true ou false")
        champs["trace"] = d["trace"]
    tr = _dict(d.get("trainee", {}) or {}, f"{ou}.trainee")
    _cles(tr, f"{ou}.trainee", {"active", "duree", "couleur", "rayon", "croissance", "jusqu_a"})
    if "active" in tr:
        if not isinstance(tr["active"], bool):
            raise ErreurConfiguration(f"{ou}.trainee.active : true ou false")
        champs["trainee"] = tr["active"]
    for k in ("duree", "croissance"):
        if k in tr:
            champs[f"trainee_{k}"] = _nombre(tr[k], f"{ou}.trainee.{k}")
    if "jusqu_a" in tr:
        champs["trainee_jusqu_a"] = (str(tr["jusqu_a"]) if isinstance(tr["jusqu_a"], str)
                                     else _nombre(tr["jusqu_a"], f"{ou}.trainee.jusqu_a"))
    if "rayon" in tr and tr["rayon"] != "auto":
        champs["trainee_rayon"] = _nombre(tr["rayon"], f"{ou}.trainee.rayon")
    if "couleur" in tr:
        champs["trainee_couleur"] = _couleur(tr["couleur"], f"{ou}.trainee.couleur")
    ecl = _dict(d.get("eclairage", {}) or {}, f"{ou}.eclairage")
    _cles(ecl, f"{ou}.eclairage", {"soleil", "intensite", "ambiance", "couleur", "jets"})
    if "couleur" in ecl:
        champs["lumiere_couleur"] = _couleur(ecl["couleur"], f"{ou}.eclairage.couleur")
    if "jets" in ecl:
        champs["lumiere_jets"] = _nombre(ecl["jets"], f"{ou}.eclairage.jets")
    if "soleil" in ecl:
        if ecl["soleil"] is None or ecl["soleil"] == "camera":
            champs["soleil"] = None
        else:
            b = ecl["soleil"]
            if not isinstance(b, list) or len(b) != 2:
                raise ErreurConfiguration(f"{ou}.eclairage.soleil : [azimut, elevation] en degrés, ou camera")
            champs["soleil"] = (_nombre(b[0], f"{ou}.eclairage.soleil"), _nombre(b[1], f"{ou}.eclairage.soleil"))
    for k in ("intensite", "ambiance"):
        if k in ecl:
            champs[k] = _nombre(ecl[k], f"{ou}.eclairage.{k}")
    if "antialiasing" in d:
        champs["antialiasing"] = str(d["antialiasing"])
    fu = _dict(d.get("fusee", {}) or {}, f"{ou}.fusee")
    _cles(fu, f"{ou}.fusee", {"couleur", "metal", "rugosite"})
    if "couleur" in fu:
        champs["fusee_couleur"] = _couleur(fu["couleur"], f"{ou}.fusee.couleur")
    for k in ("metal", "rugosite"):
        if k in fu:
            champs[f"fusee_{k}"] = _nombre(fu[k], f"{ou}.fusee.{k}")
    return replace(PRESETS_STYLE[preset], **champs)


def _flamme(d: Mapping[str, Any], base: Flamme | None, ou: str) -> Flamme:
    _cles(d, ou, {"longueur", "evasement", "couleurs", "opacite", "coeur", "diamants", "scintillement"})
    champs: dict[str, Any] = {}
    for k in ("longueur", "evasement", "opacite", "coeur", "scintillement"):
        if k in d:
            champs[k] = _nombre(d[k], f"{ou}.{k}")
    if "diamants" in d:
        if not isinstance(d["diamants"], int) or isinstance(d["diamants"], bool) or not 0 <= d["diamants"] <= 12:
            raise ErreurConfiguration(f"{ou}.diamants : un entier de 0 à 12")
        champs["diamants"] = d["diamants"]
    if "couleurs" in d:
        c = d["couleurs"]
        if not isinstance(c, list) or not 2 <= len(c) <= 6:
            raise ErreurConfiguration(f"{ou}.couleurs : 2 à 6 couleurs, de la tuyère au bout")
        champs["couleurs"] = tuple(_couleur(x, f"{ou}.couleurs") for x in c)
    f = replace(base or Flamme(), **champs)
    if not (f.longueur > 0 and 0 <= f.evasement < 60 and 0 <= f.opacite <= 1 and 0 <= f.coeur <= 1
            and 0 <= f.scintillement <= 1):
        raise ErreurConfiguration(f"{ou} : longueur > 0, 0 ≤ evasement < 60°, opacite, coeur et scintillement dans [0 ; 1]")
    return f


def _fumee(d: Mapping[str, Any], base: Fumee | None, ou: str) -> Fumee:
    _cles(d, ou, {"couleur_debut", "couleur_fin", "opacite", "duree", "rayon", "evasement", "expansion",
                  "turbulence"})
    champs: dict[str, Any] = {}
    for k in ("opacite", "duree", "rayon", "evasement", "expansion", "turbulence"):
        if k in d:
            champs[k] = _nombre(d[k], f"{ou}.{k}")
    for k in ("couleur_debut", "couleur_fin"):
        if k in d:
            champs[k] = _couleur(d[k], f"{ou}.{k}")
    f = replace(base or Fumee(), **champs)
    if not (f.duree > 0 and f.rayon > 0 and f.expansion >= 0 and f.turbulence >= 0 and 0 <= f.opacite <= 1
            and 0 <= f.evasement < 45):
        raise ErreurConfiguration(f"{ou} : duree > 0, rayon > 0, expansion et turbulence ≥ 0, "
                                  "0 ≤ evasement < 45°, opacite dans [0 ; 1]")
    return f


def _jet(brut: Any, ou: str) -> Jet:
    if isinstance(brut, str):
        if brut not in JETS:
            raise ErreurConfiguration(f"{ou} : jet {brut!r} inconnu ; préréglages : {', '.join(JETS)}")
        return JETS[brut]
    d = _dict(brut, ou)
    _cles(d, ou, {"base", "flamme", "fumee"})
    base = JETS["aucun"]
    if "base" in d:
        base = _jet(str(d["base"]), f"{ou}.base")
    flamme, fumee = base.flamme, base.fumee
    if "flamme" in d:
        flamme = None if d["flamme"] is False else _flamme(_dict(d["flamme"], f"{ou}.flamme"), flamme, f"{ou}.flamme")
    if "fumee" in d:
        fumee = None if d["fumee"] is False else _fumee(_dict(d["fumee"], f"{ou}.fumee"), fumee, f"{ou}.fumee")
    return Jet(flamme, fumee)


def _instant(v: Any, ou: str) -> float | str:
    return str(v) if isinstance(v, str) else _nombre(v, ou)


def _propulsion(d: Mapping[str, Any]) -> ConfigPropulsion:
    ou = "propulsion"
    _cles(d, ou, {"tuyeres", "rayon_tuyere", "phases", "fondu"}, {"phases"})
    tuyeres = None
    if d.get("tuyeres") is not None:
        if not isinstance(d["tuyeres"], list) or not d["tuyeres"]:
            raise ErreurConfiguration(f"{ou}.tuyeres : liste de positions [x, y, z] (FRD, m)")
        tuyeres = tuple(_triplet(t, f"{ou}.tuyeres[{k}]") for k, t in enumerate(d["tuyeres"]))
    rayon = None
    if d.get("rayon_tuyere") not in (None, "auto"):
        rayon = _nombre(d["rayon_tuyere"], f"{ou}.rayon_tuyere")
        if not rayon > 0:
            raise ErreurConfiguration(f"{ou}.rayon_tuyere : une longueur positive (m)")
    brutes = d["phases"]
    if not isinstance(brutes, list) or not brutes:
        raise ErreurConfiguration(f"{ou}.phases : liste de {{de, a, jet}}")
    phases = []
    for k, b in enumerate(brutes):
        e = _dict(b, f"{ou}.phases[{k}]")
        _cles(e, f"{ou}.phases[{k}]", {"de", "a", "jet", "nom"}, {"de", "jet"})
        phases.append(PhasePropulsion(
            de=_instant(e["de"], f"{ou}.phases[{k}].de"),
            a=None if e.get("a") is None else _instant(e["a"], f"{ou}.phases[{k}].a"),
            jet=_jet(e["jet"], f"{ou}.phases[{k}].jet"),
            nom=str(e.get("nom", e["jet"] if isinstance(e["jet"], str) else f"phase {k + 1}")),
        ))
    fondu = _nombre(d.get("fondu", 0.3), f"{ou}.fondu")
    if fondu < 0:
        raise ErreurConfiguration(f"{ou}.fondu : une durée positive ou nulle (s de vol)")
    return ConfigPropulsion(tuyeres=tuyeres, rayon_tuyere=rayon, phases=tuple(phases), fondu=fondu)


def configuration_depuis_dict(d: Mapping[str, Any], base: Path, chemin: Path | None = None) -> Configuration:
    """Construit la configuration ; les chemins relatifs partent de ``base``."""
    racine = _dict(d, "configuration")
    _cles(racine, "configuration",
          {"etude", "trajectoire", "maquette", "video", "vues", "disposition", "sequence",
           "telemetrie", "montage", "style", "propulsion", "moteur", "vent", "cdg", *SECTIONS_A_VENIR},
          {"trajectoire", "maquette"})
    etude = _dict(racine.get("etude", {}) or {}, "etude")
    _cles(etude, "etude", {"titre", "sous_titre"})
    try:
        vues = _vues(_dict(racine["vues"], "vues")) if "vues" in racine else Configuration.vues
        noms = [n for n, _ in vues]
        telemetrie = _telemetrie(_dict(racine["telemetrie"] or {}, "telemetrie")) if "telemetrie" in racine else None
        brute = racine.get("disposition") or {"type": "unique", "principale": noms[0]}
        disposition = _disposition(_dict(brute, "disposition"), "disposition", noms, telemetrie is not None)
        sequence = (_sequence(racine["sequence"], disposition, noms, telemetrie is not None)
                    if "sequence" in racine else ())
        affichees = {n for etape in (disposition, *(e.disposition for e in sequence)) for n in vues_citees(etape)}
        remarques = [f"vue « {n} » définie mais jamais affichée" for n in noms if n not in affichees]
        if telemetrie is not None and TELEMETRIE not in affichees:
            remarques.append("section telemetrie présente mais aucune disposition ne l'affiche")
        return Configuration(
            chemin=chemin,
            etude=Etude(titre=str(etude.get("titre", "")), sous_titre=str(etude.get("sous_titre", ""))),
            trajectoire=_trajectoire(_dict(racine["trajectoire"], "trajectoire"), base),
            maquette=_maquette(_dict(racine["maquette"], "maquette"), base),
            video=_video(_dict(racine.get("video", {}) or {}, "video")),
            vues=vues,
            disposition=disposition,
            sequence=sequence,
            telemetrie=telemetrie,
            montage=_montage(_dict(racine.get("montage", {}) or {}, "montage"), base),
            style=_style(_dict(racine.get("style", {}) or {}, "style")),
            propulsion=(_propulsion(_dict(racine["propulsion"], "propulsion"))
                        if racine.get("propulsion") else None),
            moteur=_moteur(_dict(racine.get("moteur", {}) or {}, "moteur")),
            vent=_vent(_dict(racine["vent"], "vent")) if racine.get("vent") else None,
            cdg=_cdg(_dict(racine["cdg"], "cdg")) if racine.get("cdg") else None,
            a_venir=tuple(s for s in SECTIONS_A_VENIR if s in racine),
            remarques=tuple(remarques),
        )
    except (ErreurTrajectoire, ErreurMaquette, TypeError, ValueError) as exc:
        if isinstance(exc, ErreurConfiguration):
            raise
        raise ErreurConfiguration(str(exc)) from None


def _vent(d: Mapping[str, Any]) -> DeclarationVent:
    _cles(d, "vent", {"colonnes", "vz", "sens", "unite"}, {"colonnes", "vz"})
    return DeclarationVent.depuis_dict(dict(d))


def _cdg(d: Mapping[str, Any]) -> DeclarationCdg:
    _cles(d, "cdg", {"colonnes", "unite", "reference", "axe"}, {"colonnes"})
    return DeclarationCdg.depuis_dict(dict(d))


def charger_configuration(chemin: str | Path) -> Configuration:
    """Lit un fichier YAML de configuration."""
    p = Path(chemin)
    if not p.is_file():
        raise ErreurConfiguration(f"fichier de configuration introuvable : {p}")
    try:
        contenu = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ErreurConfiguration(f"{p.name} : YAML invalide : {exc}") from None
    return configuration_depuis_dict(contenu or {}, base=p.resolve().parent, chemin=p)
