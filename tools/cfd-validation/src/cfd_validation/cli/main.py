"""Interface en ligne de commande de cfd-validation.

::

    cfd-validation integration REF.csv TEST.csv --entrees Mach,alpha --sorties CN,Cm
    cfd-validation integration REF.csv TEST.csv --config INTEGRATION.yaml
    cfd-validation integration REF.parquet TEST.parquet --config INTEGRATION.yaml \\
        --rtol 1e-6 --sortie RESULTATS/INT-01 --sans-figures
    cfd-validation exemple [DEST]              recopier l'exemple

Les options priment sur le fichier de configuration.

Codes de retour : ``0`` conforme, ``1`` erreur d'entrée, ``2`` non conforme —
de quoi brancher le test dans une chaîne d'intégration continue.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, NoReturn

from rich.console import Console

from cfd_validation import __version__
from cfd_validation.data.lecture import ErreurLecture, lire_table, lire_yaml
from cfd_validation.data.specification import (
    ALIGNEMENTS,
    ErreurSpecification,
    specification_depuis_dict,
)
from cfd_validation.engine.integration import IDENTIFIANT_DEFAUT
from cfd_validation.integration import valider_integration
from cfd_validation.paths import EXEMPLE_DIR
from cfd_validation.report.console import LIGNES_MAX_TERMINAL, panneau_erreur
from cfd_validation.report.figures import FORMATS, PAR_ENTREE

__all__ = ["EXIT_ERREUR_ENTREE", "EXIT_NON_CONFORME", "EXIT_OK", "build_parser", "main"]

EXIT_OK = 0
EXIT_ERREUR_ENTREE = 1
EXIT_NON_CONFORME = 2


class _Sortie:
    """Les consoles, recréées à chaque appel pour suivre ``sys.stdout`` (tests)."""

    def __init__(self) -> None:
        self.out = Console(highlight=False)
        self.err = Console(stderr=True, highlight=False)


def _echec(sortie: _Sortie, message: str, *, indice: str = "") -> NoReturn:
    sortie.err.print(panneau_erreur(message, indice=indice))
    sys.exit(EXIT_ERREUR_ENTREE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cfd-validation",
        description="Vérification de code : tests tracés, pièces justificatives.",
    )
    parser.add_argument("--version", action="version", version=f"cfd-validation {__version__}")
    sous = parser.add_subparsers(dest="commande", required=True)

    p = sous.add_parser(
        "integration",
        help="comparer deux tables (référence, test) de mêmes entrées et sorties",
        description="Test d'intégration : le code exécuté ailleurs restitue-t-il les sorties de référence ?",
    )
    p.add_argument("reference", type=Path, help="table de référence (CSV, TSV, Parquet, Feather, pickle)")
    p.add_argument("test", type=Path, help="table à tester, même format")
    p.add_argument("-c", "--config", type=Path, help="fichier YAML : entrées, sorties, tolérances, traçabilité")
    p.add_argument("-e", "--entrees", help="colonnes d'entrée, séparées par des virgules")
    p.add_argument("-s", "--sorties", help="colonnes de sortie, séparées par des virgules")
    p.add_argument("--rtol", type=float, help="tolérance relative commune")
    p.add_argument("--atol", type=float, help="tolérance absolue commune")
    p.add_argument("--justification", help="justification de la tolérance commune")
    p.add_argument("--alignement", choices=ALIGNEMENTS, help="apparier sur les entrées (défaut) ou par position")
    p.add_argument("--chiffres-cle", type=int, help="arrondir les entrées à N chiffres significatifs avant appariement")
    p.add_argument("--identifiant", help=f"identifiant de l'exigence vérifiée (défaut {IDENTIFIANT_DEFAUT})")
    p.add_argument("--sep", help="séparateur des fichiers texte (défaut : selon l'extension)")
    p.add_argument("-o", "--sortie", type=Path, default=Path("VALIDATION_INTEGRATION"), help="dossier des pièces")
    p.add_argument("--sans-figures", action="store_true", help="ne pas tracer les figures")
    p.add_argument("--formats", default=",".join(FORMATS), help="formats des figures (défaut png,pdf)")
    p.add_argument("--figures-entrees", choices=PAR_ENTREE, default="echecs",
                   help="figures « marge selon chaque entrée » : sorties en échec (défaut), toutes, aucune")
    p.add_argument("--lignes", type=int, default=LIGNES_MAX_TERMINAL, help="lignes en échec listées au terminal (0 : toutes)")
    p.add_argument("--nettoyer", action="store_true", help="vider le dossier des pièces avant d'écrire")

    e = sous.add_parser("exemple", help="recopier l'exemple (script, configuration) dans DEST")
    e.add_argument("dest", nargs="?", type=Path, default=Path("01_EXEMPLE_VALIDATION"))
    return parser


def _config(args: argparse.Namespace) -> dict[str, Any]:
    """Le contenu du fichier de configuration, surchargé par les options."""
    contenu: dict[str, Any] = {}
    if args.config is not None:
        lu = lire_yaml(args.config)
        if not isinstance(lu, dict):
            raise ErreurSpecification(f"{args.config} doit contenir un dictionnaire YAML")
        contenu = dict(lu)
    if args.entrees:
        contenu["entrees"] = args.entrees
    if args.sorties:
        contenu["sorties"] = args.sorties
    if args.alignement:
        contenu["alignement"] = args.alignement
    if args.chiffres_cle is not None:
        contenu["chiffres_cle"] = args.chiffres_cle
    if args.identifiant:
        contenu["identifiant"] = args.identifiant
    if args.rtol is not None or args.atol is not None or args.justification:
        tol = dict(contenu.get("tolerances") or {})
        defaut = dict(tol.get("defaut") or {})
        if args.rtol is not None:
            defaut["rtol"] = args.rtol
        if args.atol is not None:
            defaut["atol"] = args.atol
        if args.justification:
            defaut["justification"] = args.justification
        tol["defaut"] = defaut
        contenu["tolerances"] = tol
    return contenu


def _integration(args: argparse.Namespace, sortie: _Sortie) -> int:
    try:
        spec, descriptif = specification_depuis_dict(_config(args))
    except (ErreurSpecification, ErreurLecture) as erreur:
        _echec(sortie, str(erreur), indice="Les entrées et sorties se déclarent par --entrees/--sorties ou dans --config.")
    try:
        reference = lire_table(args.reference, sep=args.sep)
        test = lire_table(args.test, sep=args.sep)
    except ErreurLecture as erreur:
        _echec(sortie, str(erreur))
    meta = dict(descriptif["metadonnees"])
    meta.setdefault("fichier référence", str(args.reference))
    meta.setdefault("fichier test", str(args.test))
    try:
        res = valider_integration(
            reference,
            test,
            specification=spec,
            identifiant=descriptif["identifiant"] or IDENTIFIANT_DEFAUT,
            description=descriptif["description"],
            metadonnees=meta,
            sortie=args.sortie,
            figures=not args.sans_figures,
            formats=tuple(f.strip() for f in args.formats.split(",") if f.strip()),
            figures_par_entree=args.figures_entrees,
            console=sortie.out,
            lignes_max=args.lignes or None,
            nettoyer=args.nettoyer,
        )
    except ErreurSpecification as erreur:
        _echec(sortie, str(erreur))
    return EXIT_OK if res.conforme else EXIT_NON_CONFORME


def _exemple(args: argparse.Namespace, sortie: _Sortie) -> int:
    dest: Path = args.dest
    if dest.exists():
        _echec(sortie, f"{dest} existe déjà", indice="Choisissez un autre dossier : rien n'est écrasé.")
    shutil.copytree(EXEMPLE_DIR, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    sortie.out.print(f"Exemple recopié dans [cyan]{dest}[/]. Pour le lancer :\n\n    cd {dest} && bash RUN_EXEMPLE.sh\n")
    return EXIT_OK


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sortie = _Sortie()
    if args.commande == "integration":
        return _integration(args, sortie)
    if args.commande == "exemple":
        return _exemple(args, sortie)
    raise AssertionError(args.commande)  # argparse l'interdit


if __name__ == "__main__":
    sys.exit(main())
