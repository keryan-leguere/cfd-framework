"""Partition recommender with heuristic wait-time estimation.

Assumptions & Heuristic
-----------------------
See ``docs/assumptions.md`` for the full rationale.  In short:

1. Slurm does **not** expose queue wait-time estimates.
2. We approximate scheduling as FIFO-with-backfill per partition.
3. **Wait-time heuristic** (per eligible partition):

   a. If idle CPUs >= requested CPUs  ->  "immediate" (< 1 min).
   b. Otherwise, estimate how long until enough CPUs free up:

      * Collect running jobs on that partition with ``squeue``.
      * Compute *remaining time* for each running job as
        ``time_limit - time_used`` (conservative: uses the full limit).
      * Sort running jobs by remaining time ascending.
      * Accumulate freed CPUs until we reach the requested amount.
        The remaining time of the last job needed is the estimated wait.
   c. Add a penalty proportional to the number of pending jobs ahead:
      ``pending_penalty = pending_count * median_remaining / total_nodes``.
   d. If we cannot determine enough info, label as "unknown".

4. The estimate is labelled with a **confidence** tag:
   ``high`` (idle CPUs available), ``medium`` (computed from running jobs),
   or ``low`` (fallback / incomplete data).
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from slurm_utils.parsers import (
    SINFO_FORMAT,
    SQUEUE_FORMAT,
    PartitionRecord,
    parse_sinfo,
    parse_squeue,
    parse_time_to_seconds,
)
from slurm_utils.runner import SlurmCommandError, run_slurm

console = Console()


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PartitionSummary:
    """Aggregated view of a single partition."""

    name: str
    available: bool
    timelimit_min: int | None
    total_nodes: int
    total_cpus: int
    cpus_per_node: int
    memory_mb_per_node: int
    idle_cpus: int
    allocated_cpus: int
    running_jobs: int
    pending_jobs: int
    estimated_wait_s: int | None
    confidence: str  # "high", "medium", "low", "unknown"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MEM_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*([KMGT]?)B?$", re.IGNORECASE)
_MEM_MULT = {"": 1, "K": 1 / 1024, "M": 1, "G": 1024, "T": 1024 * 1024}


def _parse_mem_to_mb(spec: str | None) -> int | None:
    """Convert a human memory spec (e.g. ``4G``, ``4096M``) to MB."""
    if spec is None:
        return None
    m = _MEM_RE.match(spec.strip())
    if not m:
        return None
    value = float(m.group(1))
    suffix = m.group(2).upper()
    return int(value * _MEM_MULT.get(suffix, 1))


def _fmt_duration(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    if seconds <= 0:
        return "< 1 min"
    if seconds < 60:
        return "< 1 min"
    if seconds < 3600:
        return f"~{seconds // 60} min"
    hours = seconds / 3600
    if hours < 24:
        return f"~{hours:.1f} h"
    days = hours / 24
    return f"~{days:.1f} d"


def _parse_cpus_aiot(raw: str) -> tuple[int, int, int, int]:
    """Parse ``A/I/O/T`` CPU string from sinfo, returning (alloc, idle, other, total)."""
    parts = raw.strip().split("/")
    if len(parts) == 4:
        return tuple(int(p) for p in parts)  # type: ignore[return-value]
    return (0, 0, 0, 0)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _gather_partition_summaries() -> list[PartitionSummary]:
    """Query sinfo and squeue, return one :class:`PartitionSummary` per partition."""

    # --- sinfo ---
    sinfo_res = run_slurm(["sinfo", "-o", SINFO_FORMAT])
    sinfo_rows = parse_sinfo(sinfo_res.stdout)

    # Aggregate per partition name (sinfo may have multiple rows per partition
    # for different node states).
    part_map: dict[str, list[PartitionRecord]] = {}
    for row in sinfo_rows:
        key = row.name_clean
        part_map.setdefault(key, []).append(row)

    # --- squeue (all users, running + pending) ---
    squeue_res = run_slurm(["squeue", "-o", SQUEUE_FORMAT, "-t", "R,PD"])
    all_jobs = parse_squeue(squeue_res.stdout)

    # Per-partition running/pending counts and remaining-time list
    running_by_part: dict[str, list[tuple[int, int]]] = {}  # (cpus, remaining_s)
    pending_by_part: dict[str, int] = {}

    for j in all_jobs:
        pname = j.partition
        if j.state == "RUNNING":
            cpus = int(j.cpus) if j.cpus.isdigit() else 0
            limit_s = parse_time_to_seconds(j.time_limit)
            used_s = parse_time_to_seconds(j.time_used)
            remaining = max(limit_s - used_s, 0)
            running_by_part.setdefault(pname, []).append((cpus, remaining))
        elif j.state == "PENDING":
            pending_by_part[pname] = pending_by_part.get(pname, 0) + 1

    summaries: list[PartitionSummary] = []
    for pname, rows in part_map.items():
        up = any(r.is_up for r in rows)
        timelimit = rows[0].timelimit_minutes
        total_nodes = sum(r.nodes for r in rows)
        cpus_per_node = max(r.cpus_per_node for r in rows)
        mem_per_node = max(r.memory_mb for r in rows)

        idle_cpus = alloc_cpus = total_cpus = 0
        for r in rows:
            a, i, _o, t = _parse_cpus_aiot(r.cpus_aiot)  # A/I/O/T: Other is unused
            idle_cpus += i
            alloc_cpus += a
            total_cpus += t

        if total_cpus == 0:
            total_cpus = total_nodes * cpus_per_node

        running = running_by_part.get(pname, [])
        pending = pending_by_part.get(pname, 0)

        est_wait, conf = _estimate_wait(
            requested_cpus=0,  # placeholder -- filled per-query later
            idle_cpus=idle_cpus,
            running_jobs=running,
            pending_count=pending,
            total_nodes=total_nodes,
        )

        summaries.append(PartitionSummary(
            name=pname,
            available=up,
            timelimit_min=timelimit,
            total_nodes=total_nodes,
            total_cpus=total_cpus,
            cpus_per_node=cpus_per_node,
            memory_mb_per_node=mem_per_node,
            idle_cpus=idle_cpus,
            allocated_cpus=alloc_cpus,
            running_jobs=len(running),
            pending_jobs=pending,
            estimated_wait_s=est_wait,
            confidence=conf,
        ))

    return summaries


def _estimate_wait(
    *,
    requested_cpus: int,
    idle_cpus: int,
    running_jobs: list[tuple[int, int]],
    pending_count: int,
    total_nodes: int,
) -> tuple[int | None, str]:
    """Return (estimated_wait_seconds, confidence)."""

    if requested_cpus <= 0:
        return (None, "unknown")

    # Case 1: enough idle CPUs right now
    if idle_cpus >= requested_cpus:
        if pending_count == 0:
            return (0, "high")
        # Pending jobs ahead -- small penalty
        return (pending_count * 60, "medium")

    # Case 2: accumulate CPUs as running jobs finish
    if not running_jobs:
        return (None, "unknown")

    sorted_jobs = sorted(running_jobs, key=lambda x: x[1])
    freed = idle_cpus
    wait = 0
    for cpus, remaining in sorted_jobs:
        freed += cpus
        wait = remaining
        if freed >= requested_cpus:
            break

    if freed < requested_cpus:
        return (None, "low")

    # Pending-queue penalty
    if pending_count > 0 and total_nodes > 0:
        remaining_times = [r for _, r in running_jobs if r > 0]
        median_remaining = statistics.median(remaining_times) if remaining_times else 600
        penalty = int(pending_count * median_remaining / max(total_nodes, 1))
        wait += penalty

    return (wait, "medium")


def _parse_walltime_to_minutes(raw: str) -> int:
    """Parse user-supplied walltime ``H:MM:SS`` or ``D-HH:MM:SS`` to minutes."""
    raw = raw.strip()
    days = 0
    if "-" in raw:
        d, rest = raw.split("-", 1)
        days = int(d)
        raw = rest
    parts = raw.split(":")
    if len(parts) == 3:
        h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
        return days * 24 * 60 + h * 60 + m + (1 if s > 0 else 0)
    if len(parts) == 2:
        return days * 24 * 60 + int(parts[0]) * 60 + int(parts[1])
    return 0


# ---------------------------------------------------------------------------
# Public entry-point called by CLI
# ---------------------------------------------------------------------------

def recommend_partition(
    *,
    ntasks: int,
    mem_spec: str | None,
    walltime: str,
    partitions: list[str] | None = None,
    exclude: list[str] | None = None,
) -> None:
    """Query cluster state and recommend the best partition.

    Prints Rich-formatted output to the console.
    """
    mem_mb = _parse_mem_to_mb(mem_spec)
    wall_min = _parse_walltime_to_minutes(walltime)

    try:
        summaries = _gather_partition_summaries()
    except SlurmCommandError as exc:
        console.print(Panel(f"[bold red]{exc}[/bold red]", title="Error", border_style="red"))
        raise SystemExit(1) from exc

    # Recompute wait estimates with actual requested CPUs
    for s in summaries:
        running_data: list[tuple[int, int]] = []
        try:
            squeue_res = run_slurm(
                ["squeue", "-o", SQUEUE_FORMAT, "-p", s.name, "-t", "R"],
                check=False,
            )
            from slurm_utils.parsers import parse_squeue as _pq

            for j in _pq(squeue_res.stdout):
                cpus = int(j.cpus) if j.cpus.isdigit() else 0
                limit_s = parse_time_to_seconds(j.time_limit)
                used_s = parse_time_to_seconds(j.time_used)
                running_data.append((cpus, max(limit_s - used_s, 0)))
        except SlurmCommandError:
            pass

        s.estimated_wait_s, s.confidence = _estimate_wait(
            requested_cpus=ntasks,
            idle_cpus=s.idle_cpus,
            running_jobs=running_data,
            pending_count=s.pending_jobs,
            total_nodes=s.total_nodes,
        )

    # --- Filter eligible partitions ---
    eligible: list[PartitionSummary] = []
    reasons_map: dict[str, list[str]] = {}

    for s in summaries:
        if not s.available:
            reasons_map[s.name] = ["partition is down"]
            continue

        reasons: list[str] = []

        if partitions and s.name not in partitions:
            continue
        if exclude and s.name in exclude:
            continue

        if ntasks > s.total_cpus:
            reasons.append(f"need {ntasks} CPUs but partition has {s.total_cpus}")

        if mem_mb is not None:
            per_core_mb = s.memory_mb_per_node / max(s.cpus_per_node, 1)
            if mem_mb > per_core_mb * ntasks and mem_mb > s.memory_mb_per_node:
                reasons.append(
                    f"need {mem_mb} MB but max per-node is {s.memory_mb_per_node} MB"
                )

        if s.timelimit_min is not None and wall_min > s.timelimit_min:
            reasons.append(
                f"walltime {wall_min} min exceeds limit {s.timelimit_min} min"
            )

        if reasons:
            reasons_map[s.name] = reasons
        else:
            eligible.append(s)

    # --- Rank eligible partitions ---
    def _score(s: PartitionSummary) -> tuple[int, int, int]:
        wait = s.estimated_wait_s if s.estimated_wait_s is not None else 10**9
        return (wait, s.pending_jobs, -s.idle_cpus)

    eligible.sort(key=_score)

    # --- Display ---
    console.print()
    req_panel = (
        f"[bold]CPUs:[/bold]     {ntasks}\n"
        f"[bold]Memory:[/bold]   {mem_spec or 'any'}\n"
        f"[bold]Walltime:[/bold] {walltime}"
    )
    console.print(Panel(req_panel, title="Requested Resources", border_style="cyan"))

    if eligible:
        table = Table(
            title=f"Eligible Partitions ({len(eligible)})",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("PARTITION", style="bold")
        table.add_column("NODES", justify="right")
        table.add_column("TOTAL CPUs", justify="right")
        table.add_column("IDLE CPUs", justify="right")
        table.add_column("RUNNING", justify="right")
        table.add_column("PENDING", justify="right")
        table.add_column("EST. WAIT", justify="right")
        table.add_column("CONFIDENCE")
        table.add_column("", justify="center")

        for i, s in enumerate(eligible):
            is_best = i == 0
            marker = "[bold green]<-- best[/bold green]" if is_best else ""
            conf_style = {"high": "green", "medium": "yellow", "low": "red"}.get(s.confidence, "dim")

            table.add_row(
                s.name,
                str(s.total_nodes),
                str(s.total_cpus),
                str(s.idle_cpus),
                str(s.running_jobs),
                str(s.pending_jobs),
                _fmt_duration(s.estimated_wait_s),
                f"[{conf_style}]{s.confidence}[/{conf_style}]",
                marker,
            )

        console.print(table)

        best = eligible[0]
        console.print(Panel(
            f"[bold]Partition:[/bold]      {best.name}\n"
            f"[bold]Est. wait:[/bold]      {_fmt_duration(best.estimated_wait_s)}  "
            f"[dim]({best.confidence} confidence)[/dim]\n"
            f"[bold]Idle CPUs:[/bold]      {best.idle_cpus} / {best.total_cpus}\n"
            f"[bold]Pending ahead:[/bold]  {best.pending_jobs} jobs",
            title="Recommendation",
            border_style="green",
        ))

        console.print(
            "\n[dim]Note: Wait-time estimates are heuristic. Actual scheduling depends on "
            "priority, backfill, fair-share, and other factors. "
            "See docs/assumptions.md for details.[/dim]\n"
        )
    else:
        console.print(Panel(
            "[bold red]No eligible partition found for the requested resources.[/bold red]",
            title="Recommendation",
            border_style="red",
        ))

    if reasons_map:
        rej_table = Table(
            title="Ineligible Partitions",
            show_header=True,
            header_style="bold red",
        )
        rej_table.add_column("PARTITION")
        rej_table.add_column("REASON(S)")
        for name, reasons in sorted(reasons_map.items()):
            rej_table.add_row(name, "; ".join(reasons))
        console.print(rej_table)
