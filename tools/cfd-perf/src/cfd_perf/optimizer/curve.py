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
    params: ModelParameters,
    n_iterations: int,
    mesh: MeshStats,
) -> CandidateConfig:
    """Compute all predicted metrics for a single core count.

    Uses whichever model (beta or empirical) is encoded in *params*.
    """
    t = ss.predict_time_per_iter(nc, nc0, t0, params)
    s = t0 / t
    e = s / (nc / nc0)
    el = 1.0 - e
    rt = t * n_iterations / 3600.0

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
        build_candidate(nc, nc0, t0, params, n_iterations, mesh)
        for nc in nc_range
        if nc > 0
    ]
