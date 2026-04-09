"""Convergence analysis for CFD time-series.

Provides :class:`ConvergenceAnalyzer` which detects regime type,
computes convergence metrics (Cauchy, plateau, rate) and delivers
sliding-window statistics.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from cfd_stats.utils.validation import clean_signal


class ConvergenceAnalyzer:
    """Convergence analysis for a DataFrame of CFD coefficients.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain an iteration/time column and one or more numeric columns.
    iter_col : str
        Name of the iteration / time column.
    """

    def __init__(self, df: pd.DataFrame, iter_col: str = "iter") -> None:
        self.df = df.sort_values(iter_col).reset_index(drop=True)
        self.iter_col = iter_col
        self._iters: np.ndarray = self.df[iter_col].to_numpy(dtype=float)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_regime(self, coeff_col: str) -> dict:
        """Detect the dominant regime of *coeff_col*.

        Returns
        -------
        dict
            Keys: ``regime``, ``transient_end_iter``, ``is_steady``,
            ``quality_score``.
        """
        signal = clean_signal(self.df[coeff_col].to_numpy(dtype=float))
        n = signal.size

        transient_end_idx = self._detect_transient_end(signal)
        transient_end_iter = int(self._iters[transient_end_idx])

        steady = signal[transient_end_idx:]
        if steady.size < 20:
            return {
                "regime": "transient",
                "transient_end_iter": transient_end_iter,
                "is_steady": False,
                "quality_score": 0.0,
            }

        is_diverging = self._check_divergence(steady)
        if is_diverging:
            return {
                "regime": "diverging",
                "transient_end_iter": transient_end_iter,
                "is_steady": False,
                "quality_score": 0.0,
            }

        is_periodic, period_confidence = self._quick_periodicity_check(steady)
        cauchy = self._cauchy_criterion(steady)

        # Cauchy is (1 - p_value) from a two-sample t-test on the tail.
        # Converged when p > 0.05, i.e. cauchy < 0.95.
        cauchy_threshold = 0.95

        if is_periodic and period_confidence > 0.10:
            regime = "periodic"
            is_steady = False
            quality = min(100.0, period_confidence * 100)
        elif cauchy < cauchy_threshold:
            regime = "converged"
            is_steady = True
            quality = min(100.0, (1.0 - cauchy) * 100)
        else:
            regime = "transient"
            is_steady = False
            quality = max(0.0, (1.0 - cauchy) * 50)

        # Penalise if steady region is small
        steady_frac = steady.size / n
        quality *= min(1.0, steady_frac / 0.3)

        return {
            "regime": regime,
            "transient_end_iter": transient_end_iter,
            "is_steady": is_steady,
            "quality_score": round(float(quality), 2),
        }

    def compute_convergence_metrics(self, coeff_col: str, *, window: int | None = None) -> dict:
        """Compute convergence metrics for *coeff_col*.

        Returns
        -------
        dict
            Keys: ``convergence_rate``, ``plateau_iterations``,
            ``final_variance``, ``cauchy_criterion``, ``is_converged``.
        """
        signal = clean_signal(self.df[coeff_col].to_numpy(dtype=float))
        n = signal.size
        w = window or max(50, n // 20)

        # Compute metrics on the steady portion
        te_idx = self._detect_transient_end(signal)
        steady = signal[te_idx:] if signal[te_idx:].size > 2 * w else signal

        tail = steady[-w:]
        rate = self._convergence_rate(signal)
        cauchy = self._cauchy_criterion(steady, window=w)
        plateau_iters = self._plateau_length(steady, window=w)
        final_var = float(np.var(tail))
        converged = cauchy < 0.95 and plateau_iters > w

        return {
            "convergence_rate": round(float(rate), 8),
            "plateau_iterations": int(plateau_iters),
            "final_variance": float(final_var),
            "cauchy_criterion": round(float(cauchy), 8),
            "is_converged": converged,
        }

    def sliding_statistics(self, coeff_col: str, window_size: int = 100) -> pd.DataFrame:
        """Compute rolling statistics over *coeff_col*.

        Returns
        -------
        pd.DataFrame
            Columns: ``iter``, ``mean``, ``std``, ``min``, ``max``,
            ``variance_ratio``.
        """
        s = self.df[coeff_col]
        roll = s.rolling(window=window_size, min_periods=max(1, window_size // 2))
        out = pd.DataFrame({
            "iter": self._iters,
            "mean": roll.mean(),
            "std": roll.std(),
            "min": roll.min(),
            "max": roll.max(),
        })
        global_var = s.var()
        out["variance_ratio"] = (roll.var() / global_var) if global_var > 0 else 0.0
        return out

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _detect_transient_end(self, signal: np.ndarray, *, min_frac: float = 0.05) -> int:
        """Combined mean-drift + variance-ratio transient detection.

        A window is considered *settled* only when **both**:

        1. Its local mean is within ``2 * tail_std`` of the tail mean
           (mean has stopped drifting).
        2. Its local variance is below ``5 * tail_var``
           (amplitude has stabilised).

        Three consecutive passes are required to avoid false triggers
        from a single quiet window inside the transient.
        """
        n = signal.size
        if n < 40:
            return 0

        w = max(50, n // 20)
        tail_mean = float(signal[-w:].mean())
        tail_std = float(np.std(signal[-w:]))
        tail_var = tail_std**2

        var_thresh = max(tail_var * 5, 1e-20)
        mean_tol = max(2.0 * tail_std, 1e-20)

        step = max(1, w // 4)
        consecutive = 0
        required = 3

        for i in range(0, n - w, step):
            seg = signal[i : i + w]
            seg_mean = float(seg.mean())
            seg_var = float(np.var(seg))

            mean_ok = abs(seg_mean - tail_mean) < mean_tol
            var_ok = seg_var < var_thresh

            if mean_ok and var_ok:
                consecutive += 1
                if consecutive >= required:
                    first_pass = i - (required - 1) * step
                    idx = max(int(n * min_frac), first_pass + w)
                    return min(idx, int(n * 0.8))
            else:
                consecutive = 0

        # Fallback: CUSUM
        cusum = np.cumsum(signal - tail_mean)
        idx = int(np.argmax(np.abs(cusum)))
        min_idx = int(n * min_frac)
        return max(min_idx, min(idx, int(n * 0.8)))

    @staticmethod
    def _cauchy_criterion(signal: np.ndarray, window: int = 200) -> float:
        """Cauchy convergence criterion using a two-sample t-test.

        Compares the means of two consecutive tail windows.  Returns a
        value between 0 (perfectly converged) and 1 (clearly drifting),
        derived from the t-test p-value.
        """
        if signal.size < 2 * window:
            window = max(10, signal.size // 4)
        half = window // 2
        seg1 = signal[-(2 * half) : -half]
        seg2 = signal[-half:]
        _, p = sp_stats.ttest_ind(seg1, seg2, equal_var=False)
        # Map p-value to a 0-1 criterion: p=1 → 0 (converged), p=0 → 1
        return float(1.0 - p)

    @staticmethod
    def _convergence_rate(signal: np.ndarray) -> float:
        """Slope of log-abs-deviation from final mean (OLS)."""
        n = signal.size
        if n < 20:
            return 0.0
        final_mean = signal[-max(50, n // 10) :].mean()
        deviation = np.abs(signal - final_mean)
        deviation = np.clip(deviation, 1e-30, None)
        log_dev = np.log10(deviation)
        x = np.arange(n, dtype=float)
        slope, _, _, _, _ = sp_stats.linregress(x, log_dev)
        return float(slope)

    @staticmethod
    def _plateau_length(signal: np.ndarray, window: int = 100) -> int:
        """Count how many tail points have variance below threshold."""
        if signal.size < window:
            return 0
        tail_var = np.var(signal[-window:])
        global_var = np.var(signal)
        if global_var == 0:
            return signal.size
        threshold = 0.01 * global_var
        # Walk backwards from the end
        for k in range(signal.size, window - 1, -1):
            seg_var = np.var(signal[k - window : k])
            if seg_var > threshold:
                return signal.size - k
        return signal.size

    @staticmethod
    def _check_divergence(signal: np.ndarray) -> bool:
        """True if the signal is clearly diverging (monotone growth).

        Detrends the tail before computing the noise level so that a
        strong linear trend is not masked by its own inflated std.
        """
        n = signal.size
        if n < 20:
            return False
        tail = signal[-max(20, n // 5) :]
        x = np.arange(tail.size, dtype=float)
        slope, intercept, _, p, stderr = sp_stats.linregress(x, tail)
        # Noise level = std of residuals after removing the linear trend
        residuals = tail - (slope * x + intercept)
        noise_std = float(np.std(residuals))
        # Diverging if slope is statistically significant and much larger than noise
        return bool(abs(slope) > 0 and p < 0.01 and abs(slope) * tail.size > 3 * noise_std)

    @staticmethod
    def _quick_periodicity_check(signal: np.ndarray) -> tuple[bool, float]:
        """Fast FFT-based periodicity check returning (is_periodic, confidence).

        Uses power spectrum (squared magnitudes) with a Hanning window
        to reduce spectral leakage from incomplete cycles.
        """
        n = signal.size
        if n < 40:
            return False, 0.0
        detrended = signal - np.mean(signal)
        window = np.hanning(n)
        spectrum = np.abs(np.fft.rfft(detrended * window)) ** 2
        spectrum[0] = 0  # ignore DC
        if spectrum.max() == 0:
            return False, 0.0
        peak_power = spectrum.max()
        total_power = spectrum.sum()
        confidence = float(peak_power / total_power)
        return confidence > 0.10, confidence
