"""Generate the full scaling curve: one CandidateConfig per candidate core count."""

from __future__ import annotations

from cfd_perf.mesh.models import MeshStats
from cfd_perf.models import memory as mem_model
from cfd_perf.models import strong_scaling as ss
from cfd_perf.models.parameters import ModelParameters
from cfd_perf.optimizer.models import CandidateConfig


def build_candidate(
    nc: int,
    nc0: int,
    t0: float,
    beta: float,
    n_iterations: int,
    mesh: MeshStats,
) -> CandidateConfig:
    """Compute all predicted metrics for a single core count."""
    t = ss.time_per_iter(nc, nc0, t0, beta)
    s = ss.speedup(nc, nc0, t0, beta)
    e = ss.efficiency(nc, nc0, t0, beta)
    el = ss.efficiency_loss(nc, nc0, t0, beta)
    rt = ss.total_runtime_hours(nc, nc0, t0, beta, n_iterations)

    ram_total = mem_model.total_ram_gb(mesh)
    rpc = mem_model.ram_per_core_gb(mesh, nc)

    return CandidateConfig(
        cores=nc,
        time_per_iter_s=t,
        runtime_hours=rt,
        speedup=s,
        efficiency=e,
        efficiency_loss=el,
        ram_total_gb=ram_total if ram_total is not None else 0.0,
        ram_per_core_gb=rpc if rpc is not None else 0.0,
    )


def build_scaling_curve(
    nc_range: range,
    params: ModelParameters,
    nc0: int,
    t0: float,
    n_iterations: int,
    mesh: MeshStats,
) -> list[CandidateConfig]:
    """Build candidates for every core count in *nc_range*."""
    return [
        build_candidate(nc, nc0, t0, params.beta, n_iterations, mesh)
        for nc in nc_range
        if nc > 0
    ]
