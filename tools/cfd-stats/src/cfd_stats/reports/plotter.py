"""Figure generation using the ``plotting`` package.

Produces three diagnostic figures per coefficient:

1. Convergence history (time-series, sliding stats, variance ratio)
2. Periodicity analysis (signal + markers, FFT, autocorrelation, mean cycle)
3. Statistical distribution (histogram, Q-Q plot)

The ``plotting`` package must be importable (i.e. on ``sys.path``).
If it is not available the module raises :class:`ImportError` at import time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from plotting import (
    add_reference_lines,
    add_textbox,
    make_legend,
    new_figure,
    plot_line,
    plot_with_band,
    save_figure,
    set_suptitle,
    set_title,
    use_style,
)

from cfd_stats.analysis.phase_average import phase_average
from cfd_stats.core.convergence import ConvergenceAnalyzer
from cfd_stats.core.periodicity import PeriodicityDetector
from cfd_stats.utils.validation import clean_signal


class StatisticsPlotter:
    """Generate diagnostic figures for CFD statistical analysis.

    Parameters
    ----------
    df : pd.DataFrame
        Simulation data (already filtered by family if needed).
    coeff_cols : list of str
        Coefficient columns to plot.
    iter_col : str
        Iteration / time column.
    results : dict
        Output of :meth:`AutomaticDetector.run_full_analysis`.
    profile : str
        Plotting style profile (``"notebook"``, ``"paper"``, ``"slides"``).
    """

    def __init__(
        self,
        df: pd.DataFrame,
        coeff_cols: Sequence[str],
        iter_col: str,
        results: dict,
        *,
        profile: str = "notebook",
    ) -> None:
        self.df = df
        self.coeff_cols = list(coeff_cols)
        self.iter_col = iter_col
        self.results = results
        self.profile = profile
        self._iters = df[iter_col].to_numpy(dtype=float)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plot_all(self, output_dir: str | Path, *, formats: Sequence[str] = ("png",)) -> list[Path]:
        """Generate all figures for every coefficient.

        Returns
        -------
        list of Path
            All files written to disk.
        """
        use_style(self.profile)
        out = Path(output_dir) / "figures"
        out.mkdir(parents=True, exist_ok=True)
        files: list[Path] = []

        per_coeff = self.results.get("per_coefficient", {})
        for col in self.coeff_cols:
            if col not in per_coeff:
                continue
            data = per_coeff[col]
            signal = clean_signal(self.df[col].to_numpy(dtype=float))
            te_iter = data.get("regime", {}).get("transient_end_iter", 0)
            te_idx = int(np.searchsorted(self._iters, te_iter))

            files += self._plot_convergence(col, signal, te_iter, te_idx, data, out, formats)
            files += self._plot_periodicity(col, signal, te_idx, data, out, formats)
            files += self._plot_distribution(col, signal, te_idx, data, out, formats)

        return files

    # ------------------------------------------------------------------
    # Figure 1 — Convergence history
    # ------------------------------------------------------------------

    def _plot_convergence(
        self, col: str, signal: np.ndarray, te_iter: int, te_idx: int,
        data: dict, out: Path, formats: Sequence[str],
    ) -> list[Path]:
        fig, axes = new_figure(nrows=3, ncols=1, figsize=(12, 9))
        ax_ts, ax_slide, ax_var = axes

        iters = self._iters
        regime = data.get("regime", {})
        moments = data.get("moments", {})
        steady_mean = moments.get("mean", float(signal[te_idx:].mean()))

        # --- Subplot 1: full time-series ---
        plot_line(ax_ts, iters, signal, marker="", label=col, linewidth=0.6)
        add_reference_lines(ax_ts, vlines=[te_iter], color="C3", linestyle="--", linewidth=1.2, label="transient end")
        add_reference_lines(ax_ts, hlines=[steady_mean], color="C2", linestyle=":", linewidth=1.0, label="steady mean")
        set_title(ax_ts, f"{col} — Time-series")
        ax_ts.set_xlabel("Iteration")
        ax_ts.set_ylabel(col)
        add_textbox(
            ax_ts,
            f"regime: {regime.get('regime', '?')}\nquality: {regime.get('quality_score', '?')}",
            loc="upper right",
        )
        make_legend(ax_ts)

        # --- Subplot 2: sliding mean ± std ---
        ca = ConvergenceAnalyzer(self.df, self.iter_col)
        window = max(50, len(self.df) // 50)
        sl = ca.sliding_statistics(col, window_size=window)
        sl_iters = sl["iter"].to_numpy()
        sl_mean = sl["mean"].to_numpy()
        sl_std = sl["std"].to_numpy()

        plot_with_band(
            ax_slide, sl_iters, sl_mean,
            y_low=sl_mean - sl_std,
            y_high=sl_mean + sl_std,
            marker="", label=f"rolling mean (w={window})",
            band_label="± 1 std",
            linewidth=0.8,
        )
        add_reference_lines(ax_slide, vlines=[te_iter], color="C3", linestyle="--", linewidth=1.0)
        set_title(ax_slide, f"{col} — Sliding mean ± std")
        ax_slide.set_xlabel("Iteration")
        ax_slide.set_ylabel(col)
        make_legend(ax_slide)

        # --- Subplot 3: variance ratio ---
        sl_vr = sl["variance_ratio"].to_numpy()
        plot_line(ax_var, sl_iters, sl_vr, marker="", label="variance ratio", linewidth=0.7)
        add_reference_lines(ax_var, hlines=[1.0], color="0.4", linestyle=":", linewidth=0.8)
        add_reference_lines(ax_var, vlines=[te_iter], color="C3", linestyle="--", linewidth=1.0)
        set_title(ax_var, f"{col} — Variance ratio")
        ax_var.set_xlabel("Iteration")
        ax_var.set_ylabel("σ²_local / σ²_global")
        make_legend(ax_var)

        fig.tight_layout(rect=[0, 0, 1, 0.97])
        return save_figure(fig, str(out / f"{col}_convergence"), formats=formats)

    # ------------------------------------------------------------------
    # Figure 2 — Periodicity analysis
    # ------------------------------------------------------------------

    def _plot_periodicity(
        self, col: str, signal: np.ndarray, te_idx: int,
        data: dict, out: Path, formats: Sequence[str],
    ) -> list[Path]:
        fig, axes = new_figure(nrows=2, ncols=2, figsize=(13, 9))
        ax_sig = axes[0, 0]
        ax_fft = axes[0, 1]
        ax_acorr = axes[1, 0]
        ax_cycle = axes[1, 1]

        steady_sig = signal[te_idx:]
        steady_iters = self._iters[te_idx:]
        period_info = data.get("periodicity", {})
        period = period_info.get("period", float("inf"))

        pdet = PeriodicityDetector(steady_sig, steady_iters)
        fft_data = pdet.detect_period_fft()
        acorr_data = pdet.detect_period_autocorr()

        # --- (0,0) Signal with period markers ---
        plot_line(ax_sig, steady_iters, steady_sig, marker="", label=col, linewidth=0.5)
        if np.isfinite(period) and period > 0:
            boundaries = np.arange(steady_iters[0], steady_iters[-1], period)
            if boundaries.size <= 200:
                add_reference_lines(ax_sig, vlines=boundaries.tolist(), color="C1", alpha=0.35, linewidth=0.5)
        set_title(ax_sig, "Steady signal + period boundaries")
        ax_sig.set_xlabel("Iteration")
        ax_sig.set_ylabel(col)

        # --- (0,1) FFT power spectrum ---
        freqs = fft_data["freq_array"]
        spectrum = fft_data["power_spectrum"]
        plot_line(ax_fft, freqs[1:], spectrum[1:], marker="", label="FFT magnitude", linewidth=0.7)
        if fft_data["is_periodic"]:
            add_reference_lines(
                ax_fft, vlines=[fft_data["frequency"]],
                color="C3", linestyle="--", linewidth=1.2, label=f"f = {fft_data['frequency']:.5f}",
            )
        set_title(ax_fft, "FFT power spectrum")
        ax_fft.set_xlabel("Frequency (1/iter)")
        ax_fft.set_ylabel("|FFT|")
        make_legend(ax_fft)

        # --- (1,0) Autocorrelation ---
        lags = acorr_data["lags"]
        autocorr = acorr_data["autocorr"]
        max_lag = min(len(lags), int(10 * period)) if np.isfinite(period) and period > 0 else len(lags) // 2
        plot_line(ax_acorr, lags[:max_lag], autocorr[:max_lag], marker="", label="autocorrelation", linewidth=0.7)
        add_reference_lines(ax_acorr, hlines=[0.0], color="0.4", linestyle=":", linewidth=0.8)
        set_title(ax_acorr, "Autocorrelation")
        ax_acorr.set_xlabel("Lag (iterations)")
        ax_acorr.set_ylabel("R(τ)")

        # --- (1,1) Phase-locked mean cycle ---
        pa = phase_average(signal, self._iters, period=period if np.isfinite(period) else None, transient_end=te_idx)
        if pa["n_cycles"] > 0:
            phase = pa["phase"]
            mean_c = pa["mean_cycle"]
            std_c = pa["std_cycle"]
            plot_with_band(
                ax_cycle, phase, mean_c,
                y_low=mean_c - std_c,
                y_high=mean_c + std_c,
                marker="", label="mean cycle",
                band_label="± 1 std",
                linewidth=1.0,
            )
            add_textbox(
                ax_cycle,
                f"n_cycles: {pa['n_cycles']}\nperiod: {period:.1f}",
                loc="upper right",
            )
            make_legend(ax_cycle)
        else:
            ax_cycle.text(0.5, 0.5, "No periodic cycles detected", ha="center", va="center", transform=ax_cycle.transAxes)
        set_title(ax_cycle, "Phase-locked average")
        ax_cycle.set_xlabel("Phase (rad)")
        ax_cycle.set_ylabel(col)

        set_suptitle(fig, f"{col} — Periodicity analysis")
        fig.tight_layout(rect=[0, 0, 1, 0.95])
        return save_figure(fig, str(out / f"{col}_periodicity"), formats=formats)

    # ------------------------------------------------------------------
    # Figure 3 — Statistical distribution
    # ------------------------------------------------------------------

    def _plot_distribution(
        self, col: str, signal: np.ndarray, te_idx: int,
        data: dict, out: Path, formats: Sequence[str],
    ) -> list[Path]:
        fig, axes = new_figure(nrows=1, ncols=2, figsize=(11, 5))
        ax_hist, ax_qq = axes

        steady = signal[te_idx:]
        moments = data.get("moments", {})

        # --- Histogram ---
        ax_hist.hist(steady, bins="auto", density=True, alpha=0.7, edgecolor="0.3", linewidth=0.5)
        set_title(ax_hist, f"{col} — Distribution (steady state)")
        ax_hist.set_xlabel(col)
        ax_hist.set_ylabel("Density")
        stats_text = (
            f"mean: {moments.get('mean', steady.mean()):.6g}\n"
            f"std: {moments.get('std', steady.std()):.6g}\n"
            f"skew: {moments.get('skewness', '?')}\n"
            f"kurt: {moments.get('excess_kurtosis', '?')}"
        )
        add_textbox(ax_hist, stats_text, loc="upper right")

        # --- Q-Q plot ---
        osm, osr = sp_stats.probplot(steady, dist="norm", fit=False)
        plot_line(ax_qq, osm, osr, marker="o", label="data", markersize=2, linewidth=0)
        # Reference diagonal
        mn, mx = osm.min(), osm.max()
        m_fit, b_fit = np.polyfit(osm, osr, 1)
        ax_qq.plot([mn, mx], [m_fit * mn + b_fit, m_fit * mx + b_fit], "C3--", linewidth=1.0, label="fit")
        set_title(ax_qq, f"{col} — Q-Q plot")
        ax_qq.set_xlabel("Theoretical quantiles")
        ax_qq.set_ylabel("Sample quantiles")
        make_legend(ax_qq)

        fig.tight_layout(rect=[0, 0, 1, 0.97])
        return save_figure(fig, str(out / f"{col}_distribution"), formats=formats)
