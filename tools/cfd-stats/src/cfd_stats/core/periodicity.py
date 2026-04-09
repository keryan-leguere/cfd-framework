"""Periodicity detection and analysis using FFT and autocorrelation.

Provides :class:`PeriodicityDetector` for identifying periodic behaviour
in CFD time-series and extracting phase-locked cycles.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks

from cfd_stats.utils.validation import clean_signal


class PeriodicityDetector:
    """Detect and characterise periodicity in a 1-D signal.

    Parameters
    ----------
    signal : np.ndarray
        Values of the coefficient (1-D).
    time : np.ndarray
        Corresponding iteration / time stamps (1-D, same length).
    """

    def __init__(self, signal: np.ndarray, time: np.ndarray) -> None:
        if signal.shape != time.shape:
            raise ValueError(f"signal ({signal.shape}) and time ({time.shape}) shapes must match")
        self.signal = clean_signal(signal)
        self.time = time.astype(float)
        self._dt: float = float(np.median(np.diff(self.time))) if self.time.size > 1 else 1.0

    # ------------------------------------------------------------------
    # FFT
    # ------------------------------------------------------------------

    def detect_period_fft(self) -> dict:
        """Detect periodicity via Fast Fourier Transform.

        Returns
        -------
        dict
            Keys: ``period``, ``frequency``, ``dominant_frequencies``,
            ``power_spectrum``, ``freq_array``, ``is_periodic``, ``confidence``.
        """
        n = self.signal.size
        detrended = self.signal - np.mean(self.signal)
        window = np.hanning(n)
        spectrum = np.abs(np.fft.rfft(detrended * window))
        freqs = np.fft.rfftfreq(n, d=self._dt)

        # Ignore DC component
        spectrum[0] = 0.0
        total_power = float(spectrum.sum())
        if total_power == 0:
            return self._empty_fft(freqs, spectrum)

        # Top-5 dominant frequencies
        peak_indices, _ = find_peaks(spectrum, height=0.1 * spectrum.max())
        if peak_indices.size == 0:
            peak_indices = np.array([int(np.argmax(spectrum))])
        sorted_peaks = peak_indices[np.argsort(spectrum[peak_indices])[::-1]][:5]

        dominant_freq = float(freqs[sorted_peaks[0]])
        period = 1.0 / dominant_freq if dominant_freq > 0 else float("inf")
        confidence = float(spectrum[sorted_peaks[0]] / total_power)

        return {
            "period": period,
            "frequency": dominant_freq,
            "dominant_frequencies": [float(freqs[i]) for i in sorted_peaks],
            "power_spectrum": spectrum,
            "freq_array": freqs,
            "is_periodic": confidence > 0.15,
            "confidence": round(confidence, 4),
        }

    # ------------------------------------------------------------------
    # Autocorrelation
    # ------------------------------------------------------------------

    def detect_period_autocorr(self) -> dict:
        """Detect periodicity via autocorrelation.

        Returns
        -------
        dict
            Keys: ``period``, ``autocorr``, ``lags``, ``peaks``, ``confidence``.
        """
        n = self.signal.size
        detrended = self.signal - np.mean(self.signal)
        norm = float(np.dot(detrended, detrended))
        if norm == 0:
            return self._empty_autocorr(n)

        autocorr = np.correlate(detrended, detrended, mode="full")[n - 1 :]
        autocorr = autocorr / norm
        lags = np.arange(n) * self._dt

        # Find peaks in the positive part of autocorrelation
        min_dist = max(5, n // 50)
        peak_indices, props = find_peaks(autocorr[1:], distance=min_dist, height=0.1)
        peak_indices += 1  # offset for skipped index-0

        if peak_indices.size == 0:
            return {
                "period": float("inf"),
                "autocorr": autocorr,
                "lags": lags,
                "peaks": [],
                "confidence": 0.0,
            }

        # First significant peak is the fundamental period
        first_peak = peak_indices[0]
        period = float(lags[first_peak])
        confidence = float(autocorr[first_peak])

        return {
            "period": period,
            "autocorr": autocorr,
            "lags": lags,
            "peaks": [float(lags[i]) for i in peak_indices[:5]],
            "confidence": round(max(0.0, confidence), 4),
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_periodicity(self, n_periods_required: int = 10) -> dict:
        """Cross-validate FFT vs autocorrelation and assess quality.

        Returns
        -------
        dict
            Keys: ``n_periods_available``, ``is_sufficient``,
            ``period_stability``, ``quality_flag``, ``period``.
        """
        fft = self.detect_period_fft()
        acorr = self.detect_period_autocorr()

        # Consensus period: prefer autocorrelation when both agree
        period_fft = fft["period"]
        period_acorr = acorr["period"]

        if np.isinf(period_fft) and np.isinf(period_acorr):
            return {
                "n_periods_available": 0.0,
                "is_sufficient": False,
                "period_stability": float("inf"),
                "quality_flag": "insufficient",
                "period": float("inf"),
            }

        # If one is inf, use the other
        if np.isinf(period_fft):
            period = period_acorr
        elif np.isinf(period_acorr):
            period = period_fft
        else:
            period = period_acorr  # autocorrelation is more robust for noisy CFD

        total_time = float(self.time[-1] - self.time[0]) if self.time.size > 1 else 0.0
        n_periods = total_time / period if period > 0 else 0.0

        # Period stability: coefficient of variation between FFT and autocorr
        if not (np.isinf(period_fft) or np.isinf(period_acorr)):
            mean_p = (period_fft + period_acorr) / 2
            std_p = abs(period_fft - period_acorr) / 2
            period_stability = std_p / mean_p if mean_p > 0 else float("inf")
        else:
            period_stability = float("inf")

        is_sufficient = n_periods >= n_periods_required

        if is_sufficient and period_stability < 0.05:
            flag = "excellent"
        elif is_sufficient and period_stability < 0.15:
            flag = "good"
        elif n_periods >= n_periods_required / 2:
            flag = "poor"
        else:
            flag = "insufficient"

        return {
            "n_periods_available": round(n_periods, 2),
            "is_sufficient": is_sufficient,
            "period_stability": round(float(period_stability), 4),
            "quality_flag": flag,
            "period": round(period, 4),
        }

    # ------------------------------------------------------------------
    # Phase-locked cycle extraction
    # ------------------------------------------------------------------

    def extract_phase_locked_cycles(self, period: float | None = None) -> np.ndarray:
        """Extract individual cycles aligned in phase.

        Parameters
        ----------
        period : float, optional
            Cycle period in the same units as *time*. Auto-detected if ``None``.

        Returns
        -------
        np.ndarray
            Shape ``(n_cycles, n_points_per_cycle)``.
        """
        if period is None:
            val = self.validate_periodicity()
            period = val["period"]
            if np.isinf(period) or period <= 0:
                return np.empty((0, 0))

        pts_per_cycle = int(round(period / self._dt))
        if pts_per_cycle < 4:
            return np.empty((0, 0))

        n = self.signal.size
        n_cycles = n // pts_per_cycle
        if n_cycles == 0:
            return np.empty((0, 0))

        usable = n_cycles * pts_per_cycle
        return self.signal[:usable].reshape(n_cycles, pts_per_cycle)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_fft(freqs: np.ndarray, spectrum: np.ndarray) -> dict:
        return {
            "period": float("inf"),
            "frequency": 0.0,
            "dominant_frequencies": [],
            "power_spectrum": spectrum,
            "freq_array": freqs,
            "is_periodic": False,
            "confidence": 0.0,
        }

    @staticmethod
    def _empty_autocorr(n: int) -> dict:
        return {
            "period": float("inf"),
            "autocorr": np.zeros(n),
            "lags": np.arange(n, dtype=float),
            "peaks": [],
            "confidence": 0.0,
        }
