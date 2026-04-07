"""Rich-powered display helpers for notebooks and scripts."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cfd_perf.benchmark.models import PilotSeries
from cfd_perf.mesh.models import MeshStats
from cfd_perf.models.parameters import ModelParameters
from cfd_perf.optimizer.models import OptimizationResult

console = Console()


def print_mesh_stats(stats: MeshStats) -> None:
    """Print mesh stats as a Rich table."""
    table = Table(title="Mesh Analysis", show_header=True, header_style="bold cyan")
    table.add_column("Property", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Cells", f"{stats.num_cells:,}")
    table.add_row("Faces", f"{stats.num_faces:,}")

    if stats.cell_type_distribution:
        dist = "  ".join(f"{k}: {v:.0%}" for k, v in stats.cell_type_distribution.items())
        table.add_row("Cell types", dist)

    if stats.estimated_mem_per_cell_bytes is not None:
        GB = 1 << 30
        table.add_row("Mem / cell", f"{stats.estimated_mem_per_cell_bytes:,.0f} B")
        total_gb = stats.estimated_mem_per_cell_bytes * stats.num_cells / GB
        table.add_row("Total RAM (est.)", f"{total_gb:.1f} GB")
    else:
        table.add_row("Mem / cell", "[dim]unknown[/dim]")

    console.print(table)


def print_fit_result(params: ModelParameters, pilot: PilotSeries) -> None:
    """Print scaling fit and pilot data as Rich tables."""
    table = Table(title="Scaling Model Fit", show_header=True, header_style="bold cyan")
    table.add_column("Property", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Model", params.model_kind)
    table.add_row("Beta", f"{params.beta:.6f}")
    table.add_row("Source", params.beta_source)
    if params.empirical_coeffs is not None:
        a, b, c = params.empirical_coeffs
        table.add_row("Empirical coeffs", f"a={a:.6f}  b={b:.6f}  c={c:.6f}")
    table.add_row("Baseline cores", str(pilot.baseline_cores))
    table.add_row("Baseline T/iter", f"{pilot.baseline_time_per_iter_s:.3f} s")
    table.add_row("Iterations", f"{pilot.n_iterations:,}")
    table.add_row("Pilot points", str(len(pilot.points)))

    console.print(table)

    pilot_table = Table(title="Pilot Data", show_header=True, header_style="bold magenta")
    pilot_table.add_column("Cores", justify="right")
    pilot_table.add_column("T/iter (s)", justify="right")
    pilot_table.add_column("Peak RAM (GB)", justify="right")
    for p in pilot.points:
        pilot_table.add_row(str(p.cores), f"{p.time_per_iter_s:.3f}", f"{p.peak_ram_total_gb:.1f}")
    console.print(pilot_table)


def print_optimization_result(result: OptimizationResult) -> None:
    """Print optimization result (optimal config, accepted/rejected tables)."""
    if result.optimal:
        opt = result.optimal
        mode_label = result.mode.upper()
        panel_lines = [
            f"[bold]Cores:[/bold]           {opt.cores}",
            f"[bold]Time / iter:[/bold]     {opt.time_per_iter_s:.3f} s",
            f"[bold]Total runtime:[/bold]   {opt.runtime_hours:.2f} h",
            f"[bold]Speedup:[/bold]         {opt.speedup:.2f}x",
            f"[bold]Efficiency:[/bold]      {opt.efficiency:.1%}",
            f"[bold]Eff. loss:[/bold]       {opt.efficiency_loss:.1%}",
            f"[bold]RAM total:[/bold]       {opt.ram_total_gb:.1f} GB",
            f"[bold]RAM / core:[/bold]      {opt.ram_per_core_gb:.2f} GB",
        ]
        console.print(Panel(
            "\n".join(panel_lines),
            title=f"Optimal Configuration ({mode_label})",
            border_style="green",
        ))
    else:
        console.print(Panel(
            "[bold red]No feasible configuration found.[/bold red]",
            title="Optimization Result",
            border_style="red",
        ))

    if result.accepted:
        table = Table(
            title=f"Accepted Candidates ({len(result.accepted)})",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("Cores", justify="right", style="bold")
        table.add_column("T/iter (s)", justify="right")
        table.add_column("Runtime (h)", justify="right")
        table.add_column("Speedup", justify="right")
        table.add_column("Eff (%)", justify="right")
        table.add_column("Loss (%)", justify="right")
        table.add_column("RAM/core (GB)", justify="right")
        table.add_column("", justify="center")

        for c in result.accepted:
            is_opt = result.optimal and c.cores == result.optimal.cores
            marker = "[bold green]<--[/bold green]" if is_opt else ""
            table.add_row(
                str(c.cores),
                f"{c.time_per_iter_s:.3f}",
                f"{c.runtime_hours:.2f}",
                f"{c.speedup:.2f}",
                f"{c.efficiency * 100:.1f}",
                f"{c.efficiency_loss * 100:.1f}",
                f"{c.ram_per_core_gb:.2f}",
                marker,
            )

        console.print(table)

    mrc = result.min_runtime_candidate
    if mrc is not None and result.optimal is not None and mrc.cores != result.optimal.cores:
        console.print(Panel(
            f"[bold]Cores:[/bold]           {mrc.cores}\n"
            f"[bold]Total runtime:[/bold]   {mrc.runtime_hours:.2f} h\n"
            f"[bold]Time / iter:[/bold]     {mrc.time_per_iter_s:.3f} s",
            title="Minimum Runtime Point",
            border_style="blue",
        ))

    if result.rejected:
        rej_table = Table(
            title=f"Rejected ({len(result.rejected)})",
            show_header=True,
            header_style="bold red",
        )
        rej_table.add_column("Cores", justify="right")
        rej_table.add_column("Reasons")
        for r in result.rejected:
            rej_table.add_row(str(r.cores), ", ".join(r.reasons))
        console.print(rej_table)
