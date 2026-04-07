"""CFD Performance & Scaling Estimator for steady RANS simulations."""

from __future__ import annotations

from cfd_perf.benchmark.ingest import load_pilot, pilot_from_data
from cfd_perf.benchmark.models import PilotPoint, PilotSeries
from cfd_perf.mesh.analyzer import analyze_mesh, mesh_from_data
from cfd_perf.mesh.models import MeshStats
from cfd_perf.models.parameters import ModelParameters
from cfd_perf.models.strong_scaling import fit_beta, fit_scaling_model
from cfd_perf.optimizer.models import OptimizationResult
from cfd_perf.optimizer.selector import optimize
from cfd_perf.io.plotting import plot_scaling
from cfd_perf.checkpoint.optimal_interval import (
    survival_probability,
    expected_utilization,
    optimal_interval,
    mtbf_to_failure_rate,
    mtbf_years_to_failure_rate,
)

__version__ = "0.1.0"

__all__ = [
    "analyze_mesh",
    "mesh_from_data",
    "load_pilot",
    "pilot_from_data",
    "fit_beta",
    "fit_scaling_model",
    "optimize",
    "plot_scaling",
    "survival_probability",
    "expected_utilization",
    "optimal_interval",
    "mtbf_to_failure_rate",
    "mtbf_years_to_failure_rate",
    "MeshStats",
    "PilotPoint",
    "PilotSeries",
    "ModelParameters",
    "OptimizationResult",
]
