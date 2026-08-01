"""cfd-stats – Automatic convergence analysis and statistics for CFD time-series."""

from __future__ import annotations

from cfd_stats.__version__ import __version__
from cfd_stats.analysis.detector import AutomaticDetector
from cfd_stats.analysis.family_compare import compare_families, families_to_dataframe
from cfd_stats.analysis.phase_average import phase_average
from cfd_stats.config import AnalysisConfig
from cfd_stats.core.convergence import ConvergenceAnalyzer
from cfd_stats.core.moments import MomentCalculator
from cfd_stats.core.periodicity import PeriodicityDetector
from cfd_stats.core.quality import compute_quality_metrics
from cfd_stats.reports.console import ConsoleReporter
from cfd_stats.utils.dataframe import load_dataframe

# StatisticsPlotter requires the sibling ``cfd-plot`` package
# (``pip install -e tools/cfd-plot``); import lazily so the rest of
# cfd_stats works without it.
try:
    from cfd_stats.reports.plotter import StatisticsPlotter
except ImportError:
    StatisticsPlotter = None  # type: ignore[assignment,misc]

__all__ = [
    "__version__",
    "AnalysisConfig",
    "AutomaticDetector",
    "ConsoleReporter",
    "ConvergenceAnalyzer",
    "MomentCalculator",
    "PeriodicityDetector",
    "StatisticsPlotter",
    "compare_families",
    "compute_quality_metrics",
    "families_to_dataframe",
    "load_dataframe",
    "phase_average",
]
