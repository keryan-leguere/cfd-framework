"""SLURM job snippet generator."""

from __future__ import annotations

import math
from pathlib import Path

from cfd_perf.optimizer.models import OptimizationResult


def render_slurm_snippet(
    result: OptimizationResult,
    *,
    job_name: str = "cfd_run",
    partition: str = "compute",
    mem_mode: str = "per-cpu",
) -> str:
    """Return a SLURM header snippet for the optimal configuration.

    *mem_mode* is ``"per-cpu"`` (default) or ``"total"``.
    """
    if result.optimal is None:
        return "# No feasible configuration found."

    opt = result.optimal
    runtime_h = math.ceil(opt.runtime_hours)
    wall = f"{runtime_h}:00:00"

    lines = [
        "#!/bin/bash",
        f"#SBATCH --job-name={job_name}",
        f"#SBATCH --partition={partition}",
        f"#SBATCH --ntasks={opt.cores}",
        f"#SBATCH --time={wall}",
    ]

    if mem_mode == "per-cpu":
        mem_mb = math.ceil(opt.ram_per_core_gb * 1024)
        lines.append(f"#SBATCH --mem-per-cpu={mem_mb}M")
    else:
        mem_mb = math.ceil(opt.ram_total_gb * 1024)
        lines.append(f"#SBATCH --mem={mem_mb}M")

    lines.append("")
    return "\n".join(lines)


def export_slurm(result: OptimizationResult, path: Path, **kwargs: str) -> Path:
    """Write SLURM snippet to *path*."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_slurm_snippet(result, **kwargs))
    return path
