"""Interface en ligne de commande de cfd-nozzle.

Relations élémentaires :

    cfd-nozzle iso      --mach 2.5 | --rapport-section 4 --branche sup | --p0-p 10
    cfd-nozzle choc     --mach 3.0
    cfd-nozzle oblique  --mach 3.0 --theta 20 [--forte]
    cfd-nozzle detente  --mach 2.4 | --nu 30

Tuyère et géométrie :

    cfd-nozzle tuyere    --p0 100e5 --t0 3500 --pa 1.013e5 --diametre-col 0.2 --eps 16
    cfd-nozzle run       CAS.yaml [--figure RÉP]
    cfd-nozzle check     CAS.yaml
    cfd-nozzle geometrie --rayon-col 0.05 --eps 16 [--type conique] [--export c.dat]
    cfd-nozzle moc       --mach-sortie 2.4 [--axisymetrique] [--export c.dat]
    cfd-nozzle example   [RÉP]

Les erreurs sont affichées comme un court panneau Rich nommant le problème,
jamais une trace d'appels : le public est un ingénieur CFD qui dimensionne une
tuyère, pas un développeur Python qui débogue cet outil.
"""

from __future__ import annotations

import argparse
import math
import shutil
import sys
from pathlib import Path
from typing import NoReturn

import numpy as np
from rich.console import Console
from rich.panel import Panel

from cfd_nozzle import __version__
from cfd_nozzle.core.gas import GAS_LIBRARY, GasModel
from cfd_nozzle.core.geometry import NozzleContour, bell_contour, conical_contour
from cfd_nozzle.core.isentropic import (
    Branch,
    isentropic_state,
    mach_angle,
    mach_from_area_ratio,
    mach_from_p0_over_p,
)
from cfd_nozzle.core.moc import moc_nozzle
from cfd_nozzle.core.nozzle import Nozzle
from cfd_nozzle.core.shocks import (
    mach_from_prandtl_meyer,
    normal_shock_state,
    nu_max,
    oblique_shock,
    prandtl_meyer,
    shock_entropy_rise,
    theta_max_oblique,
)
from cfd_nozzle.data.case import CaseError, load_case
from cfd_nozzle.paths import EXEMPLE_DIR
from cfd_nozzle.report import console as report
from cfd_nozzle.report import theme

console = Console()
err_console = Console(stderr=True)

_SCHEMA_HINT = (
    "Schéma du fichier de cas : « cfd-nozzle example » en produit un valide, "
    "commenté et prêt à modifier."
)


def _fail(message: str, *, hint: str = "") -> NoReturn:
    body = message
    if hint:
        body += f"\n\n[{theme.DISCRET}]{hint}[/]"
    err_console.print(Panel(body, title=f"[{theme.ERREUR}]Erreur[/]", border_style="red"))
    sys.exit(1)


def _gas_from_args(args: argparse.Namespace) -> GasModel:
    """Resolve the gas: a library entry, overridden by explicit γ / R."""
    name = getattr(args, "gaz", None)
    gamma = getattr(args, "gamma", None)
    r = getattr(args, "r", None)
    if name is not None:
        base = GAS_LIBRARY[name]
        return GasModel(gamma if gamma is not None else base.gamma, r if r is not None else base.r, base.name)
    return GasModel(gamma if gamma is not None else 1.4, r if r is not None else 287.05, "personnalisé")


def _export_contour(path: Path, x: np.ndarray, y: np.ndarray, header: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savetxt(path, np.column_stack([x, y]), header=header, comments="# ")
    console.print(f"[{theme.OK}]Contour exporté[/] [{theme.DISCRET}]{path}[/]")


def _save(fig: object, base: Path) -> None:
    from cfd_nozzle.report.figures import save_figure

    for written in save_figure(fig, base):
        console.print(f"[{theme.OK}]Figure écrite[/] [{theme.DISCRET}]{written}[/]")


# --- elementary relations -------------------------------------------------


def cmd_iso(args: argparse.Namespace) -> int:
    gas = _gas_from_args(args)
    try:
        if args.mach is not None:
            mach = args.mach
        elif args.rapport_section is not None:
            branch: Branch = "sup" if args.branche == "sup" else "sub"
            mach = mach_from_area_ratio(args.rapport_section, gas.gamma, branch)
        elif args.p0_p is not None:
            mach = mach_from_p0_over_p(args.p0_p, gas.gamma)
        else:
            _fail("Donner « --mach », « --rapport-section » ou « --p0-p ».")
        report.print_isentropic_report(console, isentropic_state(mach, gas.gamma))
    except ValueError as exc:
        _fail(str(exc))
    report.print_gas_line(console, gas)
    return 0


def cmd_choc(args: argparse.Namespace) -> int:
    gas = _gas_from_args(args)
    try:
        state = normal_shock_state(args.mach, gas.gamma)
        rise = shock_entropy_rise(args.mach, gas)
    except ValueError as exc:
        _fail(str(exc))
    report.print_normal_shock_report(console, state, rise)
    report.print_gas_line(console, gas)
    return 0


def cmd_oblique(args: argparse.Namespace) -> int:
    gas = _gas_from_args(args)
    try:
        theta_max, _ = theta_max_oblique(args.mach, gas.gamma)
        state = oblique_shock(args.mach, math.radians(args.theta), gas.gamma, weak=not args.forte)
    except ValueError as exc:
        _fail(str(exc))
    report.print_oblique_shock_report(console, state, math.degrees(theta_max))
    report.print_gas_line(console, gas)
    return 0


def cmd_detente(args: argparse.Namespace) -> int:
    gas = _gas_from_args(args)
    try:
        if args.mach is not None:
            mach = args.mach
            nu = prandtl_meyer(mach, gas.gamma)
        elif args.nu is not None:
            nu = math.radians(args.nu)
            mach = mach_from_prandtl_meyer(nu, gas.gamma)
        else:
            _fail("Donner « --mach » ou « --nu ».")
        report.print_prandtl_meyer_report(
            console,
            mach,
            math.degrees(nu),
            math.degrees(mach_angle(mach)),
            math.degrees(nu_max(gas.gamma)),
            gas.gamma,
        )
    except ValueError as exc:
        _fail(str(exc))
    report.print_gas_line(console, gas)
    return 0


# --- nozzle ---------------------------------------------------------------


def _build_contour(
    throat_radius: float, area_ratio: float, kind: str, pct: float, half_angle: float
) -> NozzleContour:
    if kind == "bell":
        return bell_contour(throat_radius, area_ratio, pct)
    return conical_contour(throat_radius, area_ratio, half_angle)


def cmd_tuyere(args: argparse.Namespace) -> int:
    gas = _gas_from_args(args)
    if (args.diametre_col is None) == (args.aire_col is None):
        _fail("Donner « --diametre-col » [m] OU « --aire-col » [m²].")
    throat_area = (
        0.25 * math.pi * args.diametre_col**2 if args.diametre_col is not None else args.aire_col
    )
    try:
        contour = _build_contour(
            math.sqrt(throat_area / math.pi), args.eps, args.type, args.pourcentage, args.demi_angle
        )
        nozzle = Nozzle(
            throat_area,
            args.eps,
            gas,
            eta_cstar=args.eta_cstar,
            lambda_div=contour.divergence_lambda if args.lambda_contour else 1.0,
        )
        state = nozzle.solve(args.p0, args.t0, args.pa)
    except ValueError as exc:
        _fail(str(exc))
    report.print_nozzle_report(console, nozzle, state, contour=contour)
    if args.figure:
        from cfd_nozzle.report.figures import plot_flow_field, plot_performance_map

        base = Path(args.figure)
        field = nozzle.flow_field(contour.x, contour.area, args.p0, args.t0, args.pa)
        _save(plot_flow_field(contour, field), base / "champ_tuyere")
        _save(
            plot_performance_map(nozzle, args.p0, args.t0, max(args.pa * 0.01, 1.0), args.pa * 2.0),
            base / "carte_performance",
        )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    try:
        case = load_case(args.cas)
        contour = case.build_contour()
        nozzle = case.build_nozzle(contour)
        state = nozzle.solve(case.p0, case.t0, case.pa)
    except CaseError as exc:
        _fail(str(exc), hint=_SCHEMA_HINT)
    except ValueError as exc:
        _fail(str(exc))
    console.print(f"[{theme.TITRE}]Cas :[/] {case.name} [{theme.DISCRET}]({case.source})[/]")
    report.print_nozzle_report(console, nozzle, state, contour=contour)
    if args.figure:
        from cfd_nozzle.report.figures import plot_flow_field, plot_performance_map

        base = Path(args.figure)
        field = nozzle.flow_field(contour.x, contour.area, case.p0, case.t0, case.pa)
        _save(plot_flow_field(contour, field, title=f"{case.name} — champ quasi-1D"), base / "champ_tuyere")
        _save(
            plot_performance_map(nozzle, case.p0, case.t0, max(case.pa * 0.01, 1.0), case.pa * 2.0),
            base / "carte_performance",
        )
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    try:
        case = load_case(args.cas)
        contour = case.build_contour()
        nozzle = case.build_nozzle(contour)
        nozzle.solve(case.p0, case.t0, case.pa)
    except CaseError as exc:
        _fail(str(exc), hint=_SCHEMA_HINT)
    except ValueError as exc:
        _fail(str(exc))
    console.print(
        Panel(
            f"[{theme.OK}]Fichier de cas valide[/] — {case.name}\n\n"
            f"[{theme.DISCRET}]gaz {case.gas.name} · ε = {case.area_ratio:g} · "
            f"D_col = {2 * math.sqrt(case.throat_area / math.pi) * 1e3:.2f} mm · "
            f"contour {contour.label}[/]",
            title=f"[{theme.TITRE}]cfd-nozzle check[/]",
            border_style="green",
        )
    )
    return 0


def cmd_geometrie(args: argparse.Namespace) -> int:
    try:
        contour = _build_contour(
            args.rayon_col, args.eps, args.type, args.pourcentage, args.demi_angle
        )
    except ValueError as exc:
        _fail(str(exc))
    report.print_contour_report(console, contour)
    if args.export:
        _export_contour(Path(args.export), contour.x, contour.r, "x [m]   r [m]")
    if args.figure:
        from cfd_nozzle.report.figures import plot_contour

        _save(plot_contour(contour), Path(args.figure) / "contour")
    return 0


def cmd_moc(args: argparse.Namespace) -> int:
    try:
        result = moc_nozzle(
            args.mach_sortie,
            args.n,
            args.rayon_col,
            args.gamma if args.gamma is not None else 1.4,
            axisymmetric=args.axisymetrique,
        )
    except (ValueError, RuntimeError) as exc:
        _fail(str(exc))
    report.print_moc_report(console, result)
    if args.export:
        _export_contour(
            Path(args.export),
            result.wall_x,
            result.wall_y,
            f"x   y   (paroi MOC, {result.label}, Me = {result.mach_exit:g})",
        )
    if args.figure:
        from cfd_nozzle.report.figures import plot_moc

        _save(plot_moc(result, show_mesh=not args.sans_maillage), Path(args.figure) / "moc")
    return 0


def cmd_example(args: argparse.Namespace) -> int:
    destination = Path(args.destination)
    if destination.exists() and any(destination.iterdir()):
        _fail(f"« {destination} » existe déjà et n'est pas vide.")
    try:
        shutil.copytree(EXEMPLE_DIR, destination, dirs_exist_ok=True)
    except OSError as exc:
        _fail(f"copie impossible : {exc}")
    console.print(f"[{theme.OK}]Exemple copié[/] [{theme.DISCRET}]{destination}[/]")
    console.print(f"[{theme.DISCRET}]Lancer :[/] cd {destination} && bash RUN_EXEMPLE.sh")
    return 0


# --- parser ---------------------------------------------------------------


def _add_gas_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--gaz", choices=sorted(GAS_LIBRARY), help="gaz de la bibliothèque")
    parser.add_argument("--gamma", type=float, help="rapport cp/cv (surcharge --gaz)")
    parser.add_argument("--r", type=float, help="constante du gaz [J/(kg·K)] (surcharge --gaz)")


def _add_contour_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--type", default="bell", choices=["bell", "conique"], help="type de contour")
    parser.add_argument("--pourcentage", type=float, default=80.0, help="longueur du galbe [%%] (bell)")
    parser.add_argument("--demi-angle", type=float, default=15.0, help="demi-angle du cône [°]")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cfd-nozzle",
        description="Boîte à outils quasi-1D pour les tuyères convergentes-divergentes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Exemple : cfd-nozzle tuyere --p0 100e5 --t0 3500 --pa 1.013e5 "
        "--diametre-col 0.2 --eps 16 --gaz lox_rp1",
    )
    parser.add_argument("--version", action="version", version=f"cfd-nozzle {__version__}")
    sub = parser.add_subparsers(dest="commande", required=True)

    p = sub.add_parser("iso", help="Relations isentropiques.")
    p.add_argument("--mach", type=float)
    p.add_argument("--rapport-section", type=float, help="A/A*")
    p.add_argument("--p0-p", type=float, help="rapport p₀/p")
    p.add_argument("--branche", default="sub", choices=["sub", "sup"], help="racine de A/A*")
    _add_gas_options(p)
    p.set_defaults(func=cmd_iso)

    p = sub.add_parser("choc", help="Choc droit.")
    p.add_argument("--mach", type=float, required=True, help="Mach amont")
    _add_gas_options(p)
    p.set_defaults(func=cmd_choc)

    p = sub.add_parser("oblique", help="Choc oblique (relation θ-β-M).")
    p.add_argument("--mach", type=float, required=True, help="Mach amont")
    p.add_argument("--theta", type=float, required=True, help="déviation [°]")
    p.add_argument("--forte", action="store_true", help="solution forte au lieu de la faible")
    _add_gas_options(p)
    p.set_defaults(func=cmd_oblique)

    p = sub.add_parser("detente", help="Détente de Prandtl-Meyer.")
    p.add_argument("--mach", type=float)
    p.add_argument("--nu", type=float, help="angle de détente [°]")
    _add_gas_options(p)
    p.set_defaults(func=cmd_detente)

    p = sub.add_parser("tuyere", help="Analyse complète d'un point de fonctionnement.")
    p.add_argument("--p0", type=float, required=True, help="pression totale [Pa]")
    p.add_argument("--t0", type=float, required=True, help="température totale [K]")
    p.add_argument("--pa", type=float, required=True, help="pression ambiante [Pa]")
    p.add_argument("--diametre-col", type=float, help="diamètre au col [m]")
    p.add_argument("--aire-col", type=float, help="aire au col [m²]")
    p.add_argument("--eps", type=float, required=True, help="ε = Ae/At")
    p.add_argument("--eta-cstar", type=float, default=1.0, help="rendement de combustion")
    p.add_argument(
        "--lambda-contour",
        action="store_true",
        help="appliquer la perte par divergence déduite du contour",
    )
    p.add_argument("--figure", help="répertoire de sortie des figures")
    _add_contour_options(p)
    _add_gas_options(p)
    p.set_defaults(func=cmd_tuyere)

    p = sub.add_parser("run", help="Analyser un fichier de cas YAML.")
    p.add_argument("cas", help="fichier de cas")
    p.add_argument("--figure", help="répertoire de sortie des figures")
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("check", help="Valider un fichier de cas YAML.")
    p.add_argument("cas", help="fichier de cas")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("geometrie", help="Générer un contour conique ou galbé.")
    p.add_argument("--rayon-col", type=float, required=True, help="rayon au col [m]")
    p.add_argument("--eps", type=float, required=True, help="ε = Ae/At")
    p.add_argument("--export", help="fichier .dat du contour")
    p.add_argument("--figure", help="répertoire de sortie des figures")
    _add_contour_options(p)
    p.set_defaults(func=cmd_geometrie)

    p = sub.add_parser("moc", help="Tuyère à longueur minimale par la méthode des caractéristiques.")
    p.add_argument("--mach-sortie", type=float, required=True, help="Mach de sortie visé")
    p.add_argument("--n", type=int, default=30, help="nombre de caractéristiques")
    p.add_argument("--rayon-col", type=float, default=1.0, help="rayon (ou demi-hauteur) au col")
    p.add_argument("--gamma", type=float, help="rapport cp/cv (défaut 1.4)")
    p.add_argument(
        "--axisymetrique", action="store_true", help="tuyère de révolution (défaut : plane)"
    )
    p.add_argument("--export", help="fichier .dat du contour")
    p.add_argument("--figure", help="répertoire de sortie des figures")
    p.add_argument("--sans-maillage", action="store_true", help="ne pas tracer les caractéristiques")
    p.set_defaults(func=cmd_moc)

    p = sub.add_parser("example", help="Copier l'exemple exécutable.")
    p.add_argument("destination", nargs="?", default="exemple_cfd_nozzle", help="répertoire cible")
    p.set_defaults(func=cmd_example)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point of the ``cfd-nozzle`` command."""
    args = build_parser().parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
