"""Optimal check-point interval for jobs subject to node failures.

Assumes exponential failure rate **per compute node** (not per core). Failures
are modelled at node level (hardware, network, etc.); N is the number of nodes.

Maximizes expected useful compute time by balancing survival probability
vs time spent writing checkpoints.

All time arguments and return values are in **hours** unless noted.
"""

from __future__ import annotations

import math


def survival_probability(
    tc: float,
    n_nodes: int,
    lambda_per_hour: float,
) -> float:
    """Survival probability of a job running tc hours on n_nodes.

    P_N(tc | λ) = exp(-λ N tc)

    Parameters
    ----------
    tc : float
        Computation time between checkpoints (hours).
    n_nodes : int
        Number of compute nodes (not cores).
    lambda_per_hour : float
        Mean failure rate per node (per hour).

    Returns
    -------
    float
        Probability that no node fails during tc (in [0, 1]).
    """
    if tc < 0 or n_nodes <= 0 or lambda_per_hour < 0:
        raise ValueError("tc, n_nodes, and lambda_per_hour must be non-negative; n_nodes > 0")
    return math.exp(-lambda_per_hour * n_nodes * tc)


def expected_utilization(
    tc: float,
    Tc: float,
    n_nodes: int,
    lambda_per_hour: float,
) -> float:
    """Expected utilization (useful compute time fraction) w(tc).

    w(tc) = (tc / (tc + Tc)) * exp(-λ N tc)

    This is the objective to maximize: fraction of time spent computing
    (vs checkpoint I/O) weighted by survival probability.

    Parameters
    ----------
    tc : float
        Computation time between checkpoints (hours).
    Tc : float
        Duration of one checkpoint write (hours).
    n_nodes : int
        Number of compute nodes (not cores).
    lambda_per_hour : float
        Mean failure rate per node (per hour).

    Returns
    -------
    float
        Expected utilization in [0, 1].
    """
    if tc <= 0 or Tc < 0:
        raise ValueError("tc must be positive; Tc non-negative")
    if tc + Tc == 0:
        return 0.0
    ratio = tc / (tc + Tc)
    surv = survival_probability(tc, n_nodes, lambda_per_hour)
    return ratio * surv


def optimal_interval(
    Tc: float,
    n_nodes: int,
    lambda_per_hour: float,
) -> float:
    """Optimal check-point interval (hours) that maximizes expected utilization.

    Closed-form solution:

        t̂c = (Tc / 2) * (sqrt(1 + 4 / (λ N Tc)) - 1)

    Parameters
    ----------
    Tc : float
        Duration of one checkpoint write (hours).
    n_nodes : int
        Number of compute nodes (not cores).
    lambda_per_hour : float
        Mean failure rate per node (per hour).

    Returns
    -------
    float
        Optimal tc in hours.
    """
    if Tc < 0 or n_nodes <= 0 or lambda_per_hour <= 0:
        raise ValueError("Tc >= 0, n_nodes > 0, lambda_per_hour > 0 required")
    if Tc == 0:
        return float("inf")  # no I/O cost → checkpoint as rarely as desired
    x = 4.0 / (lambda_per_hour * n_nodes * Tc)
    return 0.5 * Tc * (math.sqrt(1.0 + x) - 1.0)


def mtbf_to_failure_rate(mtbf_hours: float) -> float:
    """Convert mean time between failures (MTBF) to failure rate λ (per hour).

    λ = 1 / MTBF

    Parameters
    ----------
    mtbf_hours : float
        Mean time between failures of one node (hours), e.g. 15 years in hours.

    Returns
    -------
    float
        Failure rate per hour.
    """
    if mtbf_hours <= 0:
        raise ValueError("mtbf_hours must be positive")
    return 1.0 / mtbf_hours


def mtbf_years_to_failure_rate(mtbf_years: float) -> float:
    """Convert MTBF in years to failure rate per hour.

    Uses 1 year = 365.25 days.
    """
    hours_per_year = 365.25 * 24
    return mtbf_to_failure_rate(mtbf_years * hours_per_year)
