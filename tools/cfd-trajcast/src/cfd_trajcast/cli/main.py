"""Interface en ligne de commande de cfd-trajcast.

::

    cfd-trajcast check CONFIG.yaml           conventions retenues et contrôles, sans rendu
    cfd-trajcast rendre CONFIG.yaml          la vidéo (--apercu : 540p, 15 ips, rapide)
    cfd-trajcast rendre CONFIG.yaml -j 4     sur 4 processus (défaut : automatique)
    cfd-trajcast image CONFIG.yaml --t 12.5  une image, pour régler la caméra
    cfd-trajcast ensemble CONFIG.yaml        la vue d'ensemble seule : figure paper (PDF, SVG, PNG)
    cfd-trajcast ensemble CONFIG.yaml --video --sans-rendu   … et cette figure animée en MP4
    cfd-trajcast ensemble CONFIG.yaml --video   … ou la vue d'ensemble rendue en 3D (PyVista)
    cfd-trajcast ensemble CONFIG.yaml --schema  le schéma SVG maison (aucune dépendance)
    cfd-trajcast gui [CONFIG.yaml]           interface interactive : naviguer dans le vol
    cfd-trajcast exporter CONFIG.yaml        la trajectoire lue (RocketPy compris) en CSV
    cfd-trajcast diagnostic                  ffmpeg, extras, fenêtres de rendu possibles
    cfd-trajcast exemple [DEST]              recopier l'exemple (Aim9 + vol de référence)

Codes de retour : ``0`` conforme (alertes permises), ``1`` erreur d'entrée
(fichier illisible, déclaration invalide), ``2`` contrôle en erreur.
"""

from __future__ import annotations

import argparse
import os
import shutil
from collections.abc import Sequence
from pathlib import Path

from rich.console import Console

from cfd_trajcast import __version__
from cfd_trajcast.data.configuration import ErreurConfiguration, charger_configuration
from cfd_trajcast.data.constats import ALERTE, Constat, a_des_erreurs
from cfd_trajcast.data.maquette import ErreurMaquette, Maquette
from cfd_trajcast.data.trajectoire import ErreurTrajectoire
from cfd_trajcast.data.validation import verifier
from cfd_trajcast.engine.diagnostic import diagnostiquer
from cfd_trajcast.engine.ensemble import VueEnsemble
from cfd_trajcast.engine.figure_ensemble import (
    FORMATS_FIGURE,
    PROJECTIONS,
    ErreurFigure,
    cfd_plot_disponible,
)
from cfd_trajcast.engine.pipeline import Film
from cfd_trajcast.engine.scene import ErreurPlan
from cfd_trajcast.paths import EXEMPLE_DIR
from cfd_trajcast.report import theme
from cfd_trajcast.report.console import panneau_erreur, rapport_check
from cfd_trajcast.report.rendu import (
    barre_progression,
    rapport_animation,
    rapport_diagnostic,
    rapport_figure,
    rapport_rendu,
    rapport_schema,
)

__all__ = ["EXIT_CONTROLE", "EXIT_ERREUR_ENTREE", "EXIT_OK", "build_parser", "main"]

EXIT_OK = 0
EXIT_ERREUR_ENTREE = 1
EXIT_CONTROLE = 2


def _formats(texte: str) -> tuple[str, ...]:
    formats = tuple(f.strip().lower().lstrip(".") for f in texte.split(",") if f.strip())
    inconnus = [f for f in formats if f not in FORMATS_FIGURE]
    if inconnus or not formats:
        raise argparse.ArgumentTypeError(f"formats : parmi {', '.join(FORMATS_FIGURE)}")
    return formats


def _poses(texte: str) -> int | list[float | str]:
    """``5`` : cinq poses ; ``12.5,Apogée`` : un instant et un événement."""
    if "," not in texte and texte.strip().isdigit():
        return int(texte)
    out: list[float | str] = []
    for morceau in (m.strip() for m in texte.split(",")):
        if not morceau:
            continue
        try:
            out.append(float(morceau))
        except ValueError:
            out.append(morceau)
    return out


def build_parser() -> argparse.ArgumentParser:
    """Analyseur des arguments."""
    parser = argparse.ArgumentParser(
        prog="cfd-trajcast",
        description="Simulation de vol de fusée → vidéo de présentation.",
    )
    parser.add_argument("--version", action="version", version=f"cfd-trajcast {__version__}")
    sous = parser.add_subparsers(dest="commande", required=True, metavar="COMMANDE")
    check = sous.add_parser("check", help="vérifier une configuration sans rendre")
    check.add_argument("config", type=Path, help="fichier YAML")
    check.add_argument(
        "--coherence", action="store_true",
        help="contrôler aussi l'axe du nez contre la vitesse pendant la montée "
        "(seulement si la trajectoire en a une)",
    )
    rendre = sous.add_parser("rendre", help="rendre la vidéo")
    rendre.add_argument("config", type=Path, help="fichier YAML")
    rendre.add_argument("--sortie", type=Path, help="fichier MP4 (défaut : à côté du YAML)")
    rendre.add_argument("--apercu", action="store_true", help="540p, 15 ips, encodage rapide")
    rendre.add_argument("--de", type=float, help="début du vol montré (s)")
    rendre.add_argument("--a", type=float, help="fin du vol montré (s)")
    rendre.add_argument("-j", "--processus", type=int, default=0, metavar="N",
                        help="processus de rendu en parallèle (0 : automatique, 1 : en série)")
    for p in (check, rendre):
        p.add_argument("--sans-cache", action="store_true",
                       help="refaire la simulation RocketPy au lieu de relire son cache")
    image = sous.add_parser("image", help="rendre une seule image")
    image.add_argument("config", type=Path, help="fichier YAML")
    image.add_argument("--t", type=float, required=True, help="instant de vol (s)")
    image.add_argument("--sortie", type=Path, help="fichier PNG (défaut : à côté du YAML)")
    image.add_argument("--apercu", action="store_true", help="à la résolution de l'aperçu")
    image.add_argument("--sans-cache", action="store_true", help="refaire la simulation RocketPy")
    ens = sous.add_parser(
        "ensemble", help="vue d'ensemble seule : figure paper du vol entier (sans rendu 3D), et sa vidéo",
    )
    ens.add_argument("config", type=Path, help="fichier YAML (une vue `mode: ensemble` est facultative)")
    ens.add_argument("--vue", help="nom de la vue `mode: ensemble` dont reprendre les réglages")
    ens.add_argument("--sortie", type=Path,
                     help="base des fichiers de la figure, sans extension (défaut : <config>_ensemble)")
    ens.add_argument("--formats", type=_formats, default=FORMATS_FIGURE, metavar="pdf,svg,png",
                     help="formats de la figure (défaut : pdf,svg,png)")
    ens.add_argument("--largeur-cm", type=float, default=12.0, help="largeur de la figure (défaut 12 cm)")
    ens.add_argument("--projection", choices=PROJECTIONS, default="ortho",
                     help="orthographique (défaut, distances lisibles) ou perspective")
    ens.add_argument("--sans-legende", action="store_true", help="figure sans l'encadré de légende")
    ens.add_argument("--schema", action="store_true",
                     help="schéma SVG maison au lieu de la figure (sans Matplotlib ni cfd-plot)")
    ens.add_argument("--svg", type=Path, help="schéma : fichier SVG (défaut : <config>_ensemble.svg)")
    ens.add_argument("--taille", type=int, default=1600, help="schéma : plus grand côté, en px (défaut 1600)")
    ens.add_argument("--poses", type=_poses, default=None, metavar="N|t,…",
                     help="maquette posée : un nombre (régulièrement réparties) ou une liste d'instants (s) "
                     "et de noms d'événements séparés par des virgules (défaut : aux événements)")
    ens.add_argument("--theme", choices=("clair", "sombre"), help="schéma et vidéo rendue : style.ensemble par défaut")
    ens.add_argument("--video", action="store_true", help="rendre aussi la vidéo MP4 de tout le vol")
    ens.add_argument("--sans-rendu", action="store_true",
                     help="vidéo = la figure animée (Matplotlib, ni OpenGL ni GPU) ; implique --video")
    ens.add_argument("--mp4", type=Path, help="fichier MP4 (défaut : <config>_ensemble[_anime].mp4) ; "
                     "implique --video")
    ens.add_argument("--apercu", action="store_true", help="vidéo en 540p, 15 ips, encodage rapide")
    ens.add_argument("--duree", type=float, help="durée de la vidéo (s) pour tout le vol")
    ens.add_argument("--sans-telemetrie", action="store_true", help="pas de bande de télémétrie dans la vidéo")
    ens.add_argument("-j", "--processus", type=int, default=0, metavar="N",
                     help="processus de rendu en parallèle (0 : automatique, 1 : en série)")
    ens.add_argument("--sans-cache", action="store_true", help="refaire la simulation RocketPy")
    gui = sous.add_parser("gui", help="interface interactive : vue d'ensemble, temps, télémétrie, repères, vent")
    gui.add_argument("config", type=Path, nargs="?", help="fichier YAML (facultatif : Fichier \u203a Ouvrir)")
    gui.add_argument("--moteur", choices=("mpl", "vtk"), default="mpl",
                     help="vue 3D : Matplotlib (défaut, sans OpenGL) ou VTK (OpenGL)")
    exporter = sous.add_parser("exporter", help="écrire la trajectoire lue en CSV (conventions internes)")
    exporter.add_argument("config", type=Path, help="fichier YAML")
    exporter.add_argument("--sortie", type=Path, help="fichier CSV (défaut : <config>_trajectoire.csv)")
    exporter.add_argument("--sans-cache", action="store_true", help="refaire la simulation RocketPy")
    sous.add_parser("diagnostic", help="ce que cette machine sait faire")
    exemple = sous.add_parser("exemple", help="recopier l'exemple livré")
    exemple.add_argument("dest", type=Path, nargs="?", default=Path("cfd-trajcast-exemple"))
    exemple.add_argument("--force", action="store_true", help="écraser un dossier existant")
    return parser


def _check(config: Path, coherence: bool, sans_cache: bool, out: Console, err: Console) -> int:
    try:
        cfg = charger_configuration(config)
        traj = cfg.trajectoire.charger(utiliser_cache=not sans_cache)
        maquette = Maquette.depuis_declaration(cfg.maquette)
    except (ErreurConfiguration, ErreurTrajectoire, ErreurMaquette) as exc:
        err.print(panneau_erreur(str(exc), indice=f"configuration : {config}"))
        return EXIT_ERREUR_ENTREE
    constats = verifier(traj, maquette, coherence=coherence)
    constats += [Constat(ALERTE, "configuration", r) for r in cfg.remarques]
    out.print(rapport_check(cfg, traj, maquette, constats))
    return EXIT_CONTROLE if a_des_erreurs(constats) else EXIT_OK


def _film(config: Path, err: Console, sans_cache: bool = False) -> tuple[Film | None, int]:
    try:
        cfg = charger_configuration(config)
        film = Film.depuis_configuration(cfg, utiliser_cache=not sans_cache)
    except ValueError as exc:  # ErreurConfiguration, ErreurTrajectoire, ErreurMaquette, colonne absente
        err.print(panneau_erreur(str(exc), indice=f"configuration : {config}"))
        return None, EXIT_ERREUR_ENTREE
    constats = verifier(film.trajectoire, film.maquette)
    if a_des_erreurs(constats):
        err.print(panneau_erreur("la configuration ne passe pas ses contrôles",
                                 indice=f"cfd-trajcast check {config}"))
        return None, EXIT_CONTROLE
    for remarque in cfg.remarques:
        err.print(f"[{theme.ATTENTION}]{remarque}[/]")
    return film, EXIT_OK


def _rendre(args: argparse.Namespace, out: Console, err: Console) -> int:
    film, code = _film(args.config, err, args.sans_cache)
    if film is None:
        return code
    suffixe = "_apercu.mp4" if args.apercu else ".mp4"
    sortie = args.sortie or args.config.with_name(args.config.stem + suffixe)
    try:
        with barre_progression(out, "rendu") as rappel:
            resultat = film.rendre(sortie, de=args.de, a=args.a, apercu=args.apercu, progression=rappel,
                                   processus=args.processus or None)
    except (ErreurPlan, ValueError) as exc:
        err.print(panneau_erreur(str(exc)))
        return EXIT_ERREUR_ENTREE
    out.print(rapport_rendu(resultat))
    return EXIT_OK


def _image(args: argparse.Namespace, out: Console, err: Console) -> int:
    film, code = _film(args.config, err, args.sans_cache)
    if film is None:
        return code
    sortie = args.sortie or args.config.with_name(f"{args.config.stem}_t{args.t:g}.png")
    try:
        film.image(args.t, sortie, apercu=args.apercu)
    except (ErreurPlan, ValueError) as exc:
        err.print(panneau_erreur(str(exc)))
        return EXIT_ERREUR_ENTREE
    out.print(f"Image écrite : [{theme.ACCENT}]{sortie}[/]")
    return EXIT_OK


def _ensemble(args: argparse.Namespace, out: Console, err: Console) -> int:
    try:
        cfg = charger_configuration(args.config)
        vue = VueEnsemble.depuis_configuration(cfg, vue=args.vue, utiliser_cache=not args.sans_cache)
    except ValueError as exc:  # ErreurConfiguration, ErreurTrajectoire, ErreurMaquette, vue inconnue
        err.print(panneau_erreur(str(exc), indice=f"configuration : {args.config}"))
        return EXIT_ERREUR_ENTREE
    constats = verifier(vue.trajectoire, vue.maquette)
    if a_des_erreurs(constats):
        err.print(panneau_erreur("la configuration ne passe pas ses contrôles",
                                 indice=f"cfd-trajcast check {args.config}"))
        return EXIT_CONTROLE
    schema = args.schema or args.svg is not None
    if not schema and not cfd_plot_disponible():
        out.print("cfd-plot absent : schéma SVG maison à la place de la figure paper "
                  "(pip install tools/cfd-plot pour la figure)", style=theme.ATTENTION)
        schema = True
    try:
        if schema:
            svg = args.svg or args.config.with_name(f"{args.config.stem}_ensemble.svg")
            out.print(rapport_schema(vue.svg(svg, taille=args.taille, poses=args.poses, theme=args.theme)))
        else:
            base = args.sortie or args.config.with_name(f"{args.config.stem}_ensemble")
            out.print(rapport_figure(vue.figure(base, formats=args.formats, largeur_cm=args.largeur_cm,
                                                poses=args.poses, projection=args.projection,
                                                legende=not args.sans_legende)))
    except ValueError as exc:
        err.print(panneau_erreur(str(exc)))
        return EXIT_ERREUR_ENTREE
    except ErreurFigure as exc:
        err.print(panneau_erreur(str(exc)))
        return EXIT_ERREUR_ENTREE
    if not (args.video or args.mp4 or args.sans_rendu):
        return EXIT_OK
    if args.sans_rendu:
        suffixe = "_ensemble_anime_apercu.mp4" if args.apercu else "_ensemble_anime.mp4"
        mp4 = args.mp4 or args.config.with_name(args.config.stem + suffixe)
        try:
            with barre_progression(out, "animation") as rappel:
                animation = vue.animer(mp4, apercu=args.apercu, duree=args.duree, progression=rappel)
        except (ErreurFigure, ValueError) as exc:
            err.print(panneau_erreur(str(exc)))
            return EXIT_ERREUR_ENTREE
        out.print(rapport_animation(animation))
        return EXIT_OK
    suffixe = "_ensemble_apercu.mp4" if args.apercu else "_ensemble.mp4"
    mp4 = args.mp4 or args.config.with_name(args.config.stem + suffixe)
    try:
        with barre_progression(out, "rendu") as rappel:
            resultat = vue.rendre(mp4, apercu=args.apercu, progression=rappel, processus=args.processus or None,
                                  telemetrie=False if args.sans_telemetrie else None, duree=args.duree)
    except (ErreurPlan, ValueError) as exc:
        err.print(panneau_erreur(str(exc)))
        return EXIT_ERREUR_ENTREE
    out.print(rapport_rendu(resultat))
    return EXIT_OK


def _gui(args: argparse.Namespace, err: Console) -> int:
    from cfd_trajcast.gui import ErreurInterface, lancer

    try:
        return lancer(args.config, moteur=args.moteur)
    except ErreurInterface as exc:
        err.print(panneau_erreur(str(exc), indice="cfd-trajcast diagnostic"))
        return EXIT_ERREUR_ENTREE


def _exporter(args: argparse.Namespace, out: Console, err: Console) -> int:
    try:
        cfg = charger_configuration(args.config)
        traj = cfg.trajectoire.charger(utiliser_cache=not args.sans_cache)
    except ValueError as exc:
        err.print(panneau_erreur(str(exc), indice=f"configuration : {args.config}"))
        return EXIT_ERREUR_ENTREE
    sortie = args.sortie or args.config.with_name(f"{args.config.stem}_trajectoire.csv")
    csv, evenements = traj.vers_csv(sortie)
    out.print(f"Trajectoire écrite : [{theme.ACCENT}]{csv}[/] ({len(traj.t)} lignes, {traj.source})")
    if evenements is not None:
        out.print(f"Événements : [{theme.ACCENT}]{evenements}[/] ({len(traj.evenements)})")
    out.print("Pour la relire :", style=theme.DISCRET)
    lignes = ["trajectoire:", f"  fichier: {csv.name}", "  repere: ENU",
              "  attitude: { type: quaternion, colonnes: [qw, qx, qy, qz] }"]
    if evenements is not None:
        lignes.append(f"  evenements: {evenements.name}")
    for ligne in lignes:
        out.print("  " + ligne, style=theme.DISCRET, markup=False)
    return EXIT_OK


def _diagnostic(out: Console) -> int:
    sondes = diagnostiquer()
    out.print(rapport_diagnostic(sondes))
    # Rendu possible avec la fenêtre que le moteur prendra, et pile Python au minimum déclaré.
    rendu = all(s.ok for s in sondes if s.categorie in ("rendu", "version"))
    return EXIT_OK if rendu else EXIT_CONTROLE


def _exemple(dest: Path, force: bool, out: Console, err: Console) -> int:
    if dest.exists() and not force:
        err.print(panneau_erreur(f"{dest} existe déjà", indice="--force pour l'écraser"))
        return EXIT_ERREUR_ENTREE
    shutil.copytree(
        EXEMPLE_DIR, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__")
    )
    out.print(f"Exemple copié dans [{theme.ACCENT}]{dest}[/]. Ensuite :")
    out.print(f"  cd {dest} && cfd-trajcast check CONFIG.yaml", style=theme.DISCRET)
    out.print("  cfd-trajcast rendre CONFIG.yaml --apercu", style=theme.DISCRET)
    out.print("  cfd-trajcast rendre CONFIG_MULTIVUES.yaml --apercu", style=theme.DISCRET)
    out.print("  cfd-trajcast rendre CONFIG_ENSEMBLE.yaml --apercu", style=theme.DISCRET)
    out.print("  cfd-trajcast ensemble CONFIG_ENSEMBLE.yaml --video --apercu", style=theme.DISCRET)
    out.print("  python vue_ensemble.py   (la même chose depuis Python)", style=theme.DISCRET)
    out.print("  cfd-trajcast rendre CONFIG_VIRAGE.yaml --apercu", style=theme.DISCRET)
    out.print("  cd ROCKETPY && cfd-trajcast rendre CONFIG_ROCKETPY.yaml --apercu   (RocketPy, Python ≥ 3.10)",
              style=theme.DISCRET)
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée ; renvoie le code de retour."""
    args = build_parser().parse_args(argv)
    if args.commande != "gui":
        # Sans interface, Matplotlib n'a besoin d'aucun Qt. Laissé à lui-même, il choisit le
        # backend Qt dès que PyQt5 est installé (extra gui) et qu'un écran existe : Qt se charge,
        # et avec un LD_LIBRARY_PATH d'OpenFOAM, deux Qt se croisent et tout s'arrête.
        os.environ.setdefault("MPLBACKEND", "Agg")
    out = Console(highlight=False)
    err = Console(stderr=True, highlight=False)
    if args.commande == "check":
        return _check(args.config, args.coherence, args.sans_cache, out, err)
    if args.commande == "rendre":
        return _rendre(args, out, err)
    if args.commande == "image":
        return _image(args, out, err)
    if args.commande == "gui":
        return _gui(args, err)
    if args.commande == "ensemble":
        return _ensemble(args, out, err)
    if args.commande == "exporter":
        return _exporter(args, out, err)
    if args.commande == "diagnostic":
        return _diagnostic(out)
    return _exemple(args.dest, args.force, out, err)
