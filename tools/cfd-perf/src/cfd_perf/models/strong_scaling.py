"""Strong-scaling performance model for steady RANS.

Model:
    T(Nc) = T0 * [ (Nc0 / Nc) + beta * (1 - Nc0 / Nc) ]

Derived:
    S(Nc)        = T0 / T(Nc)
    E(Nc)        = S(Nc) / (Nc / Nc0)
    eff_loss(Nc) = 1 - E(Nc)
    runtime(Nc)  = T(Nc) * N_iterations
"""

from __future__ import annotations

import numpy as np

from cfd_perf.benchmark.models import PilotSeries
from cfd_perf.models.parameters import BETA_DEFAULT, BETA_MAX, BETA_MIN, ModelParameters


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def fit_beta(pilot: PilotSeries) -> ModelParameters:
    """Fit beta from >=2 pilot points by least-squares, or use default.

    For a single pilot point, the default fixed beta is returned.
    """
    if len(pilot.points) < 2:
        return ModelParameters(beta=BETA_DEFAULT, beta_source="fixed")

    nc0 = pilot.baseline_cores
    t0 = pilot.baseline_time_per_iter_s

    measured_nc = np.array([p.cores for p in pilot.points], dtype=np.float64)
    measured_t = np.array([p.time_per_iter_s for p in pilot.points], dtype=np.float64)

    # T(Nc) = T0 * [ (Nc0/Nc) + beta * (1 - Nc0/Nc) ]
    # Let r = Nc0 / Nc, then T = T0 * [ r + beta * (1 - r) ]
    # => T / T0 = r + beta * (1 - r)
    # => beta = (T/T0 - r) / (1 - r)   for each point where r != 1
    # Least-squares: minimize sum( (T_meas - T_model)^2 ) over beta
    # Linear in beta, closed-form via normal equation on single variable.

    r = nc0 / measured_nc
    a = t0 * (1.0 - r)  # coefficient of beta
    b = t0 * r  # constant term
    residual_rhs = measured_t - b  # = a * beta (ideally)

    # Normal equation: beta_hat = sum(a * residual_rhs) / sum(a^2)
    denom = float(np.dot(a, a))
    if denom < 1e-30:
        return ModelParameters(beta=BETA_DEFAULT, beta_source="fixed")

    beta_raw = float(np.dot(a, residual_rhs)) / denom
    beta_clamped = _clamp(beta_raw, BETA_MIN, BETA_MAX)
    return ModelParameters(beta=round(beta_clamped, 6), beta_source="fitted")


def time_per_iter(nc: int, nc0: int, t0: float, beta: float) -> float:
    """Predict wall-time per iteration at *nc* cores."""
    r = nc0 / nc
    return t0 * (r + beta * (1.0 - r))


def speedup(nc: int, nc0: int, t0: float, beta: float) -> float:
    """Speedup S(Nc) = T0 / T(Nc)."""
    return t0 / time_per_iter(nc, nc0, t0, beta)


def efficiency(nc: int, nc0: int, t0: float, beta: float) -> float:
    """Parallel efficiency E(Nc) = S(Nc) / (Nc / Nc0)."""
    return speedup(nc, nc0, t0, beta) / (nc / nc0)


def efficiency_loss(nc: int, nc0: int, t0: float, beta: float) -> float:
    """Efficiency loss = 1 - E(Nc)."""
    return 1.0 - efficiency(nc, nc0, t0, beta)


def total_runtime_hours(nc: int, nc0: int, t0: float, beta: float, n_iterations: int) -> float:
    """Total runtime in hours."""
    return time_per_iter(nc, nc0, t0, beta) * n_iterations / 3600.0
