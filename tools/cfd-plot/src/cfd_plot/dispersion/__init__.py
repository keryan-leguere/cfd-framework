"""
dispersion — Statistical dispersion visualisation for Monte Carlo analyses.

Run from ``tools/cfd-plot`` with ``PYTHONPATH=.``::

    python demo_dispersion.py
    pytest dispersion/tests -q

Public API
----------
Core
~~~~
    DispersionSpec        — one dispersion component (bias or scale)
    QuantityDispersion    — nominal quantity with bias + scale specs
    dispersion_type_label — human-readable label for a type integer
    DISP_TYPE_LABELS      — {int: str} mapping for all 6 types

Plotting
~~~~~~~~
    plot_dispersion_type      — illustrative PDF shape panel
    plot_dispersion_pdf       — histogram + KDE with nominal / mean / std markers
    plot_dispersion_cdf       — empirical CDF with percentile guides
    plot_dispersion_dashboard — 3-panel figure (bias | PDF | scale)
    plot_dispersion_matrix    — grid of PDF subplots for a quantity list
"""

from .core import (
    DISP_TYPE_LABELS,
    DispersionSpec,
    QuantityDispersion,
    dispersion_type_label,
    sigma,
)
from .plots import (
    plot_dispersion_cdf,
    plot_dispersion_dashboard,
    plot_dispersion_matrix,
    plot_dispersion_pdf,
    plot_dispersion_type,
)

__all__ = [
    # Core
    "DispersionSpec",
    "QuantityDispersion",
    "DISP_TYPE_LABELS",
    "dispersion_type_label",
    "sigma",
    # Plots
    "plot_dispersion_cdf",
    "plot_dispersion_dashboard",
    "plot_dispersion_matrix",
    "plot_dispersion_pdf",
    "plot_dispersion_type",
]
