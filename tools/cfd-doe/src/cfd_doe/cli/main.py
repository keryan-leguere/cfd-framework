"""Interface en ligne de commande de cfd-doe.

::

    cfd-doe domaine ETUDE.yaml                 sous-domaines à calculer
    cfd-doe domaine ETUDE.yaml --verbose       … et la démarche qui y mène
    cfd-doe domaine --traj 6DOF --geometrie cruciforme \\
            --alpha -20 20 --beta -5 5 --dl -10 10 --dm -20 20 --dn -20 20
    cfd-doe check ETUDE.yaml                   le fichier tient-il debout ?
    cfd-doe exemple [DEST]                     recopier l'exemple

Les options priment sur le fichier : ``cfd-doe domaine ETUDE.yaml --repere
cartesien`` montre ce que coûterait de rester en (α, β).

Codes de retour : ``0`` succès, ``1`` erreur d'entrée.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

import yaml
from rich.console import Console

from cfd_doe import __version__
from cfd_doe.data.etude import (
    LIMITES_BRAQUAGE,
    REPERES,
    ErreurEtude,
    Etude,
    charger_etude,
    etude_depuis_dict,
    lire_plage,
)
from cfd_doe.data.geometries import GEOMETRIES
from cfd_doe.data.trajectoires import TRAJECTOIRES
from cfd_doe.engine.reduction import reduire, vers_dict
from cfd_doe.paths import EXEMPLE_DIR
from cfd_doe.report import theme
from cfd_doe.report.console import panneau_erreur, rapport_reduction

__all__ = ["build_parser", "main"]

EXIT_OK = 0
EXIT_ERREUR_ENTREE = 1

#: Option de ligne de commande → variable du fichier d'étude.
_OPTIONS_PLAGE = {"alpha": "alpha", "beta": "beta", "dl": "DL", "dm": "DM", "dn": "DN"}


class _Sortie:
    """Les consoles, recréées à chaque appel pour suivre ``sys.stdout`` (tests)."""

    def __init__(self) -> None:
        self.out = Console(highlight=False)
        self.err = Console(stderr=True, highlight=False)


def _echec(sortie: _Sortie, message: str, *, indice: str = "") -> NoReturn:
    sortie.err.print(panneau_erreur(message, indice=indice))
    sys.exit(EXIT_ERREUR_ENTREE)


# ---------------------------------------------------------------------------
# Construction de l'étude
# ---------------------------------------------------------------------------


def _etude(args: argparse.Namespace) -> Etude:
    """Fichier d'étude (s'il y en a un) puis surcharges de la ligne de commande."""
    if args.etude is not None:
        etude = charger_etude(args.etude)
        if args.traj or args.geometrie or args.n_ailettes:
            base = {
                "trajectoire": args.traj or etude.trajectoire.nom,
                "geometrie": _geometrie(args, etude.geometrie.nom, etude.geometrie.n_rotation),
            }
            refaite = etude_depuis_dict(base)
            etude = etude.avec(trajectoire=refaite.trajectoire, geometrie=refaite.geometrie)
    else:
        if not args.traj or not args.geometrie:
            raise ErreurEtude(
                "sans fichier d'étude, donner au moins --traj et --geometrie "
                "(et les plages : --alpha BAS HAUT, …)"
            )
        etude = etude_depuis_dict(
            {"trajectoire": args.traj, "geometrie": _geometrie(args, args.geometrie, None)}
        )

    plages = dict(etude.plages)
    for option, variable in _OPTIONS_PLAGE.items():
        valeur = getattr(args, option)
        if valeur is not None:
            plages[variable] = lire_plage(variable, list(valeur))
    changements: dict[str, object] = {"plages": plages}
    if args.repere:
        changements["repere"] = args.repere
    if args.limite_braquage:
        changements["limite_braquage"] = args.limite_braquage
    return etude.avec(**changements)


def _geometrie(args: argparse.Namespace, defaut: str, n_defaut: int | None) -> object:
    nom = args.geometrie or defaut
    if nom == "n_ailettes":
        return {"type": nom, "n_ailettes": args.n_ailettes or n_defaut}
    if args.n_ailettes:
        raise ErreurEtude("--n-ailettes ne s'emploie qu'avec --geometrie n_ailettes")
    return nom


# ---------------------------------------------------------------------------
# Sous-commandes
# ---------------------------------------------------------------------------


def cmd_domaine(args: argparse.Namespace, sortie: _Sortie) -> int:
    """Réduit le domaine et affiche les sous-domaines."""
    reduction = reduire(_etude(args))
    sortie.out.print(rapport_reduction(reduction, verbeux=args.verbose))
    if args.export is not None:
        chemin = Path(args.export)
        donnees = vers_dict(reduction)
        if chemin.suffix.lower() == ".json":
            chemin.write_text(json.dumps(donnees, indent=2, ensure_ascii=False) + "\n", "utf-8")
        else:
            chemin.write_text(
                yaml.safe_dump(donnees, sort_keys=False, allow_unicode=True), encoding="utf-8"
            )
        sortie.out.print(f"[{theme.OK}]écrit :[/] {chemin}")
    return EXIT_OK


def cmd_check(args: argparse.Namespace, sortie: _Sortie) -> int:
    """Valide un fichier d'étude sans rien calculer d'autre que la réduction."""
    etude = charger_etude(args.etude)
    reduction = reduire(etude)
    sortie.out.print(
        f"[{theme.OK}]✓[/] {etude.nom} [{theme.DISCRET}]— {etude.trajectoire.nom}, "
        f"{etude.geometrie.nom}, repère {reduction.repere}, "
        f"{len(reduction.sous_domaines)} sous-domaine(s)[/]"
    )
    for avert in reduction.avertissements:
        sortie.out.print(f"[{theme.ATTENTION}]! {avert}[/]")
    return EXIT_OK


def cmd_exemple(args: argparse.Namespace, sortie: _Sortie) -> int:
    """Recopie l'exemple livré avec le paquet."""
    destination = Path(args.destination)
    if destination.exists():
        raise ErreurEtude(f"{destination} existe déjà : choisir un autre dossier")
    shutil.copytree(EXEMPLE_DIR, destination, ignore=shutil.ignore_patterns("__pycache__"))
    sortie.out.print(f"[{theme.OK}]exemple copié dans[/] {destination}")
    sortie.out.print(
        f"[{theme.DISCRET}]essayer :[/] cfd-doe domaine {destination / 'ETUDE_FUSEE.yaml'}"
    )
    return EXIT_OK


# ---------------------------------------------------------------------------
# Analyse des arguments
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Le parseur complet."""
    parser = argparse.ArgumentParser(
        prog="cfd-doe",
        description="Plan d'expériences CFD : réduction du domaine par trajectoire et symétries.",
    )
    parser.add_argument("--version", action="version", version=f"cfd-doe {__version__}")
    sous = parser.add_subparsers(dest="commande", required=True, metavar="COMMANDE")

    domaine = sous.add_parser(
        "domaine",
        help="sous-domaines à calculer",
        description="Réduit le domaine (α, β, δl, δm, δn) selon la trajectoire et les symétries.",
    )
    domaine.add_argument("etude", nargs="?", type=Path, help="fichier d'étude YAML")
    domaine.add_argument(
        "--traj", metavar="TYPE", help=f"type de trajectoire : {', '.join(TRAJECTOIRES)}"
    )
    domaine.add_argument(
        "--geometrie",
        "--sym",
        dest="geometrie",
        metavar="GEO",
        help=f"géométrie : {', '.join([*GEOMETRIES, 'n_ailettes'])}",
    )
    domaine.add_argument(
        "--n-ailettes", type=int, metavar="N", help="nombre d'ailettes (n_ailettes)"
    )
    for option, variable in _OPTIONS_PLAGE.items():
        domaine.add_argument(
            f"--{option}",
            nargs=2,
            type=float,
            metavar=("BAS", "HAUT"),
            help=f"plage de {variable} (degrés)",
        )
    domaine.add_argument("--repere", choices=REPERES, help="repère de travail (défaut : auto)")
    domaine.add_argument(
        "--limite-braquage", choices=LIMITES_BRAQUAGE, help="limite (δm, δn) en polaire (§7.6)"
    )
    domaine.add_argument(
        "--export", metavar="FICHIER", help="écrire les sous-domaines (.yaml ou .json)"
    )
    domaine.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="détailler la démarche : trajectoire, repère, symétries, découpage en sous-domaines",
    )
    domaine.set_defaults(fonction=cmd_domaine)

    check = sous.add_parser("check", help="valider un fichier d'étude")
    check.add_argument("etude", type=Path)
    check.set_defaults(fonction=cmd_check)

    exemple = sous.add_parser("exemple", help="recopier l'exemple livré")
    exemple.add_argument("destination", nargs="?", default="cfd-doe-exemple")
    exemple.set_defaults(fonction=cmd_exemple)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée de ``cfd-doe``."""
    sortie = _Sortie()
    args = build_parser().parse_args(argv)
    try:
        code: int = args.fonction(args, sortie)
    except ErreurEtude as erreur:
        _echec(sortie, str(erreur), indice="Voir README.md, § « Fichier d'étude ».")
    return code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
