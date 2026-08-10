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

Along a sweep
~~~~~~~~~~~~~
    band_from_dispersion      — propagate one bias/scale pair along a curve
    band_from_quantities      — propagate a per-point dispersion along a curve
    DispersionBand            — the resulting nominal / mean / envelope / cloud
    plot_dispersion_band      — draw a DispersionBand (mean + envelope + nominal)
"""

from .core import (
    DISP_TYPE_LABELS,
    DispersionSpec,
    QuantityDispersion,
    dispersion_type_label,
    sigma,
)
from .curve import (
    DispersionBand,
    band_from_dispersion,
    band_from_quantities,
    plot_dispersion_band,
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
    # Along a sweep
    "DispersionBand",
    "band_from_dispersion",
    "band_from_quantities",
    "plot_dispersion_band",
    # Plots
    "plot_dispersion_cdf",
    "plot_dispersion_dashboard",
    "plot_dispersion_matrix",
    "plot_dispersion_pdf",
    "plot_dispersion_type",
]
