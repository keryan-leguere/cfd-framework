"""Interface en ligne de commande de cfd-perf.

    cfd-perf run ETUDE.yaml [--figure SORTIE.png] [--strategy ...] [-v]
    cfd-perf check ETUDE.yaml
    cfd-perf example [--output RÉP]
    cfd-perf shim [--output RÉP]

Les erreurs sont affichées comme un court panneau Rich nommant le fichier et le
problème, jamais une trace d'appels : le public est un ingénieur CFD qui
dimensionne un calcul, pas un développeur Python qui débogue cet outil.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import NoReturn

from rich.console import Console
from rich.panel import Panel

from cfd_perf.capture import BashAdapter, CaptureError, MachineOverrides, collect, submit
from cfd_perf.capture.study_writer import ObjectiveSpec
from cfd_perf.cli import shim
from cfd_perf.core.model import ModelKind, fit_model
from cfd_perf.data.study import Study, StudyError, load_study
from cfd_perf.engine.recommend import (
    DEFAULT_MAX_EFFICIENCY_LOSS,
    Recommendation,
    Strategy,
    recommend,
)
from cfd_perf.paths import EXEMPLE_DIR
from cfd_perf.report import theme
from cfd_perf.report.console import _STRATEGY_FR, _fr_int, print_report, render_pilot_warnings

console = Console()
err_console = Console(stderr=True)

_SCHEMA_HINT = (
    "Schéma du fichier d'étude : « cfd-perf example » en produit un valide, "
    "commenté et prêt à modifier."
)


def _fail(message: str, *, hint: str = "") -> NoReturn:
    body = message
    if hint:
        body += f"\n\n[dim]{hint}[/]"
    err_console.print(Panel(body, title=f"[{theme.ERREUR}]Erreur[/]", border_style="red"))
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
        console.print(f"[dim]Figure écrite dans[/] [{theme.VALEUR}]{path}[/]\n")

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
            title=f"[{theme.TITRE}]Contrôle[/]",
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
    if not EXEMPLE_DIR.is_dir():
        _fail(f"répertoire d'exemple introuvable : {EXEMPLE_DIR}")
    if dest.exists() and any(dest.iterdir()):
        _fail(
            f"{dest} existe déjà et n'est pas vide",
            hint="Passez --output vers un répertoire neuf.",
        )

    # On copie les entrées mais pas les figures générées de SORTIE/ : tout
    # l'intérêt de l'exemple est de le lancer et de les produire soi-même.
    shutil.copytree(
        EXEMPLE_DIR,
        dest,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("*.png", "*.svg", "*.pdf"),
    )
    (dest / "SORTIE").mkdir(exist_ok=True)
    study_file = next(dest.glob("*.yaml"), None)
    console.print(
        Panel(
            f"[green]Exemple copié dans[/] [{theme.VALEUR}]{dest}[/]\n\n"
            f"[dim]Lancez-le avec :[/]\n"
            f"  cfd-perf run {study_file or dest / 'ETUDE.yaml'} --figure scalabilite.png -v",
            title=f"[{theme.TITRE}]Exemple[/]",
            border_style="green",
        )
    )
    return 0


def _etat_commande(chemin: Path) -> str:
    """Décrit, en une cellule colorée, ce qu'un « cfd-perf » du PATH lancera."""
    interpreteur = shim.interpreter_of(chemin)
    if interpreteur is None:
        return "[dim]lanceur shell[/]"
    if shim.interpreter_exists(interpreteur):
        return f"[dim]{interpreteur}[/]"
    return f"[{theme.ERREUR}]interpréteur absent : {interpreteur}[/]"


def cmd_shim(args: argparse.Namespace) -> int:
    dest = Path(args.output).expanduser()
    try:
        lanceur = shim.write_launcher(dest, force=args.force)
    except FileExistsError:
        _fail(
            f"{dest / shim.LAUNCHER_NAME} existe déjà",
            hint="Passez --force pour le remplacer.",
        )
    except OSError as exc:
        _fail(f"écriture impossible dans {dest} : {exc}")

    lignes = [
        f"[{theme.OK}]Lanceur écrit :[/]",
        f"  [{theme.VALEUR}]{lanceur}[/]",
        "",
        "[dim]Il appelle « python3 -m cfd_perf » : l'interpréteur est résolu à[/]",
        "[dim]chaque appel, pas gravé à l'installation.[/]",
    ]

    if not shim.dir_is_on_path(dest):
        lignes += [
            "",
            f"[{theme.ATTENTION}]Ce répertoire n'est pas sur le PATH.[/] Ajoutez à ~/.bashrc :",
            f'  [{theme.VALEUR}]export PATH="{dest}:$PATH"[/]',
        ]

    trouvees = shim.commands_on_path()
    if trouvees:
        lignes += ["", "[dim]« cfd-perf » sur le PATH, dans l'ordre où le shell les trouve :[/]"]
        for rang, chemin in enumerate(trouvees):
            marque = "▸" if rang == 0 else " "
            lignes.append(f"  {marque} [{theme.VALEUR}]{chemin}[/]")
            lignes.append(f"      {_etat_commande(chemin)}")
        if not shim.is_runnable(trouvees[0]):
            lignes += [
                "",
                f"[{theme.ATTENTION}]La première de la liste est celle qui gagne, et elle est"
                " cassée.[/]",
                "[dim]Placez le lanceur avant elle dans le PATH, ou supprimez-la[/]",
                "[dim](« pip uninstall cfd-perf » avec le Python qui l'a installée).[/]",
            ]

    console.print(
        Panel(
            "\n".join(lignes),
            title=f"[{theme.TITRE}]Lanceur[/]",
            border_style="green",
        )
    )
    return 0


def _parse_coeurs(raw: str | None) -> list[int]:
    """Transforme « 48 96 192 » (ou « 48,96,192 ») en [48, 96, 192]."""
    if not raw:
        _fail(
            "la phase de soumission requiert --coeurs (ex. --coeurs \"48 96 192\")",
            hint="Utilisez --collect pour la phase de collecte.",
        )
    tokens = raw.replace(",", " ").split()
    coeurs: list[int] = []
    for tok in tokens:
        try:
            n = int(tok)
        except ValueError:
            _fail(f"valeur de cœurs invalide : « {tok} » (entier attendu)")
        if n <= 0:
            _fail(f"valeur de cœurs invalide : {n} (doit être > 0)")
        coeurs.append(n)
    return coeurs


def _capture_submit(args: argparse.Namespace, case_dir: Path, work_dir: Path, adapter: BashAdapter) -> int:
    coeurs = _parse_coeurs(args.coeurs)
    try:
        res = submit(
            case_dir=case_dir, adapter=adapter, coeurs=coeurs, work_dir=work_dir, queue=args.queue
        )
    except CaptureError as exc:
        _fail(str(exc))

    lignes = [f"[green]{len(res.manifest.runs)} run(s) soumis[/] via l'adaptateur "
              f"« {adapter.adapter_id} »", ""]
    for r in res.manifest.runs:
        lignes.append(f"[dim]{r.cores:>6} cœurs[/]  job {r.job_id}  [dim]{Path(r.run_dir).name}[/]")
    lignes += [
        "",
        "[dim]Quand les runs sont terminés, collectez et recommandez :[/]",
        f"  cfd-perf capture --collect --case-dir {args.case_dir}",
    ]
    console.print(
        Panel(
            "\n".join(lignes),
            title=f"[{theme.TITRE}]Capture — soumission[/]",
            border_style="blue",
        )
    )
    return 0


def _capture_collect(args: argparse.Namespace, case_dir: Path, work_dir: Path, adapter: BashAdapter) -> int:
    overrides = MachineOverrides(
        cores_per_node=args.cores_per_node,
        ram_per_node_gb=args.ram_per_node,
        max_nodes=args.max_nodes,
        max_walltime_hours=args.max_walltime,
    )
    strategy = Strategy(args.strategy) if args.strategy else Strategy.EFFICIENCY
    mel = args.max_efficiency_loss if args.max_efficiency_loss is not None else DEFAULT_MAX_EFFICIENCY_LOSS
    objective = ObjectiveSpec(
        strategy=strategy,
        max_efficiency_loss=mel,
        deadline_hours=args.deadline,
        cores_max=args.cores_max,
    )
    try:
        res = collect(
            work_dir=work_dir,
            adapter=adapter,
            machine_overrides=overrides,
            num_cells=args.num_cells,
            n_iterations=args.n_iterations,
            objective=objective,
        )
    except (CaptureError, StudyError, FileNotFoundError) as exc:
        _fail(str(exc))

    if not res.ready:
        lignes = ["[yellow]Certains runs ne sont pas terminés.[/]", ""]
        for cores, etat in res.pending:
            lignes.append(f"[dim]{cores:>6} cœurs[/]  {etat}")
        lignes += ["", "[dim]Relancez --collect plus tard.[/]"]
        console.print(
            Panel(
                "\n".join(lignes),
                title=f"[{theme.TITRE}]Capture — en cours[/]",
                border_style="yellow",
            )
        )
        return 3

    if res.study_path is None:
        _fail("aucun run exploitable (tous en échec) ; rien à recommander")

    summary = [
        f"[green]Étude générée :[/] [{theme.VALEUR}]{res.study_path}[/]",
        "",
        f"[dim]points pilotes[/] {len(res.points)}",
        f"[dim]mailles       [/] {_fr_int(res.num_cells)}",
        f"[dim]n_iterations  [/] {_fr_int(res.n_iterations)}",
    ]
    for note in res.notes:
        summary.append(f"[yellow]! {note}[/]")
    console.print(
        Panel(
            "\n".join(summary),
            title=f"[{theme.TITRE}]Capture — collecte[/]",
            border_style="green",
        )
    )

    if args.no_run:
        return 0

    study = load_study(res.study_path)
    try:
        rec = _run_study(study, strategy=None, model_kind=None)
    except ValueError as exc:
        _fail(str(exc))
    print_report(rec, study, verbose=args.verbose, con=console)

    if args.figure:
        from cfd_perf.report.figures import save_recommendation_figure

        path = save_recommendation_figure(
            rec, args.figure, title=f"{study.name}  --  sur combien de cœurs ?"
        )
        console.print(f"[dim]Figure écrite dans[/] [{theme.VALEUR}]{path}[/]\n")

    if rec.choice is None:
        return 2
    return 0


def cmd_capture(args: argparse.Namespace) -> int:
    """Capture automatique des données pilotes (soumission, puis --collect)."""
    case_dir = Path(args.case_dir).resolve()
    if not case_dir.is_dir():
        _fail(f"répertoire de cas introuvable : {case_dir}")

    work_dir = Path(args.work_dir)
    if not work_dir.is_absolute():
        work_dir = case_dir / work_dir

    try:
        adapter = BashAdapter(args.adaptateur)
    except CaptureError as exc:
        _fail(str(exc))

    if args.collect:
        return _capture_collect(args, case_dir, work_dir, adapter)
    return _capture_submit(args, case_dir, work_dir, adapter)


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

    p_shim = sub.add_parser(
        "shim",
        help="écrit un lanceur « cfd-perf » indépendant de l'interpréteur gravé par pip",
    )
    p_shim.add_argument(
        "--output", "-o", default="~/bin", help="répertoire du lanceur (défaut : ~/bin)"
    )
    p_shim.add_argument(
        "--force", action="store_true", help="remplace un lanceur déjà présent"
    )
    p_shim.set_defaults(func=cmd_shim)

    p_cap = sub.add_parser(
        "capture",
        help="capture automatique des données pilotes (soumission, puis --collect)",
    )
    p_cap.add_argument(
        "--coeurs",
        metavar='"N N …"',
        help="nombres de cœurs des runs pilotes (phase de soumission)",
    )
    p_cap.add_argument(
        "--collect",
        action="store_true",
        help="phase de collecte : lit les runs terminés, génère l'étude et recommande",
    )
    p_cap.add_argument("--adaptateur", "-a", default="mock", help="adaptateur solveur (défaut : mock)")
    p_cap.add_argument("--queue", help="queue / partition de l'ordonnanceur")
    p_cap.add_argument("--case-dir", default=".", help="répertoire du cas (défaut : .)")
    p_cap.add_argument(
        "--work-dir", default="PILOTE", help="répertoire de travail des runs (défaut : PILOTE)"
    )
    p_cap.add_argument("--figure", "-f", help="écrit la figure de scalabilité (collecte)")
    p_cap.add_argument("--no-run", action="store_true", help="génère l'étude sans lancer la recommandation")
    p_cap.add_argument("--verbose", "-v", action="store_true", help="affiche aussi toute la courbe")
    # Surcharges (sinon détection automatique / défauts)
    p_cap.add_argument("--num-cells", type=int, help="nombre de mailles (sinon via l'adaptateur)")
    p_cap.add_argument("--n-iterations", type=int, help="itérations de production (study.n_iterations)")
    p_cap.add_argument("--cores-per-node", type=int, help="cœurs par nœud (sinon auto-détecté)")
    p_cap.add_argument("--ram-per-node", type=float, metavar="GO", help="RAM par nœud en Go")
    p_cap.add_argument("--max-nodes", type=int, help="nombre maximal de nœuds")
    p_cap.add_argument("--max-walltime", type=float, metavar="HEURES", help="temps d'horloge maximal")
    # Objectif
    p_cap.add_argument("--strategy", choices=[s.value for s in Strategy], help="stratégie de l'objectif")
    p_cap.add_argument("--max-efficiency-loss", type=float, help="perte d'efficacité tolérée (0-1)")
    p_cap.add_argument("--deadline", type=float, metavar="HEURES", help="échéance en temps d'horloge")
    p_cap.add_argument("--cores-max", type=int, help="borne haute de la recherche de cœurs")
    p_cap.set_defaults(func=cmd_capture)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    exit_code: int = args.func(args)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
