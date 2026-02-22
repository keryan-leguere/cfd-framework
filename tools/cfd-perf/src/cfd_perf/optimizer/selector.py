"""Core-count selection logic: efficiency-driven or deadline-driven."""

from __future__ import annotations

from typing import Literal

from cfd_perf.benchmark.models import PilotSeries
from cfd_perf.constraints.config import HardConstraints
from cfd_perf.constraints.evaluator import check_hard_constraints
from cfd_perf.mesh.models import MeshStats
from cfd_perf.models.parameters import ModelParameters
from cfd_perf.optimizer.curve import build_scaling_curve
from cfd_perf.optimizer.models import CandidateConfig, OptimizationResult, RejectedConfig

DEFAULT_CORES_MAX = 4096
DEFAULT_STRIDE = 1
LARGE_RANGE_THRESHOLD = 512


def _auto_stride(nc0: int, nc_max: int) -> int:
    span = nc_max - nc0
    if span <= LARGE_RANGE_THRESHOLD:
        return DEFAULT_STRIDE
    return max(1, span // LARGE_RANGE_THRESHOLD)


def optimize(
    mesh: MeshStats,
    pilot: PilotSeries,
    params: ModelParameters,
    *,
    mode: Literal["efficiency", "deadline"],
    max_efficiency_loss: float | None = None,
    deadline_hours: float | None = None,
    cores_max: int = DEFAULT_CORES_MAX,
    constraints: HardConstraints | None = None,
    stride: int | None = None,
) -> OptimizationResult:
    """Run the full optimization pipeline and return structured results."""
    if mode == "efficiency" and max_efficiency_loss is None:
        raise ValueError("max_efficiency_loss is required in efficiency mode")
    if mode == "deadline" and deadline_hours is None:
        raise ValueError("deadline_hours is required in deadline mode")

    hc = constraints or HardConstraints()
    nc0 = pilot.baseline_cores
    t0 = pilot.baseline_time_per_iter_s
    n_iter = pilot.n_iterations

    step = stride if stride is not None else _auto_stride(nc0, cores_max)
    nc_range = range(nc0, cores_max + 1, step)

    candidates = build_scaling_curve(nc_range, params, nc0, t0, n_iter, mesh)

    accepted: list[CandidateConfig] = []
    rejected: list[RejectedConfig] = []

    for c in candidates:
        reasons: list[str] = check_hard_constraints(c.cores, mesh, hc)

        if mode == "efficiency" and max_efficiency_loss is not None:
            if c.efficiency_loss > max_efficiency_loss:
                reasons.append("efficiency_loss")
        elif mode == "deadline" and deadline_hours is not None:
            if c.runtime_hours > deadline_hours:
                reasons.append("deadline")

        if reasons:
            rejected.append(RejectedConfig(cores=c.cores, reasons=tuple(reasons)))
        else:
            accepted.append(c)

    optimal: CandidateConfig | None = None
    if accepted:
        if mode == "efficiency":
            optimal = max(accepted, key=lambda c: c.cores)
        else:
            optimal = min(accepted, key=lambda c: c.cores)

    metadata: dict[str, str | float | int] = {
        "mode": mode,
        "beta": params.beta,
        "beta_source": params.beta_source,
        "nc0": nc0,
        "t0_s": t0,
        "n_iterations": n_iter,
        "num_cells": mesh.num_cells,
        "cores_max": cores_max,
        "stride": step,
    }
    if max_efficiency_loss is not None:
        metadata["max_efficiency_loss"] = max_efficiency_loss
    if deadline_hours is not None:
        metadata["deadline_hours"] = deadline_hours

    return OptimizationResult(
        mode=mode,
        optimal=optimal,
        accepted=tuple(accepted),
        rejected=tuple(rejected),
        metadata=metadata,
    )
