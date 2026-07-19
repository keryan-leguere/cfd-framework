"""cfd-atm command line interface.

Subcommands:

- ``point``     : resolve one atmospheric point and print the full report;
- ``diagramme`` : generate the iso-Vc / iso-TAS figures;
- ``example``   : copy the runnable example out of the package.

Errors are reported as a Rich panel (never a traceback): the audience is a
flight-mechanics / CFD engineer, not a Python developer.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import NoReturn

import yaml
from rich.console import Console

from cfd_atm.core.airspeed import AirspeedSet, airspeeds
from cfd_atm.core.atmosphere import AtmosphereModel, temperature_profile_from_table
from cfd_atm.report import units
from cfd_atm.report.console import print_point_report

console = Console()
err_console = Console(stderr=True)

EXAMPLE_DIR = Path(__file__).resolve().parents[3] / "01_EXEMPLE"


def _fail(message: str, *, hint: str = "") -> NoReturn:
    from rich.panel import Panel

    body = message if not hint else f"{message}\n\n[dim]{hint}[/]"
    err_console.print(Panel(body, title="[bold red]Erreur[/]", border_style="red"))
    sys.exit(1)


def _load_custom_model(path: Path) -> AtmosphereModel:
    """Load a custom temperature profile from a YAML file.

    Expected shape::

        nom: "profil custom"
        profil:
          - { altitude_m: 0,     temperature_K: 300.0 }
          - { altitude_m: 11000, temperature_K: 210.0 }
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        _fail(f"Lecture du profil impossible : {exc}")
    rows = data.get("profil") if isinstance(data, dict) else None
    if not rows:
        _fail("Le fichier de profil ne contient pas de clé 'profil'.")
    try:
        h = [float(r["altitude_m"]) for r in rows]
        t = [float(r["temperature_K"]) for r in rows]
    except (KeyError, TypeError, ValueError) as exc:
        _fail(f"Profil mal formé (altitude_m / temperature_K attendus) : {exc}")
    label = str(data.get("nom", "custom")) if isinstance(data, dict) else "custom"
    return AtmosphereModel.custom(temperature_profile_from_table(h, t), label=label)


def _build_model(args: argparse.Namespace) -> AtmosphereModel:
    if args.modele == "ISA":
        return AtmosphereModel.isa()
    if args.modele == "ISA+X":
        return AtmosphereModel.isa_offset(args.dt)
    if args.modele == "custom":
        if not args.profil:
            _fail("Le modèle 'custom' requiert --profil FICHIER.yaml.")
        return _load_custom_model(Path(args.profil))
    _fail(f"Modèle inconnu : {args.modele}")


def _resolve_speed(args: argparse.Namespace, model: AtmosphereModel, state) -> AirspeedSet | None:  # type: ignore[no-untyped-def]
    if args.vitesse is None:
        return None
    value = args.vitesse
    if args.grandeur == "mach":
        return airspeeds(state.p, state.t, mach=value)
    speed_mps = units.knots_to_mps(value) if args.unite_vitesse == "kt" else value
    kwargs = {args.grandeur: speed_mps}
    return airspeeds(state.p, state.t, **kwargs)


def cmd_point(args: argparse.Namespace) -> int:
    model = _build_model(args)
    alt_m = units.feet_to_metres(args.altitude) if args.unite_altitude == "ft" else args.altitude

    if args.nature == "geometrique":
        state = model.state_from_geometric(alt_m)
    elif args.nature == "geopotentielle":
        state = model.state_from_geopotential(alt_m)
    else:
        state = model.state_from_pressure_altitude(alt_m)

    speeds = _resolve_speed(args, model, state)
    entry = f"{args.altitude:g} {args.unite_altitude} ({args.nature})"
    print_point_report(console, state, model_label=model.label, entry=entry, speeds=speeds)
    return 0


def cmd_diagramme(args: argparse.Namespace) -> int:
    from cfd_atm.report.figures import generer_diagrammes

    custom = _load_custom_model(Path(args.profil)) if args.profil else None
    sortie = Path(args.sortie)
    written = generer_diagrammes(sortie, custom=custom)
    console.print(f"[green]{len(written)} fichiers écrits dans[/] {sortie} :")
    for path in written:
        console.print(f"  [dim]•[/] {path.name}")
    return 0


def cmd_example(args: argparse.Namespace) -> int:
    dest = Path(args.destination)
    if dest.exists() and any(dest.iterdir()):
        _fail(f"La destination existe et n'est pas vide : {dest}")
    shutil.copytree(
        EXAMPLE_DIR,
        dest,
        ignore=shutil.ignore_patterns("*.png", "*.svg", "*.pdf", "SORTIE"),
        dirs_exist_ok=True,
    )
    console.print(f"[green]Exemple copié dans[/] {dest}")
    console.print(f"[dim]Lancer :[/] cd {dest} && bash RUN_EXEMPLE.sh")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cfd-atm", description="Modèle d'atmosphère et grandeurs de vitesse.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_point = sub.add_parser("point", help="Résoudre un point atmosphérique.")
    p_point.add_argument("--altitude", type=float, required=True, help="Valeur de l'altitude.")
    p_point.add_argument(
        "--nature",
        choices=["geometrique", "geopotentielle", "pression"],
        default="pression",
        help="Nature de l'altitude d'entrée (défaut : pression).",
    )
    p_point.add_argument("--unite-altitude", choices=["ft", "m"], default="ft")
    p_point.add_argument("--modele", choices=["ISA", "ISA+X", "custom"], default="ISA")
    p_point.add_argument("--dt", type=float, default=0.0, help="Écart ΔT pour ISA+X (K).")
    p_point.add_argument("--profil", help="Fichier YAML de profil T° custom.")
    p_point.add_argument("--vitesse", type=float, help="Valeur de la vitesse d'entrée.")
    p_point.add_argument(
        "--grandeur", choices=["mach", "cas", "eas", "tas"], default="cas", help="Type de vitesse fournie."
    )
    p_point.add_argument("--unite-vitesse", choices=["kt", "ms"], default="kt")
    p_point.set_defaults(func=cmd_point)

    p_diag = sub.add_parser("diagramme", help="Générer les figures iso-Vc / iso-TAS.")
    p_diag.add_argument("--sortie", default="SORTIE", help="Répertoire de sortie des figures.")
    p_diag.add_argument("--profil", help="Fichier YAML de profil T° custom (facultatif).")
    p_diag.set_defaults(func=cmd_diagramme)

    p_ex = sub.add_parser("example", help="Copier l'exemple exécutable.")
    p_ex.add_argument("destination", help="Répertoire de destination.")
    p_ex.set_defaults(func=cmd_example)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    sys.exit(main())
