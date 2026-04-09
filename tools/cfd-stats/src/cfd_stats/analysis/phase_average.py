"""Phase-locked averaging for periodic CFD signals."""

from __future__ import annotations

import numpy as np

from cfd_stats.core.periodicity import PeriodicityDetector


def phase_average(
    signal: np.ndarray,
    time: np.ndarray,
    *,
    period: float | None = None,
    transient_end: int = 0,
) -> dict:
    """Compute the phase-locked average of a periodic signal.

    Parameters
    ----------
    signal : np.ndarray
        Full time-series.
    time : np.ndarray
        Corresponding time / iteration stamps.
    period : float, optional
        Cycle period.  Auto-detected if ``None``.
    transient_end : int
        Index from which to start (skip transient).

    Returns
    -------
    dict
        Keys: ``mean_cycle``, ``std_cycle``, ``n_cycles``,
        ``phase``, ``min_envelope``, ``max_envelope``.
    """
    sig = signal[transient_end:]
    t = time[transient_end:]

    pdet = PeriodicityDetector(sig, t)
    if period is None:
        val = pdet.validate_periodicity()
        period = val["period"]

    if not np.isfinite(period) or period <= 0:
        return _empty_result()

    cycles = pdet.extract_phase_locked_cycles(period=period)
    if cycles.size == 0:
        return _empty_result()

    n_cycles, pts = cycles.shape
    mean_cycle = cycles.mean(axis=0)
    std_cycle = cycles.std(axis=0, ddof=1) if n_cycles > 1 else np.zeros(pts)
    min_env = cycles.min(axis=0)
    max_env = cycles.max(axis=0)
    phase = np.linspace(0, 2 * np.pi, pts, endpoint=False)

    return {
        "mean_cycle": mean_cycle,
        "std_cycle": std_cycle,
        "n_cycles": n_cycles,
        "phase": phase,
        "min_envelope": min_env,
        "max_envelope": max_env,
    }


def _empty_result() -> dict:
    return {
        "mean_cycle": np.array([]),
        "std_cycle": np.array([]),
        "n_cycles": 0,
        "phase": np.array([]),
        "min_envelope": np.array([]),
        "max_envelope": np.array([]),
    }
