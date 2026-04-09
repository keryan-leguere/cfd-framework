"""Typer CLI for cfd-stats.

Commands
--------
analyze   – Run the full analysis pipeline on a pickle file.
compare   – Compare families across boundary surfaces.
report    – Generate a formatted report (txt / html / json).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="cfd-stats",
    help="Automatic convergence & statistics analysis for CFD time-series.",
    add_completion=True,
    no_args_is_help=True,
)
console = Console()


# ── helpers ─────────────────────────────────────────────────────────

def _load(path: Path, iter_col: str) -> tuple:
    """Load data and detect columns.  Returns (df, coeff_cols, iter_col)."""
    from cfd_stats.utils.dataframe import detect_coeff_columns, detect_iter_column, load_dataframe

    df = load_dataframe(path)
    if iter_col == "auto":
        iter_col = detect_iter_column(df)
    coeff_cols = detect_coeff_columns(df, iter_col=iter_col)
    if not coeff_cols:
        console.print("[red]No numeric coefficient columns found.[/]")
        raise typer.Exit(code=1)
    return df, coeff_cols, iter_col


def _save_outputs(results: dict, output_dir: Path, formats: list[str], input_file: str) -> None:
    from cfd_stats.reports.html import save_html
    from cfd_stats.reports.summary import save_json, save_text

    output_dir.mkdir(parents=True, exist_ok=True)
    for fmt in formats:
        if fmt == "json":
            p = save_json(results, output_dir / "report.json", input_file=input_file)
            console.print(f"  JSON  → {p}")
        elif fmt == "txt":
            p = save_text(results, output_dir / "report.txt")
            console.print(f"  Text  → {p}")
        elif fmt == "html":
            p = save_html(results, output_dir / "report.html", input_file=input_file)
            console.print(f"  HTML  → {p}")
        elif fmt in ("markdown", "md"):
            p = save_text(results, output_dir / "report.md")
            console.print(f"  MD    → {p}")


def _run_analysis_for_family(
    df, coeff_cols: list[str], iter_col: str, cfg, family_name: str | None,
) -> dict:
    """Run the full pipeline on a single (optionally filtered) family."""
    from cfd_stats.analysis.detector import AutomaticDetector

    detector = AutomaticDetector(df, coeff_cols, iter_col=iter_col, config=cfg)
    return detector.run_full_analysis()


def _generate_figures(
    df, coeff_cols: list[str], iter_col: str, results: dict, output_dir: Path,
) -> None:
    """Generate diagnostic figures if the ``plotting`` package is available."""
    try:
        from cfd_stats.reports.plotter import StatisticsPlotter
    except ImportError:
        console.print("[yellow]Skipping figures: 'plotting' package not found on sys.path.[/]")
        return

    plotter = StatisticsPlotter(df, coeff_cols, iter_col, results)
    files = plotter.plot_all(output_dir)
    if files:
        console.print(f"\n[bold]Figures ({len(files)}):[/]")
        for f in files:
            console.print(f"  {f}")


# ── analyze ─────────────────────────────────────────────────────────

@app.command()
def analyze(
    data_file: Annotated[Path, typer.Argument(help="Path to a .pickle file containing the DataFrame")],
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o", help="Output directory")] = Path("results"),
    fmt: Annotated[Optional[list[str]], typer.Option("--format", "-f", help="Output formats")] = None,
    family: Annotated[Optional[str], typer.Option("--family", help="Analyse only this family (e.g. AIRFOIL)")] = None,
    iter_col: Annotated[str, typer.Option("--iter-col", help="Iteration column name (or 'auto')")] = "auto",
    verbose: Annotated[int, typer.Option("--verbose", "-v", count=True, help="Verbosity level")] = 0,
    config_file: Annotated[Optional[Path], typer.Option("--config", "-c", help="YAML config file")] = None,
    no_plots: Annotated[bool, typer.Option("--no-plots", help="Disable figure generation")] = False,
    list_families: Annotated[bool, typer.Option("--list-families", help="List available families and exit")] = False,
) -> None:
    """Run the full analysis pipeline on a pickle file.

    When the DataFrame contains a 'family' column (boundary surfaces like
    WALL, AIRFOIL, TOTAL), pass --family to select one, or omit it to
    analyse each family separately.
    """
    from rich.progress import Progress, SpinnerColumn, TextColumn

    from cfd_stats.config import AnalysisConfig
    from cfd_stats.reports.console import ConsoleReporter
    from cfd_stats.utils.dataframe import detect_family_column, list_families as _list_fam

    cfg = AnalysisConfig.from_yaml(config_file) if config_file else AnalysisConfig()
    df, coeff_cols, iter_col = _load(data_file, iter_col)

    fam_col = detect_family_column(df)

    # --list-families: show available families and exit
    if list_families:
        if fam_col is None:
            console.print("[yellow]No family column found in the DataFrame.[/]")
        else:
            fams = _list_fam(df, fam_col)
            console.print(f"[bold]Family column:[/] {fam_col}")
            console.print(f"[bold]Available families ({len(fams)}):[/]")
            for f in fams:
                n = len(df[df[fam_col] == f])
                console.print(f"  • {f}  ({n} rows)")
        raise typer.Exit()

    reporter = ConsoleReporter(console)

    # Determine which families to process
    if family:
        # Single family requested
        if fam_col is None:
            console.print("[red]No family column found – cannot filter.[/]")
            raise typer.Exit(code=1)
        available = _list_fam(df, fam_col)
        if family not in available:
            console.print(f"[red]Family '{family}' not found.[/]  Available: {available}")
            raise typer.Exit(code=1)
        families_to_run = [family]
    elif fam_col is not None:
        # Family column exists → loop over each family
        families_to_run = _list_fam(df, fam_col)
        console.print(f"[bold]Detected family column:[/] '{fam_col}'  →  {families_to_run}\n")
    else:
        families_to_run = [None]  # type: ignore[list-item]

    all_results: dict[str, dict] = {}

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as prog:
        for fam_name in families_to_run:
            label = fam_name or "all"
            task = prog.add_task(f"Analysing {label}…", total=None)
            if fam_name and fam_col:
                sub_df = df[df[fam_col] == fam_name].reset_index(drop=True)
            else:
                sub_df = df
            results = _run_analysis_for_family(sub_df, coeff_cols, iter_col, cfg, fam_name)
            all_results[label] = results
            prog.update(task, completed=1, total=1)

    # Print results per family
    for fam_name, results in all_results.items():
        if len(all_results) > 1:
            console.rule(f"[bold magenta]Family: {fam_name}[/]", style="magenta")
            console.print()
        reporter.print_full_report(results)
        console.print()

    # Save outputs
    formats = fmt or cfg.output_formats
    if formats:
        if len(all_results) == 1:
            # Single family → save directly
            the_results = next(iter(all_results.values()))
            console.print("[bold]Saving reports:[/]")
            _save_outputs(the_results, output_dir, formats, input_file=str(data_file))
        else:
            # Multiple families → one sub-dir per family
            console.print("[bold]Saving reports:[/]")
            for fam_name, results in all_results.items():
                fam_dir = output_dir / fam_name
                console.print(f"\n  [bold]{fam_name}/[/]")
                _save_outputs(results, fam_dir, formats, input_file=str(data_file))

    # Generate figures
    if not no_plots:
        for fam_name, results in all_results.items():
            if fam_name and fam_col and len(all_results) > 1:
                sub_df = df[df[fam_col] == fam_name].reset_index(drop=True)
                fig_dir = output_dir / fam_name
            else:
                sub_df = df if fam_name is None or fam_name == "all" else df[df[fam_col] == fam_name].reset_index(drop=True)
                fig_dir = output_dir
            _generate_figures(sub_df, coeff_cols, iter_col, results, fig_dir)

    if verbose >= 2:
        import json
        console.print_json(json.dumps({k: str(v) for k, v in all_results.items()}))


# ── compare ─────────────────────────────────────────────────────────

@app.command()
def compare(
    data_file: Annotated[Path, typer.Argument(help="Path to a .pickle file")],
    families: Annotated[Optional[str], typer.Option("--families", help="Comma-separated family names (default: all)")] = None,
    metric: Annotated[Optional[str], typer.Option("--metric", help="Focus on one coefficient")] = None,
    iter_col: Annotated[str, typer.Option("--iter-col")] = "auto",
    output: Annotated[Optional[Path], typer.Option("--output", "-o")] = None,
) -> None:
    """Compare statistics across families (boundary surfaces, models, …)."""
    from cfd_stats.analysis.family_compare import compare_families, families_to_dataframe
    from cfd_stats.utils.dataframe import detect_family_column, list_families as _list_fam

    df, coeff_cols, iter_col = _load(data_file, iter_col)
    fam_col = detect_family_column(df)

    if fam_col is None:
        console.print("[red]No family column found in the DataFrame.[/]")
        raise typer.Exit(code=1)

    if families:
        fam_list = [f.strip() for f in families.split(",")]
        df = df[df[fam_col].isin(fam_list)]
        if df.empty:
            available = _list_fam(df, fam_col)
            console.print(f"[red]No rows match families: {fam_list}[/]  Available: {available}")
            raise typer.Exit(code=1)

    cols = [metric] if metric and metric in coeff_cols else coeff_cols
    comparison = compare_families(df, cols, family_col=fam_col, iter_col=iter_col)
    tidy = families_to_dataframe(comparison)
    console.print(tidy.to_string(index=False))

    if output:
        from cfd_stats.reports.summary import save_json

        save_json({"family_comparison": comparison}, output)
        console.print(f"\nSaved to {output}")


# ── report ──────────────────────────────────────────────────────────

@app.command()
def report(
    data_file: Annotated[Path, typer.Argument(help="Path to a .pickle file")],
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o")] = Path("results"),
    fmt: Annotated[Optional[list[str]], typer.Option("--format", "-f")] = None,
    family: Annotated[Optional[str], typer.Option("--family", help="Restrict to one family")] = None,
    template: Annotated[str, typer.Option("--template")] = "full",
    iter_col: Annotated[str, typer.Option("--iter-col")] = "auto",
) -> None:
    """Generate a formatted report without interactive console output."""
    from cfd_stats.analysis.detector import AutomaticDetector
    from cfd_stats.utils.dataframe import detect_family_column

    df, coeff_cols, iter_col = _load(data_file, iter_col)

    if family:
        fam_col = detect_family_column(df)
        if fam_col and fam_col in df.columns:
            df = df[df[fam_col] == family].reset_index(drop=True)

    detector = AutomaticDetector(df, coeff_cols, iter_col=iter_col)
    results = detector.run_full_analysis()

    formats = fmt or ["txt", "json", "html"]
    console.print("[bold]Generating reports:[/]")
    _save_outputs(results, output_dir, formats, input_file=str(data_file))
    console.print("[green]Done.[/]")


# ── entry point ─────────────────────────────────────────────────────

def main() -> None:
    app()


if __name__ == "__main__":
    main()
