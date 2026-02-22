"""Rich-powered display helpers for Slurm data."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from slurm_utils.parsers import JobRecord, PartitionRecord, PriorityRecord

console = Console()


# ---------------------------------------------------------------------------
# squeue / myjobs
# ---------------------------------------------------------------------------

_STATE_STYLE = {
    "RUNNING": "bold green",
    "PENDING": "bold yellow",
    "COMPLETING": "cyan",
    "COMPLETED": "dim",
    "FAILED": "bold red",
    "CANCELLED": "dim red",
    "TIMEOUT": "bold red",
    "PREEMPTED": "magenta",
    "SUSPENDED": "bold magenta",
}


def print_jobs(jobs: list[JobRecord], *, title: str = "Job Queue") -> None:
    if not jobs:
        console.print(Panel("[dim]No jobs found.[/dim]", title=title, border_style="blue"))
        return

    table = Table(title=title, show_header=True, header_style="bold cyan", show_lines=False)
    table.add_column("JOBID", justify="right", style="bold")
    table.add_column("NAME")
    table.add_column("PARTITION")
    table.add_column("STATE")
    table.add_column("USER")
    table.add_column("TIME", justify="right")
    table.add_column("LIMIT", justify="right")
    table.add_column("NODES", justify="right")
    table.add_column("CPUS", justify="right")
    table.add_column("MEMORY", justify="right")
    table.add_column("REASON")

    for j in jobs:
        style = _STATE_STYLE.get(j.state, "")
        table.add_row(
            j.jobid, j.name, j.partition,
            f"[{style}]{j.state}[/{style}]" if style else j.state,
            j.user, j.time_used, j.time_limit,
            j.nodes, j.cpus, j.min_memory, j.reason,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# sinfo
# ---------------------------------------------------------------------------

_AVAIL_STYLE = {"up": "green", "down": "red", "drain": "yellow", "inact": "dim"}


def print_partitions(parts: list[PartitionRecord], *, title: str = "Partitions") -> None:
    if not parts:
        console.print(Panel("[dim]No partition data.[/dim]", title=title, border_style="blue"))
        return

    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("PARTITION", style="bold")
    table.add_column("AVAIL")
    table.add_column("TIMELIMIT", justify="right")
    table.add_column("NODES", justify="right")
    table.add_column("STATE")
    table.add_column("CPUS/NODE", justify="right")
    table.add_column("MEM (MB)", justify="right")
    table.add_column("CPUS A/I/O/T", justify="right")

    for p in parts:
        avail_s = _AVAIL_STYLE.get(p.avail.lower(), "")
        avail_str = f"[{avail_s}]{p.avail}[/{avail_s}]" if avail_s else p.avail
        table.add_row(
            p.partition, avail_str, p.timelimit,
            str(p.nodes), p.state, str(p.cpus_per_node),
            f"{p.memory_mb:,}", p.cpus_aiot,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# sprio
# ---------------------------------------------------------------------------

def print_priority(records: list[PriorityRecord], *, explain: bool = True) -> None:
    if not records:
        console.print(Panel("[dim]No pending jobs with priority data.[/dim]", title="Priority", border_style="blue"))
        return

    table = Table(title="Job Priority Breakdown", show_header=True, header_style="bold cyan")
    table.add_column("JOBID", justify="right", style="bold")
    table.add_column("USER")
    table.add_column("PRIORITY", justify="right", style="bold green")
    table.add_column("AGE", justify="right")
    table.add_column("ASSOC", justify="right")
    table.add_column("FAIRSHARE", justify="right")
    table.add_column("JOBSIZE", justify="right")
    table.add_column("NICE", justify="right")
    table.add_column("PARTITION", justify="right")
    table.add_column("QOS", justify="right")
    table.add_column("TRES", justify="right")

    for r in records:
        table.add_row(
            r.jobid, r.user, r.priority,
            r.age, r.assoc, r.fairshare, r.jobsize,
            r.nice, r.partition, r.qos, r.tres,
        )

    console.print(table)

    if explain:
        console.print(Panel(
            "[bold]Priority[/bold] = "
            "PriorityWeightAge x age + "
            "PriorityWeightAssoc x assoc + "
            "PriorityWeightFairshare x fairshare + "
            "PriorityWeightJobSize x jobsize + "
            "PriorityWeightPartition x partition + "
            "PriorityWeightQOS x qos + "
            "TRES factors  [dim](higher = scheduled sooner)[/dim]\n\n"
            "Run [bold cyan]sprio -w[/bold cyan] to see the weights configured on your cluster.\n"
            "Run [bold cyan]sprio -l[/bold cyan] for long (detailed) output.",
            title="How Slurm priority works",
            border_style="blue",
        ))


# ---------------------------------------------------------------------------
# Generic error
# ---------------------------------------------------------------------------

def print_error(msg: str) -> None:
    console.print(Panel(f"[bold red]{msg}[/bold red]", title="Error", border_style="red"))
