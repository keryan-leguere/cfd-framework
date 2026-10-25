"""Interface en ligne de commande de cfd-aq.

Rapport de traînée d'une aspérité :

    cfd-aq marche --type montante --hauteur 1.5e-3 --envergure 2.4 \\
                  --altitude 11000 --mach 0.82 --x 10

La vitesse peut aussi être donnée en Vc, TAS ou EAS, et l'altitude en altitude
pression ou avec un écart ΔT : ces conversions passent par le paquet frère
cfd-atm.

Rapport de traînée d'un cas complet :

    cfd-aq run CAS.yaml [--figures RÉP]
    cfd-aq check CAS.yaml

Corrélations nues, sans écoulement :

    cfd-aq ratio --h-plus 500 --mach 0.8

Reste :

    cfd-aq figures RÉP
    cfd-aq exemple [RÉP]

Les erreurs sont affichées comme un court panneau Rich nommant le problème,
jamais une trace d'appels : le public est un ingénieur qui chiffre une
tolérance de fabrication, pas un développeur Python qui débogue cet outil.

Codes de sortie : 0 tout va bien, 1 erreur d'entrée, 2 le calcul a abouti mais
au moins une extrapolation hors du domaine mesuré a été signalée.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from rich.console import Console
from rich.panel import Panel

from cfd_aq import __version__
from cfd_aq.core.atmosphere import PointAtmospherique, mach_depuis_vitesse
from cfd_aq.core.couche_limite import CoucheLimite, EtatLocal
from cfd_aq.core.marches import (
    TypeAsperite,
    ratio_arete,
    ratio_arete_rectangulaire_2h,
    ratio_marche_descendante,
    ratio_marche_montante,
)
from cfd_aq.core.trainee import Asperite, ResultatTrainee, calculer_trainee
from cfd_aq.data.cas import CasError, charger_cas
from cfd_aq.paths import EXEMPLE_DIR
from cfd_aq.report import console as rapport
from cfd_aq.report import theme

__all__ = ["main"]

CODE_OK = 0
CODE_ERREUR_ENTREE = 1
CODE_HORS_DOMAINE = 2


def _echouer(console: Console, message: str) -> NoReturn:
    console.print(Panel(message, title=f"[{theme.ERREUR}]Erreur[/]", border_style="red"))
    raise SystemExit(CODE_ERREUR_ENTREE)


_VITESSES = (
    ("--mach", "mach"),
    ("--vc", "vitesse_conventionnelle"),
    ("--tas", "vitesse_vraie"),
    ("--eas", "vitesse_equivalente"),
)


def _etat_depuis_arguments(console: Console, args: argparse.Namespace) -> EtatLocal:
    vitesses = {nom: getattr(args, nom) for _, nom in _VITESSES if getattr(args, nom) is not None}
    if len(vitesses) != 1:
        drapeaux = ", ".join(drapeau for drapeau, _ in _VITESSES)
        _echouer(
            console,
            f"Donner exactement une vitesse parmi {drapeaux} (reçu : {len(vitesses)}).",
        )

    if args.altitude is not None and (args.temperature is not None or args.pression is not None):
        _echouer(
            console,
            "Donner soit --altitude, soit --temperature et --pression, pas les deux.",
        )
    try:
        if args.altitude is not None:
            return EtatLocal.atmosphere(
                args.altitude,
                delta_isa=args.delta_isa,
                type_altitude=args.type_altitude,
                **vitesses,
            )
        if args.temperature is None or args.pression is None:
            _echouer(
                console,
                "Conditions locales manquantes : donner --altitude, ou bien "
                "--temperature et --pression.",
            )
        if args.delta_isa != 0.0 or args.type_altitude != "geometrique":
            _echouer(
                console,
                "--delta-isa et --type-altitude n'ont de sens qu'avec --altitude.",
            )
        point = PointAtmospherique(args.temperature, args.pression, "imposé", "cli")
        mach = vitesses.get("mach")
        if mach is None:
            mach = mach_depuis_vitesse(point, **vitesses)
        return EtatLocal.depuis_point(point, mach)
    except (ValueError, RuntimeError) as erreur:
        _echouer(console, str(erreur))


def _couche_limite_depuis_arguments(
    console: Console, args: argparse.Namespace, etat: EtatLocal
) -> CoucheLimite:
    fournis = [
        nom
        for nom, valeur in (("--x", args.x), ("--cf", args.cf), ("--tau", args.tau))
        if valeur is not None
    ]
    if len(fournis) != 1:
        _echouer(
            console,
            "Donner exactement une description de la couche limite : --x (distance au bord "
            "d'attaque), --cf (coefficient de frottement local) ou --tau (cisaillement "
            f"pariétal). Reçu : {', '.join(fournis) or 'aucune'}.",
        )
    try:
        if args.x is not None:
            return CoucheLimite.plaque_plane(etat, args.x, args.temperature_paroi)
        if args.cf is not None:
            return CoucheLimite.depuis_cf(etat, args.cf, args.temperature_paroi)
        return CoucheLimite.depuis_cisaillement(etat, args.tau, args.temperature_paroi)
    except ValueError as erreur:
        _echouer(console, str(erreur))


def _code_sortie(resultats: Sequence[ResultatTrainee]) -> int:
    return CODE_HORS_DOMAINE if any(r.avertissements for r in resultats) else CODE_OK


# --- sous-commandes -------------------------------------------------------


def _commande_ratio(console: Console, args: argparse.Namespace) -> int:
    try:
        ratios: list[tuple[str, float]] = [
            ("Marche montante", ratio_marche_montante(args.h_plus, args.mach)),
            ("Marche descendante", ratio_marche_descendante(args.h_plus, args.mach)),
            (
                f"Arête, t/h = {args.t_sur_h:g}",
                ratio_arete(args.h_plus, args.mach, args.t_sur_h),
            ),
        ]
        if abs(args.t_sur_h - 2.0) < 1e-9:
            ratios.append(
                (
                    "Arête t = 2h (table dédiée)",
                    ratio_arete_rectangulaire_2h(args.h_plus, args.mach),
                )
            )
    except ValueError as erreur:
        _echouer(console, str(erreur))

    rapport.afficher_ratios(console, args.h_plus, args.mach, ratios)
    from cfd_aq.core.marches import verifier_domaine

    avertissements = verifier_domaine(TypeAsperite.ARETE, args.h_plus, args.mach)
    rapport.afficher_avertissements(console, avertissements)
    return CODE_HORS_DOMAINE if avertissements else CODE_OK


def _commande_marche(console: Console, args: argparse.Namespace) -> int:
    etat = _etat_depuis_arguments(console, args)
    couche_limite = _couche_limite_depuis_arguments(console, args, etat)
    try:
        asperite = Asperite(
            type_asperite=TypeAsperite(args.type),
            hauteur=args.hauteur,
            envergure=args.envergure,
            t_sur_h=args.t_sur_h,
            rayon_sur_h=args.rayon_sur_h,
            angle_chanfrein=args.chanfrein,
            angle_derapage=args.derapage,
        )
        resultat = calculer_trainee(
            asperite,
            etat,
            couche_limite,
            surface_reference=args.surface_reference,
            amplification=args.amplification,
        )
    except ValueError as erreur:
        _echouer(console, str(erreur))

    rapport.afficher_paquets(console)
    rapport.afficher_ecoulement(console, etat)
    rapport.afficher_couche_limite(console, couche_limite)
    rapport.afficher_asperite(console, args.nom, asperite, resultat)
    return _code_sortie([resultat])


def _commande_run(console: Console, args: argparse.Namespace) -> int:
    try:
        cas = charger_cas(args.cas)
    except CasError as erreur:
        _echouer(console, str(erreur))

    rapport.afficher_paquets(console)
    rapport.afficher_ecoulement(console, cas.etat)
    rapport.afficher_couche_limite(console, cas.couche_limite)

    resultats: list[tuple[str, ResultatTrainee]] = []
    for nom, asperite in cas.asperites:
        try:
            resultat = calculer_trainee(
                asperite,
                cas.etat,
                cas.couche_limite,
                surface_reference=cas.surface_reference,
                amplification=cas.amplification,
            )
        except ValueError as erreur:
            _echouer(console, f"« {nom} » : {erreur}")
        rapport.afficher_asperite(console, nom, asperite, resultat)
        resultats.append((nom, resultat))

    rapport.afficher_bilan(console, resultats, cas.surface_reference)

    if args.figures is not None:
        _ecrire_figures(console, Path(args.figures))

    return _code_sortie([r for _, r in resultats])


def _commande_check(console: Console, args: argparse.Namespace) -> int:
    try:
        cas = charger_cas(args.cas)
    except CasError as erreur:
        _echouer(console, str(erreur))
    console.print(
        Panel(
            f"« {cas.etude} » : {len(cas.asperites)} aspérité(s), "
            f"M = {cas.etat.mach:g}, C_fe = {cas.couche_limite.cf:.6f}",
            title=f"[{theme.OK}]Cas valide[/]",
            border_style="green",
        )
    )
    return CODE_OK


def _ecrire_figures(console: Console, repertoire: Path) -> None:
    from cfd_aq.report import figures

    ecrits = [
        figures.enregistrer(figures.tracer_geometries(), repertoire / "01_geometries.png"),
        figures.enregistrer(figures.tracer_rapports(), repertoire / "02_rapports_h_plus.png"),
        figures.enregistrer(figures.tracer_effet_mach(), repertoire / "03_effet_mach.png"),
        figures.enregistrer(figures.tracer_corrections(), repertoire / "04_corrections.png"),
    ]
    console.print(
        Panel(
            "\n".join(str(chemin) for chemin in ecrits)
            + f"\n[{theme.DISCRET}]tracées via {figures.sortie_graphique()}[/]",
            title=f"[{theme.TITRE}]Figures écrites[/]",
            border_style="cyan",
        )
    )


def _commande_figures(console: Console, args: argparse.Namespace) -> int:
    _ecrire_figures(console, Path(args.repertoire))
    return CODE_OK


def _commande_exemple(console: Console, args: argparse.Namespace) -> int:
    destination = Path(args.repertoire)
    if destination.exists() and any(destination.iterdir()):
        _echouer(console, f"« {destination} » existe déjà et n'est pas vide.")
    shutil.copytree(EXEMPLE_DIR, destination, dirs_exist_ok=True)
    fichiers = sorted(p.name for p in destination.iterdir())
    console.print(
        Panel(
            "\n".join(fichiers),
            title=f"[{theme.OK}]Exemple copié dans {destination}[/]",
            border_style="green",
        )
    )
    return CODE_OK


# --- analyse des arguments ------------------------------------------------


def _ajouter_arguments_ecoulement(sous: argparse.ArgumentParser) -> None:
    sous.add_argument("--mach", type=float, help="Mach local [-]")
    sous.add_argument(
        "--vc",
        type=float,
        dest="vitesse_conventionnelle",
        help="vitesse conventionnelle Vc/CAS [m/s] (demande cfd-atm)",
    )
    sous.add_argument(
        "--tas", type=float, dest="vitesse_vraie", help="vitesse vraie TAS [m/s] (demande cfd-atm)"
    )
    sous.add_argument(
        "--eas",
        type=float,
        dest="vitesse_equivalente",
        help="vitesse équivalente EAS [m/s] (demande cfd-atm)",
    )
    sous.add_argument("--altitude", type=float, help="altitude [m]")
    sous.add_argument(
        "--type-altitude",
        choices=("geometrique", "geopotentielle", "pression"),
        default="geometrique",
        help="lecture de --altitude (les deux dernières demandent cfd-atm)",
    )
    sous.add_argument(
        "--delta-isa",
        type=float,
        default=0.0,
        help="écart ΔT par rapport à l'ISA [K] (demande cfd-atm)",
    )
    sous.add_argument("--temperature", type=float, help="température statique locale [K]")
    sous.add_argument("--pression", type=float, help="pression statique locale [Pa]")
    sous.add_argument(
        "--temperature-paroi", type=float, help="température de paroi [K] (adiabatique par défaut)"
    )
    sous.add_argument("--x", type=float, help="distance au bord d'attaque [m]")
    sous.add_argument("--cf", type=float, help="coefficient de frottement local C_fe [-]")
    sous.add_argument("--tau", type=float, help="cisaillement pariétal τ_w [Pa]")


def _construire_parseur() -> argparse.ArgumentParser:
    parseur = argparse.ArgumentParser(
        prog="cfd-aq",
        description=(
            "Traînée des aspérités de surface (marche montante, descendante, arête), "
            "d'après AGARD-AG-264 §4.3."
        ),
    )
    parseur.add_argument("--version", action="version", version=f"cfd-aq {__version__}")
    sous_parseurs = parseur.add_subparsers(dest="commande", required=True)

    ratio = sous_parseurs.add_parser("ratio", help="rapport CDe/Cfe nu, à (h⁺, M) donnés")
    ratio.add_argument("--h-plus", type=float, required=True, help="h⁺ = u_τ·h/ν_w [-]")
    ratio.add_argument("--mach", type=float, required=True, help="Mach local [-]")
    ratio.add_argument("--t-sur-h", type=float, default=1.0, help="épaisseur d'arête t/h [-]")
    ratio.set_defaults(fonction=_commande_ratio)

    marche = sous_parseurs.add_parser("marche", help="traînée d'une aspérité isolée")
    marche.add_argument(
        "--type",
        choices=[t.value for t in TypeAsperite],
        required=True,
        help="forme de l'aspérité",
    )
    marche.add_argument("--hauteur", type=float, required=True, help="hauteur h [m]")
    marche.add_argument("--envergure", type=float, required=True, help="envergure b [m]")
    marche.add_argument("--t-sur-h", type=float, default=1.0, help="épaisseur d'arête t/h [-]")
    marche.add_argument("--rayon-sur-h", type=float, default=0.0, help="rayon d'arête r/h [-]")
    marche.add_argument("--chanfrein", type=float, default=90.0, help="angle de chanfrein θ [°]")
    marche.add_argument("--derapage", type=float, default=90.0, help="angle de dérapage α [°]")
    marche.add_argument("--surface-reference", type=float, help="S_ref pour le ΔCx [m²]")
    marche.add_argument(
        "--amplification",
        type=float,
        default=1.0,
        help="facteur m_d de Nash-Bradshaw (gradient de pression)",
    )
    marche.add_argument("--nom", default="Aspérité", help="étiquette du rapport")
    _ajouter_arguments_ecoulement(marche)
    marche.set_defaults(fonction=_commande_marche)

    run = sous_parseurs.add_parser("run", help="traînée d'un cas YAML complet")
    run.add_argument("cas", type=Path, help="fichier de cas YAML")
    run.add_argument("--figures", help="répertoire où écrire les figures")
    run.set_defaults(fonction=_commande_run)

    check = sous_parseurs.add_parser("check", help="valider un cas YAML sans calculer")
    check.add_argument("cas", type=Path, help="fichier de cas YAML")
    check.set_defaults(fonction=_commande_check)

    figures = sous_parseurs.add_parser("figures", help="tracer les corrélations du paquet")
    figures.add_argument("repertoire", help="répertoire de sortie")
    figures.set_defaults(fonction=_commande_figures)

    exemple = sous_parseurs.add_parser("exemple", help="copier l'exemple prêt à l'emploi")
    exemple.add_argument("repertoire", nargs="?", default="exemple_cfd_aq")
    exemple.set_defaults(fonction=_commande_exemple)

    return parseur


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the ``cfd-aq`` command."""
    parseur = _construire_parseur()
    args = parseur.parse_args(argv)
    console = Console()
    try:
        code: int = args.fonction(console, args)
    except SystemExit as sortie:
        return int(sortie.code or 0)
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
