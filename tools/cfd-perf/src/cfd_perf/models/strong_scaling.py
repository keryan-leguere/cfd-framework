"""Strong-scaling performance model for steady RANS.

Beta model (classical):
    T(Nc) = T0 * [ (Nc0 / Nc) + beta * (1 - Nc0 / Nc) ]

Empirical model (quadratic in log-space):
    T(Nc) = a * ln(Nc)^2 + b * ln(Nc) + c

Derived (both models):
    S(Nc)        = T0 / T(Nc)
    E(Nc)        = S(Nc) / (Nc / Nc0)
    eff_loss(Nc) = 1 - E(Nc)
    runtime(Nc)  = T(Nc) * N_iterations
"""

from __future__ import annotations

from typing import Literal

import numpy as np

from cfd_perf.benchmark.models import PilotSeries
from cfd_perf.models.parameters import BETA_DEFAULT, BETA_MAX, BETA_MIN, ModelParameters

_MIN_PILOT_FOR_EMPIRICAL = 3


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Beta fitting (existing)
# ---------------------------------------------------------------------------

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

    r = nc0 / measured_nc
    a = t0 * (1.0 - r)
    b = t0 * r
    residual_rhs = measured_t - b

    denom = float(np.dot(a, a))
    if denom < 1e-30:
        return ModelParameters(beta=BETA_DEFAULT, beta_source="fixed")

    beta_raw = float(np.dot(a, residual_rhs)) / denom
    beta_clamped = _clamp(beta_raw, BETA_MIN, BETA_MAX)
    return ModelParameters(beta=round(beta_clamped, 6), beta_source="fitted")


# ---------------------------------------------------------------------------
# Empirical fitting (quadratic in ln(cores) space)
# ---------------------------------------------------------------------------

def _fit_empirical(pilot: PilotSeries) -> tuple[float, float, float]:
    """Fit T(Nc) = a*ln(Nc)^2 + b*ln(Nc) + c from pilot points.

    Returns (a, b, c).  Requires >= 3 points.
    """
    nc = np.array([p.cores for p in pilot.points], dtype=np.float64)
    t = np.array([p.time_per_iter_s for p in pilot.points], dtype=np.float64)
    x = np.log(nc)
    coeffs = np.polyfit(x, t, deg=2)
    return (float(coeffs[0]), float(coeffs[1]), float(coeffs[2]))


def fit_scaling_model(
    pilot: PilotSeries,
    model_hint: Literal["auto", "beta", "empirical"] = "auto",
) -> ModelParameters:
    """Fit the scaling model from pilot data with automatic model selection.

    *model_hint* controls the strategy:

    - ``"auto"``: empirical if >= 3 pilot points, beta otherwise.
    - ``"beta"``:  always use the single-beta model.
    - ``"empirical"``: require >= 3 points for the quadratic fit;
      raises ``ValueError`` if fewer are available.

    The returned ``ModelParameters`` always contains a valid *beta* (used
    for backward-compatible derived metrics) alongside any empirical data.
    """
    n_pts = len(pilot.points)

    use_empirical = False
    if model_hint == "empirical":
        if n_pts < _MIN_PILOT_FOR_EMPIRICAL:
            raise ValueError(
                f"empirical model requires >= {_MIN_PILOT_FOR_EMPIRICAL} pilot points, "
                f"got {n_pts}"
            )
        use_empirical = True
    elif model_hint == "auto":
        use_empirical = n_pts >= _MIN_PILOT_FOR_EMPIRICAL

    beta_params = fit_beta(pilot)

    if not use_empirical:
        return beta_params

    coeffs = _fit_empirical(pilot)
    nc_min = min(p.cores for p in pilot.points)
    nc_max = max(p.cores for p in pilot.points)

    return ModelParameters(
        beta=beta_params.beta,
        beta_source=beta_params.beta_source,
        model_kind="empirical",
        empirical_coeffs=coeffs,
        empirical_nc_range=(nc_min, nc_max),
    )


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

def time_per_iter(nc: int, nc0: int, t0: float, beta: float) -> float:
    """Predict wall-time per iteration at *nc* cores (beta model only)."""
    r = nc0 / nc
    return t0 * (r + beta * (1.0 - r))


def predict_time_per_iter(nc: int, nc0: int, t0: float, params: ModelParameters) -> float:
    """Predict wall-time per iteration using whichever model *params* carries."""
    if params.model_kind == "empirical" and params.empirical_coeffs is not None:
        a, b, c = params.empirical_coeffs
        x = np.log(float(nc))
        t = a * x * x + b * x + c
        return max(t, 1e-9)
    return time_per_iter(nc, nc0, t0, params.beta)


def speedup(nc: int, nc0: int, t0: float, beta: float) -> float:
    """Speedup S(Nc) = T0 / T(Nc)."""
    return t0 / time_per_iter(nc, nc0, t0, beta)


def predict_speedup(nc: int, nc0: int, t0: float, params: ModelParameters) -> float:
    """Speedup using whichever model *params* carries."""
    return t0 / predict_time_per_iter(nc, nc0, t0, params)


def efficiency(nc: int, nc0: int, t0: float, beta: float) -> float:
    """Parallel efficiency E(Nc) = S(Nc) / (Nc / Nc0)."""
    return speedup(nc, nc0, t0, beta) / (nc / nc0)


def predict_efficiency(nc: int, nc0: int, t0: float, params: ModelParameters) -> float:
    """Parallel efficiency using whichever model *params* carries."""
    return predict_speedup(nc, nc0, t0, params) / (nc / nc0)


def efficiency_loss(nc: int, nc0: int, t0: float, beta: float) -> float:
    """Efficiency loss = 1 - E(Nc)."""
    return 1.0 - efficiency(nc, nc0, t0, beta)


def predict_efficiency_loss(nc: int, nc0: int, t0: float, params: ModelParameters) -> float:
    """Efficiency loss using whichever model *params* carries."""
    return 1.0 - predict_efficiency(nc, nc0, t0, params)


def total_runtime_hours(nc: int, nc0: int, t0: float, beta: float, n_iterations: int) -> float:
    """Total runtime in hours."""
    return time_per_iter(nc, nc0, t0, beta) * n_iterations / 3600.0


def predict_total_runtime_hours(
    nc: int, nc0: int, t0: float, params: ModelParameters, n_iterations: int,
) -> float:
    """Total runtime in hours using whichever model *params* carries."""
    return predict_time_per_iter(nc, nc0, t0, params) * n_iterations / 3600.0
