"""Argparse CLI for cfd-stats.

Commands
--------
analyze   – Run the full analysis pipeline on a pickle file.
compare   – Compare families across boundary surfaces.
report    – Generate a formatted report (txt / html / json).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    import pandas as pd


console = Console()


class CLIError(Exception):
    """Expected CLI error that should become a non-zero exit code."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def _load(path: Path, iter_col: str) -> tuple[pd.DataFrame, list[str], str]:
    """Load data and detect columns. Returns ``(df, coeff_cols, iter_col)``."""
    from cfd_stats.utils.dataframe import detect_coeff_columns, detect_iter_column, load_dataframe

    df = load_dataframe(path)
    if iter_col == "auto":
        iter_col = detect_iter_column(df)
    coeff_cols = detect_coeff_columns(df, iter_col=iter_col)
    if not coeff_cols:
        raise CLIError("No numeric coefficient columns found.")
    return df, coeff_cols, iter_col


def _save_outputs(results: dict, output_dir: Path, formats: list[str], input_file: str) -> None:
    from cfd_stats.reports.html import save_html
    from cfd_stats.reports.summary import save_json, save_text

    output_dir.mkdir(parents=True, exist_ok=True)
    for fmt in formats:
        if fmt == "json":
            path = save_json(results, output_dir / "report.json", input_file=input_file)
            console.print(f"  JSON  -> {path}")
        elif fmt == "txt":
            path = save_text(results, output_dir / "report.txt")
            console.print(f"  Text  -> {path}")
        elif fmt == "html":
            path = save_html(results, output_dir / "report.html", input_file=input_file)
            console.print(f"  HTML  -> {path}")
        elif fmt in ("markdown", "md"):
            path = save_text(results, output_dir / "report.md")
            console.print(f"  MD    -> {path}")


def _run_analysis_for_family(
    df: pd.DataFrame,
    coeff_cols: list[str],
    iter_col: str,
    cfg,
) -> dict:
    """Run the full pipeline on a single family selection."""
    from cfd_stats.analysis.detector import AutomaticDetector

    detector = AutomaticDetector(df, coeff_cols, iter_col=iter_col, config=cfg)
    return detector.run_full_analysis()


def _generate_figures(
    df: pd.DataFrame,
    coeff_cols: list[str],
    iter_col: str,
    results: dict,
    output_dir: Path,
) -> None:
    """Generate diagnostic figures if the ``cfd-plot`` package is installed."""
    try:
        from cfd_stats.reports.plotter import StatisticsPlotter
    except ImportError:
        console.print(
            "[yellow]Skipping figures: 'cfd-plot' is not installed "
            "(pip install -e tools/cfd-plot).[/]"
        )
        return

    plotter = StatisticsPlotter(df, coeff_cols, iter_col, results)
    files = plotter.plot_all(output_dir)
    if files:
        console.print(f"\n[bold]Figures ({len(files)}):[/]")
        for figure in files:
            console.print(f"  {figure}")


def analyze(args: argparse.Namespace) -> int:
    """Run the full analysis pipeline on a pickle file."""
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from cfd_stats.config import AnalysisConfig
    from cfd_stats.reports.console import ConsoleReporter
    from cfd_stats.utils.dataframe import detect_family_column, list_families as list_families_for_df

    cfg = AnalysisConfig.from_yaml(args.config_file) if args.config_file else AnalysisConfig()
    df, coeff_cols, iter_col = _load(args.data_file, args.iter_col)

    fam_col = detect_family_column(df)

    if args.list_families:
        if fam_col is None:
            console.print("[yellow]No family column found in the DataFrame.[/]")
        else:
            families = list_families_for_df(df, fam_col)
            console.print(f"[bold]Family column:[/] {fam_col}")
            console.print(f"[bold]Available families ({len(families)}):[/]")
            for family_name in families:
                rows = len(df[df[fam_col] == family_name])
                console.print(f"  * {family_name}  ({rows} rows)")
        return 0

    reporter = ConsoleReporter(console)

    if args.family:
        if fam_col is None:
            raise CLIError("No family column found - cannot filter.")
        available = list_families_for_df(df, fam_col)
        if args.family not in available:
            raise CLIError(f"Family '{args.family}' not found. Available: {available}")
        families_to_run: list[str | None] = [args.family]
    elif fam_col is not None:
        families_to_run = list_families_for_df(df, fam_col)
        console.print(f"[bold]Detected family column:[/] '{fam_col}'  ->  {families_to_run}\n")
    else:
        families_to_run = [None]

    all_results: dict[str, dict] = {}

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        for family_name in families_to_run:
            label = family_name or "all"
            task_id = progress.add_task(f"Analysing {label}...", total=None)
            if family_name and fam_col:
                sub_df = df[df[fam_col] == family_name].reset_index(drop=True)
            else:
                sub_df = df
            results = _run_analysis_for_family(sub_df, coeff_cols, iter_col, cfg)
            all_results[label] = results
            progress.update(task_id, completed=1, total=1)

    for family_name, results in all_results.items():
        if len(all_results) > 1:
            console.rule(f"[bold magenta]Family: {family_name}[/]", style="magenta")
            console.print()
        reporter.print_full_report(results)
        console.print()

    formats = args.format or cfg.output_formats
    if formats:
        console.print("[bold]Saving reports:[/]")
        if len(all_results) == 1:
            the_results = next(iter(all_results.values()))
            _save_outputs(the_results, args.output_dir, formats, input_file=str(args.data_file))
        else:
            for family_name, results in all_results.items():
                family_dir = args.output_dir / family_name
                console.print(f"\n  [bold]{family_name}/[/]")
                _save_outputs(results, family_dir, formats, input_file=str(args.data_file))

    if not args.no_plots:
        for family_name, results in all_results.items():
            if family_name != "all" and fam_col and len(all_results) > 1:
                sub_df = df[df[fam_col] == family_name].reset_index(drop=True)
                figure_dir = args.output_dir / family_name
            else:
                if family_name == "all":
                    sub_df = df
                elif fam_col:
                    sub_df = df[df[fam_col] == family_name].reset_index(drop=True)
                else:
                    sub_df = df
                figure_dir = args.output_dir
            _generate_figures(sub_df, coeff_cols, iter_col, results, figure_dir)

    if args.verbose >= 2:
        import json

        console.print_json(json.dumps({key: str(value) for key, value in all_results.items()}))

    return 0


def compare(args: argparse.Namespace) -> int:
    """Compare statistics across families."""
    from cfd_stats.analysis.family_compare import compare_families, families_to_dataframe
    from cfd_stats.utils.dataframe import detect_family_column, list_families as list_families_for_df

    df, coeff_cols, iter_col = _load(args.data_file, args.iter_col)
    fam_col = detect_family_column(df)

    if fam_col is None:
        raise CLIError("No family column found in the DataFrame.")

    available = list_families_for_df(df, fam_col)
    if args.families:
        requested = [family.strip() for family in args.families.split(",") if family.strip()]
        df = df[df[fam_col].isin(requested)]
        if df.empty:
            raise CLIError(f"No rows match families: {requested}. Available: {available}")

    cols = [args.metric] if args.metric and args.metric in coeff_cols else coeff_cols
    comparison = compare_families(df, cols, family_col=fam_col, iter_col=iter_col)
    tidy = families_to_dataframe(comparison)
    console.print(tidy.to_string(index=False))

    if args.output:
        from cfd_stats.reports.summary import save_json

        save_json({"family_comparison": comparison}, args.output)
        console.print(f"\nSaved to {args.output}")

    return 0


def report(args: argparse.Namespace) -> int:
    """Generate a formatted report without interactive console output."""
    from cfd_stats.analysis.detector import AutomaticDetector
    from cfd_stats.utils.dataframe import detect_family_column

    df, coeff_cols, iter_col = _load(args.data_file, args.iter_col)

    if args.family:
        fam_col = detect_family_column(df)
        if fam_col and fam_col in df.columns:
            df = df[df[fam_col] == args.family].reset_index(drop=True)

    detector = AutomaticDetector(df, coeff_cols, iter_col=iter_col)
    results = detector.run_full_analysis()

    formats = args.format or ["txt", "json", "html"]
    console.print("[bold]Generating reports:[/]")
    _save_outputs(results, args.output_dir, formats, input_file=str(args.data_file))
    console.print("[green]Done.[/]")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Create the top-level CLI parser."""
    parser = argparse.ArgumentParser(
        prog="cfd-stats",
        description="Automatic convergence & statistics analysis for CFD time-series.",
    )
    subparsers = parser.add_subparsers(dest="command")

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Run the full analysis pipeline on a pickle file.",
        description=(
            "Run the full analysis pipeline on a pickle file. When the DataFrame "
            "contains a family column, use --family to select one family or omit "
            "it to analyse each family separately."
        ),
    )
    analyze_parser.add_argument("data_file", type=Path, help="Path to a .pickle file containing the DataFrame")
    analyze_parser.add_argument("--output-dir", "-o", type=Path, default=Path("results"), help="Output directory")
    analyze_parser.add_argument("--format", "-f", action="append", dest="format", help="Output formats")
    analyze_parser.add_argument("--family", help="Analyse only this family (e.g. AIRFOIL)")
    analyze_parser.add_argument("--iter-col", default="auto", help="Iteration column name (or 'auto')")
    analyze_parser.add_argument("--verbose", "-v", action="count", default=0, help="Verbosity level")
    analyze_parser.add_argument("--config", "-c", type=Path, dest="config_file", help="YAML config file")
    analyze_parser.add_argument("--no-plots", action="store_true", help="Disable figure generation")
    analyze_parser.add_argument("--list-families", action="store_true", help="List available families and exit")
    analyze_parser.set_defaults(handler=analyze)

    compare_parser = subparsers.add_parser(
        "compare",
        help="Compare statistics across families.",
        description="Compare statistics across families (boundary surfaces, models, ...).",
    )
    compare_parser.add_argument("data_file", type=Path, help="Path to a .pickle file")
    compare_parser.add_argument("--families", help="Comma-separated family names (default: all)")
    compare_parser.add_argument("--metric", help="Focus on one coefficient")
    compare_parser.add_argument("--iter-col", default="auto")
    compare_parser.add_argument("--output", "-o", type=Path)
    compare_parser.set_defaults(handler=compare)

    report_parser = subparsers.add_parser(
        "report",
        help="Generate a formatted report.",
        description="Generate a formatted report without interactive console output.",
    )
    report_parser.add_argument("data_file", type=Path, help="Path to a .pickle file")
    report_parser.add_argument("--output-dir", "-o", type=Path, default=Path("results"))
    report_parser.add_argument("--format", "-f", action="append", dest="format")
    report_parser.add_argument("--family", help="Restrict to one family")
    report_parser.add_argument("--template", default="full")
    report_parser.add_argument("--iter-col", default="auto")
    report_parser.set_defaults(handler=report)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args_list = list(sys.argv[1:] if argv is None else argv)

    if not args_list:
        parser.print_help()
        return 0

    try:
        args = parser.parse_args(args_list)
    except SystemExit as exc:
        return int(exc.code)

    if not hasattr(args, "handler"):
        parser.print_help()
        return 0

    try:
        return args.handler(args)
    except CLIError as exc:
        console.print(f"[red]{exc}[/]")
        return exc.code
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/]")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
