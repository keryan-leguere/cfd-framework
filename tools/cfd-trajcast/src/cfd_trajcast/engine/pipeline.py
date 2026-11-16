"""``Film`` : de la trajectoire et de la maquette à la vidéo.

::

    film = Film.depuis_yaml("CONFIG.yaml")
    film.rendre("vol.mp4")             # toute la vidéo
    film.image(12.5, "t12.png")        # une image, pour régler la caméra

Chaque image : les vues de la disposition courante sont rendues à la taille de
leur case, la télémétrie dessinée, le tout collé (deux agencements mélangés
pendant un fondu), puis habillé (titre, bandeaux, logo, générique).

**Rendu parallèle** (``processus``) : le plan — caméras lissées comprises — est
calculé une fois ; chaque image n'en dépend plus que par son indice, donc la vidéo
se découpe en tronçons d'images consécutives, rendus et encodés par des processus
indépendants (un moteur 3D chacun), puis recollés sans réencodage. Le résultat est
le même qu'en série, aux arrondis de compression près.
"""

from __future__ import annotations

import atexit
import math
import os
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from cfd_trajcast.core.camera import ParametresPoursuite, ParametresVue
from cfd_trajcast.core.disposition import TELEMETRIE, Case, Disposition
from cfd_trajcast.data.configuration import (
    ConfigMontage,
    ConfigMoteur,
    ConfigPropulsion,
    ConfigStyle,
    ConfigTelemetrie,
    Configuration,
    ConfigVideo,
    EtapeSequence,
    Etude,
    charger_configuration,
)
from cfd_trajcast.data.maquette import Maquette
from cfd_trajcast.data.trajectoire import Trajectoire
from cfd_trajcast.engine.encodage import Encodeur, concatener, ecrire_png
from cfd_trajcast.engine.montage import Habillage, coller, couleur, encadrer, melanger, poser
from cfd_trajcast.engine.rendu import creer_moteur
from cfd_trajcast.engine.scene import (
    Plan,
    Scene,
    construire_scene,
    planifier,
    recaler,
    resoudre_propulsion,
)
from cfd_trajcast.engine.telemetrie import FOND, PanneauTelemetrie, Serie, chemin_police, series

__all__ = ["APERCU", "PROCESSUS_MAX", "TRONCON_MIN", "Film", "Progression", "ResultatRendu",
           "memoire_disponible", "processus_auto"]

#: Rappel ``(images faites, images totales)``.
Progression = Callable[[int, int], None]

#: Réglages de l'aperçu : petit, peu d'images, encodage rapide.
APERCU = ConfigVideo(resolution=(960, 540), ips=15.0, crf=26, preset="veryfast")

#: Images par tronçon au minimum : en deçà, préparer une scène coûte plus que la rendre.
TRONCON_MIN = 30
#: Au-delà, les processus se disputent le GPU et la mémoire sans rien gagner (mesuré au J5 :
#: 8 cœurs, 6 processus valent 4, 8 font moins bien).
PROCESSUS_MAX = 6


#: Mémoire d'un processus de rendu : une part fixe (VTK, scène, textures) et une part par pixel
#: d'image (tampons SSAA, composition en flottants, encodeur). Mesuré au J6 : un processus 4K
#: dépasse 1,5 Go ; sur un GPU intégré, ses tampons sont aussi en mémoire centrale.
MEMOIRE_FIXE = 500e6
MEMOIRE_PAR_PIXEL = 160.0


def memoire_disponible() -> float | None:
    """Mémoire disponible (octets, ``MemAvailable`` de Linux), ``None`` si illisible."""
    try:
        with open("/proc/meminfo", encoding="ascii") as f:
            for ligne in f:
                if ligne.startswith("MemAvailable:"):
                    return float(ligne.split()[1]) * 1024
    except OSError:
        pass
    return None


def processus_auto(n_images: int, taille: tuple[int, int] = (1920, 1080),
                   memoire: float | None = None) -> int:
    """Processus de rendu par défaut : les cœurs moins deux (pilote GPU, recollage), au plus
    ``PROCESSUS_MAX``, au moins ``TRONCON_MIN`` images chacun, et **ce que la mémoire permet**
    (80 % de la mémoire disponible ; un processus 4K coûte environ 1,8 Go)."""
    coeurs = os.cpu_count() or 1
    n = min(coeurs - 2, PROCESSUS_MAX, n_images // TRONCON_MIN)
    memoire = memoire_disponible() if memoire is None else memoire
    if memoire is not None:
        par_processus = MEMOIRE_FIXE + MEMOIRE_PAR_PIXEL * taille[0] * taille[1]
        n = min(n, int(0.8 * memoire // par_processus))
    return max(1, n)


@dataclass(frozen=True)
class ResultatRendu:
    """Ce qu'un rendu a produit."""

    chemin: Path
    n_images: int
    largeur: int
    hauteur: int
    ips: float
    duree_video: float
    t_vol: tuple[float, float]
    secondes: float
    processus: int = 1
    troncons: int = 1

    @property
    def ms_par_image(self) -> float:
        """Temps de rendu ramené à une image (tout compris : plan, rendu, encodage, recollage)."""
        return 1000 * self.secondes / max(self.n_images, 1)


def _video_apercu(video: ConfigVideo) -> ConfigVideo:
    largeur, hauteur = video.resolution
    h = min(hauteur, APERCU.resolution[1])
    l_ = round(largeur * h / hauteur / 2) * 2
    return replace(video, resolution=(l_, h), ips=min(video.ips, APERCU.ips),
                   crf=APERCU.crf, preset=APERCU.preset)


def _resoudre_sequence(sequence: tuple[EtapeSequence, ...], traj: Trajectoire) -> tuple[EtapeSequence, ...]:
    """Noms d'événements → instants de vol ; puis instants strictement croissants."""
    instants = {e.nom: e.t for e in traj.evenements}
    out = []
    for k, e in enumerate(sequence):
        if isinstance(e.de, str):
            if e.de not in instants:
                raise ValueError(f"sequence[{k}].de : événement « {e.de} » inconnu ; "
                                 f"événements : {', '.join(instants) or 'aucun'}")
            e = replace(e, de=float(instants[e.de]))
        out.append(e)
    if any(float(b.de) <= float(a.de) for a, b in zip(out, out[1:])):
        raise ValueError("sequence : les instants `de` doivent être strictement croissants")
    return tuple(out)


def _instant(valeur: float | str | None, traj: Trajectoire, ou: str) -> float | None:
    """Un instant de vol donné en secondes ou par un nom d'événement."""
    if valeur is None or not isinstance(valeur, str):
        return valeur
    for e in traj.evenements:
        if e.nom == valeur:
            return float(e.t)
    raise ValueError(f"{ou} : événement « {valeur} » inconnu ; événements : "
                     f"{', '.join(e.nom for e in traj.evenements) or 'aucun'}")


def _zone_principale(plan: Plan) -> tuple[int, int]:
    """(x, largeur) de la première vue 3D de la disposition de départ : là où va le titre."""
    for case in plan.agencements[int(plan.etape[0])]:
        if case.nom != TELEMETRIE:
            return case.x, case.largeur
    return 0, plan.largeur


class _Atelier:
    """Ce qu'il faut pour composer les images d'un plan : moteur 3D, panneaux, habillage."""

    def __init__(self, film: Film, plan: Plan, duree: float | None = None,
                 intervalle: tuple[float, float] | None = None) -> None:
        self.plan = plan
        #: Vol montré par la vidéo entière (axe des temps du panneau), même pour un plan partiel.
        self.intervalle = intervalle or (float(plan.t_vol[0]), float(plan.t_vol[-1]))
        self.film = film
        self.moteur = creer_moteur(film.scene, plan, film.moteur)
        self._panneaux: dict[tuple[int, int], PanneauTelemetrie] = {}
        self._series = film.series_telemetrie()
        police = chemin_police()
        self.habillage = Habillage(film.montage, film.etude, film.trajectoire.evenements,
                                   (plan.largeur, plan.hauteur), plan.t_video, plan.t_vol, police,
                                   duree=len(plan) / plan.ips if duree is None else duree,
                                   zone_titre=_zone_principale(plan))
        # Fond des zones qu'aucune case ne couvre (dispositions libres) : celui du panneau.
        self._fond = couleur(FOND)

    def _panneau(self, taille: tuple[int, int]) -> PanneauTelemetrie:
        if taille not in self._panneaux:
            if self._series is None:
                raise ValueError("la disposition affiche la télémétrie mais aucune n'est configurée")
            self._panneaux[taille] = PanneauTelemetrie(self._series, taille, *self.intervalle)
        return self._panneaux[taille]

    def _agencement(self, k: int, cases: Sequence[Case]) -> NDArray[np.uint8]:
        canevas = np.empty((self.plan.hauteur, self.plan.largeur, 3), dtype=np.uint8)
        canevas[:] = self._fond
        for case in cases:
            if case.nom == TELEMETRIE:
                image = self._panneau(case.taille).image(float(self.plan.t_vol[k]))
            else:
                image = self.moteur.image(k, case.nom, case.taille)
            coller(canevas, case, image)
            if case.medaillon:
                encadrer(canevas, case)
            elif len(cases) > 1:
                # Cases juxtaposées (grille, libre) : un filet sombre les sépare.
                encadrer(canevas, case, epaisseur=1, teinte=FOND)
            etiquette = self.habillage.etiquette(case)
            if etiquette is not None:
                poser(canevas, etiquette, 0.9)
        return canevas

    def image(self, k: int) -> NDArray[np.uint8]:
        plan = self.plan
        image = self._agencement(k, plan.agencements[int(plan.etape[k])])
        if plan.fondu[k] > 0:
            avant = self._agencement(k, plan.agencements[int(plan.etape_prec[k])])
            image = melanger(avant, image, float(plan.fondu[k]))
        return self.habillage.appliquer(image, float(plan.t_video[k]))

    def fermer(self) -> None:
        self.moteur.fermer()


# -- rendu parallèle : l'état d'un processus de rendu --------------------------------------
_ATELIER: _Atelier | None = None


def _fermer_atelier() -> None:
    global _ATELIER
    if _ATELIER is not None:
        _ATELIER.fermer()
        _ATELIER = None


def _initialiser_travailleur(film: Film, plan: Plan) -> None:
    """Une fois par processus : scène, moteur 3D et panneaux, réutilisés pour tous ses tronçons."""
    global _ATELIER
    _ATELIER = _Atelier(film, plan)
    atexit.register(_fermer_atelier)


def _rendre_troncon(debut: int, fin: int, chemin: str, crf: int, preset: str, threads: int) -> int:
    """Rend et encode les images ``[debut ; fin[`` dans ``chemin`` ; renvoie leur nombre."""
    atelier = _ATELIER
    if atelier is None:
        raise RuntimeError("processus de rendu non initialisé")
    plan = atelier.plan
    with Encodeur(chemin, plan.largeur, plan.hauteur, plan.ips, crf=crf, preset=preset,
                  threads=threads) as encodeur:
        for k in range(debut, fin):
            encodeur.ajouter(atelier.image(k))
    return fin - debut


def _decouper(n: int, processus: int) -> list[tuple[int, int]]:
    """Tronçons consécutifs : ~4 par processus (équilibrage), jamais moins de TRONCON_MIN images."""
    taille = max(TRONCON_MIN, math.ceil(n / (4 * processus)))
    return [(a, min(a + taille, n)) for a in range(0, n, taille)]


class Film:
    """Une vidéo à rendre : trajectoire, maquette, format, vues, disposition, habillage."""

    def __init__(
        self,
        trajectoire: Trajectoire,
        maquette: Maquette,
        *,
        video: ConfigVideo | None = None,
        vues: Mapping[str, ParametresVue] | Sequence[tuple[str, ParametresVue]] | None = None,
        disposition: Disposition | None = None,
        sequence: Sequence[EtapeSequence] = (),
        telemetrie: ConfigTelemetrie | None = None,
        montage: ConfigMontage | None = None,
        etude: Etude | None = None,
        style: ConfigStyle | None = None,
        propulsion: ConfigPropulsion | None = None,
        moteur: ConfigMoteur | None = None,
    ) -> None:
        self.trajectoire = trajectoire
        self.maquette = maquette
        self.video = video or ConfigVideo()
        if vues is None:
            vues = {"poursuite": ParametresPoursuite()}
        self.vues: tuple[tuple[str, ParametresVue], ...] = tuple(
            vues.items() if isinstance(vues, Mapping) else vues
        )
        self.disposition = disposition or Disposition(type="unique", principale=self.vues[0][0])
        self.sequence = _resoudre_sequence(tuple(sequence), trajectoire)
        #: Partie du vol montrée par défaut (``video.de``/``video.a``, noms d'événements résolus).
        self.de = _instant(self.video.de, trajectoire, "video.de")
        self.a = _instant(self.video.a, trajectoire, "video.a")
        self.telemetrie = telemetrie
        self.montage = montage if montage is not None else ConfigMontage(titre_debut=0, generique_fin=0)
        self.etude = etude or Etude()
        self.style = style or ConfigStyle()
        self.moteur = moteur or ConfigMoteur()
        # Résolue tout de suite : un événement inconnu doit échouer avant le rendu.
        self.propulsion = resoudre_propulsion(propulsion, trajectoire, maquette, self.style)
        self._scene: Scene | None = None

    @classmethod
    def depuis_configuration(cls, cfg: Configuration, *, utiliser_cache: bool = True) -> Film:
        """Construit le film d'un fichier de configuration déjà chargé.

        ``utiliser_cache=False`` refait les calculs mis en cache (simulation RocketPy).
        """
        ct = cfg.trajectoire
        traj = ct.charger(utiliser_cache=utiliser_cache)
        film = cls(traj, Maquette.depuis_declaration(cfg.maquette), video=cfg.video, vues=cfg.vues,
                   disposition=cfg.disposition, sequence=cfg.sequence, telemetrie=cfg.telemetrie,
                   montage=cfg.montage, etude=cfg.etude, style=cfg.style, propulsion=cfg.propulsion,
                   moteur=cfg.moteur)
        film.series_telemetrie()  # une colonne absente doit échouer ici, pas au milieu du rendu
        return film

    @classmethod
    def depuis_yaml(cls, chemin: str | Path, *, utiliser_cache: bool = True) -> Film:
        """Charge un fichier de configuration et construit le film."""
        return cls.depuis_configuration(charger_configuration(chemin), utiliser_cache=utiliser_cache)

    @property
    def scene(self) -> Scene:
        """Scène construite à la première demande."""
        if self._scene is None:
            self._scene = construire_scene(self.trajectoire, self.maquette, self.style, self.propulsion)
        return self._scene

    def series_telemetrie(self) -> list[Serie] | None:
        """Les grandeurs du panneau, ou None sans télémétrie."""
        return None if self.telemetrie is None else series(self.trajectoire, self.telemetrie)

    def plan(self, *, de: float | None = None, a: float | None = None, apercu: bool = False) -> Plan:
        """Le plan de tournage, sans rien rendre."""
        video = _video_apercu(self.video) if apercu else self.video
        return planifier(self.trajectoire, self.maquette, video, self.vues, self.disposition,
                         self.sequence, fondu=self.montage.fondu,
                         de=self.de if de is None else de, a=self.a if a is None else a)

    def rendre(self, chemin: str | Path, *, de: float | None = None, a: float | None = None,
               apercu: bool = False, progression: Progression | None = None,
               processus: int | None = None) -> ResultatRendu:
        """Rend la vidéo du vol ``[de ; a]`` (défaut : ``video.de``/``video.a``, sinon tout le vol).

        ``processus`` : nombre de processus de rendu (``None`` : :func:`processus_auto` ;
        ``1`` : en série, dans ce processus).
        """
        debut = time.perf_counter()
        video = _video_apercu(self.video) if apercu else self.video
        plan = self.plan(de=de, a=a, apercu=apercu)
        n = len(plan)
        nproc = processus_auto(n, (plan.largeur, plan.hauteur)) if processus is None else max(1, int(processus))
        troncons = _decouper(n, nproc) if nproc > 1 else [(0, n)]
        if len(troncons) < 2:
            nproc = 1
        if nproc == 1:
            atelier = _Atelier(self, plan)
            try:
                with Encodeur(chemin, plan.largeur, plan.hauteur, plan.ips, crf=video.crf,
                              preset=video.preset) as encodeur:
                    for k in range(n):
                        encodeur.ajouter(atelier.image(k))
                        if progression is not None:
                            progression(k + 1, n)
            finally:
                atelier.fermer()
            troncons = [(0, n)]
        else:
            self._rendre_en_parallele(Path(chemin), plan, video, troncons, nproc, progression)
        return ResultatRendu(
            chemin=Path(chemin), n_images=n, largeur=plan.largeur, hauteur=plan.hauteur,
            ips=plan.ips, duree_video=n / plan.ips,
            t_vol=(float(plan.t_vol[0]), float(plan.t_vol[-1])),
            secondes=time.perf_counter() - debut, processus=nproc, troncons=len(troncons),
        )

    def _rendre_en_parallele(self, chemin: Path, plan: Plan, video: ConfigVideo,
                             troncons: list[tuple[int, int]], nproc: int,
                             progression: Progression | None) -> None:
        import multiprocessing

        chemin.parent.mkdir(parents=True, exist_ok=True)
        dossier = Path(tempfile.mkdtemp(prefix=f".{chemin.stem}_troncons_", dir=chemin.parent))
        fichiers = [dossier / f"{i:04d}.mp4" for i in range(len(troncons))]
        # x264 est lui-même multitâche : on partage les cœurs plutôt que de les surcharger.
        threads = max(1, (os.cpu_count() or 1) // nproc)
        # « spawn » : un contexte OpenGL/EGL ne survit pas à un fork.
        contexte = multiprocessing.get_context("spawn")
        try:
            with ProcessPoolExecutor(max_workers=nproc, mp_context=contexte,
                                     initializer=_initialiser_travailleur,
                                     initargs=(self, plan)) as pool:
                futurs = [pool.submit(_rendre_troncon, a, b, str(f), video.crf, video.preset, threads)
                          for (a, b), f in zip(troncons, fichiers)]
                faites = 0
                for futur in as_completed(futurs):
                    faites += futur.result()
                    if progression is not None:
                        progression(faites, len(plan))
            concatener(fichiers, chemin)
        finally:
            shutil.rmtree(dossier, ignore_errors=True)

    def __getstate__(self) -> dict[str, object]:
        # La scène (maillages VTK à venir, textures) se reconstruit dans chaque processus.
        etat = dict(self.__dict__)
        etat["_scene"] = None
        return etat

    def image(self, t: float, chemin: str | Path | None = None, *, apercu: bool = False) -> NDArray[np.uint8]:
        """L'image complète (vues, télémétrie, habillage) à l'instant de vol ``t``.

        Caméras lissées, séquence et habillage dépendent de ce qui précède : le plan
        est calculé depuis le début du vol jusqu'à ``t`` et seule sa dernière image
        est rendue, recalée exactement sur ``t``.
        """
        t0, t_fin = float(self.trajectoire.t[0]), float(self.trajectoire.t[-1])
        if not t0 <= t <= t_fin:
            raise ValueError(f"t = {t:g} s hors du vol [{t0:g} ; {t_fin:g}] s")
        video = _video_apercu(self.video) if apercu else self.video
        # La vidéo commence à `video.de` : son historique de caméra aussi.
        debut_video = t0 if self.de is None else self.de
        fin_video = t_fin if self.a is None else self.a
        if video.duree is not None:  # même vitesse que la vidéo entière, mais plan raccourci
            video = replace(video, vitesse=(fin_video - debut_video) / video.duree, duree=None)
        if t >= debut_video:
            t0 = debut_video
        a = max(t, t0 + 1.0 / video.ips)
        plan = planifier(self.trajectoire, self.maquette, video, self.vues, self.disposition,
                         self.sequence, fondu=self.montage.fondu, de=t0, a=min(a, t_fin))
        k = 0 if t <= t0 else len(plan) - 1
        plan = recaler(plan, self.trajectoire, self.maquette, self.vues, k, t)
        complet = self.plan(apercu=apercu)
        atelier = _Atelier(self, plan, duree=len(complet) / complet.ips,
                           intervalle=(float(complet.t_vol[0]), float(complet.t_vol[-1])))
        try:
            img = atelier.image(k)
        finally:
            atelier.fermer()
        if chemin is not None:
            ecrire_png(img, chemin)
        return img
