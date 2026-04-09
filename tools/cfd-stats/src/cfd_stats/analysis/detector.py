"""Automatic regime detection pipeline.

:class:`AutomaticDetector` runs convergence, periodicity, moments and
quality analysis for every coefficient in a DataFrame, then produces a
per-coefficient and global assessment dict.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import pandas as pd

from cfd_stats.config import AnalysisConfig
from cfd_stats.core.convergence import ConvergenceAnalyzer
from cfd_stats.core.moments import MomentCalculator
from cfd_stats.core.periodicity import PeriodicityDetector
from cfd_stats.core.quality import compute_quality_metrics


class AutomaticDetector:
    """Run the full analysis pipeline for a set of coefficients.

    Parameters
    ----------
    df : pd.DataFrame
        Simulation data.
    coeff_cols : list of str
        Columns to analyse.
    iter_col : str
        Iteration / time column name.
    config : AnalysisConfig, optional
        Override default analysis parameters.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        coeff_cols: Sequence[str],
        iter_col: str = "iter",
        config: AnalysisConfig | None = None,
    ) -> None:
        self.df = df
        self.coeff_cols = list(coeff_cols)
        self.iter_col = iter_col
        self.cfg = config or AnalysisConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_full_analysis(self) -> dict:
        """Execute the full pipeline.

        Returns
        -------
        dict
            Top-level keys: ``per_coefficient``, ``global_assessment``.
        """
        conv = ConvergenceAnalyzer(self.df, self.iter_col)
        iters = self.df[self.iter_col].to_numpy(dtype=float)

        per_coeff: dict[str, dict] = {}

        for col in self.coeff_cols:
            signal = self.df[col].to_numpy(dtype=float)
            regime = conv.detect_regime(col)
            convergence = conv.compute_convergence_metrics(col)

            pdet = PeriodicityDetector(signal, iters)
            periodicity_val = pdet.validate_periodicity(n_periods_required=self.cfg.min_periods_required)
            periodicity_fft = pdet.detect_period_fft()

            # Compute moments on the steady part
            te_idx = self._iter_to_index(regime["transient_end_iter"])
            steady = signal[te_idx:]
            if steady.size >= 10:
                mc = MomentCalculator(steady)
                moments = mc.compute_all_moments(max_order=self.cfg.max_moment_order)
                robust = mc.compute_robust_statistics()
                ci = mc.compute_confidence_intervals(
                    confidence=self.cfg.confidence_level,
                    n_bootstrap=self.cfg.bootstrap_samples,
                )
                gof = mc.goodness_of_fit()
                moments.update(robust)
                moments["confidence_intervals"] = ci
            else:
                moments = {}
                gof = {}

            quality = compute_quality_metrics(signal)

            per_coeff[col] = {
                "regime": regime,
                "convergence": convergence,
                "periodicity": {
                    "detected": periodicity_val["quality_flag"] not in ("insufficient",),
                    "period": periodicity_val["period"],
                    "frequency": (
                        periodicity_fft["frequency"] if periodicity_fft["is_periodic"] else 0.0
                    ),
                    "n_periods": periodicity_val["n_periods_available"],
                    "confidence": periodicity_fft["confidence"],
                    "quality_flag": periodicity_val["quality_flag"],
                    "method": "autocorrelation",
                },
                "moments": moments,
                "quality": {
                    **quality,
                    "is_normal": gof.get("is_normal", False),
                    "recommended_distribution": gof.get("recommended_distribution", "unknown"),
                },
            }

        global_assessment = self._compute_global(per_coeff)

        return {
            "per_coefficient": per_coeff,
            "global_assessment": global_assessment,
        }

    def detect_transient_end(self, signal: np.ndarray) -> int:
        """Detect end of transient phase using CUSUM.

        Delegates to :class:`ConvergenceAnalyzer` internal method.

        Returns
        -------
        int
            Index in *signal* where the transient ends.
        """
        return ConvergenceAnalyzer._detect_transient_end(None, signal)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _iter_to_index(self, target_iter: int) -> int:
        iters = self.df[self.iter_col].to_numpy()
        idx = int(np.searchsorted(iters, target_iter))
        return min(idx, len(iters) - 1)

    @staticmethod
    def _compute_global(per_coeff: dict[str, dict]) -> dict:
        regimes = [v["regime"]["regime"] for v in per_coeff.values()]
        converged_flags = [v["convergence"]["is_converged"] for v in per_coeff.values()]
        qualities = [v["regime"]["quality_score"] for v in per_coeff.values()]

        all_converged = all(converged_flags)

        if all_converged:
            overall = "converged"
        elif "periodic" in regimes:
            overall = "periodic"
        elif "diverging" in regimes:
            overall = "diverging"
        else:
            overall = "transient"

        avg_quality = float(np.mean(qualities)) if qualities else 0.0

        recommendation = _build_recommendation(overall, all_converged, avg_quality)

        return {
            "overall_regime": overall,
            "all_converged": all_converged,
            "quality_score": round(avg_quality, 2),
            "recommendation": recommendation,
        }


def _build_recommendation(regime: str, all_converged: bool, quality: float) -> str:
    if regime == "diverging":
        return "Simulation is diverging – check boundary conditions, mesh quality, and numerical schemes."
    if regime == "transient":
        return "Still in transient – continue the simulation before computing statistics."
    if regime == "periodic":
        if quality > 80:
            return "Periodic regime well established. Phase-averaged statistics are meaningful."
        return "Periodic regime detected but quality is low. Consider running more iterations."
    if all_converged and quality > 90:
        return "All coefficients converged with high quality. Results are publication-ready."
    if all_converged:
        return "Converged, but some quality scores are moderate. Review individual coefficients."
    return "Mixed regime across coefficients – inspect each one individually."
