"""Interface en ligne de commande de cfd-validation.

Cinq commandes, dans l'ordre où on les emploie ::

    cfd-validation toolchain            de quoi f2py dispose ici
    cfd-validation construire SOURCE    compiler le modèle en module Python
    cfd-validation inspecter --module M ce que le module expose vraiment
    cfd-validation check --tables T     la déclaration tient-elle debout ?
    cfd-validation valider …            le contrôle lui-même, et son rapport
    cfd-validation exemple DEST         recopier l'exemple prêt à tourner

Le public est un ingénieur qui a écrit le Fortran, pas un développeur Python :
une erreur d'entrée sort en panneau rouge nommant le fichier et le remède,
jamais en trace d'appels.

Codes de retour : ``0`` succès, ``1`` erreur d'entrée, ``2`` la commande a
abouti mais son résultat exige une action — des points sont hors tolérance.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from rich.console import Console

from cfd_validation import __version__
from cfd_validation.data.spec import ErreurSpec, SpecTable, charger_fichier
from cfd_validation.engine.tables import Modele, valider_tables
from cfd_validation.paths import EXEMPLE_DIR
from cfd_validation.report import theme
from cfd_validation.report.console import (
    panneau_erreur,
    panneau_toolchain,
    rapport_tables,
    tableau_blocs,
)
from cfd_validation.wrap.bloc import ErreurBloc, blocs_exposes
from cfd_validation.wrap.construire import ErreurConstruction, construire
from cfd_validation.wrap.f2py_module import ErreurResolution, resoudre_module, resoudre_objet
from cfd_validation.wrap.toolchain import inspecter_toolchain

console = Console()
err_console = Console(stderr=True)

__all__ = ["build_parser", "main"]

EXIT_OK = 0
EXIT_ERREUR_ENTREE = 1
EXIT_ACTION_REQUISE = 2

_INDICE_TABLES = "Voir 00_DOC/02_DECLARER_SES_TABLES.md pour le schéma du fichier de tables."


def _echec(message: str, *, indice: str = "") -> NoReturn:
    """Panneau rouge puis sortie en code 1, sans trace d'exécution."""
    err_console.print(panneau_erreur(message, indice=indice))
    sys.exit(EXIT_ERREUR_ENTREE)


# ---------------------------------------------------------------------------
# Sous-commandes
# ---------------------------------------------------------------------------


def cmd_toolchain(args: argparse.Namespace) -> int:
    """Affiche l'état de la chaîne de compilation."""
    chaine = inspecter_toolchain()
    console.print(panneau_toolchain(chaine))
    return EXIT_OK if chaine.pret else EXIT_ACTION_REQUISE


def cmd_construire(args: argparse.Namespace) -> int:
    """Compile des sources Fortran/C en module Python, par f2py."""
    try:
        produit = construire(
            args.sources,
            nom_module=args.nom,
            destination=args.sortie,
            options=tuple(args.option or ()),
        )
    except ErreurConstruction as erreur:
        _echec(str(erreur), indice="`cfd-validation toolchain` dit ce qui manque.")
    console.print(f"[{theme.OK}]écrit :[/] {produit}")
    return EXIT_OK


def cmd_inspecter(args: argparse.Namespace) -> int:
    """Liste les COMMON blocks qu'un module expose, et leurs tableaux."""
    module = _module(args.module)
    blocs = blocs_exposes(module)
    console.print(tableau_blocs(blocs))
    if not blocs:
        console.print(
            f"[{theme.ATTENTION}]Aucun COMMON block détecté. "
            "Le module a-t-il bien été compilé avec ses blocs, "
            "et sont-ils bien nommés dans le source ?[/]"
        )
        return EXIT_ACTION_REQUISE
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    """Valide un fichier de tables, sans modèle ni module."""
    specs = _specs(args.tables)
    for nom, spec in specs.items():
        console.print(
            f"[{theme.OK}]✓[/] {nom} "
            f"[{theme.DISCRET}]— {spec.bloc}.{spec.tableau}, "
            f"{len(spec.independantes)} variable(s) indépendante(s), "
            f"QOI {list(spec.qoi)}[/]"
        )
    console.print(f"[{theme.ACCENT}]{len(specs)} table(s) déclarée(s) sans erreur.[/]")
    return EXIT_OK


def cmd_valider(args: argparse.Namespace) -> int:
    """Contrôle que le module relit bien ses tables, et rapporte."""
    specs = _specs(args.tables)
    module = _module(args.module)
    modele = _modele(args.modele)

    try:
        rapport = valider_tables(module, specs, modele=modele)
    except (ErreurBloc, ErreurSpec) as erreur:
        _echec(str(erreur), indice=_INDICE_TABLES)
    except ValueError as erreur:
        _echec(
            str(erreur), indice="Voir 00_DOC/03_BRANCHER_SON_MODELE.md pour le contrat du modèle."
        )

    console.print(rapport_tables(rapport))

    if args.figures is not None:
        _tracer(rapport, args)

    return EXIT_OK if rapport.conforme else EXIT_ACTION_REQUISE


def cmd_exemple(args: argparse.Namespace) -> int:
    """Recopie l'exemple prêt à tourner."""
    destination = Path(args.destination)
    if destination.exists() and any(destination.iterdir()):
        _echec(
            f"{destination} existe et n'est pas vide.",
            indice="Donnez un répertoire neuf, ou videz celui-ci.",
        )
    shutil.copytree(
        EXEMPLE_DIR,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "SORTIE", "*.pyc", "*.so", "*.mod"),
    )
    console.print(f"[{theme.OK}]exemple recopié dans :[/] {destination}")
    console.print(f"[{theme.DISCRET}]lancez-le avec : bash {destination}/RUN_EXEMPLE.sh[/]")
    return EXIT_OK


# ---------------------------------------------------------------------------
# Résolution des arguments
# ---------------------------------------------------------------------------


def _specs(chemin: Path) -> dict[str, SpecTable]:
    try:
        return charger_fichier(chemin)
    except ErreurSpec as erreur:
        _echec(str(erreur), indice=_INDICE_TABLES)


def _module(designation: str) -> object:
    try:
        return resoudre_module(designation)
    except ErreurResolution as erreur:
        _echec(
            str(erreur),
            indice="`cfd-validation construire` compile un source en module importable.",
        )


def _modele(designation: str) -> Modele:
    try:
        modele = resoudre_objet(designation)
    except ErreurResolution as erreur:
        _echec(str(erreur), indice="Attendu « module:fonction », par exemple mon_appel:appeler.")
    if not callable(modele):
        _echec(f"« {designation} » n'est pas appelable (type {type(modele).__name__}).")
    appelable: Modele = modele
    return appelable


def _tracer(rapport: object, args: argparse.Namespace) -> None:
    """Le tracé est facultatif : il dépend de cfd-plot, qui peut manquer."""
    try:
        from cfd_validation.report.figures import tracer_rapport
    except ImportError as erreur:  # pragma: no cover - dépend de l'installation
        _echec(str(erreur))

    try:
        ecrits = tracer_rapport(
            rapport,  # type: ignore[arg-type]
            sortie=args.figures,
            formats=tuple(args.formats),
            max_valeurs=args.max_valeurs,
            verbeux=args.verbeux,
            a_blanc=args.a_blanc,
            n_jobs=args.n_jobs,
            seulement_fautives=args.seulement_fautives,
        )
    except ImportError as erreur:
        _echec(str(erreur))
    total = sum(len(fichiers) for fichiers in ecrits.values())
    verbe = "seraient écrites" if args.a_blanc else "écrites"
    console.print(f"[{theme.OK}]{total} planche(s) {verbe} dans[/] {args.figures}")


# ---------------------------------------------------------------------------
# Analyse des arguments
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments de la commande."""
    parser = argparse.ArgumentParser(
        prog="cfd-validation",
        description="Envelopper un code Fortran/C, contrôler qu'il relit ses tables, rapporter.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exemple :\n"
            "  cfd-validation valider --tables TABLES.yaml --module aero "
            "--modele mon_appel:appeler --figures FIGURE"
        ),
    )
    parser.add_argument("--version", action="version", version=f"cfd-validation {__version__}")
    sub = parser.add_subparsers(dest="commande", required=True)

    p = sub.add_parser("toolchain", help="État de la chaîne de compilation f2py.")
    p.set_defaults(func=cmd_toolchain)

    p = sub.add_parser("construire", help="Compiler des sources Fortran/C en module Python.")
    p.add_argument("sources", nargs="+", type=Path, help="fichiers .f, .f90 ou .c")
    p.add_argument("-m", "--nom", help="nom du module produit (défaut : celui de la 1re source)")
    p.add_argument("-o", "--sortie", type=Path, help="répertoire de destination")
    p.add_argument("--option", action="append", help="option passée telle quelle à f2py")
    p.set_defaults(func=cmd_construire)

    p = sub.add_parser("inspecter", help="Lister les COMMON blocks exposés par un module.")
    p.add_argument("--module", required=True, help="nom importable, ou chemin du .so")
    p.set_defaults(func=cmd_inspecter)

    p = sub.add_parser("check", help="Valider un fichier de tables, sans rien exécuter.")
    p.add_argument("--tables", type=Path, required=True, help="fichier TABLES.yaml")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("valider", help="Contrôler la relecture des tables, et rapporter.")
    p.add_argument("--tables", type=Path, required=True, help="fichier TABLES.yaml")
    p.add_argument("--module", required=True, help="module enveloppé : nom importable ou .so")
    p.add_argument("--modele", required=True, help="votre fonction, « module:fonction »")
    p.add_argument("--figures", type=Path, help="répertoire de sortie des planches")
    p.add_argument(
        "--formats",
        nargs="+",
        default=["png"],
        help="formats de figure (défaut : png)",
    )
    p.add_argument(
        "--max-valeurs",
        type=int,
        default=5,
        dest="max_valeurs",
        help="valeurs retenues par variable épinglée ; 0 pour toutes (défaut : 5)",
    )
    p.add_argument(
        "--seulement-fautives",
        action="store_true",
        dest="seulement_fautives",
        help="ne tracer que les tables qui ont des points hors tolérance",
    )
    p.add_argument("--verbeux", action="store_true", help="afficher le plan du tracé")
    p.add_argument("--a-blanc", action="store_true", dest="a_blanc", help="énumérer sans écrire")
    p.add_argument("--n-jobs", type=int, default=1, dest="n_jobs", help="processus de tracé")
    p.set_defaults(func=cmd_valider)

    p = sub.add_parser("exemple", help="Recopier l'exemple prêt à tourner.")
    p.add_argument("destination", type=Path, help="répertoire à créer")
    p.set_defaults(func=cmd_exemple)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée de la commande ``cfd-validation``."""
    args = build_parser().parse_args(argv)
    if getattr(args, "max_valeurs", None) == 0:
        # 0 veut dire « toutes » : argparse ne sait pas dire None sur la ligne.
        args.max_valeurs = None
    resultat: int = args.func(args)
    return resultat


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
