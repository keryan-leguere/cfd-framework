"""Interface en ligne de commande de cfd-traj.

Six commandes, dans l'ordre où on les emploie :

    cfd-traj generer      produire un lot de trajectoires synthétiques
    cfd-traj inspecter    comprendre ce qu'il y a dans les fichiers
    cfd-traj analyser     construire l'enveloppe conditionnelle
    cfd-traj doe          en tirer un plan d'expériences
    cfd-traj couverture   vérifier que le plan couvre bien les trajectoires
    cfd-traj example      copier l'exemple prêt à l'emploi

Le public est un ingénieur CFD, pas un développeur Python : une erreur d'entrée
sort sous forme de panneau rouge nommant le fichier et le problème, jamais sous
forme de trace d'appels.

Codes de retour : 0 succès, 1 erreur d'entrée, 2 la commande a abouti mais le
résultat exige une action (couverture incomplète, plan trop gros).
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

from cfd_traj.core.adim import Reference
from cfd_traj.data.columns import ColumnError, ColumnSpec, build_specs
from cfd_traj.data.dataset import DatasetError, TrajectoryDataset, load_dataset
from cfd_traj.data.derive import add_derived_columns
from cfd_traj.data.plan_io import (
    write_envelope_csv,
    write_offenders_csv,
    write_plan_csv,
    write_plan_yaml,
)
from cfd_traj.data.study import (
    DoeMethod,
    Study,
    StudyError,
    default_study,
    load_study,
    write_study,
)
from cfd_traj.engine.bands import build_bands
from cfd_traj.engine.coverage import check_coverage
from cfd_traj.engine.doe import PlanTooLarge, build_plan
from cfd_traj.engine.envelope import Envelope, build_envelope
from cfd_traj.engine.inspect import inspect
from cfd_traj.report import console as report

console = Console()
err_console = Console(stderr=True)

EXAMPLE_DIR = Path(__file__).resolve().parents[3] / "01_EXEMPLE"
SCHEMA_HINT = "Voir 00_DOC/03_FORMAT_ENTREE.md pour le schéma du fichier d'étude."

EXIT_OK = 0
EXIT_INPUT_ERROR = 1
EXIT_ACTION_REQUIRED = 2


def _fail(message: str, *, hint: str = "") -> NoReturn:
    """Panneau rouge puis sortie en code 1. Jamais de trace d'appels."""
    body = message if not hint else f"{message}\n\n[dim]{hint}[/]"
    err_console.print(Panel(body, title="[bold red]Erreur[/]", border_style="red"))
    sys.exit(EXIT_INPUT_ERROR)


def _load_study(path: str | Path) -> Study:
    """Charge une étude, ou échoue proprement."""
    try:
        return load_study(path)
    except StudyError as exc:
        _fail(str(exc), hint=SCHEMA_HINT)


def _load_dataset(source: str | Path, *, max_shots: int | None = None) -> TrajectoryDataset:
    """Charge un lot, ou échoue proprement."""
    try:
        return load_dataset(source, max_shots=max_shots)
    except DatasetError as exc:
        _fail(
            str(exc),
            hint="Chaque fichier doit porter les colonnes time, Mach, Altitude, "
            "alpha, beta, dl, dm, dn, puis autant de colonnes de paramètres "
            "que voulu, sous n'importe quels noms.",
        )


def _prepare(
    study: Study, *, source: str | Path | None = None, max_shots: int | None = None
) -> tuple[TrajectoryDataset, tuple[ColumnSpec, ...], tuple[str, ...]]:
    """Charge le lot, ajoute les colonnes dérivées, résout les rôles."""
    ds = _load_dataset(
        source if source is not None else study.resolved_source(), max_shots=max_shots
    )
    try:
        ds = add_derived_columns(
            ds,
            reference=study.reference,
            symmetry=study.symmetry,
            delta_t_k=study.delta_t_k,
        )
    except ValueError as exc:
        _fail(str(exc))
    try:
        specs, notes = build_specs(ds.columns, ds.column_values(), dict(study.declared_columns))
    except ColumnError as exc:
        _fail(str(exc), hint=SCHEMA_HINT)
    return ds, specs, (*ds.notes, *notes)


def _build_envelope(ds: TrajectoryDataset, study: Study, specs: Sequence[ColumnSpec]) -> Envelope:
    """Construit bandes puis enveloppe, ou échoue proprement."""
    try:
        band_set = build_bands(ds.values("Mach"), study.bands)
    except ValueError as exc:
        _fail(str(exc))
    return build_envelope(
        ds,
        band_set=band_set,
        specs=specs,
        spec=study.envelope,
        symmetry=study.symmetry,
    )


def _written(paths: Sequence[Path]) -> None:
    """Liste les fichiers produits."""
    if not paths:
        return
    body = "\n".join(f"[green]écrit[/] {p}" for p in paths)
    console.print(Panel(body, title="[bold]Sorties[/]", border_style="green"))


# --- generer ---------------------------------------------------------------


def cmd_generer(args: argparse.Namespace) -> int:
    """Produit un lot de trajectoires dispersées et son étude compagnon."""
    from cfd_traj.synth.lot import LotSpec, generate_lot, summarise, write_shot
    from cfd_traj.synth.parametres import ArchetypeError, default_models, parse_models

    try:
        if args.parametres:
            models = parse_models(args.parametres)
        else:
            models = default_models(args.n_parametres, prefix=args.prefixe_colonne)
    except (ArchetypeError, ValueError) as exc:
        _fail(str(exc))

    destination = Path(args.sortie)
    if destination.exists() and any(destination.glob("*.csv")):
        _fail(
            f"{destination} contient déjà des fichiers CSV",
            hint="Passez --sortie vers un répertoire neuf.",
        )

    try:
        spec = LotSpec(
            n_shots=args.n_tirs,
            seed=args.graine,
            dt=args.dt,
            dt_out=args.dt_sortie,
            t_max=args.t_max,
            prefix=args.prefixe,
            parameters=models,
        )
    except ValueError as exc:
        _fail(str(exc))

    shots = generate_lot(spec)
    destination.mkdir(parents=True, exist_ok=True)
    for shot in shots:
        write_shot(shot, destination / f"{shot.name}.csv")

    written = [destination]
    if not args.sans_etude:
        # A glob on the shot prefix, not "." : the study file lives next to the
        # CSVs, and a plain directory source would later swallow whatever the
        # tool itself writes there (a plan, an envelope) as if it were a shot.
        pattern = f"{spec.prefix}_*.csv"
        study = default_study(pattern, name=destination.name)
        study = Study(
            name=destination.name,
            source=pattern,
            output_dir="SORTIE",
            reference=Reference(length_m=2.5, area_m2=0.049),
            symmetry=study.symmetry,
            bands=study.bands,
            envelope=study.envelope,
            doe=study.doe,
        )
        written.append(
            write_study(
                study,
                destination / "ETUDE.yaml",
                header="# Étude compagnon générée par « cfd-traj generer ».\n"
                "# Les rôles des colonnes sont laissés à l'auto-détection :\n"
                "# lancez « cfd-traj inspecter » pour les voir et les figer ici.\n",
            )
        )

    stats = summarise(shots)
    body = (
        f"[green]{int(stats['n_shots'])} tirs[/] écrits dans [bold]{destination}[/]\n\n"
        f"[dim]points de vol[/]     {int(stats['n_rows'])}"
        f"  ({int(stats['rows_min'])} à {int(stats['rows_max'])} par tir)\n"
        f"[dim]colonnes[/]          {', '.join(spec.columns)}\n"
        f"[dim]apogée moyenne[/]    {stats['apogee_mean_m'] / 1000:.1f} km"
        f"  (dispersion {stats['apogee_std_m'] / max(stats['apogee_mean_m'], 1) * 100:.1f} %)\n"
        f"[dim]Mach maximal[/]      {stats['mach_max_max']:.2f}\n"
        f"[dim]graine[/]            {args.graine}"
    )
    console.print(Panel(body, title="[bold]Lot généré[/]", border_style="green"))
    _written(written)
    return EXIT_OK


# --- inspecter -------------------------------------------------------------


def cmd_inspecter(args: argparse.Namespace) -> int:
    """Décrit un lot : statistiques, corrélations, dimension intrinsèque."""
    source = Path(args.source)
    if source.suffix in (".yaml", ".yml"):
        study = _load_study(source)
        ds, specs, notes = _prepare(study, max_shots=args.max_tirs)
    else:
        study = _load_study(args.etude) if args.etude else default_study(source)
        ds, specs, notes = _prepare(study, source=source, max_shots=args.max_tirs)

    result = inspect(ds, specs=specs, pca_threshold=args.seuil_acp, with_pca=not args.sans_acp)
    report.print_report(report.render_inspection(result, specs, verbose=args.verbose), con=console)

    if notes and args.verbose:
        console.print(Panel("\n".join(f"• {n}" for n in notes), border_style="yellow"))

    if args.proposer:
        console.print(
            Panel(
                report.suggest_parameters_block(specs),
                title="[bold]Bloc « parametres » prêt à coller[/]",
                border_style="blue",
            )
        )

    written: list[Path] = []
    if args.csv:
        import pandas as pd

        target = Path(args.csv)
        target.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([s.as_row() for s in result.stats]).to_csv(
            target, index=False, float_format="%.10g"
        )
        written.append(target)
    if args.figure:
        from cfd_traj.report.figures import plot_inspection, save_figure

        written.append(save_figure(plot_inspection(result, title=study.name), args.figure))
    _written(written)
    return EXIT_OK


# --- analyser --------------------------------------------------------------


def cmd_analyser(args: argparse.Namespace) -> int:
    """Construit et affiche l'enveloppe conditionnelle."""
    study = _load_study(args.etude)
    ds, specs, notes = _prepare(study, max_shots=args.max_tirs)
    envelope = _build_envelope(ds, study, specs)

    report.print_report(report.render_study(study), con=console)
    report.print_report(report.render_symmetry(study.symmetry), con=console)
    report.print_report(report.render_envelope(envelope, verbose=args.verbose), con=console)

    if notes and args.verbose:
        console.print(Panel("\n".join(f"• {n}" for n in notes), border_style="yellow"))

    written: list[Path] = []
    if args.csv:
        written.append(write_envelope_csv(envelope.table_rows(), args.csv))
    if args.figure:
        from cfd_traj.report.figures import plot_envelope, save_figure

        written.append(save_figure(plot_envelope(ds, envelope, title=study.name), args.figure))
    _written(written)
    return EXIT_OK


# --- doe -------------------------------------------------------------------


def cmd_doe(args: argparse.Namespace) -> int:
    """Construit le plan d'expériences."""
    import dataclasses

    study = _load_study(args.etude)
    doe = study.doe
    if args.methode:
        doe = dataclasses.replace(doe, method=DoeMethod(args.methode))
    if args.graine is not None:
        doe = dataclasses.replace(doe, seed=args.graine)
    if args.noeuds_max is not None:
        doe = dataclasses.replace(doe, max_nodes=args.noeuds_max)
    if args.sans_coins:
        doe = dataclasses.replace(doe, include_corners=False)

    ds, specs, notes = _prepare(study, max_shots=args.max_tirs)
    envelope = _build_envelope(ds, study, specs)

    try:
        plan = build_plan(envelope, doe=doe, symmetry=study.symmetry, ds=ds)
    except PlanTooLarge as exc:
        err_console.print(
            Panel(
                f"{exc}\n\n"
                f"[dim]La grille tensorielle explose avec ce nombre d'axes. "
                f"Deux issues :[/]\n"
                f"  • [bold]--methode lhs[/] : hypercube latin, borné par bande\n"
                f"  • rétrograder des colonnes en « discret » ou « ignore » "
                f"dans la section « parametres » de l'étude",
                title="[bold yellow]Plan trop volumineux[/]",
                border_style="yellow",
            )
        )
        return EXIT_ACTION_REQUIRED

    report.print_report(report.render_plan(plan, verbose=args.verbose), con=console)

    if notes and args.verbose:
        console.print(Panel("\n".join(f"• {n}" for n in notes), border_style="yellow"))

    written: list[Path] = []
    target = Path(args.sortie) if args.sortie else study.resolved_output() / "PLAN.csv"
    written.append(write_plan_csv(plan.to_frame(), target))

    # Le classeur porte le taux de couverture dans sa feuille de synthèse : on
    # le calcule dès qu'un classeur est demandé, même sans --couverture, pour
    # que le livrable se suffise à lui-même.
    result = (
        check_coverage(ds, envelope=envelope, max_offenders=args.pires)
        if args.couverture or args.excel is not None
        else None
    )

    if args.yaml:
        written.append(write_plan_yaml(plan.to_yaml_payload(), args.yaml))
    if args.excel is not None:
        from cfd_traj.report.excel import write_plan_excel

        classeur = Path(args.excel) if args.excel else target.with_suffix(".xlsx")
        written.append(write_plan_excel(plan, study, classeur, coverage=result))
    if args.figure:
        from cfd_traj.report.figures import plot_plan, save_figure

        written.append(save_figure(plot_plan(plan, ds, title=study.name), args.figure))
    _written(written)

    if args.couverture and result is not None:
        report.print_report(
            report.render_coverage(result, worst=args.pires, verbose=args.verbose), con=console
        )
        if not result.is_complete:
            return EXIT_ACTION_REQUIRED
    return EXIT_OK


# --- couverture ------------------------------------------------------------


def cmd_couverture(args: argparse.Namespace) -> int:
    """Rejoue les trajectoires à travers l'enveloppe."""
    study = _load_study(args.etude)
    ds, specs, _ = _prepare(study, max_shots=args.max_tirs)
    envelope = _build_envelope(ds, study, specs)

    result = check_coverage(ds, envelope=envelope, max_offenders=max(args.pires, 200))
    report.print_report(
        report.render_coverage(result, worst=args.pires, verbose=args.verbose), con=console
    )

    written: list[Path] = []
    if args.csv:
        written.append(write_offenders_csv([o.as_row() for o in result.offenders], args.csv))
    if args.figure:
        from cfd_traj.report.figures import plot_coverage, save_figure

        written.append(save_figure(plot_coverage(result, title=study.name), args.figure))
    _written(written)

    return EXIT_OK if result.is_complete else EXIT_ACTION_REQUIRED


# --- example ---------------------------------------------------------------


def cmd_example(args: argparse.Namespace) -> int:
    """Copie l'exemple prêt à l'emploi dans un répertoire de travail."""
    dest = Path(args.output)
    if not EXAMPLE_DIR.is_dir():
        _fail(f"répertoire d'exemple introuvable : {EXAMPLE_DIR}")
    if dest.exists() and any(dest.iterdir()):
        _fail(
            f"{dest} existe déjà et n'est pas vide",
            hint="Passez --output vers un répertoire neuf.",
        )

    # On copie les entrées mais pas les figures de SORTIE/ : tout l'intérêt de
    # l'exemple est de le lancer et de les produire soi-même.
    shutil.copytree(
        EXAMPLE_DIR,
        dest,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("*.png", "*.svg", "*.pdf"),
    )
    (dest / "SORTIE").mkdir(exist_ok=True)
    console.print(
        Panel(
            f"[green]Exemple copié dans[/] [bold]{dest}[/]\n\n"
            f"[dim]Lancez-le avec :[/]\n"
            f"  cd {dest} && bash RUN_EXEMPLE.sh",
            title="[bold]Exemple[/]",
            border_style="green",
        )
    )
    return EXIT_OK


# --- analyse des arguments -------------------------------------------------


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-v", "--verbose", action="store_true", help="tableaux détaillés")
    parser.add_argument(
        "--max-tirs",
        type=int,
        default=None,
        dest="max_tirs",
        help="ne lire que les N premiers tirs",
    )


def build_parser() -> argparse.ArgumentParser:
    """Construit l'analyseur d'arguments complet."""
    parser = argparse.ArgumentParser(
        prog="cfd-traj",
        description="Réduire un lot de trajectoires dispersées à un plan de calcul CFD minimal.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("generer", help="produire un lot de trajectoires synthétiques")
    p.add_argument("--sortie", default="TRAJECTOIRES", help="répertoire des CSV produits")
    p.add_argument("--n-tirs", type=int, default=40, dest="n_tirs", help="nombre de tirs")
    p.add_argument("--graine", type=int, default=12345, help="graine de reproductibilité")
    p.add_argument("--dt", type=float, default=0.02, help="pas d'intégration (s)")
    p.add_argument(
        "--dt-sortie", type=float, default=0.25, dest="dt_sortie", help="pas d'échantillonnage (s)"
    )
    p.add_argument(
        "--t-max", type=float, default=400.0, dest="t_max", help="durée maximale simulée (s)"
    )
    p.add_argument(
        "--parametres",
        default="",
        help='colonnes génériques, ex. "PARA1:correle_mach,PRESSION:rampe"',
    )
    p.add_argument(
        "--n-parametres",
        type=int,
        default=2,
        dest="n_parametres",
        help="nombre de colonnes PARAn si --parametres n'est pas donné",
    )
    p.add_argument("--prefixe", default="tir", help="préfixe des noms de fichiers")
    p.add_argument(
        "--prefixe-colonne",
        default="PARA",
        dest="prefixe_colonne",
        help="préfixe des colonnes générées",
    )
    p.add_argument(
        "--sans-etude", action="store_true", dest="sans_etude", help="ne pas écrire ETUDE.yaml"
    )
    _add_common(p)
    p.set_defaults(func=cmd_generer)

    p = sub.add_parser("inspecter", help="décrire un lot de trajectoires")
    p.add_argument("source", help="répertoire, motif, ou fichier d'étude")
    p.add_argument("--etude", default="", help="étude fournissant les rôles déclarés")
    p.add_argument("--figure", default="", help="figure ACP et corrélations")
    p.add_argument("--csv", default="", help="export du tableau de statistiques")
    p.add_argument("--sans-acp", action="store_true", dest="sans_acp", help="sauter l'ACP")
    p.add_argument(
        "--seuil-acp", type=float, default=0.95, dest="seuil_acp", help="seuil de variance cumulée"
    )
    p.add_argument(
        "--proposer",
        action="store_true",
        help="afficher le bloc « parametres » prêt à coller dans l'étude",
    )
    _add_common(p)
    p.set_defaults(func=cmd_inspecter)

    p = sub.add_parser("analyser", help="construire l'enveloppe conditionnelle")
    p.add_argument("etude", help="fichier d'étude")
    p.add_argument("--figure", default="", help="figure du nuage et de l'enveloppe")
    p.add_argument("--csv", default="", help="export du tableau d'enveloppe")
    _add_common(p)
    p.set_defaults(func=cmd_analyser)

    p = sub.add_parser("doe", help="construire le plan d'expériences")
    p.add_argument("etude", help="fichier d'étude")
    p.add_argument(
        "--methode", choices=[m.value for m in DoeMethod], default="", help="surcharge doe.methode"
    )
    p.add_argument("--sortie", default="", help="fichier CSV du plan")
    p.add_argument("--yaml", default="", help="export YAML du plan, groupé par bande")
    p.add_argument(
        "--excel",
        nargs="?",
        const="",
        default=None,
        metavar="FICHIER",
        help="classeur Excel du plan (sans valeur : à côté du CSV, en .xlsx)",
    )
    p.add_argument("--figure", default="", help="figure des nœuds sur le nuage")
    p.add_argument("--graine", type=int, default=None, help="surcharge doe.graine")
    p.add_argument(
        "--noeuds-max", type=int, default=None, dest="noeuds_max", help="surcharge doe.noeuds_max"
    )
    p.add_argument(
        "--sans-coins", action="store_true", dest="sans_coins", help="ne pas ajouter les coins"
    )
    p.add_argument("--couverture", action="store_true", help="enchaîner le contrôle de couverture")
    p.add_argument("--pires", type=int, default=10, help="nombre de points fautifs listés")
    _add_common(p)
    p.set_defaults(func=cmd_doe)

    p = sub.add_parser("couverture", help="vérifier la couverture des trajectoires")
    p.add_argument("etude", help="fichier d'étude")
    p.add_argument("--figure", default="", help="figure de couverture par bande")
    p.add_argument("--csv", default="", help="export des points hors domaine")
    p.add_argument("--pires", type=int, default=20, help="nombre de points fautifs listés")
    _add_common(p)
    p.set_defaults(func=cmd_couverture)

    p = sub.add_parser("example", help="copier l'exemple prêt à l'emploi")
    p.add_argument("--output", default="cfd-traj-exemple", help="répertoire de destination")
    p.set_defaults(func=cmd_example)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée."""
    parser = build_parser()
    args = parser.parse_args(argv)
    exit_code: int = args.func(args)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
