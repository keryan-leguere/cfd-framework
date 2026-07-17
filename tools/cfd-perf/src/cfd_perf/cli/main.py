"""Interface en ligne de commande de cfd-perf.

    cfd-perf run ETUDE.yaml [--figure SORTIE.png] [--strategy ...] [-v]
    cfd-perf check ETUDE.yaml
    cfd-perf example [--output RÉP]

Les erreurs sont affichées comme un court panneau Rich nommant le fichier et le
problème, jamais une trace d'appels : le public est un ingénieur CFD qui
dimensionne un calcul, pas un développeur Python qui débogue cet outil.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from cfd_perf.core.model import ModelKind, fit_model
from cfd_perf.data.study import Study, StudyError, load_study
from cfd_perf.engine.recommend import Recommendation, Strategy, recommend
from cfd_perf.report.console import _STRATEGY_FR, _fr_int, print_report, render_pilot_warnings

console = Console()
err_console = Console(stderr=True)

EXAMPLE_DIR = Path(__file__).resolve().parents[3] / "01_EXEMPLE"

_SCHEMA_HINT = "Voir 00_DOC/03_FORMAT_ENTREE.md pour le schéma du fichier d'étude."


def _fail(message: str, *, hint: str = "") -> None:
    body = message
    if hint:
        body += f"\n\n[dim]{hint}[/]"
    err_console.print(Panel(body, title="[bold red]Erreur[/]", border_style="red"))
    sys.exit(1)


def _run_study(
    study: Study,
    *,
    strategy: Strategy | None,
    model_kind: ModelKind | None,
    deadline_hours: float | None = None,
    cores_max: int | None = None,
) -> Recommendation:
    """Ajuste et recommande, les options CLI l'emportant sur le fichier d'étude."""
    model = fit_model(study.pilot, kind=model_kind)
    obj = study.objective
    return recommend(
        model=model,
        mesh=study.mesh,
        pilot=study.pilot,
        machine=study.machine,
        constraints=study.constraints,
        strategy=strategy or obj.strategy,
        max_efficiency_loss=obj.max_efficiency_loss,
        deadline_hours=deadline_hours or obj.deadline_hours,
        cores_min=obj.cores_min,
        cores_max=cores_max or obj.cores_max,
    )


def cmd_run(args: argparse.Namespace) -> int:
    try:
        study = load_study(args.study)
    except StudyError as exc:
        _fail(str(exc), hint=_SCHEMA_HINT)

    strategy = Strategy(args.strategy) if args.strategy else None
    model_kind = ModelKind(args.model) if args.model else None

    try:
        rec = _run_study(
            study,
            strategy=strategy,
            model_kind=model_kind,
            deadline_hours=args.deadline,
            cores_max=args.cores_max,
        )
    except ValueError as exc:
        hint = ""
        if "deadline_hours est requis" in str(exc):
            hint = (
                "Passez --deadline HEURES, ou renseignez objective.deadline_hours "
                "dans le fichier d'étude."
            )
        _fail(str(exc), hint=hint)

    print_report(rec, study, verbose=args.verbose, con=console)

    if args.figure:
        try:
            from cfd_perf.report.figures import save_recommendation_figure
        except ImportError as exc:  # pragma: no cover - matplotlib toujours présent
            _fail(f"impossible d'importer le moteur de tracé : {exc}")
        path = save_recommendation_figure(
            rec, args.figure, title=f"{study.name}  --  sur combien de cœurs ?"
        )
        console.print(f"[dim]Figure écrite dans[/] [bold]{path}[/]\n")

    if rec.choice is None:
        return 2
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Valide un fichier d'étude et signale la qualité du pilote, sans recommander."""
    try:
        study = load_study(args.study)
    except StudyError as exc:
        _fail(str(exc), hint=_SCHEMA_HINT)

    console.print(
        Panel(
            f"[green]Fichier d'étude valide.[/]\n\n"
            f"[dim]nom       [/] {study.name}\n"
            f"[dim]maillage  [/] {_fr_int(study.mesh.num_cells)} mailles\n"
            f"[dim]pilote    [/] {len(study.pilot.points)} points, "
            f"{study.pilot.core_range[0]}-{study.pilot.core_range[1]} cœurs\n"
            f"[dim]stratégie [/] {_STRATEGY_FR[study.objective.strategy]}",
            title="[bold]Contrôle[/]",
            border_style="green",
        )
    )
    warn = render_pilot_warnings(study.pilot)
    if warn is not None:
        console.print(warn)
    return 0


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

    # On copie les entrées mais pas les figures générées de SORTIE/ : tout
    # l'intérêt de l'exemple est de le lancer et de les produire soi-même.
    shutil.copytree(
        EXAMPLE_DIR,
        dest,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("*.png", "*.svg", "*.pdf"),
    )
    (dest / "SORTIE").mkdir(exist_ok=True)
    study_file = next(dest.glob("*.yaml"), None)
    console.print(
        Panel(
            f"[green]Exemple copié dans[/] [bold]{dest}[/]\n\n"
            f"[dim]Lancez-le avec :[/]\n"
            f"  cfd-perf run {study_file or dest / 'ETUDE.yaml'} --figure scalabilite.png -v",
            title="[bold]Exemple[/]",
            border_style="green",
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cfd-perf",
        description="Sur combien de CPU lancer ma simulation CFD ?",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="répond à la question de dimensionnement d'une étude")
    p_run.add_argument("study", help="chemin du fichier d'étude YAML")
    p_run.add_argument("--figure", "-f", help="écrit aussi la figure de scalabilité ici")
    p_run.add_argument(
        "--strategy",
        choices=[s.value for s in Strategy],
        help="remplace objective.strategy du fichier d'étude",
    )
    p_run.add_argument(
        "--deadline",
        type=float,
        metavar="HEURES",
        help="échéance en temps d'horloge ; remplace objective.deadline_hours",
    )
    p_run.add_argument(
        "--cores-max",
        type=int,
        metavar="N",
        help="borne haute de la recherche de cœurs ; remplace objective.cores_max",
    )
    p_run.add_argument(
        "--model",
        choices=[k.value for k in ModelKind],
        help="force une forme de modèle au lieu du choix automatique",
    )
    p_run.add_argument(
        "--verbose", "-v", action="store_true", help="affiche aussi toute la courbe de scalabilité"
    )
    p_run.set_defaults(func=cmd_run)

    p_check = sub.add_parser("check", help="valide un fichier d'étude et signale la qualité du pilote")
    p_check.add_argument("study", help="chemin du fichier d'étude YAML")
    p_check.set_defaults(func=cmd_check)

    p_ex = sub.add_parser("example", help="copie ici l'exemple prêt à l'emploi")
    p_ex.add_argument(
        "--output", "-o", default="cfd-perf-exemple", help="répertoire de destination"
    )
    p_ex.set_defaults(func=cmd_example)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    exit_code: int = args.func(args)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
