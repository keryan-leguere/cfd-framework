"""Strong-scaling performance model for steady RANS.

Model
-----
Wall-time per iteration on ``Nc`` cores is decomposed into three physical
contributions::

    T(Nc) = t_serial + t_parallel / Nc + t_comm * Nc^gamma
            \\_______/   \\____________/   \\______________/
             Amdahl       perfect            communication
             floor        speedup            / halo exchange

- ``t_serial``    work that never parallelises (I/O, setup, reductions).
- ``t_parallel``  work that divides perfectly across cores.
- ``t_comm``      MPI cost, which *grows* with core count: with a fixed mesh,
  adding cores shrinks subdomains, so the surface/volume ratio rises and each
  rank spends proportionally more time exchanging halos.
- ``gamma``       how aggressively that communication cost grows.

The ``t_comm`` term is what makes this model able to represent the U-shaped
curve every real machine shows: time falls, bottoms out, then *rises* once
communication dominates.  A model without it (see ``ModelKind.AMDAHL``) is
monotonically decreasing and will always mis-predict the high-core regime.

Fitting
-------
For a *fixed* gamma the model is linear in ``(t_serial, t_parallel, t_comm)``,
so we solve a linear least-squares problem for each gamma on a scan grid and
keep the best.  Two details matter for real data:

1. Residuals are weighted by ``1/T_measured``, so we minimise *relative*
   error.  Unweighted fitting lets the slow low-core points dominate and the
   fast high-core points -- exactly the ones that decide the answer -- are
   fitted to noise.
2. All three coefficients are constrained non-negative (they are physical
   times).  We enforce this by enumerating active sets: with only three
   coefficients there are seven subsets, so this is exact and cheap, with no
   iterative solver and no SciPy dependency.

Everything here is NumPy-only, deliberately: the package must install on an
air-gapped cluster with nothing but a wheel cache.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from itertools import product

import numpy as np

from cfd_perf.data.pilot import PilotSeries

# Communication exponent scan range.  0.05 is "communication barely grows";
# 2.0 covers all-to-all-ish behaviour on a badly decomposed mesh.
GAMMA_MIN = 0.05
GAMMA_MAX = 2.0
GAMMA_STEPS = 196

MIN_POINTS_FOR_COMM = 3
_EPS = 1e-12


class ModelKind(enum.StrEnum):
    """Which functional form was fitted."""

    AMDAHL_COMM = "amdahl+comm"
    """Full model with the communication term.  Needs >= 3 pilot points."""

    AMDAHL = "amdahl"
    """Fallback without the communication term.  Monotone; needs >= 2 points."""


@dataclass(frozen=True)
class FitQuality:
    """How well the fitted model reproduces the pilot measurements.

    Fit quality is a first-class result, always shown by the CLI: a sizing
    tool must never present a poor fit as if it were reliable, so the user
    can see the error and act on it.
    """

    r_squared: float
    max_rel_err_pct: float
    rmse_rel_pct: float
    n_points: int

    @property
    def is_trustworthy(self) -> bool:
        """Whether the fit tracks the pilot data closely enough to act on.

        5% is the threshold below which the fit error is comparable to the
        run-to-run jitter of a real cluster, so tightening it further would
        be fitting noise.
        """
        return self.max_rel_err_pct <= 5.0

    @property
    def verdict(self) -> str:
        if self.max_rel_err_pct <= 2.0:
            return "excellent"
        if self.max_rel_err_pct <= 5.0:
            return "good"
        if self.max_rel_err_pct <= 10.0:
            return "marginal"
        return "poor"


@dataclass(frozen=True)
class ScalingModel:
    """A fitted strong-scaling model.

    ``ref_cores``/``ref_time_s`` are the measured baseline, kept so that
    speedup and efficiency are always reported against a real measurement
    rather than an extrapolation.
    """

    t_serial: float
    t_parallel: float
    t_comm: float
    gamma: float
    kind: ModelKind
    quality: FitQuality
    ref_cores: int
    ref_time_s: float
    fitted_range: tuple[int, int]

    def __post_init__(self) -> None:
        for name in ("t_serial", "t_parallel", "t_comm"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative, got {getattr(self, name)}")
        if self.ref_cores <= 0:
            raise ValueError(f"ref_cores must be positive, got {self.ref_cores}")
        if self.ref_time_s <= 0:
            raise ValueError(f"ref_time_s must be positive, got {self.ref_time_s}")

    # -- prediction ---------------------------------------------------------

    def time_per_iter(self, nc: int | float) -> float:
        """Predicted wall-time per iteration (s) on *nc* cores."""
        nc_f = float(nc)
        if nc_f <= 0:
            raise ValueError(f"nc must be positive, got {nc}")
        t = self.t_serial + self.t_parallel / nc_f + self.t_comm * nc_f**self.gamma
        return float(max(t, _EPS))

    def speedup(self, nc: int | float) -> float:
        """Speedup against the model at the reference core count.

        Deliberately referenced to ``self.time_per_iter(ref_cores)`` and not
        to the raw measurement, so that ``speedup(ref_cores) == 1`` exactly
        and the curve is internally consistent.
        """
        return self.time_per_iter(self.ref_cores) / self.time_per_iter(nc)

    def efficiency(self, nc: int | float) -> float:
        """Parallel efficiency E(Nc) = S(Nc) / (Nc / Nc_ref)."""
        return self.speedup(nc) / (float(nc) / self.ref_cores)

    def efficiency_loss(self, nc: int | float) -> float:
        return 1.0 - self.efficiency(nc)

    def runtime_hours(self, nc: int | float, n_iterations: int) -> float:
        return self.time_per_iter(nc) * n_iterations / 3600.0

    def core_hours(self, nc: int | float, n_iterations: int) -> float:
        """Billed CPU budget -- what the allocation is actually charged."""
        return self.runtime_hours(nc, n_iterations) * float(nc)

    # -- diagnostics --------------------------------------------------------

    def time_minimum_cores(self, nc_max: int) -> int | None:
        """Core count minimising wall-time, or None if still falling at *nc_max*.

        Past this point extra cores make the job *slower*: the answer to
        "how many CPUs" can never usefully exceed it.
        """
        grid = np.arange(1, nc_max + 1)
        times = np.array([self.time_per_iter(int(n)) for n in grid])
        idx = int(np.argmin(times))
        if idx == len(grid) - 1:
            return None
        return int(grid[idx])

    def is_extrapolating(self, nc: int) -> bool:
        """Whether *nc* falls outside the pilot range the fit was built from."""
        lo, hi = self.fitted_range
        return nc < lo or nc > hi

    def describe(self) -> str:
        """One-line human-readable formula with the fitted numbers."""
        if self.kind is ModelKind.AMDAHL:
            return f"T(Nc) = {self.t_serial:.4g} + {self.t_parallel:.4g}/Nc"
        return (
            f"T(Nc) = {self.t_serial:.4g} + {self.t_parallel:.4g}/Nc "
            f"+ {self.t_comm:.4g}*Nc^{self.gamma:.3g}"
        )


# ---------------------------------------------------------------------------
# Fitting
# ---------------------------------------------------------------------------


def _design_matrix(nc: np.ndarray, gamma: float, with_comm: bool) -> np.ndarray:
    cols = [np.ones_like(nc), 1.0 / nc]
    if with_comm:
        cols.append(nc**gamma)
    return np.column_stack(cols)


def _solve_nonneg(design: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, float] | None:
    """Relative-error least squares with all coefficients constrained >= 0.

    Returns ``(coeffs, sse_relative)`` or None if no non-negative solution
    exists.  Exact via active-set enumeration (<= 3 coefficients -> 7 subsets).
    """
    n_coef = design.shape[1]
    weights = 1.0 / t
    design_w = design * weights[:, None]
    t_w = t * weights

    best: tuple[np.ndarray, float] | None = None
    for mask in product((0, 1), repeat=n_coef):
        if not any(mask):
            continue
        idx = [i for i, m in enumerate(mask) if m]
        sol, *_ = np.linalg.lstsq(design_w[:, idx], t_w, rcond=None)
        if np.any(sol < 0):
            continue
        coeffs = np.zeros(n_coef)
        coeffs[idx] = sol
        resid = (design @ coeffs - t) / t
        sse = float(np.sum(resid**2))
        if best is None or sse < best[1]:
            best = (coeffs, sse)
    return best


def _quality(pred: np.ndarray, meas: np.ndarray) -> FitQuality:
    rel = (pred - meas) / meas
    ss_res = float(np.sum((pred - meas) ** 2))
    ss_tot = float(np.sum((meas - meas.mean()) ** 2))
    # A single distinct measurement makes R^2 undefined; report 1.0 rather
    # than dividing by zero, and let max_rel_err_pct carry the signal.
    r2 = 1.0 - ss_res / ss_tot if ss_tot > _EPS else 1.0
    return FitQuality(
        r_squared=r2,
        max_rel_err_pct=float(np.max(np.abs(rel)) * 100.0),
        rmse_rel_pct=float(np.sqrt(np.mean(rel**2)) * 100.0),
        n_points=len(meas),
    )


def fit_model(pilot: PilotSeries, *, kind: ModelKind | None = None) -> ScalingModel:
    """Fit the scaling model to *pilot* measurements.

    *kind* forces a functional form; the default (None) picks the full
    ``amdahl+comm`` model when there are enough points and falls back to
    plain ``amdahl`` otherwise.

    Raises
    ------
    ValueError
        If fewer than 2 pilot points are supplied, or if ``AMDAHL_COMM`` is
        forced with fewer than 3 points (the fit would be exactly determined
        and would report a meaningless perfect quality score).
    """
    n_pts = len(pilot.points)
    if n_pts < 2:
        raise ValueError(
            f"fitting needs >= 2 pilot points, got {n_pts}. "
            "Run the pilot at a second core count."
        )

    if kind is ModelKind.AMDAHL_COMM and n_pts < MIN_POINTS_FOR_COMM:
        raise ValueError(
            f"the '{ModelKind.AMDAHL_COMM}' model needs >= {MIN_POINTS_FOR_COMM} pilot "
            f"points, got {n_pts}"
        )

    resolved = kind or (
        ModelKind.AMDAHL_COMM if n_pts >= MIN_POINTS_FOR_COMM else ModelKind.AMDAHL
    )
    with_comm = resolved is ModelKind.AMDAHL_COMM

    nc = np.array([p.cores for p in pilot.points], dtype=np.float64)
    t = np.array([p.time_per_iter_s for p in pilot.points], dtype=np.float64)

    gammas = (
        np.linspace(GAMMA_MIN, GAMMA_MAX, GAMMA_STEPS) if with_comm else np.array([0.0])
    )

    best_coeffs: np.ndarray | None = None
    best_sse = np.inf
    best_gamma = 0.0
    for gamma in gammas:
        design = _design_matrix(nc, float(gamma), with_comm)
        solved = _solve_nonneg(design, t)
        if solved is None:
            continue
        coeffs, sse = solved
        if sse < best_sse:
            best_coeffs, best_sse, best_gamma = coeffs, sse, float(gamma)

    if best_coeffs is None:
        raise ValueError(
            "could not fit any non-negative model to the pilot data. "
            "Check that time_per_iter_s decreases with cores at least initially."
        )

    t_serial = float(best_coeffs[0])
    t_parallel = float(best_coeffs[1])
    t_comm = float(best_coeffs[2]) if with_comm else 0.0

    design = _design_matrix(nc, best_gamma, with_comm)
    pred = design @ best_coeffs

    return ScalingModel(
        t_serial=t_serial,
        t_parallel=t_parallel,
        t_comm=t_comm,
        gamma=best_gamma if with_comm else 0.0,
        kind=resolved,
        quality=_quality(pred, t),
        ref_cores=pilot.baseline_cores,
        ref_time_s=pilot.baseline_time_per_iter_s,
        fitted_range=(int(nc.min()), int(nc.max())),
    )
