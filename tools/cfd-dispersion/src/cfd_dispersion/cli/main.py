"""Point d'entrée de la commande ``cfd-dispersion``."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any, NoReturn

from rich.console import Console

from .. import __version__
from ..core.lois import charger_lois_yaml
from ..core.tirage import tirer, tirer_tableau
from ..core.validation import valider_lot
from ..paths import EXEMPLE_DIR
from ..report import theme
from ..report.console import panneau_erreur, table_lois, table_tirage

console = Console()
err_console = Console(stderr=True)

__all__ = ["build_parser", "main"]


def _echec(message: str, *, indice: str = "") -> NoReturn:
    """Affiche une erreur encadrée et sort en code 1, sans trace d'exécution."""
    err_console.print(panneau_erreur(message, indice=indice))
    sys.exit(1)


def _charger(chemin: Path) -> Any:
    try:
        return charger_lois_yaml(chemin)
    except ValueError as erreur:
        _echec(str(erreur), indice="cfd-dispersion exemple pour obtenir un fichier de lois valide")


# ---------------------------------------------------------------------------
# Sous-commandes
# ---------------------------------------------------------------------------


def cmd_check(args: argparse.Namespace) -> int:
    """Valide un fichier de lois et en affiche le contenu."""
    lois = _charger(args.lois)
    console.print(table_lois(lois))
    console.print(f"[{theme.OK}]{len(lois)} coefficient(s) chargé(s) sans erreur.[/]")
    return 0


def cmd_tirage(args: argparse.Namespace) -> int:
    """Tire les lois, et écrit éventuellement le lot et les figures."""
    lois = _charger(args.lois)

    if args.n == 1:
        resultat = tirer(lois, graine=args.graine, methode=args.methode)
        console.print(table_tirage(resultat))
    else:
        lot = tirer_tableau(lois, args.n, graine=args.graine, methode=args.methode)
        console.print(
            f"[{theme.ACCENT}]{args.n} tirages[/] · plan {args.methode} · "
            f"graine {args.graine if args.graine is not None else 'libre'}"
        )
        console.print(lot.describe().to_string())
        if args.sortie:
            args.sortie.parent.mkdir(parents=True, exist_ok=True)
            lot.to_csv(args.sortie, index=False)
            console.print(f"[{theme.OK}]écrit :[/] {args.sortie}")

    if args.figures:
        _ecrire_figures_tirage(lois, args)
    return 0


def _ecrire_figures_tirage(lois: Any, args: argparse.Namespace) -> None:
    """Écrit une figure de tirage par coefficient."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from ..figures.tirage import figure_tirage

    resultat = tirer(lois, graine=args.graine, methode=args.methode)
    args.figures.mkdir(parents=True, exist_ok=True)
    for coefficient in lois:
        # Tracer et écrire ne font qu'un appel, et le fichier sort par le
        # gabarit d'export de cfd-plot — pas par un `savefig` de fortune.
        # Sans `nominal` : la ligne de commande ne connaît pas vos valeurs
        # nominales, et une loi de coefficient calculée sur un nominal inventé
        # serait un chiffre faux présenté comme un résultat. Le troisième
        # panneau le dit et reste vide.
        rendue = figure_tirage(
            coefficient,
            lois[coefficient],
            resultat,
            chemin=args.figures / f"tirage_{coefficient}",
        )
        plt.close(rendue.figure)
        for chemin in rendue.fichiers:
            console.print(f"[{theme.OK}]écrit :[/] {chemin}")


def cmd_valider(args: argparse.Namespace) -> int:
    """Valide une sortie de modèle contre ses lois, et rend la synthèse."""
    import pandas as pd

    lois = _charger(args.lois)
    if not args.donnees.is_file():
        _echec(f"fichier de données introuvable : {args.donnees}")

    tableau = pd.read_csv(args.donnees)
    par = tuple(args.par or ())

    try:
        verdicts = valider_lot(tableau, lois, par=par, alpha=args.alpha, correction=args.correction)
    except ValueError as erreur:
        _echec(str(erreur), indice="vérifier les colonnes du CSV et l'option --par")

    from ..figures.synthese import pdv_rejetes, table_rich

    console.print(table_rich(verdicts))

    rejetes = pdv_rejetes(verdicts)
    if rejetes:
        console.print(f"[{theme.ERREUR}]{len(rejetes)} point(s) de vol rejeté(s)[/] : {rejetes}")
    else:
        console.print(f"[{theme.OK}]Tous les points de vol sont validés.[/]")

    if args.sortie:
        args.sortie.parent.mkdir(parents=True, exist_ok=True)
        verdicts.to_csv(args.sortie, index=False)
        console.print(f"[{theme.OK}]écrit :[/] {args.sortie}")

    if args.figures:
        _ecrire_figures_synthese(verdicts, args)

    return 1 if rejetes and args.strict else 0


def _ecrire_figures_synthese(verdicts: Any, args: argparse.Namespace) -> None:
    """Écrit le damier de synthèse."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from ..figures.synthese import figure_synthese

    args.figures.mkdir(parents=True, exist_ok=True)
    figure, _ = figure_synthese(verdicts)
    chemin = args.figures / "synthese.png"
    figure.savefig(chemin, dpi=130, bbox_inches="tight")
    plt.close(figure)
    console.print(f"[{theme.OK}]écrit :[/] {chemin}")


def cmd_exemple(args: argparse.Namespace) -> int:
    """Recopie l'exemple exécutable livré avec le paquet."""
    destination = Path(args.destination)
    if destination.exists() and any(destination.iterdir()):
        _echec(
            f"le répertoire {destination} existe et n'est pas vide",
            indice="choisir une destination vide, ou la supprimer",
        )
    # Sans filtre, une exécution antérieure de l'exemple voyage avec lui : on
    # livrerait des figures déjà faites dans un répertoire censé être vierge.
    shutil.copytree(
        EXEMPLE_DIR,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "SORTIE", "*.pyc"),
    )
    console.print(f"[{theme.OK}]Exemple copié dans[/] {destination}")
    console.print(f"[{theme.DISCRET}]bash {destination}/RUN_EXEMPLE.sh[/]")
    return 0


# ---------------------------------------------------------------------------
# Analyse des arguments
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments de la commande."""
    parser = argparse.ArgumentParser(
        prog="cfd-dispersion",
        description="Lois de dispersion, tirage Monte-Carlo et validation, sur OpenTURNS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemple : cfd-dispersion tirage --lois LOIS.yaml -n 1000 --sortie lot.csv",
    )
    parser.add_argument("--version", action="version", version=f"cfd-dispersion {__version__}")
    sub = parser.add_subparsers(dest="commande", required=True)

    p = sub.add_parser("check", help="Vérifier un fichier de lois.")
    p.add_argument("--lois", type=Path, required=True, help="fichier LOIS.yaml")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("tirage", help="Tirer les lois.")
    p.add_argument("--lois", type=Path, required=True, help="fichier LOIS.yaml")
    p.add_argument("-n", type=int, default=1, help="nombre de tirages (défaut : 1)")
    p.add_argument("--graine", type=int, default=None, help="graine de reproductibilité")
    p.add_argument(
        "--methode",
        choices=("mc", "lhs", "sobol"),
        default="mc",
        help="plan d'échantillonnage (défaut : mc)",
    )
    p.add_argument("--sortie", type=Path, default=None, help="CSV où écrire le lot")
    p.add_argument("--figures", type=Path, default=None, help="répertoire des figures")
    p.set_defaults(func=cmd_tirage)

    p = sub.add_parser("valider", help="Valider une sortie de modèle contre ses lois.")
    p.add_argument("--lois", type=Path, required=True, help="fichier LOIS.yaml")
    p.add_argument("--donnees", type=Path, required=True, help="CSV de sortie du modèle")
    p.add_argument(
        "--par",
        nargs="*",
        default=None,
        help="colonnes définissant un point de vol (ex. : --par Mach Altitude_m)",
    )
    p.add_argument("--alpha", type=float, default=0.05, help="risque sur l'ensemble du tableau")
    p.add_argument(
        "--correction",
        choices=("sidak", "bonferroni", "aucune"),
        default="sidak",
        help="correction de multiplicité (défaut : sidak)",
    )
    p.add_argument("--sortie", type=Path, default=None, help="CSV où écrire les verdicts")
    p.add_argument("--figures", type=Path, default=None, help="répertoire des figures")
    p.add_argument(
        "--strict", action="store_true", help="sortir en code 1 si un point de vol est rejeté"
    )
    p.set_defaults(func=cmd_valider)

    p = sub.add_parser("exemple", help="Copier l'exemple exécutable.")
    p.add_argument(
        "destination", nargs="?", default="exemple_cfd_dispersion", help="répertoire cible"
    )
    p.set_defaults(func=cmd_exemple)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée de la commande ``cfd-dispersion``."""
    args = build_parser().parse_args(argv)
    if getattr(args, "correction", None) == "aucune":
        args.correction = None
    resultat: int = args.func(args)
    return resultat


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
